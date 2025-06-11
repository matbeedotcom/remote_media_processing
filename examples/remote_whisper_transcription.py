#!/usr/bin/env python3
"""
Example of using the RemoteExecutionNode to run the WhisperTranscriptionNode
on a remote server for real-time audio transcription.

This demonstrates how to offload a heavy ML workload to a remote machine.

**TO RUN THIS EXAMPLE:**

1.  **Start the server:**
    In a separate terminal, ensure the server has the required ML libraries installed:
    $ pip install -r requirements-ml.txt
    
    Then, start the server with the project root in the python path:
    $ PYTHONPATH=. python remote_service/src/server.py

2.  **Run this script:**
    $ python examples/remote_whisper_transcription.py
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
from remotemedia.nodes.audio import AudioTransform
from remotemedia.nodes.remote import RemoteExecutionNode, RemoteObjectExecutionNode
from remotemedia.nodes import PassThroughNode
from remotemedia.nodes.ml import WhisperTranscriptionNode

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class PrintNode(PassThroughNode):
    """A simple node that prints any data it receives."""
    async def process(self, data):
        # The data from the remote whisper node is a tuple, e.g., ('some text',)
        print(f"REMOTE TRANSCRIPTION: {data[0]}")
        yield data


async def create_dummy_audio_file(filepath: str, duration_s: int = 10, sample_rate: int = 44100):
    """Creates a dummy audio file with a sine wave for testing."""
    if os.path.exists(filepath):
        return
    logging.info(f"Creating dummy audio file at '{filepath}'...")
    t = np.linspace(0., float(duration_s), int(sample_rate * duration_s))
    amplitude = np.iinfo(np.int16).max * 0.5
    data = amplitude * np.sin(2. * np.pi * 440. * t)
    await asyncio.to_thread(sf.write, filepath, data.astype(np.int16), sample_rate)
    logging.info("Dummy audio file created.")


async def main():
    """
    Main function to run the remote Whisper transcription example.
    """
    import os
    REMOTE_HOST = os.environ.get("REMOTE_HOST", "127.0.0.1")
    # This example demonstrates sending a locally-defined `WhisperTranscriptionNode`
    # instance to a remote server for execution. This is useful for offloading
    # heavy ML tasks to a machine with more resources (e.g., a GPU).

    # This example uses a pre-existing audio file.
    # 1. Create a dummy audio file for the example
    dummy_audio_path = "examples/transcribe_demo.wav"
    # await create_dummy_audio_file(dummy_audio_path)

    # 2. Create and configure the pipeline
    pipeline = Pipeline()

    # The MediaReaderNode will provide the initial stream of audio chunks locally
    pipeline.add_node(MediaReaderNode(path=dummy_audio_path, chunk_size=4096))

    # Convert av.AudioFrame objects into (ndarray, sample_rate) tuples
    pipeline.add_node(AudioTrackSource())

    # Whisper expects 16kHz mono audio, so we resample it locally.
    pipeline.add_node(AudioTransform(output_sample_rate=16000, output_channels=1))

    # 2. Configure the remote execution node.
    #    This node takes the `transcription_node` object, sends it to the server,
    #    and manages the remote execution.
    #    NOTE: The remote server must be running on the specified host and port.
    remote_config = RemoteExecutorConfig(host=REMOTE_HOST, port=50052, ssl_enabled=False)
    transcription_node = WhisperTranscriptionNode()
    remote_exec_node = RemoteObjectExecutionNode(
        obj_to_execute=transcription_node,
        remote_config=remote_config
    )
    pipeline.add_node(remote_exec_node)

    # Add a simple node to print the transcribed text received from the server
    pipeline.add_node(PrintNode())

    # 3. Run the pipeline
    logging.info("Starting remote transcription pipeline...")
    async with pipeline.managed_execution():
        async for _ in pipeline.process():
            # The pipeline runs as we consume its output stream.
            pass

    logging.info("Remote transcription pipeline finished.")


if __name__ == "__main__":
    # Note: The first time you run this, the *server* will download the Whisper model.
    try:
        asyncio.run(main())
    except Exception as e:
        logging.error(f"An error occurred: {e}")
        logging.error("Please ensure the remote server is running and has the ML dependencies installed.") 