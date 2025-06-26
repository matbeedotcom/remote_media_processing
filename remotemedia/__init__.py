"""
Remote Media SDK
"""

# Version and author information
__version__ = "0.1.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

# Core classes
from .core import Pipeline, Node, RemoteExecutorConfig

# Exceptions
from .core.exceptions import (
    RemoteMediaError,
    PipelineError,
    NodeError,
    RemoteExecutionError,
    WebRTCError,
)

# WebRTC components
from .webrtc import (
    WebRTCManager,
    WebRTCServer,
    WebRTCStreamSource,
    WebRTCSinkNode,
    PipelineTrack
)


__all__ = [
    # Core classes
    "Pipeline",
    "Node",
    "RemoteExecutorConfig",
    # WebRTC components
    "WebRTCManager",
    "WebRTCServer",
    "WebRTCStreamSource",
    "WebRTCSinkNode",
    "PipelineTrack",
    # Exceptions
    "RemoteMediaError",
    "PipelineError",
    "NodeError",
    "RemoteExecutionError",
    "WebRTCError",
    # Version info
    "__version__",
    "__author__",
    "__email__",
] 