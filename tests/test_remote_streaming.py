import pytest
import asyncio
from remotemedia.core.pipeline import Pipeline
from remotemedia.nodes.remote import RemoteExecutionNode
from remotemedia.nodes.custom import StatefulCounter
from remotemedia.core.node import RemoteExecutorConfig

async def number_stream(n):
    for i in range(n):
        yield (i,)
        await asyncio.sleep(0.01)

@pytest.mark.asyncio
async def test_remote_streaming_execution():
    """
    Tests end-to-end remote streaming execution of a node.
    """
    pipeline = Pipeline()
    REMOTE_HOST = os.environ.get("REMOTE_HOST", "127.0.0.1")

    remote_config = RemoteExecutorConfig(host=REMOTE_HOST, port=50052, ssl_enabled=False)
    node_config = {"initial_value": 100}
    
    pipeline.add_node(RemoteExecutionNode(
        node_to_execute="StatefulCounter",
        remote_config=remote_config,
        node_config=node_config
    ))

    input_stream = number_stream(5)
    
    output = []
    async with pipeline.managed_execution():
        async for result in pipeline.process(input_stream):
            output.append(result[0])

    expected_output = [100, 101, 102, 103, 104]
    assert output == expected_output 