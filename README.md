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

## Development Status

**Current Phase**: Phase 1 - Core SDK Framework & Local Processing

This project is under active development. See `DevelopmentStrategyDocument.md` for detailed roadmap and `PROJECT_TRACKING.md` for current progress.

## Quick Start

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