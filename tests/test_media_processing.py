import pytest
import asyncio
from pathlib import Path
import av
import logging

from remotemedia import Pipeline
from remotemedia.nodes import PassThroughNode
from remotemedia.core.node import Node

# Force logging to be visible in pytest
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


class DummyMediaSourceNode(Node):
    """A test source node that generates a finite stream of dummy frames."""
    def __init__(self, audio_frames=10, video_frames=10):
        super().__init__(name="DummySource")
        self.audio_frames_to_generate = audio_frames
        self.video_frames_to_generate = video_frames

    def process(self, data=None):
        return self.stream()

    async def stream(self):
        """Yields a stream of mixed audio and video frames."""
        audio_counter = 0
        video_counter = 0

        while (audio_counter < self.audio_frames_to_generate or 
               video_counter < self.video_frames_to_generate):
            
            if video_counter < self.video_frames_to_generate:
                frame = av.VideoFrame(640, 480, 'yuv420p')
                for plane in frame.planes:
                    plane.update(b'\x00' * plane.buffer_size)
                yield {'video': frame}
                video_counter += 1

            if audio_counter < self.audio_frames_to_generate:
                frame = av.AudioFrame(format='s16', layout='stereo', samples=1024)
                for plane in frame.planes:
                    plane.update(b'\x00' * plane.buffer_size)
                yield {'audio': frame}
                audio_counter += 1
            
            await asyncio.sleep(0.01) # simulate frame interval


@pytest.mark.asyncio
async def test_process_dummy_source(caplog):
    """
    Test processing an in-memory dummy media source.
    """
    caplog.set_level(logging.DEBUG)
    
    num_frames = 25
    pipeline = Pipeline(name="DummySourceTest")
    pipeline.add_node(DummyMediaSourceNode(audio_frames=num_frames, video_frames=num_frames))
    pipeline.add_node(PassThroughNode())
    
    processed_audio = 0
    processed_video = 0

    async with pipeline.managed_execution():
        async for result in pipeline.process():
            if 'audio' in result:
                processed_audio += 1
            if 'video' in result:
                processed_video += 1

    assert processed_audio == num_frames
    assert processed_video == num_frames 