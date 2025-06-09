#!/usr/bin/env python3
"""
Example of using the RemoteExecutionClient to stream a custom,
dynamically-defined object for real-time audio processing.

This script demonstrates the full power of the cloudpickle streaming solution.
"""

import asyncio
import numpy as np
import logging

# Ensure the 'remotemedia' package is in the Python path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from remotemedia.core.node import Node, RemoteExecutorConfig
from remotemedia.core.pipeline import Pipeline
from remotemedia.nodes.remote import RemoteObjectExecutionNode

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class AudioEchoEffect(Node):
    """
    A simple, stateful audio effect that adds a decaying echo to an audio stream.
    
    This object is defined here and will be serialized and sent to the server.
    """
    def __init__(self, sample_rate: int, delay_seconds: float = 0.5, decay: float = 0.4, **kwargs):
        super().__init__(**kwargs)
        self.sample_rate = sample_rate
        self.delay_samples = int(delay_seconds * sample_rate)
        self.decay = decay
        self.is_streaming = True
        self.buffer = None

    async def initialize(self):
        """Initializes the echo buffer."""
        self.buffer = np.zeros(self.delay_samples, dtype=np.float32)
        logging.info(f"AudioEchoEffect initialized with {self.delay_samples}-sample delay.")

    async def cleanup(self):
        """Cleans up resources."""
        logging.info("AudioEchoEffect cleaned up.")
        self.buffer = None

    async def process(self, data_stream: asyncio.StreamReader):
        """
        Applies the echo effect to the incoming audio stream.
        """
        async for chunk, rate in data_stream:
            if rate != self.sample_rate:
                raise ValueError("Mismatched sample rates!")

            # Ensure chunk is 1D
            if chunk.ndim > 1:
                chunk = chunk.flatten()

            output_chunk = np.zeros_like(chunk)
            for i in range(len(chunk)):
                # Mix current sample with the delayed sample
                output_chunk[i] = chunk[i] + self.buffer[0] * self.decay
                
                # Update delay buffer: shift left and add new sample
                self.buffer = np.roll(self.buffer, -1)
                self.buffer[-1] = chunk[i]
            
            # The output of a node must be a tuple
            yield (output_chunk, self.sample_rate)


async def generate_sine_wave(duration_s: int, sample_rate: int, chunk_size: int):
    """
    An async generator that yields chunks of a sine wave.
    """
    logging.info("Starting to generate sine wave chunks...")
    total_samples = duration_s * sample_rate
    num_chunks = total_samples // chunk_size
    
    for i in range(num_chunks):
        start_sample = i * chunk_size
        time_vector = (start_sample + np.arange(chunk_size)) / sample_rate
        # A 440 Hz tone (A4)
        audio_chunk = np.sin(2 * np.pi * 440 * time_vector, dtype=np.float32)
        yield (audio_chunk, sample_rate)
        await asyncio.sleep(0.01) # Simulate real-time stream
    logging.info("Finished generating sine wave chunks.")


async def main():
    """
    Main function to set up and run the remote object streaming pipeline.
    """
    # 1. Configuration
    remote_config = RemoteExecutorConfig(host="127.0.0.1", port=50052, ssl_enabled=False)
    sample_rate = 16000
    
    # 2. Create the custom object to be executed remotely
    echo_effect = AudioEchoEffect(sample_rate=sample_rate, delay_seconds=0.2, decay=0.5)
    
    # 3. Create the audio stream generator
    audio_stream = generate_sine_wave(duration_s=5, sample_rate=sample_rate, chunk_size=512)
    
    # 4. Set up the pipeline
    pipeline = Pipeline(name="RemoteAudioEchoPipeline")
    pipeline.add_node(
        RemoteObjectExecutionNode(
            obj_to_execute=echo_effect,
            remote_config=remote_config
        )
    )
    
    # 5. Execute the pipeline
    logging.info("Starting remote audio processing pipeline...")
    processed_chunks = 0
    try:
        async with pipeline.managed_execution():
            async for _ in pipeline.process(audio_stream):
                processed_chunks += 1
                logging.info(f"Received processed audio chunk #{processed_chunks}")
    
    except Exception as e:
        logging.error(f"An error occurred during pipeline execution: {e}")
    finally:
        logging.info(f"Finished processing. Received a total of {processed_chunks} chunks.")


if __name__ == "__main__":
    # Note: Ensure the remote_service/src/server.py is running first.
    # You can run it with: `PYTHONPATH=. python remote_service/src/server.py`
    asyncio.run(main()) 