# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RemoteMedia Processing SDK is a Python SDK for building distributed audio/video/data processing pipelines with transparent remote offloading capabilities. The project enables developers to create complex, real-time processing applications that can seamlessly offload computationally intensive tasks to remote execution services.

## Key Architecture Components

### Core Pipeline System
- **Pipeline** (`remotemedia/core/pipeline.py`): Manages sequences of processing nodes with async parallel execution using unbounded queues and threaded workers
- **Node** (`remotemedia/core/node.py`): Base class for all processing steps with optional `RemoteExecutorConfig` for remote execution
- **RemoteExecutorConfig**: Specifies connection details (host, port, auth, protocol) for remote execution services

### Remote Execution
- **RemoteExecutionClient** (`remotemedia/remote/client.py`): gRPC client for remote node execution
- **Code Packaging** (`remotemedia/packaging/`): AST-based dependency analysis and CloudPickle serialization for user-defined code
- **Remote Service** (`remote_service/`): Docker-based gRPC server for sandboxed code execution

### Node Types
- **Built-in Nodes** (`remotemedia/nodes/`): Audio, video, transform, calculator, text processing
- **Audio Nodes**: `AudioTransform`, `AudioBuffer`, `VoiceActivityDetector` (VAD)
- **Custom Execution**: `CodeExecutorNode` for remote Python code, `SerializedClassExecutorNode` for CloudPickle objects
- **Streaming Support**: Nodes can be streaming (async generators) or regular (single item processing)

## Development Commands

### Testing
```bash
# Run all tests with coverage
pytest

# Run specific test file
pytest tests/test_pipeline.py

# Run tests matching pattern
pytest -k "test_remote"

# Run with verbose output
pytest -v
```

### Code Quality
```bash
# Format code with black
black remotemedia/ tests/

# Lint with flake8
flake8 remotemedia/ tests/

# Type check with mypy
mypy remotemedia/
```

### Building
```bash
# Build package
python -m build

# Install in development mode
pip install -e .

# Install with dev dependencies
pip install -e ".[dev]"

# Install with ML dependencies
pip install -e ".[ml]"
```

### Remote Service
```bash
# Build Docker image
cd remote_service && ./scripts/build.sh

# Run tests
cd remote_service && ./scripts/test.sh

# Start service
cd remote_service && docker-compose up
```

## Testing Strategy

The project has comprehensive test coverage including:
- Unit tests for individual components
- Integration tests for pipeline execution
- Remote execution tests with actual gRPC connections
- CloudPickle serialization tests
- Dependency packaging tests with custom libraries

Key test files:
- `test_working_system.py`: Full system integration tests
- `test_remote_code_execution.py`: Remote Python code execution
- `test_cloudpickle_execution.py`: Object serialization tests
- `test_dependency_packaging.py`: AST analysis and packaging

## Important Implementation Details

### Pipeline Execution
- Uses async/await patterns throughout
- Parallel node execution with worker threads
- Sentinel-based stream termination
- Support for node flushing on stream end

### Remote Code Execution Security
- Sandboxed execution environment in Docker
- Restricted globals in remote execution
- Process-level isolation with resource limits
- Future plans for microVM isolation (Firecracker/gVisor)

### Data Serialization
- JSON for simple types
- CloudPickle for complex Python objects
- Custom serializers for NumPy arrays and media frames
- gRPC with Protocol Buffers for remote communication

### Error Handling
- Custom exceptions in `remotemedia/core/exceptions.py`
- Comprehensive logging throughout the codebase
- Error propagation from remote execution back to client

## Current Development Phase

Phase 3 (Advanced Offloading for User-Defined Python Code) is COMPLETE:
- ✅ Remote Python code execution with CloudPickle
- ✅ AST-based dependency analysis for local imports
- ✅ Code and dependency packaging system
- ✅ Secure sandboxed execution environment
- ✅ Full test coverage (7/7 scenarios passing)

## Common Development Tasks

### Adding a New Node Type
1. Create new class inheriting from `Node` in `remotemedia/nodes/`
2. Implement `process()` method (can be sync or async)
3. Optional: Add `flush()` method for stateful nodes
4. Optional: Set `is_streaming = True` for streaming nodes
5. Add tests in `tests/`

### Making a Node Remotable
1. Ensure node is serializable (no file handles, sockets, etc.)
2. Add to remote service's node registry if SDK-defined
3. For user nodes, use `SerializedClassExecutorNode` with CloudPickle

### Debugging Remote Execution
1. Check remote service logs: `docker-compose logs -f`
2. Enable debug logging: Set log level in `remotemedia/utils/logging.py`
3. Use `RemoteExecutionClient` directly for testing
4. Inspect serialized payloads and gRPC messages