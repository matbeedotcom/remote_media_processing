"""
Node for executing other nodes on a remote service.
"""
from typing import Any, Dict, AsyncGenerator, Optional
import logging
import asyncio

from ..core.node import Node, RemoteExecutorConfig
from ..core.exceptions import NodeError
from ..remote.client import RemoteExecutionClient

logger = logging.getLogger(__name__)


class RemoteExecutionNode(Node):
    """
    A gateway node that executes a specified node type on a remote service.
    
    This node acts as a bridge in a local pipeline, sending its input data
    to a remote service for processing by another node and then passing the
    result on to the next local node. This version supports streaming.
    """

    def __init__(self, node_to_execute: str, remote_config: RemoteExecutorConfig, 
                 node_config: Dict[str, Any] = None, serialization_format: str = "pickle", **kwargs):
        """
        Initializes the RemoteExecutionNode.

        Args:
            node_to_execute (str): The class name of the node to execute remotely.
            remote_config (RemoteExecutorConfig): Configuration for the remote connection.
            node_config (Dict[str, Any], optional): The configuration for the remote node itself. Defaults to None.
            serialization_format (str, optional): Serialization format to use. Defaults to "pickle".
        """
        super().__init__(**kwargs)
        if not isinstance(remote_config, RemoteExecutorConfig):
            raise ValueError("remote_config must be a valid RemoteExecutorConfig instance.")
            
        self.node_to_execute = node_to_execute
        self.remote_config = remote_config
        self.node_config = node_config or {}
        self.serialization_format = serialization_format
        self.is_streaming = True  # Mark as a streaming node
        self.client: RemoteExecutionClient = None

    async def initialize(self):
        """Initializes the remote execution client and connects."""
        await super().initialize()
        self.client = RemoteExecutionClient(self.remote_config)
        await self.client.connect()
        logger.info(f"RemoteExecutionNode '{self.name}' connected to {self.remote_config.host}:{self.remote_config.port}")

    async def cleanup(self):
        """Cleans up the client connection."""
        if self.client:
            await self.client.disconnect()
            logger.info(f"RemoteExecutionNode '{self.name}' disconnected.")
        await super().cleanup()

    async def process(self, data_stream: AsyncGenerator[Any, None]) -> AsyncGenerator[Any, None]:
        """
        Sends a stream of data to the remote service for execution and yields the results.
        """
        if not self.client or not self.client.stub:
            raise NodeError("Remote client not initialized or connected.")

        logger.debug(f"RemoteExecutionNode '{self.name}': starting stream to remote for node '{self.node_to_execute}'")

        try:
            async for result in self.client.stream_node(
                node_type=self.node_to_execute,
                config=self.node_config,
                input_stream=data_stream,
                serialization_format=self.serialization_format
            ):
                yield result
        except Exception as e:
            logger.error(f"RemoteExecutionNode '{self.name}': Failed to stream remote node '{self.node_to_execute}'. Error: {e}")
            # The exception will be propagated by the pipeline
            raise

    def __repr__(self) -> str:
        """String representation of the node."""
        return f"{self.__class__.__name__}(name='{self.name}', target='{self.node_to_execute}')"


class RemoteObjectExecutionNode(Node):
    """
    A node that executes a cloudpickled Python object on a remote server.
    """
    def __init__(self, obj_to_execute: Any, remote_config: RemoteExecutorConfig, node_config: Optional[Dict[str, Any]] = None, **kwargs):
        super().__init__(**kwargs)
        if not all(hasattr(obj_to_execute, attr) for attr in ['initialize', 'process', 'cleanup']):
            raise ValueError("The object to execute must have initialize, process, and cleanup methods.")
            
        if not isinstance(remote_config, RemoteExecutorConfig):
            raise ValueError("remote_config must be a valid RemoteExecutorConfig instance.")

        self.obj_to_execute = obj_to_execute
        self.remote_config = remote_config
        self.node_config = node_config or {}
        self.client: Optional[RemoteExecutionClient] = None
        self.is_streaming = getattr(self.obj_to_execute, 'is_streaming', False)

    async def initialize(self):
        """Initializes the remote execution client."""
        await super().initialize()
        self.client = RemoteExecutionClient(self.remote_config)
        await self.client.connect()

    async def cleanup(self):
        """Disconnects the remote execution client."""
        if self.client:
            await self.client.disconnect()
            self.client = None
        await super().cleanup()

    async def process(self, data: Any) -> AsyncGenerator[Any, None]:
        """
        Processes data by sending it to the remote object.
        Handles both streaming and non-streaming cases.
        """
        if not self.client:
            raise NodeError("Remote client not initialized.")
        
        if self.is_streaming:
            # We need to wrap the input stream to serialize each item before sending.
            # The remote end will deserialize each item.
            async def serialized_stream_generator(input_stream: AsyncGenerator[Any, None]):
                async for item in input_stream:
                    yield item

            try:
                async for result in self.client.stream_object(
                    obj=self.obj_to_execute,
                    config=self.node_config,
                    input_stream=serialized_stream_generator(data)
                ):
                    yield result
            except Exception as e:
                self.logger.error(f"Error streaming object remotely: {e}", exc_info=True)
                raise NodeError("Remote object stream failed") from e
        else:
            # Non-streaming case: process a single item
            try:
                # We need a new client method for single-item execution
                # For now, let's assume it exists and is called `execute_object_method`
                result = await self.client.execute_object_method(
                    obj=self.obj_to_execute,
                    method_name='process',
                    method_args=[data]
                )
                yield result
            except Exception as e:
                self.logger.error(f"Error executing object method remotely: {e}")
                raise NodeError("Remote object execution failed") from e

    def __repr__(self) -> str:
        """String representation of the node."""
        target_name = getattr(self.obj_to_execute, 'name', self.obj_to_execute.__class__.__name__)
        return f"{self.__class__.__name__}(name='{self.name}', target='{target_name}')"


__all__ = ["RemoteExecutionNode", "RemoteObjectExecutionNode"] 