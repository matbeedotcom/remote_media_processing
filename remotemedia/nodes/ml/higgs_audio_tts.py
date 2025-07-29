"""
Higgs Audio TTS Node for high-quality text-to-speech synthesis.
"""

import logging
import numpy as np
from typing import Any, AsyncGenerator, Optional, Union, Tuple, List, Dict
import asyncio
import torch

from ...core.node import Node
from ...core.exceptions import NodeError

logger = logging.getLogger(__name__)


class HiggsAudioTTSNode(Node):
    """
    Text-to-speech synthesis using Higgs Audio V2.
    
    Higgs Audio is a 5.77B parameter model that supports expressive audio generation,
    multilingual synthesis, and zero-shot voice cloning.
    """
    
    def __init__(
        self,
        model_path: str = "bosonai/higgs-audio-v2-generation-3B-base",
        tokenizer_path: str = "bosonai/higgs-audio-v2-tokenizer",
        system_prompt: str = "Generate audio following instruction.",
        max_new_tokens: int = 1024,
        temperature: float = 0.3,
        sample_rate: int = 16000,
        device: Optional[str] = None,
        torch_dtype: str = "float16",
        ref_audio_path: Optional[str] = None,
        **kwargs
    ):
        """
        Initialize Higgs Audio TTS node.
        
        Args:
            model_path: Path to the Higgs Audio model
            tokenizer_path: Path to the audio tokenizer
            system_prompt: System prompt for generation
            max_new_tokens: Maximum number of tokens to generate
            temperature: Generation temperature (lower = more deterministic)
            sample_rate: Output sample rate (default: 16000)
            device: Device to run on (cuda/cpu/mps, auto-detects if None)
            torch_dtype: Torch data type for model (float16/float32/bfloat16)
            ref_audio_path: Optional reference audio for voice cloning
        """
        super().__init__(**kwargs)
        self.model_path = model_path
        self.tokenizer_path = tokenizer_path
        self.system_prompt = system_prompt
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.sample_rate = sample_rate
        self._requested_device = device
        self._requested_torch_dtype = torch_dtype
        self.ref_audio_path = ref_audio_path
        self.is_streaming = True
        
        self._serve_engine = None
        self._initialized = False
        self.device = None
        self.torch_dtype = None
        
    async def initialize(self) -> None:
        """Initialize the Higgs Audio TTS engine."""
        if self._initialized:
            return
            
        try:
            # Import dependencies
            try:
                from boson_multimodal.serve.serve_engine import HiggsAudioServeEngine
                from boson_multimodal.data_types import ChatMLSample, Message
                import torchaudio
                self._ChatMLSample = ChatMLSample
                self._Message = Message
                self._torchaudio = torchaudio
            except ImportError as e:
                raise NodeError(
                    "Higgs Audio dependencies are not installed. Please install with:\n"
                    "git clone https://github.com/boson-ai/higgs-audio.git && "
                    "cd higgs-audio && pip install -r requirements.txt && pip install -e ."
                ) from e
            
            # Determine device
            if self._requested_device:
                self.device = self._requested_device
            elif torch.cuda.is_available():
                self.device = "cuda:0"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                self.device = "mps"
            else:
                self.device = "cpu"
                
            # Set torch dtype
            try:
                self.torch_dtype = getattr(torch, self._requested_torch_dtype)
            except AttributeError:
                raise NodeError(f"Invalid torch_dtype '{self._requested_torch_dtype}'")
            
            logger.info(f"Initializing Higgs Audio TTS on device='{self.device}' with dtype={self._requested_torch_dtype}")
            
            # Initialize the serve engine in a thread to avoid blocking
            self._serve_engine = await asyncio.to_thread(
                HiggsAudioServeEngine,
                self.model_path,
                self.tokenizer_path,
                device=self.device,
                torch_dtype=self.torch_dtype
            )
            
            # Load reference audio if provided
            if self.ref_audio_path:
                try:
                    self._ref_audio, self._ref_sample_rate = await asyncio.to_thread(
                        self._torchaudio.load, self.ref_audio_path
                    )
                    logger.info(f"Loaded reference audio from {self.ref_audio_path}")
                except Exception as e:
                    logger.warning(f"Failed to load reference audio: {e}")
                    self._ref_audio = None
                    self._ref_sample_rate = None
            else:
                self._ref_audio = None
                self._ref_sample_rate = None
            
            self._initialized = True
            logger.info("Higgs Audio TTS engine initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Higgs Audio TTS: {e}")
            raise
            
        await super().initialize()
    
    async def cleanup(self) -> None:
        """Clean up the TTS engine."""
        if self._serve_engine is not None:
            # Clean up the engine
            self._serve_engine = None
            self._initialized = False
            self._ref_audio = None
            self._ref_sample_rate = None
            logger.info("Higgs Audio TTS engine cleaned up")
        await super().cleanup()
    
    async def process(self, data: Any) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
        """
        Process text input and generate speech audio.
        
        Args:
            data: Text string or stream of text strings to synthesize
            
        Yields:
            Audio data as numpy array with sample rate tuples
        """
        if not self._initialized:
            await self.initialize()
            
        if hasattr(data, '__aiter__'):
            # Handle streaming input
            async for result in self._process_stream(data):
                yield result
        else:
            # Handle single text input
            result = await self._process_single(data)
            if result:
                yield result
    
    async def _process_stream(self, data_stream: AsyncGenerator[Any, None]) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
        """Process a stream of text inputs."""
        async for text_data in data_stream:
            # Extract text from various input formats
            text = self._extract_text(text_data)
            if text:
                logger.info(f"🎤 Higgs Audio TTS: Starting synthesis for text: '{text[:100]}{'...' if len(text) > 100 else ''}'")
                
                # Generate audio for this text
                audio_result = await self._synthesize(text)
                if audio_result:
                    duration = audio_result[0].shape[-1] / self.sample_rate
                    logger.info(f"🎤 Higgs Audio TTS: Generated audio: {duration:.2f}s")
                    yield audio_result
    
    async def _process_single(self, data: Any) -> Optional[Tuple[np.ndarray, int]]:
        """Process a single text input."""
        text = self._extract_text(data)
        if not text:
            return None
            
        return await self._synthesize(text)
    
    def _extract_text(self, data: Any) -> Optional[str]:
        """Extract text from various input formats."""
        if isinstance(data, str):
            return data
        elif isinstance(data, tuple) and len(data) > 0:
            # Handle (text, metadata) tuples
            return str(data[0]) if data[0] else None
        elif hasattr(data, 'get') and 'text' in data:
            # Handle dict with text field
            return data.get('text')
        elif hasattr(data, 'text'):
            # Handle objects with text attribute
            return getattr(data, 'text', None)
        else:
            # Try to convert to string
            try:
                text = str(data).strip()
                return text if text else None
            except:
                logger.warning(f"Could not extract text from data: {type(data)}")
                return None
    
    async def _synthesize(self, text: str) -> Optional[Tuple[np.ndarray, int]]:
        """Generate audio for the given text."""
        try:
            logger.info(f"🎤 Higgs Audio TTS: Synthesizing: '{text[:50]}{'...' if len(text) > 50 else ''}'")
            
            # Create messages for the model
            messages = [
                self._Message(role="system", content=self.system_prompt),
                self._Message(role="user", content=text)
            ]
            
            # Create ChatML sample
            chat_ml_sample = self._ChatMLSample(messages=messages)
            
            # Add reference audio if available
            generation_kwargs = {
                "chat_ml_sample": chat_ml_sample,
                "max_new_tokens": self.max_new_tokens,
                "temperature": self.temperature
            }
            
            if self._ref_audio is not None:
                generation_kwargs["ref_audio"] = self._ref_audio
                generation_kwargs["ref_sample_rate"] = self._ref_sample_rate
            
            # Run generation in a thread to avoid blocking
            output = await asyncio.to_thread(
                self._serve_engine.generate,
                **generation_kwargs
            )
            
            # Convert output audio to numpy array
            if hasattr(output, 'audio') and output.audio is not None:
                audio = output.audio
                
                # Ensure audio is a numpy array
                if not isinstance(audio, np.ndarray):
                    if torch.is_tensor(audio):
                        audio = audio.numpy()
                    else:
                        audio = np.array(audio, dtype=np.float32)
                
                # Ensure proper shape (1, samples) for mono audio
                if audio.ndim == 1:
                    audio = audio.reshape(1, -1)
                elif audio.ndim > 2:
                    # If multi-channel, take first channel
                    audio = audio[0].reshape(1, -1)
                
                # Get sampling rate from output or use default
                sample_rate = getattr(output, 'sampling_rate', self.sample_rate)
                
                duration = audio.shape[-1] / sample_rate
                logger.info(f"🎤 Higgs Audio TTS: Generated {duration:.2f}s of audio at {sample_rate}Hz")
                
                return (audio, sample_rate)
            else:
                logger.warning("Higgs Audio TTS: No audio generated")
                return None
                
        except Exception as e:
            logger.error(f"Error during Higgs Audio TTS synthesis: {e}")
            raise
    
    def get_config(self) -> dict:
        """Get node configuration."""
        config = super().get_config()
        config.update({
            "model_path": self.model_path,
            "tokenizer_path": self.tokenizer_path,
            "system_prompt": self.system_prompt,
            "max_new_tokens": self.max_new_tokens,
            "temperature": self.temperature,
            "sample_rate": self.sample_rate,
            "device": self._requested_device,
            "torch_dtype": self._requested_torch_dtype,
            "ref_audio_path": self.ref_audio_path,
        })
        return config


__all__ = ["HiggsAudioTTSNode"]