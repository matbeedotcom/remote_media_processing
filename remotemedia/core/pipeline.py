"""
Pipeline class for managing sequences of processing nodes.
"""

from typing import Any, List, Optional, Dict, Iterator, AsyncGenerator
import logging
import time
from contextlib import contextmanager
import asyncio
from inspect import isasyncgen
import inspect

from .node import Node
from .exceptions import PipelineError, NodeError

logger = logging.getLogger(__name__)


class Pipeline:
    """
    Manages a sequence of processing nodes and orchestrates data flow.
    
    The Pipeline class handles execution logic, checking if nodes should
    run remotely, and managing the overall processing workflow.
    """
    
    def __init__(self, name: Optional[str] = None):
        """
        Initialize a new pipeline.
        
        Args:
            name: Optional name for the pipeline
        """
        self.name = name or f"Pipeline_{id(self)}"
        self.nodes: List[Node] = []
        self._is_initialized = False
        self.logger = logging.getLogger(self.__class__.__name__)
        
        self.logger.debug(f"Created pipeline: {self.name}")
    
    def add_node(self, node: Node) -> "Pipeline":
        """
        Add a processing node to the pipeline.
        
        Args:
            node: The node to add
            
        Returns:
            Self for method chaining
            
        Raises:
            PipelineError: If the pipeline is already initialized
        """
        if self._is_initialized:
            raise PipelineError("Cannot add nodes to an initialized pipeline")
        
        if not isinstance(node, Node):
            raise PipelineError(f"Expected Node instance, got {type(node)}")
        
        self.nodes.append(node)
        self.logger.debug(f"Added node '{node.name}' to pipeline '{self.name}'")
        
        return self
    
    def remove_node(self, node_name: str) -> bool:
        """
        Remove a node from the pipeline by name.
        
        Args:
            node_name: Name of the node to remove
            
        Returns:
            True if node was removed, False if not found
            
        Raises:
            PipelineError: If the pipeline is already initialized
        """
        if self._is_initialized:
            raise PipelineError("Cannot remove nodes from an initialized pipeline")
        
        for i, node in enumerate(self.nodes):
            if node.name == node_name:
                removed_node = self.nodes.pop(i)
                self.logger.debug(f"Removed node '{removed_node.name}' from pipeline '{self.name}'")
                return True
        
        return False
    
    def get_node(self, node_name: str) -> Optional[Node]:
        """
        Get a node by name.
        
        Args:
            node_name: Name of the node to find
            
        Returns:
            The node if found, None otherwise
        """
        for node in self.nodes:
            if node.name == node_name:
                return node
        return None
    
    def initialize(self) -> None:
        """
        Initialize the pipeline and all its nodes.
        
        This method must be called before processing data.
        
        Raises:
            PipelineError: If initialization fails
        """
        if self._is_initialized:
            return
        
        if not self.nodes:
            raise PipelineError("Cannot initialize empty pipeline")
        
        self.logger.info(f"Initializing pipeline '{self.name}' with {len(self.nodes)} nodes")
        
        try:
            for node in self.nodes:
                self.logger.debug(f"Initializing node: {node.name}")
                node.initialize()
            
            self._is_initialized = True
            self.logger.info(f"Pipeline '{self.name}' initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize pipeline '{self.name}': {e}")
            # Clean up any partially initialized nodes
            self.cleanup()
            raise PipelineError(f"Pipeline initialization failed: {e}") from e
    
    async def process(self, data: Any = None) -> AsyncGenerator[Any, None]:
        """
        Process data through the entire pipeline asynchronously.

        This method can handle both single-item processing and streaming data
        from source nodes.

        If a node's `process()` method returns an async generator, the pipeline
        will iterate through it, feeding each item to the subsequent nodes.

        Args:
            data: Initial input data. For source nodes, this is typically None.

        Yields:
            The final processed data item(s).
        """
        if not self._is_initialized:
            raise PipelineError("Pipeline must be initialized before processing")

        if not self.nodes:
            self.logger.warning("Cannot process data with an empty pipeline.")
            return

        first_node = self.nodes[0]
        remaining_nodes = self.nodes[1:]

        # If initial data is provided, wrap it in a stream. Otherwise,
        # the first node is the source and its process() method must
        # return the initial stream.
        if data is not None:
            async def _initial_stream_gen(d):
                yield d
            initial_stream = _initial_stream_gen(data)
            # The first node processes the initial data
            nodes_to_process = self.nodes
        else:
            # The first node is the source
            initial_stream = first_node.process(None)
            nodes_to_process = remaining_nodes

        if not inspect.isasyncgen(initial_stream):
            async def _wrap_in_async_gen(d):
                yield d
            current_stream = _wrap_in_async_gen(initial_stream)
        else:
            current_stream = initial_stream
        

        # Chain the remaining nodes together
        for node in nodes_to_process:
            # Create a new generator that applies the current node to the stream
            async def _next_stream_generator(current_node, stream):
                loop = asyncio.get_running_loop()
                async for item in stream:
                    # Execute the node's process method
                    result = await loop.run_in_executor(None, current_node.process, item)
                    
                    # If the result is a stream (async_generator), yield from it
                    if inspect.isasyncgen(result):
                        async for sub_item in result:
                            yield sub_item
                    # Otherwise, just yield the single result
                    else:
                        yield result
            
            current_stream = _next_stream_generator(node, current_stream)

        # Pull the data through the entire pipeline
        async for final_result in current_stream:
            yield final_result
    
    def cleanup(self) -> None:
        """
        Clean up the pipeline and all its nodes.
        
        This method should be called when the pipeline is no longer needed.
        """
        self.logger.info(f"Cleaning up pipeline '{self.name}'")
        
        for node in self.nodes:
            try:
                node.cleanup()
            except Exception as e:
                self.logger.warning(f"Error cleaning up node '{node.name}': {e}")
        
        self._is_initialized = False
        self.logger.debug(f"Pipeline '{self.name}' cleanup completed")
    
    @contextmanager
    def managed_execution(self):
        """
        Context manager for automatic pipeline initialization and cleanup.
        
        Usage:
            with pipeline.managed_execution():
                result = pipeline.process(data)
        """
        try:
            self.initialize()
            yield self
        finally:
            self.cleanup()
    
    @property
    def is_initialized(self) -> bool:
        """Check if the pipeline is initialized."""
        return self._is_initialized
    
    @property
    def node_count(self) -> int:
        """Get the number of nodes in the pipeline."""
        return len(self.nodes)
    
    @property
    def remote_node_count(self) -> int:
        """Get the number of remote nodes in the pipeline."""
        return sum(1 for node in self.nodes if node.is_remote)
    
    def get_config(self) -> Dict[str, Any]:
        """Get the pipeline configuration."""
        return {
            "name": self.name,
            "node_count": self.node_count,
            "remote_node_count": self.remote_node_count,
            "nodes": [node.get_config() for node in self.nodes],
            "is_initialized": self.is_initialized,
        }
    
    def __iter__(self) -> Iterator[Node]:
        """Iterate over nodes in the pipeline."""
        return iter(self.nodes)
    
    def __len__(self) -> int:
        """Get the number of nodes in the pipeline."""
        return len(self.nodes)
    
    def __repr__(self) -> str:
        """String representation of the pipeline."""
        status = "initialized" if self.is_initialized else "not initialized"
        return f"Pipeline(name='{self.name}', nodes={len(self.nodes)}, {status})" 