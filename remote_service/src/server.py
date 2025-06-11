#!/usr/bin/env python3
"""
RemoteMedia Remote Execution Service - Main gRPC Server

This module implements the main gRPC server for the remote execution service.
It handles incoming requests for executing SDK nodes and user-defined code
in a secure, sandboxed environment.
"""

import asyncio
import logging
import os
import signal
import sys
import time
from concurrent import futures
from typing import Dict, Any, AsyncIterable, AsyncGenerator
import inspect
from concurrent.futures import ThreadPoolExecutor
import uuid

import grpc
from grpc_health.v1 import health_pb2_grpc
from grpc_health.v1.health_pb2 import HealthCheckResponse

# Import generated gRPC code
import execution_pb2
import execution_pb2_grpc
import types_pb2
import zipfile
import io
import tempfile
import base64

# Import service components
from config import ServiceConfig
from executor import TaskExecutor
from sandbox import SandboxManager
from remotemedia.core.node import Node
from remotemedia.serialization import PickleSerializer, JSONSerializer
import cloudpickle
import numpy as np


class RemoteExecutionServicer(execution_pb2_grpc.RemoteExecutionServiceServicer):
    """
    gRPC servicer implementation for remote execution.
    """
    
    def __init__(self, config: ServiceConfig):
        """
        Initialize the remote execution servicer.
        
        Args:
            config: Service configuration
        """
        self.config = config
        self.executor = TaskExecutor(config)
        self.sandbox_manager = SandboxManager(config)
        self.start_time = time.time()
        self.request_count = 0
        self.success_count = 0
        self.error_count = 0
        self.active_sessions: Dict[str, Any] = {}
        self.object_sessions: Dict[str, Any] = {}
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("RemoteExecutionServicer initialized")
    
    async def ExecuteNode(
        self, 
        request: execution_pb2.ExecuteNodeRequest, 
        context: grpc.aio.ServicerContext
    ) -> execution_pb2.ExecuteNodeResponse:
        """
        Execute a predefined SDK node.
        
        Args:
            request: Node execution request
            context: gRPC context
            
        Returns:
            Node execution response
        """
        self.request_count += 1
        start_time = time.time()
        
        self.logger.info(f"Executing SDK node: {request.node_type}")
        
        try:
            # Execute the node using the task executor
            result = await self.executor.execute_sdk_node(
                node_type=request.node_type,
                config=dict(request.config),
                input_data=request.input_data,
                serialization_format=request.serialization_format,
                options=request.options
            )
            
            self.success_count += 1
            
            # Build response
            response = execution_pb2.ExecuteNodeResponse(
                status=types_pb2.EXECUTION_STATUS_SUCCESS,
                output_data=result.output_data,
                metrics=self._build_metrics(start_time, result)
            )
            
            self.logger.info(f"Successfully executed node: {request.node_type}")
            return response
            
        except Exception as e:
            self.error_count += 1
            self.logger.error(f"Error executing node {request.node_type}: {e}")
            
            return execution_pb2.ExecuteNodeResponse(
                status=types_pb2.EXECUTION_STATUS_ERROR,
                error_message=str(e),
                error_traceback=self._get_traceback(),
                metrics=self._build_error_metrics(start_time)
            )
    
    async def ExecuteCustomTask(
        self,
        request: execution_pb2.ExecuteCustomTaskRequest,
        context: grpc.aio.ServicerContext
    ) -> execution_pb2.ExecuteCustomTaskResponse:
        """
        Execute user-defined code (Phase 3 feature).
        
        Args:
            request: Custom task execution request
            context: gRPC context
            
        Returns:
            Custom task execution response
        """
        self.request_count += 1
        start_time = time.time()
        
        self.logger.info("Executing custom task")
        
        try:
            # This will be implemented in Phase 3
            result = await self.executor.execute_custom_task(
                code_package=request.code_package,
                entry_point=request.entry_point,
                input_data=request.input_data,
                serialization_format=request.serialization_format,
                dependencies=list(request.dependencies),
                options=request.options
            )
            
            self.success_count += 1
            
            response = execution_pb2.ExecuteCustomTaskResponse(
                status=types_pb2.EXECUTION_STATUS_SUCCESS,
                output_data=result.output_data,
                metrics=self._build_metrics(start_time, result),
                installed_deps=result.installed_dependencies
            )
            
            self.logger.info("Successfully executed custom task")
            return response
            
        except NotImplementedError:
            self.error_count += 1
            return execution_pb2.ExecuteCustomTaskResponse(
                status=types_pb2.EXECUTION_STATUS_ERROR,
                error_message="Custom task execution not yet implemented (Phase 3)",
                metrics=self._build_error_metrics(start_time)
            )
        except Exception as e:
            self.error_count += 1
            self.logger.error(f"Error executing custom task: {e}")
            
            return execution_pb2.ExecuteCustomTaskResponse(
                status=types_pb2.EXECUTION_STATUS_ERROR,
                error_message=str(e),
                error_traceback=self._get_traceback(),
                metrics=self._build_error_metrics(start_time)
            )
    
    async def ExecuteObjectMethod(
        self,
        request: execution_pb2.ExecuteObjectMethodRequest,
        context: grpc.aio.ServicerContext
    ) -> execution_pb2.ExecuteObjectMethodResponse:
        """Execute a method on a serialized object, using session management."""
        self.logger.info("Executing ExecuteObjectMethod")
        
        session_id = request.session_id
        obj = None
        sandbox_path = None
        
        try:
            if session_id:
                if session_id in self.object_sessions:
                    # Use existing object from session
                    obj = self.object_sessions[session_id]['object']
                    self.logger.info(f"Using existing object from session {session_id}")
                else:
                    raise ValueError("Session not found")
            else:
                # Create new object and session
                session_id = str(uuid.uuid4())
                self.logger.info(f"Creating new session {session_id}")
                
                # Setup sandbox and load object
                sandbox_path = tempfile.mkdtemp(prefix="remotemedia_")
                with io.BytesIO(request.code_package) as bio:
                    with zipfile.ZipFile(bio, 'r') as zf:
                        zf.extractall(sandbox_path)
                
                sys.path.insert(0, os.path.join(sandbox_path, "code"))
                
                object_pkl_path = os.path.join(sandbox_path, "serialized_object.pkl")
                with open(object_pkl_path, 'r') as f:
                    encoded_obj = f.read()
                
                obj = cloudpickle.loads(base64.b64decode(encoded_obj))
                
                self.object_sessions[session_id] = {
                    "object": obj,
                    "sandbox_path": sandbox_path
                }

                # Initialize object if it has an initialize method
                if hasattr(obj, 'initialize') and callable(getattr(obj, 'initialize')):
                    await obj.initialize()

            # Deserialize arguments
            serializer = PickleSerializer() if request.serialization_format == 'pickle' else JSONSerializer()
            method_args = serializer.deserialize(request.method_args_data)

            # Get and call method
            method = getattr(obj, request.method_name)
            
            if asyncio.iscoroutinefunction(method):
                result = await method(*method_args)
            else:
                result = method(*method_args)

            if inspect.isasyncgen(result):
                result = await result.__anext__()

            result_data = serializer.serialize(result)

            return execution_pb2.ExecuteObjectMethodResponse(
                status=types_pb2.EXECUTION_STATUS_SUCCESS,
                result_data=result_data,
                session_id=session_id
            )
        except Exception as e:
            self.logger.error(f"Error during ExecuteObjectMethod: {e}", exc_info=True)
            return execution_pb2.ExecuteObjectMethodResponse(
                status=types_pb2.EXECUTION_STATUS_ERROR,
                error_message=str(e),
                error_traceback=self._get_traceback()
            )
        # Note: We are not cleaning up the session here. A separate mechanism
        # for session timeout/cleanup would be needed in a production system.
    
    async def StreamObject(
        self,
        request_iterator: AsyncIterable[execution_pb2.StreamObjectRequest],
        context: grpc.aio.ServicerContext
    ) -> AsyncGenerator[execution_pb2.StreamObjectResponse, None]:
        """
        Handle bidirectional streaming for a serialized object.
        """
        self.logger.info("New StreamObject connection opened.")
        obj = None
        sandbox_path = None
        
        try:
            # First message is initialization
            init_request_data = await request_iterator.__anext__()
            if not init_request_data.HasField("init"):
                yield execution_pb2.StreamObjectResponse(error="Stream must be initialized with a StreamObjectInit message.")
                return

            init_request = init_request_data.init
            
            code_root = None
            try:
                # Create a temporary directory to act as a sandbox
                sandbox_path = tempfile.mkdtemp(prefix="remotemedia_")
                
                # Extract the code package
                with io.BytesIO(init_request.code_package) as bio:
                    with zipfile.ZipFile(bio, 'r') as zf:
                        zf.extractall(sandbox_path)
                
                # Add the code path to sys.path
                code_root = os.path.join(sandbox_path, "code")
                sys.path.insert(0, code_root)
                
                # Load the serialized object
                object_pkl_path = os.path.join(sandbox_path, "serialized_object.pkl")
                with open(object_pkl_path, 'r') as f:
                    encoded_obj = f.read()
                
                decoded_obj = base64.b64decode(encoded_obj)
                obj = cloudpickle.loads(decoded_obj)

            except Exception as e:
                self.logger.error(f"Failed to deserialize object: {e}")
                yield execution_pb2.StreamObjectResponse(error=f"Failed to deserialize object: {e}")
                return

            # Check for required methods
            if not hasattr(obj, 'initialize') or not hasattr(obj, 'process') or not hasattr(obj, 'cleanup'):
                 yield execution_pb2.StreamObjectResponse(error="Serialized object must have initialize, process, and cleanup methods.")
                 return

            await obj.initialize()

            serialization_format = init_request.serialization_format
            if serialization_format == 'pickle':
                serializer = PickleSerializer()
            elif serialization_format == 'json':
                serializer = JSONSerializer()
            else:
                 yield execution_pb2.StreamObjectResponse(error=f"Unsupported serialization format: {serialization_format}")
                 return

            async def input_stream_generator():
                async for req in request_iterator:
                    if req.HasField("data"):
                        yield serializer.deserialize(req.data)

            # Pass the async generator directly to the process method
            async for result in obj.process(input_stream_generator()):
                serialized_result = serializer.serialize(result)
                yield execution_pb2.StreamObjectResponse(data=serialized_result)

        except Exception as e:
            self.logger.error(f"Error during StreamObject execution with object type {type(obj).__name__}: {e}")
            yield execution_pb2.StreamObjectResponse(error=f"Error during execution: {e}")
        finally:
            if obj and hasattr(obj, 'cleanup'):
                await obj.cleanup()
            
            # Clean up sandbox
            if sandbox_path:
                code_root = os.path.join(sandbox_path, "code")
                if code_root in sys.path:
                    sys.path.remove(code_root)
                try:
                    import shutil
                    shutil.rmtree(sandbox_path)
                except Exception as e:
                    self.logger.error(f"Failed to cleanup sandbox {sandbox_path}: {e}")

            self.logger.info("StreamObject connection closed.")
    
    async def StreamNode(
        self,
        request_iterator: AsyncIterable[execution_pb2.StreamData],
        context: grpc.aio.ServicerContext
    ) -> AsyncGenerator[execution_pb2.StreamData, None]:
        """
        Handle bidirectional streaming for a single node.
        
        The first message from the client must contain the `init` payload
        to configure the node for the stream.
        """
        self.logger.info("New StreamNode connection opened.")
        node = None
        loop = asyncio.get_running_loop()
        executor = ThreadPoolExecutor()
        
        try:
            # The first message is the initialization message
            init_request_data = await request_iterator.__anext__()
            if not init_request_data.HasField("init"):
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("Stream must be initialized with a StreamInit message.")
                return

            init_request = init_request_data.init
            node_type = init_request.node_type
            
            # Convert config values back to their likely types
            config = {}
            for k, v in init_request.config.items():
                try:
                    config[k] = int(v)
                except ValueError:
                    try:
                        config[k] = float(v)
                    except ValueError:
                        if v.lower() in ['true', 'false']:
                            config[k] = v.lower() == 'true'
                        else:
                            config[k] = v

            serialization_format = init_request.serialization_format

            self.logger.info(f"Stream initialized for node type '{node_type}' with config {config}")

            # Dynamically create the node instance from the client library
            # This is a simplification; a real service would have a more robust
            # and secure way of mapping node_type to a class.
            from remotemedia.nodes import __all__ as all_nodes
            from remotemedia import nodes

            if node_type not in all_nodes:
                raise ValueError(f"Node type '{node_type}' is not supported for remote execution.")
            
            NodeClass = getattr(nodes, node_type)
            node = NodeClass(**config)
            await node.initialize()

            # Get the correct serializer
            if serialization_format == 'pickle':
                serializer = PickleSerializer()
            elif serialization_format == 'json':
                serializer = JSONSerializer()
            else:
                raise ValueError(f"Unsupported serialization format: {serialization_format}")

            async def input_stream_generator():
                """Reads from the client stream and yields deserialized data."""
                async for req in request_iterator:
                    if req.HasField("data"):
                        yield serializer.deserialize(req.data)
                    else:
                        self.logger.warning("Received non-data message in stream, ignoring.")

            # Check if the node's process method is a streaming one
            if inspect.isasyncgenfunction(node.process):
                # It's a streaming node, so we pass the generator
                async for result in node.process(input_stream_generator()):
                    serialized_result = serializer.serialize(result)
                    yield execution_pb2.StreamData(data=serialized_result)
            else:
                # It's a standard node, process item by item
                async for item in input_stream_generator():
                    if inspect.iscoroutinefunction(node.process):
                        result = await node.process(item)
                    else:
                        result = await loop.run_in_executor(executor, node.process, item)
                    if result is not None:
                        serialized_result = serializer.serialize(result)
                        yield execution_pb2.StreamData(data=serialized_result)

            # After the stream is done, flush the node if possible
            if hasattr(node, 'flush') and callable(getattr(node, 'flush')):
                if inspect.iscoroutinefunction(node.flush):
                    flushed_result = await node.flush()
                else:
                    flushed_result = node.flush()
                if flushed_result is not None:
                    serialized_result = serializer.serialize(flushed_result)
                    yield execution_pb2.StreamData(data=serialized_result)

        except Exception as e:
            self.logger.error(f"Error during StreamNode execution: {e}", exc_info=True)
            # Send an error message back to the client
            yield execution_pb2.StreamData(error_message=f"Error on server: {e}")
        
        finally:
            if node and hasattr(node, 'cleanup'):
                await node.cleanup()
            self.logger.info("StreamNode connection closed.")
    
    async def GetStatus(
        self,
        request: execution_pb2.StatusRequest,
        context: grpc.aio.ServicerContext
    ) -> execution_pb2.StatusResponse:
        """
        Get service status and health information.
        
        Args:
            request: Status request
            context: gRPC context
            
        Returns:
            Service status response
        """
        uptime = int(time.time() - self.start_time)
        
        metrics = types_pb2.ServiceMetrics(
            total_requests=self.request_count,
            successful_requests=self.success_count,
            failed_requests=self.error_count,
            active_sessions=len(self.active_sessions),
            available_workers=self.config.max_workers,
            busy_workers=0  # TODO: Implement worker tracking
        )
        
        return execution_pb2.StatusResponse(
            status=types_pb2.SERVICE_STATUS_HEALTHY,
            metrics=metrics if request.include_metrics else None,
            version=self.config.version,
            uptime_seconds=uptime
        )
    
    async def ListNodes(
        self,
        request: execution_pb2.ListNodesRequest,
        context: grpc.aio.ServicerContext
    ) -> execution_pb2.ListNodesResponse:
        """
        List available SDK nodes.
        
        Args:
            request: List nodes request
            context: gRPC context
            
        Returns:
            List of available nodes
        """
        available_nodes = await self.executor.get_available_nodes(request.category)
        
        return execution_pb2.ListNodesResponse(
            available_nodes=available_nodes
        )
    
    def _build_metrics(self, start_time: float, result: Any) -> types_pb2.ExecutionMetrics:
        """Build execution metrics from result."""
        end_time = time.time()
        return types_pb2.ExecutionMetrics(
            start_timestamp=int(start_time * 1000),
            end_timestamp=int(end_time * 1000),
            duration_ms=int((end_time - start_time) * 1000),
            input_size_bytes=getattr(result, 'input_size', 0),
            output_size_bytes=getattr(result, 'output_size', 0),
            memory_peak_mb=getattr(result, 'memory_peak', 0),
            cpu_time_ms=getattr(result, 'cpu_time', 0)
        )
    
    def _build_error_metrics(self, start_time: float) -> types_pb2.ExecutionMetrics:
        """Build metrics for failed execution."""
        end_time = time.time()
        return types_pb2.ExecutionMetrics(
            start_timestamp=int(start_time * 1000),
            end_timestamp=int(end_time * 1000),
            duration_ms=int((end_time - start_time) * 1000),
            exit_code=-1
        )
    
    def _get_traceback(self) -> str:
        """Get current exception traceback."""
        import traceback
        return traceback.format_exc()
    
    async def _handle_stream_init(self, init_request) -> str:
        """Handle streaming session initialization."""
        # TODO: Implement streaming session management
        session_id = f"session_{int(time.time() * 1000)}"
        self.active_sessions[session_id] = {
            'created': time.time(),
            'node_type': init_request.node_type,
            'processed_items': 0
        }
        return session_id
    
    async def _handle_stream_data(self, data_request):
        """Handle streaming data processing."""
        # TODO: Implement streaming data processing
        return execution_pb2.StreamDataResponse(
            session_id=data_request.session_id,
            output_data=data_request.input_data  # Echo for now
        )
    
    async def _handle_stream_close(self, close_request):
        """Handle streaming session closure."""
        session_id = close_request.session_id
        if session_id in self.active_sessions:
            session = self.active_sessions[session_id]
            return execution_pb2.StreamCloseResponse(
                session_id=session_id,
                total_metrics=types_pb2.ExecutionMetrics(
                    duration_ms=int((time.time() - session['created']) * 1000)
                )
            )
        return execution_pb2.StreamCloseResponse(session_id=session_id)


class HealthServicer(health_pb2_grpc.HealthServicer):
    """Health check servicer for the gRPC server."""
    
    def Check(self, request, context):
        """Perform health check."""
        return HealthCheckResponse(
            status=HealthCheckResponse.SERVING
        )


async def serve():
    """Start the gRPC server."""
    # Load configuration
    config = ServiceConfig()
    
    # Set up logging
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    # Create gRPC server
    server = grpc.aio.server(futures.ThreadPoolExecutor(max_workers=config.max_workers))
    
    # Add servicers
    execution_pb2_grpc.add_RemoteExecutionServiceServicer_to_server(
        RemoteExecutionServicer(config), server
    )
    health_pb2_grpc.add_HealthServicer_to_server(HealthServicer(), server)
    
    # Configure server
    listen_addr = f'0.0.0.0:{config.grpc_port}'
    server.add_insecure_port(listen_addr)
    
    # Start server
    logger.info(f"Starting RemoteMedia Execution Service on {listen_addr}")
    await server.start()
    
    # Set up graceful shutdown
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        asyncio.create_task(server.stop(grace=10))
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Wait for server termination
    await server.wait_for_termination()
    logger.info("Server stopped")


if __name__ == '__main__':
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        print("Server interrupted")
        sys.exit(0) 