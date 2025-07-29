#!/usr/bin/env python3
"""
Simple test of the VoiceActivityDetector node functionality.
"""

import asyncio
import numpy as np
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from remotemedia.core.pipeline import Pipeline
from remotemedia.nodes.audio import VoiceActivityDetector
from remotemedia.nodes import PassThroughNode


class AudioGenerator(PassThroughNode):
    """Generate test audio with speech and silence."""
    
    def __init__(self, duration_s=5.0, sample_rate=16000, **kwargs):
        super().__init__(**kwargs)
        self.duration_s = duration_s
        self.sample_rate = sample_rate
        self.is_streaming = True
    
    async def process(self):
        """Generate audio chunks."""
        chunk_duration = 0.5  # 500ms chunks
        chunks_count = int(self.duration_s / chunk_duration)
        
        for i in range(chunks_count):
            t_start = i * chunk_duration
            t_end = (i + 1) * chunk_duration
            
            samples = int(chunk_duration * self.sample_rate)
            t = np.linspace(0, chunk_duration, samples)
            
            if i % 2 == 1:  # Every other chunk has speech
                # Speech: 440Hz tone with amplitude 0.3
                audio = 0.3 * np.sin(2 * np.pi * 440 * t)
                print(f"Generated SPEECH chunk {i+1}/{chunks_count} ({t_start:.1f}s - {t_end:.1f}s)")
            else:
                # Silence: just noise
                audio = np.random.normal(0, 0.01, samples)
                print(f"Generated silence chunk {i+1}/{chunks_count} ({t_start:.1f}s - {t_end:.1f}s)")
            
            yield (audio.reshape(1, -1), self.sample_rate)
            await asyncio.sleep(0.1)  # Simulate real-time


class LoggerNode(PassThroughNode):
    """Log VAD results."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.is_streaming = True
        self.chunk_count = 0
    
    async def process(self, data_stream):
        """Log each chunk."""
        async for data in data_stream:
            self.chunk_count += 1
            
            if isinstance(data, tuple) and len(data) == 2 and isinstance(data[1], dict):
                # With metadata
                (audio_data, metadata) = data
                print(f"Chunk {self.chunk_count}: is_speech={metadata['is_speech']}, "
                      f"speech_ratio={metadata['speech_ratio']:.2f}, "
                      f"avg_energy={metadata['avg_energy']:.4f}")
                yield audio_data
            else:
                # Without metadata
                print(f"Chunk {self.chunk_count}: No VAD metadata")
                yield data


async def test_vad_passthrough():
    """Test VAD in passthrough mode with metadata."""
    print("\n=== Testing VAD in Passthrough Mode ===\n")
    
    pipeline = Pipeline()
    
    # Audio source
    pipeline.add_node(AudioGenerator(duration_s=5.0, name="AudioGen"))
    
    # VAD in passthrough mode
    vad = VoiceActivityDetector(
        frame_duration_ms=30,
        energy_threshold=0.02,
        speech_threshold=0.3,
        filter_mode=False,
        include_metadata=True,
        name="VAD"
    )
    vad.is_streaming = True
    pipeline.add_node(vad)
    
    # Logger
    pipeline.add_node(LoggerNode(name="Logger"))
    
    async with pipeline.managed_execution():
        async for result in pipeline.process():
            pass  # Just consume the stream
    
    print("\n✓ Passthrough test completed\n")


async def test_vad_filter():
    """Test VAD in filter mode."""
    print("\n=== Testing VAD in Filter Mode ===\n")
    
    pipeline = Pipeline()
    
    # Audio source
    pipeline.add_node(AudioGenerator(duration_s=5.0, name="AudioGen"))
    
    # VAD in filter mode
    vad = VoiceActivityDetector(
        frame_duration_ms=30,
        energy_threshold=0.02,
        speech_threshold=0.3,
        filter_mode=True,
        name="VADFilter"
    )
    vad.is_streaming = True
    pipeline.add_node(vad)
    
    # Counter node
    class CounterNode(PassThroughNode):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.is_streaming = True
            self.count = 0
        
        async def process(self, data_stream):
            async for data in data_stream:
                self.count += 1
                print(f"Received chunk {self.count} (speech detected)")
                yield data
    
    counter = CounterNode(name="Counter")
    pipeline.add_node(counter)
    
    async with pipeline.managed_execution():
        async for result in pipeline.process():
            pass
    
    print(f"\n✓ Filter test completed. Received {counter.count} speech chunks out of 10 total\n")


async def main():
    """Run all tests."""
    await test_vad_passthrough()
    await test_vad_filter()


if __name__ == "__main__":
    asyncio.run(main())