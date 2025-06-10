import pytest
import asyncio
import subprocess
import time
import os

@pytest.fixture(scope="module")
def grpc_server():
    """Starts the gRPC server as a background process for the test module."""
    env = os.environ.copy()
    env["PYTHONPATH"] = "."
    
    server_process = subprocess.Popen(
        ["python", "remote_service/src/server.py"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    # Give the server a moment to start up and check if it's running.
    time.sleep(2) 

    # Check if the process started correctly
    if server_process.poll() is not None:
        stdout, stderr = server_process.communicate()
        pytest.fail(f"Server failed to start. Return code: {server_process.returncode}\nstdout: {stdout}\nstderr: {stderr}")
        
    yield server_process
    
    server_process.terminate()
    try:
        server_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server_process.kill()
        server_process.wait() 