"""
Remote Execution Client for the RemoteMedia SDK.

This module provides the client-side interface for communicating with
the remote execution service via gRPC.
"""

import asyncio
import logging
from typing import Any, Dict, Optional, List
import grpc

from ..core.exceptions import RemoteExecutionError
from ..core.node import RemoteExecutorConfig
from ..serialization import JSONSerializer, PickleSerializer

# These will be generated from the proto files
try:
    import sys
    from pathlib import Path
    
    # Add the remote_service/src directory to the path to find the generated gRPC files
    remote_service_src = Path(__file__).parent.parent.parent / "remote_service" / "src"
    if remote_service_src.exists():
        sys.path.insert(0, str(remote_service_src))
    
    import execution_pb2
    import execution_pb2_grpc
    import types_pb2
except ImportError:
    # Fallback for development when proto files aren't generated yet
    execution_pb2 = None
    execution_pb2_grpc = None
    types_pb2 = None

logger = logging.getLogger(__name__)


class RemoteExecutionClient:
    """
    Client for communicating with the remote execution service.
    """
    
    def __init__(self, config: RemoteExecutorConfig):
        """
        Initialize the remote execution client.
        
        Args:
            config: Remote executor configuration
        """
        self.config = config
        self.channel: Optional[grpc.aio.Channel] = None
        self.stub: Optional[Any] = None
        
        # Initialize serializers
        self.serializers = {
            'json': JSONSerializer(),
            'pickle': PickleSerializer(),
        }
        
        logger.debug(f"RemoteExecutionClient initialized for {config.host}:{config.port}")
    
    async def connect(self) -> None:
        """
        Establish connection to the remote execution service.
        
        Raises:
            RemoteExecutionError: If connection fails
        """
        if execution_pb2_grpc is None:
            raise RemoteExecutionError("gRPC proto files not available")
        
        try:
            # Create gRPC channel
            if self.config.ssl_enabled:
                credentials = grpc.ssl_channel_credentials()
                self.channel = grpc.aio.secure_channel(
                    f"{self.config.host}:{self.config.port}",
                    credentials
                )
            else:
                self.channel = grpc.aio.insecure_channel(
                    f"{self.config.host}:{self.config.port}"
                )
            
            # Create stub
            self.stub = execution_pb2_grpc.RemoteExecutionServiceStub(self.channel)
            
            # Test connection with a status request
            await self.get_status()
            
            logger.info(f"Connected to remote execution service at {self.config.host}:{self.config.port}")
            
        except Exception as e:
            logger.error(f"Failed to connect to remote execution service: {e}")
            raise RemoteExecutionError(f"Connection failed: {e}") from e
    
    async def disconnect(self) -> None:
        """Disconnect from the remote execution service."""
        if self.channel:
            await self.channel.close()
            self.channel = None
            self.stub = None
            logger.debug("Disconnected from remote execution service")
    
    async def execute_node(
        self,
        node_type: str,
        config: Dict[str, Any],
        input_data: Any,
        serialization_format: str = "pickle"
    ) -> Any:
        """
        Execute a SDK node remotely.
        
        Args:
            node_type: Type of SDK node to execute
            config: Node configuration parameters
            input_data: Input data to process
            serialization_format: Serialization format to use
            
        Returns:
            Processed output data
            
        Raises:
            RemoteExecutionError: If execution fails
        """
        if not self.stub:
            raise RemoteExecutionError("Not connected to remote service")
        
        try:
            # Serialize input data
            serializer = self.serializers.get(serialization_format)
            if not serializer:
                raise ValueError(f"Unknown serialization format: {serialization_format}")
            
            serialized_input = serializer.serialize(input_data)
            
            # Convert config to string map (gRPC requirement)
            string_config = {k: str(v) for k, v in config.items()}
            
            # Create execution options
            options = types_pb2.ExecutionOptions(
                timeout_seconds=int(self.config.timeout),
                memory_limit_mb=512,  # Default limit
                cpu_limit_percent=100,
                enable_networking=False,
                enable_filesystem=False
            )
            
            # Create request
            request = execution_pb2.ExecuteNodeRequest(
                node_type=node_type,
                config=string_config,
                input_data=serialized_input,
                serialization_format=serialization_format,
                options=options
            )
            
            # Execute with timeout
            response = await asyncio.wait_for(
                self.stub.ExecuteNode(request),
                timeout=self.config.timeout
            )
            
            # Check execution status
            if response.status != types_pb2.EXECUTION_STATUS_SUCCESS:
                error_msg = response.error_message or "Unknown error"
                raise RemoteExecutionError(
                    f"Remote execution failed: {error_msg}",
                    response.error_traceback
                )
            
            # Deserialize output data
            output_data = serializer.deserialize(response.output_data)
            
            logger.debug(f"Successfully executed {node_type} remotely")
            return output_data
            
        except asyncio.TimeoutError:
            logger.error(f"Remote execution timed out for {node_type}")
            raise RemoteExecutionError(f"Execution timed out after {self.config.timeout}s")
        except Exception as e:
            logger.error(f"Error executing {node_type} remotely: {e}")
            raise RemoteExecutionError(f"Remote execution failed: {e}") from e
    
    async def execute_custom_task(
        self,
        code_package: bytes,
        entry_point: str,
        input_data: Any,
        dependencies: Optional[List[str]] = None,
        serialization_format: str = "pickle"
    ) -> Any:
        """
        Execute custom user code remotely (Phase 3 feature).
        
        Args:
            code_package: Packaged user code
            entry_point: Entry point function/method
            input_data: Input data to process
            dependencies: Required Python packages
            serialization_format: Serialization format to use
            
        Returns:
            Processed output data
            
        Raises:
            RemoteExecutionError: If execution fails
        """
        if not self.stub:
            raise RemoteExecutionError("Not connected to remote service")
        
        try:
            # Serialize input data
            serializer = self.serializers.get(serialization_format)
            if not serializer:
                raise ValueError(f"Unknown serialization format: {serialization_format}")
            
            serialized_input = serializer.serialize(input_data)
            
            # Create execution options
            options = types_pb2.ExecutionOptions(
                timeout_seconds=int(self.config.timeout),
                memory_limit_mb=512,
                cpu_limit_percent=100,
                enable_networking=False,
                enable_filesystem=False
            )
            
            # Create request
            request = execution_pb2.ExecuteCustomTaskRequest(
                code_package=code_package,
                entry_point=entry_point,
                input_data=serialized_input,
                serialization_format=serialization_format,
                dependencies=dependencies or [],
                options=options
            )
            
            # Execute with timeout
            response = await asyncio.wait_for(
                self.stub.ExecuteCustomTask(request),
                timeout=self.config.timeout
            )
            
            # Check execution status
            if response.status != types_pb2.EXECUTION_STATUS_SUCCESS:
                error_msg = response.error_message or "Unknown error"
                raise RemoteExecutionError(
                    f"Remote custom task execution failed: {error_msg}",
                    response.error_traceback
                )
            
            # Deserialize output data
            output_data = serializer.deserialize(response.output_data)
            
            logger.debug("Successfully executed custom task remotely")
            return output_data
            
        except asyncio.TimeoutError:
            logger.error("Remote custom task execution timed out")
            raise RemoteExecutionError(f"Execution timed out after {self.config.timeout}s")
        except Exception as e:
            logger.error(f"Error executing custom task remotely: {e}")
            raise RemoteExecutionError(f"Remote execution failed: {e}") from e
    
    async def get_status(self) -> Dict[str, Any]:
        """
        Get status of the remote execution service.
        
        Returns:
            Service status information
            
        Raises:
            RemoteExecutionError: If status request fails
        """
        if not self.stub:
            raise RemoteExecutionError("Not connected to remote service")
        
        try:
            request = execution_pb2.StatusRequest(
                include_metrics=True,
                include_sessions=False
            )
            
            response = await self.stub.GetStatus(request)
            
            return {
                "status": response.status,
                "version": response.version,
                "uptime_seconds": response.uptime_seconds,
                "metrics": {
                    "total_requests": response.metrics.total_requests,
                    "successful_requests": response.metrics.successful_requests,
                    "failed_requests": response.metrics.failed_requests,
                    "active_sessions": response.metrics.active_sessions,
                } if response.metrics else None
            }
            
        except Exception as e:
            logger.error(f"Error getting remote service status: {e}")
            raise RemoteExecutionError(f"Status request failed: {e}") from e
    
    async def list_available_nodes(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List available SDK nodes on the remote service.
        
        Args:
            category: Optional category filter
            
        Returns:
            List of available nodes
            
        Raises:
            RemoteExecutionError: If request fails
        """
        if not self.stub:
            raise RemoteExecutionError("Not connected to remote service")
        
        try:
            request = execution_pb2.ListNodesRequest(category=category or "")
            response = await self.stub.ListNodes(request)
            
            nodes = []
            for node_info in response.available_nodes:
                nodes.append({
                    "node_type": node_info.node_type,
                    "category": node_info.category,
                    "description": node_info.description,
                    "parameters": [
                        {
                            "name": param.name,
                            "type": param.type,
                            "description": param.description,
                            "required": param.required,
                            "default_value": param.default_value,
                        }
                        for param in node_info.parameters
                    ]
                })
            
            return nodes
            
        except Exception as e:
            logger.error(f"Error listing available nodes: {e}")
            raise RemoteExecutionError(f"List nodes request failed: {e}") from e
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect() 