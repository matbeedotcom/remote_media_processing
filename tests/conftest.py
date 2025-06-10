import pytest
import subprocess
import time
import os

@pytest.fixture(scope="session")
def grpc_server():
    """Starts the gRPC server in a separate process with the correct PYTHONPATH."""
    env = os.environ.copy()
    project_root = os.getcwd()
    
    if 'PYTHONPATH' in env:
        env['PYTHONPATH'] = f"{project_root}:{env['PYTHONPATH']}"
    else:
        env['PYTHONPATH'] = project_root
        
    server_process = subprocess.Popen(
        ['python', 'remote_service/src/server.py', '--port', '50052'],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Give the server a moment to start. A simple delay is more robust
    # than a complex health check that might have its own issues.
    time.sleep(2)
    
    # Check if the server started successfully
    if server_process.poll() is not None:
        # Communicate can hang if the process is still running, so we read directly
        stdout, stderr = server_process.communicate(timeout=1)
        pytest.fail(
            f"Server failed to start. Return code: {server_process.returncode}\n"
            f"--- STDOUT ---\n{stdout.decode() if stdout else ''}\n"
            f"--- STDERR ---\n{stderr.decode() if stderr else ''}"
        )

    yield server_process
    
    # Teardown: stop the server
    server_process.terminate()
    try:
        server_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        server_process.kill()
        server_process.wait() 