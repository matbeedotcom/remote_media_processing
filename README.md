# RemoteMedia Processing SDK

A Python SDK for building distributed, real-time audio/video/data processing pipelines with transparent remote offloading and high-performance, multimodal AI capabilities.

## Overview

The RemoteMedia Processing SDK enables developers to create complex processing applications that can seamlessly offload computationally intensive tasks—especially large language model (LLM) inference—to remote execution services. The SDK handles data synchronization, dependency packaging, and remote execution, allowing you to focus on building powerful, modular pipelines.

## Key Features

- **Pythonic Pipeline API**: High-level, intuitive API for defining processing pipelines.
- **Transparent Remote Offloading**: Execute processing nodes on a remote server with minimal code changes.
- **High-Performance LLM Inference**: Integrated `VLLMNode` for fast, streaming, and multimodal generation.
- **Flexible ML Integration**: Works with both `vLLM` and standard Hugging Face `transformers`.
- **Automatic Dependency Packaging**: User-defined nodes and their local dependencies are automatically packaged and sent to the server for execution.
- **Composable Utility Nodes**: A rich set of helper nodes for common tasks like audio/video processing, batching, and data transformation.
- **Secure Remote Execution**: Sandboxed execution environment for user-defined code.

## Quick Start

The SDK makes it simple to define a sophisticated, multimodal pipeline locally and have it execute on a remote server. This is ideal for offloading heavy ML workloads.

```python
# client_script.py
from remotemedia.core import Pipeline, RemoteExecutorConfig
from remotemedia.nodes import (
    MediaReaderNode, VideoTrackSource, DecodeVideoFrame, TakeFirstFrameNode,
    TransformNode, VLLMNode
)

# 1. Configure the connection to the remote server
remote_config = RemoteExecutorConfig(host="127.0.0.1", port=50052, ssl_enabled=False)

# 2. Define a VLLMNode for a multimodal model
#    This object will be serialized and sent to the server for execution.
vllm_node = VLLMNode(
    model="OpenGVLab/InternVL2-2B",
    use_chat_template=True, # Use the model's official prompt format
    modalities=["image"],
    sampling_params={"max_tokens": 128}
)

# 3. Build the pipeline. The remote node fits in just like any other.
pipeline = Pipeline(
    [
        MediaReaderNode(path="examples/draw.mp4"),
        VideoTrackSource(),
        TakeFirstFrameNode(),
        DecodeVideoFrame(),
        # Prepare the data for the model using a simple transform function
        TransformNode(
            transform_func=lambda img: {
                "messages": [{'role': 'user', 'content': f'<image>\nDescribe this image.'}],
                "image": img,
            }
        ),
        # Wrap the VLLMNode with the remote config to make it run on the server
        remote_config(vllm_node),
        # Add a node to print the streaming response
        PrintResponseStream(), # (Assumes a simple custom node for printing)
    ]
)

# When run, the pipeline will transparently execute the VLLM inference on the remote server.
pipeline.run()
```

## Installation

```bash
# For core functionality:
pip install -e .

# For ML nodes, examples, and the remote server:
pip install -r requirements-ml.txt
pip install vllm
```

## Examples

The `examples/` directory contains a rich set of scripts demonstrating the SDK's capabilities.

| Example File                      | Description                                                                                             |
|-----------------------------------|---------------------------------------------------------------------------------------------------------|
| **VLLM Multimodal Examples**      |                                                                                                         |
| `remote_vllm_internvl.py`         | **Image-to-Text**: Uses the powerful `InternVL` model with its chat template to describe an image.        |
| `remote_vllm_deepseek_vl.py`      | **Image-to-Text**: An alternative vision model example using `deepseek-vl` with a simple prompt template.  |
| `remote_vllm_ultravox.py`         | **Audio-to-Text**: Uses the `Ultravox` model to answer a question based on an audio clip.                 |
| `remote_vllm_minicpmo.py`         | **Image-to-Text**: Demonstrates using the `MiniCPM-o` model with its specific prompt format.              |
| **Transformers-based Examples**   |                                                                                                         |
| `remote_transformers_pipeline.py` | **Audio Classification**: A general-purpose example of using the `TransformersPipelineNode` for inference. |
| `remote_ultravox.py`              | **Audio-to-Text**: The original `Ultravox` example using the Hugging Face `transformers` library directly. |
| `remote_qwen_omni_assistant.py`   | **Video & Audio-to-Text/Speech**: A complex example using `Qwen2.5-Omni` for multimodal conversation.     |
| **Core SDK Concepts**             |                                                                                                         |
| `basic_pipeline.py`               | A minimal example of a purely local pipeline.                                                           |
| `remote_whisper_transcription.py` | Demonstrates remote execution of a pre-registered node (`WhisperTranscriptionNode`).                    |

## Project Structure

A high-level overview of the most important directories.

```
remotemedia/
├── core/                   # Core Pipeline, Node, and RemoteExecutorConfig classes
├── nodes/                  # Built-in processing nodes (audio, video, ML, etc.)
├── packaging/              # Automatic dependency analysis and code packaging
└── remote/                 # Client for communicating with the remote service

examples/                   # Example scripts for various use cases

remote_service/             # The remote execution gRPC server
└── src/server.py           # Main server entry point
```

## Documentation

- [**Developer Guide**](DEVELOPER_GUIDE.md) - **Start here!** The essential, in-depth guide for building with the SDK.
- [Development Strategy](DevelopmentStrategyDocument.md) - The original planning and strategy document.

## Contributing

This project is under active development. Please see the [Developer Guide](DEVELOPER_GUIDE.md) for principles and patterns.

## Requirements

- Python 3.9+
- See `requirements.txt` and `requirements-ml.txt` for all dependencies. 