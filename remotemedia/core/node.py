"""
Base Node class and remote execution configuration.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from dataclasses import dataclass
import logging

from .exceptions import ConfigurationError

logger = logging.getLogger(__name__)


@dataclass
class RemoteExecutorConfig:
    """Configuration for remote execution of a node."""
    
    host: str
    port: int
    protocol: str = "grpc"
    auth_token: Optional[str] = None
    timeout: float = 30.0
    max_retries: int = 3
    ssl_enabled: bool = True
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        if self.protocol not in ["grpc", "http"]:
            raise ConfigurationError(f"Unsupported protocol: {self.protocol}")
        
        if self.port <= 0 or self.port > 65535:
            raise ConfigurationError(f"Invalid port: {self.port}")
        
        if self.timeout <= 0:
            raise ConfigurationError(f"Invalid timeout: {self.timeout}")


class Node(ABC):
    """
    Base class for all processing nodes in the pipeline.
    
    A Node represents a single processing step that can be executed
    locally or remotely. Each node must implement the process() method
    to define its processing logic.
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        remote_config: Optional[RemoteExecutorConfig] = None,
        **kwargs
    ):
        """
        Initialize a processing node.
        
        Args:
            name: Optional name for the node (defaults to class name)
            remote_config: Configuration for remote execution
            **kwargs: Additional node-specific parameters
        """
        self.name = name or self.__class__.__name__
        self.remote_config = remote_config
        self.config = kwargs
        self._is_initialized = False
        self.logger = logging.getLogger(self.__class__.__name__)
        
        self.logger.debug(f"Created node: {self.name}")
    
    @abstractmethod
    def process(self, data: Any) -> Any:
        """
        Process input data and return the result.
        
        This method must be implemented by all concrete node classes.
        
        Args:
            data: Input data to process
            
        Returns:
            Processed data
            
        Raises:
            NodeError: If processing fails
        """
        pass
    
    def initialize(self) -> None:
        """
        Initialize the node before processing.
        
        This method is called once before the first process() call.
        Override this method to perform any setup required by the node.
        """
        if self._is_initialized:
            return
            
        self.logger.debug(f"Initializing node: {self.name}")
        self._initialize_impl()
        self._is_initialized = True
    
    def _initialize_impl(self) -> None:
        """
        Internal initialization implementation.
        
        Override this method in subclasses to provide custom initialization.
        """
        pass
    
    def cleanup(self) -> None:
        """
        Clean up resources used by the node.
        
        This method is called when the node is no longer needed.
        Override this method to perform any cleanup required by the node.
        """
        self.logger.debug(f"Cleaning up node: {self.name}")
        self._cleanup_impl()
        self._is_initialized = False
    
    def _cleanup_impl(self) -> None:
        """
        Internal cleanup implementation.
        
        Override this method in subclasses to provide custom cleanup.
        """
        pass
    
    @property
    def is_remote(self) -> bool:
        """Check if this node is configured for remote execution."""
        return self.remote_config is not None
    
    @property
    def is_initialized(self) -> bool:
        """Check if this node has been initialized."""
        return self._is_initialized
    
    def get_config(self) -> Dict[str, Any]:
        """Get the node configuration."""
        return {
            "name": self.name,
            "class": self.__class__.__name__,
            "remote_config": self.remote_config,
            "config": self.config,
        }
    
    def __repr__(self) -> str:
        """String representation of the node."""
        remote_str = " (remote)" if self.is_remote else ""
        return f"{self.__class__.__name__}(name='{self.name}'){remote_str}" 