"""
Audio processing nodes for the RemoteMedia SDK.
"""

from typing import Any
import logging
import librosa
import numpy as np

from ..core.node import Node
from ..core.types import _SENTINEL

logger = logging.getLogger(__name__)


class AudioTransform(Node):
    """
    Audio transformation node that supports resampling and channel conversion.
    """

    def __init__(self, output_sample_rate: int = 44100, output_channels: int = 2, **kwargs):
        """
        Initializes the AudioTransform node.

        Args:
            output_sample_rate (int): The target sample rate for the audio.
            output_channels (int): The target number of channels for the audio.
        """
        super().__init__(**kwargs)
        self.output_sample_rate = output_sample_rate
        self.output_channels = output_channels

    def process(self, data: Any) -> Any:
        """
        Processes audio data by resampling and converting channel counts.

        This method expects `data` to be a tuple `(audio_data, sample_rate)`,
        where `audio_data` is a NumPy array with shape (channels, samples).

        Args:
            data: A tuple containing the audio data and its sample rate.

        Returns:
            A tuple `(processed_audio_data, output_sample_rate)`.
        """
        if not isinstance(data, tuple) or len(data) != 2:
            logger.warning(
                f"AudioTransform '{self.name}': received data in "
                "unexpected format. Expected (audio_data, sample_rate)."
            )
            return data

        audio_data, input_sample_rate = data

        if not isinstance(audio_data, np.ndarray):
            logger.warning(f"AudioTransform '{self.name}': audio data is not a numpy array.")
            return data

        # Ensure audio_data is at least 2D
        if audio_data.ndim == 1:
            audio_data = audio_data.reshape(1, -1)

        input_channels = audio_data.shape[0]

        # Resample if necessary
        if input_sample_rate != self.output_sample_rate:
            # librosa.resample works with mono or multi-channel.
            # y (np.ndarray): audio time series. Multi-channel is supported.
            audio_data = librosa.resample(
                y=audio_data, orig_sr=input_sample_rate, target_sr=self.output_sample_rate
            )

        # Mix channels if necessary
        if input_channels != self.output_channels:
            if self.output_channels == 1:
                # Mix down to mono
                audio_data = librosa.to_mono(y=audio_data)
                audio_data = audio_data.reshape(1, -1)  # ensure it is 2d
            elif input_channels == 1 and self.output_channels > 1:
                # upmix mono to multi-channel by duplicating the channel
                audio_data = np.tile(audio_data, (self.output_channels, 1))
            else:
                # For other cases (e.g., 5.1 to stereo), it's more complex.
                # A simple approach is to take the first `output_channels`.
                # This is a simplification.
                logger.warning(
                    f"AudioTransform '{self.name}': complex channel conversion from "
                    f"{input_channels} to {self.output_channels} is simplified "
                    "by taking the first channels."
                )
                audio_data = audio_data[: self.output_channels, :]

        logger.debug(
            f"AudioTransform '{self.name}': processed audio to "
            f"{self.output_sample_rate}Hz and {self.output_channels} channels."
        )
        return (audio_data, self.output_sample_rate)


class AudioBuffer(Node):
    """
    Audio buffering node that accumulates audio data until a target size is reached.
    """

    def __init__(self, buffer_size_samples: int, **kwargs):
        """
        Initializes the AudioBuffer node.

        Args:
            buffer_size_samples (int): The number of samples to buffer before outputting.
        """
        super().__init__(**kwargs)
        self.buffer_size_samples = buffer_size_samples
        self._buffer = None
        self._sample_rate = None
        self._channels = None

    def process(self, data: Any) -> Any:
        """
        Buffers audio data until `buffer_size_samples` is reached.

        This method expects `data` to be a tuple `(audio_data, sample_rate)`,
        where `audio_data` is a NumPy array with shape (channels, samples).

        It accumulates `audio_data` and when at least `buffer_size_samples` are
        available, it returns a chunk of that size. Any remaining samples are
        kept in the buffer for the next call. If not enough data is available to
        form a full chunk, it returns `None`.

        Args:
            data: A tuple containing the audio data and its sample rate.

        Returns:
            A tuple `(buffered_audio_data, sample_rate)` when the buffer is
            full, otherwise `None`.
        """
        if not isinstance(data, tuple) or len(data) != 2:
            logger.warning(
                f"AudioBuffer '{self.name}': received data in unexpected format. "
                "Expected (audio_data, sample_rate)."
            )
            return None

        audio_chunk, sample_rate = data

        if not isinstance(audio_chunk, np.ndarray):
            logger.warning(f"AudioBuffer '{self.name}': audio data is not a numpy array.")
            return None

        if audio_chunk.ndim == 1:
            audio_chunk = audio_chunk.reshape(1, -1)

        if self._buffer is None:
            self._sample_rate = sample_rate
            self._channels = audio_chunk.shape[0]
            self._buffer = np.zeros((self._channels, 0), dtype=audio_chunk.dtype)

        if sample_rate != self._sample_rate or audio_chunk.shape[0] != self._channels:
            logger.warning(
                f"AudioBuffer '{self.name}': Audio format changed mid-stream. "
                "Flushing buffer and resetting."
            )
            flushed_data = self.flush()
            self._sample_rate = sample_rate
            self._channels = audio_chunk.shape[0]
            self._buffer = audio_chunk
            return flushed_data

        self._buffer = np.concatenate((self._buffer, audio_chunk), axis=1)

        if self._buffer.shape[1] >= self.buffer_size_samples:
            output_chunk = self._buffer[:, : self.buffer_size_samples]
            self._buffer = self._buffer[:, self.buffer_size_samples :]
            logger.debug(
                f"AudioBuffer '{self.name}': outputting chunk of "
                f"{self.buffer_size_samples} samples."
            )
            return (output_chunk, self._sample_rate)
        else:
            logger.debug(
                f"AudioBuffer '{self.name}': buffering, have "
                f"{self._buffer.shape[1]}/{self.buffer_size_samples} samples."
            )
            return None

    def flush(self) -> Any:
        """
        Flushes any remaining data from the buffer.

        Returns:
            A tuple `(buffered_audio_data, sample_rate)` if there is any
            data in the buffer, otherwise `None`.
        """
        if self._buffer is not None and self._buffer.shape[1] > 0:
            logger.debug(f"AudioBuffer '{self.name}': flushing {self._buffer.shape[1]} samples.")
            output_chunk = self._buffer
            self._buffer = np.zeros((self._channels, 0), dtype=output_chunk.dtype)
            return (output_chunk, self._sample_rate)
        return None


class AudioResampler(Node):
    """Audio resampling node."""
    
    def __init__(self, target_sample_rate: int = 44100, **kwargs):
        super().__init__(**kwargs)
        self.target_sample_rate = target_sample_rate
    
    def process(self, data: Any) -> Any:
        """Resample audio data."""
        # TODO: Implement audio resampling
        logger.debug(f"AudioResampler '{self.name}': resampling to {self.target_sample_rate}Hz")
        return data


__all__ = ["AudioTransform", "AudioBuffer", "AudioResampler"] 