# RemoteMedia Processing SDK

A Python SDK for building distributed audio/video/data processing pipelines with transparent remote offloading capabilities.

## Overview

The RemoteMedia Processing SDK enables developers to create complex, real-time processing applications that can seamlessly offload computationally intensive tasks to remote execution services. The SDK handles WebRTC communication, data synchronization, and remote execution while providing a transparent and intuitive developer experience.

## Key Features

- **Pythonic Pipeline API**: High-level, intuitive API for defining processing pipelines
- **Transparent Remote Offloading**: Execute processing nodes remotely with minimal code changes
- **Real-time A/V Processing**: Optimized for low-latency audio/video processing
- **WebRTC Integration**: Built-in WebRTC support for real-time communication
- **Flexible Architecture**: Support for both SDK-provided and custom processing nodes
- **Secure Remote Execution**: Sandboxed execution environment for user-defined code
- **CloudPickle Integration**: Serialize and execute user-defined Python classes remotely
- **AST-Based Dependency Analysis**: Automatic detection and packaging of local Python dependencies

## Development Status

**Current Phase**: Phase 4 - WebRTC Real-time Audio Processing (COMPLETE) ✅

**Phase 4 Achievements:**
- ✅ **WebRTC Server Integration**: Real-time audio/video streaming with aiortc
- ✅ **Voice Activity Detection (VAD)**: Speech segmentation with buffering
- ✅ **Speech-to-Speech Pipeline**: Ultravox STT + Kokoro TTS integration
- ✅ **Remote Proxy Client**: Transparent remote execution for ANY Python object

**Phase 3 Achievements:**
- ✅ **Remote Python Code Execution**: Full support for executing user-defined Python code remotely
- ✅ **CloudPickle Class Serialization**: Serialize and execute custom Python classes with state preservation
- ✅ **AST-Based Dependency Analysis**: Automatic detection of local Python file dependencies
- ✅ **Code & Dependency Packaging**: Complete packaging system for deployable archives
- ✅ **Secure Execution Environment**: Sandboxed remote execution with restricted globals
- ✅ **Comprehensive Testing**: 7/7 test scenarios passing (4 CloudPickle + 3 dependency packaging)

**What Works Now:**
- **NEW**: RemoteProxyClient - Make ANY Python object remote with one line of code
- WebRTC real-time audio processing with proper frame timing
- Voice-triggered speech-to-speech conversation system
- Users can define Python classes locally with custom dependencies
- AST analysis automatically detects and packages local Python file imports
- CloudPickle enables serialization of complex user-defined objects
- Remote execution preserves object state and functionality across network boundaries
- End-to-end remote code execution with proper error handling and logging

See `PHASE_3_PROJECT_TRACKING.md` for detailed status and `DevelopmentStrategyDocument.md` for complete roadmap.

## Quick Start

### Local Processing Pipeline
```python
from remotemedia.core import Pipeline
from remotemedia.nodes import MediaReaderNode, AudioResampleNode, MediaWriterNode

# Create a simple local processing pipeline
pipeline = Pipeline(
    MediaReaderNode(file_path="input.mp3"),
    AudioResampleNode(target_sample_rate=16000),
    MediaWriterNode(output_path="output.wav")
)
pipeline.run()
```

### Remote Code Execution
The SDK makes it simple to define a node locally and have it execute on a remote server. This is ideal for offloading heavy ML workloads.

```python
# client_script.py
from remotemedia.core import Pipeline
from remotemedia.nodes import MediaReaderNode, MediaWriterNode, RemoteObjectExecutionNode
from my_custom_nodes import AudioEchoEffect # A custom node defined in your project

# 1. Instantiate your custom node locally.
#    This object will be serialized and sent to the server for execution.
echo_effect = AudioEchoEffect(delay_seconds=0.5, decay_factor=0.6)

# 2. Wrap it in a RemoteObjectExecutionNode
remote_echo_node = RemoteObjectExecutionNode(node_object=echo_effect)

# 3. Build the pipeline. The remote node fits in just like any other.
pipeline = Pipeline(
    MediaReaderNode(file_path="input.wav"),
    remote_echo_node,
    MediaWriterNode(output_path="output_with_echo.wav")
)

# When run, the pipeline will transparently execute the echo effect on the remote server.
pipeline.run()
```

### Remote Proxy Client
The RemoteProxyClient provides the simplest way to execute ANY Python object remotely:

```python
from remotemedia.remote import RemoteProxyClient
from remotemedia.core.node import RemoteExecutorConfig

# Configure connection
config = RemoteExecutorConfig(host="localhost", port=50052)

async with RemoteProxyClient(config) as client:
    # Make ANY object remote with just ONE line!
    calculator = Calculator()
    remote_calc = await client.create_proxy(calculator)
    
    # Use it exactly like a local object (just add await)
    result = await remote_calc.add(5, 3)
    print(f"5 + 3 = {result}")  # Executed on remote server!
    
    # The remote object maintains state
    await remote_calc.multiply(10, 4)
    history = await remote_calc.history()  # State persists remotely
```

**Key Features:**
- **One-line remote conversion**: `remote_obj = await client.create_proxy(obj)`
- **Works with ANY Python object**: No special base class required
- **Transparent usage**: Call methods exactly as you would locally
- **State persistence**: Objects maintain state on the remote server
- **Session management**: Automatic session handling with unique IDs

See `examples/simplest_proxy.py` for more examples.

## Installation

```bash
# Development installation
pip install -e .

# Or install from PyPI (when available)
pip install remotemedia
```

## Project Structure

```
remotemedia/                 # Core SDK package
├── core/                   # Core pipeline and node classes
│   ├── pipeline.py         # Pipeline management
│   ├── node.py             # Base Node and RemoteExecutorConfig
│   └── exceptions.py       # Custom exceptions
├── nodes/                  # Built-in processing nodes
│   ├── base.py             # Basic utility nodes (PassThrough, Buffer)
│   ├── audio.py            # Audio processing nodes
│   ├── video.py            # Video processing nodes
│   ├── transform.py        # Data transformation nodes
│   ├── calculator.py       # Calculator node for testing
│   ├── text_processor.py   # Text processing node
│   ├── code_executor.py    # Remote Python code execution
│   └── serialized_class_executor.py  # CloudPickle class execution
├── packaging/              # Code & dependency packaging (Phase 3)
│   ├── dependency_analyzer.py  # AST-based import analysis
│   └── code_packager.py    # Archive creation with dependencies
├── webrtc/                 # WebRTC communication
│   └── manager.py          # WebRTC connection manager
├── remote/                 # Remote execution client
│   ├── client.py           # gRPC remote execution client
│   └── proxy_client.py     # Transparent proxy for ANY Python object
├── serialization/          # Data serialization utilities
│   └── base.py             # JSON and Pickle serializers
├── utils/                  # Common utilities
│   └── logging.py          # Logging configuration
└── cli.py                  # Command-line interface

examples/                   # Example applications
├── basic_pipeline.py       # Basic local pipeline usage
├── simple_remote_test.py   # Remote execution examples
└── README.md               # Examples documentation

tests/                      # Comprehensive test suite
├── test_pipeline.py        # Pipeline class tests
├── test_connection.py      # Basic connection tests
├── test_working_system.py  # System integration tests
├── test_remote_code_execution.py     # Remote Python execution
├── test_cloudpickle_execution.py     # CloudPickle class execution
├── test_dependency_packaging.py      # AST analysis & packaging
├── test_custom_node_remote_execution.py  # Custom node execution
├── test_custom_library_packaging.py  # Custom library tests
├── test_existing_custom_library.py   # Real file dependency tests
├── import_detection_tests/ # Test files for dependency analysis
└── run_remote_test.py      # Test runner utilities

remote_service/             # Remote execution service (Docker)
├── src/                    # gRPC server implementation
├── Dockerfile              # Container configuration
├── requirements.txt        # Service dependencies
└── README.md               # Service documentation

docs/                       # Documentation
scripts/                    # Development scripts
```

## Documentation

- [**Developer Guide**](DEVELOPER_GUIDE.md) - **Start here!** Essential guide for building with the SDK.
- [Development Strategy](DevelopmentStrategyDocument.md)
- [Project Tracking](PROJECT_TRACKING.md)
- [API Documentation](docs/) (Coming soon)

## Contributing

This project is in early development. Please see `PROJECT_TRACKING.md` for current development status and priorities.

## License

[License to be determined]

## Requirements

- Python 3.9+
- See `requirements.txt` for dependencies 