"""
Pipeline class for managing sequences of processing nodes.
"""

from typing import Any, List, Optional, Dict, Iterator
import logging
import time
from contextlib import contextmanager

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
        
        logger.debug(f"Created pipeline: {self.name}")
    
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
        logger.debug(f"Added node '{node.name}' to pipeline '{self.name}'")
        
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
                logger.debug(f"Removed node '{removed_node.name}' from pipeline '{self.name}'")
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
        
        logger.info(f"Initializing pipeline '{self.name}' with {len(self.nodes)} nodes")
        
        try:
            for node in self.nodes:
                logger.debug(f"Initializing node: {node.name}")
                node.initialize()
            
            self._is_initialized = True
            logger.info(f"Pipeline '{self.name}' initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize pipeline '{self.name}': {e}")
            # Clean up any partially initialized nodes
            self.cleanup()
            raise PipelineError(f"Pipeline initialization failed: {e}") from e
    
    def process(self, data: Any) -> Any:
        """
        Process data through the entire pipeline.
        
        Args:
            data: Input data to process
            
        Returns:
            Processed data after passing through all nodes
            
        Raises:
            PipelineError: If the pipeline is not initialized or processing fails
        """
        if not self._is_initialized:
            raise PipelineError("Pipeline must be initialized before processing")
        
        if not self.nodes:
            raise PipelineError("Cannot process data with empty pipeline")
        
        logger.debug(f"Processing data through pipeline '{self.name}'")
        start_time = time.time()
        
        try:
            current_data = data
            
            for i, node in enumerate(self.nodes):
                logger.debug(f"Processing node {i+1}/{len(self.nodes)}: {node.name}")
                
                try:
                    if node.is_remote:
                        # TODO: Implement remote execution in Phase 2
                        logger.warning(f"Remote execution not yet implemented for node '{node.name}', running locally")
                        current_data = node.process(current_data)
                    else:
                        current_data = node.process(current_data)
                        
                except Exception as e:
                    logger.error(f"Node '{node.name}' failed: {e}")
                    raise NodeError(f"Node '{node.name}' processing failed: {e}") from e
            
            processing_time = time.time() - start_time
            logger.debug(f"Pipeline '{self.name}' processing completed in {processing_time:.3f}s")
            
            return current_data
            
        except Exception as e:
            logger.error(f"Pipeline '{self.name}' processing failed: {e}")
            raise PipelineError(f"Pipeline processing failed: {e}") from e
    
    def cleanup(self) -> None:
        """
        Clean up the pipeline and all its nodes.
        
        This method should be called when the pipeline is no longer needed.
        """
        logger.info(f"Cleaning up pipeline '{self.name}'")
        
        for node in self.nodes:
            try:
                node.cleanup()
            except Exception as e:
                logger.warning(f"Error cleaning up node '{node.name}': {e}")
        
        self._is_initialized = False
        logger.debug(f"Pipeline '{self.name}' cleanup completed")
    
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