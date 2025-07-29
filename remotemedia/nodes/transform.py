"""
Data transformation nodes for the RemoteMedia SDK.
"""

from typing import Any, Callable
import logging

from ..core.node import Node

logger = logging.getLogger(__name__)


class DataTransform(Node):
    """Generic data transformation node."""
    
    def process(self, data: Any) -> Any:
        """Transform data."""
        # TODO: Implement data transformation
        logger.debug(f"DataTransform '{self.name}': transforming data")
        return data


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


class TextTransformNode(Node):
    """Node for transforming text using a custom function."""
    
    def __init__(self, transform_func: Callable[[str], str], **kwargs):
        """
        Initialize the text transform node.
        
        Args:
            transform_func: Function that takes a string and returns a transformed string
        """
        super().__init__(**kwargs)
        self.transform_func = transform_func
    
    def process(self, data: Any) -> Any:
        """Transform text data using the provided function."""
        if isinstance(data, str):
            result = self.transform_func(data)
            logger.debug(f"TextTransformNode '{self.name}': transformed '{data}' -> '{result}'")
            return result
        elif isinstance(data, tuple) and len(data) > 0 and isinstance(data[0], str):
            # Handle (text, metadata) tuples
            transformed_text = self.transform_func(data[0])
            result = (transformed_text,) + data[1:]
            logger.debug(f"TextTransformNode '{self.name}': transformed tuple text")
            return result
        else:
            # Pass through non-text data unchanged
            logger.debug(f"TextTransformNode '{self.name}': passing through non-text data: {type(data)}")
            return data


__all__ = ["DataTransform", "FormatConverter", "TextTransformNode"] 