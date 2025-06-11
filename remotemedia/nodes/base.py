"""
Basic utility nodes for the RemoteMedia SDK.
"""

from typing import Any, List
import logging

from ..core.node import Node

logger = logging.getLogger(__name__)


class PassThroughNode(Node):
    """
    A node that simply passes data through without modification.
    Useful for debugging and testing pipeline connections.
    """
    async def process(self, data: Any) -> Any:
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


class TakeFirstItem(Node):
    """
    A node that takes only the first item from a stream and then ignores the rest.
    """
    _produced = False
    
    async def process(self, data: Any) -> Any:
        if not self._produced:
            self._produced = True
            return data
        # Return nothing for subsequent calls
        return None


__all__ = ["PassThroughNode", "BufferNode", "TakeFirstItem"] 