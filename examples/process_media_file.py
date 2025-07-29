#!/usr/bin/env python3
"""
Example of processing a local media file using the new process_media method.
"""

import sys
import os
import asyncio
import logging

# Add the parent directory to the path so we can import remotemedia
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from remotemedia import Pipeline
from remotemedia.nodes import AudioTransform, VideoTransform, PassThroughNode, MediaReaderNode
from remotemedia.utils import setup_logging

# --- Configuration ---
# You may need to change this path to a media file on your system.
# For example, a .mp4 or .mov file with audio and video.
MEDIA_SOURCE_PATH = "examples/BigBuckBunny_320x180.mp4"
LOG_LEVEL = "INFO"


async def main():
    """Run the media file processing example."""
    setup_logging(level=LOG_LEVEL)
    
    print("RemoteMedia SDK - Media File Processing Example")
    print("=" * 50)
    print(f"Attempting to process media from: {MEDIA_SOURCE_PATH}")
    
    # 1. Create a pipeline with a source node
    pipeline = Pipeline(name="MediaFileProcessing")
    pipeline.add_node(MediaReaderNode(MEDIA_SOURCE_PATH, name="media_source"))
    pipeline.add_node(PassThroughNode(name="output"))
    
    # 2. Use the pipeline with managed execution for setup/teardown
    try:
        async with pipeline.managed_execution():
            print(f"\nProcessing media stream from '{MEDIA_SOURCE_PATH}'...")
            
            frame_count = 0
            async for processed_data in pipeline.process():
                if processed_data.get('audio') is not None:
                    logging.info(f"Processed Audio Frame")
                if processed_data.get('video') is not None:
                    logging.info(f"Processed Video Frame")
                frame_count += 1

            print(f"\nFinished processing. Total frames processed: {frame_count}")
            
    except Exception as e:
        logging.error(f"An error occurred: {e}", exc_info=True)
        print("\n---")
        print("This example requires a media source (like a webcam or a file).")
        print("If you don't have a webcam, please edit this script and set")
        print("the MEDIA_SOURCE_PATH variable to a local video file.")
        print(f"Current path: {MEDIA_SOURCE_PATH}")
        print("---")
        return 1
    
    print("\nExample completed successfully!")
    return 0


if __name__ == "__main__":
    asyncio.run(main()) 