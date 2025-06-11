"""
Base Node class and remote execution configuration.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Union
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

    def __call__(self, target: Union[str, "Node"], **kwargs) -> "Node":
        """
        Create a remote execution node from this configuration.

        This method acts as a smart factory. It inspects the `target` argument
        and returns the appropriate remote node wrapper.

        - If `target` is a string, it returns a `RemoteExecutionNode`, which
          tells the server to instantiate a node with that class name.
        - If `target` is a `Node` object instance, it returns a
          `RemoteObjectExecutionNode`, which serializes the object and sends
          it to the server for execution.

        Example:
            config = RemoteExecutorConfig(host="localhost", port=50051)
            
            # Use case 1: Run a pre-registered node on the server by its class name.
            # This creates a RemoteExecutionNode.
            remote_node = config("WhisperTranscriptionNode", node_config={"model": "large-v3"})

            # Use case 2: Run a local node object on the server.
            # This creates a RemoteObjectExecutionNode.
            local_node = MyCustomFilterNode(strength=0.8)
            remote_node = config(local_node)

        Args:
            target (Union[str, "Node"]): The node to execute remotely. This can be
                the class name (str) of a node known to the server, or a local
                Node instance to be serialized and executed.
            **kwargs: Additional arguments for the remote node's constructor.
                      For `RemoteExecutionNode`, this can include `node_config`.

        Returns:
            A `RemoteExecutionNode` or `RemoteObjectExecutionNode` instance.
        """
        # Local import to avoid circular dependencies
        from ..nodes.remote import RemoteExecutionNode, RemoteObjectExecutionNode

        if isinstance(target, str):
            return RemoteExecutionNode(
                node_class_name=target,
                remote_config=self,
                **kwargs
            )
        elif isinstance(target, Node):
            # The object to execute is the target itself
            return RemoteObjectExecutionNode(
                node_object=target,
                remote_config=self,
                **kwargs
            )
        else:
            raise TypeError(
                "Target for remote execution must be a node class name (str) or a Node object."
            )


class Node(ABC):
    """
    Base class for all processing nodes in the pipeline.
    
    A Node represents a single processing step. The core logic is in the
    `process` method. Nodes are chained together in a `Pipeline` to create
    complex data flows.
    """
    
    def __init__(
        self,
        name: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize a processing node.
        
        Args:
            name: Optional name for the node (defaults to class name)
            **kwargs: Additional node-specific parameters
        """
        self.name = name or self.__class__.__name__
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
    
    async def initialize(self) -> None:
        """
        Initialize the node before processing.
        
        This method is called once before the first process() call.
        Override this method to perform any setup required by the node.
        For remote nodes, this method runs on the remote server.
        """
        if self._is_initialized:
            return
            
        self.logger.debug(f"Initializing node: {self.name}")
        self._is_initialized = True
    
    async def cleanup(self) -> None:
        """
        Clean up resources used by the node.
        
        This method is called when the node is no longer needed.
        Override this method to perform any cleanup required by the node.
        """
        self.logger.debug(f"Cleaning up node: {self.name}")
        self._is_initialized = False
    
    @property
    def is_initialized(self) -> bool:
        """Check if this node has been initialized."""
        return self._is_initialized
    
    def get_config(self) -> Dict[str, Any]:
        """Get the node configuration."""
        return {
            "name": self.name,
            "class": self.__class__.__name__,
            "config": self.config,
        }
    
    def __repr__(self) -> str:
        """String representation of the node."""
        return f"{self.__class__.__name__}(name='{self.name}')" 