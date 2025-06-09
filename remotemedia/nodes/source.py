"""
Source nodes for the RemoteMedia SDK.

Source nodes are responsible for introducing data into the pipeline,
for example by reading from a file, network stream, or hardware device.
"""
import asyncio
from typing import AsyncGenerator, Any

from ..core.node import Node
from ..core.exceptions import NodeError

class MediaReaderNode(Node):
    """
    A node that reads media from a local file or URL and yields frames.

    This node is a "source" and is not meant to be used in the middle of a
    pipeline. Its purpose is to generate a stream of data to be fed into
    a pipeline.
    """

    def __init__(self, path: str, **kwargs):
        """
        Initialize the media source node.

        Args:
            path: Path to the media file or URL
            **kwargs: Additional node parameters
        """
        super().__init__(**kwargs)
        self.path = path

    def process(self, data=None):
        """
        Ignores any input data and returns an async generator of media frames.
        """
        return self.stream()

    async def stream(self) -> AsyncGenerator[Any, None]:
        """
        Asynchronously yields frames from the media source.
        """
        try:
            from aiortc.contrib.media import MediaPlayer
            from aiortc.mediastreams import MediaStreamError
        except ImportError:
            raise NodeError("PyAV and aiortc are required for MediaReaderNode. Please install them.")

        player = MediaPlayer(self.path)
        
        if player.audio is None and player.video is None:
            self.logger.warning("No audio or video tracks found in the source.")
            return

        # We can create a simple multiplexer here to yield frames as they come
        queue = asyncio.Queue()
        _sentinel = object()

        async def track_reader(track, track_type):
            self.logger.info(f"Starting reader for {track_type} track.")
            try:
                while True:
                    try:
                        frame = await track.recv()
                        self.logger.debug(f"Received {track_type} frame: {frame.pts}")
                        await queue.put({track_type: frame})
                    except MediaStreamError:
                        self.logger.info(f"{track_type} track finished.")
                        break
            finally:
                await queue.put(_sentinel)

        tasks = []
        if player.audio:
            tasks.append(asyncio.create_task(track_reader(player.audio, 'audio')))
        if player.video:
            tasks.append(asyncio.create_task(track_reader(player.video, 'video')))
        
        finished_tracks = 0
        while finished_tracks < len(tasks):
            item = await queue.get()
            if item is _sentinel:
                finished_tracks += 1
                self.logger.info(f"A track reader finished. {finished_tracks}/{len(tasks)} done.")
            else:
                self.logger.debug("Yielding frame from queue.")
                yield item
        self.logger.info("All track readers have finished.")

__all__ = ["MediaReaderNode"] 