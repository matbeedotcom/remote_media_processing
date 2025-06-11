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


class BatchingNode(Node):
    """
    A node that buffers a specific number of items for batch processing.
    When the batch size is reached, it emits a list of the buffered items.
    """
    
    def __init__(self, batch_size: int = 10, **kwargs):
        """
        Initialize the batching node.
        
        Args:
            batch_size: Maximum number of items to buffer in a batch.
            **kwargs: Additional node parameters
        """
        super().__init__(**kwargs)
        self.batch_size = batch_size
        self.buffer: List[Any] = []
    
    def process(self, data: Any) -> Any:
        """Buffer data and return when the batch is full."""
        self.buffer.append(data)
        logger.debug(f"BatchingNode '{self.name}': buffered item ({len(self.buffer)}/{self.batch_size})")
        
        if len(self.buffer) >= self.batch_size:
            result = self.buffer.copy()
            self.buffer.clear()
            logger.debug(f"BatchingNode '{self.name}': returning batch of {len(result)} items")
            return result
        
        return None  # No output until batch is full
    
    def flush(self) -> List[Any]:
        """Flush the current buffer and return its contents as a final batch."""
        result = self.buffer.copy()
        self.buffer.clear()
        logger.debug(f"BatchingNode '{self.name}': flushed buffer of {len(result)} items")
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


__all__ = ["PassThroughNode", "BatchingNode", "TakeFirstItem"] 