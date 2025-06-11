#!/usr/bin/env python3
"""
Example of using the WhisperTranscriptionNode for real-time audio transcription.
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
from remotemedia.nodes.source import MediaReaderNode, AudioTrackSource
from remotemedia.nodes.audio import AudioTransform
from remotemedia.nodes.ml import WhisperTranscriptionNode
from remotemedia.nodes import PassThroughNode

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
    Main function to set up and run the transcription pipeline.
    """
    # 1. Create a dummy audio file for the example
    dummy_audio_path = "examples/transcribe_demo.wav"

    # 2. Create and configure the pipeline
    pipeline = Pipeline()

    # The MediaReaderNode will provide the initial stream of audio chunks
    pipeline.add_node(MediaReaderNode(path=dummy_audio_path, chunk_size=4096))
    # Convert av.AudioFrame objects into (ndarray, sample_rate) tuples
    pipeline.add_node(AudioTrackSource())
    # Whisper expects 16kHz audio, so we resample it.
    pipeline.add_node(AudioTransform(output_sample_rate=16000, output_channels=1))

    # Add the Whisper node to perform transcription
    pipeline.add_node(WhisperTranscriptionNode())

    # Add a simple node to print the transcribed text
    pipeline.add_node(PrintNode())

    # 3. Run the pipeline
    logging.info("Starting transcription pipeline...")
    async with pipeline.managed_execution():
        async for _ in pipeline.process():
            # The pipeline runs as we consume its output stream.
            pass

    logging.info("Transcription pipeline finished.")


if __name__ == "__main__":
    # Note: The first time you run this, it will download the Whisper model,
    # which can be several gigabytes.
    try:
        asyncio.run(main())
    except Exception as e:
        logging.error(f"An error occurred: {e}") 