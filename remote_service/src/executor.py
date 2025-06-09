"""
Task Executor for the Remote Execution Service.

This module handles the execution of SDK nodes and user-defined tasks
in a secure, controlled environment.
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass

# Import SDK components
try:
    from remotemedia.nodes import (
        PassThroughNode, BufferNode,
        AudioTransform, AudioBuffer, AudioResampler,
        VideoTransform, VideoBuffer, VideoResizer,
        DataTransform, FormatConverter,
        CalculatorNode, CodeExecutorNode, TextProcessorNode,
        SerializedClassExecutorNode
    )
    from remotemedia.serialization import JSONSerializer, PickleSerializer
    from remotemedia.core.node import Node
    SDK_AVAILABLE = True
except ImportError:
    # Fallback for development/testing
    logging.warning("RemoteMedia SDK not available, using mock implementations")
    SDK_AVAILABLE = False
    Node = object
    PassThroughNode = BufferNode = None
    AudioTransform = AudioBuffer = AudioResampler = None
    VideoTransform = VideoBuffer = VideoResizer = None
    DataTransform = FormatConverter = None
    CalculatorNode = CodeExecutorNode = TextProcessorNode = None
    SerializedClassExecutorNode = None
    JSONSerializer = PickleSerializer = None

from config import ServiceConfig


@dataclass
class ExecutionResult:
    """Result of task execution."""
    output_data: bytes
    input_size: int
    output_size: int
    memory_peak: int
    cpu_time: int
    installed_dependencies: List[str] = None


class TaskExecutor:
    """
    Handles execution of SDK nodes and custom tasks.
    """
    
    def __init__(self, config: ServiceConfig):
        """
        Initialize the task executor.
        
        Args:
            config: Service configuration
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Initialize serializers
        self.serializers = {
            'json': JSONSerializer() if JSONSerializer else self._get_json_serializer(),
            'pickle': PickleSerializer() if PickleSerializer else self._get_pickle_serializer(),
        }
        
        # Build node registry from SDK
        self.node_registry = self._build_sdk_node_registry()
        
        self.logger.info(f"TaskExecutor initialized with {len(self.node_registry)} node types")
    
    def _build_sdk_node_registry(self) -> Dict[str, type]:
        """Build registry of available SDK nodes."""
        registry = {}
        
        if SDK_AVAILABLE:
            # Base nodes
            if PassThroughNode:
                registry['PassThroughNode'] = PassThroughNode
            if BufferNode:
                registry['BufferNode'] = BufferNode
            
            # Audio nodes
            if AudioTransform:
                registry['AudioTransform'] = AudioTransform
            if AudioBuffer:
                registry['AudioBuffer'] = AudioBuffer
            if AudioResampler:
                registry['AudioResampler'] = AudioResampler
            
            # Video nodes
            if VideoTransform:
                registry['VideoTransform'] = VideoTransform
            if VideoBuffer:
                registry['VideoBuffer'] = VideoBuffer
            if VideoResizer:
                registry['VideoResizer'] = VideoResizer
            
            # Transform nodes
            if DataTransform:
                registry['DataTransform'] = DataTransform
            if FormatConverter:
                registry['FormatConverter'] = FormatConverter
            
            # Utility nodes
            if CalculatorNode:
                registry['CalculatorNode'] = CalculatorNode
            if CodeExecutorNode:
                registry['CodeExecutorNode'] = CodeExecutorNode
            if TextProcessorNode:
                registry['TextProcessorNode'] = TextProcessorNode
            if SerializedClassExecutorNode:
                registry['SerializedClassExecutorNode'] = SerializedClassExecutorNode
            
            self.logger.info(f"Registered {len(registry)} SDK nodes")
        else:
            self.logger.warning("SDK not available, no nodes registered")
        
        return registry
    
    def _get_json_serializer(self):
        """Get primitive JSON serializer."""
        import json
        
        class PrimitiveJSONSerializer:
            def serialize(self, data):
                return json.dumps(data).encode('utf-8')
            
            def deserialize(self, data):
                return json.loads(data.decode('utf-8'))
        
        return PrimitiveJSONSerializer()
    
    def _get_pickle_serializer(self):
        """Get primitive Pickle serializer."""
        import pickle
        
        class PrimitivePickleSerializer:
            def serialize(self, data):
                return pickle.dumps(data)
            
            def deserialize(self, data):
                return pickle.loads(data)
        
        return PrimitivePickleSerializer()
    
    async def execute_sdk_node(
        self,
        node_type: str,
        config: Dict[str, Any],
        input_data: bytes,
        serialization_format: str,
        options: Any
    ) -> ExecutionResult:
        """
        Execute a predefined SDK node.
        
        Args:
            node_type: Type of SDK node to execute
            config: Node configuration parameters
            input_data: Serialized input data
            serialization_format: Format used for serialization
            options: Execution options
            
        Returns:
            Execution result
            
        Raises:
            ValueError: If node type is not available
            RuntimeError: If execution fails
        """
        start_time = time.time()
        
        self.logger.info(f"Executing SDK node: {node_type}")
        
        # Check if node type is available
        if node_type not in self.node_registry:
            available = list(self.node_registry.keys())
            raise ValueError(f"Unknown node type: {node_type}. Available: {available}")
        
        # Get serializer
        serializer = self.serializers.get(serialization_format)
        if not serializer:
            raise ValueError(f"Unknown serialization format: {serialization_format}")
        
        try:
            # Deserialize input data
            input_obj = serializer.deserialize(input_data)
            input_size = len(input_data)
            
            # Create and configure node using SDK
            node_class = self.node_registry[node_type]
            node = node_class(name=f"remote_{node_type}", **config)
            
            # Initialize node (if method exists)
            if hasattr(node, 'initialize'):
                await node.initialize()
            
            # Execute node
            output_obj = node.process(input_obj)
            
            # Serialize output
            output_data = serializer.serialize(output_obj)
            output_size = len(output_data)
            
            # Clean up node (if method exists)
            if hasattr(node, 'cleanup'):
                await node.cleanup()
            
            execution_time = int((time.time() - start_time) * 1000)
            
            self.logger.info(f"Successfully executed {node_type} in {execution_time}ms")
            
            return ExecutionResult(
                output_data=output_data,
                input_size=input_size,
                output_size=output_size,
                memory_peak=0,  # TODO: Implement memory tracking
                cpu_time=execution_time
            )
            
        except Exception as e:
            self.logger.error(f"Error executing SDK node {node_type}: {e}")
            raise RuntimeError(f"Node execution failed: {e}") from e
    
    async def execute_custom_task(
        self,
        code_package: bytes,
        entry_point: str,
        input_data: bytes,
        serialization_format: str,
        dependencies: List[str],
        options: Any
    ) -> ExecutionResult:
        """
        Execute user-defined code (Phase 3 feature).
        
        Args:
            code_package: Packaged user code
            entry_point: Entry point function/method
            input_data: Serialized input data
            serialization_format: Serialization format
            dependencies: Required Python packages
            options: Execution options
            
        Returns:
            Execution result
            
        Raises:
            NotImplementedError: This feature is not yet implemented
        """
        self.logger.warning("Custom task execution not yet implemented (Phase 3)")
        raise NotImplementedError("Custom task execution will be implemented in Phase 3")
    
    async def get_available_nodes(self, category: Optional[str] = None) -> List[Any]:
        """
        Get list of available SDK nodes.
        
        Args:
            category: Optional category filter
            
        Returns:
            List of available nodes
        """
        nodes = []
        
        for node_type, node_class in self.node_registry.items():
            # Determine category based on node type
            if 'Audio' in node_type:
                node_category = 'audio'
            elif 'Video' in node_type:
                node_category = 'video'
            elif 'Transform' in node_type or 'Converter' in node_type:
                node_category = 'transform'
            elif 'Calculator' in node_type:
                node_category = 'math'
            elif 'Code' in node_type or 'Serialized' in node_type:
                node_category = 'execution'
            elif 'Text' in node_type:
                node_category = 'text'
            else:
                node_category = 'base'
            
            # Apply category filter
            if category and node_category != category:
                continue
            
            # Create node info
            node_info = {
                'node_type': node_type,
                'category': node_category,
                'description': getattr(node_class, '__doc__', f"{node_type} processing node") or f"{node_type} processing node",
                'parameters': []  # TODO: Extract parameters from node class
            }
            nodes.append(node_info)
        
        return nodes
    
    def _extract_node_parameters(self, node_class: type) -> List[Dict[str, Any]]:
        """
        Extract parameter information from a node class.
        
        Args:
            node_class: Node class to inspect
            
        Returns:
            List of parameter information
        """
        # TODO: Implement parameter extraction using inspection
        # This would analyze the __init__ method signature and docstrings
        return [] 