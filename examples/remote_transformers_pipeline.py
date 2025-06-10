#!/usr/bin/env python3
"""
Demonstrates using the generic TransformersPipelineNode for a remote audio
classification task.

This example showcases the power and flexibility of the SDK's remote execution
capabilities. We define a standard audio processing pipeline but insert a
`RemoteObjectExecutionNode` to offload the machine learning part to a server.

**TO RUN THIS EXAMPLE:**

1.  **Install all dependencies:**
    $ pip install -r requirements.txt
    $ pip install -r requirements-ml.txt

2.  **Start the server:**
    In a separate terminal, start the gRPC server. The server needs access to
    the `remotemedia` library.
    $ PYTHONPATH=. python remote_service/src/server.py

3.  **Run this script:**
    The first time you run this, the server will download the required model
    from the Hugging Face Hub (e.g., "superb/wav2vec2-base-superb-ks").
    $ python examples/remote_transformers_pipeline.py
"""

import asyncio
import logging
import os

# Ensure the 'remotemedia' package is in the Python path
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from remotemedia.core.pipeline import Pipeline
from remotemedia.core.node import RemoteExecutorConfig, Node
from remotemedia.nodes.source import MediaReaderNode, AudioTrackSource
from remotemedia.nodes.audio import AudioTransform, ExtractAudioDataNode
from remotemedia.nodes.remote import RemoteExecutionNode

# Configure basic logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class PrintOutputNode(Node):
    """A simple node that prints any data it receives and passes it through."""
    async def process(self, data):
        logging.info(f"Received classification result: {data}")
        return data


async def main():
    """
    Main function to set up and run the remote audio classification pipeline.
    """
    # This example uses a pre-existing audio file.
    # A suitable file would be a clear, single-channel WAV.
    audio_path = "examples/BigBuckBunny_320x180.mp4"
    if not os.path.exists(audio_path):
        logging.error(
            f"Audio file not found: {audio_path}. "
            "Please provide a path to a media file."
        )
        return

    # 1. Configure the remote execution for a standard `TransformersPipelineNode`.
    #    The server will instantiate this node with the provided configuration.
    remote_config = RemoteExecutorConfig(host="127.0.0.1", port=50052, ssl_enabled=False)
    remote_classifier_node = RemoteExecutionNode(
        node_to_execute="TransformersPipelineNode",
        remote_config=remote_config,
        node_config={
            "task": "audio-classification",
            "model": "superb/wav2vec2-base-superb-ks",
        },
    )

    # 3. Build the pipeline. The first node is the source.
    pipeline = Pipeline(
        [
            MediaReaderNode(path=audio_path),
            AudioTrackSource(),
            # Resample to 16kHz mono audio for the classification model
            AudioTransform(output_sample_rate=16000, output_channels=1),
            ExtractAudioDataNode(),
            remote_classifier_node,
            PrintOutputNode(),
        ]
    )

    logging.info("Starting remote audio classification pipeline...")
    # The 'managed_execution' context handles init and cleanup.
    # The process() method will internally use the MediaReaderNode as the stream source.
    async with pipeline.managed_execution():
        async for _ in pipeline.process():
            # We just want to exhaust the stream; the PrintOutputNode handles the logging.
            pass

    logging.info("Pipeline finished.")


if __name__ == "__main__":
    # Ensure a sample audio file exists for the demo
    if not os.path.exists("examples/BigBuckBunny_320x180.mp4"):
        logging.warning("examples/BigBuckBunny_320x180.mp4 not found. Please add it to run the demo")
    else:
        try:
            asyncio.run(main())
        except Exception as e:
            logging.error(f"An error occurred during pipeline execution: {e}", exc_info=True)
            logging.error(
                "Please ensure the remote server is running and all dependencies "
                "from requirements.txt and requirements-ml.txt are installed."
            ) 