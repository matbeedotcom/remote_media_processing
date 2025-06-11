import pytest
import asyncio
import os

from remotemedia.core.node import RemoteExecutorConfig

# A flag to check if ML dependencies are available.
# We avoid a top-level import to prevent collection-time errors if torch is broken.
ml_deps_installed = False
try:
    import transformers
    import torch
    ml_deps_installed = True
except ImportError:
    pass

# Pytest marker to skip tests if ML dependencies are not installed
pytestmark = [
    pytest.mark.skipif(
        not ml_deps_installed,
        reason="ML dependencies (transformers, torch) not installed or broken"
    ),
    pytest.mark.asyncio,
]


async def test_transformers_pipeline_node_text_classification():
    """
    Tests the TransformersPipelineNode with a text-classification task
    running locally. This test uses the real model.
    """
    # Import the node here to avoid collection-time errors
    from remotemedia.nodes.ml import TransformersPipelineNode

    task = "text-classification"
    # Use a small, fast model for testing
    model = "distilbert-base-uncased-finetuned-sst-2-english"

    # Instantiate the node
    node = TransformersPipelineNode(task=task, model=model, device="mps")

    # Initialize the node (this will download the model on the first run)
    await node.initialize()

    # Process a sample text
    input_text = "This is a fantastic library!"
    result = await node.process(input_text)

    # Validate the output
    assert isinstance(result, list)
    assert "score" in result[0]
    assert result[0]['label'] == 'POSITIVE'
    # The score should be high for a clearly positive statement
    assert result[0]['score'] > 0.9

    # Clean up the node's resources
    await node.cleanup()
    assert node.pipe is None


async def test_remote_transformers_pipeline_node(tmp_path):
    """
    Tests that a TransformersPipelineNode can be executed remotely via
    RemoteObjectExecutionNode using the real model.
    """
    from remotemedia.nodes.ml import TransformersPipelineNode
    from remotemedia.nodes.remote import RemoteObjectExecutionNode
    from remote_service.src.server import serve

    # Define a simple text classification node instance.
    # This object will be sent to the server, which will initialize it,
    # causing the real model to be downloaded there.
    classifier_object = TransformersPipelineNode(
        task="text-classification",
        model="distilbert-base-uncased-finetuned-sst-2-english",
        device="mps"
    )

    # Use a high port to avoid conflicts
    port = 50099
    os.environ["GRPC_PORT"] = str(port)
    server_task = None

    try:
        # Run the server in the background
        server_task = asyncio.create_task(serve())
        # Give the server a moment to start
        await asyncio.sleep(1)

        # Create a client to connect to the server
        remote_exec_node = RemoteObjectExecutionNode(
            obj_to_execute=classifier_object,
            remote_config=RemoteExecutorConfig(host="127.0.0.1", port=port, ssl_enabled=False)
        )

        # The remote node also needs to be initialized
        await remote_exec_node.initialize()

        # Process data through the remote node
        input_text = "This is a fantastic library!"
        result_stream = remote_exec_node.process(input_text)
        results = [res async for res in result_stream]

        # Clean up the remote node
        await remote_exec_node.cleanup()

        # Assertions
        assert len(results) == 1
        result_data = results[0]

        # The remote node returns a dictionary with the result and session_id
        assert isinstance(result_data, dict)
        assert "result" in result_data
        assert "session_id" in result_data

        result = result_data["result"]
        assert isinstance(result, list)
        assert "score" in result[0]
        assert result[0]['label'] == 'POSITIVE'
        assert result[0]['score'] > 0.9

    finally:
        # Stop the server
        if server_task:
            server_task.cancel()
            try:
                await server_task
            except asyncio.CancelledError:
                pass  # Expected
        # Clean up environment variable
        if "GRPC_PORT" in os.environ:
            del os.environ["GRPC_PORT"] 