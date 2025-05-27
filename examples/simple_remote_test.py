#!/usr/bin/env python3
"""Simple test for remote execution service."""

import asyncio
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from remotemedia.core.node import RemoteExecutorConfig  # noqa: E402
from remotemedia.remote.client import RemoteExecutionClient  # noqa: E402


class SimpleCalculator:
    """Simple calculator for testing remote execution."""

    def __init__(self, name="Calculator"):
        self.name = name
        self.count = 0

    def add(self, a, b):
        """Add two numbers."""
        self.count += 1
        result = a + b
        print(f"{self.name}: {a} + {b} = {result}")
        return result

    def multiply(self, a, b):
        """Multiply two numbers."""
        self.count += 1
        result = a * b
        print(f"{self.name}: {a} * {b} = {result}")
        return result


async def test_connection():
    """Test connection to remote service."""
    print("=== Testing Connection ===")

    config = RemoteExecutorConfig(
        host="localhost",
        port=50051,
        protocol="grpc",
        timeout=30.0,
        ssl_enabled=False
    )

    try:
        async with RemoteExecutionClient(config) as client:
            print("✓ Connected to remote service")

            status = await client.get_status()
            print(f"✓ Service status: {status.get('status', 'unknown')}")

            nodes = await client.list_available_nodes()
            print(f"✓ Available nodes: {len(nodes)}")

            return True

    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False


async def test_node_execution():
    """Test executing a simple node."""
    print("\n=== Testing Node Execution ===")

    config = RemoteExecutorConfig(
        host="localhost",
        port=50051,
        protocol="grpc",
        timeout=30.0,
        ssl_enabled=False
    )

    try:
        async with RemoteExecutionClient(config) as client:
            test_data = {
                "message": "Hello remote!",
                "timestamp": time.time(),
                "data": [1, 2, 3, 4, 5]
            }

            print(f"Sending: {test_data}")

            result = await client.execute_node(
                node_type="PassThroughNode",
                config={},
                input_data=test_data,
                serialization_format="pickle"
            )

            print(f"Received: {result}")

            if result == test_data:
                print("✓ PassThroughNode test passed")
                return True
            else:
                print("✗ Data mismatch")
                return False

    except Exception as e:
        print(f"✗ Node execution failed: {e}")
        return False


async def test_calculator_simulation():
    """Simulate remote calculator execution."""
    print("\n=== Testing Calculator Simulation ===")

    # Local calculation for comparison
    calc = SimpleCalculator("Local")
    local_result = calc.add(10, 5)
    print(f"Local result: {local_result}")

    # Simulate remote execution
    config = RemoteExecutorConfig(
        host="localhost",
        port=50051,
        protocol="grpc",
        timeout=30.0,
        ssl_enabled=False
    )

    try:
        async with RemoteExecutionClient(config) as client:
            simulation_data = {
                "class_name": "SimpleCalculator",
                "operation": "add",
                "args": [10, 5],
                "expected": local_result
            }

            print("Simulating remote execution...")

            result = await client.execute_node(
                node_type="PassThroughNode",
                config={"simulation": "calculator"},
                input_data=simulation_data,
                serialization_format="pickle"
            )

            print(f"Simulation result: {result}")
            print("✓ Calculator simulation completed")
            print("  (Phase 3 will enable actual remote execution)")

            return True

    except Exception as e:
        print(f"✗ Calculator simulation failed: {e}")
        return False


async def run_tests():
    """Run all tests."""
    print("RemoteMedia Simple Remote Execution Test")
    print("=" * 50)

    tests = [
        ("Connection", test_connection),
        ("Node Execution", test_node_execution),
        ("Calculator Simulation", test_calculator_simulation),
    ]

    results = []

    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            print(f"✗ {name} failed: {e}")
            results.append((name, False))

    # Summary
    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "PASS" if result else "FAIL"
        icon = "✓" if result else "✗"
        print(f"{icon} {name}: {status}")

    print(f"\nResults: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed!")
        return 0
    else:
        print("❌ Some tests failed")
        return 1


def main():
    """Main entry point."""
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print("Simple Remote Execution Test")
        print("Usage: python simple_remote_test.py [--help]")
        print("\nTests the remote execution service.")
        print("Make sure service is running on localhost:50051")
        return 0

    print("Starting tests...")
    print("Make sure remote service is running on localhost:50051")
    print("Start with: cd remote_service && ./scripts/run.sh")
    print()

    try:
        exit_code = asyncio.run(run_tests())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nTest interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
