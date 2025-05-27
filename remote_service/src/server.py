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
from typing import Dict, Any

import grpc
from grpc_health.v1 import health_pb2_grpc
from grpc_health.v1.health_pb2 import HealthCheckResponse

# Import generated gRPC code
import execution_pb2
import execution_pb2_grpc
import types_pb2

# Import service components
from config import ServiceConfig
from executor import TaskExecutor
from sandbox import SandboxManager


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
    
    async def StreamExecute(
        self,
        request_iterator,
        context: grpc.aio.ServicerContext
    ):
        """
        Handle bidirectional streaming execution.
        
        Args:
            request_iterator: Stream of execution requests
            context: gRPC context
            
        Yields:
            Stream of execution responses
        """
        self.logger.info("Starting streaming execution session")
        
        session_id = None
        try:
            async for request in request_iterator:
                if request.HasField('init'):
                    # Initialize streaming session
                    session_id = await self._handle_stream_init(request.init)
                    yield execution_pb2.StreamExecuteResponse(
                        init=execution_pb2.StreamInitResponse(
                            session_id=session_id,
                            status=types_pb2.EXECUTION_STATUS_SUCCESS
                        )
                    )
                elif request.HasField('data'):
                    # Process data in streaming session
                    response = await self._handle_stream_data(request.data)
                    yield execution_pb2.StreamExecuteResponse(data=response)
                elif request.HasField('close'):
                    # Close streaming session
                    response = await self._handle_stream_close(request.close)
                    yield execution_pb2.StreamExecuteResponse(close=response)
                    break
                    
        except Exception as e:
            self.logger.error(f"Error in streaming session {session_id}: {e}")
            yield execution_pb2.StreamExecuteResponse(
                error=execution_pb2.StreamErrorResponse(
                    session_id=session_id or "unknown",
                    error_message=str(e),
                    error_traceback=self._get_traceback()
                )
            )
        finally:
            if session_id and session_id in self.active_sessions:
                del self.active_sessions[session_id]
    
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
    listen_addr = f'[::]:{config.grpc_port}'
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