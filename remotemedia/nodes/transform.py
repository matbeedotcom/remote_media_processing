"""
Data transformation nodes for the RemoteMedia SDK.
"""

from typing import Any, Callable
import logging
import inspect

from ..core.node import Node

logger = logging.getLogger(__name__)


class TransformNode(Node):
    """
    A generic node that applies a synchronous or asynchronous function
    to each item of data in the pipeline.
    """

    def __init__(self, transform_func: Callable[[Any], Any], **kwargs):
        """
        Initializes the TransformNode.

        Args:
            transform_func: The function to apply to each data item.
                            Can be a regular function or an async function.
        """
        super().__init__(**kwargs)
        if not callable(transform_func):
            raise TypeError("transform_func must be a callable function.")
        self.transform_func = transform_func
        self._is_async = inspect.iscoroutinefunction(transform_func)

    async def process(self, data: Any) -> Any:
        """Applies the transformation function to the data."""
        logger.debug(f"TransformNode '{self.name}': transforming data.")
        if self._is_async:
            return await self.transform_func(data)
        else:
            return self.transform_func(data)


class FormatConverter(Node):
    """Format conversion node."""
    
    def __init__(self, target_format: str = "json", **kwargs):
        super().__init__(**kwargs)
        self.target_format = target_format
    
    def process(self, data: Any) -> Any:
        """Convert data format."""
        # TODO: Implement format conversion
        logger.debug(f"FormatConverter '{self.name}': converting to {self.target_format}")
        return data


__all__ = ["TransformNode", "FormatConverter"] 