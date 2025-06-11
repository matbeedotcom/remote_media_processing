#!/usr/bin/env python3
"""
Example of using the VLLMNode to run the Ultravox model remotely for
audio-to-text generation, using the model's chat template.

**TO RUN THIS EXAMPLE:**

1.  **Install all dependencies:**
    $ pip install -r requirements.txt
    $ pip install -r requirements-ml.txt
    $ pip install vllm Pillow PyAV transformers

2.  **Start the server:**
    In a separate terminal, start the gRPC server.
    $ PYTHONPATH=. python remote_service/src/server.py

3.  **Run this script:**
    $ python examples/remote_vllm_ultravox.py
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Ensure the 'remotemedia' package is in the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from remotemedia.core.node import Node, RemoteExecutorConfig
from remotemedia.core.pipeline import Pipeline
from remotemedia.nodes.ml import VLLMNode
from remotemedia.nodes.source import MediaReaderNode, AudioTrackSource
from remotemedia.nodes.audio import AudioTransform, ConcatenateAudioNode
from remotemedia.nodes.transform import TransformNode

# Configure basic logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class PrintResponseStream(Node):
    """
    A sink node that prints the streaming text response in a formatted block.
    """
    _started_printing = False

    async def process(self, token: str):
        if not self._started_printing:
            print("\n--- Model Response ---")
            self._started_printing = True

        if token:
            print(token, end="", flush=True)

    async def cleanup(self) -> None:
        """Prints a footer after the stream is finished."""
        if self._started_printing:
            print("\n----------------------\n")
        await super().cleanup()


async def main():
    """Main function to set up and run the remote VLLM pipeline."""
    REMOTE_HOST = os.environ.get("REMOTE_HOST", "127.0.0.1")
    audio_path = "examples/transcribe_demo.wav"
    question = "What is recited in the audio?"
    
    if not os.path.exists(audio_path):
        logger.error(f"Audio file not found: '{audio_path}'. Please add a sample WAV file.")
        return

    logger.info("--- Running Remote VLLM Ultravox Pipeline ---")

    # For Ultravox, we use the chat template.
    ultravox_vllm_node = VLLMNode(
        model="fixie-ai/ultravox-v0_5-llama-3_2-1b",
        use_chat_template=True,
        modalities=["audio"],
        max_model_len=4096,
        max_num_seqs=5,
        limit_mm_per_prompt={"audio": 1}, # This kwarg is passed to engine_kwargs
        sampling_params={
            "temperature": 0.2,
            "max_tokens": 128,
        },
    )

    # Configure for remote execution.
    remote_config = RemoteExecutorConfig(host=REMOTE_HOST, port=50052, ssl_enabled=False)
    
    # This node prepares the data in the format expected by VLLMNode when
    # using a chat template. It receives the concatenated (audio_data, sample_rate)
    # tuple and formats it into the final dictionary.
    transform_for_chat = TransformNode(
        transform_func=lambda audio_tuple: {
            "messages": [{'role': 'user', 'content': f'<|audio|>\n{question}'}],
            "audio": audio_tuple,
        }
    )

    # Build the pipeline
    pipeline = Pipeline(
        [
            MediaReaderNode(path=audio_path),
            AudioTrackSource(),
            AudioTransform(output_sample_rate=16000, output_channels=1), # Ultravox expects 16kHz mono audio
            ConcatenateAudioNode(),
            transform_for_chat,
            remote_config(ultravox_vllm_node),
            PrintResponseStream(),
        ]
    )

    try:
        logger.info("Starting remote VLLM pipeline...")
        async with pipeline.managed_execution():
            async for _ in pipeline.process():
                pass
        logger.info("Pipeline finished successfully.")
    except Exception as e:
        logger.error(f"An error occurred during pipeline execution: {e}", exc_info=True)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Execution cancelled by user.") 