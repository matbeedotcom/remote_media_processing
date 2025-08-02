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
import ast

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


class GeneratorSession:
    """Manages a generator's state for streaming."""
    def __init__(self, generator, session_id: str):
        self.generator = generator
        self.session_id = session_id
        self.created_at = time.time()
        self.last_accessed = time.time()
        self.is_exhausted = False
        self.lock = asyncio.Lock()


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
        self.generator_sessions: Dict[str, GeneratorSession] = {}  # Track generator sessions
        self.connection_objects: Dict[str, Dict[str, Any]] = {}  # Track objects per connection
        self._cleanup_lock = asyncio.Lock()
        
        self.logger = logging.getLogger(__name__)
        self.logger.info("RemoteExecutionServicer initialized")
        
        # Start periodic cleanup task
        asyncio.create_task(self._periodic_cleanup())
    
    def _get_peer_info(self, context: grpc.aio.ServicerContext) -> str:
        """Get a unique identifier for the peer connection."""
        peer = context.peer() if hasattr(context, 'peer') else 'unknown'
        return str(peer)
    
    async def _cleanup_connection_resources(self, connection_id: str) -> None:
        """Clean up all resources associated with a connection."""
        async with self._cleanup_lock:
            if connection_id in self.connection_objects:
                self.logger.info(f"Cleaning up resources for connection: {connection_id}")
                connection_data = self.connection_objects[connection_id]
                
                # Clean up all objects associated with this connection
                for session_id, session_data in list(connection_data.get('sessions', {}).items()):
                    await self._cleanup_session(session_id, session_data)
                
                # Remove connection tracking
                del self.connection_objects[connection_id]
                self.logger.info(f"Completed cleanup for connection: {connection_id}")
    
    async def _cleanup_session(self, session_id: str, session_data: Dict[str, Any]) -> None:
        """Clean up a specific session and its resources."""
        try:
            obj = session_data.get('object')
            if obj:
                # Call cleanup on the object if it has the method
                if hasattr(obj, 'cleanup') and callable(getattr(obj, 'cleanup')):
                    self.logger.info(f"Calling cleanup on object {type(obj).__name__} for session {session_id}")
                    if asyncio.iscoroutinefunction(obj.cleanup):
                        await obj.cleanup()
                    else:
                        obj.cleanup()
                
                # For ML models, explicitly free VRAM
                if hasattr(obj, 'llm_pipeline'):
                    obj.llm_pipeline = None
                if hasattr(obj, '_serve_engine'):
                    obj._serve_engine = None
                if hasattr(obj, 'model'):
                    obj.model = None
                
                # Force garbage collection to free VRAM
                import gc
                gc.collect()
                
                # If torch is available, clear cache
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                        self.logger.info(f"Cleared CUDA cache after cleaning up session {session_id}")
                except ImportError:
                    pass
            
            # Clean up sandbox if exists
            sandbox_path = session_data.get('sandbox_path')
            if sandbox_path:
                code_root = os.path.join(sandbox_path, "code")
                if code_root in sys.path:
                    sys.path.remove(code_root)
                try:
                    import shutil
                    shutil.rmtree(sandbox_path)
                    self.logger.info(f"Removed sandbox directory: {sandbox_path}")
                except Exception as e:
                    self.logger.error(f"Failed to cleanup sandbox {sandbox_path}: {e}")
            
            # Remove from object_sessions if present
            if session_id in self.object_sessions:
                del self.object_sessions[session_id]
                
        except Exception as e:
            self.logger.error(f"Error during session cleanup for {session_id}: {e}", exc_info=True)
    
    async def _periodic_cleanup(self) -> None:
        """Periodically clean up orphaned sessions and free resources."""
        while True:
            try:
                await asyncio.sleep(300)  # Run every 5 minutes
                
                async with self._cleanup_lock:
                    # Clean up orphaned sessions (sessions without connections)
                    orphaned_sessions = []
                    tracked_sessions = set()
                    
                    # Collect all tracked sessions
                    for conn_data in self.connection_objects.values():
                        tracked_sessions.update(conn_data.get('sessions', {}).keys())
                    
                    # Find orphaned sessions
                    for session_id in list(self.object_sessions.keys()):
                        if session_id not in tracked_sessions:
                            orphaned_sessions.append(session_id)
                    
                    # Clean up orphaned sessions
                    if orphaned_sessions:
                        self.logger.info(f"Found {len(orphaned_sessions)} orphaned sessions, cleaning up...")
                        for session_id in orphaned_sessions:
                            session_data = self.object_sessions.get(session_id, {})
                            await self._cleanup_session(session_id, session_data)
                    
                    # Clean up old generator sessions (older than 10 minutes)
                    old_generators = []
                    current_time = time.time()
                    for gen_id, gen_session in self.generator_sessions.items():
                        if current_time - gen_session.last_accessed > 600:  # 10 minutes
                            old_generators.append(gen_id)
                    
                    if old_generators:
                        self.logger.info(f"Cleaning up {len(old_generators)} old generator sessions")
                        for gen_id in old_generators:
                            session = self.generator_sessions[gen_id]
                            # Close generator if possible
                            if hasattr(session.generator, 'aclose'):
                                try:
                                    await session.generator.aclose()
                                except:
                                    pass
                            elif hasattr(session.generator, 'close'):
                                try:
                                    session.generator.close()
                                except:
                                    pass
                            del self.generator_sessions[gen_id]
                    
                    # Force garbage collection and clear CUDA cache
                    import gc
                    gc.collect()
                    
                    try:
                        import torch
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                            self.logger.info("Periodic CUDA cache cleanup completed")
                    except ImportError:
                        pass
                        
            except Exception as e:
                self.logger.error(f"Error during periodic cleanup: {e}", exc_info=True)
    
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
        connection_id = self._get_peer_info(context)
        
        # Track this connection
        if connection_id not in self.connection_objects:
            self.connection_objects[connection_id] = {'sessions': {}}
        
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
                
                # Track this session under the connection
                self.connection_objects[connection_id]['sessions'][session_id] = {
                    "object": obj,
                    "sandbox_path": sandbox_path
                }

                # Initialize object if it has an initialize method
                if hasattr(obj, 'initialize') and callable(getattr(obj, 'initialize')):
                    await obj.initialize()

            # Deserialize arguments
            serializer = PickleSerializer() if request.serialization_format == 'pickle' else JSONSerializer()
            method_args = serializer.deserialize(request.method_args_data)
            
            # Deserialize keyword arguments if provided
            method_kwargs = {}
            if request.method_kwargs_data:
                method_kwargs = serializer.deserialize(request.method_kwargs_data)

            # Handle special proxy initialization
            if request.method_name == "__init__":
                # No-op for proxy initialization
                result = None
            else:
                # Get attribute/method
                attr = getattr(obj, request.method_name)
                
                # Check if it's callable (method) or not (property/attribute)
                if callable(attr):
                    # It's a method - call it
                    if asyncio.iscoroutinefunction(attr):
                        result = await attr(*method_args, **method_kwargs)
                    else:
                        result = attr(*method_args, **method_kwargs)
                    
                    # Handle generators by creating a session instead of materializing
                    if inspect.isgenerator(result) or inspect.isasyncgen(result):
                        # Create generator session
                        generator_id = str(uuid.uuid4())
                        self.generator_sessions[generator_id] = GeneratorSession(
                            generator=result,
                            session_id=generator_id
                        )
                        # Return special marker
                        result = {"__generator__": True, "generator_id": generator_id, 
                                 "is_async": inspect.isasyncgen(result)}
                else:
                    # It's a property or attribute - just return its value
                    result = attr

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
        logger = logging.getLogger(__name__)
        logger.info("New StreamObject connection opened.")
        obj = None
        sandbox_path = None
        session_id = None
        connection_id = self._get_peer_info(context)
        
        # Track this connection
        if connection_id not in self.connection_objects:
            self.connection_objects[connection_id] = {'sessions': {}}
        
        try:
            # The first message from the client MUST be the initialization message.
            logger.debug("Waiting for initialization message...")
            init_request = None
            async for request in request_iterator:
                if request.HasField("init"):
                    init_request = request
                    break
                else:
                    logger.warning("Skipping non-init message while waiting for initialization")
            
            if not init_request:
                logger.error("No initialization message received")
                yield execution_pb2.StreamObjectResponse(error="Stream must be initialized with a StreamObjectInit message.")
                return

            init_request_data = init_request.init
            logger.debug(f"Received init request with session_id: {init_request_data.session_id}")
            
            # If a session ID is provided, use the existing object
            session_id = init_request_data.session_id
            if session_id and session_id in self.object_sessions:
                logger.info(f"StreamObject: Using existing object from session {session_id}")
                obj = self.object_sessions[session_id]['object']
            elif session_id:
                logger.error(f"StreamObject error: Session ID {session_id} not found.")
                yield execution_pb2.StreamObjectResponse(error=f"Session ID {session_id} not found.")
                return
            else:
                # No session ID, create a temporary object for this stream
                logger.info("StreamObject: No session ID, creating temporary object.")
                try:
                    # Create a temporary directory to act as a sandbox
                    sandbox_path = tempfile.mkdtemp(prefix="remotemedia_")
                    logger.debug(f"Created sandbox at {sandbox_path}")
                    
                    # Extract the code package
                    with io.BytesIO(init_request_data.code_package) as bio:
                        with zipfile.ZipFile(bio, 'r') as zf:
                            zf.extractall(sandbox_path)
                            logger.debug("Code package extracted successfully")
                    
                    # Add the code path to sys.path
                    code_root = os.path.join(sandbox_path, "code")
                    sys.path.insert(0, code_root)
                    logger.debug(f"Added {code_root} to sys.path")
                    
                    # Load the serialized object
                    object_pkl_path = os.path.join(sandbox_path, "serialized_object.pkl")
                    logger.debug(f"Loading object from {object_pkl_path}")
                    with open(object_pkl_path, 'r') as f:
                        encoded_obj = f.read()
                    
                    decoded_obj = base64.b64decode(encoded_obj)
                    obj = cloudpickle.loads(decoded_obj)
                    logger.info(f"Successfully loaded object of type {type(obj).__name__}")

                except Exception as e:
                    logger.error(f"Failed to deserialize object: {e}", exc_info=True)
                    yield execution_pb2.StreamObjectResponse(error=f"Failed to deserialize object: {e}")
                    return

            # Check for required methods
            if not hasattr(obj, 'process'):
                 logger.error("StreamObject error: object is missing process method.")
                 yield execution_pb2.StreamObjectResponse(error="Serialized object must have a process method.")
                 return

            logger.info(f"StreamObject: Successfully got object of type {type(obj).__name__}.")

            # Initialization is now handled by the client's initialize() call.
            serialization_format = init_request_data.serialization_format
            if serialization_format == 'pickle':
                serializer = PickleSerializer()
            elif serialization_format == 'json':
                serializer = JSONSerializer()
            else:
                 logger.error(f"StreamObject error: unsupported serialization format '{serialization_format}'.")
                 yield execution_pb2.StreamObjectResponse(error=f"Unsupported serialization format: {serialization_format}")
                 return

            async def input_stream_generator():
                logger.info("StreamObject: Starting input stream processing.")
                chunk_count = 0
                try:
                    async for req in request_iterator:
                        if req.HasField("data"):
                            chunk_count += 1
                            logger.debug(f"Server: Received chunk {chunk_count} for remote object.")
                            yield serializer.deserialize(req.data)
                except Exception as e:
                    logger.error(f"Error in input stream generator: {e}", exc_info=True)
                    raise
                logger.info(f"StreamObject: Input stream finished after {chunk_count} chunks.")

            # Pass the async generator directly to the process method
            logger.info("StreamObject: Calling process() on remote object.")
            try:
                async for result in obj.process(input_stream_generator()):
                    logger.debug("StreamObject: Sending result chunk to client.")
                    serialized_result = serializer.serialize(result)
                    yield execution_pb2.StreamObjectResponse(data=serialized_result)
                logger.info("StreamObject: process() method finished.")
                
                # After the stream is done, flush the object if possible
                if hasattr(obj, 'flush') and callable(getattr(obj, 'flush')):
                    logger.info("StreamObject: Calling flush() on remote object.")
                    if inspect.iscoroutinefunction(obj.flush):
                        flushed_result = await obj.flush()
                    else:
                        flushed_result = obj.flush()
                    if flushed_result is not None:
                        logger.info("StreamObject: Sending flushed result to client.")
                        serialized_result = serializer.serialize(flushed_result)
                        yield execution_pb2.StreamObjectResponse(data=serialized_result)
                
            except Exception as e:
                logger.error(f"Error during object processing: {e}", exc_info=True)
                yield execution_pb2.StreamObjectResponse(error=f"Error during processing: {e}")

        except StopAsyncIteration:
            logger.error("StreamObject error: Client disconnected before sending initialization message.")
            yield execution_pb2.StreamObjectResponse(error="Client disconnected before initialization.")
        except Exception as e:
            logger.error(f"Error during StreamObject execution with object type {type(obj).__name__ if obj else 'Unknown'}: {e}", exc_info=True)
            yield execution_pb2.StreamObjectResponse(error=f"Error during execution: {e}")
        finally:
            # Clean up all resources for this connection
            await self._cleanup_connection_resources(connection_id)
            
            # Additional cleanup for temporary objects (no session_id)
            if not session_id and obj and hasattr(obj, 'cleanup'):
                await obj.cleanup()
            
            # Clean up sandbox if it was created and not tracked in sessions
            if sandbox_path and not session_id:
                code_root = os.path.join(sandbox_path, "code")
                if code_root in sys.path:
                    sys.path.remove(code_root)
                try:
                    import shutil
                    shutil.rmtree(sandbox_path)
                except Exception as e:
                    logger.error(f"Failed to cleanup sandbox {sandbox_path}: {e}")

            logger.info(f"StreamObject connection closed for {connection_id}")
    
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
        connection_id = self._get_peer_info(context)
        session_id = str(uuid.uuid4())
        
        # Track this connection
        if connection_id not in self.connection_objects:
            self.connection_objects[connection_id] = {'sessions': {}}
        
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
                    # Safely evaluate literals like lists, dicts, booleans, numbers
                    config[k] = ast.literal_eval(v)
                except (ValueError, SyntaxError):
                    # Keep it as a string if it's not a literal
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
            
            # Track this node under the connection
            self.connection_objects[connection_id]['sessions'][session_id] = {
                "object": node,
                "node_type": node_type
            }

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
            # Clean up all resources for this connection
            await self._cleanup_connection_resources(connection_id)
            self.logger.info(f"StreamNode connection closed for {connection_id}")
    
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
    
    async def InitGenerator(
        self,
        request: execution_pb2.InitGeneratorRequest,
        context: grpc.aio.ServicerContext
    ) -> execution_pb2.InitGeneratorResponse:
        """Initialize a new generator from an object method."""
        try:
            # Get object from session
            if request.session_id not in self.object_sessions:
                raise ValueError("Session not found")
            
            obj = self.object_sessions[request.session_id]['object']
            
            # Deserialize arguments
            serializer = PickleSerializer() if request.serialization_format == 'pickle' else JSONSerializer()
            method_args = serializer.deserialize(request.method_args_data)
            
            # Deserialize keyword arguments if provided
            method_kwargs = {}
            if request.method_kwargs_data:
                method_kwargs = serializer.deserialize(request.method_kwargs_data)
            
            # Call method to get generator
            attr = getattr(obj, request.method_name)
            if asyncio.iscoroutinefunction(attr):
                result = await attr(*method_args, **method_kwargs)
            else:
                result = attr(*method_args, **method_kwargs)
            
            # Verify it's a generator
            if not (inspect.isgenerator(result) or inspect.isasyncgen(result)):
                raise ValueError(f"Method {request.method_name} did not return a generator")
            
            # Create generator session
            generator_id = str(uuid.uuid4())
            self.generator_sessions[generator_id] = GeneratorSession(
                generator=result,
                session_id=generator_id
            )
            
            return execution_pb2.InitGeneratorResponse(
                status=types_pb2.EXECUTION_STATUS_SUCCESS,
                generator_id=generator_id
            )
        except Exception as e:
            self.logger.error(f"Error in InitGenerator: {e}", exc_info=True)
            return execution_pb2.InitGeneratorResponse(
                status=types_pb2.EXECUTION_STATUS_ERROR,
                error_message=str(e)
            )
    
    async def GetNextBatch(
        self,
        request: execution_pb2.GetNextBatchRequest,
        context: grpc.aio.ServicerContext
    ) -> execution_pb2.GetNextBatchResponse:
        """Get next batch of items from a generator."""
        try:
            if request.generator_id not in self.generator_sessions:
                raise ValueError("Generator session not found")
            
            session = self.generator_sessions[request.generator_id]
            session.last_accessed = time.time()
            
            async with session.lock:
                if session.is_exhausted:
                    return execution_pb2.GetNextBatchResponse(
                        status=types_pb2.EXECUTION_STATUS_SUCCESS,
                        items=[],
                        has_more=False
                    )
                
                serializer = PickleSerializer() if request.serialization_format == 'pickle' else JSONSerializer()
                items = []
                
                for _ in range(request.batch_size):
                    try:
                        if inspect.isasyncgen(session.generator):
                            item = await session.generator.__anext__()
                        else:
                            item = next(session.generator)
                        
                        items.append(serializer.serialize(item))
                    except (StopIteration, StopAsyncIteration):
                        session.is_exhausted = True
                        break
                
                return execution_pb2.GetNextBatchResponse(
                    status=types_pb2.EXECUTION_STATUS_SUCCESS,
                    items=items,
                    has_more=not session.is_exhausted
                )
        except Exception as e:
            self.logger.error(f"Error in GetNextBatch: {e}", exc_info=True)
            return execution_pb2.GetNextBatchResponse(
                status=types_pb2.EXECUTION_STATUS_ERROR,
                error_message=str(e)
            )
    
    async def CloseGenerator(
        self,
        request: execution_pb2.CloseGeneratorRequest,
        context: grpc.aio.ServicerContext
    ) -> execution_pb2.CloseGeneratorResponse:
        """Close and cleanup a generator session."""
        try:
            if request.generator_id in self.generator_sessions:
                session = self.generator_sessions[request.generator_id]
                
                # Close generator if it has close method
                if hasattr(session.generator, 'aclose'):
                    await session.generator.aclose()
                elif hasattr(session.generator, 'close'):
                    session.generator.close()
                
                del self.generator_sessions[request.generator_id]
            
            return execution_pb2.CloseGeneratorResponse(
                status=types_pb2.EXECUTION_STATUS_SUCCESS
            )
        except Exception as e:
            self.logger.error(f"Error in CloseGenerator: {e}", exc_info=True)
            return execution_pb2.CloseGeneratorResponse(
                status=types_pb2.EXECUTION_STATUS_ERROR
            )


class HealthServicer(health_pb2_grpc.HealthServicer):
    """Health check servicer for the gRPC server."""
    
    def Check(self, request, context):
        """Perform health check."""
        return HealthCheckResponse(
            status=HealthCheckResponse.SERVING
        )


async def serve():
    """Starts the gRPC server."""
    # Load configuration
    config = ServiceConfig()
    
    # Set up logging
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    
    # Create gRPC server
    server = grpc.aio.server(
        futures.ThreadPoolExecutor(max_workers=config.max_workers),
        options=[
            ('grpc.max_receive_message_length', -1),
            ('grpc.max_send_message_length', -1)
        ]
    )
    
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