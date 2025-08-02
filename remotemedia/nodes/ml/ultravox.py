import asyncio
import numpy as np
import logging
from typing import Optional, Any, AsyncGenerator
from datetime import datetime, timedelta

from remotemedia.core.node import Node
from remotemedia.core.exceptions import NodeError

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    import torch
    from transformers import pipeline
except ImportError:
    logger.warning("ML libraries not found. UltravoxNode will not be available.")
    torch = None
    pipeline = None


class UltravoxNode(Node):
    """
    A node that uses the Ultravox model for multimodal audio/text to text generation.
    It receives audio chunks and immediately processes them to generate a text response.
    """

    def __init__(self,
                 model_id: str = "fixie-ai/ultravox-v0_5-llama-3_2-1b",
                 device: Optional[str] = None,
                 torch_dtype: str = "bfloat16",
                 max_new_tokens: int = 16382,
                 system_prompt: str = "You are a friendly and helpful AI assistant.",
                 enable_conversation_history: bool = True,
                 conversation_history_minutes: float = 10.0,
                 **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.is_streaming = True
        self.model_id = model_id
        self._requested_device = device
        self._requested_torch_dtype = torch_dtype
        self.sample_rate = 16000  # Ultravox expects 16kHz audio
        self.max_new_tokens = max_new_tokens
        self.system_prompt = system_prompt
        self.enable_conversation_history = enable_conversation_history
        self.conversation_history_minutes = conversation_history_minutes

        self.llm_pipeline = None
        self.device = None
        self.torch_dtype = None

    async def initialize(self) -> None:
        """
        Load the model and processor. This runs on the execution environment (local or remote).
        """
        await super().initialize()
        
        # Only initialize if not already done
        if self.llm_pipeline is not None:
            logger.info("UltravoxNode already initialized, skipping.")
            return
            
        try:
            import torch
            from transformers import pipeline
        except ImportError:
            raise NodeError("Required ML libraries (torch, transformers, peft) are not installed on the execution environment.")

        if self._requested_device:
            self.device = self._requested_device
        elif torch.cuda.is_available():
            self.device = "cuda:0"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            self.device = "mps"
            if self._requested_torch_dtype == "bfloat16":
                self.torch_dtype = torch.bfloat16
        else:
            self.device = "cpu"

        if not self.torch_dtype:
            try:
                resolved_torch_dtype = getattr(torch, self._requested_torch_dtype)
            except AttributeError:
                raise NodeError(f"Invalid torch_dtype '{self._requested_torch_dtype}'")
            self.torch_dtype = resolved_torch_dtype if torch.cuda.is_available() else torch.float32
        
        logger.info(f"UltravoxNode configured for model '{self.model_id}' on device '{self.device}'")
        logger.info(f"Initializing Ultravox model '{self.model_id}'...")
        try:
            self.llm_pipeline = await asyncio.to_thread(
                pipeline,
                model=self.model_id,
                torch_dtype=self.torch_dtype,
                device=self.device,
                trust_remote_code=True
            )
            logger.info("Ultravox model initialized successfully.")
        except Exception as e:
            raise NodeError(f"Failed to initialize Ultravox model: {e}")

    async def _generate_response(self, audio_data: np.ndarray, session_id: Optional[str] = None, user_text: Optional[str] = None) -> Optional[str]:
        """Run model inference in a separate thread with conversation context."""
        logger.info(f"Generating response for {len(audio_data) / self.sample_rate:.2f}s of audio...")
        
        # Build conversation turns
        turns = [{"role": "system", "content": self.system_prompt}]
        
        # Get conversation history from state if enabled
        logger.info(f"Generating response for session ID: {session_id}, enable_conversation_history: {self.enable_conversation_history}")
        if self.enable_conversation_history and session_id:
            session_state = await self.get_session_state(session_id)
            if session_state:
                history = session_state.get('conversation_history', [])
                current_time = datetime.now()
                cutoff_time = current_time - timedelta(minutes=self.conversation_history_minutes)
                
                # Add previous conversation turns, filtering by time and formatting for model
                for msg in history:
                    if msg.get("role") != "system":  # Skip system messages as we already added it
                        # Check timestamp if present
                        if 'timestamp' in msg:
                            msg_time = datetime.fromisoformat(msg['timestamp'])
                            if msg_time >= cutoff_time:
                                # Add turn without timestamp for model (it doesn't need it)
                                turns.append({
                                    "role": msg["role"],
                                    "content": msg["content"]
                                })
                        else:
                            # Legacy message without timestamp - skip it
                            pass
                
                logger.info(f"UltravoxNode: Using {len(turns)} turns in conversation context for session {session_id} "
                            f"(from last {self.conversation_history_minutes} minutes)")
        
        try:
            # Include user text if provided (for hybrid audio+text input)
            input_data = {
                'audio': audio_data, 
                'turns': turns, 
                'sampling_rate': self.sample_rate
            }
            if user_text:
                input_data['text'] = user_text
            
            result = await asyncio.to_thread(
                self.llm_pipeline,
                input_data,
                max_new_tokens=self.max_new_tokens
            )
            logger.info(f"Ultravox result: {result}")
            
            # Extract response
            response = None
            if isinstance(result, list) and result and isinstance(result[0], dict) and 'generated_text' in result[0]:
                response = result[0]['generated_text']
            elif isinstance(result, str):
                response = result

            if not isinstance(response, str):
                logger.warning(f"Model did not return an expected string response. Full result: {result}")
                return None

            response = response.strip()
            logger.info(f"Ultravox generated response: '{response}'")
            
            # Add the interaction to history
            if self.enable_conversation_history and response and session_id:
                session_state = await self.get_session_state(session_id)
                if session_state:
                    history = session_state.get('conversation_history', [])
                    current_time = datetime.now()
                    
                    # Add new interaction with timestamps
                    history.append({
                        "role": "user", 
                        "content": user_text or f"[Audio input: {len(audio_data) / self.sample_rate:.1f}s]",
                        "timestamp": current_time.isoformat()
                    })
                    history.append({
                        "role": "assistant", 
                        "content": response,
                        "timestamp": current_time.isoformat()
                    })
                    
                    # Filter history to keep only recent messages within time window
                    cutoff_time = current_time - timedelta(minutes=self.conversation_history_minutes)
                    filtered_history = []
                    for msg in history:
                        # Handle messages with timestamps
                        if isinstance(msg, dict) and 'timestamp' in msg:
                            msg_time = datetime.fromisoformat(msg['timestamp'])
                            if msg_time >= cutoff_time:
                                filtered_history.append(msg)
                        else:
                            # Keep messages without timestamps (legacy) but don't include in turns
                            # This ensures backward compatibility
                            pass
                    
                    # Update state with filtered history
                    session_state.set('conversation_history', filtered_history)
                    logger.debug(f"UltravoxNode: Updated conversation history for session {session_id} "
                                f"(kept {len(filtered_history)} messages from last {self.conversation_history_minutes} minutes)")
            
            return response
        except Exception as e:
            logger.error(f"Error during Ultravox inference: {e}", exc_info=True)
            return None

    async def process(self, data_stream: AsyncGenerator[Any, None]) -> AsyncGenerator[Any, None]:
        """
        Process an incoming audio stream and yield generated text responses.
        Expects tuples of (numpy_array, sample_rate) or (numpy_array, sample_rate, metadata_dict).
        
        The node uses the built-in state management system to maintain conversation history
        per session. Session IDs can be provided in the metadata or extracted automatically.
        """
        if not self.llm_pipeline:
            raise NodeError("Ultravox pipeline is not initialized.")

        async for data in data_stream:
            logger.info(f"Processing data: {data}")
            audio_chunk = None
            sample_rate = None
            metadata = {}
            
            # Extract session ID from data
            session_id = self.extract_session_id(data)
            logger.info(f"Session ID: {session_id}")
            
            # Handle different input formats
            if isinstance(data, tuple):
                if len(data) == 2:
                    audio_chunk, sample_rate = data
                elif len(data) == 3:
                    audio_chunk, sample_rate, metadata = data
                else:
                    logger.warning(f"UltravoxNode received tuple of unexpected length {len(data)}, skipping.")
                    continue
            else:
                logger.warning(f"UltravoxNode received data of unexpected type {type(data)}, skipping.")
                continue

            if not isinstance(audio_chunk, np.ndarray):
                logger.warning(f"Received non-numpy audio_chunk of type {type(audio_chunk)}, skipping.")
                continue
            
            # Process metadata
            user_text = None
            if metadata:
                # Clear history if requested
                if metadata.get('clear_history', False) and session_id:
                    session_state = await self.get_session_state(session_id)
                    if session_state:
                        session_state.set('conversation_history', [])
                        logger.info(f"UltravoxNode: Cleared conversation history for session {session_id}")
                
                # Get any user text
                user_text = metadata.get('user_text')

            # Process the audio chunk
            audio_data = audio_chunk.flatten().astype(np.float32)
            if len(audio_data) > 0:
                response = await self._generate_response(audio_data, session_id, user_text)
                if response:
                    # Include state info in output if we have a session
                    if self.enable_conversation_history and session_id:
                        session_state = await self.get_session_state(session_id)
                        if session_state:
                            output_data = {
                                'response': response,
                                'session_id': session_id,
                                'conversation_length': len(session_state.get('conversation_history', []))
                            }
                            yield (response, output_data)
                        else:
                            yield (response,)
                    else:
                        yield (response,)

    async def flush(self) -> Optional[tuple]:
        """No buffering needed - flush is a no-op."""
        return None

    async def cleanup(self) -> None:
        """Clean up the model resources."""
        # Call parent cleanup which handles state cleanup
        await super().cleanup()
        
        # Clear model resources
        self.llm_pipeline = None
        self.device = None
        self.torch_dtype = None
        
        logger.info("UltravoxNode cleaned up.")


__all__ = ["UltravoxNode"] 