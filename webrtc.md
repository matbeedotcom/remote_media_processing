# Using WebRTC for Real-Time Media Pipelines

The Remote Media Processing SDK provides a powerful, high-level integration with `aiortc` to enable real-time, bidirectional media streaming directly into and out of processing pipelines. This guide explains the key components and demonstrates how to build a complete WebRTC-enabled application using an automated signaling server.

## Core WebRTC Components

The WebRTC integration is built around these key classes in the `remotemedia.webrtc` module:

| Class              | Role                                                                                                              |
| ------------------ | ----------------------------------------------------------------------------------------------------------------- |
| `WebRTCManager`    | The central controller. It manages the `RTCPeerConnection`, handles signaling, creates the pipeline nodes, and runs the entire session. |
| `WebRTCSourceNode` | A pipeline **source**. It listens to an `RTCPeerConnection` and injects incoming media and data into the pipeline. |
| `WebRTCSinkNode`   | A pipeline **sink**. It consumes media and data from the pipeline and sends it out over the `RTCPeerConnection`.   |
| `signaling.SignalingClient` | An internal helper used by the `WebRTCManager` to automate the offer/answer handshake. |

### The Highly Simplified Workflow

The `WebRTCManager` is designed to make setting up a real-time pipeline incredibly simple. The entire process is now handled by the manager.

1.  **Instantiate `WebRTCManager`**: This prepares the WebRTC connection.
2.  **Create a `Pipeline`**: Build your pipeline using `manager.create_source_node()` and `manager.create_sink_node()`.
3.  **Run It**: Call `manager.run_with_signaling(pipeline, url)`. This single method handles connecting to the signaling server, performing the handshake, and running the pipeline.

## Full Example: Automated Echo Pipeline

This example demonstrates a complete "echo" server with a fully automated handshake and execution process.

The workflow is as follows:
1.  Run the signaling server.
2.  Run the main Python application (`webrtc_with_signaling.py`).
3.  Open the web client (`webrtc_client.html`) in a browser.
4.  The manager automatically handles the offer/answer exchange via the signaling server, establishes the connection, and starts the pipeline.

### 1. The Signaling Server

First, start the signaling server, which relays messages between the two peers.

```bash
# From the project root directory
python remote_service/src/signaling_server.py
```

### 2. The Python Pipeline Application

Next, run the main pipeline script. The new, highly simplified setup is shown below. See the full source code at [`examples/webrtc_with_signaling.py`](./examples/webrtc_with_signaling.py).

```python
# A snippet from examples/webrtc_with_signaling.py

# 1. Create a manager.
manager = WebRTCManager()

# 2. Create the pipeline using the manager as a factory.
pipeline = Pipeline([
    manager.create_source_node(),
    TransformNode(transform_func=lambda data: logging.info(f"Echoing a '{list(data.keys())[0]}' frame") or data),
    manager.create_sink_node(),
])

# 3. Run everything.
# The manager will handle the signaling handshake and pipeline execution.
await manager.run_with_signaling(pipeline, SIGNALING_URL)
```

To run the full application:
```bash
# From the project root directory
python examples/webrtc_with_signaling.py
```

### 3. The Web Client

Finally, open the client HTML file in a web browser: [`examples/webrtc_client.html`](./examples/webrtc_client.html).

The JavaScript client will connect, and the `WebRTCManager` on the server will drive the rest of the setup. Once connected, you will see your local video on the left and the video being echoed back from the Python pipeline on the right.

## Manual End-to-End Testing with Python

For more advanced use cases or for testing the low-level components, the [`examples/webrtc_manual_test.py`](./examples/webrtc_manual_test.py) script provides a complete example of a Python-to-Python WebRTC connection.

This script does not use the automated `run_with_signaling` method. Instead, it demonstrates how to:

*   Run the signaling server in a separate process directly from the test script.
*   Manually create `WebRTCManager` instances for both the offerer and the answerer.
*   Perform the SDP offer/answer exchange programmatically using HTTP requests.
*   Use a public **STUN server** (`stun:stun.l.google.com:19302`) to facilitate connections, a recommended practice for robust NAT traversal.
*   Stream a local media file (e.g., `examples/draw.mp4`) into the pipeline using `aiortc.contrib.media.MediaPlayer`.
*   Set up a full bidirectional "echo" test where a client sends audio and video, and the server echoes it back to the client for verification.

To run the test:
```bash
# From the project root directory
python examples/webrtc_manual_test.py
```

> **Note for macOS users**: This test uses Python's `multiprocessing` module to run the server. Due to the way macOS spawns new processes, you may need to explicitly set the start method to `"fork"` at the beginning of your script to ensure correct behavior. The example script already includes this logic. 