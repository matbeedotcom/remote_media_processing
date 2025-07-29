import asyncio
import numpy as np
import logging
from typing import Optional, Any, AsyncGenerator

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
                 **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.is_streaming = True
        self.model_id = model_id
        self._requested_device = device
        self._requested_torch_dtype = torch_dtype
        self.sample_rate = 16000  # Ultravox expects 16kHz audio
        self.max_new_tokens = max_new_tokens
        self.system_prompt = system_prompt

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

    async def _generate_response(self, audio_data: np.ndarray) -> Optional[str]:
        """Run model inference in a separate thread."""
        logger.info(f"Generating response for {len(audio_data) / self.sample_rate:.2f}s of audio...")
        turns = [{"role": "system", "content": self.system_prompt}]
        
        try:
            result = await asyncio.to_thread(
                self.llm_pipeline,
                {'audio': audio_data, 'turns': turns, 'sampling_rate': self.sample_rate},
                max_new_tokens=self.max_new_tokens
            )
            logger.info(f"Ultravox result: {result}")
            # The pipeline's output for this model can be a list containing a single dictionary
            # with 'generated_text', or just a raw string.
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
            return response
        except Exception as e:
            logger.error(f"Error during Ultravox inference: {e}", exc_info=True)
            return None

    async def process(self, data_stream: AsyncGenerator[Any, None]) -> AsyncGenerator[Any, None]:
        """
        Process an incoming audio stream and yield generated text responses.
        Expects tuples of (numpy_array, sample_rate).
        """
        if not self.llm_pipeline:
            raise NodeError("Ultravox pipeline is not initialized.")

        async for data in data_stream:
            if not isinstance(data, tuple) or len(data) != 2:
                logger.warning(f"UltravoxNode received data of unexpected type or length {type(data)}, skipping.")
                continue

            audio_chunk, _ = data

            if not isinstance(audio_chunk, np.ndarray):
                logger.warning(f"Received non-numpy audio_chunk of type {type(audio_chunk)}, skipping.")
                continue

            # Process the audio chunk immediately
            audio_data = audio_chunk.flatten().astype(np.float32)
            if len(audio_data) > 0:
                response = await self._generate_response(audio_data)
                if response:
                    yield (response,)

    async def flush(self) -> Optional[tuple]:
        """No buffering needed - flush is a no-op."""
        return None

    async def cleanup(self) -> None:
        """Clean up the model resources."""
        self.llm_pipeline = None
        self.device = None
        self.torch_dtype = None
        logger.info("UltravoxNode cleaned up.")


__all__ = ["UltravoxNode"] 