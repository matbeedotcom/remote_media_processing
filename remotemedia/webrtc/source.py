import asyncio
import logging
from typing import Any, AsyncGenerator, Dict, Optional, Union

from av.frame import Frame
from ..core.node import Node
from ..core.exceptions import NodeError

logger = logging.getLogger(__name__)

# To avoid a hard dependency on aiortc, we will use duck typing and check for it at runtime.
try:
    from aiortc import RTCPeerConnection, MediaStreamTrack, RTCDataChannel
    from aiortc.mediastreams import MediaStreamError
    from aiortc.contrib.media import MediaRelay
    AIORTC_AVAILABLE = True
except ImportError:
    AIORTC_AVAILABLE = False
    # Create dummy classes for type hinting so the file can be imported
    class RTCPeerConnection: pass
    class MediaStreamTrack: pass
    class RTCDataChannel: pass
    class MediaStreamError(Exception): pass
    class MediaRelay: pass


class WebRTCStreamSource(Node):
    """
    A source node that takes an RTCPeerConnection and streams media and data
    from it into a pipeline.

    This node acts as a bridge between a WebRTC peer connection and the
    processing pipeline. It listens for incoming audio/video tracks and
    data channels, and yields the received data as dictionaries.
    e.g., `{'audio': frame}`, `{'video': frame}`, `{'data': message}`.

    The RTCPeerConnection object must be created and managed externally,
    and then passed to this node using `set_connection` before the
    pipeline is initialized.
    """

    def __init__(self, **kwargs):
        """
        Initialize the WebRTC source node.
        An RTCPeerConnection should be set later via `set_connection`.
        """
        super().__init__(**kwargs)
        if not AIORTC_AVAILABLE:
            raise NodeError("aiortc is not installed. Please install it to use WebRTCStreamSource.")

        self._connection: Optional[RTCPeerConnection] = None
        self._relay = MediaRelay()
        self._queue: asyncio.Queue[
            Optional[Dict[str, Union[Frame, Dict[str, Any]]]]
        ] = asyncio.Queue()
        self._listeners_created = False
        self._tasks: list[asyncio.Task] = []
        self._sentinel = object()

    def set_connection(self, connection: RTCPeerConnection):
        """
        Sets the RTCPeerConnection for this source node. This must be called
        before the pipeline is initialized.
        
        Args:
            connection: The configured RTCPeerConnection object.
        """
        if self._connection:
            logger.warning(f"Peer connection already set on node '{self.name}'. Ignoring.")
            return
        logger.info(f"Setting peer connection for node '{self.name}'")
        self._connection = connection
        # Listeners are now created lazily on initialization to ensure they
        # are in the correct asyncio loop.

    def _create_listeners(self):
        """Creates and attaches event listeners to the peer connection."""
        if not self._connection or self._listeners_created:
            return

        logger.info(f"Creating listeners for WebRTCStreamSource '{self.name}'")

        @self._connection.on("track")
        async def on_track(track: MediaStreamTrack):
            logger.info(f"Track {track.kind} received on node '{self.name}'")
            relayed_track = self._relay.subscribe(track)
            loop = asyncio.get_running_loop()
            task = loop.create_task(self._track_reader(relayed_track))
            self._tasks.append(task)

        @self._connection.on("datachannel")
        def on_datachannel(channel: RTCDataChannel):
            logger.info(f"Data channel '{channel.label}' received on node '{self.name}'")

            @channel.on("message")
            def on_message(message):
                logger.debug(f"Message on data channel '{channel.label}': len={len(message)}")
                try:
                    self._queue.put_nowait(
                        {'data': {'payload': message, 'channel': channel.label}}
                    )
                except asyncio.QueueFull:
                    logger.warning(
                        f"WebRTC source queue is full on node '{self.name}'. "
                        f"Dropping message from data channel '{channel.label}'."
                    )
        
        self._listeners_created = True
        logger.info(f"Listeners created for WebRTCStreamSource '{self.name}'")

    async def initialize(self):
        """
        Initializes the node and creates the listeners.
        """
        await super().initialize()
        logger.info(f"WebRTCStreamSource.initialize() called for node '{self.name}'")

        if not self._connection:
            logger.warning(
                f"WebRTCStreamSource '{self.name}' initialized without a PeerConnection. "
                "It will not produce any data. Call set_connection() before initialization."
            )
            return

        self._create_listeners()
        logger.info(f"WebRTCStreamSource '{self.name}' initialized with listeners")

    async def _track_reader(self, track: MediaStreamTrack):
        logger.info(f"Starting reader for {track.kind} track on node '{self.name}'.")
        try:
            while True:
                try:
                    frame = await track.recv()
                    logger.debug(f"Received {track.kind} frame")
                    await self._queue.put({track.kind: frame})
                except MediaStreamError:
                    logger.info(f"{track.kind} track ended on node '{self.name}'.")
                    break
        except asyncio.CancelledError:
            logger.info(f"{track.kind} track reader for node '{self.name}' cancelled.")
        except Exception as e:
            logger.error(f"Error in {track.kind} track reader for node '{self.name}': {e}", exc_info=True)

    async def process(
        self, data: None = None
    ) -> AsyncGenerator[Dict[str, Union[Frame, Dict[str, Any]]], None]:
        """
        Yields media frames and data messages from the WebRTC connection.
        As a source node, this method ignores any input `data`.

        The output format for each item will be one of:
        - `{'audio': av.AudioFrame}`
        - `{'video': av.VideoFrame}`
        - `{'data': {'channel': 'label', 'payload': str_or_bytes}}`
        """
        if self._connection is None:
            raise NodeError("WebRTC connection is not set.")

        logger.info(f"WebRTC source stream started for node '{self.name}'.")
        try:
            while True:
                item = await self._queue.get()
                if item is self._sentinel:
                    break
                yield item
        except asyncio.CancelledError:
            logger.info(f"WebRTC source stream cancelled for node '{self.name}'.")
            raise
        finally:
            logger.info(f"WebRTC source stream finished for node '{self.name}'.")

    async def cleanup(self):
        """Cleans up resources, including stopping the stream and reader tasks."""
        logger.info(f"Cleaning up WebRTCStreamSource '{self.name}'.")
        
        for task in self._tasks:
            if not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            self._tasks.clear()

        if self._queue and self._connection and self._connection.connectionState != 'closed':
            # This is to unblock a potentially waiting `process` generator
            await self._queue.put(self._sentinel)

        await super().cleanup() 