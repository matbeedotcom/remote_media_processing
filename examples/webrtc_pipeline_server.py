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
from aiortc import RTCIceServer, RTCPeerConnection, RTCDataChannel, RTCSessionDescription

# Ensure the 'remotemedia' package is in the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from remotemedia.core.pipeline import Pipeline
from remotemedia.nodes.audio import AudioTransform, ConcatenateAudioNode
from remotemedia.nodes.source import AudioTrackSource
from remotemedia.webrtc.source import WebRTCStreamSource
from remotemedia.webrtc.server import WebRTCServer
from remotemedia.nodes.base import PassThroughNode


# Configure basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

ROOT = os.path.dirname(__file__)


class PrintNode(PassThroughNode):
    """A simple node that prints any data it receives."""
    async def process(self, data):
        logger.info(f"PIPELINE-SINK: {data}")
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
            msg = f"{self.message}_{self.count}"
            self.channel.send(msg)
            logger.info(f"Sent feedback message: {msg}")
        else:
            logger.warning(f"Data channel not available or not open")
        
        return data


# Global to store feedback nodes by peer connection
feedback_nodes = {}


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
    
    pipeline = Pipeline(
        [
            WebRTCStreamSource(),
            AudioTrackSource(),
            AudioTransform(output_sample_rate=16000, output_channels=1),
            ConcatenateAudioNode(duration_seconds=2.0), # Buffer 2s of audio
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
    
    # Create peer connection
    pc = RTCPeerConnection()
    
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
            await pipeline.cleanup()
            feedback_nodes.pop(pc, None)
    
    # Set remote description and create answer
    await pc.setRemoteDescription(RTCSessionDescription(sdp=offer_sdp, type=offer_type))
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    
    # Start pipeline
    logger.info(f"Starting pipeline {pipeline}")
    asyncio.create_task(run_pipeline(pipeline))
    
    return web.json_response({
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type
    })


async def run_pipeline(pipeline: Pipeline):
    """Run the pipeline."""
    try:
        async with pipeline.managed_execution():
            async for _ in pipeline.process():
                pass
    except Exception as e:
        logger.error(f"Error during pipeline execution: {e}", exc_info=True)
    finally:
        logger.info("Pipeline execution finished.")


async def index(request):
    # Serve the client that creates data channel
    content = open(os.path.join(ROOT, "webrtc_client_with_datachannel.html"), "r").read()
    return web.Response(content_type="text/html", text=content)


async def on_shutdown(app: web.Application):
    """aiohttp shutdown handler."""
    # Clean up any remaining connections
    pass


def main():
    """Main function to set up and run the server."""
    # Setup aiohttp server
    app = web.Application()
    app.on_shutdown.append(on_shutdown)
    app.router.add_get("/", index)
    app.router.add_post("/offer", offer_handler)

    logger.info("Starting aiohttp server on http://127.0.0.1:8899")
    logger.info("Open this URL in a browser to start the test.")
    web.run_app(app, host="127.0.0.1", port=8899)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Server shut down by user.") 