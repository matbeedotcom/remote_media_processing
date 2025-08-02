# RemoteMedia SDK Examples

This directory contains example applications and tests for the RemoteMedia SDK.

## Simple Remote Execution Test

The `simple_remote_test.py` script demonstrates how to test the remote execution service with simple Python classes.

### Prerequisites

1. **Start the Remote Service**: The remote execution service must be running before running the test.

```bash
# From the project root
cd remote_service
./scripts/run.sh
```

2. **Install Dependencies**: Make sure you have the required dependencies installed.

```bash
# From the project root
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### Running the Test

```bash
# From the project root
python examples/simple_remote_test.py
```

Or with help:

```bash
python examples/simple_remote_test.py --help
```

### What the Test Does

The test performs the following operations:

1. **Connection Test**: Verifies that it can connect to the remote execution service
2. **Service Status**: Gets the service status and lists available nodes
3. **Node Execution**: Tests executing a simple `PassThroughNode` remotely
4. **Calculator Simulation**: Simulates running a custom Python class remotely

### Expected Output

When successful, you should see output like:

```
RemoteMedia Simple Remote Execution Test
==================================================
=== Testing Connection ===
✓ Connected to remote service
✓ Service status: 1
✓ Available nodes: 6

=== Testing Node Execution ===
Sending: {'message': 'Hello remote!', 'timestamp': 1703123456.789, 'data': [1, 2, 3, 4, 5]}
Received: {'message': 'Hello remote!', 'timestamp': 1703123456.789, 'data': [1, 2, 3, 4, 5]}
✓ PassThroughNode test passed

=== Testing Calculator Simulation ===
Local: 10 + 5 = 15
Local result: 15
Simulating remote execution...
Simulation result: {'class_name': 'SimpleCalculator', 'operation': 'add', 'args': [10, 5], 'expected': 15}
✓ Calculator simulation completed
  (Phase 3 will enable actual remote execution)

==================================================
TEST SUMMARY
==================================================
✓ Connection: PASS
✓ Node Execution: PASS
✓ Calculator Simulation: PASS

Results: 3/3 tests passed
🎉 All tests passed!
```

### Troubleshooting

**Connection Failed**: Make sure the remote service is running on `localhost:50051`. Start it with:
```bash
cd remote_service && ./scripts/run.sh
```

**Import Errors**: Make sure you're running from the project root and have installed dependencies:
```bash
pip install -r requirements.txt
```

**gRPC Errors**: The remote service may need time to start. Wait a few seconds and try again.

### Current Limitations

- **Phase 2 Implementation**: Currently, only SDK-defined nodes can be executed remotely
- **Phase 3 Coming**: Actual user-defined Python class execution will be implemented in Phase 3
- **Simulation Mode**: The calculator test currently simulates remote execution using PassThroughNode

### Next Steps

This test provides a foundation for:
1. Validating the gRPC communication system
2. Testing serialization and data flow
3. Preparing for Phase 3 custom code execution
4. Debugging remote execution issues

## Remote Proxy Client Examples

The RemoteProxyClient provides transparent remote execution for ANY Python object. Here are the example scripts:

### simplest_proxy.py
The simplest demonstration of RemoteProxyClient - shows how ANY object can be made remote with just one line:

```bash
python examples/simplest_proxy.py
```

Features demonstrated:
- One-line remote object creation: `remote_obj = await client.create_proxy(obj)`
- Works with calculators, todo lists, string processors
- State persistence across method calls

### simple_remote_proxy.py
More comprehensive examples showing RemoteProxyClient with various object types:

```bash
python examples/simple_remote_proxy.py
```

Features demonstrated:
- Simple counters and string processors
- Math operations with numpy arrays
- Stateful objects (todo lists)
- Built-in Python objects

### remote_proxy_example.py
Advanced examples including decorator patterns and dynamic clients:

```bash
python examples/remote_proxy_example.py
```

Features demonstrated:
- Manual proxy creation
- Chained method calls
- Alternative syntax approaches

### minimal_proxy.py / ultra_simple_proxy.py
Minimal examples focused on clarity:

```bash
python examples/minimal_proxy.py
python examples/ultra_simple_proxy.py
```

### Key Concepts

1. **Zero Setup**: No special base classes or interfaces required
2. **Transparent Usage**: Methods are called exactly like local objects (just add `await`)
3. **State Persistence**: Objects maintain their state on the remote server
4. **Session Management**: Automatic session handling with unique IDs

### Example Usage

```python
from remotemedia.remote import RemoteProxyClient
from remotemedia.core.node import RemoteExecutorConfig

config = RemoteExecutorConfig(host="localhost", port=50052)

async with RemoteProxyClient(config) as client:
    # ANY object becomes remote with one line!
    calculator = Calculator()
    remote_calc = await client.create_proxy(calculator)
    
    # Use it normally (with await)
    result = await remote_calc.add(5, 3)
    print(f"Result: {result}")  # Executed remotely!
```

For more complex examples and integration tests, see the `tests/` directory. 