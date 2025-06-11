"""
Video processing nodes for the RemoteMedia SDK.
"""

from typing import Any, Tuple
import logging
from .base import TakeFirstItem

from ..core.node import Node

logger = logging.getLogger(__name__)


try:
    import av
    AV_AVAILABLE = True
except ImportError:
    AV_AVAILABLE = False


class DecodeVideoFrame(Node):
    """
    Decodes a raw video packet (from PyAV) into a PIL Image.
    """
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not AV_AVAILABLE:
            raise ImportError("PyAV is not installed. Please install it with 'pip install av'.")

    async def process(self, frame: "av.VideoFrame"):
        """Decodes the video frame into a PIL image."""
        if not isinstance(frame, av.VideoFrame):
            logger.warning(f"DecodeVideoFrame expected av.VideoFrame, got {type(frame)}. Skipping.")
            return None
        return frame.to_image()


class TakeFirstFrameNode(TakeFirstItem):
    """
    A node that takes only the first video frame from a stream and then
    ignores the rest. This is a convenience alias for TakeFirstItem.
    """
    pass


class VideoTransform(Node):
    """Basic video transformation node."""
    
    def __init__(self, resolution: Tuple[int, int] = (1920, 1080), **kwargs):
        super().__init__(**kwargs)
        self.resolution = resolution
    
    def process(self, data: Any) -> Any:
        """Process video data."""
        # TODO: Implement video processing
        logger.debug(f"VideoTransform '{self.name}': processing video at {self.resolution}")
        return data


class VideoBuffer(Node):
    """Video buffering node."""
    
    def process(self, data: Any) -> Any:
        """Buffer video data."""
        # TODO: Implement video buffering
        logger.debug(f"VideoBuffer '{self.name}': buffering video")
        return data


class VideoResizer(Node):
    """Video resizing node."""
    
    def __init__(self, target_resolution: Tuple[int, int] = (1920, 1080), **kwargs):
        super().__init__(**kwargs)
        self.target_resolution = target_resolution
    
    def process(self, data: Any) -> Any:
        """Resize video data."""
        # TODO: Implement video resizing
        logger.debug(f"VideoResizer '{self.name}': resizing to {self.target_resolution}")
        return data


__all__ = ["DecodeVideoFrame", "TakeFirstFrameNode", "VideoTransform", "VideoBuffer", "VideoResizer"] 