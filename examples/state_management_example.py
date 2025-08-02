#!/usr/bin/env python3
"""
Example demonstrating the generic state management system.

This example shows how any node can use the built-in state management
to maintain session-specific data for multi-user scenarios.
"""

import asyncio
import numpy as np
import logging
from typing import AsyncGenerator, Any, Optional, Tuple
from remotemedia.core.pipeline import Pipeline
from remotemedia.core.node import Node
from remotemedia.nodes.audio import AudioTransform
from remotemedia.nodes.ml import UltravoxNode
from remotemedia.remote.config import RemoteExecutorConfig

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class StatefulProcessingNode(Node):
    """
    Example custom node that uses the state management system.
    
    This node demonstrates:
    - Storing per-session data (e.g., user preferences, counters)
    - Retrieving and updating session state
    - Handling multiple concurrent users
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.is_streaming = True
    
    async def process(self, data_stream: AsyncGenerator[Any, None]) -> AsyncGenerator[Any, None]:
        """Process data with session state tracking."""
        async for data in data_stream:
            # Extract session ID from the data
            session_id = self.extract_session_id(data)
            
            if not session_id:
                # No session ID, pass through without state
                yield data
                continue
            
            # Get or create session state
            session_state = await self.get_session_state(session_id)
            if not session_state:
                yield data
                continue
            
            # Update session statistics
            message_count = session_state.get('message_count', 0)
            message_count += 1
            session_state.set('message_count', message_count)
            
            # Track user preferences
            if isinstance(data, tuple) and len(data) >= 3:
                audio_data, sample_rate, metadata = data
                
                # Store user preferences from metadata
                if 'user_name' in metadata:
                    session_state.set('user_name', metadata['user_name'])
                if 'language' in metadata:
                    session_state.set('language', metadata['language'])
                
                # Add session info to output metadata
                enhanced_metadata = metadata.copy()
                enhanced_metadata.update({
                    'message_number': message_count,
                    'session_user': session_state.get('user_name', 'Anonymous'),
                    'session_language': session_state.get('language', 'en'),
                    'session_created': session_state.created_at.isoformat(),
                    'session_last_accessed': session_state.last_accessed.isoformat()
                })
                
                yield (audio_data, sample_rate, enhanced_metadata)
            else:
                yield data


class SessionAwareVADBuffer(Node):
    """
    VAD buffer that maintains separate buffers per session.
    
    This demonstrates how to use state management for audio buffering
    in multi-user scenarios.
    """
    
    def __init__(self, buffer_duration_s: float = 5.0, sample_rate: int = 16000, **kwargs):
        super().__init__(**kwargs)
        self.is_streaming = True
        self.buffer_duration_s = buffer_duration_s
        self.sample_rate = sample_rate
        self.max_buffer_samples = int(buffer_duration_s * sample_rate)
    
    async def process(self, data_stream: AsyncGenerator[Any, None]) -> AsyncGenerator[Any, None]:
        """Buffer audio per session."""
        async for data in data_stream:
            session_id = self.extract_session_id(data)
            
            if not session_id or not isinstance(data, tuple) or len(data) < 2:
                yield data
                continue
            
            audio_data, sample_rate = data[:2]
            metadata = data[2] if len(data) > 2 else {}
            
            # Get session state
            session_state = await self.get_session_state(session_id)
            if not session_state:
                yield data
                continue
            
            # Get or create audio buffer for this session
            buffer = session_state.get('audio_buffer', np.array([], dtype=np.float32))
            
            # Append new audio
            if isinstance(audio_data, np.ndarray):
                buffer = np.concatenate([buffer, audio_data.flatten()])
                
                # Trim buffer if too long
                if len(buffer) > self.max_buffer_samples:
                    buffer = buffer[-self.max_buffer_samples:]
                
                # Update state
                session_state.set('audio_buffer', buffer)
                session_state.set('buffer_duration_s', len(buffer) / self.sample_rate)
                
                # Add buffer info to metadata
                enhanced_metadata = metadata.copy()
                enhanced_metadata['buffer_size_s'] = len(buffer) / self.sample_rate
                
                yield (audio_data, sample_rate, enhanced_metadata)
            else:
                yield data


async def simulate_multi_user_pipeline():
    """Simulate multiple users interacting with a stateful pipeline."""
    
    # Create pipeline
    pipeline = Pipeline()
    
    # Add stateful processing node
    pipeline.add_node('state_processor', StatefulProcessingNode(
        name="StateProcessor"
    ))
    
    # Add session-aware VAD buffer
    pipeline.add_node('vad_buffer', SessionAwareVADBuffer(
        buffer_duration_s=3.0,
        sample_rate=16000,
        name="SessionVADBuffer"
    ))
    
    # Add audio transform
    pipeline.add_node('audio_transform', AudioTransform(
        source_rate=48000,
        target_rate=16000,
        name="AudioTransform"
    ))
    
    # Add Ultravox with conversation history
    # For remote execution:
    # remote_config = RemoteExecutorConfig(host="localhost", port=50051, ssl_enabled=False)
    # ultravox = UltravoxNode(
    #     model_id="fixie-ai/ultravox-v0_5-llama-3_2-1b",
    #     enable_conversation_history=True,
    #     conversation_history_minutes=5.0,  # Keep 5 minutes of conversation history
    #     remote_executor_config=remote_config
    # )
    
    ultravox = UltravoxNode(
        model_id="fixie-ai/ultravox-v0_5-llama-3_2-1b",
        enable_conversation_history=True,
        conversation_history_minutes=5.0  # Keep 5 minutes of conversation history
    )
    pipeline.add_node('ultravox', ultravox)
    
    # Connect nodes
    pipeline.connect('state_processor', 'vad_buffer')
    pipeline.connect('vad_buffer', 'audio_transform')
    pipeline.connect('audio_transform', 'ultravox')
    
    logger.info("=== Multi-User Stateful Pipeline ===")
    
    # Simulate three different users
    users = [
        {
            'session_id': 'user-alice-123',
            'user_name': 'Alice',
            'language': 'en',
            'messages': [
                "Hello, my name is Alice.",
                "I like cats.",
                "What's my name?",
                "What do I like?"
            ]
        },
        {
            'session_id': 'user-bob-456',
            'user_name': 'Bob',
            'language': 'es',
            'messages': [
                "Hi, I'm Bob.",
                "I enjoy programming.",
                "Do you remember my name?",
                "What do I enjoy?"
            ]
        },
        {
            'session_id': 'user-charlie-789',
            'user_name': 'Charlie',
            'language': 'fr',
            'messages': [
                "Bonjour, je suis Charlie.",
                "I speak French and English.",
                "What languages do I speak?",
                "What's my name again?"
            ]
        }
    ]
    
    # Process messages from different users in interleaved fashion
    for message_idx in range(4):
        for user in users:
            if message_idx < len(user['messages']):
                logger.info(f"\n--- {user['user_name']} (Message {message_idx + 1}) ---")
                
                # Generate test audio
                audio = generate_test_audio(1.5, 48000)
                
                # Create metadata with session info
                metadata = {
                    'session_id': user['session_id'],
                    'user_name': user['user_name'],
                    'language': user['language'],
                    'user_text': user['messages'][message_idx]
                }
                
                # Process through pipeline
                async for result in pipeline.process_stream([
                    (audio, 48000, metadata)
                ]):
                    if isinstance(result, tuple) and len(result) >= 2:
                        response_text = result[0]
                        response_metadata = result[1] if len(result) > 1 else {}
                        
                        logger.info(f"{user['user_name']}: {user['messages'][message_idx]}")
                        logger.info(f"Assistant: {response_text}")
                        
                        if isinstance(response_metadata, dict):
                            logger.info(f"Session info: Message #{response_metadata.get('conversation_length', 0)//2}")
                
                await asyncio.sleep(0.5)
    
    # Show session states
    logger.info("\n=== Final Session States ===")
    for node_name, node in pipeline.nodes.items():
        if node.state:
            sessions = await node.state.get_all_sessions()
            if sessions:
                logger.info(f"\n{node_name} sessions:")
                for session_id, session_state in sessions.items():
                    logger.info(f"  {session_id}:")
                    logger.info(f"    Created: {session_state.created_at}")
                    logger.info(f"    Last accessed: {session_state.last_accessed}")
                    logger.info(f"    Data keys: {list(session_state.data.keys())}")
    
    # Clean up
    await pipeline.cleanup()
    logger.info("\n=== Pipeline cleaned up ===")


def generate_test_audio(duration_seconds: float, sample_rate: int) -> np.ndarray:
    """Generate test audio data."""
    t = np.linspace(0, duration_seconds, int(duration_seconds * sample_rate))
    audio = (
        0.3 * np.sin(2 * np.pi * 440 * t) +
        0.2 * np.sin(2 * np.pi * 880 * t) +
        0.05 * np.random.randn(len(t))
    )
    return audio.astype(np.float32)


async def main():
    """Run the state management examples."""
    await simulate_multi_user_pipeline()


if __name__ == "__main__":
    asyncio.run(main())