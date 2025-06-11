"""
Source nodes for the RemoteMedia SDK.

Source nodes are responsible for introducing data into the pipeline,
for example by reading from a file, network stream, or hardware device.
"""
import asyncio
import logging
from typing import AsyncGenerator, Any

import numpy as np
from av import AudioFrame, VideoFrame
from av.frame import Frame

from ..core.node import Node
from ..core.exceptions import NodeError

logger = logging.getLogger(__name__)

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
            logger.warning("No audio or video tracks found in the source.")
            return

        # We can create a simple multiplexer here to yield frames as they come
        queue = asyncio.Queue()
        _sentinel = object()

        async def track_reader(track, track_type):
            logger.info(f"Starting reader for {track_type} track.")
            try:
                while True:
                    try:
                        frame = await track.recv()
                        logger.debug(f"Received {track_type} frame: {frame.pts}")
                        await queue.put({track_type: frame})
                    except MediaStreamError:
                        logger.info(f"{track_type} track finished.")
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
                logger.info(f"A track reader finished. {finished_tracks}/{len(tasks)} done.")
            else:
                logger.debug("Yielding frame from queue.")
                yield item
        logger.info("All track readers have finished.")


class TrackSource(Node):
    """
    Base class for track source nodes that extract a specific track from a
    stream of mixed-media dictionaries.
    """
    # Subclasses should override these
    _track_type: str = ""
    _frame_type: type = Frame

    def process(self, data: Any) -> Any:
        """
        Processes input data, expecting a dictionary like `{'audio': frame}`.
        It extracts the frame for the specific track type and processes it.
        """
        if not isinstance(data, dict) or self._track_type not in data:
            # Not the data this track is looking for, ignore silently.
            return None

        frame = data[self._track_type]

        if not isinstance(frame, self._frame_type):
            logger.warning(
                f"{self.__class__.__name__} '{self.name}': received data for track "
                f"'{self._track_type}' with unexpected frame type {type(frame)}."
            )
            return None

        return self._process_frame(frame)

    def _process_frame(self, frame: Frame) -> Any:
        raise NotImplementedError


class AudioTrackSource(TrackSource):
    """
    An audio track source node that converts `av.AudioFrame` objects into NumPy arrays.
    """
    _track_type = "audio"
    _frame_type = AudioFrame

    def _process_frame(self, frame: AudioFrame) -> Any:
        """
        Converts an `av.AudioFrame` to a tuple of (audio_data, sample_rate).

        Args:
            frame: An `av.AudioFrame`.

        Returns:
            A tuple `(audio_data, sample_rate)` where `audio_data` is a
            NumPy array with shape (channels, samples).
        """
        try:
            audio_data = frame.to_ndarray()
            # Normalize and convert to float32, as expected by librosa
            if audio_data.dtype == np.int16:
                audio_data = audio_data.astype(np.float32) / 32768.0
            elif audio_data.dtype == np.int32:
                audio_data = audio_data.astype(np.float32) / 2147483648.0
            
            logger.debug(
                f"AudioTrackSource '{self.name}': processed audio frame with "
                f"{frame.samples} samples at {frame.sample_rate}Hz."
            )
            return (audio_data, frame.sample_rate)
        except Exception as e:
            logger.error(f"Error converting audio frame to numpy array: {e}")
            return None


class VideoTrackSource(TrackSource):
    """
    A video track source node that converts `av.VideoFrame` objects into NumPy arrays.
    """
    _track_type = "video"
    _frame_type = VideoFrame

    def __init__(self, output_format: str = "bgr24", **kwargs):
        """
        Initializes the VideoTrackSource node.

        Args:
            output_format (str): The desired output format for the NumPy array
                                 (e.g., 'bgr24', 'rgb24').
        """
        super().__init__(**kwargs)
        self.output_format = output_format

    def _process_frame(self, frame: VideoFrame) -> Any:
        """
        Converts an `av.VideoFrame` to a NumPy array.

        Args:
            frame: An `av.VideoFrame`.

        Returns:
            A NumPy array representing the video frame.
        """
        try:
            video_data = frame.to_ndarray(format=self.output_format)
            logger.debug(
                f"VideoTrackSource '{self.name}': processed video frame with "
                f"resolution {frame.width}x{frame.height}."
            )
            return (video_data, frame.pts)
        except Exception as e:
            logger.error(f"Error converting video frame to numpy array: {e}")
            return None


__all__ = ["MediaReaderNode", "AudioTrackSource", "VideoTrackSource", "TrackSource"] 