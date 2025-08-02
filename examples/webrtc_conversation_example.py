#!/usr/bin/env python3
"""
WebRTC Server with Conversation History Example.

This example demonstrates a WebRTC server that maintains conversation history
for each connected client, allowing the AI assistant to remember previous
interactions within the same session.

Key features:
- Each WebRTC connection gets a unique session ID
- Ultravox maintains conversation history per session
- History persists for the duration of the connection
- Different users have separate conversation contexts
"""

import asyncio
import logging
import os
from pathlib import Path

from remotemedia.core.pipeline import Pipeline
from remotemedia.nodes.audio import AudioTransform, VoiceActivityDetector
from remotemedia.nodes.ml import UltravoxNode
from remotemedia.remote.config import RemoteExecutorConfig
from remotemedia.webrtc import WebRTCServer, WebRTCConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_conversation_pipeline() -> Pipeline:
    """
    Create a pipeline with conversation history support.
    
    This pipeline:
    1. Transforms audio to the correct format
    2. Detects voice activity
    3. Processes speech with Ultravox (with history)
    4. Returns responses that can reference previous interactions
    """
    pipeline = Pipeline()
    
    # Audio preprocessing
    pipeline.add_node('audio_transform', AudioTransform(
        output_sample_rate=16000,
        output_channels=1,
        name="AudioTransform"
    ))
    
    # Voice Activity Detection
    pipeline.add_node('vad', VoiceActivityDetector(
        frame_duration_ms=30,
        speech_threshold=0.3,
        name="VAD"
    ))
    
    # Ultravox with conversation history
    # You can use local or remote execution
    remote_config = RemoteExecutorConfig(
        host=os.environ.get("REMOTE_HOST", "localhost"),
        port=50051,
        ssl_enabled=False
    )
    
    ultravox = UltravoxNode(
        model_id="fixie-ai/ultravox-v0_5-llama-3_2-1b",
        system_prompt=(
            "You are a helpful AI assistant with perfect memory. "
            "You remember everything the user tells you during this conversation. "
            "Always acknowledge what you remember about the user when relevant. "
            "Keep responses concise and friendly."
        ),
        enable_conversation_history=True,
        conversation_history_minutes=30.0,  # Remember 30 minutes of conversation
        max_new_tokens=100,  # Keep responses concise
        name="UltravoxNode"
    )
    
    # For remote execution (optional):
    # from remotemedia.nodes.remote import RemoteObjectExecutionNode
    # pipeline.add_node('ultravox', RemoteObjectExecutionNode(
    #     obj_to_execute=ultravox,
    #     remote_config=remote_config,
    #     name="RemoteUltravox"
    # ))
    
    pipeline.add_node('ultravox', ultravox)
    
    # Connect nodes
    pipeline.connect('audio_transform', 'vad')
    pipeline.connect('vad', 'ultravox')
    
    return pipeline


async def main():
    """Run the WebRTC server with conversation history."""
    
    # Configuration
    SERVER_HOST = os.environ.get("SERVER_HOST", "0.0.0.0")
    SERVER_PORT = int(os.environ.get("SERVER_PORT", "8080"))
    
    logger.info("=== WebRTC Conversation History Server ===")
    logger.info(f"Server: {SERVER_HOST}:{SERVER_PORT}")
    logger.info("Features:")
    logger.info("  ✓ Maintains conversation history per connection")
    logger.info("  ✓ AI remembers user information within a session")
    logger.info("  ✓ Each connection has isolated conversation context")
    logger.info("  ✓ History persists for 30 minutes of inactivity")
    
    # Create server configuration
    config = WebRTCConfig(
        host=SERVER_HOST,
        port=SERVER_PORT,
        enable_cors=True,
        stun_servers=["stun:stun.l.google.com:19302"]
    )
    
    # Create and start server
    server = WebRTCServer(
        config=config,
        pipeline_factory=create_conversation_pipeline
    )
    
    try:
        await server.start()
        
        logger.info("\nServer is running!")
        logger.info("\nExample conversation flow:")
        logger.info("  User: 'My name is Alice and I love cats'")
        logger.info("  AI: 'Nice to meet you, Alice! Cats are wonderful.'")
        logger.info("  User: 'What's my name?'")
        logger.info("  AI: 'Your name is Alice.'")
        logger.info("  User: 'What do I like?'")
        logger.info("  AI: 'You mentioned that you love cats.'")
        logger.info("\nPress Ctrl+C to stop the server")
        
        # Keep the server running
        while True:
            await asyncio.sleep(60)
            
            # Log active connections with conversation stats
            if server.connections:
                logger.info(f"\nActive connections: {len(server.connections)}")
                for conn_id, conn in server.connections.items():
                    if conn.pipeline_processor and conn.pipeline_processor.pipeline:
                        # Try to get conversation stats from Ultravox node
                        for node_name, node in conn.pipeline_processor.pipeline.nodes.items():
                            if isinstance(node, UltravoxNode) and node.state:
                                session_state = await node.state.get_session(conn_id)
                                if session_state:
                                    history = session_state.get('conversation_history', [])
                                    logger.info(f"  Connection {conn_id[:8]}...: {len(history)} messages")
                
    except KeyboardInterrupt:
        logger.info("\nShutting down server...")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
    finally:
        await server.stop()
        logger.info("Server stopped")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("WebRTC Conversation History Example")
    print("="*60)
    print("\nThis example shows how to build a WebRTC server where the AI")
    print("assistant remembers conversation history for each connection.")
    print("\nTo test:")
    print("1. Run this server")
    print("2. Connect with a WebRTC client")
    print("3. Have a conversation - the AI will remember what you say!")
    print("4. Each connection has its own isolated conversation history")
    print("\n" + "="*60 + "\n")
    
    asyncio.run(main())