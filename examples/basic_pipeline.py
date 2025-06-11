#!/usr/bin/env python3
"""
Basic Pipeline Example for RemoteMedia SDK

This example demonstrates how to create and use a simple processing pipeline
with the RemoteMedia SDK.
"""

import sys
import os
import asyncio

# Add the parent directory to the path so we can import remotemedia
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from remotemedia import Pipeline
from remotemedia.nodes import PassThroughNode, AudioTransform, VideoTransform
from remotemedia.utils import setup_logging


async def main():
    """Run the basic pipeline example."""
    # Set up logging
    setup_logging(level="DEBUG")
    
    print("RemoteMedia SDK - Basic Pipeline Example")
    print("=" * 50)
    
    # Create a simple pipeline
    pipeline = Pipeline(name="BasicExample")
    
    # Add some processing nodes
    pipeline.add_node(PassThroughNode(name="input"))
    pipeline.add_node(AudioTransform(sample_rate=44100, name="audio_proc"))
    pipeline.add_node(VideoTransform(resolution=(1920, 1080), name="video_proc"))
    pipeline.add_node(PassThroughNode(name="output"))
    
    print(f"Created pipeline: {pipeline}")
    print(f"Pipeline configuration: {pipeline.get_config()}")
    
    # Use the pipeline with managed execution
    test_data = {"audio": "sample_audio_data", "video": "sample_video_data"}
    
    try:
        async with pipeline.managed_execution():
            print(f"\nProcessing data: {test_data}")
            async for result in pipeline.process(test_data):
                print(f"Result: {result}")
            
    except Exception as e:
        print(f"Error during processing: {e}")
        return 1
    
    print("\nExample completed successfully!")
    return 0


if __name__ == "__main__":
    asyncio.run(main()) 