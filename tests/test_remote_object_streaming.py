import pytest
import asyncio
from remotemedia.remote.client import RemoteExecutionClient
from remotemedia.core.node import RemoteExecutorConfig, Node


class TestStreamingObject(Node):
    """A simple stateful streaming object for testing remote execution."""
    
    def __init__(self, initial_value=0, **kwargs):
        super().__init__(**kwargs)
        self.value = initial_value
        self.is_streaming = True

    async def initialize(self):
        # In a real node, this is where you'd acquire resources
        pass

    async def cleanup(self):
        # In a real node, this is where you'd release resources
        pass

    async def process(self, data_stream):
        """
        Increments the internal value for each item received in the stream.
        """
        async for item, in data_stream:
            self.value += item
            yield (self.value,)


async def number_stream(n):
    for i in range(n):
        yield (i,)
        await asyncio.sleep(0.01)


@pytest.fixture(scope="module")
def remote_config():
    return RemoteExecutorConfig(host="127.0.0.1", port=50052, ssl_enabled=False)


@pytest.mark.asyncio
async def test_remote_object_streaming(remote_config):
    """
    Tests end-to-end remote streaming execution of a serialized object.
    """
    streaming_object = TestStreamingObject(initial_value=100)
    input_stream = number_stream(5)
    
    output = []
    async with RemoteExecutionClient(remote_config) as client:
        async for result in client.stream_object(
            obj=streaming_object,
            config={}, 
            input_stream=input_stream
        ):
            output.append(result[0])

    # 0+100, 1+100, 2+101, 3+103, 4+106
    expected_output = [100, 101, 103, 106, 110]
    assert output == expected_output 