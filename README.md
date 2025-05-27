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

**Current Phase**: Phase 3 - Advanced Offloading for User-Defined Python Code (COMPLETE) ✅

**Phase 3 Achievements:**
- ✅ **Remote Python Code Execution**: Full support for executing user-defined Python code remotely
- ✅ **CloudPickle Class Serialization**: Serialize and execute custom Python classes with state preservation
- ✅ **AST-Based Dependency Analysis**: Automatic detection of local Python file dependencies
- ✅ **Code & Dependency Packaging**: Complete packaging system for deployable archives
- ✅ **Secure Execution Environment**: Sandboxed remote execution with restricted globals
- ✅ **Comprehensive Testing**: 7/7 test scenarios passing (4 CloudPickle + 3 dependency packaging)

**What Works Now:**
- Users can define Python classes locally with custom dependencies
- AST analysis automatically detects and packages local Python file imports
- CloudPickle enables serialization of complex user-defined objects
- Remote execution preserves object state and functionality across network boundaries
- End-to-end remote code execution with proper error handling and logging

See `PHASE_3_PROJECT_TRACKING.md` for detailed status and `DevelopmentStrategyDocument.md` for complete roadmap.

## Quick Start

### Local Processing Pipeline
```python
from remotemedia import Pipeline
from remotemedia.nodes import AudioTransform, VideoTransform

# Create a simple local processing pipeline
pipeline = Pipeline()
pipeline.add_node(AudioTransform(sample_rate=44100))
pipeline.add_node(VideoTransform(resolution=(1920, 1080)))

# Process data
result = pipeline.process(input_data)
```

### Remote Code Execution (Phase 3)
```python
from remotemedia.remote.client import RemoteExecutionClient
from remotemedia.core.node import RemoteExecutorConfig

# Define a custom class
class DataProcessor:
    def __init__(self):
        self.processed_count = 0
    
    def process(self, data):
        self.processed_count += 1
        return {"result": data * 2, "count": self.processed_count}

# Execute remotely with CloudPickle
config = RemoteExecutorConfig(host='localhost', port=50051)
async with RemoteExecutionClient(config) as client:
    result = await client.execute_node(
        node_type="SerializedClassExecutorNode",
        config={},
        input_data={
            "serialized_object": cloudpickle.dumps(DataProcessor()),
            "method_name": "process",
            "method_args": [42]
        }
    )
```

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
├── nodes/                  # Built-in processing nodes
├── webrtc/                 # WebRTC communication
├── remote/                 # Remote execution client
├── serialization/          # Data serialization utilities
└── utils/                  # Common utilities

examples/                   # Example applications
tests/                      # Test suite
remote_service/             # Remote execution service (Docker)
docs/                       # Documentation
scripts/                    # Development scripts
```

## Documentation

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