import pytest
import asyncio
import cloudpickle

from remotemedia.core.node import RemoteExecutorConfig
from remotemedia.remote.client import RemoteExecutionClient
from remotemedia.core.exceptions import RemoteExecutionError

# A simple stateful class for testing, defined directly in the test module
# to ensure that the CodePackager is correctly handling its dependency.
class StatefulCounter:
    def __init__(self, initial_value=0):
        self.value = initial_value

    def increment(self):
        self.value += 1
        return self.value

    def get_value(self):
        return self.value

@pytest.fixture(scope="function")
async def remote_client(grpc_server):
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
    This uses the session-based ExecuteObjectMethod RPC.
    """
    counter = StatefulCounter(initial_value=5)
    
    response = await remote_client.execute_object_method(
        obj=counter,
        method_name="get_value",
        method_args=[]
    )

    assert 'result' in response
    assert response['result'] == 5
    assert 'session_id' in response

@pytest.mark.asyncio
async def test_remote_class_stateful_execution(remote_client):
    """
    Tests that state is preserved between calls by using the new
    session-based ExecuteObjectMethod RPC.
    """
    counter = StatefulCounter(initial_value=10)
    
    # --- First call: initialize session and increment from 10 to 11 ---
    response_1 = await remote_client.execute_object_method(
        obj=counter,
        method_name="increment",
        method_args=[]
    )

    assert response_1['result'] == 11
    session_id = response_1['session_id']
    assert session_id is not None
    
    # --- Second call: increment from 11 to 12 using the session_id ---
    response_2 = await remote_client.execute_object_method(
        obj=None,  # No object needed when session_id is provided
        session_id=session_id,
        method_name="increment",
        method_args=[]
    )
    
    assert response_2['result'] == 12

    # --- Third call: get_value to confirm state ---
    response_3 = await remote_client.execute_object_method(
        obj=None,
        session_id=session_id,
        method_name="get_value",
        method_args=[]
    )

    assert response_3['result'] == 12

@pytest.mark.asyncio
async def test_remote_class_error_handling(remote_client):
    """
    Tests that the remote executor correctly handles calling a method
    that does not exist in a session.
    """
    counter = StatefulCounter()
    
    # First, create the session
    response_init = await remote_client.execute_object_method(
        obj=counter,
        method_name="get_value",
        method_args=[]
    )
    session_id = response_init['session_id']

    # Now, try to call a non-existent method
    with pytest.raises(RemoteExecutionError) as excinfo:
        await remote_client.execute_object_method(
            obj=None,
            session_id=session_id,
            method_name="non_existent_method",
            method_args=[]
        )
    
    assert "'StatefulCounter' object has no attribute 'non_existent_method'" in str(excinfo.value)

@pytest.mark.asyncio
async def test_remote_class_bad_session_id(remote_client):
    """
    Tests that the server correctly reports an error if a bad
    session ID is provided.
    """
    with pytest.raises(RemoteExecutionError) as excinfo:
        await remote_client.execute_object_method(
            obj=None,
            session_id="this-is-not-a-valid-session-id",
            method_name="any_method",
            method_args=[]
        )
    
    assert "Session not found" in str(excinfo.value)

@pytest.mark.asyncio
async def test_remote_class_deserialization_error(remote_client):
    """
    Tests that the server correctly reports an error if it cannot
    deserialize the provided object because the data is corrupted.
    This test is now more complex because the packaging is robust. We'll
    simulate a failure by sending a valid object that *tries* to import
    a non-existent module.
    """
    class BadImportClass:
        def __init__(self):
            pass
        async def initialize(self):
            import a_module_that_will_never_exist
        def process(self, data):
            return "should not get here"
        async def cleanup(self):
            pass

    bad_obj = BadImportClass()

    with pytest.raises(Exception) as excinfo:
        await remote_client.execute_object_method(
            obj=bad_obj,
            method_name="process",
            method_args=["test"]
        )
    
    assert "No module named 'a_module_that_will_never_exist'" in str(excinfo.value) 