import pytest
import numpy as np
import asyncio

from remotemedia.core.pipeline import Pipeline
from remotemedia.core.node import RemoteExecutorConfig
from remotemedia.nodes.audio import AudioBuffer, AudioTransform
from remotemedia.nodes.remote import RemoteExecutionNode

# Helper from the local audio pipeline test
async def generate_audio_chunks(total_samples, sample_rate, chunk_sizes):
    full_audio = np.sin(2 * np.pi * 440 * np.arange(total_samples) / sample_rate, dtype=np.float32).reshape(1, -1)
    start = 0
    for chunk_size in chunk_sizes:
        end = start + chunk_size
        if end > total_samples:
            break
        yield (full_audio[:, start:end], sample_rate)
        start = end
    if start < total_samples:
        yield (full_audio[:, start:], sample_rate)


@pytest.mark.asyncio
@pytest.mark.parametrize("input_rate, output_rate, buffer_size", [
    (48000, 16000, 2048),
])
async def test_remote_audio_resampling_pipeline(input_rate, output_rate, buffer_size):
    """
    Test a pipeline with a remote node that resamples streaming audio data
    against a live, locally running server.
    """
    # 1. Setup the pipeline with the remote node
    remote_config = RemoteExecutorConfig(host='127.0.0.1', port=50052, ssl_enabled=False)
    pipeline = Pipeline()
    pipeline.add_node(AudioBuffer(buffer_size_samples=buffer_size))
    pipeline.add_node(RemoteExecutionNode(
        name="RemoteAudioTransform",
        node_to_execute="AudioTransform",
        remote_config=remote_config,
        node_config={'output_sample_rate': output_rate, 'output_channels': 1}
    ))

    # 2. Setup the streaming source
    total_duration_s = 2
    total_input_samples = input_rate * total_duration_s
    chunk_sizes = [300, 512, 1024, 400, 800] * 50
    audio_stream = generate_audio_chunks(total_input_samples, input_rate, chunk_sizes)

    # 3. Process the stream and collect output
    output_chunks = []
    async with pipeline.managed_execution():
        async for result in pipeline.process(audio_stream):
            output_chunks.append(result[0])

    assert output_chunks, "Pipeline should have produced some output"

    # 4. Verify the output
    final_audio = np.concatenate(output_chunks, axis=1)
    expected_output_samples = total_input_samples * (output_rate / input_rate)
    # Allow for a small tolerance due to resampling algorithm behavior at edges
    tolerance = expected_output_samples * 0.05
    assert abs(final_audio.shape[1] - expected_output_samples) < tolerance
    assert final_audio.shape[0] == 1 