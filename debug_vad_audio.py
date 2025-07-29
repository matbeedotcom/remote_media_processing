#!/usr/bin/env python3
"""
Debug script to check what the VAD is detecting in the audio file.
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from remotemedia.core.pipeline import Pipeline
from remotemedia.nodes.source import MediaReaderNode, AudioTrackSource
from remotemedia.nodes.audio import AudioTransform, VoiceActivityDetector
from remotemedia.nodes import PassThroughNode

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class VADDebugger(PassThroughNode):
    """Debug node to analyze VAD output."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.is_streaming = True
        self.chunk_count = 0
        self.speech_chunks = 0
        self.total_samples = 0
        self.speech_samples = 0
        
    async def process(self, data_stream):
        """Log detailed VAD analysis."""
        logger.info("VADDebugger: Starting analysis...")
        
        async for data in data_stream:
            self.chunk_count += 1
            
            if isinstance(data, tuple) and len(data) == 2 and isinstance(data[1], dict):
                (audio_data, sample_rate), metadata = data
                
                is_speech = metadata.get("is_speech", False)
                speech_ratio = metadata.get("speech_ratio", 0.0)
                avg_energy = metadata.get("avg_energy", 0.0)
                
                samples = audio_data.size if hasattr(audio_data, 'size') else len(audio_data)
                duration_ms = (samples / sample_rate) * 1000
                
                self.total_samples += samples
                if is_speech:
                    self.speech_chunks += 1
                    self.speech_samples += samples
                
                logger.info(
                    f"Chunk {self.chunk_count}: "
                    f"SPEECH={is_speech}, "
                    f"ratio={speech_ratio:.2f}, "
                    f"energy={avg_energy:.4f}, "
                    f"duration={duration_ms:.0f}ms, "
                    f"samples={samples}"
                )
                
                yield data
            else:
                logger.warning(f"Chunk {self.chunk_count}: Unexpected format {type(data)}")
                yield data
        
        total_duration_s = self.total_samples / 16000
        speech_duration_s = self.speech_samples / 16000
        
        logger.info("=== VAD ANALYSIS SUMMARY ===")
        logger.info(f"Total chunks: {self.chunk_count}")
        logger.info(f"Speech chunks: {self.speech_chunks} ({100*self.speech_chunks/max(self.chunk_count,1):.1f}%)")
        logger.info(f"Total duration: {total_duration_s:.2f}s")
        logger.info(f"Speech duration: {speech_duration_s:.2f}s ({100*speech_duration_s/max(total_duration_s,1):.1f}%)")


async def main():
    """Debug VAD detection on the audio file."""
    logger.info("=== Debugging VAD Detection ===")
    
    pipeline = Pipeline()
    
    # Source
    pipeline.add_node(MediaReaderNode(
        path="examples/transcribe_demo.wav",
        chunk_size=4096,
        name="MediaReader"
    ))
    
    pipeline.add_node(AudioTrackSource(name="AudioTrackSource"))
    
    # Transform to 16kHz
    pipeline.add_node(AudioTransform(
        output_sample_rate=16000,
        output_channels=1,
        name="AudioTransform"
    ))
    
    # VAD with more sensitive settings
    vad = VoiceActivityDetector(
        frame_duration_ms=30,
        energy_threshold=0.01,  # More sensitive
        speech_threshold=0.2,   # Lower ratio needed
        filter_mode=False,
        include_metadata=True,
        name="VAD"
    )
    vad.is_streaming = True
    pipeline.add_node(vad)
    
    # Debug analyzer
    pipeline.add_node(VADDebugger(name="VADDebugger"))
    
    async with pipeline.managed_execution():
        chunk_count = 0
        async for result in pipeline.process():
            chunk_count += 1
        logger.info(f"Pipeline processed {chunk_count} final chunks")


if __name__ == "__main__":
    asyncio.run(main())