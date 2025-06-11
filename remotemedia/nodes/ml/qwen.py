import asyncio
import logging
from typing import Optional, Any, List, Dict, Tuple, AsyncGenerator
import numpy as np
import tempfile
import os
import requests
import copy
import soundfile as sf
import librosa

from remotemedia.core.node import Node
from remotemedia.core.exceptions import NodeError, ConfigurationError

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    import torch
    import av
    from transformers import Qwen2_5OmniForConditionalGeneration, Qwen2_5OmniProcessor
    from qwen_omni_utils import process_mm_info
except ImportError:
    logger.warning("ML libraries not found. Qwen2_5OmniNode will not be available.")
    torch = None
    av = None
    Qwen2_5OmniForConditionalGeneration = None
    Qwen2_5OmniProcessor = None
    process_mm_info = None

class Qwen2_5OmniNode(Node):
    """
    A node that uses the Qwen2.5-Omni model for multimodal generation from a stream.
    https://huggingface.co/Qwen/Qwen2.5-Omni-3B
    """

    def __init__(self,
                 model_id: str = "Qwen/Qwen2.5-Omni-3B",
                 device: Optional[str] = None,
                 torch_dtype: str = "auto",
                 attn_implementation: Optional[str] = None,
                 conversation_template: Optional[List[Dict[str, Any]]] = None,
                 buffer_duration_s: float = 5.0,
                 video_fps: int = 10,
                 audio_sample_rate: int = 16000,
                 speaker: Optional[str] = None,
                 use_audio_in_video: bool = False,
                 **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.is_streaming = True
        self.model_id = model_id
        self._requested_device = device
        self.torch_dtype_str = torch_dtype
        self.attn_implementation = attn_implementation
        self.conversation_template = conversation_template or []
        self.buffer_duration_s = buffer_duration_s
        self.video_fps = video_fps
        self.audio_sample_rate = audio_sample_rate
        self.speaker = speaker
        self.use_audio_in_video = use_audio_in_video

        self.model = None
        self.processor = None
        self.device = None
        self.torch_dtype = None
        
        self.video_buffer = []
        self.audio_buffer = []
        self.video_buffer_max_frames = int(self.buffer_duration_s * self.video_fps)

    async def initialize(self) -> None:
        """
        Load the model and processor. This runs on the execution environment (local or remote).
        """
        await super().initialize()
        if not all([torch, av, Qwen2_5OmniForConditionalGeneration, Qwen2_5OmniProcessor, process_mm_info]):
             raise NodeError("Required ML libraries (torch, transformers, soundfile, pyav, qwen_omni_utils) are not installed.")

        if self._requested_device:
            self.device = self._requested_device
        elif torch.cuda.is_available():
            self.device = "cuda:0"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            self.device = "mps"
        else:
            self.device = "cpu"

        if self.torch_dtype_str == "auto":
            self.torch_dtype = "auto"
        else:
            try:
                self.torch_dtype = getattr(torch, self.torch_dtype_str)
            except AttributeError:
                raise ConfigurationError(f"Invalid torch_dtype '{self.torch_dtype_str}'")

        logger.info(f"Qwen2.5-Omni configured for model '{self.model_id}' on device '{self.device}'")
        
        model_kwargs = {
            "torch_dtype": self.torch_dtype,
            "device_map": "auto" if self.device != "cpu" else "cpu"
        }

        if self.attn_implementation:
            model_kwargs["attn_implementation"] = self.attn_implementation
            logger.info(f"Using attn_implementation: {self.attn_implementation}")
        
        try:
            print(f"Qwen2_5OmniNode.initialize: Initializing model {self.model_id} with kwargs {model_kwargs}")
            self.model = await asyncio.to_thread(
                Qwen2_5OmniForConditionalGeneration.from_pretrained, self.model_id, **model_kwargs)
            print(f"Qwen2_5OmniNode.initialize: Model initialized")
            self.processor = await asyncio.to_thread(
                Qwen2_5OmniProcessor.from_pretrained, self.model_id)
            print(f"Qwen2_5OmniNode.initialize: Processor initialized")
            if self.device == "mps":
                self.model.to(self.device)
            print(f"Qwen2_5OmniNode.initialize: Model moved to device {self.device}")

            logger.info("Qwen2.5-Omni model initialized successfully.")
            self._is_initialized = True
        except Exception as e:
            raise NodeError(f"Failed to initialize Qwen2.5-Omni model: {e}")

    async def _run_inference(self) -> Optional[Tuple[List[str], Optional[np.ndarray]]]:
        if not self.video_buffer and not self.audio_buffer:
            return None
        
        with tempfile.TemporaryDirectory() as temp_dir:
            final_conversation = copy.deepcopy(self.conversation_template)
            video_path, audio_path = None, None
            
            # Save buffered video to a temporary file
            if self.video_buffer:
                video_path = await self._save_video_buffer(temp_dir)

            # Save buffered audio to a temporary file
            if self.audio_buffer:
                audio_path = await self._save_audio_buffer(temp_dir)
            
            # This node's purpose is to add media from the stream to the conversation.
            # So, we'll inject the paths we just created.
            self._inject_media_paths(final_conversation, video_path, audio_path)

            # If this node buffered and injected its own audio, we must tell the model
            # to use it, overriding the initial `use_audio_in_video` setting.
            use_audio_in_video_flag = self.use_audio_in_video
            if audio_path:
                use_audio_in_video_flag = False

            def _inference_thread():
                text = self.processor.apply_chat_template(final_conversation, add_generation_prompt=True, tokenize=False)
                
                self.logger.info(f"Running inference with use_audio_in_video={use_audio_in_video_flag}")
                audios, images, videos = process_mm_info(final_conversation, use_audio_in_video=use_audio_in_video_flag)
                
                inputs = self.processor(text=text, audio=audios, images=images, videos=videos, return_tensors="pt", padding=True, use_audio_in_video=use_audio_in_video_flag)
                inputs = inputs.to(self.model.device)
                if self.torch_dtype != 'auto':
                    inputs = inputs.to(self.torch_dtype)

                # The processor may pass through its own kwargs which are not
                # recognized by the model's generate method. We remove them here
                # to avoid "Unused or unrecognized kwargs" warnings.
                inputs.pop("images", None)
                inputs.pop("return_tensors", None)

                generate_kwargs = {}
                if self.speaker:
                    generate_kwargs["speaker"] = self.speaker

                text_ids, audio_tensor = self.model.generate(**inputs, **generate_kwargs)
                
                decoded_text = self.processor.batch_decode(text_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)
                audio_np = audio_tensor.reshape(-1).detach().cpu().numpy() if audio_tensor is not None and audio_tensor.numel() > 0 else None
                return decoded_text, audio_np

            return await asyncio.to_thread(_inference_thread)

    async def process(self, data_stream: AsyncGenerator[Any, None]) -> AsyncGenerator[Any, None]:
        self.logger.info("Qwen process method started.")
        async for data in data_stream:
            # When data is serialized and sent over the network, complex objects like
            # av.VideoFrame can be converted to their underlying numpy array representation.
            # We need to handle both the direct object (for local runs) and the raw
            # array (for remote runs).
            if isinstance(data, av.VideoFrame):
                self.video_buffer.append(data.to_ndarray(format='rgb24'))
            elif isinstance(data, np.ndarray):
                # This is the likely type for video frames after network serialization
                self.video_buffer.append(data)
            elif isinstance(data, av.AudioFrame):
                # Audio frames should be handled correctly now
                resampled_chunk = librosa.resample(
                    data.to_ndarray().astype(np.float32).mean(axis=0),  # aac is stereo
                    orig_sr=data.sample_rate,
                    target_sr=self.audio_sample_rate
                )
                self.audio_buffer.append(resampled_chunk)
            else:
                self.logger.warning(f"Qwen node received unexpected data type: {type(data)}")

            if len(self.video_buffer) >= self.video_buffer_max_frames:
                self.logger.info(f"Buffer full ({len(self.video_buffer)} frames). Running inference...")
                result = await self._run_inference()
                if result:
                    yield result
                self.video_buffer.clear()
                self.audio_buffer.clear()
        
        # After the stream is exhausted, process any remaining buffered data.
        if self.video_buffer or self.audio_buffer:
            self.logger.info(f"Processing final buffer segment at end of stream ({len(self.video_buffer)} video frames, {len(self.audio_buffer)} audio chunks).")
            result = await self._run_inference()
            if result:
                yield result
            self.video_buffer.clear()
            self.audio_buffer.clear()

    async def cleanup(self) -> None:
        self.logger.info(f"Cleaning up node '{self.name}'.")
        self.video_buffer.clear()
        self.audio_buffer.clear()
        
        del self.model
        del self.processor
        self.model = None
        self.processor = None
        if torch and torch.cuda.is_available():
            torch.cuda.empty_cache()

    async def _save_video_buffer(self, temp_dir: str) -> str:
        video_path = os.path.join(temp_dir, "temp_video.mp4")
        first_frame = self.video_buffer[0]
        height, width, _ = first_frame.shape
        
        output_container = av.open(video_path, mode='w')
        stream = output_container.add_stream('libx264', rate=self.video_fps)
        stream.width = width
        stream.height = height
        stream.pix_fmt = 'yuv420p'

        for frame_data in self.video_buffer:
            frame = av.VideoFrame.from_ndarray(frame_data, format='rgb24')
            for packet in stream.encode(frame):
                output_container.mux(packet)
        
        for packet in stream.encode(): # Flush
            output_container.mux(packet)
        output_container.close()
        return video_path

    async def _save_audio_buffer(self, temp_dir: str) -> str:
        audio_path = os.path.join(temp_dir, "temp_audio.wav")
        full_audio = np.concatenate(self.audio_buffer)
        await asyncio.to_thread(sf.write, audio_path, full_audio, self.audio_sample_rate)
        return audio_path

    def _inject_media_paths(self, conversation: List[Dict[str, Any]], video_path: Optional[str], audio_path: Optional[str]) -> None:
        """
        Injects media file paths into the conversation.

        This method finds the first user turn and ensures the video and audio paths
        are present, either by replacing placeholders or by adding new entries if
        placeholders do not exist.
        """
        for turn in conversation:
            if turn.get("role") == "user":
                content = turn.get("content", [])
                if not isinstance(content, list):
                    continue

                video_injected = False
                if video_path:
                    for item in content:
                        if item.get("type") == "video":
                            item["video"] = video_path
                            video_injected = True
                            self.logger.info(f"Injected video path '{video_path}' into conversation.")
                            break
                    if not video_injected:
                        content.insert(0, {"type": "video", "video": video_path})
                        self.logger.info(f"Added video path '{video_path}' to conversation.")

                audio_injected = False
                if audio_path:
                    for item in content:
                        if item.get("type") == "audio":
                            item["audio"] = audio_path
                            audio_injected = True
                            self.logger.info(f"Injected audio path '{audio_path}' into conversation.")
                            break
                    if not audio_injected:
                        content.insert(0, {"type": "audio", "audio": audio_path})
                        self.logger.info(f"Added audio path '{audio_path}' to conversation.")

                turn["content"] = content
                # We only inject into the first user turn found.
                return

__all__ = ["Qwen2_5OmniNode"] 