import pytest
import asyncio
import base64
import cloudpickle

from remotemedia.core.node import RemoteExecutorConfig
from remotemedia.remote.client import RemoteExecutionClient
from remotemedia.nodes.custom import StatefulCounter

# A simple stateful class for testing
class StatefulCounter:
    def __init__(self, initial_value=0):
        self.value = initial_value

    def increment(self):
        self.value += 1
        return self.value

    def get_value(self):
        return self.value

@pytest.fixture(scope="function")
async def remote_client():
    """A pytest fixture to set up and tear down the remote client."""
    config = RemoteExecutorConfig(
        host='127.0.0.1',
        port=50052,
        ssl_enabled=False
    )
    client = RemoteExecutionClient(config)
    await client.connect()
    yield client
    await client.disconnect()


@pytest.mark.asyncio
async def test_remote_class_simple_execution(remote_client):
    """
    Tests a single, simple method call on a remotely executed object.
    """
    counter = StatefulCounter(initial_value=5)
    
    serialized_obj = base64.b64encode(cloudpickle.dumps(counter)).decode('ascii')
    
    request_data = {
        "serialized_object": serialized_obj,
        "method_name": "get_value",
    }

    response = await remote_client.execute_node(
        node_type="SerializedClassExecutorNode",
        config={},
        input_data=request_data,
        serialization_format="pickle"
    )

    assert 'error' not in response, f"Received an unexpected error: {response.get('error')}"
    assert response['result'] == 5

@pytest.mark.asyncio
async def test_remote_class_stateful_execution(remote_client):
    """
    Tests that state is preserved between calls by passing the updated
    serialized object back to the remote executor.
    """
    counter = StatefulCounter(initial_value=10)
    
    # --- First call: increment from 10 to 11 ---
    serialized_obj = base64.b64encode(cloudpickle.dumps(counter)).decode('ascii')
    
    request_data_1 = {
        "serialized_object": serialized_obj,
        "method_name": "increment",
    }

    response_1 = await remote_client.execute_node(
        node_type="SerializedClassExecutorNode",
        config={},
        input_data=request_data_1,
        serialization_format="pickle"
    )

    assert 'error' not in response_1
    assert response_1['result'] == 11
    assert 'updated_serialized_object' in response_1

    # --- Second call: increment from 11 to 12 ---
    # Use the updated object from the first response
    updated_serialized_obj = response_1['updated_serialized_object']
    
    request_data_2 = {
        "serialized_object": updated_serialized_obj,
        "method_name": "increment",
    }

    response_2 = await remote_client.execute_node(
        node_type="SerializedClassExecutorNode",
        config={},
        input_data=request_data_2,
        serialization_format="pickle"
    )
    
    assert 'error' not in response_2
    assert response_2['result'] == 12

    # --- Third call: get_value to confirm state ---
    # Use the updated object from the second response
    final_serialized_obj = response_2['updated_serialized_object']

    request_data_3 = {
        "serialized_object": final_serialized_obj,
        "method_name": "get_value",
    }

    response_3 = await remote_client.execute_node(
        node_type="SerializedClassExecutorNode",
        config={},
        input_data=request_data_3,
        serialization_format="pickle"
    )

    assert 'error' not in response_3
    assert response_3['result'] == 12

@pytest.mark.asyncio
async def test_remote_class_error_handling(remote_client):
    """
    Tests that the remote executor correctly handles and reports errors,
    such as calling a method that does not exist.
    """
    counter = StatefulCounter()
    serialized_obj = base64.b64encode(cloudpickle.dumps(counter)).decode('ascii')
    
    request_data = {
        "serialized_object": serialized_obj,
        "method_name": "non_existent_method",
    }

    response = await remote_client.execute_node(
        node_type="SerializedClassExecutorNode",
        config={},
        input_data=request_data,
        serialization_format="pickle"
    )

    assert 'error' in response
    assert response['error_type'] == 'AttributeError'
    assert "Object does not have method 'non_existent_method'" in response['error']

@pytest.mark.asyncio
async def test_remote_class_deserialization_error(remote_client):
    """
    Tests that the server correctly reports an error if it cannot
    deserialize the provided object because the data is corrupted.
    """
    request_data = {
        "serialized_object": "this is not valid base64 or pickle data",
        "method_name": "do_something",
    }

    response = await remote_client.execute_node(
        node_type="SerializedClassExecutorNode",
        config={},
        input_data=request_data,
        serialization_format="pickle"
    )

    assert 'error' in response
    assert response['error_type'] == 'ValueError'
    assert 'Failed to deserialize object' in response['error'] 