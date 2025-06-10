#!/usr/bin/env python3
"""
Example of using the RemoteExecutionNode to run the UltravoxNode
on a remote server for multimodal audio-text to text generation.

This demonstrates how to offload a heavy, conversational ML workload.

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
from remotemedia.nodes.source import MediaReaderNode
from remotemedia.nodes.audio import AudioResampler
from remotemedia.nodes.remote import RemoteExecutionNode
from remotemedia.nodes.transform import PassThrough

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class PrintNode(PassThrough):
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
    dummy_audio_path = "ultravox_sample.wav"
    await create_dummy_audio_file(dummy_audio_path)

    pipeline = Pipeline()

    # The MediaReaderNode will provide the initial stream of audio chunks locally
    pipeline.add_node(MediaReaderNode(file_path=dummy_audio_path, chunk_size=4096))

    # Ultravox expects 16kHz audio, so we resample it locally.
    pipeline.add_node(AudioResampler(target_sample_rate=16000))

    # Configure the remote execution
    remote_config = RemoteExecutorConfig(host="127.0.0.1", port=50052, ssl_enabled=False)
    
    # This node tells the server to run an 'UltravoxNode'.
    # The audio stream is sent to the server, and the text response is sent back.
    pipeline.add_node(RemoteExecutionNode(
        node_to_execute="UltravoxNode",
        remote_config=remote_config,
        # We can pass config to the remote node.
        # Here we define the persona of the AI assistant.
        node_config={
            "system_prompt": "You are a poetic assistant, skilled in explaining complex scientific concepts with creative flair."
        }
    ))

    # Add a simple node to print the text response from the server
    pipeline.add_node(PrintNode())

    logging.info("Starting remote Ultravox pipeline...")
    async with pipeline.managed_execution():
        while pipeline.is_running():
            await asyncio.sleep(0.5)

    logging.info("Remote Ultravox pipeline finished.")
    os.remove(dummy_audio_path)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logging.error(f"An error occurred: {e}", exc_info=True)
        logging.error("Please ensure the remote server is running and has the ML dependencies installed.") 