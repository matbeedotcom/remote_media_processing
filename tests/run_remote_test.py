#!/usr/bin/env python3
"""
Quick start script for running the remote execution test.

This script helps set up and run the remote execution test by:
1. Checking if the remote service is running
2. Starting the test
3. Providing helpful error messages
"""

import subprocess
import sys
import time
import socket
from pathlib import Path


def check_service_running(host="localhost", port=50051):
    """Check if the remote service is running."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


def wait_for_service(host="localhost", port=50051, timeout=30):
    """Wait for the service to become available."""
    print(f"Waiting for service on {host}:{port}...")
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        if check_service_running(host, port):
            print("✓ Service is ready!")
            return True
        
        print(".", end="", flush=True)
        time.sleep(1)
    
    print(f"\n✗ Service not available after {timeout} seconds")
    return False


def run_test():
    """Run the remote execution test."""
    test_script = Path(__file__).parent / "examples" / "simple_remote_test.py"
    
    if not test_script.exists():
        print(f"✗ Test script not found: {test_script}")
        return 1
    
    print("Running remote execution test...")
    print("=" * 50)
    
    try:
        cmd = [sys.executable, str(test_script)]
        result = subprocess.run(cmd, capture_output=False)
        return result.returncode
    except Exception as e:
        print(f"✗ Failed to run test: {e}")
        return 1


def main():
    """Main entry point."""
    print("RemoteMedia Remote Execution Test Runner")
    print("=" * 50)
    
    # Check if service is running
    if check_service_running():
        print("✓ Remote service is already running")
    else:
        print("✗ Remote service is not running")
        print("\nTo start the service, run:")
        print("  cd remote_service")
        print("  ./scripts/run.sh")
        print("\nOr on Windows:")
        print("  cd remote_service")
        print("  python src/server.py")
        print("\nWaiting for service to start...")
        
        if not wait_for_service():
            print("\n✗ Please start the remote service first")
            return 1
    
    # Run the test
    return run_test()


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\nTest runner interrupted")
        sys.exit(1) 