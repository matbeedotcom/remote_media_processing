#!/usr/bin/env python3
"""
Example of using the VLLMNode to run the deepseek-vl-tiny model remotely
for image-to-text generation.

This example demonstrates how to configure the VLLMNode for a specific
multimodal model and process an image from a video file using a standard pipeline.

**TO RUN THIS EXAMPLE:**

1.  **Install all dependencies:**
    $ pip install -r requirements.txt
    $ pip install -r requirements-ml.txt
    $ pip install vllm Pillow PyAV

2.  **Start the server:**
    In a separate terminal, start the gRPC server. The server needs access to
    the `remotemedia` library and have vLLM and other ML libraries installed.
    $ PYTHONPATH=. python remote_service/src/server.py

3.  **Run this script:**
    The first time you run this, the server will download the required model
    from the Hugging Face Hub (e.g., "deepseek-ai/deepseek-vl2-tiny").
    $ python examples/remote_vllm_deepseek_vl.py
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
    question = "What is being drawn in this image?"
    
    if not os.path.exists(video_path):
        logger.error(f"Video file not found: '{video_path}'. This example requires it.")
        logger.error("You can find the video in the project's 'examples' directory.")
        return

    logger.info("--- Running Remote VLLM DeepSeek-VL Pipeline ---")

    # 1. Define the VLLMNode instance locally.
    #    The arguments now directly mirror the common parameters for vLLM's
    #    engine, making configuration more straightforward.
    deepseek_vllm_node = VLLMNode(
        model="deepseek-ai/deepseek-vl2-tiny",
        prompt_template="<|User|>: <image>\\n{question}\\n\\n<|Assistant|>:",
        modalities=["image"],
        max_model_len=4096,
        max_num_seqs=2,
        # Other engine arguments can be passed directly as kwargs.
        # e.g., hf_overrides is passed to AsyncEngineArgs.
        hf_overrides={"architectures": ["DeepseekVLV2ForCausalLM"]},
        sampling_params={
            "temperature": 0.2,
            "max_tokens": 128,
        },
    )

    # 2. Configure for remote execution.
    remote_config = RemoteExecutorConfig(host=REMOTE_HOST, port=50052, ssl_enabled=False)
    
    # 3. Build the pipeline
    pipeline = Pipeline(
        [
            MediaReaderNode(path=video_path),
            VideoTrackSource(),
            DecodeVideoFrame(),
            TakeFirstFrameNode(),
            TransformNode(
                transform_func=lambda image: {"image": image, "question": question}
            ),
            remote_config(deepseek_vllm_node),
            PrintResponseStream(),
        ]
    )

    try:
        logger.info("Starting remote VLLM pipeline...")
        async with pipeline.managed_execution():
            async for _ in pipeline.process():
                pass
        # The final newline is now handled by the PrintResponseStream's cleanup
        logger.info("Pipeline finished successfully.")
    except Exception as e:
        logger.error(f"An error occurred during pipeline execution: {e}", exc_info=True)
        logger.error(
            "Please ensure the remote server is running and all dependencies "
            "(including vllm, Pillow, PyAV) are installed on it."
        )

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Execution cancelled by user.") 