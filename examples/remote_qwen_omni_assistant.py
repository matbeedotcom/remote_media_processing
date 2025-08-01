#!/usr/bin/env python3
"""
Example of using the RemoteObjectExecutionNode to stream video to a
Qwen2.5-Omni assistant on a remote server and get a response.

This demonstrates how a custom-configured, streaming-capable node can be executed
remotely within a pipeline.

**TO RUN THIS EXAMPLE:**

1.  **Install ML dependencies:**
    $ pip install -r requirements-ml.txt
    $ pip install qwen-omni-utils soundfile PyAV

2.  **Start the server:**
    In a separate terminal, start the server with the project root in the python path.
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
from remotemedia.core.pipeline import Pipeline
from remotemedia.nodes.source import LocalMediaReaderNode
from remotemedia.nodes.ml import Qwen2_5OmniNode
from remotemedia.nodes.remote import RemoteObjectExecutionNode


# Configure basic logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def main():
    """
    Main function to set up and run the remote Qwen2.5-Omni pipeline.
    """
    REMOTE_HOST = os.environ.get("REMOTE_HOST", "127.0.0.1")
    
    logger.info("--- Running Remote Qwen2.5-Omni Assistant Pipeline ---")

    # This is the conversation structure, with placeholders for the media
    # that will be filled in by the Qwen2_5OmniNode from its input stream.
    conversation_template = [
        {
            "role": "system",
            "content": [{"type": "text", "text": "You are Qwen, a virtual human developed by the Qwen Team, Alibaba Group."}],
        },
        {
            "role": "user",
            "content": [
                {"type": "video", "video": "<video_placeholder>"},
                {"type": "text", "text": "What is the person in the video drawing? Please answer in character, as a pirate, with a cheerful male voice."}
            ],
        },
    ]

    # 1. Create a local instance of the node with its configuration.
    #    This object will be serialized and sent to the server for execution.
    local_qwen_instance = Qwen2_5OmniNode(
        name="RemoteQwenAssistant",
        model_id="Qwen/Qwen2.5-Omni-3B",
        device="cuda",
        torch_dtype="bfloat16",
        conversation_template=conversation_template,
        buffer_duration_s=5.0,
        speaker="Ethan",
        use_audio_in_video=True
    )
    
    # 2. Configure the remote execution wrapper.
    remote_config = RemoteExecutorConfig(host=REMOTE_HOST, port=50052, ssl_enabled=False)
    
    # 3. Set up the pipeline
    pipeline = Pipeline()
    
    # The source node reads the video and produces a stream of AV packets
    pipeline.add_node(LocalMediaReaderNode(
        path="examples/draw.mp4"
    ))
    
    # The RemoteObjectExecutionNode sends the local_qwen_instance to the server
    # and streams the data from the previous node to it. The Qwen node will
    # handle the mixed audio/video dictionary stream itself.
    pipeline.add_node(RemoteObjectExecutionNode(
        obj_to_execute=local_qwen_instance,
        remote_config=remote_config
    ))

    try:
        logger.info("Starting remote Qwen pipeline...")
        async with pipeline.managed_execution():
            async for text_responses, audio_response in pipeline.process():
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

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Execution cancelled by user.") 