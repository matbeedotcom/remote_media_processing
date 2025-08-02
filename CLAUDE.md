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
- **RemoteProxyClient** (`remotemedia/remote/proxy_client.py`): Transparent proxy that makes ANY Python object remotely executable
- **Code Packaging** (`remotemedia/packaging/`): AST-based dependency analysis and CloudPickle serialization for user-defined code
- **Remote Service** (`remote_service/`): Docker-based gRPC server for sandboxed code execution

### Node Types
- **Built-in Nodes** (`remotemedia/nodes/`): Audio, video, transform, calculator, text processing
- **Audio Nodes**: `AudioTransform`, `AudioBuffer`, `VoiceActivityDetector` (VAD)
- **ML Nodes**: `UltravoxNode` (speech-to-text), `KokoroTTSNode` (text-to-speech)
- **WebRTC Integration**: Real-time audio/video streaming with aiortc
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

### WebRTC Server
```bash
# Run WebRTC server with ML pipeline
USE_ML=true python examples/webrtc_pipeline_server.py

# Run basic WebRTC server (no ML)
python examples/webrtc_pipeline_server.py

# Connect with web client
open http://localhost:8080/webrtc_client.html
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

Phase 4 (WebRTC Real-time Audio Processing) is COMPLETE:
- ✅ WebRTC server with aiortc integration
- ✅ Real-time audio streaming with proper frame timing
- ✅ Voice Activity Detection (VAD) with speech segmentation
- ✅ Speech-to-speech pipeline (Ultravox + Kokoro TTS)
- ✅ VAD-triggered buffering with pre-speech context
- ✅ WebRTC audio output with 20ms frame synchronization

Phase 3 (Advanced Offloading for User-Defined Python Code) is COMPLETE:
- ✅ Remote Python code execution with CloudPickle
- ✅ AST-based dependency analysis for local imports
- ✅ Code and dependency packaging system
- ✅ Secure sandboxed execution environment
- ✅ Full test coverage (7/7 scenarios passing)

## Common Development Tasks

### Using RemoteProxyClient for Transparent Remote Execution
The RemoteProxyClient provides the simplest way to make any Python object execute remotely:

```python
from remotemedia.remote import RemoteProxyClient
from remotemedia.core.node import RemoteExecutorConfig

config = RemoteExecutorConfig(host="localhost", port=50052)
async with RemoteProxyClient(config) as client:
    # Make ANY object remote with one line
    obj = MyComplexObject()
    remote_obj = await client.create_proxy(obj)
    
    # Use exactly like the local object (just add await)
    result = await remote_obj.process_data(input_data)
```

Key points:
- Works with ANY serializable Python object
- No special base class or interface required
- Maintains object state on remote server between calls
- Session management is automatic
- All method calls are transparently forwarded to remote execution

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

### WebRTC Audio Pipeline Architecture

The WebRTC integration implements a complete speech-to-speech system:

1. **Audio Input**: WebRTC client captures microphone audio
2. **Audio Processing**: `AudioTransform` resamples to 16kHz for ML models
3. **Voice Activity Detection**: `VoiceActivityDetector` identifies speech vs silence
4. **Speech Buffering**: `VADTriggeredBuffer` accumulates complete utterances:
   - Maintains 1s rolling pre-speech buffer
   - Waits for ≥1s of speech + 500ms silence before triggering
   - Includes pre-speech context in output
5. **Speech Recognition**: `UltravoxImmediateProcessor` processes complete utterances:
   - Bypasses internal buffering to prevent accumulation
   - Clears buffer after each inference
   - Processes each speech segment individually
6. **Text-to-Speech**: `KokoroTTSNode` synthesizes response audio
7. **Audio Output**: `AudioOutputTrack` streams back to WebRTC client:
   - Splits audio into 20ms frames
   - Implements proper frame timing (50 FPS)
   - Uses real-time rate limiting to prevent flooding

### Key WebRTC Components

- **WebRTCServer** (`remotemedia/webrtc/server.py`): Main server with signaling
- **WebRTCPipelineProcessor** (`remotemedia/webrtc/pipeline_processor.py`): Integrates WebRTC with pipeline
- **AudioOutputTrack**: Custom aiortc track with frame timing and PTS management
- **VADTriggeredBuffer**: Smart buffering for complete speech segments