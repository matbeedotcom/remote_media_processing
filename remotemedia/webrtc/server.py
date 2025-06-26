"""
A server class to manage WebRTC connections and associated processing pipelines.
"""

import asyncio
import logging
from typing import Callable, Coroutine
from functools import partial

from ..core.pipeline import Pipeline
from .source import WebRTCStreamSource

# To avoid a hard dependency on aiortc, we will use duck typing and check for it at runtime.
try:
    from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer
    AIORTC_AVAILABLE = True
except ImportError:
    AIORTC_AVAILABLE = False
    # Create dummy classes for type hinting so the file can be imported
    class RTCPeerConnection: pass
    class RTCSessionDescription: pass
    class RTCConfiguration: pass
    class RTCIceServer: pass


logger =logging.getLogger(__name__)


class WebRTCServer:
    """
    Manages multiple WebRTC peer connections, creating a new processing pipeline
    for each connection.

    This class is designed for server-side applications where each connected
    client requires its own independent media processing pipeline. It handles
    the signaling (offer/answer) and launches a given pipeline factory for
    each new peer.
    """
    def __init__(
        self,
        pipeline_factory: Callable[..., Pipeline],
        **pc_kwargs,
    ):
        """
        Initializes the WebRTCServer.

        Args:
            pipeline_factory: A callable (e.g., a function or class) that
                              returns a new `Pipeline` instance for each client.
                              It will be called with the `RTCPeerConnection`
                              instance as its first argument. The first node
                              of the returned pipeline MUST be a `WebRTCStreamSource`.
            **pc_kwargs: Keyword arguments to be passed to the RTCPeerConnection
                         constructor. If 'iceServers' is provided, it will be
                         converted to an RTCConfiguration object.
        """
        if not AIORTC_AVAILABLE:
            raise ImportError("aiortc is not installed. Please install it to use WebRTCServer.")
        
        self.pipeline_factory = pipeline_factory
        
        # Handle ice servers configuration
        ice_servers = pc_kwargs.pop('iceServers', None)
        if ice_servers:
            # Convert ice servers to RTCConfiguration
            rtc_ice_servers = [RTCIceServer(urls=server.urls) for server in ice_servers]
            self.configuration = RTCConfiguration(iceServers=rtc_ice_servers)
        else:
            self.configuration = None
            
        self.pc_kwargs = pc_kwargs
        self._tasks: list[asyncio.Task] = []

    async def handle_offer(self, offer_sdp: str, offer_type: str) -> tuple[str, str]:
        """
        Handles an SDP offer from a client.

        This method creates a new RTCPeerConnection, sets up the associated
        pipeline, and generates an SDP answer.

        Args:
            offer_sdp: The SDP data from the client's offer.
            offer_type: The type of the client's offer (e.g., "offer").

        Returns:
            A tuple containing the SDP data and type of the generated answer.
        """
        offer = RTCSessionDescription(sdp=offer_sdp, type=offer_type)
        
        # Create peer connection with configuration if available
        if self.configuration:
            pc = RTCPeerConnection(configuration=self.configuration, **self.pc_kwargs)
        else:
            pc = RTCPeerConnection(**self.pc_kwargs)
        
        # Create a feedback channel BEFORE setting remote description
        # This ensures the data channel is included in the answer
        feedback_channel = pc.createDataChannel("feedback")
        logger.info(f"Created data channel 'feedback' with state: {feedback_channel.readyState}")

        # The pipeline factory is called with the peer connection so that
        # nodes can be configured with it (e.g. to create data channels).
        pipeline = self.pipeline_factory(pc, feedback_channel)
        
        # The first node is assumed to be the WebRTCStreamSource
        source_node = pipeline.nodes[0]
        if not isinstance(source_node, WebRTCStreamSource):
            raise TypeError(
                "The first node of the pipeline must be an instance of WebRTCStreamSource."
            )
        
        source_node.set_connection(pc)

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info(f"Connection state is {pc.connectionState}")
            if pc.connectionState in ("failed", "closed", "disconnected"):
                await pipeline.cleanup()
        
        # Set remote description AFTER creating the data channel
        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        
        # Run pipeline in the background AFTER establishing the connection
        logger.info(f"Creating task to run pipeline {pipeline}")
        pipeline_task = asyncio.create_task(self._run_pipeline(pipeline))
        logger.info(f"Created pipeline task: {pipeline_task}")
        self._tasks.append(pipeline_task)
        
        logger.info("Returning SDP answer to client")
        return pc.localDescription.sdp, pc.localDescription.type

    async def _run_pipeline(self, pipeline: Pipeline):
        """Initializes, runs, and cleans up a pipeline instance."""
        logger.info(f"Starting _run_pipeline for {pipeline}")
        try:
            logger.info("Entering pipeline.managed_execution()")
            async with pipeline.managed_execution():
                logger.info("Pipeline initialization complete, starting to process")
                async for item in pipeline.process():
                    # The pipeline is responsible for its own sinks.
                    # We just consume the generator to drive it.
                    logger.debug(f"Pipeline yielded item: {item}")
                    pass
                logger.info("Pipeline processing loop completed")
        except Exception as e:
            logger.error(f"Error during pipeline execution: {e}", exc_info=True)
        finally:
            logger.info("Pipeline execution finished.")

    async def close(self):
        """Closes all running pipeline tasks."""
        logger.info(f"Closing {len(self._tasks)} pipeline tasks.")
        for task in self._tasks:
            if not task.done():
                task.cancel()
        
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        logger.info("WebRTCServer closed.") 