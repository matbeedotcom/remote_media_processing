#!/usr/bin/env python3
"""
Simple test to demonstrate time-based conversation history filtering.
This test doesn't require loading the model.
"""

import asyncio
from datetime import datetime, timedelta
import logging

from remotemedia.nodes.ml import UltravoxNode

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def test_history_filtering():
    """Test the time-based history filtering logic."""
    
    # Create UltravoxNode with 5 minute history window
    node = UltravoxNode(
        conversation_history_minutes=5.0,
        enable_conversation_history=True
    )
    
    # Initialize state management
    await node.initialize()
    
    # Create a test session
    session_id = "test-session"
    session_state = await node.get_session_state(session_id)
    
    # Create test conversation history with different timestamps
    current_time = datetime.now()
    test_history = [
        # Old messages (should be filtered out)
        {
            "role": "user",
            "content": "Message from 10 minutes ago",
            "timestamp": (current_time - timedelta(minutes=10)).isoformat()
        },
        {
            "role": "assistant", 
            "content": "Response from 10 minutes ago",
            "timestamp": (current_time - timedelta(minutes=10)).isoformat()
        },
        # Messages from 6 minutes ago (should be filtered out)
        {
            "role": "user",
            "content": "Message from 6 minutes ago",
            "timestamp": (current_time - timedelta(minutes=6)).isoformat()
        },
        {
            "role": "assistant",
            "content": "Response from 6 minutes ago", 
            "timestamp": (current_time - timedelta(minutes=6)).isoformat()
        },
        # Recent messages (should be kept)
        {
            "role": "user",
            "content": "Message from 4 minutes ago",
            "timestamp": (current_time - timedelta(minutes=4)).isoformat()
        },
        {
            "role": "assistant",
            "content": "Response from 4 minutes ago",
            "timestamp": (current_time - timedelta(minutes=4)).isoformat()
        },
        {
            "role": "user",
            "content": "Message from 2 minutes ago",
            "timestamp": (current_time - timedelta(minutes=2)).isoformat()
        },
        {
            "role": "assistant",
            "content": "Response from 2 minutes ago",
            "timestamp": (current_time - timedelta(minutes=2)).isoformat()
        },
        {
            "role": "user",
            "content": "Message from just now",
            "timestamp": current_time.isoformat()
        },
        {
            "role": "assistant",
            "content": "Response from just now",
            "timestamp": current_time.isoformat()
        }
    ]
    
    # Set the test history
    session_state.set('conversation_history', test_history)
    
    logger.info("=== Time-Based History Filtering Test ===")
    logger.info(f"History window: {node.conversation_history_minutes} minutes")
    logger.info(f"Initial history length: {len(test_history)} messages")
    
    # Simulate building conversation context (like in _generate_response)
    turns = [{"role": "system", "content": "You are a helpful assistant."}]
    
    history = session_state.get('conversation_history', [])
    cutoff_time = current_time - timedelta(minutes=node.conversation_history_minutes)
    
    logger.info(f"\nCutoff time: {cutoff_time.isoformat()}")
    logger.info("\nFiltering messages:")
    
    filtered_count = 0
    for msg in history:
        if 'timestamp' in msg:
            msg_time = datetime.fromisoformat(msg['timestamp'])
            age_minutes = (current_time - msg_time).total_seconds() / 60
            
            if msg_time >= cutoff_time:
                turns.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
                filtered_count += 1
                logger.info(f"  ✓ KEPT: {msg['role']} - '{msg['content']}' (age: {age_minutes:.1f} min)")
            else:
                logger.info(f"  ✗ FILTERED: {msg['role']} - '{msg['content']}' (age: {age_minutes:.1f} min)")
    
    logger.info(f"\nResult: {filtered_count} messages kept from last {node.conversation_history_minutes} minutes")
    logger.info(f"Conversation turns for model: {len(turns)} (including system message)")
    
    # Test the filtering that happens when adding new messages
    logger.info("\n--- Testing automatic filtering when adding new message ---")
    
    # Add a new message (this will trigger filtering)
    new_history = test_history.copy()
    new_history.append({
        "role": "user",
        "content": "Brand new message",
        "timestamp": current_time.isoformat()
    })
    new_history.append({
        "role": "assistant", 
        "content": "Brand new response",
        "timestamp": current_time.isoformat()
    })
    
    # Simulate the filtering logic from the node
    filtered_history = []
    for msg in new_history:
        if isinstance(msg, dict) and 'timestamp' in msg:
            msg_time = datetime.fromisoformat(msg['timestamp'])
            if msg_time >= cutoff_time:
                filtered_history.append(msg)
    
    logger.info(f"After adding new message and filtering:")
    logger.info(f"  Original length: {len(new_history)}")
    logger.info(f"  Filtered length: {len(filtered_history)}")
    logger.info(f"  Messages removed: {len(new_history) - len(filtered_history)}")
    
    # Cleanup
    await node.cleanup()
    logger.info("\n=== Test Complete ===")


if __name__ == "__main__":
    asyncio.run(test_history_filtering())