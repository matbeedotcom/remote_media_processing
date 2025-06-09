import pytest
import numpy as np

# PyAV is an optional dependency, so we skip these tests if it's not installed.
try:
    from av import AudioFrame, VideoFrame
    from av.frame import Frame
except ImportError:
    pytest.skip("PyAV not installed, skipping source node tests", allow_module_level=True)

from remotemedia.nodes.source import AudioTrackSource, VideoTrackSource, TrackSource


@pytest.fixture
def audio_frame() -> AudioFrame:
    """Fixture to create a mock AudioFrame for testing."""
    frame = AudioFrame(format='s16', layout='mono', samples=1024)
    frame.pts = 0
    frame.sample_rate = 48000
    # Create dummy data and load it into the frame
    data = (np.sin(2 * np.pi * 440 * np.arange(1024) / 48000)).astype(np.float32)
    data_s16 = (data * 32767).astype(np.int16)
    frame.planes[0].update(data_s16.tobytes())
    return frame


@pytest.fixture
def video_frame() -> VideoFrame:
    """Fixture to create a mock VideoFrame for testing."""
    width, height = 640, 480
    frame = VideoFrame(width=width, height=height, format='bgr24')
    frame.pts = 0
    # Create dummy data and load it into the frame
    data = np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)
    frame.planes[0].update(data.tobytes())
    return frame


def test_track_source_base_class_non_frame_input():
    """Verify TrackSource base class handles non-frame input correctly."""
    node = TrackSource(name="base_track_source")
    # The process method should return None for invalid input type
    assert node.process("this is not an AV frame") is None


def test_track_source_base_class_not_implemented():
    """Verify that calling process on the base class with a frame raises NotImplementedError."""
    node = TrackSource(name="base_track_source")
    # Using a generic Frame object for the test
    with pytest.raises(NotImplementedError):
        node.process(Frame())


class TestAudioTrackSource:
    """Tests for the AudioTrackSource node."""

    def test_process_valid_audio_frame(self, audio_frame):
        """Test processing of a valid AudioFrame."""
        node = AudioTrackSource(name="audio_source")
        result = node.process(audio_frame)

        assert isinstance(result, tuple)
        audio_data, sample_rate = result

        assert isinstance(audio_data, np.ndarray)
        assert audio_data.shape == (1, 1024)  # (channels, samples)
        assert audio_data.dtype == np.int16
        assert sample_rate == 48000

    def test_process_invalid_input(self):
        """Test that non-frame input is handled gracefully."""
        node = AudioTrackSource(name="audio_source")
        assert node.process(b"some_random_bytes") is None

    def test_stereo_audio_frame_conversion(self):
        """Test conversion of a stereo audio frame."""
        node = AudioTrackSource(name="stereo_audio_source")
        stereo_frame = AudioFrame(format='s16', layout='stereo', samples=512)
        stereo_frame.sample_rate = 44100
        # Create dummy stereo data and load it
        stereo_data = np.random.randint(-32767, 32767, size=(2, 512), dtype=np.int16)
        stereo_frame.planes[0].update(stereo_data.tobytes())

        audio_data, sample_rate = node.process(stereo_frame)

        # The to_ndarray() method for interleaved stereo audio returns a 1D array.
        # We need to reshape it to (channels, samples) and then compare.
        reshaped_audio_data = audio_data.reshape((2, 512))

        assert reshaped_audio_data.shape == (2, 512)
        assert sample_rate == 44100
        assert np.array_equal(reshaped_audio_data, stereo_data)


class TestVideoTrackSource:
    """Tests for the VideoTrackSource node."""

    def test_process_valid_video_frame(self, video_frame):
        """Test processing of a valid VideoFrame."""
        node = VideoTrackSource(name="video_source")
        video_data = node.process(video_frame)

        assert isinstance(video_data, np.ndarray)
        assert video_data.shape == (480, 640, 3)  # (height, width, planes)
        assert video_data.dtype == np.uint8

    def test_process_invalid_input(self):
        """Test that non-frame input is handled gracefully."""
        node = VideoTrackSource(name="video_source")
        assert node.process({"not": "a frame"}) is None

    def test_output_format_conversion(self, video_frame):
        """Test conversion to a different output format."""
        node = VideoTrackSource(name="video_source_rgb", output_format="rgb24")
        video_data = node.process(video_frame)

        assert isinstance(video_data, np.ndarray)
        assert video_data.shape == (480, 640, 3)

    def test_different_resolution_video_frame(self):
        """Test with a video frame of a different resolution."""
        node = VideoTrackSource(name="video_source_hd")
        width, height = 1920, 1080
        hd_frame = VideoFrame(width=width, height=height, format='bgr24')
        data = np.zeros((height, width, 3), dtype=np.uint8)
        hd_frame.planes[0].update(data.tobytes())

        video_data = node.process(hd_frame)
        assert video_data.shape == (1080, 1920, 3) 