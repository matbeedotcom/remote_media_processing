"""
Example of a streaming pipeline that uses a RemoteExecutionNode.

This script demonstrates how to set up a pipeline that includes a node
executed on a remote gRPC service. It creates a stream of audio data,
buffers it locally, and then sends it to the remote service to be
resampled by an AudioTransform node.

Usage:
1. Ensure the remote gRPC server is running:
   python remote_service/src/server.py

2. Run this script in a separate terminal:
   python examples/remote_streaming_pipeline.py
"""
import asyncio
import numpy as np

from remotemedia.core.pipeline import Pipeline
from remotemedia.core.node import RemoteExecutorConfig
from remotemedia.nodes.audio import AudioBuffer
from remotemedia.nodes.remote import RemoteExecutionNode


async def generate_audio_chunks(total_samples, sample_rate, chunk_size):
    """Generate a stream of audio chunks from a sine wave."""
    print(f"Generating a {total_samples/sample_rate:.1f}s sine wave at {sample_rate} Hz...")
    full_audio = np.sin(2 * np.pi * 440 * np.arange(total_samples) / sample_rate, dtype=np.float32).reshape(1, -1)
    
    start = 0
    while start < total_samples:
        end = start + chunk_size
        chunk = full_audio[:, start:end]
        if chunk.shape[1] > 0:
            # Yields a tuple of (audio_data, sample_rate)
            yield (chunk, sample_rate)
        start = end
        await asyncio.sleep(0.01) # Simulate a real-time stream
    print("Finished generating audio chunks.")


async def main():
    """
    Sets up and runs the remote streaming pipeline.
    """
    print("--- Remote Streaming Pipeline Example ---")

    # 1. Configure the connection to the remote execution service.
    #    This should match the host and port your gRPC server is running on.
    remote_config = RemoteExecutorConfig(
        host='127.0.0.1', 
        port=50052,         # Default port is 50052
        ssl_enabled=False
    )
    print(f"Configured to connect to remote server at {remote_config.host}:{remote_config.port}")

    # 2. Create a pipeline and add nodes.
    pipeline = Pipeline(name="RemoteAudioPipeline")

    # The first node runs locally, buffering audio into 2048-sample chunks.
    pipeline.add_node(AudioBuffer(buffer_size_samples=2048))

    # The second node is a RemoteExecutionNode. It will send the buffered
    # audio chunks to the remote server, which will execute an AudioTransform
    # node with the specified configuration.
    pipeline.add_node(RemoteExecutionNode(
        name="RemoteResampler",
        node_to_execute="AudioTransform",
        remote_config=remote_config,
        node_config={'output_sample_rate': 16000, 'output_channels': 1}
    ))
    print("Pipeline created: AudioBuffer (local) -> RemoteExecutionNode (AudioTransform @ remote)")

    # 3. Setup the streaming source.
    #    We'll generate 2 seconds of audio at 48000 Hz.
    input_rate = 48000
    total_duration_s = 2
    total_input_samples = input_rate * total_duration_s
    # Use a small chunk size to demonstrate streaming
    chunk_size = 512
    audio_stream = generate_audio_chunks(total_input_samples, input_rate, chunk_size)

    # 4. Process the stream through the pipeline.
    print("\nStarting pipeline processing...")
    output_chunk_count = 0
    total_output_samples = 0
    
    # managed_execution handles the setup and teardown of the pipeline,
    # including the connection to the remote service.
    async with pipeline.managed_execution():
        async for result in pipeline.process(audio_stream):
            # The 'result' is the data returned from the last node in the
            # pipeline, which is our remote AudioTransform node.
            processed_audio, output_rate = result
            output_chunk_count += 1
            total_output_samples += processed_audio.shape[1]
            print(
                f"  -> Received chunk {output_chunk_count} from remote. "
                f"Shape: {processed_audio.shape}, Sample Rate: {output_rate} Hz"
            )

    print("\nPipeline processing finished.")
    print("--- Summary ---")
    print(f"Total chunks received from remote: {output_chunk_count}")
    print(f"Total audio samples received: {total_output_samples}")
    
    expected_output_samples = total_input_samples * (16000 / 48000)
    print(f"Expected audio samples: {int(expected_output_samples)}")
    
    # Verify the output
    if abs(total_output_samples - expected_output_samples) < (expected_output_samples * 0.05):
        print("Output sample count is within the expected range. Success!")
    else:
        print("Output sample count does not match expected. Something went wrong.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting.")
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        print("Please ensure the remote gRPC server is running.")
        print("You can start it with: python remote_service/src/server.py") 