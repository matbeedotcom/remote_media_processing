#!/usr/bin/env python3
"""
Example of using RemoteObjectExecutionNode to execute a Qwen2.5-Omni assistant
on a remote server.

This script demonstrates how a locally defined `Qwen2_5OmniNode` instance can
be sent to a remote server for execution. This is useful when you want to prototype
or run custom node logic without needing to pre-install it on the server, as long
as the server has the required dependencies (e.g., PyTorch, transformers,
qwen-omni-utils).

**TO RUN THIS EXAMPLE:**

1.  **Install ML dependencies:**
    $ pip install -r requirements-ml.txt
    $ pip install qwen-omni-utils soundfile

2.  **Start the server:**
    In a separate terminal, start the server with the project root in the python path.
    The first time this runs, the server will download the Qwen model.
    $ PYTHONPATH=. python remote_service/src/server.py

3.  **Run this script:**
    $ python examples/remote_qwen_omni_assistant.py
"""

import asyncio
import logging
import os
import soundfile as sf
import sys
from pathlib import Path

# Ensure the 'remotemedia' package is in the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from remotemedia.core.node import RemoteExecutorConfig
from remotemedia.nodes.ml import Qwen2_5OmniNode

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def main():
    """
    Main function to set up and run the remote Qwen2.5-Omni node.
    """
    REMOTE_HOST = os.environ.get("REMOTE_HOST", "127.0.0.1")
    
    logger.info("--- Running Remote Qwen2.5-Omni Assistant ---")

    # Configure the connection to the remote server that will execute the node
    # Port 50052 is the default for RemoteObjectExecutionNode
    remote_config = RemoteExecutorConfig(host=REMOTE_HOST, port=50052, ssl_enabled=False)

    # 1. Create an instance of the Qwen2_5OmniNode locally.
    #    The parameters configured here will be used when the node is executed
    #    on the remote server.
    # According to a memory from a past conversation, 'mps' is the preferred device backend for PyTorch.
    local_qwen_instance = Qwen2_5OmniNode(
        name="RemoteQwenAssistant",
        model_id="Qwen/Qwen2.5-Omni-3B",
        device="mps",  # This device setting applies to the *remote* server
        torch_dtype="bfloat16"
        # For NVIDIA GPUs, you might enable flash attention for better performance:
        # attn_implementation="flash_attention_2",
    )

    # 2. Wrap the local instance with the remote config. This creates a proxy
    #    object (`RemoteObjectExecutionNode`) that forwards calls to the server.
    remote_qwen_node = remote_config(local_qwen_instance)

    try:
        # Initialize the node on the remote server. This is where the model
        # will be downloaded and loaded into memory on the server.
        logger.info("Initializing remote Qwen node... (This may take a while on first run)")
        await remote_qwen_node.initialize()
        logger.info("Remote Qwen node initialized successfully.")

        # Define the multimodal conversation payload
        conversation = [
            {
                "role": "system",
                "content": [
                    {"type": "text", "text": "You are Qwen, a virtual human developed by the Qwen Team, Alibaba Group, capable of perceiving auditory and visual inputs, as well as generating text and speech."}
                ],
            },
            {
                "role": "user",
                "content": [
                    {"type": "video", "video": "https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen2.5-Omni/draw.mp4"},
                    {"type": "text", "text": "What is the person in the video drawing? Please answer in character, as a pirate."}
                ],
            },
        ]

        logger.info("Processing conversation with remote Qwen node...")
        # The `process` call is sent to the server, executed there, and the
        # result is returned as an async generator. Since we expect only one
        # result, we use `anext()` to retrieve it.
        result_generator = remote_qwen_node.process(conversation)
        text_responses, audio_response = await anext(result_generator)

        if text_responses:
            for i, response in enumerate(text_responses):
                logger.info(f"Generated Text Response {i+1}: '{response}'")

        if audio_response is not None and audio_response.size > 0:
            output_filename = "remote_qwen_output.wav"
            await asyncio.to_thread(sf.write, output_filename, audio_response, samplerate=24000)
            logger.info(f"Generated audio saved to '{os.path.abspath(output_filename)}'")
        else:
            logger.info("No audio was generated for this response.")

    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        logger.error("Please ensure the remote server is running and has all ML dependencies installed.")
    finally:
        # Clean up resources on the remote server
        if remote_qwen_node.is_initialized:
            logger.info("Cleaning up remote Qwen node...")
            await remote_qwen_node.cleanup()
            logger.info("Remote Qwen node cleaned up.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Execution cancelled by user.") 