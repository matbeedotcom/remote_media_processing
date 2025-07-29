import asyncio
import numpy as np
import pytest
import soundfile as sf
import av

from remotemedia.core.pipeline import Pipeline
from remotemedia.nodes.sink import MediaWriterNode
from remotemedia.nodes.source import MediaReaderNode

pytestmark = pytest.mark.asyncio


async def create_dummy_audio(path, duration=1, sample_rate=48000):
    """Creates a dummy WAV file with a sine wave."""
    t = np.linspace(0.0, float(duration), int(sample_rate * duration), endpoint=False)
    amplitude = np.iinfo(np.int16).max * 0.5
    data = (amplitude * np.sin(2.0 * np.pi * 440.0 * t)).astype(np.int16)
    await asyncio.to_thread(sf.write, path, data, sample_rate)


async def create_dummy_video(path, width=320, height=240, duration=1, rate=30):
    """Creates a dummy MP4 video file."""

    def _create():
        with av.open(path, mode="w") as container:
            stream = container.add_stream("libx264", rate=rate)
            stream.width = width
            stream.height = height
            stream.pix_fmt = "yuv420p"

            for i in range(duration * rate):
                img = np.full((height, width, 3), (i * 5, i * 2, i * 3), dtype=np.uint8)
                frame = av.VideoFrame.from_ndarray(img, format="rgb24")
                for packet in stream.encode(frame):
                    container.mux(packet)

            for packet in stream.encode():
                container.mux(packet)

    await asyncio.to_thread(_create)


async def test_media_writer_node_audio(tmp_path):
    """
    Tests that MediaWriterNode can correctly write an audio stream read
    from a MediaReaderNode.
    """
    input_path = tmp_path / "input.wav"
    output_path = tmp_path / "output.wav"
    sample_rate = 48000
    duration = 1

    await create_dummy_audio(input_path, duration=duration, sample_rate=sample_rate)

    reader = MediaReaderNode(path=str(input_path))
    writer = MediaWriterNode(output_path=str(output_path))

    await reader.initialize()
    await writer.initialize()

    try:
        async for frame in reader.stream():
            await writer.process(frame)
    finally:
        await reader.cleanup()
        await writer.cleanup()

    assert output_path.exists()

    with av.open(str(output_path)) as container:
        assert container is not None
        assert len(container.streams.audio) == 1
        assert len(container.streams.video) == 0

        audio_stream = container.streams.audio[0]
        assert audio_stream.rate == sample_rate
        output_duration = float(audio_stream.duration * audio_stream.time_base)
        assert output_duration == pytest.approx(duration, abs=0.1)


async def test_media_writer_node_video(tmp_path):
    """
    Tests that MediaWriterNode can correctly write a video stream.
    """
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "output.mp4"
    width, height, duration, rate = 320, 240, 1, 30

    await create_dummy_video(
        input_path, width=width, height=height, duration=duration, rate=rate
    )

    reader = MediaReaderNode(path=str(input_path))
    writer = MediaWriterNode(output_path=str(output_path))

    await reader.initialize()
    await writer.initialize()

    try:
        async for frame in reader.stream():
            await writer.process(frame)
    finally:
        await reader.cleanup()
        await writer.cleanup()

    assert output_path.exists()

    with av.open(str(output_path)) as container:
        assert len(container.streams.audio) == 0
        assert len(container.streams.video) == 1

        video_stream = container.streams.video[0]
        assert video_stream.width == width
        assert video_stream.height == height
        assert video_stream.average_rate == rate
        output_duration = float(video_stream.duration * video_stream.time_base)
        assert output_duration == pytest.approx(duration, abs=0.1) 