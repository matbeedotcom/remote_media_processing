import asyncio
import numpy as np
import logging
from typing import Optional, Any, AsyncGenerator, Dict

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


class UltravoxNode(Node):
    """
    A node that uses the Ultravox model for multimodal audio/text to text generation.
    It receives audio chunks and, after buffering a set duration, processes the
    buffered audio along with a text prompt to generate a text response.
    """

    def __init__(self,
                 model_id: str = "fixie-ai/ultravox-v0_5-llama-3_2-1b",
                 device: Optional[str] = None,
                 torch_dtype: str = "bfloat16",
                 buffer_duration_s: float = 5.0,
                 max_new_tokens: int = 100,
                 system_prompt: str = "You are a friendly and helpful AI assistant.",
                 **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.is_streaming = True
        self.model_id = model_id
        self._requested_device = device
        self._requested_torch_dtype = torch_dtype
        self.buffer_duration_s = buffer_duration_s
        self.sample_rate = 16000  # Ultravox expects 16kHz audio
        self.buffer_size = int(buffer_duration_s * self.sample_rate)
        self.max_new_tokens = max_new_tokens
        self.system_prompt = system_prompt

        self.llm_pipeline = None
        self.device = None
        self.torch_dtype = None
        self.audio_buffer = np.array([], dtype=np.float32)

    async def initialize(self) -> None:
        """
        Load the model and processor. This runs on the execution environment (local or remote).
        """
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
            # The pipeline's output for this model is a list containing a single dictionary,
            # where 'generated_text' holds the final response string.
            if not (isinstance(result, list) and result and
                    isinstance(result[0], dict) and 'generated_text' in result[0]):
                logger.warning(f"Model did not return an expected response format. Full result: {result}")
                return None

            response = result[0]['generated_text']
            if not isinstance(response, str):
                logger.warning(f"Expected 'generated_text' to be a string, but got {type(response)}. Full result: {result}")
                return None

            response = response.strip()
            logger.info(f"Ultravox generated response: '{response}'")
            return response
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

        async for data in data_stream:
            if not isinstance(data, tuple) or len(data) != 2:
                logger.warning(f"UltravoxNode received data of unexpected type or length {type(data)}, skipping.")
                continue

            audio_chunk, _ = data

            if not isinstance(audio_chunk, np.ndarray):
                logger.warning(f"Received non-numpy audio_chunk of type {type(audio_chunk)}, skipping.")
                continue

            self.audio_buffer = np.concatenate([self.audio_buffer, audio_chunk.flatten().astype(np.float32)])

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
        self.device = None
        self.torch_dtype = None
        logger.info("UltravoxNode cleaned up.")


class TransformersPipelineNode(Node):
    """
    A generic node that wraps a Hugging Face Transformers pipeline.

    This node can be configured to run various tasks like text-classification,
    automatic-speech-recognition, etc., by leveraging the `transformers.pipeline`
    factory.

    See: https://huggingface.co/docs/transformers/main_classes/pipelines
    """

    def __init__(
        self,
        task: str,
        model: Optional[str] = None,
        device: Optional[Any] = None,
        model_kwargs: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        """
        Initializes the TransformersPipelineNode.

        Args:
            task (str): The task for the pipeline (e.g., "text-classification").
            model (str, optional): The model identifier from the Hugging Face Hub.
            device (Any, optional): The device to run the model on (e.g., "cpu", "cuda", 0).
                                    If None, automatically selects GPU if available.
            model_kwargs (Dict[str, Any], optional): Extra keyword arguments for the model.
            **kwargs: Additional node parameters.
        """
        super().__init__(**kwargs)
        if not task:
            raise ValueError("The 'task' argument is required.")

        self.task = task
        self.model = model
        self.device = device
        self.model_kwargs = model_kwargs or {}
        self.pipe = None

    async def initialize(self):
        """
        Initializes the underlying `transformers` pipeline.

        This method handles heavy imports and model downloading, making it suitable
        for execution on a remote server.
        """
        self.logger.info(f"Initializing node '{self.name}'...")
        try:
            from transformers import pipeline
            import torch
        except ImportError:
            raise NodeError(
                "TransformersPipelineNode requires `transformers` and `torch`. "
                "Please install them, e.g., `pip install transformers torch`."
            )

        if self.device is None:
            if torch.cuda.is_available():
                self.device = "cuda:0"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                self.device = "mps"
            else:
                self.device = "cpu"
        
        self.logger.info(
            f"Loading transformers pipeline for task '{self.task}'"
            f" with model '{self.model or 'default'}' on device '{self.device}'."
        )

        try:
            # This can be a slow, blocking operation (e.g., downloading a model)
            self.pipe = await asyncio.to_thread(
                pipeline,
                task=self.task,
                model=self.model,
                device=self.device,
                **self.model_kwargs,
            )
        except Exception as e:
            raise NodeError(f"Failed to load transformers pipeline: {e}") from e

        self.logger.info(f"Node '{self.name}' initialized successfully.")

    async def process(self, data: Any) -> Any:
        """
        Processes a single data item using the loaded pipeline.

        This method is designed to be thread-safe and non-blocking.

        Args:
            data: The single input data item to be processed by the pipeline.

        Returns:
            The processing result.
        """
        if not self.pipe:
            raise NodeError("Pipeline not initialized. Call initialize() first.")

        # The pipeline call can be blocking, so run it in a thread
        result = await asyncio.to_thread(self.pipe, data)
        return result

    async def cleanup(self):
        """Cleans up the pipeline and associated resources."""
        self.logger.info(f"Cleaning up node '{self.name}'.")

        if hasattr(self, "pipe") and self.pipe is not None:
            # Check if the pipeline was on a CUDA device before deleting it
            is_cuda = hasattr(self.pipe, "device") and "cuda" in str(self.pipe.device)

            del self.pipe
            self.pipe = None

            if is_cuda:
                try:
                    import torch
                    torch.cuda.empty_cache()
                    self.logger.debug("Cleared CUDA cache.")
                except (ImportError, AttributeError):
                    pass  # Should not happen if initialize succeeded on CUDA
                except Exception as e:
                    self.logger.warning(f"Could not clear CUDA cache: {e}")


__all__ = ["WhisperTranscriptionNode", "UltravoxNode", "TransformersPipelineNode"] 