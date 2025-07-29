#!/usr/bin/env python3
"""
Test VAD with a simple remote execution to debug the data flow.
"""

import asyncio
import logging
import numpy as np
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from remotemedia.core.pipeline import Pipeline
from remotemedia.core.node import RemoteExecutorConfig, Node
from remotemedia.nodes.source import MediaReaderNode, AudioTrackSource
from remotemedia.nodes.audio import AudioTransform, AudioBuffer, VoiceActivityDetector
from remotemedia.nodes.remote import RemoteObjectExecutionNode
from remotemedia.nodes import PassThroughNode

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Reduce noise from pipeline
logging.getLogger("Pipeline").setLevel(logging.INFO)


class AudioLogger(Node):
    """Simple node that logs audio data it receives."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.is_streaming = True
        self.chunk_count = 0
        
    async def process(self, data_stream):
        """Log audio chunks."""
        logger.info(f"{self.name}: Starting to process stream")
        
        async for data in data_stream:
            self.chunk_count += 1
            
            if isinstance(data, tuple) and len(data) == 2:
                audio, rate = data
                if isinstance(audio, np.ndarray):
                    logger.info(f"{self.name}: Chunk {self.chunk_count} - audio shape: {audio.shape}, rate: {rate}")
                else:
                    logger.warning(f"{self.name}: Chunk {self.chunk_count} - unexpected audio type: {type(audio)}")
            else:
                logger.warning(f"{self.name}: Chunk {self.chunk_count} - unexpected data format: {type(data)}")
            
            yield data
        
        logger.info(f"{self.name}: Finished processing {self.chunk_count} chunks")


async def test_without_vad():
    """Test pipeline without VAD to establish baseline."""
    logger.info("\n=== Testing Pipeline WITHOUT VAD ===\n")
    
    pipeline = Pipeline()
    
    # Add nodes
    pipeline.add_node(MediaReaderNode(
        path="examples/transcribe_demo.wav",
        chunk_size=4096,
        name="MediaReader"
    ))
    
    pipeline.add_node(AudioTrackSource(name="AudioTrackSource"))
    
    pipeline.add_node(AudioTransform(
        output_sample_rate=16000,
        output_channels=1,
        name="AudioTransform"
    ))
    
    pipeline.add_node(AudioLogger(name="AudioLogger1"))
    
    buffer_node = AudioBuffer(
        buffer_size_samples=8000,  # 0.5 seconds at 16kHz
        name="AudioBuffer"
    )
    buffer_node.is_streaming = True
    pipeline.add_node(buffer_node)
    
    pipeline.add_node(AudioLogger(name="AudioLogger2"))
    
    # Run pipeline
    async with pipeline.managed_execution():
        chunk_count = 0
        async for result in pipeline.process():
            chunk_count += 1
            logger.debug(f"Pipeline output chunk {chunk_count}")
        logger.info(f"Pipeline produced {chunk_count} output chunks")


async def test_with_vad_passthrough():
    """Test pipeline with VAD in passthrough mode."""
    logger.info("\n=== Testing Pipeline WITH VAD (Passthrough) ===\n")
    
    pipeline = Pipeline()
    
    # Add nodes
    pipeline.add_node(MediaReaderNode(
        path="examples/transcribe_demo.wav",
        chunk_size=4096,
        name="MediaReader"
    ))
    
    pipeline.add_node(AudioTrackSource(name="AudioTrackSource"))
    
    pipeline.add_node(AudioTransform(
        output_sample_rate=16000,
        output_channels=1,
        name="AudioTransform"
    ))
    
    pipeline.add_node(AudioLogger(name="PreVAD"))
    
    # VAD in passthrough mode
    vad = VoiceActivityDetector(
        frame_duration_ms=30,
        filter_mode=False,
        include_metadata=True,
        name="VAD"
    )
    vad.is_streaming = True
    pipeline.add_node(vad)
    
    # Custom stats node that properly handles VAD output
    class VADHandler(Node):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.is_streaming = True
            
        async def process(self, data_stream):
            async for data in data_stream:
                if isinstance(data, tuple) and len(data) == 2 and isinstance(data[1], dict):
                    # Extract audio from ((audio, rate), metadata)
                    (audio_data, metadata) = data
                    logger.info(f"VAD metadata: is_speech={metadata['is_speech']}, ratio={metadata['speech_ratio']:.2f}")
                    yield audio_data
                else:
                    yield data
    
    pipeline.add_node(VADHandler(name="VADHandler"))
    
    pipeline.add_node(AudioLogger(name="PostVAD"))
    
    buffer_node = AudioBuffer(
        buffer_size_samples=8000,
        name="AudioBuffer"
    )
    buffer_node.is_streaming = True
    pipeline.add_node(buffer_node)
    
    pipeline.add_node(AudioLogger(name="PostBuffer"))
    
    # Run pipeline
    async with pipeline.managed_execution():
        chunk_count = 0
        async for result in pipeline.process():
            chunk_count += 1
            logger.debug(f"Pipeline output chunk {chunk_count}")
        logger.info(f"Pipeline produced {chunk_count} output chunks")


async def main():
    """Run tests."""
    await test_without_vad()
    await test_with_vad_passthrough()


if __name__ == "__main__":
    asyncio.run(main())