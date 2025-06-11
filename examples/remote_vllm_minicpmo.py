#!/usr/bin/env python3
"""
Example of using the VLLMNode to run the OpenGVLab/MiniCPM-o-2_6 model
remotely for image-to-text generation, using the model's chat template.

**TO RUN THIS EXAMPLE:**

1.  **Install all dependencies:**
    $ pip install -r requirements.txt
    $ pip install -r requirements-ml.txt
    $ pip install vllm Pillow PyAV transformers

2.  **Start the server:**
    In a separate terminal, start the gRPC server.
    $ PYTHONPATH=. python remote_service/src/server.py

3.  **Run this script:**
    $ python examples/remote_vllm_minicpmo.py
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
from remotemedia.nodes.source import MediaReaderNode, VideoTrackSource
from remotemedia.nodes.video import DecodeVideoFrame, TakeFirstFrameNode
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
    video_path = "examples/draw.mp4"
    question = "Describe the object being drawn."
    
    if not os.path.exists(video_path):
        logger.error(f"Video file not found: '{video_path}'.")
        return

    logger.info("--- Running Remote VLLM MiniCPM-o Pipeline ---")

    minicpmo_vllm_node = VLLMNode(
        model="openbmb/MiniCPM-o-2_6",
        use_chat_template=True,
        modalities=["image"],
        max_model_len=4096,
        max_num_seqs=2,
        sampling_params={
            "temperature": 0.2,
            "max_tokens": 128,
            "stop_tokens": ["<|im_end|>", "<|endoftext|>"]
        },
    )

    # Configure for remote execution.
    remote_config = RemoteExecutorConfig(host=REMOTE_HOST, port=50052, ssl_enabled=False)
    
    # This node prepares the data in the format expected by VLLMNode when
    # using a chat template. Note the specific placeholder format for MiniCPM.
    transform_for_chat = TransformNode(
        transform_func=lambda image: {
            "messages": [{'role': 'user', 'content': f'(<image>./</image>)\n{question}'}],
            "image": image,
        }
    )

    # Build the pipeline
    pipeline = Pipeline(
        [
            MediaReaderNode(path=video_path),
            VideoTrackSource(),
            DecodeVideoFrame(),
            TakeFirstFrameNode(),
            transform_for_chat,
            remote_config(minicpmo_vllm_node),
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