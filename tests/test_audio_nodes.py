import pytest
import numpy as np

from remotemedia.nodes.audio import AudioTransform, AudioBuffer


@pytest.fixture
def mono_audio_data():
    """Fixture for single-channel (mono) audio data."""
    sample_rate = 44100
    duration_s = 1
    # (channels, samples)
    audio = np.random.uniform(-1, 1, (1, sample_rate * duration_s)).astype(np.float32)
    return audio, sample_rate


@pytest.fixture
def stereo_audio_data():
    """Fixture for two-channel (stereo) audio data."""
    sample_rate = 48000
    duration_s = 1
    # (channels, samples)
    audio = np.random.uniform(-1, 1, (2, sample_rate * duration_s)).astype(np.float32)
    return audio, sample_rate


class TestAudioTransform:
    """Tests for the AudioTransform node."""

    def test_mono_to_mono_no_change(self, mono_audio_data):
        """Test that mono audio passes through unchanged when output is mono."""
        audio_data, sample_rate = mono_audio_data
        node = AudioTransform(output_sample_rate=sample_rate, output_channels=1)

        processed_audio, processed_rate = node.process((audio_data, sample_rate))

        assert processed_rate == sample_rate
        assert processed_audio.shape[0] == 1
        assert np.array_equal(processed_audio, audio_data)

    def test_stereo_to_stereo_no_change(self, stereo_audio_data):
        """Test that stereo audio passes through unchanged when output is stereo."""
        audio_data, sample_rate = stereo_audio_data
        node = AudioTransform(output_sample_rate=sample_rate, output_channels=2)

        processed_audio, processed_rate = node.process((audio_data, sample_rate))

        assert processed_rate == sample_rate
        assert processed_audio.shape[0] == 2
        assert np.array_equal(processed_audio, audio_data)

    def test_stereo_to_mono_downmix(self, stereo_audio_data):
        """Test downmixing from stereo to mono."""
        audio_data, sample_rate = stereo_audio_data
        node = AudioTransform(output_sample_rate=sample_rate, output_channels=1)

        processed_audio, processed_rate = node.process((audio_data, sample_rate))

        assert processed_rate == sample_rate
        assert processed_audio.ndim == 2
        assert processed_audio.shape[0] == 1  # Should be mono
        assert processed_audio.shape[1] == audio_data.shape[1]

    def test_mono_to_stereo_upmix(self, mono_audio_data):
        """Test upmixing from mono to stereo."""
        audio_data, sample_rate = mono_audio_data
        node = AudioTransform(output_sample_rate=sample_rate, output_channels=2)

        processed_audio, processed_rate = node.process((audio_data, sample_rate))

        assert processed_rate == sample_rate
        assert processed_audio.shape[0] == 2  # Should be stereo
        assert processed_audio.shape[1] == audio_data.shape[1]
        # Check that the two channels are identical
        assert np.array_equal(processed_audio[0, :], processed_audio[1, :])
        assert np.array_equal(processed_audio[0, :], audio_data[0, :])

    def test_resampling_and_channel_conversion(self, stereo_audio_data):
        """Test simultaneous resampling and channel conversion."""
        audio_data, input_rate = stereo_audio_data  # 48000Hz, 2 channels
        output_rate = 22050
        node = AudioTransform(output_sample_rate=output_rate, output_channels=1)

        processed_audio, processed_rate = node.process((audio_data, input_rate))

        assert processed_rate == output_rate
        assert processed_audio.shape[0] == 1  # Mono
        # The number of samples should change according to the sample rate ratio
        expected_samples = audio_data.shape[1] * (output_rate / input_rate)
        assert abs(processed_audio.shape[1] - expected_samples) < 2

    def test_invalid_input_format(self, caplog):
        """Test that the node handles improperly formatted input data."""
        node = AudioTransform()
        invalid_data = np.random.rand(1024)  # Not a tuple
        result = node.process(invalid_data)

        assert result is invalid_data
        assert "received data in unexpected format" in caplog.text

    def test_input_not_numpy_array(self, caplog):
        """Test handling when audio data is not a numpy array."""
        node = AudioTransform()
        invalid_data = ([1, 2, 3], 44100)  # list instead of np.ndarray
        result = node.process(invalid_data)

        assert result is invalid_data
        assert "audio data is not a numpy array" in caplog.text

    def test_1d_mono_input_handling(self):
        """Test that a 1D numpy array is correctly handled as mono."""
        sample_rate = 44100
        # 1D array
        audio_data = np.random.uniform(-1, 1, sample_rate).astype(np.float32)
        node = AudioTransform(output_sample_rate=sample_rate, output_channels=2)

        processed_audio, _ = node.process((audio_data, sample_rate))

        assert processed_audio.shape[0] == 2
        assert processed_audio.shape[1] == sample_rate


class TestAudioBuffer:
    """Tests for the AudioBuffer node."""

    def test_basic_buffering(self):
        """Test that the buffer accumulates data and outputs a chunk when full."""
        buffer_size = 1024
        node = AudioBuffer(buffer_size_samples=buffer_size)
        sample_rate = 44100
        chunk_size = 512
        
        # First chunk, should not trigger output
        chunk1 = np.zeros((1, chunk_size), dtype=np.float32)
        assert node.process((chunk1, sample_rate)) is None

        # Second chunk, should fill the buffer and trigger an output
        chunk2 = np.ones((1, chunk_size), dtype=np.float32)
        result = node.process((chunk2, sample_rate))
        assert result is not None
        
        output_audio, output_rate = result
        assert output_audio.shape == (1, buffer_size)
        assert output_rate == sample_rate
        # Verify that the output is the concatenation of the first two chunks
        assert np.array_equal(output_audio[:, :chunk_size], chunk1)
        assert np.array_equal(output_audio[:, chunk_size:], chunk2)

    def test_buffer_leftovers(self):
        """Test that leftover samples are kept in the buffer."""
        buffer_size = 1024
        node = AudioBuffer(buffer_size_samples=buffer_size)
        sample_rate = 44100

        # Send a chunk larger than the buffer size
        large_chunk = np.zeros((1, buffer_size + 200), dtype=np.float32)
        result = node.process((large_chunk, sample_rate))
        
        assert result is not None
        assert result[0].shape == (1, buffer_size)
        # Check internal buffer state (not ideal, but useful for this test)
        assert node._buffer.shape == (1, 200)

        # Send another chunk that's more than enough to fill the buffer again
        next_chunk = np.ones((1, 900), dtype=np.float32)
        result2 = node.process((next_chunk, sample_rate))

        # The buffer had 200, we added 900. Total 1100.
        # It should output one chunk of 1024.
        assert result2 is not None
        assert result2[0].shape == (1, buffer_size)

        # The buffer should have 1100 - 1024 = 76 samples left.
        assert node._buffer.shape == (1, 76)

    def test_multiple_outputs_from_large_chunk(self):
        """Test that a very large input chunk produces multiple output chunks."""
        buffer_size = 1024
        node = AudioBuffer(buffer_size_samples=buffer_size)
        sample_rate = 44100

        # Send a chunk that is 2.5x the buffer size
        large_chunk = np.zeros((1, buffer_size * 2 + 512), dtype=np.float32)
        
        # The current implementation's process method can only return one chunk at a time.
        # So we process the large chunk, and then process empty chunks to get the rest.
        
        result1 = node.process((large_chunk, sample_rate))
        assert result1 is not None
        assert result1[0].shape == (1, buffer_size)
        assert node._buffer.shape == (1, buffer_size + 512)

        # Process an empty chunk to get the next buffered chunk
        result2 = node.process((np.zeros((1, 0)), sample_rate))
        assert result2 is not None
        assert result2[0].shape == (1, buffer_size)
        assert node._buffer.shape == (1, 512)

        # Process another empty chunk; no more full chunks are available
        result3 = node.process((np.zeros((1, 0)), sample_rate))
        assert result3 is None
        assert node._buffer.shape == (1, 512)

    def test_flush_buffer(self):
        """Test the flush method."""
        node = AudioBuffer(buffer_size_samples=1024)
        sample_rate = 44100
        
        # Buffer some data
        node.process((np.zeros((1, 500)), sample_rate))
        
        # Flush the buffer
        result = node.flush()
        assert result is not None
        output_audio, output_rate = result
        assert output_audio.shape == (1, 500)
        assert output_rate == sample_rate
        
        # Buffer should be empty after flush
        assert node.flush() is None
        assert node._buffer.shape == (1, 0)

    def test_empty_flush(self):
        """Test flushing an empty buffer."""
        node = AudioBuffer(buffer_size_samples=1024)
        assert node.flush() is None

    def test_format_change_reset(self, caplog):
        """Test that a change in sample rate or channels flushes and resets."""
        node = AudioBuffer(buffer_size_samples=1024)
        sample_rate1 = 44100
        sample_rate2 = 22050

        # Initial data
        node.process((np.zeros((1, 500)), sample_rate1))
        
        # Data with different sample rate
        chunk2 = np.ones((1, 200), dtype=np.float32)
        result = node.process((chunk2, sample_rate2))
        
        # Should have flushed the first 500 samples
        assert "Audio format changed mid-stream" in caplog.text
        assert result is not None
        assert result[0].shape == (1, 500)
        assert result[1] == sample_rate1
        
        # The new chunk should now be in the buffer
        assert node._buffer.shape == (1, 200)
        assert node._sample_rate == sample_rate2

        # Data with different channel count
        chunk3 = np.ones((2, 300), dtype=np.float32)
        result2 = node.process((chunk3, sample_rate2))

        # Should have flushed the 200 samples
        assert result2[0].shape == (1, 200)
        assert node._buffer.shape == (2, 300)
        assert node._channels == 2 