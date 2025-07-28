#!/usr/bin/env python3
"""
VAD-triggered Ultravox: Generate responses only when speech ends.

This example demonstrates how to use VAD to trigger Ultravox generation only when:
1. At least 1 second of speech has been accumulated
2. VAD detects the end of speech (silence)

This prevents interrupting ongoing speech and ensures complete utterances.

**TO RUN THIS EXAMPLE:**

1.  **Install ML dependencies:**
    $ pip install -r requirements-ml.txt

2.  **Start the server:**
    $ PYTHONPATH=. python remote_service/src/server.py

3.  **Run this script:**
    $ python examples/remote_ultravox_vad_triggered.py
"""

import asyncio
import logging
import numpy as np
import soundfile as sf
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
from remotemedia.nodes.ml import UltravoxNode
from remotemedia.nodes import PassThroughNode

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Reduce noise from some loggers
logging.getLogger("Pipeline").setLevel(logging.INFO)
logging.getLogger("remotemedia.nodes.remote").setLevel(logging.INFO)


class VADTriggeredBuffer(Node):
    """
    A buffer that accumulates speech audio and triggers output only when speech ends.
    
    This node:
    1. Accumulates audio chunks that contain speech
    2. Tracks speech/silence state transitions
    3. Outputs accumulated speech audio only when:
       - Speech ends (VAD transitions to silence)
       - At least minimum duration of speech was accumulated
    """
    
    def __init__(
        self,
        min_speech_duration_s: float = 1.0,
        max_speech_duration_s: float = 10.0,
        silence_duration_s: float = 0.5,
        sample_rate: int = 16000,
        **kwargs
    ):
        """
        Initialize the VAD-triggered buffer.
        
        Args:
            min_speech_duration_s: Minimum speech duration before triggering (default: 1.0s)
            max_speech_duration_s: Maximum speech duration (forces trigger, default: 10.0s)
            silence_duration_s: Duration of silence needed to confirm speech end (default: 0.5s)
            sample_rate: Expected audio sample rate (default: 16000)
        """
        super().__init__(**kwargs)
        self.min_speech_duration_s = min_speech_duration_s
        self.max_speech_duration_s = max_speech_duration_s
        self.silence_duration_s = silence_duration_s
        self.sample_rate = sample_rate
        self.is_streaming = True
        
        # State tracking
        self._speech_buffer = None
        self._speech_start_time = None
        self._last_speech_time = None
        self._is_in_speech = False
        self._silence_buffer = None
        self._silence_accumulated_samples = 0
        
        # Derived parameters
        self.min_samples = int(min_speech_duration_s * sample_rate)
        self.max_samples = int(max_speech_duration_s * sample_rate)
        self.silence_samples = int(silence_duration_s * sample_rate)
        
    async def process(self, data_stream: AsyncGenerator[Any, None]) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
        """
        Process VAD-annotated audio stream and trigger output on speech end.
        
        Expected input: ((audio_data, sample_rate), vad_metadata) tuples
        """
        async for data in data_stream:
            # Debug the data format
            logger.debug(f"VADTriggeredBuffer: Received data type: {type(data)}")
            
            if not isinstance(data, tuple) or len(data) != 2:
                logger.warning(f"VADTriggeredBuffer: Invalid input format: {type(data)}, len: {len(data) if hasattr(data, '__len__') else 'N/A'}")
                continue
                
            # The VAD output format is: ((audio_data, sample_rate), vad_metadata)
            item1, item2 = data
            
            if isinstance(item2, dict):
                # Correct format: ((audio_data, sample_rate), vad_metadata)
                if isinstance(item1, tuple) and len(item1) == 2:
                    audio_data, sample_rate = item1
                    vad_metadata = item2
                else:
                    logger.warning(f"VADTriggeredBuffer: Expected (audio_data, sample_rate) tuple, got {type(item1)}")
                    continue
            else:
                logger.warning(f"VADTriggeredBuffer: Expected VAD metadata dict as second item, got {type(item2)}")
                continue
                
            if not isinstance(audio_data, np.ndarray):
                logger.warning(f"VADTriggeredBuffer: Expected numpy array audio, got {type(audio_data)}")
                continue
                
            # Ensure consistent sample rate
            if sample_rate != self.sample_rate:
                logger.warning(f"VADTriggeredBuffer: Sample rate mismatch: {sample_rate} vs {self.sample_rate}")
                continue
                
            # Flatten audio to 1D for processing
            if audio_data.ndim > 1:
                audio_flat = audio_data.flatten()
            else:
                audio_flat = audio_data
                
            is_speech = vad_metadata.get("is_speech", False)
            speech_ratio = vad_metadata.get("speech_ratio", 0.0)
            avg_energy = vad_metadata.get("avg_energy", 0.0)
            chunk_samples = len(audio_flat)
            
            logger.info(f"VADTriggeredBuffer: is_speech={is_speech}, ratio={speech_ratio:.2f}, energy={avg_energy:.4f}, samples={chunk_samples}, buffer_size={len(self._speech_buffer) if self._speech_buffer is not None else 0}")
            
            # Process based on speech state
            if is_speech:
                triggered_audio = await self._handle_speech_chunk(audio_flat, chunk_samples)
                if triggered_audio is not None:
                    logger.info(
                        f"VADTriggeredBuffer: Triggering on max duration "
                        f"({len(triggered_audio)/self.sample_rate:.2f}s of speech)"
                    )
                    yield (triggered_audio.reshape(1, -1), self.sample_rate)
            else:
                # Check if we should trigger on silence
                triggered_audio = await self._handle_silence_chunk(chunk_samples)
                if triggered_audio is not None:
                    logger.info(
                        f"VADTriggeredBuffer: Triggering on speech end "
                        f"({len(triggered_audio)/self.sample_rate:.2f}s of speech)"
                    )
                    yield (triggered_audio.reshape(1, -1), self.sample_rate)
                    
    async def _handle_speech_chunk(self, audio_chunk: np.ndarray, chunk_samples: int) -> Optional[np.ndarray]:
        """Handle a chunk containing speech. Returns audio if max duration reached."""
        if not self._is_in_speech:
            # Starting new speech segment
            logger.info("VADTriggeredBuffer: Speech started")
            self._is_in_speech = True
            self._speech_start_time = 0
            self._speech_buffer = audio_chunk.copy()
            self._silence_accumulated_samples = 0  # Reset silence counter
        else:
            # Continuing speech segment
            if self._speech_buffer is not None:
                self._speech_buffer = np.concatenate([self._speech_buffer, audio_chunk])
                # Reset silence counter when speech continues
                self._silence_accumulated_samples = 0
                
                # Check if we've exceeded max duration
                if len(self._speech_buffer) >= self.max_samples:
                    logger.info(
                        f"VADTriggeredBuffer: Max speech duration reached "
                        f"({len(self._speech_buffer)/self.sample_rate:.2f}s), forcing trigger"
                    )
                    # Trigger and reset
                    triggered_audio = self._speech_buffer.copy()
                    self._reset_state()
                    return triggered_audio
                    
        self._last_speech_time = chunk_samples
        return None
        
    async def _handle_silence_chunk(self, chunk_samples: int) -> Optional[np.ndarray]:
        """Handle a chunk containing silence. Returns audio if trigger conditions are met."""
        if not self._is_in_speech or self._speech_buffer is None:
            # Reset silence tracking if we're not in speech
            self._silence_accumulated_samples = 0
            return None
            
        # Accumulate silence duration
        self._silence_accumulated_samples += chunk_samples
        silence_duration_s = self._silence_accumulated_samples / self.sample_rate
        
        logger.debug(f"VADTriggeredBuffer: Accumulated {silence_duration_s:.2f}s of silence (need {self.silence_duration_s:.2f}s)")
        
        # Check if we have enough silence to confirm speech end
        if self._silence_accumulated_samples >= self.silence_samples:
            # Check if we have minimum speech duration
            speech_duration_s = len(self._speech_buffer) / self.sample_rate
            if len(self._speech_buffer) >= self.min_samples:
                # Trigger!
                logger.info(f"VADTriggeredBuffer: Speech end confirmed after {silence_duration_s:.2f}s silence (speech: {speech_duration_s:.2f}s)")
                triggered_audio = self._speech_buffer.copy()
                self._reset_state()
                return triggered_audio
            else:
                logger.debug(
                    f"VADTriggeredBuffer: Speech too short "
                    f"({speech_duration_s:.2f}s < {self.min_speech_duration_s}s), discarding"
                )
                self._reset_state()
        else:
            # Not enough silence yet, but we need to include this silence in the buffer
            # to avoid gaps in the final audio
            silence_chunk = np.zeros(chunk_samples, dtype=np.float32)
            if self._speech_buffer is not None:
                self._speech_buffer = np.concatenate([self._speech_buffer, silence_chunk])
                
        return None
        
    def _reset_state(self):
        """Reset the buffer state."""
        self._speech_buffer = None
        self._speech_start_time = None
        self._last_speech_time = None
        self._is_in_speech = False
        self._silence_buffer = None
        self._silence_accumulated_samples = 0


class UltravoxMinDurationWrapper(Node):
    """
    Wrapper around UltravoxNode that enforces minimum audio duration.
    
    This prevents generation on insufficient audio data.
    """
    
    def __init__(self, ultravox_node, min_duration_s: float = 1.0, sample_rate: int = 16000, **kwargs):
        super().__init__(**kwargs)
        self.ultravox_node = ultravox_node
        self.min_duration_s = min_duration_s
        self.sample_rate = sample_rate
        self.min_samples = int(min_duration_s * sample_rate)
        self.is_streaming = True
        
    async def initialize(self):
        """Initialize the wrapped Ultravox node."""
        await self.ultravox_node.initialize()
        
    async def cleanup(self):
        """Cleanup the wrapped Ultravox node."""
        await self.ultravox_node.cleanup()
        
    async def process(self, data_stream):
        """Filter out audio chunks that are too short."""
        async def filtered_stream():
            async for data in data_stream:
                if isinstance(data, tuple) and len(data) == 2:
                    audio_data, sample_rate = data
                    if isinstance(audio_data, np.ndarray):
                        duration_s = audio_data.size / sample_rate
                        if duration_s >= self.min_duration_s:
                            logger.info(f"UltravoxWrapper: Processing {duration_s:.2f}s of audio (≥{self.min_duration_s:.2f}s minimum)")
                            yield data
                        else:
                            logger.warning(f"UltravoxWrapper: Rejecting {duration_s:.2f}s of audio (< {self.min_duration_s:.2f}s minimum)")
                            continue
                else:
                    # Pass through non-audio data
                    yield data
                    
        async for result in self.ultravox_node.process(filtered_stream()):
            yield result


class PrintResponseNode(PassThroughNode):
    """Node that prints Ultravox responses."""
    
    def process(self, data):
        """Print each response."""
        if isinstance(data, (str, tuple)):
            text = data[0] if isinstance(data, tuple) else data
            print(f"\n🎤 ULTRAVOX RESPONSE: {text}\n")
        return data


async def create_speech_with_pauses(filepath: str, duration_s: int = 15, sample_rate: int = 44100):
    """Create demo audio with speech segments separated by pauses."""
    if os.path.exists(filepath):
        return
        
    logger.info(f"Creating demo audio with speech and pauses at '{filepath}'...")
    
    samples = int(sample_rate * duration_s)
    t = np.linspace(0., float(duration_s), samples)
    audio = np.zeros(samples)
    
    # Define speech segments with clear pauses
    speech_segments = [
        (1.0, 3.5, "Hello there"),        # 2.5s speech
        (5.0, 7.0, "How are you today"),  # 2.0s speech  
        (9.0, 12.0, "Tell me about artificial intelligence"), # 3.0s speech
        (13.5, 14.5, "Thank you")        # 1.0s speech
    ]
    
    for start, end, description in speech_segments:
        mask = (t >= start) & (t < end)
        # Create varied speech-like patterns
        freq_base = 200 + 150 * np.sin(2 * np.pi * 0.5 * t[mask])
        freq_mod = 100 * np.sin(2 * np.pi * 5 * t[mask])
        speech_signal = 0.3 * np.sin(2 * np.pi * (freq_base + freq_mod) * t[mask])
        audio[mask] = speech_signal
        logger.info(f"  Speech segment: {start:.1f}s-{end:.1f}s ({description})")
    
    # Add light background noise
    audio += 0.01 * np.random.randn(samples)
    
    await asyncio.to_thread(sf.write, filepath, audio.astype(np.float32), sample_rate)
    logger.info(f"Demo audio created: {duration_s}s with {len(speech_segments)} speech segments")


async def main():
    """Run the VAD-triggered Ultravox pipeline."""
    REMOTE_HOST = os.environ.get("REMOTE_HOST", "127.0.0.1")
    logger.info("--- VAD-Triggered Ultravox: Generate only when speech ends ---")

    # Create demo audio
    demo_audio_path = "examples/audio.wav"
    pipeline = Pipeline()

    # Audio source
    pipeline.add_node(MediaReaderNode(
        path=demo_audio_path,
        chunk_size=4096,
        name="MediaReader"
    ))

    pipeline.add_node(AudioTrackSource(name="AudioTrackSource"))

    # Resample for VAD and Ultravox
    pipeline.add_node(AudioTransform(
        output_sample_rate=16000,
        output_channels=1,
        name="AudioTransform"
    ))

    # VAD to detect speech/silence
    vad = VoiceActivityDetector(
        frame_duration_ms=30,
        energy_threshold=0.02,
        speech_threshold=0.3,
        filter_mode=False,  # Keep metadata
        include_metadata=True,
        name="VAD"
    )
    vad.is_streaming = True
    pipeline.add_node(vad)

    # VAD-triggered buffer that only outputs complete speech segments
    vad_buffer = VADTriggeredBuffer(
        min_speech_duration_s=0.8,    # Minimum 0.8s of speech before triggering
        max_speech_duration_s=8.0,    # Force trigger after 8s of continuous speech
        silence_duration_s=1.0,       # 1000ms of silence to confirm speech end (more robust)
        sample_rate=16000,
        name="VADTriggeredBuffer"
    )
    vad_buffer.is_streaming = True
    pipeline.add_node(vad_buffer)

    # Remote Ultravox execution with minimum duration protection
    remote_config = RemoteExecutorConfig(host=REMOTE_HOST, port=50052, ssl_enabled=False)
    
    ultravox_instance = UltravoxNode(
        model_id="fixie-ai/ultravox-v0_5-llama-3_1-8b",
        system_prompt=(
            "You are a helpful assistant. Listen to what the user says and respond "
            "appropriately and concisely. Keep responses under 2 sentences."
        ),
        buffer_duration_s=10.0,  # Large buffer to process complete utterances (up to 10s)
        name="UltravoxNode"
    )
    
    # Wrap Ultravox with minimum duration protection
    protected_ultravox = UltravoxMinDurationWrapper(
        ultravox_node=ultravox_instance,
        min_duration_s=1.0,  # Require at least 1s of audio
        sample_rate=16000,
        name="ProtectedUltravox"
    )

    remote_node = RemoteObjectExecutionNode(
        obj_to_execute=protected_ultravox,
        remote_config=remote_config,
        name="RemoteUltravox",
        node_config={'streaming': True}
    )
    remote_node.is_streaming = True
    pipeline.add_node(remote_node)

    # Print responses
    pipeline.add_node(PrintResponseNode(name="PrintResponse"))

    logger.info("Starting VAD-triggered pipeline...")
    logger.info("Ultravox will generate responses only when speech segments end.")
    
    async with pipeline.managed_execution():
        try:
            response_count = 0
            async for result in pipeline.process():
                response_count += 1
                logger.debug(f"Received response {response_count}")
            logger.info(f"Pipeline completed. Generated {response_count} responses.")
        except Exception as e:
            logger.error(f"Pipeline error: {e}", exc_info=True)
            raise

    logger.info("VAD-triggered Ultravox pipeline finished.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logging.error(f"An error occurred: {e}", exc_info=True)
        logging.error("Please ensure the remote server is running.")