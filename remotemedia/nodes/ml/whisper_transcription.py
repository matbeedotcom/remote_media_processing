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
                 torch_dtype: str = "float16",
                 chunk_length_s: int = 30,
                 buffer_duration_s: int = 5,
                 **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.is_streaming = True
        self.model_id = model_id
        self._requested_device = device
        self._requested_torch_dtype = torch_dtype
        self.chunk_length_s = chunk_length_s
        self.sample_rate = 16000  # Whisper models expect 16kHz audio
        self.buffer_size = buffer_duration_s * self.sample_rate
        self.audio_buffer = np.array([], dtype=np.float32)

        self.transcription_pipeline = None
        self.device = None
        self.torch_dtype = None

    async def initialize(self) -> None:
        """
        Load the model and processor. This runs on the execution environment (local or remote).
        """
        await super().initialize()
        try:
            import torch
            from transformers import AutoModelForSpeechSeq2Seq, AutoProcessor, pipeline
        except ImportError:
            raise NodeError("Required ML libraries (torch, transformers) are not installed on the execution environment.")

        if self._requested_device:
            self.device = self._requested_device
        elif torch.cuda.is_available():
            self.device = "cuda:0"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            self.device = "mps"
        else:
            self.device = "cpu"

        try:
            resolved_torch_dtype = getattr(torch, self._requested_torch_dtype)
        except AttributeError:
            raise NodeError(f"Invalid torch_dtype '{self._requested_torch_dtype}'")
        self.torch_dtype = resolved_torch_dtype if torch.cuda.is_available() else torch.float32

        logger.info(f"WhisperNode configured for model '{self.model_id}' on device '{self.device}'")
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

        async for data in data_stream:
            if not isinstance(data, tuple) or len(data) != 2:
                logger.warning(f"WhisperNode received data of unexpected type or length {type(data)}, skipping.")
                continue
            
            audio_chunk, _ = data

            if not isinstance(audio_chunk, np.ndarray):
                logger.warning(f"Received non-numpy audio_chunk of type {type(audio_chunk)}, skipping.")
                continue

            # Append to buffer, ensuring the chunk is flattened to 1D.
            self.audio_buffer = np.concatenate([self.audio_buffer, audio_chunk.flatten().astype(np.float32)])

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
        self.device = None
        self.torch_dtype = None
        logger.info("WhisperNode cleaned up.")


__all__ = ["WhisperTranscriptionNode"] 