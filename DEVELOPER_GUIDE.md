# Developer Guide: Building with the Remote Media Processing SDK

This guide provides developers with the essential concepts, rules, and best practices for building custom processing nodes and leveraging the full power of the Remote Media Processing SDK.

## 1. Core Concepts

### The Pipeline

The `Pipeline` is the heart of the SDK. It manages the flow of data between different processing units. You connect `Node` objects together in a sequence, and the pipeline ensures that data produced by one node is fed into the next.

```python
from remotemedia.core import Pipeline
from remotemedia.nodes import MediaReaderNode, AudioResampleNode, MediaWriterNode

pipeline = Pipeline(
    MediaReaderNode(file_path="input.mp3"),
    AudioResampleNode(target_sample_rate=16000),
    MediaWriterNode(output_path="output.wav")
)
pipeline.run()
```

### The Node

A `Node` is the fundamental building block of a pipeline. It's a Python class that performs a specific, atomic operation on the data that passes through it. Examples include reading a file, resizing an image, resampling audio, or running an ML model.

Every node you create should inherit from the base `remotemedia.core.node.Node` class.

## 2. The Node Lifecycle: `__init__` vs. `initialize`

Understanding the lifecycle of a Node is **critical** for using the remote execution features correctly. A node has four key methods: `__init__`, `initialize`, `process`, and `cleanup`.

| Method         | Purpose                               | When is it Called?                                       | Where does it Run?                                                              |
|----------------|---------------------------------------|----------------------------------------------------------|---------------------------------------------------------------------------------|
| `__init__`     | Basic setup, store configuration.     | When the node object is first created in your script.    | **Always on the client machine.**                                               |
| `async initialize` | Heavy setup, load models, check hardware. | Just before processing begins.                           | On the **local machine** for local pipelines, or on the **remote server** for remote pipelines. |
| `async process`  | The main data processing logic.       | Repeatedly for each chunk of data in the stream.         | On the **local machine** or the **remote server**, depending on the pipeline setup.     |
| `async cleanup`    | Release resources (files, models, etc). | After the stream ends or on an error.                    | On the **local machine** or the **remote server**.                                      |

### The Golden Rule of Node Development

> **Heavy setup, dependency imports, and hardware checks MUST go in `initialize`, not `__init__`.**

This is the most important principle for creating robust, reusable, and truly "remote" nodes.

-   **`__init__` is for configuration:** It should be lightweight and only store parameters. It runs on the client, which should not need heavy libraries like `torch` or `tensorflow` just to *define* a pipeline.
-   **`initialize` is for execution setup:** It runs in the actual execution environment (e.g., the remote server with GPUs). This is the place to import heavy libraries, load models, and check for `cuda` availability.

**Correct Implementation:**

```python
# remotemedia/nodes/ml.py

class MyHeavyMLNode(Node):
    def __init__(self, model_path: str, **kwargs):
        super().__init__(**kwargs)
        # GOOD: Only store config. No heavy imports here.
        self.model_path = model_path
        self.model = None

    async def initialize(self):
        # GOOD: Heavy imports and model loading are done here.
        # This code will run on the remote server.
        import torch
        from my_ml_library import load_model

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = load_model(self.model_path).to(self.device)
        logger.info(f"MyHeavyMLNode initialized on device: {self.device}")

    async def process(self, data):
        # ... processing logic using self.model ...
        pass
```

## 3. Remote Execution Models

The SDK's most powerful feature is its ability to offload intensive work to a more powerful server. There are two primary ways to achieve this.

### A. `RemoteObjectExecutionNode`: For Custom, Streamed Objects

This is the most flexible and powerful pattern. You create a node *instance* on your client machine, and the SDK serializes the object, sends it to the server (along with its code dependencies), and executes it there.

-   **Pros:** Ultimate flexibility. Allows you to run arbitrary, custom code on the remote server without needing to modify the server's codebase. Perfect for experimentation and custom user logic.
-   **Cons:** Incurs a slight overhead for serialization and code packaging.

This is where the Golden Rule from Section 2 is **essential**. The `__init__` runs on your client, but `initialize` and `process` run on the server.

### B. `RemoteExecutionNode`: For Pre-Registered Nodes

Use this when the node's class (e.g., `WhisperTranscriptionNode`) is already known and present in the `remotemedia.nodes` package on the server. You simply tell the server the *name* of the node to use.

-   **Pros:** Efficient, simple to call.
-   **Cons:** Requires the node to be part of the core SDK and deployed on the server.

### The `RemoteExecutorConfig` Smart Factory

While you can use the nodes above directly, the recommended approach is to use the `RemoteExecutorConfig` class. It acts as a "smart factory" that automatically chooses the correct remote execution node based on what you provide it.

```python
from remotemedia.core import RemoteExecutorConfig

# Define the connection to your remote server
remote_config = RemoteExecutorConfig(
    host="192.168.1.100", 
    port=50052, 
    ssl_enabled=False
)

# --- Use Case 1: Run a pre-registered node by its name (uses RemoteExecutionNode) ---
remote_whisper = remote_config(
    "WhisperTranscriptionNode",
    node_config={"model": "large-v3"}
)

# --- Use Case 2: Run a local object remotely (uses RemoteObjectExecutionNode) ---
my_custom_node = MyCustomFilterNode(strength=0.8)
remote_custom = remote_config(my_custom_node)

# --- Build the pipeline ---
pipeline = Pipeline(
    MediaReaderNode(file_path="input.wav"),
    remote_custom,  # The remote node fits in just like any other
    MediaWriterNode(output_path="output.wav")
)
pipeline.run()
```

## 4. Built-in ML Nodes

The SDK includes several pre-built nodes that integrate with popular machine learning libraries.

### `TransformersPipelineNode` & `UltravoxNode`

These nodes provide access to the Hugging Face `transformers` library. `TransformersPipelineNode` is a generic wrapper for dozens of tasks like `audio-classification`, `text-generation`, and `image-to-text`, while `UltravoxNode` is specialized for the Ultravox multimodal model. They are excellent examples of the `RemoteObjectExecutionNode` pattern, where a locally defined object is executed on a remote server.

**Example: Remote Audio Classification**

This example shows how to define a `TransformersPipelineNode` on the client to perform audio classification on a remote server. The server will download the model (`superb/wav2vec2-base-superb-ks`) on the first run.

```python
# client_script.py
from remotemedia.nodes.ml import TransformersPipelineNode

# 1. Define the TransformersPipelineNode instance locally.
#    This object itself will be serialized and sent to the server.
classifier_node = TransformersPipelineNode(
    task="audio-classification",
    model="superb/wav2vec2-base-superb-ks",
)

# 2. Use the remote_config factory to wrap it.
remote_classifier = remote_config(classifier_node)

# 3. Build the audio processing pipeline.
pipeline = Pipeline(
    [
        MediaReaderNode(path="sample_audio.wav"),
        AudioTrackSource(),
        # Resample to 16kHz mono audio for the classification model
        AudioTransform(output_sample_rate=16000, output_channels=1),
        ExtractAudioDataNode(),
        remote_classifier,
        PrintOutputNode(), # A custom node to print the results
    ]
)
pipeline.run()
```

**Example: Running a custom `UltravoxNode` remotely.**

```python
# examples/remote_ultravox.py
from remotemedia.nodes.ml import UltravoxNode

# 1. Instantiate the node locally. The __init__ method runs here.
local_ultravox_object = UltravoxNode(
    model_id="fixie-ai/ultravox-v0_5-llama-3_1-8b",
    system_prompt="You are a helpful poetic assistant."
)

# 2. Use the remote_config factory to wrap the local object.
#    The SDK will serialize `local_ultravox_object` and send it to the server.
remote_node = remote_config(local_ultravox_object)

# 3. Use the remote_node in a pipeline
pipeline = Pipeline(
    MediaReaderNode(file_path="gettysburg.wav"),
    remote_node,
    # ...
)
pipeline.run()
```

### `VLLMNode`: Your Gateway to High-Performance LLMs

For maximum performance, the `VLLMNode` provides direct access to the `vLLM` inference engine, allowing for high-throughput, streaming generation from a wide variety of open-source models. Its constructor is designed to mirror `vllm.LLM` for a familiar experience.

#### Key Features:
- **Streaming-first**: Natively streams tokens as they are generated.
- **Multimodal**: Supports text, image, and audio inputs.
- **Familiar API**: Arguments like `model`, `tensor_parallel_size`, `quantization`, and `max_model_len` are exposed directly.
- **Flexible Prompting**: Supports both simple f-string-style prompts and complex, model-specific chat templates.

#### Example 1: Simple Prompt Formatting

```python
# Create a VLLMNode for a vision model
deepseek_vllm_node = VLLMNode(
    model="deepseek-ai/deepseek-vl2-tiny",
    prompt_template="<|User|>: <image>\\n{question}\\n\\n<|Assistant|>:",
    modalities=["image"],
    max_model_len=4096,
    hf_overrides={"architectures": ["DeepseekVLV2ForCausalLM"]},
    sampling_params={"temperature": 0.2, "max_tokens": 128},
)
```

#### Example 2: Using Model-Specific Chat Templates

For models requiring a complex conversation structure, set `use_chat_template=True`. The node will then expect a `messages` list in the data it receives.

```python
# Create a VLLMNode that uses the model's chat template
internvl_vllm_node = VLLMNode(
    model="OpenGVLab/InternVL2-2B",
    use_chat_template=True,
    modalities=["image"],
    sampling_params={
        "temperature": 0.2,
        "max_tokens": 128,
        "stop_tokens": ["<|endoftext|>", "<|im_start|>"] # Automatically converted to token IDs
    },
)

# A TransformNode prepares the data for the chat template
transform_for_chat = TransformNode(
    transform_func=lambda image: {
        "messages": [{'role': 'user', 'content': f'<image>\n{question}'}],
        "image": image,
    }
)
```

## 5. Utility Nodes

The SDK provides a set of small, reusable utility nodes that are essential for building complex and robust pipelines.

| Node                   | Description                                                                                             |
|------------------------|---------------------------------------------------------------------------------------------------------|
| `TransformNode`        | Applies a custom function (sync or async) to each item in the stream. Perfect for simple data shaping.    |
| `TakeFirstFrameNode`   | A specialized node that passes only the first video frame from a stream and ignores the rest.             |
| `DecodeVideoFrame`     | Decodes a raw `av.VideoFrame` object into a `PIL.Image` for use in vision models.                         |
| `ConcatenateAudioNode` | Consumes an entire audio stream and outputs a single, flattened audio array. Ideal for non-streaming models. |
| `BatchingNode`         | Collects items into a list of a specified size (`batch_size`) before passing the batch downstream.      |
| `PassThroughNode`      | Passes data through without modification. Useful for debugging.                                         |

### Example: Building a Vision Pipeline

This pipeline demonstrates how to chain several utility nodes together to feed a single video frame to a remote `VLLMNode`.

```python
from remotemedia.nodes.source import MediaReaderNode, VideoTrackSource
from remotemedia.nodes.video import DecodeVideoFrame, TakeFirstFrameNode
from remotemedia.nodes.transform import TransformNode
from remotemedia.nodes.ml import VLLMNode

# Assume remote_config and internvl_vllm_node are defined as above
question = "What is happening in this image?"

transform_for_chat = TransformNode(
    transform_func=lambda image: {
        "messages": [{'role': 'user', 'content': f'<image>\n{question}'}],
        "image": image,
    }
)

pipeline = Pipeline(
    [
        MediaReaderNode(path="input_video.mp4"),
        VideoTrackSource(),       # Extracts raw video frames
        TakeFirstFrameNode(),     # Takes only the first frame
        DecodeVideoFrame(),       # Decodes the frame to an image
        transform_for_chat,       # Formats the data for the model
        remote_config(internvl_vllm_node), # Runs the model remotely
        PrintResponseStream(),    # A custom node to print the output
    ]
)

pipeline.run()
```

## 6. Server Setup

To use remote execution, you need the gRPC server running.

1.  **Install dependencies:** The server needs both the core SDK requirements and any extra dependencies for the nodes it might run (like the ML libraries).
    ```bash
    pip install -r requirements.txt
    pip install -r requirements-ml.txt
    pip install vllm transformers
    ```

2.  **Run the server:** You must run the server from the project's root directory with the `PYTHONPATH` set, so it can find all the necessary modules.
    ```bash
    PYTHONPATH=. python remote_service/src/server.py
    ```

The server will then listen for incoming gRPC requests from clients running a remote node. 