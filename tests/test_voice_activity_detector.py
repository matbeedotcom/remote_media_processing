"""
Tests for the VoiceActivityDetector node.
"""

import pytest
import numpy as np
import asyncio
from remotemedia.nodes.audio import VoiceActivityDetector


def create_audio_with_speech(
    sample_rate: int = 16000,
    duration_s: float = 1.0,
    speech_segments: list = None
) -> np.ndarray:
    """
    Create synthetic audio with speech and silence segments.
    
    Args:
        sample_rate: Audio sample rate
        duration_s: Total duration in seconds
        speech_segments: List of (start, end) tuples for speech segments in seconds
        
    Returns:
        Audio array with shape (1, samples)
    """
    samples = int(sample_rate * duration_s)
    audio = np.zeros(samples)
    
    if speech_segments is None:
        speech_segments = [(0.2, 0.8)]  # Default: speech from 0.2s to 0.8s
    
    # Add speech segments (sine waves with higher amplitude)
    for start, end in speech_segments:
        start_sample = int(start * sample_rate)
        end_sample = int(end * sample_rate)
        t = np.linspace(0, end - start, end_sample - start_sample)
        # Speech: 440Hz sine wave with amplitude 0.3
        audio[start_sample:end_sample] = 0.3 * np.sin(2 * np.pi * 440 * t)
    
    # Add background noise
    noise = np.random.normal(0, 0.01, samples)
    audio += noise
    
    return audio.reshape(1, -1)


async def async_generator_from_list(items):
    """Helper to create async generator from list."""
    for item in items:
        yield item


@pytest.mark.asyncio
async def test_vad_basic_functionality():
    """Test basic VAD functionality with synthetic audio."""
    vad = VoiceActivityDetector(
        frame_duration_ms=30,
        energy_threshold=0.02,
        speech_threshold=0.3,
        filter_mode=False,
        include_metadata=True
    )
    
    # Create audio with speech in the middle
    audio = create_audio_with_speech(
        sample_rate=16000,
        duration_s=1.0,
        speech_segments=[(0.3, 0.7)]
    )
    
    # Create input stream
    input_data = [(audio, 16000)]
    stream = async_generator_from_list(input_data)
    
    # Process through VAD
    results = []
    async for result in vad.process(stream):
        results.append(result)
    
    assert len(results) == 1
    
    # Check output format
    ((output_audio, output_rate), metadata) = results[0]
    assert np.array_equal(output_audio, audio)
    assert output_rate == 16000
    assert "is_speech" in metadata
    assert "speech_ratio" in metadata
    assert "avg_energy" in metadata


@pytest.mark.asyncio
async def test_vad_filter_mode():
    """Test VAD in filter mode - only outputs speech segments."""
    vad = VoiceActivityDetector(
        frame_duration_ms=30,
        energy_threshold=0.02,
        speech_threshold=0.3,
        filter_mode=True
    )
    
    # Create multiple audio chunks - some with speech, some without
    chunks = [
        # Silence
        (create_audio_with_speech(16000, 0.5, []), 16000),
        # Speech
        (create_audio_with_speech(16000, 0.5, [(0.1, 0.4)]), 16000),
        # Silence
        (create_audio_with_speech(16000, 0.5, []), 16000),
        # Speech
        (create_audio_with_speech(16000, 0.5, [(0.0, 0.5)]), 16000),
    ]
    
    stream = async_generator_from_list(chunks)
    
    # Process through VAD
    results = []
    async for result in vad.process(stream):
        results.append(result)
    
    # In filter mode, should only get speech chunks (2 out of 4)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_vad_adaptive_threshold():
    """Test that VAD adapts to changing noise levels."""
    vad = VoiceActivityDetector(
        frame_duration_ms=30,
        energy_threshold=0.02,
        speech_threshold=0.3,
        filter_mode=False,
        include_metadata=True
    )
    
    # Create audio chunks with increasing noise floor
    chunks = []
    for i in range(5):
        noise_level = 0.01 * (i + 1)  # Increasing noise
        samples = int(16000 * 0.5)
        audio = np.random.normal(0, noise_level, samples)
        
        # Add speech with constant relative amplitude
        speech_start = int(0.1 * 16000)
        speech_end = int(0.4 * 16000)
        t = np.linspace(0, 0.3, speech_end - speech_start)
        audio[speech_start:speech_end] += 0.3 * np.sin(2 * np.pi * 440 * t)
        
        chunks.append((audio.reshape(1, -1), 16000))
    
    stream = async_generator_from_list(chunks)
    
    # Process all chunks
    results = []
    async for result in vad.process(stream):
        results.append(result)
    
    # All chunks should be processed
    assert len(results) == 5
    
    # Extract metadata
    metadata_list = [result[1] for result in results]
    
    # Despite increasing noise, speech should still be detected
    # due to adaptive thresholding
    speech_detected = [m["is_speech"] for m in metadata_list]
    assert sum(speech_detected) >= 3  # At least 3 out of 5 should detect speech


@pytest.mark.asyncio
async def test_vad_multichannel_audio():
    """Test VAD with multi-channel audio."""
    vad = VoiceActivityDetector(
        frame_duration_ms=30,
        filter_mode=False,
        include_metadata=True
    )
    
    # Create stereo audio with speech
    mono_audio = create_audio_with_speech(16000, 1.0, [(0.2, 0.8)])
    stereo_audio = np.vstack([mono_audio, mono_audio * 0.8])  # Slightly different channels
    
    input_data = [(stereo_audio, 16000)]
    stream = async_generator_from_list(input_data)
    
    results = []
    async for result in vad.process(stream):
        results.append(result)
    
    assert len(results) == 1
    
    # Output should preserve channel count
    ((output_audio, output_rate), metadata) = results[0]
    assert output_audio.shape[0] == 2  # Stereo preserved
    assert metadata["is_speech"] is True


@pytest.mark.asyncio
async def test_vad_edge_cases():
    """Test VAD with edge cases."""
    vad = VoiceActivityDetector()
    
    # Test with empty stream
    empty_stream = async_generator_from_list([])
    results = []
    async for result in vad.process(empty_stream):
        results.append(result)
    assert len(results) == 0
    
    # Test with invalid data format
    invalid_data = [
        "not a tuple",
        (np.array([1, 2, 3]),),  # Missing sample rate
        (None, 16000),  # Invalid audio data
    ]
    
    stream = async_generator_from_list(invalid_data)
    results = []
    async for result in vad.process(stream):
        results.append(result)
    
    # Should skip invalid data
    assert len(results) == 0


@pytest.mark.asyncio
async def test_vad_streaming_behavior():
    """Test that VAD properly handles streaming data."""
    vad = VoiceActivityDetector(
        frame_duration_ms=30,
        filter_mode=True
    )
    
    # Simulate streaming with small chunks
    sample_rate = 16000
    chunk_duration = 0.1  # 100ms chunks
    
    chunks = []
    for i in range(10):
        t_start = i * chunk_duration
        t_end = (i + 1) * chunk_duration
        
        # Add speech to chunks 3-6 (0.3s to 0.7s)
        if 3 <= i <= 6:
            audio = create_audio_with_speech(
                sample_rate, 
                chunk_duration,
                [(0, chunk_duration)]  # Full chunk is speech
            )
        else:
            audio = create_audio_with_speech(
                sample_rate,
                chunk_duration,
                []  # No speech
            )
        
        chunks.append((audio, sample_rate))
    
    stream = async_generator_from_list(chunks)
    
    # Process stream
    results = []
    async for result in vad.process(stream):
        results.append(result)
    
    # Should get approximately 4 chunks with speech
    assert 3 <= len(results) <= 5  # Some tolerance for edge detection


if __name__ == "__main__":
    asyncio.run(test_vad_basic_functionality())
    print("All tests passed!")