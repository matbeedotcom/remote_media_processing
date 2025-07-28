#!/usr/bin/env python3
"""
VAD-triggered Ultravox that processes complete utterances.

This version ensures Ultravox processes the entire speech segment at once,
not just its internal buffer size.
"""

import asyncio
import logging
import numpy as np
import os
import sys
from pathlib import Path
from typing import AsyncGenerator, Any, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from remotemedia.core.pipeline import Pipeline
from remotemedia.core.node import RemoteExecutorConfig, Node
from remotemedia.nodes.source import MediaReaderNode, AudioTrackSource
from remotemedia.nodes.audio import AudioTransform, VoiceActivityDetector
from remotemedia.nodes.remote import RemoteObjectExecutionNode
from remotemedia.nodes import PassThroughNode

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Reduce noise from some loggers
logging.getLogger("Pipeline").setLevel(logging.INFO)
logging.getLogger("remotemedia.nodes.remote").setLevel(logging.INFO)


class CompleteUtteranceUltravoxNode(Node):
    """
    A custom Ultravox node that processes complete utterances at once.
    
    This bypasses the internal buffering of UltravoxNode to ensure the entire
    speech segment is processed as a single unit.
    """
    
    def __init__(
        self,
        model_id: str = "fixie-ai/ultravox-v0_5-llama-3_1-8b",
        system_prompt: str = "You are a helpful assistant.",
        min_duration_s: float = 1.0,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.model_id = model_id
        self.system_prompt = system_prompt
        self.min_duration_s = min_duration_s
        self.llm_pipeline = None
        
    async def initialize(self):
        """Initialize the Ultravox model."""
        try:
            import torch
            from transformers import pipeline
            
            # Initialize model
            logger.info(f"Initializing Ultravox model '{self.model_id}'...")
            
            device = "cuda:0" if torch.cuda.is_available() else "cpu"
            torch_dtype = torch.bfloat16 if device == "cuda:0" else torch.float32
            
            self.llm_pipeline = pipeline(
                "audio-text-generation",
                model=self.model_id,
                device=device,
                torch_dtype=torch_dtype
            )
            
            logger.info(f"Ultravox model initialized on {device}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Ultravox: {e}")
            raise
            
    async def cleanup(self):
        """Cleanup resources."""
        self.llm_pipeline = None
        logger.info("CompleteUtteranceUltravoxNode cleaned up.")
        
    def process(self, data: Tuple[np.ndarray, int]) -> Optional[str]:
        """
        Process a complete audio utterance.
        
        Args:
            data: Tuple of (audio_array, sample_rate)
            
        Returns:
            Generated text response
        """
        if not isinstance(data, tuple) or len(data) != 2:
            logger.warning(f"Invalid input format: {type(data)}")
            return None
            
        audio_data, sample_rate = data
        
        if not isinstance(audio_data, np.ndarray):
            logger.warning(f"Invalid audio data type: {type(audio_data)}")
            return None
            
        # Flatten audio if needed
        if audio_data.ndim > 1:
            audio_data = audio_data.flatten()
            
        duration_s = len(audio_data) / sample_rate
        
        # Check minimum duration
        if duration_s < self.min_duration_s:
            logger.warning(
                f"Audio too short: {duration_s:.2f}s < {self.min_duration_s:.2f}s minimum"
            )
            return None
            
        logger.info(f"Processing complete utterance: {duration_s:.2f}s of audio")
        
        try:
            # Generate response for the complete utterance
            prompt = f"<|user|>\n{self.system_prompt}<|end|>\n<|assistant|>\n"
            
            result = self.llm_pipeline(
                {
                    "audio": audio_data.astype(np.float32),
                    "text": prompt,
                    "sampling_rate": sample_rate
                },
                max_new_tokens=256
            )
            
            generated_text = result["generated_text"]
            response = generated_text.split("<|assistant|>\n")[-1].strip()
            
            logger.info(f"Generated response: {response[:100]}...")
            return response
            
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return None


class VADTriggeredBuffer(Node):
    """
    Accumulates speech segments and outputs complete utterances.
    """
    
    def __init__(
        self,
        min_speech_duration_s: float = 1.0,
        max_speech_duration_s: float = 10.0,
        silence_duration_s: float = 1.0,
        sample_rate: int = 16000,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.min_speech_duration_s = min_speech_duration_s
        self.max_speech_duration_s = max_speech_duration_s
        self.silence_duration_s = silence_duration_s
        self.sample_rate = sample_rate
        self.is_streaming = True
        
        # State
        self._speech_buffer = None
        self._is_in_speech = False
        self._silence_accumulated_samples = 0
        
        # Derived
        self.min_samples = int(min_speech_duration_s * sample_rate)
        self.max_samples = int(max_speech_duration_s * sample_rate)
        self.silence_samples = int(silence_duration_s * sample_rate)
        
    async def process(self, data_stream: AsyncGenerator[Any, None]) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
        """Process VAD-annotated stream and output complete utterances."""
        async for data in data_stream:
            if not isinstance(data, tuple) or len(data) != 2:
                continue
                
            # Parse VAD output
            item1, item2 = data
            if isinstance(item2, dict) and isinstance(item1, tuple) and len(item1) == 2:
                audio_data, sample_rate = item1
                vad_metadata = item2
            else:
                continue
                
            if not isinstance(audio_data, np.ndarray) or sample_rate != self.sample_rate:
                continue
                
            # Flatten audio
            audio_flat = audio_data.flatten() if audio_data.ndim > 1 else audio_data
            is_speech = vad_metadata.get("is_speech", False)
            
            if is_speech:
                # Handle speech
                if not self._is_in_speech:
                    logger.info("Speech started")
                    self._is_in_speech = True
                    self._speech_buffer = audio_flat.copy()
                else:
                    self._speech_buffer = np.concatenate([self._speech_buffer, audio_flat])
                    
                # Reset silence counter
                self._silence_accumulated_samples = 0
                
                # Check max duration
                if len(self._speech_buffer) >= self.max_samples:
                    duration_s = len(self._speech_buffer) / self.sample_rate
                    logger.info(f"Max duration reached: {duration_s:.2f}s")
                    yield (self._speech_buffer, self.sample_rate)
                    self._reset_state()
                    
            else:
                # Handle silence
                if self._is_in_speech and self._speech_buffer is not None:
                    # Add silence to buffer to maintain continuity
                    silence_chunk = np.zeros(len(audio_flat), dtype=np.float32)
                    self._speech_buffer = np.concatenate([self._speech_buffer, silence_chunk])
                    
                    # Accumulate silence
                    self._silence_accumulated_samples += len(audio_flat)
                    
                    # Check if enough silence to trigger
                    if self._silence_accumulated_samples >= self.silence_samples:
                        duration_s = len(self._speech_buffer) / self.sample_rate
                        
                        if len(self._speech_buffer) >= self.min_samples:
                            logger.info(f"Speech ended: {duration_s:.2f}s utterance")
                            yield (self._speech_buffer, self.sample_rate)
                        else:
                            logger.info(f"Speech too short: {duration_s:.2f}s")
                            
                        self._reset_state()
                        
    def _reset_state(self):
        """Reset buffer state."""
        self._speech_buffer = None
        self._is_in_speech = False
        self._silence_accumulated_samples = 0


class PrintResponseNode(PassThroughNode):
    """Print Ultravox responses."""
    
    def process(self, data):
        """Print response."""
        if data:
            print(f"\n🎤 ULTRAVOX: {data}\n")
        return data


async def main():
    """Run the complete utterance pipeline."""
    REMOTE_HOST = os.environ.get("REMOTE_HOST", "127.0.0.1")
    logger.info("=== Complete Utterance Ultravox Pipeline ===")
    
    demo_audio_path = "examples/audio.wav"
    
    pipeline = Pipeline()
    
    # Audio source
    pipeline.add_node(MediaReaderNode(
        path=demo_audio_path,
        chunk_size=4096,
        name="MediaReader"
    ))
    
    pipeline.add_node(AudioTrackSource(name="AudioTrackSource"))
    
    # Resample to 16kHz
    pipeline.add_node(AudioTransform(
        output_sample_rate=16000,
        output_channels=1,
        name="AudioTransform"
    ))
    
    # VAD
    vad = VoiceActivityDetector(
        frame_duration_ms=30,
        energy_threshold=0.02,
        speech_threshold=0.3,
        filter_mode=False,
        include_metadata=True,
        name="VAD"
    )
    vad.is_streaming = True
    pipeline.add_node(vad)
    
    # VAD-triggered buffer
    vad_buffer = VADTriggeredBuffer(
        min_speech_duration_s=1.0,
        max_speech_duration_s=10.0,
        silence_duration_s=1.0,
        sample_rate=16000,
        name="VADBuffer"
    )
    vad_buffer.is_streaming = True
    pipeline.add_node(vad_buffer)
    
    # Complete utterance Ultravox
    ultravox = CompleteUtteranceUltravoxNode(
        model_id="fixie-ai/ultravox-v0_5-llama-3_1-8b",
        system_prompt="You are a helpful assistant. Listen and respond concisely.",
        min_duration_s=1.0,
        name="Ultravox"
    )
    
    # Remote execution
    remote_config = RemoteExecutorConfig(host=REMOTE_HOST, port=50052, ssl_enabled=False)
    remote_node = RemoteObjectExecutionNode(
        obj_to_execute=ultravox,
        remote_config=remote_config,
        name="RemoteUltravox"
    )
    pipeline.add_node(remote_node)
    
    # Print responses
    pipeline.add_node(PrintResponseNode(name="Print"))
    
    logger.info("Starting pipeline...")
    async with pipeline.managed_execution():
        try:
            response_count = 0
            async for result in pipeline.process():
                response_count += 1
            logger.info(f"Completed with {response_count} responses")
        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            raise


if __name__ == "__main__":
    asyncio.run(main())