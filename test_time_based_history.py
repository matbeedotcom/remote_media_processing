#!/usr/bin/env python3
"""
Test script to demonstrate time-based conversation history in UltravoxNode.
"""

import asyncio
import numpy as np
from datetime import datetime, timedelta
import logging

from remotemedia.core.pipeline import Pipeline
from remotemedia.nodes.ml import UltravoxNode

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def test_time_based_history():
    """Test the time-based conversation history feature."""
    
    # Create a pipeline with UltravoxNode
    pipeline = Pipeline()
    
    # Create UltravoxNode with 2 minute conversation history window
    ultravox = UltravoxNode(
        model_id="fixie-ai/ultravox-v0_5-llama-3_2-1b",
        enable_conversation_history=True,
        conversation_history_minutes=2.0,  # Only keep 2 minutes of history
        system_prompt="You are a helpful assistant with a 2-minute memory window."
    )
    
    pipeline.add_node('ultravox', ultravox)
    
    # Test session
    session_id = "test-user-123"
    
    # Helper to create test audio
    def create_test_audio(duration_s=1.0, sample_rate=16000):
        samples = int(duration_s * sample_rate)
        return np.random.randn(samples).astype(np.float32)
    
    logger.info("=== Time-Based Conversation History Test ===")
    
    # Initialize the pipeline
    await ultravox.initialize()
    
    # Message 1: Initial interaction
    logger.info("\n--- Message 1 (T=0) ---")
    audio1 = create_test_audio()
    metadata1 = {
        'session_id': session_id,
        'user_text': "My favorite color is blue. Remember this."
    }
    
    async for result in ultravox.process(iter([(audio1, 16000, metadata1)])):
        if isinstance(result, tuple):
            response, _ = result
            logger.info(f"User: {metadata1['user_text']}")
            logger.info(f"Assistant: {response}")
    
    # Check history
    session_state = await ultravox.get_session_state(session_id)
    history = session_state.get('conversation_history', [])
    logger.info(f"History length after message 1: {len(history)} messages")
    
    # Message 2: After 1 minute (within window)
    logger.info("\n--- Message 2 (T=1 minute) - Within 2-minute window ---")
    await asyncio.sleep(1)  # Simulate 1 minute passing (using 1 second for testing)
    
    audio2 = create_test_audio()
    metadata2 = {
        'session_id': session_id,
        'user_text': "What is my favorite color?"
    }
    
    async for result in ultravox.process(iter([(audio2, 16000, metadata2)])):
        if isinstance(result, tuple):
            response, _ = result
            logger.info(f"User: {metadata2['user_text']}")
            logger.info(f"Assistant: {response}")
            logger.info("(Should remember blue from 1 minute ago)")
    
    # Check history
    history = session_state.get('conversation_history', [])
    logger.info(f"History length after message 2: {len(history)} messages")
    
    # Message 3: Simulate 3 minutes passing (outside window)
    logger.info("\n--- Message 3 (T=3 minutes) - Outside 2-minute window ---")
    
    # Manually update timestamps to simulate time passing
    # In real usage, this would happen naturally with actual time
    if history:
        # Make the first messages appear 3 minutes old
        old_time = (datetime.now() - timedelta(minutes=3)).isoformat()
        if len(history) >= 2:
            history[0]['timestamp'] = old_time  # User message from msg 1
            history[1]['timestamp'] = old_time  # Assistant message from msg 1
    
    audio3 = create_test_audio()
    metadata3 = {
        'session_id': session_id,
        'user_text': "What is my favorite color?"
    }
    
    async for result in ultravox.process(iter([(audio3, 16000, metadata3)])):
        if isinstance(result, tuple):
            response, _ = result
            logger.info(f"User: {metadata3['user_text']}")
            logger.info(f"Assistant: {response}")
            logger.info("(Should NOT remember blue - outside 2-minute window)")
    
    # Check final history
    history = session_state.get('conversation_history', [])
    logger.info(f"\nFinal history length: {len(history)} messages")
    logger.info("History contents:")
    for i, msg in enumerate(history):
        if 'timestamp' in msg:
            msg_time = datetime.fromisoformat(msg['timestamp'])
            age = datetime.now() - msg_time
            logger.info(f"  {i+1}. {msg['role']}: {msg['content'][:50]}... (age: {age.total_seconds():.1f}s)")
        else:
            logger.info(f"  {i+1}. {msg['role']}: {msg['content'][:50]}... (no timestamp)")
    
    # Cleanup
    await pipeline.cleanup()
    logger.info("\n=== Test Complete ===")


if __name__ == "__main__":
    asyncio.run(test_time_based_history())