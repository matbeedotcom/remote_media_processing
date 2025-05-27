"""
Basic utility nodes for the RemoteMedia SDK.
"""

from typing import Any, List
import logging

from ..core.node import Node

logger = logging.getLogger(__name__)


class PassThroughNode(Node):
    """A node that passes data through without modification."""
    
    def process(self, data: Any) -> Any:
        """Pass data through unchanged."""
        logger.debug(f"PassThroughNode '{self.name}': passing through data")
        return data


class BufferNode(Node):
    """A node that buffers data for batch processing."""
    
    def __init__(self, buffer_size: int = 10, **kwargs):
        """
        Initialize the buffer node.
        
        Args:
            buffer_size: Maximum number of items to buffer
            **kwargs: Additional node parameters
        """
        super().__init__(**kwargs)
        self.buffer_size = buffer_size
        self.buffer: List[Any] = []
    
    def process(self, data: Any) -> Any:
        """Buffer data and return when buffer is full."""
        self.buffer.append(data)
        logger.debug(f"BufferNode '{self.name}': buffered item ({len(self.buffer)}/{self.buffer_size})")
        
        if len(self.buffer) >= self.buffer_size:
            result = self.buffer.copy()
            self.buffer.clear()
            logger.debug(f"BufferNode '{self.name}': returning buffer of {len(result)} items")
            return result
        
        return None  # No output until buffer is full
    
    def flush(self) -> List[Any]:
        """Flush the current buffer and return its contents."""
        result = self.buffer.copy()
        self.buffer.clear()
        logger.debug(f"BufferNode '{self.name}': flushed buffer of {len(result)} items")
        return result


__all__ = ["PassThroughNode", "BufferNode"] 