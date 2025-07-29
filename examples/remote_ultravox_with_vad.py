#!/usr/bin/env python3
"""
Example of using VoiceActivityDetector with RemoteObjectExecutionNode for Ultravox.

This example demonstrates how to use VAD to filter out silence before sending
audio to the remote Ultravox model, reducing unnecessary processing and
improving response times.

**TO RUN THIS EXAMPLE:**

1.  **Install ML dependencies:**
    $ pip install -r requirements-ml.txt

2.  **Start the server:**
    In a separate terminal, start the server with the project root in the python path.
    The first time this runs, the server will download the Ultravox model (~700MB).
    $ PYTHONPATH=. python remote_service/src/server.py

3.  **Run this script:**
    $ python examples/remote_ultravox_with_vad.py
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
from remotemedia.nodes.audio import AudioTransform, AudioBuffer, VoiceActivityDetector
from remotemedia.nodes.remote import RemoteObjectExecutionNode
from remotemedia.nodes.ml import UltravoxNode
from remotemedia.nodes import PassThroughNode

# Configure basic logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Set specific loggers to INFO to reduce noise
logging.getLogger("Pipeline").setLevel(logging.INFO)
logging.getLogger("remotemedia.nodes.remote").setLevel(logging.INFO)


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


class VADStatsNode(PassThroughNode):
    """A node that logs VAD statistics while passing data through."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.total_chunks = 0
        self.speech_chunks = 0
        self.is_streaming = True
    
    async def process(self, data_stream):
        """Process and log VAD statistics."""
        async for data in data_stream:
            self.total_chunks += 1
            logger.debug(f"VADStats received data type: {type(data)}, shape: {data[0].shape if isinstance(data, tuple) and hasattr(data[0], 'shape') else 'N/A'}")
            
            # If data includes VAD metadata
            if isinstance(data, tuple) and len(data) == 2 and isinstance(data[1], dict):
                (audio_data, metadata) = data
                if metadata.get("is_speech", False):
                    self.speech_chunks += 1
                    logger.info(
                        f"VAD: Speech detected (chunk {self.total_chunks}, "
                        f"ratio: {metadata['speech_ratio']:.2f}, "
                        f"energy: {metadata['avg_energy']:.4f})"
                    )
                else:
                    logger.debug(
                        f"VAD: Silence (chunk {self.total_chunks}, "
                        f"ratio: {metadata['speech_ratio']:.2f})"
                    )
                # Pass through only audio data (the tuple, not just the array)
                logger.debug(f"VADStats yielding audio_data: {type(audio_data)}")
                yield audio_data
            else:
                # No metadata, just pass through
                logger.debug(f"VADStats passing through data without metadata")
                yield data
        
        logger.info(
            f"VAD Summary: {self.speech_chunks}/{self.total_chunks} chunks "
            f"contained speech ({100*self.speech_chunks/max(self.total_chunks,1):.1f}%)"
        )


async def create_demo_audio_with_silence(filepath: str, duration_s: int = 10, sample_rate: int = 44100):
    """Creates a demo audio file with alternating speech and silence."""
    if os.path.exists(filepath):
        return
    
    logger.info(f"Creating demo audio file with speech and silence at '{filepath}'...")
    
    samples = int(sample_rate * duration_s)
    t = np.linspace(0., float(duration_s), samples)
    audio = np.zeros(samples)
    
    # Create alternating speech and silence segments
    segments = [
        (0.5, 2.0),    # Speech: "Hello"
        (3.0, 5.0),    # Speech: "How are you?"
        (6.0, 8.0),    # Speech: "Tell me about AI"
        (8.5, 9.5),    # Speech: "Thank you"
    ]
    
    for start, end in segments:
        mask = (t >= start) & (t < end)
        # Simulate speech with modulated tones
        freq = 440 + 100 * np.sin(2 * np.pi * 2 * t[mask])
        audio[mask] = 0.3 * np.sin(2 * np.pi * freq * t[mask])
    
    # Add light background noise
    audio += 0.005 * np.random.randn(samples)
    
    await asyncio.to_thread(sf.write, filepath, audio.astype(np.float32), sample_rate)
    logger.info(f"Demo audio file created ({duration_s}s with speech segments at {segments})")


async def main():
    """
    Main function to set up and run the remote Ultravox pipeline with VAD.
    """
    REMOTE_HOST = os.environ.get("REMOTE_HOST", "127.0.0.1")
    logger.info("--- Running Remote Ultravox with Voice Activity Detection ---")

    demo_audio_path = "examples/vad_demo.wav"
    await create_demo_audio_with_silence(demo_audio_path)

    pipeline = Pipeline()

    # Source: Read media file
    pipeline.add_node(MediaReaderNode(
        path=demo_audio_path, 
        chunk_size=4096,
        name="MediaReader"
    ))

    # Extract audio track
    pipeline.add_node(AudioTrackSource(name="AudioTrackSource"))

    # Resample to 16kHz for Ultravox
    pipeline.add_node(AudioTransform(
        output_sample_rate=16000, 
        output_channels=1,
        name="AudioTransform"
    ))

    # Add VAD to detect speech segments
    # In passthrough mode with metadata for logging
    vad_node = VoiceActivityDetector(
        frame_duration_ms=30,
        energy_threshold=0.02,
        speech_threshold=0.3,
        filter_mode=False,  # Passthrough mode
        include_metadata=True,
        name="VAD"
    )
    vad_node.is_streaming = True
    pipeline.add_node(vad_node)

    # Log VAD statistics
    pipeline.add_node(VADStatsNode(name="VADStats"))

    # Buffer audio (required for Ultravox)
    buffer_node = AudioBuffer(
        buffer_size_samples=16000,  # 1 second buffer at 16kHz
        name="AudioBuffer"
    )
    buffer_node.is_streaming = True
    pipeline.add_node(buffer_node)

    # Configure remote execution
    remote_config = RemoteExecutorConfig(host=REMOTE_HOST, port=50052, ssl_enabled=False)
    
    # Create Ultravox instance
    ultravox_instance = UltravoxNode(
        model_id="fixie-ai/ultravox-v0_5-llama-3_1-8b",
        system_prompt=(
            "You are a helpful assistant. When you hear speech, respond appropriately. "
            "If someone greets you, greet them back. If they ask a question, answer it. "
            "Keep your responses concise and friendly."
        ),
        buffer_duration_s=1.0,
        name="UltravoxNode"
    )

    # Execute Ultravox remotely
    remote_node = RemoteObjectExecutionNode(
        obj_to_execute=ultravox_instance,
        remote_config=remote_config,
        name="RemoteUltravox",
        node_config={
            'streaming': True,
            'buffer_size': 16000
        }
    )
    remote_node.is_streaming = True
    pipeline.add_node(remote_node)

    # Print responses
    pipeline.add_node(PrintNode(name="PrintNode"))

    logger.info("Starting pipeline with VAD-filtered audio...")
    async with pipeline.managed_execution():
        try:
            logger.info("Pipeline execution started, processing audio with VAD...")
            async for result in pipeline.process():
                logger.debug(f"Pipeline produced result: {result}")
            logger.info("Pipeline completed successfully.")
        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            raise

    logger.info("Remote Ultravox pipeline with VAD finished.")


# Alternative configuration using VAD in filter mode
async def main_filter_mode():
    """
    Alternative pipeline using VAD in filter mode to only send speech to Ultravox.
    """
    REMOTE_HOST = os.environ.get("REMOTE_HOST", "127.0.0.1")
    logger.info("--- Running Remote Ultravox with VAD Filter Mode ---")

    demo_audio_path = "examples/vad_demo.wav"
    await create_demo_audio_with_silence(demo_audio_path)

    pipeline = Pipeline()

    # Source nodes
    pipeline.add_node(MediaReaderNode(path=demo_audio_path, chunk_size=4096))
    pipeline.add_node(AudioTrackSource())
    pipeline.add_node(AudioTransform(output_sample_rate=16000, output_channels=1))

    # VAD in filter mode - only passes speech segments
    vad_node = VoiceActivityDetector(
        frame_duration_ms=30,
        energy_threshold=0.02,
        speech_threshold=0.3,
        filter_mode=True,  # Only output speech
        name="VADFilter"
    )
    vad_node.is_streaming = True
    pipeline.add_node(vad_node)

    # Buffer and remote execution
    buffer_node = AudioBuffer(buffer_size_samples=16000)
    buffer_node.is_streaming = True
    pipeline.add_node(buffer_node)

    remote_config = RemoteExecutorConfig(host=REMOTE_HOST, port=50052, ssl_enabled=False)
    
    ultravox_instance = UltravoxNode(
        model_id="fixie-ai/ultravox-v0_5-llama-3_1-8b",
        system_prompt="You are a helpful assistant. Respond to what you hear.",
        buffer_duration_s=1.0
    )

    remote_node = RemoteObjectExecutionNode(
        obj_to_execute=ultravox_instance,
        remote_config=remote_config,
        node_config={'streaming': True, 'buffer_size': 16000}
    )
    remote_node.is_streaming = True
    pipeline.add_node(remote_node)

    pipeline.add_node(PrintNode())

    logger.info("Starting pipeline with VAD filter (only speech sent to Ultravox)...")
    async with pipeline.managed_execution():
        try:
            async for result in pipeline.process():
                pass
            logger.info("Pipeline completed.")
        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            raise


if __name__ == "__main__":
    # Choose which mode to run
    mode = os.environ.get("VAD_MODE", "passthrough")
    
    try:
        if mode == "filter":
            asyncio.run(main_filter_mode())
        else:
            asyncio.run(main())
    except Exception as e:
        logging.error(f"An error occurred: {e}", exc_info=True)
        logging.error("Please ensure the remote server is running and has the ML dependencies installed.")