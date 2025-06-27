#!/usr/bin/env python3
"""
Example of a WebRTC server that receives audio from a client,
processes it through a pipeline, and sends feedback via data channel.
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

from aiohttp import web
from aiortc import RTCIceServer, RTCPeerConnection, RTCDataChannel, RTCSessionDescription, RTCConfiguration

# Ensure the 'remotemedia' package is in the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from remotemedia.core.pipeline import Pipeline
from remotemedia.nodes.audio import AudioTransform, ConcatenateAudioNode, AudioBuffer
from remotemedia.nodes.source import AudioTrackSource
from remotemedia.webrtc.source import WebRTCStreamSource
from remotemedia.webrtc.server import WebRTCServer
from remotemedia.nodes.base import PassThroughNode
from remotemedia.nodes.ml import WhisperTranscriptionNode


# Configure basic logging
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG for testing
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),  # Console output
        logging.FileHandler('webrtc_server.log')  # Also log to file
    ]
)
logger = logging.getLogger(__name__)

# Set specific loggers to appropriate levels to reduce noise
logging.getLogger("aiohttp").setLevel(logging.INFO)
logging.getLogger("aiortc").setLevel(logging.INFO)

ROOT = os.path.dirname(__file__)


class PrintNode(PassThroughNode):
    """A simple node that prints any data it receives."""
    async def process(self, data):
        if isinstance(data, dict) and 'audio' in data:
            logger.info(f"PrintNode: Received audio frame")
        elif isinstance(data, str):
            # This is likely transcription text from WhisperTranscriptionNode
            logger.info(f"🎤 TRANSCRIPTION: '{data}'")
        elif isinstance(data, tuple) and len(data) == 1 and isinstance(data[0], str):
            # WhisperTranscriptionNode yields (text,) tuples
            logger.info(f"🎤 TRANSCRIPTION: '{data[0]}'")
        else:
            logger.info(f"PrintNode: Received data type: {type(data)}, keys: {data.keys() if isinstance(data, dict) else 'N/A'}")
        return data


class FeedbackSinkNode(PassThroughNode):
    """
    A node that sends a confirmation message over a data channel
    for each item it processes.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.channel = None
        self.message = "processed_chunk"
        self.count = 0

    def set_channel(self, channel: RTCDataChannel):
        """Set the data channel to use for feedback."""
        self.channel = channel
        logger.info(f"FeedbackSinkNode: channel set, state: {channel.readyState if channel else 'None'}")

    async def process(self, data):
        self.count += 1
        logger.info(f"FeedbackSinkNode received data #{self.count}")
        
        if self.channel and self.channel.readyState == "open":
            # Send transcription text if available
            if isinstance(data, str):
                msg = f"transcription: {data}"
                self.channel.send(msg)
                logger.info(f"Sent transcription: {data}")
            elif isinstance(data, tuple) and len(data) == 1 and isinstance(data[0], str):
                # WhisperTranscriptionNode yields (text,) tuples
                msg = f"transcription: {data[0]}"
                self.channel.send(msg)
                logger.info(f"Sent transcription: {data[0]}")
            else:
                msg = f"{self.message}_{self.count}"
                self.channel.send(msg)
                logger.info(f"Sent feedback message: {msg}")
        else:
            logger.warning(f"Data channel not available or not open")
        
        return data


# Global to store feedback nodes by peer connection
feedback_nodes = {}
# Global to store processing tasks by peer connection
processing_tasks = {}


class DebugAudioTrackSource(AudioTrackSource):
    """Debug version of AudioTrackSource with extra logging."""
    def process(self, data):
        logger.info(f"DebugAudioTrackSource received: {type(data)}, keys: {data.keys() if isinstance(data, dict) else 'N/A'}")
        # Call parent process (synchronous)
        result = super().process(data)
        if result is not None:
            logger.info(f"DebugAudioTrackSource returning audio data: {type(result)}")
        return result


def create_transcription_pipeline(pc: RTCPeerConnection) -> Pipeline:
    """
    Factory function to create the audio processing pipeline.
    The data channel will be set later when received from client.
    """
    logger.info("Creating new transcription pipeline instance.")
    
    # Create feedback node without channel (will be set later)
    feedback_node = FeedbackSinkNode()
    
    # Store it so we can set the channel later
    feedback_nodes[pc] = feedback_node
    # Convert av.AudioFrame objects into (ndarray, sample_rate) tuples
    # Whisper expects 16kHz audio, so we resample it.

    # Simpler pipeline without buffering for testing
    pipeline = Pipeline(
        [
            WebRTCStreamSource(),
            AudioTrackSource(),  # Use debug version
            AudioBuffer(buffer_size_samples=16000),
            AudioTransform(output_sample_rate=16000, output_channels=1),
            WhisperTranscriptionNode(),
            PrintNode(),  # Add debug logging
            feedback_node,
        ]
    )
    return pipeline


async def offer_handler(request: web.Request):
    """
    Handles the incoming offer from the client using a custom
    WebRTC server that supports client-created data channels.
    """
    params = await request.json()
    offer_sdp = params["sdp"]
    offer_type = params["type"]
    
    # Create peer connection with ICE servers
    config = RTCConfiguration(
        iceServers=[RTCIceServer(urls=["stun:stun.l.google.com:19302"])]
    )
    pc = RTCPeerConnection(configuration=config)
    
    # Create pipeline
    pipeline = create_transcription_pipeline(pc)
    feedback_node = feedback_nodes[pc]
    
    # Set up data channel handler
    @pc.on("datachannel")
    def on_datachannel(channel: RTCDataChannel):
        logger.info(f"Data channel '{channel.label}' received from client")
        if channel.label == "feedback":
            feedback_node.set_channel(channel)
            
            @channel.on("open")  
            def on_open():
                logger.info(f"Data channel '{channel.label}' opened")
                
            @channel.on("message")
            def on_message(message):
                logger.info(f"Received message on feedback channel: {message}")
                if message == "client_ready":
                    # Send immediate test feedback
                    if channel.readyState == "open":
                        channel.send("processed_chunk_0")
                        logger.info("Sent initial feedback message")
    
    # Set up WebRTC source
    source_node = pipeline.nodes[0]
    if isinstance(source_node, WebRTCStreamSource):
        source_node.set_connection(pc)
    
    # Handle connection state
    @pc.on("connectionstatechange")
    async def on_connectionstatechange():
        logger.info(f"Connection state is {pc.connectionState}")
        if pc.connectionState in ("failed", "closed", "disconnected"):
            # Cancel the processing task if it exists
            if pc in processing_tasks:
                task = processing_tasks[pc]
                if not task.done():
                    logger.info("Cancelling pipeline processing task")
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        logger.info("Pipeline processing task cancelled successfully")
                processing_tasks.pop(pc, None)
            
            await pipeline.cleanup()
            feedback_nodes.pop(pc, None)
    
    # Initialize the pipeline BEFORE negotiating to ensure listeners are ready
    logger.info(f"Initializing pipeline {pipeline}")
    await pipeline.initialize()
    
    # Check if the offer contains audio tracks
    if "m=audio" in offer_sdp:
        logger.info("Offer contains audio track")
    else:
        logger.warning("Offer does NOT contain audio track!")
    
    # Set remote description and create answer
    await pc.setRemoteDescription(RTCSessionDescription(sdp=offer_sdp, type=offer_type))
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    
    # Check if answer accepts audio
    if "m=audio" in answer.sdp:
        logger.info("Answer accepts audio track")
    else:
        logger.warning("Answer does NOT accept audio track!")
    
    # Start pipeline processing
    logger.info(f"Starting pipeline processing for {pipeline}")
    task = asyncio.create_task(run_pipeline_processing(pipeline))
    processing_tasks[pc] = task
    
    return web.json_response({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })


async def run_pipeline_processing(pipeline: Pipeline):
    """Run the pipeline processing (assumes already initialized)."""
    try:
        logger.info("Starting pipeline processing loop")
        item_count = 0
        async for item in pipeline.process():
            item_count += 1
            logger.info(f"Pipeline processed item #{item_count}: {type(item)}")
            if item_count % 10 == 0:  # Log every 10 items
                logger.info(f"Pipeline processed {item_count} items")
        logger.info(f"Pipeline processed total {item_count} items")
    except asyncio.CancelledError:
        logger.info("Pipeline processing cancelled")
        raise
    except Exception as e:
        logger.error(f"Error during pipeline execution: {e}", exc_info=True)
    finally:
        await pipeline.cleanup()
        logger.info("Pipeline execution finished.")


async def index(request):
    # Serve the client that creates data channel
    content = open(os.path.join(ROOT, "webrtc_client_with_datachannel.html"), "r").read()
    return web.Response(content_type="text/html", text=content)


async def serve_test_client(request):
    # Serve the test client that uses media files
    content = open(os.path.join(ROOT, "webrtc_test_client_with_media_files.html"), "r").read()
    return web.Response(content_type="text/html", text=content)


async def serve_media_file(request):
    """Serve media files for testing."""
    filename = request.match_info['filename']
    
    # Security: only allow specific files
    allowed_files = ['transcribe_demo.wav', 'BigBuckBunny_320x180.mp4', 'draw.mp4']
    if filename not in allowed_files:
        return web.Response(status=404)
    
    filepath = os.path.join(ROOT, filename)
    if not os.path.exists(filepath):
        return web.Response(status=404)
    
    # Determine content type
    if filename.endswith('.wav'):
        content_type = 'audio/wav'
    elif filename.endswith('.mp4'):
        content_type = 'video/mp4'
    else:
        content_type = 'application/octet-stream'
    
    # Stream the file
    return web.FileResponse(filepath, headers={'Content-Type': content_type})


async def on_shutdown(app: web.Application):
    """aiohttp shutdown handler."""
    # Cancel all remaining processing tasks
    logger.info(f"Shutting down, cancelling {len(processing_tasks)} processing tasks")
    for pc, task in list(processing_tasks.items()):
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    processing_tasks.clear()
    feedback_nodes.clear()
    logger.info("Shutdown complete")


def main():
    """Main function to set up and run the server."""
    # Setup aiohttp server
    app = web.Application()
    app.on_shutdown.append(on_shutdown)
    app.router.add_get("/", index)
    app.router.add_get("/test", serve_test_client)
    app.router.add_get("/{filename}", serve_media_file)
    app.router.add_post("/offer", offer_handler)

    logger.info("Starting aiohttp server on http://127.0.0.1:8899")
    logger.info("Open this URL in a browser to start the test.")
    web.run_app(app, host="127.0.0.1", port=8899)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Server shut down by user.") 