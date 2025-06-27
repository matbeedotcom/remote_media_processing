# RemoteMedia SDK Tests

This directory contains the comprehensive test suite for the RemoteMedia SDK. The tests cover everything from basic pipeline functionality to complex remote execution scenarios and WebRTC streaming.

📋 **Quick Start**: See [QUICKSTART.md](QUICKSTART.md) for the most common test commands.

## Prerequisites

### 1. Install Test Dependencies

```bash
# From the project root
pip install -r requirements-dev.txt
pip install -r requirements-ml.txt  # For ML node tests

# For WebRTC tests specifically
pip install pytest-playwright-asyncio
playwright install chromium
```

### 2. Remote Service (Optional)

Many tests require the remote execution service to be running:

```bash
# From the project root
cd remote_service
./scripts/run.sh
```

The service will start on `localhost:50051` (gRPC) and `localhost:50052` (HTTP health check).

## Test Categories

### Core Pipeline Tests
- `test_pipeline.py` - Basic pipeline construction and execution
- `test_audio_pipeline.py` - Audio-specific pipeline tests
- `test_media_processing.py` - Video and media file processing

### Node Tests
- `test_audio_nodes.py` - Audio processing nodes (transform, buffer, etc.)
- `test_source_nodes.py` - Data source nodes (file readers, generators)
- `test_sink_nodes.py` - Output nodes (file writers, collectors)
- `test_ml_nodes.py` - Machine learning nodes (Whisper, VLLM, etc.)

### Remote Execution Tests
- `test_connection.py` - Basic gRPC connection tests
- `test_remote_pipeline.py` - Remote pipeline execution
- `test_remote_streaming.py` - Streaming data over gRPC
- `test_remote_object_pipeline.py` - Object serialization and remote execution
- `test_remote_object_streaming.py` - Streaming objects remotely
- `test_remote_code_execution.py` - Custom code execution on remote server
- `test_custom_node_remote_execution.py` - User-defined node remote execution
- `test_cloudpickle_execution.py` - Advanced serialization scenarios
- `test_serialized_node_execution.py` - Node serialization and deserialization

### Packaging Tests
- `test_dependency_packaging.py` - Automatic dependency detection
- `test_custom_library_packaging.py` - Packaging user libraries
- `test_existing_custom_library.py` - Using pre-existing custom code

### WebRTC Tests
- `webrtc/` - Real-time streaming tests (see [WebRTC README](webrtc/README.md))

### Integration Tests
- `test_working_system.py` - End-to-end system tests
- `run_remote_test.py` - Standalone remote execution test

## Running Tests

### Run All Tests

```bash
# From the project root
pytest tests/ -v
```

### Run Specific Test Categories

```bash
# Core functionality only (no remote service needed)
pytest tests/test_pipeline.py tests/test_audio_nodes.py -v

# Remote execution tests (requires remote service)
pytest tests/test_remote_*.py -v

# ML node tests (requires ML dependencies)
pytest tests/test_ml_nodes.py -v

# WebRTC tests (requires special setup)
pytest tests/webrtc/ -v
```

### Run with Coverage

```bash
# Generate coverage report
pytest tests/ --cov=remotemedia --cov-report=html

# View coverage report
open htmlcov/index.html
```

### Run with Specific Markers

```bash
# Skip slow tests
pytest tests/ -v -m "not slow"

# Run only integration tests
pytest tests/ -v -m "integration"
```

## Test Fixtures

Common fixtures are defined in `conftest.py`:

- `temp_audio_file` - Creates a temporary WAV file
- `temp_video_file` - Creates a temporary MP4 file
- `remote_service` - Ensures remote service is available
- Various node fixtures for common test scenarios

## Writing New Tests

### Basic Test Structure

```python
import pytest
from remotemedia.core import Pipeline
from remotemedia.nodes import YourNode

def test_your_feature():
    """Test description."""
    # Arrange
    node = YourNode(param="value")
    
    # Act
    result = node.process(input_data)
    
    # Assert
    assert result.data == expected_value
```

### Testing Remote Execution

```python
@pytest.mark.requires_remote
async def test_remote_feature(remote_service):
    """Test that requires remote service."""
    from remotemedia.remote import RemoteExecutor
    
    executor = RemoteExecutor()
    result = await executor.execute(node, input_data)
    assert result == expected
```

### Testing with Async

```python
@pytest.mark.asyncio
async def test_async_feature():
    """Test async functionality."""
    result = await async_function()
    assert result == expected
```

## Debugging Failed Tests

### Enable Verbose Output

```bash
# Show print statements and logs
pytest tests/test_specific.py -v -s

# Enable debug logging
pytest tests/ -v --log-cli-level=DEBUG
```

### Run Single Test

```bash
# Run specific test function
pytest tests/test_file.py::test_specific_function -v
```

### Use PDB Debugger

```python
def test_with_debugging():
    import pdb; pdb.set_trace()  # Debugger breakpoint
    # Test code here
```

## Common Issues

### "ModuleNotFoundError: No module named 'remotemedia'"

Ensure you've installed the package in development mode:
```bash
pip install -e .
```

### "Remote service not available"

Start the remote service:
```bash
cd remote_service && ./scripts/run.sh
```

### ML Model Tests Failing

Ensure ML dependencies are installed:
```bash
pip install -r requirements-ml.txt
```

### WebRTC Tests Failing

See the dedicated [WebRTC README](webrtc/README.md) for troubleshooting.

### M1/M2 Mac Issues

See the [M1 Mac Troubleshooting Guide](M1_MAC_TROUBLESHOOTING.md) for Apple Silicon specific issues.

## CI/CD Integration

The test suite is designed to work in CI environments:

1. **Parallel Execution**: Most tests can run in parallel
2. **Service Detection**: Tests skip if remote service unavailable
3. **Resource Cleanup**: All tests clean up temporary files
4. **Timeout Protection**: Long-running tests have timeouts

### GitHub Actions Example

```yaml
- name: Run Tests
  run: |
    pytest tests/ -v --timeout=300 --cov=remotemedia
```

## Performance Testing

For performance-sensitive tests:

```python
@pytest.mark.slow
def test_performance():
    """Mark slow tests to skip in quick runs."""
    # Performance test here
```

Run without slow tests:
```bash
pytest tests/ -v -m "not slow"
```

## Test Data

Test data files are located in:
- `examples/` - Sample media files (BigBuckBunny.mp4, transcribe_demo.wav)
- Tests create temporary files as needed using fixtures

## Contributing

When adding new tests:
1. Follow existing naming conventions (`test_*.py`)
2. Add docstrings explaining what's being tested
3. Use appropriate markers (@pytest.mark.slow, @pytest.mark.requires_remote)
4. Clean up resources (files, connections) after tests
5. Add to this README if introducing new test categories 