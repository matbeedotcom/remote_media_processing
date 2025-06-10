import pytest
import asyncio
import numpy as np

from remotemedia.core.pipeline import Pipeline
from remotemedia.core.node import Node, RemoteExecutorConfig
from remotemedia.nodes.remote import RemoteObjectExecutionNode


# This class will be cloudpickled and sent to the server.
# It does NOT need to be in the server's known SDK nodes.
class AudioEchoEffect(Node):
    """A custom audio effect that adds a simple echo."""
    def __init__(self, sample_rate=44100, delay_s=0.2, decay=0.5, **kwargs):
        super().__init__(**kwargs)
        self.is_streaming = True
        self.sample_rate = sample_rate
        self.delay_samples = int(delay_s * self.sample_rate)
        self.decay = decay
        self.delay_buffer = np.zeros((1, self.delay_samples), dtype=np.float32)

    async def initialize(self):
        pass

    async def cleanup(self):
        pass

    async def process(self, data_stream):
        async for chunk, _ in data_stream:
            if chunk.ndim == 1:
                chunk = chunk.reshape(1, -1)
            output_chunk = np.zeros_like(chunk)
            for i in range(chunk.shape[1]):
                delayed_sample = self.delay_buffer[0, 0]
                output_chunk[0, i] = chunk[0, i] + delayed_sample * self.decay
                self.delay_buffer[0, :-1] = self.delay_buffer[0, 1:]
                self.delay_buffer[0, -1] = chunk[0, i]
            yield (output_chunk,)


async def generate_sine_wave(duration_s=1, sample_rate=44100, chunk_size=1024):
    """Generate a stream of sine wave audio chunks."""
    total_samples = duration_s * sample_rate
    num_chunks = total_samples // chunk_size
    
    for i in range(num_chunks):
        start_sample = i * chunk_size
        time_vector = np.arange(start_sample, start_sample + chunk_size) / sample_rate
        audio_chunk = np.sin(2 * np.pi * 440 * time_vector, dtype=np.float32).reshape(1, -1)
        yield (audio_chunk, sample_rate)
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_remote_object_audio_pipeline(grpc_server):
    """
    Tests a full pipeline that streams audio to a remote, dynamically-defined
    object for processing.
    """
    # 1. Configuration
    remote_config = RemoteExecutorConfig(host="127.0.0.1", port=50052, ssl_enabled=False)
    
    # This object is defined locally and will be sent to the server.
    audio_effect = AudioEchoEffect(
        sample_rate=44100, 
        delay_s=0.1, 
        decay=0.5
    )

    # 2. Setup the pipeline
    pipeline = Pipeline(name="RemoteAudioEchoTestPipeline")
    pipeline.add_node(
        RemoteObjectExecutionNode(
            obj_to_execute=audio_effect,
            remote_config=remote_config
        )
    )

    # 3. Process the stream
    sample_rate = 44100
    duration_s = 1
    chunk_size = 1024
    input_stream = generate_sine_wave(
        duration_s=duration_s, 
        sample_rate=sample_rate, 
        chunk_size=chunk_size
    )
    
    output_chunks = []
    async with pipeline.managed_execution():
        async for result in pipeline.process(input_stream):
            output_chunks.append(result[0])
            
    # 4. Verify the output
    assert output_chunks, "Pipeline should have produced output"
    
    total_input_samples = (duration_s * sample_rate // chunk_size) * chunk_size
    output_samples = sum(chunk.shape[1] for chunk in output_chunks)
    
    assert total_input_samples == output_samples, "Input and output sample counts should match"
    
    first_chunk = output_chunks[0]
    assert first_chunk.shape[0] == 1, "Output should have 1 channel"
    assert first_chunk.dtype == np.float32, "Output data type should be float32" 