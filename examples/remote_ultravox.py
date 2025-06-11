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
from remotemedia.nodes.audio import AudioTransform, ExtractAudioDataNode
from remotemedia.nodes.remote import RemoteObjectExecutionNode
from remotemedia.nodes.ml import UltravoxNode
from remotemedia.nodes import PassThroughNode

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class PrintNode(PassThroughNode):
    """A simple node that prints any data it receives."""
    async def process(self, data_stream):
        async for data in data_stream:
            print(f"\n>> ULTRAVOX RESPONSE: {data[0]}\n")
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
    # This example demonstrates using the Ultravox models for text-to-speech
    # and voice cloning, executed on a remote server.

    # --- Text-to-Speech (TTS) ---
    logging.info("--- Running Remote Ultravox TTS ---")

    dummy_audio_path = "examples/transcribe_demo.wav"

    pipeline = Pipeline()

    # The MediaReaderNode will provide the initial stream of audio chunks locally
    pipeline.add_node(MediaReaderNode(path=dummy_audio_path, chunk_size=4096))

    # Convert av.AudioFrame objects into (ndarray, sample_rate) tuples
    pipeline.add_node(AudioTrackSource())

    # Ultravox expects 16kHz audio, so we resample it locally.
    pipeline.add_node(AudioTransform(output_sample_rate=16000, output_channels=1))

    # Configure the remote execution
    remote_config = RemoteExecutorConfig(host=REMOTE_HOST, port=50052, ssl_enabled=False)
    
    # 1. Create an instance of the UltravoxNode locally.
    #    We can configure its parameters just like any other local object.
    ultravox_instance = UltravoxNode(
        model_id="fixie-ai/ultravox-v0_5-llama-3_1-8b",
        system_prompt="You are a friendly and helpful poetic assistant who loves answering questions. You excel at explaining complex scientific concepts with creative flair and a warm, engaging personality."
    )

    # 2. Use RemoteObjectExecutionNode to execute this object on the server.
    #    The node object is serialized and sent to the server, which then streams
    #    data to and from its `process` method.
    pipeline.add_node(remote_config(ultravox_instance))

    # Add a simple node to print the text response from the server
    pipeline.add_node(PrintNode())

    logging.info("Starting remote Ultravox pipeline (via object streaming)...")
    async with pipeline.managed_execution():
        async for _ in pipeline.process():
            # The pipeline runs as we consume its output stream.
            pass

    logging.info("Remote Ultravox pipeline finished.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logging.error(f"An error occurred: {e}", exc_info=True)
        logging.error("Please ensure the remote server is running and has the ML dependencies installed.") 