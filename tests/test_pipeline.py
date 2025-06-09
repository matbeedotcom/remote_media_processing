"""
Tests for the Pipeline class.
"""

import pytest
from remotemedia.core.pipeline import Pipeline
from remotemedia.core.node import Node
from remotemedia.core.exceptions import PipelineError


class MockNode(Node):
    """Mock node for testing."""
    
    def __init__(self, return_value=None, **kwargs):
        super().__init__(**kwargs)
        self.return_value = return_value or "processed"
        self.process_called = False
    
    def process(self, data):
        self.process_called = True
        return self.return_value


class TestPipeline:
    """Test cases for the Pipeline class."""
    
    def test_pipeline_creation(self):
        """Test pipeline creation."""
        pipeline = Pipeline(name="test")
        assert pipeline.name == "test"
        assert len(pipeline) == 0
        assert not pipeline.is_initialized
    
    def test_add_node(self):
        """Test adding nodes to pipeline."""
        pipeline = Pipeline()
        node = MockNode(name="test_node")
        
        result = pipeline.add_node(node)
        assert result is pipeline  # Test method chaining
        assert len(pipeline) == 1
        assert pipeline.get_node("test_node") is node
    
    def test_remove_node(self):
        """Test removing nodes from pipeline."""
        pipeline = Pipeline()
        node = MockNode(name="test_node")
        pipeline.add_node(node)
        
        assert pipeline.remove_node("test_node") is True
        assert len(pipeline) == 0
        assert pipeline.get_node("test_node") is None
        
        # Test removing non-existent node
        assert pipeline.remove_node("nonexistent") is False
    
    @pytest.mark.asyncio
    async def test_pipeline_processing(self):
        """Test pipeline data processing."""
        pipeline = Pipeline()
        node1 = MockNode(name="node1", return_value="step1")
        node2 = MockNode(name="node2", return_value="step2")
        
        pipeline.add_node(node1)
        pipeline.add_node(node2)
        
        with pipeline.managed_execution():
            final_result = None
            async for result in pipeline.process("input"):
                final_result = result
            
        assert final_result == "step2"
        assert node1.process_called
        assert node2.process_called
    
    def test_empty_pipeline_error(self):
        """Test that empty pipeline raises error."""
        pipeline = Pipeline()
        
        with pytest.raises(PipelineError, match="Cannot initialize empty pipeline"):
            pipeline.initialize()
    
    @pytest.mark.asyncio
    async def test_uninitialized_processing_error(self):
        """Test that uninitialized pipeline raises error on processing."""
        pipeline = Pipeline()
        pipeline.add_node(MockNode())
        
        with pytest.raises(PipelineError, match="Pipeline must be initialized"):
            # We need to try to start the async generator to trigger the check
            p = pipeline.process("data")
            await p.asend(None)
    
    def test_pipeline_iteration(self):
        """Test pipeline iteration."""
        pipeline = Pipeline()
        nodes = [MockNode(name=f"node{i}") for i in range(3)]
        
        for node in nodes:
            pipeline.add_node(node)
        
        pipeline_nodes = list(pipeline)
        assert len(pipeline_nodes) == 3
        assert all(node in nodes for node in pipeline_nodes) 