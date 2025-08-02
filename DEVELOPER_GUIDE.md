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

## 3. Execution Models

### Local Execution

This is the simplest model. The entire pipeline runs in a single process on your local machine. It's perfect for development, testing, and tasks that aren't computationally intensive.

### Remote Execution (Two Flavors)

This is the SDK's most powerful feature, allowing you to offload intensive work to a more powerful server.

#### A. `RemoteExecutionNode`: For Pre-Registered Nodes

Use this when the node's class (e.g., `WhisperTranscriptionNode`) is already known and present in the `remotemedia.nodes` package on the server. You tell the server the *name* of the node to use.

-   **Pros:** Efficient, simple to call.
-   **Cons:** Requires the node to be part of the core SDK and deployed on the server.

```python
# client_script.py
from remotemedia.nodes import RemoteExecutionNode

# The server will look for a registered node named "WhisperTranscriptionNode"
# and instantiate it with these parameters.
remote_whisper = RemoteExecutionNode(
    node_type="WhisperTranscriptionNode",
    node_config={
        "model_id": "openai/whisper-large-v3-turbo",
        "device": "cuda"
    }
)
```

#### B. `RemoteObjectExecutionNode`: For Custom, Streamed Objects

This is the most flexible and powerful pattern. You create a node *instance* on your client machine, and the SDK serializes the object, sends it to the server, and executes it there.

-   **Pros:** Ultimate flexibility. Allows you to run arbitrary, custom code on the remote server without needing to modify the server's codebase. Perfect for experimentation and custom user logic.
-   **Cons:** Incurs a slight overhead for serialization.

This is where the Golden Rule from Section 2 is **essential**. The `__init__` runs on your client, but `initialize` and `process` run on the server.

**Example: Running a custom `UltravoxNode` remotely via object streaming.**

```python
# examples/remote_ultravox.py

# 1. Import the node class itself, not just the remote executor
from remotemedia.nodes.ml import UltravoxNode
from remotemedia.nodes.remote import RemoteObjectExecutionNode

# 2. Instantiate the node locally. The __init__ method runs here.
#    Note that no heavy libraries are imported or used at this stage.
local_ultravox_object = UltravoxNode(
    system_prompt="You are a helpful assistant.",
    buffer_duration_s=5,
)

# 3. Wrap the local object in a RemoteObjectExecutionNode.
#    The SDK will serialize `local_ultravox_object` and send it to the server.
#    The server will then call .initialize(), .process(), and .cleanup() on the deserialized object.
remote_node = RemoteObjectExecutionNode(
    node_object=local_ultravox_object
)

# 4. Use the remote_node in a pipeline
pipeline = Pipeline(
    MediaReaderNode(file_path="gettysburg.wav"),
    remote_node,
    # ...
)
pipeline.run()
```

## 4. Built-in ML Nodes

The SDK includes several pre-built nodes that integrate with popular machine learning models and libraries, making it easy to add powerful AI capabilities to your pipelines. These nodes follow the "remote-first" design principle, ensuring that heavy dependencies and model loading are handled on the execution server, not on the client.

### `TransformersPipelineNode`: Your Gateway to Hugging Face

The `TransformersPipelineNode` is a versatile node that allows you to use almost any model from the Hugging Face Hub by simply specifying a `task`. It wraps the `transformers.pipeline` factory, giving you access to dozens of pre-trained models for audio, vision, and NLP.

**Example: Remote Text Classification**

Here's how you could use this node to perform sentiment analysis on a remote server. This example uses the `RemoteObjectExecutionNode` to send a locally-defined `TransformersPipelineNode` instance to the server for execution.

```python
# client_script.py
from remotemedia.core import Pipeline
from remotemedia.nodes import RemoteObjectExecutionNode, TransformersPipelineNode

# 1. Define the TransformersPipelineNode locally.
#    The __init__ method runs on the client and is very lightweight.
#    No models are downloaded here.
sentiment_analyzer_object = TransformersPipelineNode(
    task="text-classification",
    model="distilbert-base-uncased-finetuned-sst-2-english"
)

# 2. Wrap it in a RemoteObjectExecutionNode to send it to the server.
remote_sentiment_node = RemoteObjectExecutionNode(
    node_object=sentiment_analyzer_object
)

# 3. Create a simple pipeline to process some text.
#    (In a real application, the data might come from a MediaReaderNode,
#    a database, or another source).
pipeline = Pipeline()
# ... add a source node that yields text strings ...
pipeline.add_node(remote_sentiment_node)
# ... add a sink node to handle the results ...

# When the pipeline runs, the server will receive sentiment_analyzer_object,
# call its .initialize() method (which downloads the model and starts the
# transformers pipeline), and then feed data to its .process() method.
pipeline.run()

```

This pattern allows you to experiment with different models and tasks on the fly, without ever needing to modify the server's code.

## 5. RemoteProxyClient: The Simplest Remote Execution

While the pipeline approach is powerful for streaming data processing, sometimes you just want to execute arbitrary Python objects remotely. The `RemoteProxyClient` provides transparent remote execution for ANY Python object with minimal setup.

### Basic Usage

```python
from remotemedia.remote import RemoteProxyClient
from remotemedia.core.node import RemoteExecutorConfig

# Configure the connection
config = RemoteExecutorConfig(host="localhost", port=50052)

async with RemoteProxyClient(config) as client:
    # ANY object can be made remote with one line!
    calculator = Calculator()
    remote_calc = await client.create_proxy(calculator)
    
    # Use it exactly like a local object (just add await)
    result = await remote_calc.add(5, 3)
    print(f"Result: {result}")  # Executed on remote server!
    
    # Keyword arguments work transparently!
    result = await remote_calc.calculate(operation="multiply", a=10, b=4)
    
    # Object state is maintained remotely
    history = await remote_calc.history()
```

### Key Benefits

1. **Zero Configuration**: No special base classes or interfaces required
2. **Transparent Usage**: Call methods exactly as you would locally
3. **State Persistence**: Objects maintain their state on the remote server
4. **Session Management**: Automatic session handling across method calls

### How It Works

The `RemoteProxyClient` uses Python's `__getattr__` magic method to intercept all method calls on the proxy object. When you call a method:

1. The proxy captures the method name and arguments
2. Serializes them using CloudPickle
3. Sends them to the remote server via gRPC
4. The server executes the method on the actual object
5. Returns the result back to the client
6. The proxy deserializes and returns the result

**Special Handling:**
- **Generator Streaming (NEW!)**: Generators return proxy objects that stream data as needed
- **Async Generators**: Both sync and async generators are transparently streamed
- **Properties**: Non-callable attributes are fetched as values from the remote object
- **Keyword Arguments (NEW!)**: Full support for kwargs in all method types
- **Mixed Args**: Both positional and keyword arguments are properly serialized and passed
- **Batched Fetching**: Generator items are fetched in configurable batches (default: 10)
- **Early Termination**: Breaking from iteration properly closes the generator on the server
- **Error Propagation**: Exceptions in generators are propagated to the client

**Implementation Details:**
When a method returns a generator, the server:
1. Creates a `GeneratorSession` to track the generator state
2. Returns a special marker `{"__generator__": True, "generator_id": "...", "is_async": bool}`
3. The client creates a `RemoteGeneratorProxy` that implements async iteration
4. Items are fetched in batches using the `GetNextBatch` RPC method
5. The generator is automatically closed on completion or error

**Example - Streaming Large Files:**

```python
class DataProcessor:
    def __init__(self):
        self.data_path = "/large/dataset"
    
    def read_file_chunks(self, filename: str, chunk_size: int = 1024):
        """Generator that yields file chunks."""
        with open(f"{self.data_path}/{filename}", 'rb') as f:
            while chunk := f.read(chunk_size):
                yield chunk
    
    async def stream_sensor_data(self, sensor_id: str):
        """Async generator for real-time data."""
        while True:
            data = await self.read_sensor(sensor_id)
            if data is None:
                break
            yield data

# Usage with RemoteProxyClient:
async with RemoteProxyClient(config) as client:
    processor = DataProcessor()
    remote = await client.create_proxy(processor)
    
    # Streaming file chunks - only fetches as needed!
    async for chunk in await remote.read_file_chunks("large_dataset.bin"):
        process(chunk)
        if processed_enough():
            break  # Generator properly closed on server
    
    # Streaming sensor data
    async for data in await remote.stream_sensor_data("sensor_001"):
        handle_sensor_data(data)
```

### Best Practices

- **Serializable Objects**: Ensure your objects and their dependencies are serializable with CloudPickle
- **Avoid `__main__` Classes**: Classes defined in `__main__` can't be pickled. Define classes in importable modules instead
- **Avoid Local Resources**: Objects shouldn't depend on local files, sockets, or hardware
- **Async Methods**: All proxy methods return coroutines, so use `await`
- **Error Handling**: Remote exceptions are propagated back to the client

### Common Pitfall: Classes in `__main__`

CloudPickle cannot serialize classes defined in the `__main__` module. Always define your classes in a separate module:

```python
# BAD - This won't work
if __name__ == "__main__":
    class MyClass:
        def method(self):
            return "result"
    
    obj = MyClass()
    remote_obj = await client.create_proxy(obj)  # Will fail!

# GOOD - Define in a module
# my_module.py
class MyClass:
    def method(self):
        return "result"

# main.py
from my_module import MyClass
obj = MyClass()
remote_obj = await client.create_proxy(obj)  # Works!
```

### Use Cases

- **Heavy Computation**: Offload CPU/GPU intensive operations
- **Stateful Services**: Maintain complex state on powerful servers
- **ML Model Inference**: Run models without local installation
- **Data Processing**: Process large datasets remotely

### Supported Python Features

The RemoteProxyClient transparently handles various Python patterns:

```python
# Example class with different method types
class DataProcessor:
    def __init__(self):
        self._count = 0
    
    # Regular methods - work perfectly
    def process(self, data):
        return data.upper()
    
    # Methods with keyword arguments - work perfectly
    def process_with_options(self, data, capitalize=True, reverse=False):
        result = data.upper() if capitalize else data.lower()
        return result[::-1] if reverse else result
    
    # Async methods - work perfectly
    async def async_process(self, data, delay=0.1):
        await asyncio.sleep(delay)
        return data.lower()
    
    # Generators - automatically converted to lists
    def generate_numbers(self, n):
        for i in range(n):
            yield i * 2
    
    # Async generators - automatically converted to lists
    async def async_generate(self, n):
        for i in range(n):
            await asyncio.sleep(0.01)
            yield i * 3
    
    # Properties - access with await
    @property
    def count(self):
        return self._count
    
    # Special methods - most work correctly
    def __call__(self, x):
        return x * self._count

# Usage
async with RemoteProxyClient(config) as client:
    processor = DataProcessor()
    remote = await client.create_proxy(processor)
    
    # All these work transparently
    result = await remote.process("hello")           # Regular method
    
    # Keyword arguments work exactly as expected!
    options_result = await remote.process_with_options("Test", capitalize=False, reverse=True)
    async_result = await remote.async_process("WORLD", delay=0.5)  # Async with kwargs
    
    numbers = await remote.generate_numbers(5)      # Generator → list
    async_nums = await remote.async_generate(3)     # Async gen → list
    count = await remote.count                      # Property access
    called = await remote.__call__(10)              # Special method
```

## 6. Server Setup

To use remote execution, you need the gRPC server running.

1.  **Install dependencies:** The server needs both the core SDK requirements and any extra dependencies for the nodes it might run (like the ML libraries).
    ```bash
    pip install -r requirements.txt
    pip install -r requirements-ml.txt
    ```

2.  **Run the server:** You must run the server from the project's root directory with the `PYTHONPATH` set, so it can find all the necessary modules.
    ```bash
    PYTHONPATH=. python remote_service/src/server.py
    ```

The server will then listen for incoming gRPC requests from clients running a `RemoteExecutionNode` or `RemoteObjectExecutionNode`. 