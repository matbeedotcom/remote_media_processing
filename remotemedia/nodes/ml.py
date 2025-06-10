import asyncio
import numpy as np
import logging
from typing import Optional, Any, AsyncGenerator

from remotemedia.core.node import Node, NodeError

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    import torch
    from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
except ImportError:
    logger.warning("ML libraries not found. WhisperTranscriptionNode will not be available.")
    torch = None
    pipeline = None


class WhisperTranscriptionNode(Node):
    """
    A node that performs real-time audio transcription using a Whisper model.
    """

    def __init__(self,
                 model_id: str = "openai/whisper-large-v3-turbo",
                 device: Optional[str] = None,
                 torch_dtype: Optional[str] = "float16",
                 chunk_length_s: int = 30,
                 buffer_duration_s: int = 5,
                 **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if not torch or not pipeline:
            raise NodeError("Required ML libraries (torch, transformers) are not installed.")

        self.is_streaming = True
        self.model_id = model_id
        self.device = device or ("cuda:0" if torch.cuda.is_available() else "cpu")
        self.torch_dtype = getattr(torch, torch_dtype) if torch.cuda.is_available() else torch.float32
        self.chunk_length_s = chunk_length_s
        self.sample_rate = 16000  # Whisper models expect 16kHz audio
        self.buffer_size = buffer_duration_s * self.sample_rate
        self.audio_buffer = np.array([], dtype=np.float32)

        self.transcription_pipeline = None
        logger.info(f"WhisperNode configured for model '{model_id}' on device '{self.device}'")

    async def initialize(self) -> None:
        """Load the model and processor."""
        logger.info(f"Initializing Whisper model '{self.model_id}'...")
        try:
            model = await asyncio.to_thread(
                AutoModelForSpeechSeq2Seq.from_pretrained,
                self.model_id,
                torch_dtype=self.torch_dtype,
                low_cpu_mem_usage=True,
                use_safetensors=True
            )
            model.to(self.device)

            processor = await asyncio.to_thread(AutoProcessor.from_pretrained, self.model_id)

            self.transcription_pipeline = pipeline(
                "automatic-speech-recognition",
                model=model,
                tokenizer=processor.tokenizer,
                feature_extractor=processor.feature_extractor,
                torch_dtype=self.torch_dtype,
                device=self.device,
                chunk_length_s=self.chunk_length_s,
            )
            logger.info("Whisper model initialized successfully.")
        except Exception as e:
            raise NodeError(f"Failed to initialize Whisper model: {e}")

    async def process(self, data_stream: AsyncGenerator[Any, None]) -> AsyncGenerator[Any, None]:
        """
        Process an incoming audio stream, buffer it, and yield transcriptions.
        Expects tuples of (numpy_array, sample_rate).
        """
        if not self.transcription_pipeline:
            raise NodeError("Transcription pipeline is not initialized.")

        async for audio_chunk, _ in data_stream:
            if not isinstance(audio_chunk, np.ndarray):
                logger.warning(f"Received non-numpy data of type {type(audio_chunk)}, skipping.")
                continue

            # Append to buffer
            self.audio_buffer = np.concatenate([self.audio_buffer, audio_chunk.astype(np.float32)])

            # If buffer is full, transcribe
            while len(self.audio_buffer) >= self.buffer_size:
                segment_to_process = self.audio_buffer[:self.buffer_size]
                self.audio_buffer = self.audio_buffer[self.buffer_size:]

                try:
                    logger.info(f"Transcribing {len(segment_to_process) / self.sample_rate:.2f}s of audio...")
                    result = await asyncio.to_thread(self.transcription_pipeline, segment_to_process.copy())
                    transcribed_text = result["text"].strip()
                    if transcribed_text:
                        logger.info(f"Transcription result: '{transcribed_text}'")
                        yield (transcribed_text,)
                except Exception as e:
                    logger.error(f"Error during transcription: {e}")

    async def cleanup(self) -> None:
        """Transcribe any remaining audio in the buffer."""
        if self.transcription_pipeline and len(self.audio_buffer) > 0:
            logger.info(f"Cleaning up and transcribing remaining {len(self.audio_buffer) / self.sample_rate:.2f}s of audio...")
            try:
                result = await asyncio.to_thread(self.transcription_pipeline, self.audio_buffer.copy())
                transcribed_text = result["text"].strip()
                if transcribed_text:
                    logger.info(f"Final transcription result: '{transcribed_text}'")
                    # In a real scenario, we might want to push this last result to a final queue
            except Exception as e:
                logger.error(f"Error during final transcription: {e}")
        self.audio_buffer = np.array([], dtype=np.float32)
        self.transcription_pipeline = None
        logger.info("WhisperNode cleaned up.")


class UltravoxNode(Node):
    """
    A node that uses the Ultravox model for multimodal audio/text to text generation.
    It receives audio chunks and, after buffering a set duration, processes the
    buffered audio along with a text prompt to generate a text response.
    """

    def __init__(self,
                 model_id: str = "fixie-ai/ultravox-v0_5-llama-3_2-1b",
                 device: Optional[str] = None,
                 torch_dtype: Optional[str] = "float16",
                 buffer_duration_s: float = 5.0,
                 max_new_tokens: int = 100,
                 system_prompt: str = "You are a friendly and helpful AI assistant.",
                 **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if not torch or not pipeline:
            raise NodeError("Required ML libraries (torch, transformers, peft) are not installed.")

        self.model_id = model_id
        self.device = device or ("cuda:0" if torch.cuda.is_available() else "cpu")
        self.torch_dtype = getattr(torch, torch_dtype) if torch.cuda.is_available() else torch.float32
        self.buffer_duration_s = buffer_duration_s
        self.sample_rate = 16000  # Ultravox expects 16kHz audio
        self.buffer_size = int(buffer_duration_s * self.sample_rate)
        self.max_new_tokens = max_new_tokens
        self.system_prompt = system_prompt

        self.llm_pipeline = None
        self.audio_buffer = np.array([], dtype=np.float32)
        logger.info(f"UltravoxNode configured for model '{model_id}' on device '{self.device}'")

    async def initialize(self) -> None:
        """Load the model and processor."""
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
            # The pipeline returns the full conversation history. We want the last message from the assistant.
            last_turn = result[0]['generated_text'][-1]
            if last_turn['role'] == 'assistant':
                response = last_turn['content'].strip()
                logger.info(f"Ultravox generated response: '{response}'")
                return response
            else:
                logger.warning("Model did not return an assistant message as the last turn.")
                return None
        except Exception as e:
            logger.error(f"Error during Ultravox inference: {e}", exc_info=True)
            return None

    async def process(self, data_stream: AsyncGenerator[Any, None]) -> AsyncGenerator[Any, None]:
        """
        Process an incoming audio stream, buffer it, and yield generated text responses.
        Expects tuples of (numpy_array, sample_rate).
        """
        if not self.llm_pipeline:
            raise NodeError("Ultravox pipeline is not initialized.")

        async for audio_chunk, _ in data_stream:
            if not isinstance(audio_chunk, np.ndarray):
                logger.warning(f"Received non-numpy data of type {type(audio_chunk)}, skipping.")
                continue

            self.audio_buffer = np.concatenate([self.audio_buffer, audio_chunk.astype(np.float32)])

            while len(self.audio_buffer) >= self.buffer_size:
                segment_to_process = self.audio_buffer[:self.buffer_size]
                self.audio_buffer = self.audio_buffer[self.buffer_size:]

                response = await self._generate_response(segment_to_process.copy())
                if response:
                    yield (response,)

    async def cleanup(self) -> None:
        """Process any remaining audio in the buffer before shutting down."""
        if self.llm_pipeline and len(self.audio_buffer) > 0:
            logger.info(f"Cleaning up and processing remaining {len(self.audio_buffer) / self.sample_rate:.2f}s of audio...")
            response = await self._generate_response(self.audio_buffer.copy())
            if response:
                # This response will be yielded if the pipeline is still being iterated
                pass
        self.audio_buffer = np.array([], dtype=np.float32)
        self.llm_pipeline = None
        logger.info("UltravoxNode cleaned up.") 