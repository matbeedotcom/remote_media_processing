#!/usr/bin/env python3
"""
WebRTC Server with Pipeline Integration Example.

This example demonstrates how to create a WebRTC server that processes
audio and video streams through RemoteMedia pipelines in real-time.

**Features:**
- Real-time audio processing with VAD and speech recognition
- Video processing capabilities
- Data channel communication
- Multiple concurrent WebRTC connections
- Integration with remote execution services

**TO RUN THIS EXAMPLE:**

1.  **Install WebRTC dependencies:**
    $ pip install aiortc aiohttp aiohttp-cors

2.  **Install ML dependencies (optional):**
    $ pip install -r requirements-ml.txt

3.  **Start the remote service (if using remote nodes):**
    $ PYTHONPATH=. python remote_service/src/server.py

4.  **Run the WebRTC server:**
    $ python examples/webrtc_pipeline_server.py

5.  **Connect with a WebRTC client:**
    - Open a WebRTC client application
    - Connect to ws://localhost:8080/ws for signaling
    - The server will process your audio/video streams through the pipeline

**Example Client HTML:**
Save this as 'client.html' and open in a browser:

```html
<!DOCTYPE html>
<html>
<head>
    <title>WebRTC Pipeline Client</title>
</head>
<body>
    <h1>WebRTC Pipeline Client</h1>
    <video id="localVideo" autoplay muted width="320" height="240"></video>
    <video id="remoteVideo" autoplay width="320" height="240"></video>
    <br>
    <button id="startBtn">Start Call</button>
    <button id="stopBtn" disabled>Stop Call</button>
    <br>
    <div id="status">Disconnected</div>
    <div id="messages"></div>

    <script>
        const localVideo = document.getElementById('localVideo');
        const remoteVideo = document.getElementById('remoteVideo');
        const startBtn = document.getElementById('startBtn');
        const stopBtn = document.getElementById('stopBtn');
        const status = document.getElementById('status');
        const messages = document.getElementById('messages');

        let pc = null;
        let ws = null;
        let localStream = null;

        startBtn.onclick = start;
        stopBtn.onclick = stop;

        async function start() {
            // Get user media
            localStream = await navigator.mediaDevices.getUserMedia({
                video: true,
                audio: true
            });
            localVideo.srcObject = localStream;

            // Create peer connection
            pc = new RTCPeerConnection({
                iceServers: [{ urls: 'stun:stun.l.google.com:19302' }]
            });

            // Add tracks
            localStream.getTracks().forEach(track => {
                pc.addTrack(track, localStream);
            });

            // Handle remote stream
            pc.ontrack = (event) => {
                remoteVideo.srcObject = event.streams[0];
            };

            // Create data channel
            const dataChannel = pc.createDataChannel('messages');
            dataChannel.onopen = () => {
                console.log('Data channel opened');
                dataChannel.send('Hello from client!');
            };
            dataChannel.onmessage = (event) => {
                messages.innerHTML += '<div>Received: ' + event.data + '</div>';
            };

            // Connect WebSocket
            ws = new WebSocket('ws://localhost:8080/ws');
            ws.onopen = () => {
                status.textContent = 'Connected';
            };
            ws.onmessage = async (event) => {
                const message = JSON.parse(event.data);
                if (message.type === 'answer') {
                    await pc.setRemoteDescription(new RTCSessionDescription(message));
                }
            };

            // Create offer
            const offer = await pc.createOffer();
            await pc.setLocalDescription(offer);
            ws.send(JSON.stringify({
                type: 'offer',
                sdp: offer.sdp
            }));

            startBtn.disabled = true;
            stopBtn.disabled = false;
        }

        async function stop() {
            if (localStream) {
                localStream.getTracks().forEach(track => track.stop());
            }
            if (pc) {
                pc.close();
            }
            if (ws) {
                ws.close();
            }
            status.textContent = 'Disconnected';
            startBtn.disabled = false;
            stopBtn.disabled = true;
        }
    </script>
</body>
</html>
```
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from remotemedia.core.pipeline import Pipeline
from remotemedia.core.node import RemoteExecutorConfig
from remotemedia.nodes.audio import AudioTransform, VoiceActivityDetector
from remotemedia.nodes.ml import WhisperTranscriptionNode, KokoroTTSNode
from remotemedia.nodes.transform import TextTransformNode
from remotemedia.nodes import PassThroughNode
from remotemedia.webrtc import WebRTCServer, WebRTCConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Reduce noise from some loggers
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("aiortc").setLevel(logging.WARNING)


class MessageLoggingNode(PassThroughNode):
    """Node that logs processed messages."""
    
    def __init__(self, message_prefix: str = "", **kwargs):
        super().__init__(**kwargs)
        self.message_prefix = message_prefix
        
    def process(self, data):
        """Log the data and pass it through."""
        if isinstance(data, str):
            logger.info(f"{self.message_prefix}: {data}")
        elif isinstance(data, dict):
            if 'type' in data:
                logger.info(f"{self.message_prefix} ({data['type']}): {data}")
            else:
                logger.info(f"{self.message_prefix}: {data}")
        else:
            logger.info(f"{self.message_prefix}: {type(data)} - {data}")
        return data


def create_audio_processing_pipeline() -> Pipeline:
    """
    Create a pipeline for processing audio streams from WebRTC.
    
    This pipeline:
    1. Receives audio from WebRTC
    2. Applies audio transforms (resampling, etc.)
    3. Performs voice activity detection
    4. Transcribes speech using Whisper
    5. Optionally processes text
    6. Synthesizes response using Kokoro TTS
    """
    pipeline = Pipeline()
    
    # Audio preprocessing
    pipeline.add_node(AudioTransform(
        output_sample_rate=16000,
        output_channels=1,
        name="AudioPreprocess"
    ))
    
    # Voice Activity Detection
    vad = VoiceActivityDetector(
        frame_duration_ms=30,
        energy_threshold=0.02,
        speech_threshold=0.3,
        filter_mode=True,  # Only pass speech
        include_metadata=False,
        name="VAD"
    )
    pipeline.add_node(vad)
    
    # Speech Recognition
    whisper = WhisperTranscriptionNode(
        model_size="base",
        language="en",
        name="WhisperASR"
    )
    pipeline.add_node(whisper)
    
    # Text Processing (simple echo with prefix)
    text_processor = TextTransformNode(
        transform_func=lambda text: f"Server received: {text}",
        name="TextProcessor"
    )
    pipeline.add_node(text_processor)
    
    # Log processed text
    pipeline.add_node(MessageLoggingNode(
        message_prefix="🎤 TRANSCRIBED",
        name="TextLogger"
    ))
    
    # Text-to-Speech (optional - enable if you want audio responses)
    tts = KokoroTTSNode(
        lang_code='a',  # American English
        voice='af_heart',
        speed=1.0,
        sample_rate=24000,
        stream_chunks=True,
        name="KokoroTTS"
    )
    pipeline.add_node(tts)
    
    # Log audio output
    pipeline.add_node(MessageLoggingNode(
        message_prefix="🔊 SYNTHESIZED",
        name="AudioLogger"
    ))
    
    return pipeline


def create_simple_pipeline() -> Pipeline:
    """
    Create a simple pipeline for testing without ML dependencies.
    """
    pipeline = Pipeline()
    
    # Simple audio processing
    pipeline.add_node(AudioTransform(
        output_sample_rate=16000,
        output_channels=1,
        name="AudioPreprocess"
    ))
    
    # Log audio data
    pipeline.add_node(MessageLoggingNode(
        message_prefix="🎵 AUDIO",
        name="AudioLogger"
    ))
    
    return pipeline


def create_data_channel_pipeline() -> Pipeline:
    """
    Create a pipeline for processing WebRTC data channel messages.
    """
    pipeline = Pipeline()
    
    # Log data channel messages
    pipeline.add_node(MessageLoggingNode(
        message_prefix="📡 DATA CHANNEL",
        name="DataChannelLogger"
    ))
    
    # Echo messages back with prefix
    echo_processor = TextTransformNode(
        transform_func=lambda data: f"Echo: {data}",
        name="EchoProcessor"
    )
    pipeline.add_node(echo_processor)
    
    return pipeline


async def main():
    """Run the WebRTC server with pipeline integration."""
    
    # Configuration
    USE_ML_PIPELINE = os.environ.get("USE_ML", "false").lower() == "true"
    REMOTE_HOST = os.environ.get("REMOTE_HOST", "127.0.0.1")
    SERVER_HOST = os.environ.get("SERVER_HOST", "0.0.0.0")
    SERVER_PORT = int(os.environ.get("SERVER_PORT", "8080"))
    
    logger.info("=== WebRTC Pipeline Server ===")
    logger.info(f"Server: {SERVER_HOST}:{SERVER_PORT}")
    logger.info(f"ML Pipeline: {'Enabled' if USE_ML_PIPELINE else 'Disabled'}")
    logger.info(f"Remote Host: {REMOTE_HOST}")
    
    # Create server configuration
    examples_dir = Path(__file__).parent
    config = WebRTCConfig(
        host=SERVER_HOST,
        port=SERVER_PORT,
        enable_cors=True,
        stun_servers=["stun:stun.l.google.com:19302"],
        static_files_path=str(examples_dir)  # Serve client files from examples directory
    )
    
    # Pipeline factory function
    def create_pipeline() -> Pipeline:
        if USE_ML_PIPELINE:
            try:
                return create_audio_processing_pipeline()
            except ImportError as e:
                logger.warning(f"ML dependencies not available: {e}")
                logger.info("Falling back to simple pipeline")
                return create_simple_pipeline()
        else:
            return create_simple_pipeline()
    
    # Create and start server
    server = WebRTCServer(config=config, pipeline_factory=create_pipeline)
    
    try:
        await server.start()
        
        logger.info("WebRTC server is running!")
        logger.info("Connect with a WebRTC client:")
        logger.info(f"  📱 Web Client: http://localhost:{SERVER_PORT}/webrtc_client.html")
        logger.info(f"  🌐 WebSocket: ws://{SERVER_HOST}:{SERVER_PORT}/ws")
        logger.info(f"  ❤️  Health check: http://{SERVER_HOST}:{SERVER_PORT}/health")
        logger.info(f"  📊 Connections: http://{SERVER_HOST}:{SERVER_PORT}/connections")
        
        if not USE_ML_PIPELINE:
            logger.info("")
            logger.info("💡 To enable ML features (speech recognition, TTS):")
            logger.info("   1. Install ML dependencies: pip install -r requirements-ml.txt")
            logger.info("   2. Set environment variable: USE_ML=true")
            logger.info("   3. Start remote service if using remote execution")
        
        logger.info("")
        logger.info("Press Ctrl+C to stop the server")
        
        # Keep the server running
        while True:
            await asyncio.sleep(10)
            
            # Log connection statistics
            connections_count = len(server.connections)
            if connections_count > 0:
                logger.info(f"Active connections: {connections_count}")
                
    except KeyboardInterrupt:
        logger.info("Shutting down server...")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
    finally:
        await server.stop()
        logger.info("Server stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logging.error(f"Failed to start server: {e}", exc_info=True)