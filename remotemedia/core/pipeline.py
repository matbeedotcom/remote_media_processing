"""
Pipeline class for managing sequences of processing nodes.
"""

from typing import Any, List, Optional, Dict, Iterator, AsyncGenerator
import logging
import time
from contextlib import contextmanager
from contextlib import asynccontextmanager
import asyncio
from inspect import isasyncgen
import inspect
from concurrent.futures import ThreadPoolExecutor

from .node import Node
from .exceptions import PipelineError, NodeError
from .types import _SENTINEL

logger = logging.getLogger(__name__)

# A unique object to represent an empty item that should be ignored by nodes.
_EMPTY = object()


class Pipeline:
    """
    Manages a sequence of processing nodes and orchestrates data flow.
    
    The Pipeline class handles execution logic, checking if nodes should
    run remotely, and managing the overall processing workflow.
    """
    
    def __init__(self, nodes: Optional[List[Node]] = None, name: Optional[str] = None):
        """
        Initialize a new pipeline.
        
        Args:
            nodes: Optional list of nodes to initialize the pipeline with.
            name: Optional name for the pipeline
        """
        self.name = name or f"Pipeline_{id(self)}"
        self.nodes: List[Node] = []
        self._is_initialized = False
        self.logger = logging.getLogger(self.__class__.__name__)

        if nodes:
            for node in nodes:
                self.add_node(node)
        
        self.logger.info(f"Created pipeline: {self}")
    
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
    
    async def initialize(self) -> None:
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
                await node.initialize()
            
            self._is_initialized = True
            self.logger.info(f"Pipeline '{self.name}' initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize pipeline '{self.name}': {e}")
            # Clean up any partially initialized nodes
            await self.cleanup()
            raise PipelineError(f"Pipeline initialization failed: {e}") from e
    
    async def process(self, stream: Optional[AsyncGenerator[Any, None]] = None) -> AsyncGenerator[Any, None]:
        """
        Process a stream of data through the pipeline asynchronously and in parallel.

        If `stream` is not provided, this method assumes the first node in the
        pipeline is a source node (i.e., its `process` method returns an async
        generator) and uses its output as the stream for the rest of the pipeline.

        Args:
            stream: An optional async generator that yields data chunks for the pipeline.

        Yields:
            The final processed data item(s) from the end of the pipeline.
        """
        if not self._is_initialized:
            raise PipelineError("Pipeline must be initialized before processing")

        if not self.nodes:
            self.logger.warning("Cannot process data with an empty pipeline.")
            return

        nodes_to_process = self.nodes
        input_stream = stream

        if input_stream is None:
            # If no stream is provided, treat the first node as the source.
            source_node = self.nodes[0]
            source_output = source_node.process()

            if not inspect.isasyncgen(source_output):
                raise PipelineError(
                    f"The first node '{source_node.name}' is not a valid source. "
                    "Its process() method must return an async generator."
                )

            input_stream = source_output
            nodes_to_process = self.nodes[1:]

        # If there are no nodes left to process (e.g., pipeline had only a source),
        # then we just yield the results from the source stream.
        if not nodes_to_process:
            async for item in input_stream:
                yield item
            return
        
        loop = asyncio.get_running_loop()
        queues = [asyncio.Queue(maxsize=0) for _ in range(len(nodes_to_process) + 1)]
        executor = ThreadPoolExecutor(max_workers=len(nodes_to_process), thread_name_prefix='PipelineWorker')

        async def _worker(node: Node, in_queue: asyncio.Queue, out_queue: asyncio.Queue):
            self.logger.debug(f"WORKER-START: '{node.name}'")
            try:
                while True:
                    item = await in_queue.get()
                    if item is _SENTINEL:
                        self.logger.debug(f"WORKER-SENTINEL: '{node.name}'")

                        # Flush the node if it has a flush method
                        if hasattr(node, 'flush') and callable(getattr(node, 'flush')):
                            self.logger.debug(f"WORKER-FLUSH: Flushing node '{node.name}'")
                            flush_method = getattr(node, 'flush')
                            if inspect.iscoroutinefunction(flush_method):
                                flushed_result = await flush_method()
                            else:
                                flushed_result = await loop.run_in_executor(executor, flush_method)
                            
                            if flushed_result is not None:
                                self.logger.debug(f"WORKER-FLUSH-RESULT: '{node.name}' produced output.")
                                await out_queue.put(flushed_result)

                        await out_queue.put(_SENTINEL)
                        break
                    
                    # Run the node's process method
                    if inspect.isasyncgenfunction(node.process):
                        async for result in node.process(item):
                            if result is not None:
                                self.logger.debug(f"WORKER-RESULT: '{node.name}' produced output.")
                                await out_queue.put(result)
                    elif inspect.iscoroutinefunction(node.process):
                        result = await node.process(item)
                        if result is not None:
                            self.logger.debug(f"WORKER-RESULT: '{node.name}' produced output.")
                            await out_queue.put(result)
                    else:
                        result = await loop.run_in_executor(executor, node.process, item)
                        if result is not None:
                            self.logger.debug(f"WORKER-RESULT: '{node.name}' produced output.")
                            await out_queue.put(result)

            except Exception as e:
                self.logger.error(f"WORKER-ERROR: in '{node.name}': {e}", exc_info=True)
                await out_queue.put(_SENTINEL)
            finally:
                self.logger.debug(f"WORKER-FINISH: '{node.name}'")

        async def _streaming_worker(node: Node, in_queue: asyncio.Queue, out_queue: asyncio.Queue):
            self.logger.debug(f"STREAMING-WORKER-START: '{node.name}'")
            try:
                # The node's process method will take the input queue and return an async gen
                async def in_stream():
                    while True:
                        item = await in_queue.get()
                        if item is _SENTINEL:
                            break
                        yield item

                # The process method of a streaming node is an async generator
                # that takes an async generator as input.
                if inspect.isasyncgenfunction(node.process):
                    async for result in node.process(in_stream()):
                        if result is not None:
                            await out_queue.put(result)

                # Signal completion
                await out_queue.put(_SENTINEL)

            except Exception as e:
                self.logger.error(f"STREAMING-WORKER-ERROR: in '{node.name}': {e}", exc_info=True)
                await out_queue.put(_SENTINEL)
            finally:
                self.logger.debug(f"STREAMING-WORKER-FINISH: '{node.name}'")

        tasks = []
        for i, node in enumerate(nodes_to_process):
            if getattr(node, 'is_streaming', False):
                task = asyncio.create_task(
                    _streaming_worker(node, queues[i], queues[i+1])
                )
            else:
                task = asyncio.create_task(
                    _worker(node, queues[i], queues[i+1])
                )
            tasks.append(task)

        try:
            # Feeder: Puts data from the input stream into the first queue
            self.logger.debug("FEEDER-START")
            async for item in input_stream:
                await queues[0].put(item)
            await queues[0].put(_SENTINEL)
            self.logger.debug("FEEDER-FINISH")

            # Consumer: Yields results from the final queue
            final_queue = queues[-1]
            while True:
                result = await final_queue.get()
                if result is _SENTINEL:
                    break
                yield result
        finally:
            # Ensure all worker tasks are cancelled
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            executor.shutdown(wait=False)
    
    async def cleanup(self) -> None:
        """
        Clean up the pipeline and all its nodes.
        
        This method should be called when the pipeline is no longer needed.
        """
        self.logger.info(f"Cleaning up pipeline '{self.name}'")
        
        for node in self.nodes:
            try:
                await node.cleanup()
            except Exception as e:
                self.logger.warning(f"Error cleaning up node '{node.name}': {e}")
        
        self._is_initialized = False
        self.logger.debug(f"Pipeline '{self.name}' cleanup completed")
    
    @asynccontextmanager
    async def managed_execution(self):
        """
        Context manager for automatic pipeline initialization and cleanup.
        
        Usage:
            async with pipeline.managed_execution():
                async for result in pipeline.process(data_stream):
                    ...
        """
        try:
            await self.initialize()
            yield self
        finally:
            await self.cleanup()
    
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