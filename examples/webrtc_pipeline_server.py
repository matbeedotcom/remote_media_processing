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
from remotemedia.core.node import RemoteExecutorConfig, Node
from remotemedia.nodes.audio import AudioTransform, VoiceActivityDetector
from remotemedia.nodes.ml import UltravoxNode, KokoroTTSNode
from remotemedia.nodes.transform import TextTransformNode
from remotemedia.nodes.remote import RemoteObjectExecutionNode
from remotemedia.nodes import PassThroughNode
from remotemedia.webrtc import WebRTCServer, WebRTCConfig
import numpy as np
from typing import AsyncGenerator, Any, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Reduce noise from some loggers
logging.getLogger("aiohttp").setLevel(logging.WARNING)
logging.getLogger("aiortc").setLevel(logging.WARNING)
logging.getLogger("remotemedia.core.pipeline").setLevel(logging.WARNING)  # Reduce pipeline worker noise
logging.getLogger("Pipeline").setLevel(logging.WARNING)  # Class-based logger name

# Also suppress after import
import logging
logging.getLogger("Pipeline").setLevel(logging.ERROR)
logging.getLogger("remotemedia.core.pipeline").setLevel(logging.ERROR)


class VADLoggingNode(PassThroughNode):
    """Node that logs VAD events for debugging."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.frame_count = 0
        self._last_is_speech = None
        
    def process(self, data):
        """Log VAD metadata and pass data through."""
        if isinstance(data, tuple) and len(data) == 2:
            item1, item2 = data
            
            # Check if this is VAD output: ((audio_data, sample_rate), vad_metadata)
            if isinstance(item2, dict) and isinstance(item1, tuple) and len(item1) == 2:
                audio_data, sample_rate = item1
                vad_metadata = item2
                
                if isinstance(audio_data, np.ndarray):
                    self.frame_count += 1
                    is_speech = vad_metadata.get("is_speech", False)
                    speech_ratio = vad_metadata.get("speech_ratio", 0.0)
                    avg_energy = vad_metadata.get("avg_energy", 0.0)
                    
                    # Only log speech transitions and periodic updates
                    should_log = False
                    
                    # Log speech start/end transitions
                    if self._last_is_speech is not None:
                        if not self._last_is_speech and is_speech:
                            logger.info("🟢 WebRTC VAD: SPEECH STARTED")
                            should_log = True
                        elif self._last_is_speech and not is_speech:
                            logger.info("🔴 WebRTC VAD: SPEECH ENDED")
                            should_log = True
                    
                    # Log periodic status (every 50 frames = ~2 seconds)
                    if self.frame_count % 50 == 0:
                        should_log = True
                    
                    if should_log:
                        speech_indicator = "🎤 SPEECH" if is_speech else "🔇 SILENCE"
                        logger.info(f"WebRTC VAD #{self.frame_count}: {speech_indicator} | ratio={speech_ratio:.3f} | energy={avg_energy:.4f}")
                    
                    self._last_is_speech = is_speech
        
        return data


class VADTriggeredBuffer(Node):
    """
    A buffer that accumulates speech audio and triggers output only when speech ends.
    
    This node:
    1. Maintains a rolling buffer of the past 1 second of audio (pre-speech context)
    2. Accumulates audio chunks that contain speech
    3. Tracks speech/silence state transitions
    4. Outputs accumulated speech audio only when:
       - Speech ends (VAD transitions to silence for sufficient duration)
       - At least minimum duration of speech was accumulated
    """
    
    def __init__(
        self,
        min_speech_duration_s: float = 1.0,
        max_speech_duration_s: float = 10.0,
        silence_duration_s: float = 0.5,
        pre_speech_buffer_s: float = 1.0,
        sample_rate: int = 16000,
        **kwargs
    ):
        """
        Initialize the VAD-triggered buffer.
        
        Args:
            min_speech_duration_s: Minimum speech duration before triggering (default: 1.0s)
            max_speech_duration_s: Maximum speech duration (forces trigger, default: 10.0s)
            silence_duration_s: Duration of silence needed to confirm speech end (default: 0.5s)
            pre_speech_buffer_s: Duration of audio to buffer before speech starts (default: 1.0s)
            sample_rate: Expected audio sample rate (default: 16000)
        """
        super().__init__(**kwargs)
        self.min_speech_duration_s = min_speech_duration_s
        self.max_speech_duration_s = max_speech_duration_s
        self.silence_duration_s = silence_duration_s
        self.pre_speech_buffer_s = pre_speech_buffer_s
        self.sample_rate = sample_rate
        self.is_streaming = True
        
        # State tracking
        self._speech_buffer = None
        self._pre_speech_buffer = []  # Rolling buffer for pre-speech context
        self._is_in_speech = False
        self._silence_accumulated_samples = 0
        self._speech_samples_count = 0  # Track actual speech samples (not including pre-buffer)
        
        # Derived parameters
        self.min_samples = int(min_speech_duration_s * sample_rate)
        self.max_samples = int(max_speech_duration_s * sample_rate)
        self.silence_samples = int(silence_duration_s * sample_rate)
        self.pre_speech_samples = int(pre_speech_buffer_s * sample_rate)
        
    async def process(self, data_stream: AsyncGenerator[Any, None]) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
        """
        Process VAD-annotated audio stream and trigger output on speech end.
        
        Expected input: ((audio_data, sample_rate), vad_metadata) tuples
        """
        async for data in data_stream:
            # Debug the data format
            logger.debug(f"VADTriggeredBuffer: Received data type: {type(data)}")
            
            if not isinstance(data, tuple) or len(data) != 2:
                logger.warning(f"VADTriggeredBuffer: Invalid input format: {type(data)}, len: {len(data) if hasattr(data, '__len__') else 'N/A'}")
                continue
                
            # The VAD output format is: ((audio_data, sample_rate), vad_metadata)
            item1, item2 = data
            
            if isinstance(item2, dict):
                # Correct format: ((audio_data, sample_rate), vad_metadata)
                if isinstance(item1, tuple) and len(item1) == 2:
                    audio_data, sample_rate = item1
                    vad_metadata = item2
                else:
                    logger.warning(f"VADTriggeredBuffer: Expected (audio_data, sample_rate) tuple, got {type(item1)}")
                    continue
            else:
                logger.warning(f"VADTriggeredBuffer: Expected VAD metadata dict as second item, got {type(item2)}")
                continue
                
            if not isinstance(audio_data, np.ndarray):
                logger.warning(f"VADTriggeredBuffer: Expected numpy array audio, got {type(audio_data)}")
                continue
                
            # Ensure consistent sample rate
            if sample_rate != self.sample_rate:
                logger.warning(f"VADTriggeredBuffer: Sample rate mismatch: {sample_rate} vs {self.sample_rate}")
                continue
                
            # Flatten audio to 1D for processing
            if audio_data.ndim > 1:
                audio_flat = audio_data.flatten()
            else:
                audio_flat = audio_data
                
            is_speech = vad_metadata.get("is_speech", False)
            speech_ratio = vad_metadata.get("speech_ratio", 0.0)
            avg_energy = vad_metadata.get("avg_energy", 0.0)
            chunk_samples = len(audio_flat)
            
            # Always maintain the pre-speech rolling buffer
            self._maintain_pre_speech_buffer(audio_flat)
            
            pre_buffer_duration = sum(len(chunk) for chunk in self._pre_speech_buffer) / self.sample_rate
            speech_buffer_duration = len(self._speech_buffer) / self.sample_rate if self._speech_buffer is not None else 0
            
            # Only log significant VAD buffer events
            if is_speech and not self._is_in_speech:
                # Speech starting
                logger.info(f"VADTriggeredBuffer: Speech starting | ratio={speech_ratio:.2f}, energy={avg_energy:.4f}")
            elif not is_speech and self._is_in_speech and self._silence_accumulated_samples > 0:
                # In silence after speech
                silence_duration_s = self._silence_accumulated_samples / self.sample_rate
                if silence_duration_s % 0.25 < 0.04:  # Log every 250ms of accumulated silence
                    logger.debug(f"VADTriggeredBuffer: Accumulating silence {silence_duration_s:.2f}s (need {self.silence_duration_s:.2f}s)")
            
            # Process based on speech state
            if is_speech:
                triggered_audio = await self._handle_speech_chunk(audio_flat, chunk_samples)
                if triggered_audio is not None:
                    logger.info(
                        f"VADTriggeredBuffer: Triggering on max duration "
                        f"({len(triggered_audio)/self.sample_rate:.2f}s total audio)"
                    )
                    yield (triggered_audio.reshape(1, -1), self.sample_rate)
            else:
                # Check if we should trigger on silence
                triggered_audio = await self._handle_silence_chunk(audio_flat, chunk_samples)
                if triggered_audio is not None:
                    logger.info(
                        f"VADTriggeredBuffer: Triggering on speech end "
                        f"({len(triggered_audio)/self.sample_rate:.2f}s total audio)"
                    )
                    yield (triggered_audio.reshape(1, -1), self.sample_rate)
                    
    def _maintain_pre_speech_buffer(self, audio_chunk: np.ndarray):
        """Maintain a rolling buffer of pre-speech audio."""
        self._pre_speech_buffer.append(audio_chunk.copy())
        
        # Calculate total samples in buffer
        total_samples = sum(len(chunk) for chunk in self._pre_speech_buffer)
        
        # Remove oldest chunks if buffer exceeds target duration
        while total_samples > self.pre_speech_samples and len(self._pre_speech_buffer) > 1:
            removed = self._pre_speech_buffer.pop(0)
            total_samples -= len(removed)
    
    async def _handle_speech_chunk(self, audio_chunk: np.ndarray, chunk_samples: int) -> Optional[np.ndarray]:
        """Handle a chunk containing speech. Returns audio if max duration reached."""
        if not self._is_in_speech:
            # Starting new speech segment - include pre-speech context
            logger.info("VADTriggeredBuffer: Speech started - including pre-speech context")
            self._is_in_speech = True
            
            # Start with pre-speech buffer
            if self._pre_speech_buffer:
                self._speech_buffer = np.concatenate(self._pre_speech_buffer)
                pre_speech_duration = len(self._speech_buffer) / self.sample_rate
                logger.info(f"VADTriggeredBuffer: Added {pre_speech_duration:.2f}s of pre-speech context")
            else:
                self._speech_buffer = np.array([], dtype=np.float32)
            
            # Add current speech chunk
            self._speech_buffer = np.concatenate([self._speech_buffer, audio_chunk])
            self._speech_samples_count = chunk_samples  # Only count actual speech samples
            self._silence_accumulated_samples = 0  # Reset silence counter
        else:
            # Continuing speech segment
            if self._speech_buffer is not None:
                self._speech_buffer = np.concatenate([self._speech_buffer, audio_chunk])
                self._speech_samples_count += chunk_samples  # Track actual speech samples
                # Reset silence counter when speech continues
                self._silence_accumulated_samples = 0
                
                # Check if we've exceeded max duration (based on total buffer, including pre-speech)
                total_duration_s = len(self._speech_buffer) / self.sample_rate
                if total_duration_s >= self.max_speech_duration_s:
                    logger.info(
                        f"VADTriggeredBuffer: Max duration reached "
                        f"({total_duration_s:.2f}s total, {self._speech_samples_count/self.sample_rate:.2f}s speech), forcing trigger"
                    )
                    # Trigger and reset
                    triggered_audio = self._speech_buffer.copy()
                    self._reset_state()
                    return triggered_audio
                    
        return None
        
    async def _handle_silence_chunk(self, silence_chunk: np.ndarray, chunk_samples: int) -> Optional[np.ndarray]:
        """Handle a chunk containing silence. Returns audio if trigger conditions are met."""
        if not self._is_in_speech or self._speech_buffer is None:
            # Reset silence tracking if we're not in speech
            self._silence_accumulated_samples = 0
            return None
            
        # Add the silence chunk to the buffer first (to preserve natural pauses)
        self._speech_buffer = np.concatenate([self._speech_buffer, silence_chunk])
        
        # Accumulate silence duration
        self._silence_accumulated_samples += chunk_samples
        silence_duration_s = self._silence_accumulated_samples / self.sample_rate
        
        logger.debug(f"VADTriggeredBuffer: Accumulated {silence_duration_s:.2f}s of silence (need {self.silence_duration_s:.2f}s)")
        
        # Check if we have enough silence to confirm speech end
        if self._silence_accumulated_samples >= self.silence_samples:
            # Check if we have minimum speech duration (based on actual speech samples, not including pre-buffer)
            speech_duration_s = self._speech_samples_count / self.sample_rate
            total_duration_s = len(self._speech_buffer) / self.sample_rate
            
            if self._speech_samples_count >= self.min_samples:
                # Trigger!
                logger.info(f"VADTriggeredBuffer: Speech end confirmed after {silence_duration_s:.2f}s silence "
                           f"(speech: {speech_duration_s:.2f}s, total: {total_duration_s:.2f}s)")
                triggered_audio = self._speech_buffer.copy()
                self._reset_state()
                return triggered_audio
            else:
                logger.debug(
                    f"VADTriggeredBuffer: Speech too short "
                    f"({speech_duration_s:.2f}s < {self.min_speech_duration_s}s), discarding"
                )
                self._reset_state()
                
        return None
        
    def _reset_state(self):
        """Reset the buffer state."""
        self._speech_buffer = None
        self._is_in_speech = False
        self._silence_accumulated_samples = 0
        self._speech_samples_count = 0
        # Keep the pre-speech buffer for the next utterance


class UltravoxImmediateProcessor(Node):
    """
    Wrapper around UltravoxNode that processes complete utterances immediately.
    
    This bypasses UltravoxNode's internal buffering and processes each complete
    utterance from VAD immediately, then clears the internal buffer.
    """
    
    def __init__(self, ultravox_node, min_duration_s: float = 1.0, sample_rate: int = 16000, **kwargs):
        super().__init__(**kwargs)
        self.ultravox_node = ultravox_node
        self.min_duration_s = min_duration_s
        self.sample_rate = sample_rate
        self.min_samples = int(min_duration_s * sample_rate)
        self.is_streaming = True
        
    async def initialize(self):
        """Initialize the wrapped Ultravox node."""
        if not self.ultravox_node.is_initialized:
            await self.ultravox_node.initialize()
        
    async def flush(self):
        """Flush the wrapped Ultravox node."""
        if hasattr(self.ultravox_node, 'flush'):
            return await self.ultravox_node.flush()
        return None
        
    async def cleanup(self):
        """Cleanup the wrapped Ultravox node."""
        await self.ultravox_node.cleanup()
        
    async def process(self, data_stream):
        """Process complete utterances immediately."""
        async for data in data_stream:
            if isinstance(data, tuple) and len(data) == 2:
                audio_data, sample_rate = data
                if isinstance(audio_data, np.ndarray):
                    duration_s = audio_data.size / sample_rate
                    if duration_s >= self.min_duration_s:
                        logger.info(f"UltravoxProcessor: Processing complete {duration_s:.2f}s utterance immediately")
                        
                        # Clear any existing buffer to prevent accumulation
                        self.ultravox_node.audio_buffer = np.array([], dtype=np.float32)
                        
                        # Process the complete utterance directly
                        if self.ultravox_node.llm_pipeline:
                            audio_flat = audio_data.flatten().astype(np.float32)
                            response = await self.ultravox_node._generate_response(audio_flat)
                            if response:
                                logger.info(f"UltravoxProcessor: Generated response for {duration_s:.2f}s utterance")
                                yield (response,)
                        else:
                            logger.error("UltravoxProcessor: Pipeline not initialized")
                    else:
                        logger.warning(f"UltravoxProcessor: Rejecting {duration_s:.2f}s of audio (< {self.min_duration_s:.2f}s minimum)")
            else:
                # Pass through non-audio data
                yield data


class TextLoggingNode(PassThroughNode):
    """Node that logs text responses from Ultravox."""
    
    def process(self, data):
        """Log text responses."""
        if isinstance(data, (str, tuple)):
            text = data[0] if isinstance(data, tuple) else data
            print(f"\n🎤 ULTRAVOX RESPONSE: {text}\n")
        return data


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


def create_speech_to_speech_pipeline(remote_host: str = "127.0.0.1") -> Pipeline:
    """
    Create a VAD-triggered Ultravox + Kokoro TTS pipeline for WebRTC.
    
    This pipeline implements a complete speech-to-speech system:
    1. Receives audio from WebRTC client
    2. Applies audio transforms (resampling, etc.)
    3. Performs voice activity detection with metadata
    4. Buffers speech segments until speech ends
    5. Processes complete utterances with Ultravox
    6. Synthesizes responses using Kokoro TTS
    7. Streams audio back to WebRTC client
    """
    pipeline = Pipeline()
    
    # Audio preprocessing - resample for VAD and Ultravox
    pipeline.add_node(AudioTransform(
        output_sample_rate=16000,
        output_channels=1,
        name="AudioTransform"
    ))
    
    # Voice Activity Detection with metadata
    vad = VoiceActivityDetector(
        frame_duration_ms=30,
        energy_threshold=0.02,
        speech_threshold=0.3,
        filter_mode=False,  # Keep metadata for buffering
        include_metadata=True,
        name="VAD"
    )
    vad.is_streaming = True
    pipeline.add_node(vad)
    
    # Add VAD logging for debugging microphone input
    pipeline.add_node(VADLoggingNode(name="VADLogger"))
    
    # VAD-triggered buffer that only outputs complete speech segments
    vad_buffer = VADTriggeredBuffer(
        min_speech_duration_s=1.0,    # Minimum 1.0s of speech before triggering
        max_speech_duration_s=8.0,    # Force trigger after 8s of continuous speech
        silence_duration_s=0.5,       # 500ms of silence to confirm speech end
        pre_speech_buffer_s=1.0,      # 1s of pre-speech context
        sample_rate=16000,
        name="VADTriggeredBuffer"
    )
    vad_buffer.is_streaming = True
    pipeline.add_node(vad_buffer)
    
    # Remote Ultravox execution with minimum duration protection
    remote_config = RemoteExecutorConfig(host=remote_host, port=50052, ssl_enabled=False)
    
    ultravox_instance = UltravoxNode(
        model_id="fixie-ai/ultravox-v0_5-llama-3_1-8b",
        system_prompt=(
            "You are a helpful assistant. Listen to what the user says and respond "
            "appropriately and concisely. Keep responses under 2 sentences."
        ),
        buffer_duration_s=10.0,  # Large buffer to process complete utterances
        name="UltravoxNode"
    )
    
    # Wrap Ultravox with immediate processing for complete utterances
    immediate_ultravox = UltravoxImmediateProcessor(
        ultravox_node=ultravox_instance,
        min_duration_s=1.0,  # Require at least 1s of audio (matches VAD buffer)
        sample_rate=16000,
        name="ImmediateUltravox"
    )

    remote_ultravox = RemoteObjectExecutionNode(
        obj_to_execute=immediate_ultravox,
        remote_config=remote_config,
        name="RemoteUltravox",
        node_config={'streaming': True}
    )
    remote_ultravox.is_streaming = True
    pipeline.add_node(remote_ultravox)
    
    logger.info("⏳ RemoteUltravox node added to pipeline - will initialize during pipeline setup")

    # Log text responses
    pipeline.add_node(TextLoggingNode(name="TextLogger"))

    # Kokoro TTS for speech synthesis
    kokoro_tts = KokoroTTSNode(
        lang_code='a',  # American English
        voice='af_heart',
        speed=1.0,
        sample_rate=24000,
        stream_chunks=True,  # Enable streaming
        name="KokoroTTS"
    )
    kokoro_tts.is_streaming = True
    
    # Use remote execution for Kokoro TTS too
    remote_tts = RemoteObjectExecutionNode(
        obj_to_execute=kokoro_tts,
        remote_config=remote_config,
        name="RemoteKokoroTTS",
        node_config={'streaming': True}
    )
    remote_tts.is_streaming = True
    pipeline.add_node(remote_tts)
    
    logger.info("⏳ RemoteKokoroTTS node added to pipeline - will initialize during pipeline setup")

    # Log audio output
    pipeline.add_node(MessageLoggingNode(
        message_prefix="🔊 SYNTHESIZED AUDIO",
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
    
    # Add VAD for debugging microphone input even in simple mode
    vad = VoiceActivityDetector(
        frame_duration_ms=30,
        energy_threshold=0.02,
        speech_threshold=0.3,
        filter_mode=False,  # Keep metadata for debugging
        include_metadata=True,
        name="SimpleVAD"
    )
    vad.is_streaming = True
    pipeline.add_node(vad)
    
    # Add VAD logging for debugging microphone input
    pipeline.add_node(VADLoggingNode(name="SimpleVADLogger"))
    
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
                return create_speech_to_speech_pipeline(remote_host=REMOTE_HOST)
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