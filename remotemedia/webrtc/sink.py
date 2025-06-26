import asyncio
import logging
from typing import Any, Dict, Optional, Union

from aiortc import MediaStreamTrack, RTCDataChannel
from av.frame import Frame

from ..core.node import Node
from ..core.exceptions import NodeError

logger = logging.getLogger(__name__)


class PipelineTrack(MediaStreamTrack):
    """
    An aiortc.MediaStreamTrack implementation that gets frames from an
    asyncio.Queue, allowing a pipeline to programmatically send media.
    """

    def __init__(self, kind: str):
        """
        Initialize the PipelineTrack.
        Args:
            kind: The kind of media ('audio' or 'video').
        """
        super().__init__()
        self.kind = kind
        self._queue: asyncio.Queue = asyncio.Queue()
        self._stopped = False

    async def recv(self) -> Optional[Frame]:
        """
        The method called by aiortc to get the next frame for the stream.
        """
        if self._stopped:
            return None

        frame = await self._queue.get()
        if frame is None:  # Sentinel value indicates the stream is stopping.
            self._stopped = True
            return None
        return frame

    async def put_frame(self, frame: Frame):
        """
        Puts a frame into the queue to be sent over the WebRTC track.
        """
        if not self._stopped:
            await self._queue.put(frame)

    def stop(self):
        """
        Signals that the track should be stopped. This is a synchronous method
        to match the aiortc.MediaStreamTrack interface.
        """
        if not self._stopped:
            self._stopped = True
            # This method can be called from a different thread than the one
            # running the asyncio event loop, so we use call_soon_threadsafe.
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon_threadsafe(self._queue.put_nowait, None)
            except RuntimeError:
                # This can happen if the loop is not running or shutting down.
                # In this case, we can't schedule the sentinel.
                logger.warning(
                    f"Could not schedule sentinel for PipelineTrack {self.kind} stop: no running loop."
                )


class WebRTCSinkNode(Node):
    """
    A sink node that sends media and data over a WebRTC connection.

    This node takes audio/video frames and data channel messages from the
    pipeline and sends them through an existing RTCPeerConnection's tracks
    and data channels.
    """
    def __init__(
        self,
        audio_track: Optional[PipelineTrack] = None,
        video_track: Optional[PipelineTrack] = None,
        data_channels: Optional[Dict[str, RTCDataChannel]] = None,
        **kwargs
    ):
        """
        Initialize the WebRTC sink node.
        Args:
            audio_track: A PipelineTrack for sending audio.
            video_track: A PipelineTrack for sending video.
            data_channels: A dictionary mapping labels to RTCDataChannel objects.
            **kwargs: Additional node parameters.
        """
        super().__init__(**kwargs)
        if not audio_track and not video_track and not data_channels:
            raise NodeError("WebRTCSinkNode must be configured with at least one track or data channel.")

        self.audio_track = audio_track
        self.video_track = video_track
        self.data_channels = data_channels or {}

    async def process(self, data: Dict[str, Union[Frame, Dict[str, Any]]]):
        """
        Processes incoming data from the pipeline and sends it over WebRTC.

        The `data` format determines how it is sent:
        - For audio: `{'audio': av.AudioFrame}`
        - For video: `{'video': av.VideoFrame}`
        - For data: `{'data': {'channel': 'label', 'payload': 'message'}}`
        """
        if not isinstance(data, dict):
            logger.warning(
                f"'{self.name}' received non-dict data of type {type(data)}. Ignoring."
            )
            return

        if "audio" in data and self.audio_track:
            frame = data["audio"]
            if isinstance(frame, Frame):
                await self.audio_track.put_frame(frame)
                logger.debug(f"Sent audio frame (pts={frame.pts})")
        
        if "video" in data and self.video_track:
            frame = data["video"]
            if isinstance(frame, Frame):
                await self.video_track.put_frame(frame)
                logger.debug(f"Sent video frame (pts={frame.pts})")

        if "data" in data and self.data_channels:
            data_payload = data["data"]
            if isinstance(data_payload, dict):
                self._send_data_payload(data_payload)
            else:
                logger.warning(
                    f"Invalid 'data' payload for sink: expected a dict, got {type(data_payload)}"
                )

    def _send_data_payload(self, data_payload: Dict[str, Any]):
        """Handles sending data on a data channel."""
        if "channel" not in data_payload or "payload" not in data_payload:
            logger.warning(f"Invalid data payload for data channel: {data_payload}")
            return
            
        channel_label = data_payload["channel"]
        payload = data_payload["payload"]
        
        if channel_label in self.data_channels:
            # RTCDataChannel.send() is synchronous
            self.data_channels[channel_label].send(payload)
            logger.debug(f"Sent data on channel '{channel_label}'")
        else:
            logger.warning(
                f"Data channel '{channel_label}' not configured for this sink node."
            )

    async def cleanup(self):
        """
        Stops the media tracks to signal the end of the stream.
        """
        logger.info(f"Cleaning up WebRTCSinkNode '{self.name}' and stopping tracks.")
        if self.audio_track:
            self.audio_track.stop()
        if self.video_track:
            self.video_track.stop()
        
        # Allow any final processing to complete
        await asyncio.sleep(0) 
        
        await super().cleanup()

__all__ = ["WebRTCSinkNode", "PipelineTrack"] 