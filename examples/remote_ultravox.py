#!/usr/bin/env python3
"""
Example of using the RemoteObjectExecutionNode to stream and execute an
UltravoxNode instance on a remote server.

This demonstrates how to define a node locally, then offload its execution
to a remote machine without requiring the node to be pre-registered on the server.
The server only needs the required dependencies (e.g. PyTorch, transformers).

**TO RUN THIS EXAMPLE:**

1.  **Install ML dependencies:**
    $ pip install -r requirements-ml.txt

2.  **Start the server:**
    In a separate terminal, start the server with the project root in the python path.
    The first time this runs, the server will download the Ultravox model (~700MB).
    $ PYTHONPATH=. python remote_service/src/server.py

3.  **Run this script:**
    $ python examples/remote_ultravox.py
"""

import asyncio
import logging
import numpy as np
import soundfile as sf
import os

# Ensure the 'remotemedia' package is in the Python path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from remotemedia.core.pipeline import Pipeline
from remotemedia.core.node import RemoteExecutorConfig
from remotemedia.nodes.source import MediaReaderNode, AudioTrackSource
from remotemedia.nodes.audio import AudioTransform, ExtractAudioDataNode, AudioBuffer
from remotemedia.nodes.remote import RemoteObjectExecutionNode
from remotemedia.nodes.ml import UltravoxNode
from remotemedia.nodes import PassThroughNode

# Configure basic logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class PrintNode(PassThroughNode):
    """A simple node that prints any data it receives."""
    async def process(self, data):
        """
        Process data, which can be either a single item or an async generator.
        """
        if hasattr(data, '__aiter__'):  # If it's an async generator
            async for item in data:
                print(f"\n>> ULTRAVOX RESPONSE: {item[0] if isinstance(item, tuple) else item}\n")
                yield item
        else:  # If it's a single item
            print(f"\n>> ULTRAVOX RESPONSE: {data[0] if isinstance(data, tuple) else data}\n")
            yield data


async def create_dummy_audio_file(filepath: str, duration_s: int = 5, sample_rate: int = 44100):
    """Creates a dummy audio file with a sine wave for testing."""
    if os.path.exists(filepath):
        return
    logging.info(f"Creating dummy audio file at '{filepath}'...")
    t = np.linspace(0., float(duration_s), int(sample_rate * duration_s))
    amplitude = np.iinfo(np.int16).max * 0.5
    # A simple spoken phrase might be "hello world", let's simulate that with two tones.
    data1 = amplitude * np.sin(2. * np.pi * 440. * t[:len(t)//2])
    data2 = amplitude * np.sin(2. * np.pi * 880. * t[len(t)//2:])
    data = np.concatenate([data1, data2])
    await asyncio.to_thread(sf.write, filepath, data.astype(np.int16), sample_rate)
    logging.info("Dummy audio file created.")


async def main():
    """
    Main function to set up and run the remote Ultravox pipeline.
    """
    REMOTE_HOST = os.environ.get("REMOTE_HOST", "127.0.0.1")
    logger.info("--- Running Remote Ultravox TTS ---")

    dummy_audio_path = "examples/transcribe_demo.wav"
    await create_dummy_audio_file(dummy_audio_path)

    pipeline = Pipeline()

    # The MediaReaderNode will provide the initial stream of audio chunks locally
    pipeline.add_node(MediaReaderNode(
        path=dummy_audio_path, 
        chunk_size=4096,
        name="MediaReader"
    ))

    # Convert av.AudioFrame objects into (ndarray, sample_rate) tuples
    pipeline.add_node(AudioTrackSource(name="AudioTrackSource"))

    # Ultravox expects 16kHz audio, so we resample it locally.
    pipeline.add_node(AudioTransform(
        output_sample_rate=16000, 
        output_channels=1,
        name="AudioTransform"
    ))

    # Add a buffer to properly handle streaming
    buffer_node = AudioBuffer(
        buffer_size_samples=16000,  # 1 second buffer at 16kHz
        name="AudioBuffer"
    )
    buffer_node.is_streaming = True  # Ensure streaming mode is enabled
    pipeline.add_node(buffer_node)

    # Configure the remote execution
    remote_config = RemoteExecutorConfig(host=REMOTE_HOST, port=50052, ssl_enabled=False)
    
    # 1. Create an instance of the UltravoxNode locally.
    #    We can configure its parameters just like any other local object.
    ultravox_instance = UltravoxNode(
        model_id="fixie-ai/ultravox-v0_5-llama-3_1-8b",
        system_prompt="You are a friendly and helpful poetic assistant who loves answering questions. You excel at explaining complex scientific concepts with creative flair and a warm, engaging personality.",
        buffer_duration_s=1.0,  # Match the AudioBuffer size
        name="UltravoxNode"
    )

    # 2. Use RemoteObjectExecutionNode to execute this object on the server.
    #    The node object is serialized and sent to the server, which then streams
    #    data to and from its `process` method.
    remote_node = RemoteObjectExecutionNode(
        obj_to_execute=ultravox_instance,
        remote_config=remote_config,
        name="RemoteUltravox",
        node_config={
            'streaming': True,  # Enable streaming in node config
            'buffer_size': 16000  # Match audio buffer size
        }
    )
    remote_node.is_streaming = True  # Ensure streaming mode is enabled
    pipeline.add_node(remote_node)

    # Add a simple node to print the text response from the server
    pipeline.add_node(PrintNode(name="PrintNode"))

    logger.info("Starting remote Ultravox pipeline (via object streaming)...")
    async with pipeline.managed_execution():
        try:
            logger.info("Pipeline execution started, consuming stream...")
            # Process the stream in chunks
            async for result in pipeline.process():
                logger.debug(f"Pipeline produced result: {result}")
            logger.info("Pipeline stream consumed successfully.")
        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            raise  # Re-raise to ensure proper cleanup

    logger.info("Remote Ultravox pipeline finished.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logging.error(f"An error occurred: {e}", exc_info=True)
        logging.error("Please ensure the remote server is running and has the ML dependencies installed.") 