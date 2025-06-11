import asyncio
import logging
from typing import Optional, Any, List, Dict, Tuple
import numpy as np

from remotemedia.core.node import Node
from remotemedia.core.exceptions import NodeError, ConfigurationError

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    import torch
    import soundfile as sf
    from transformers import Qwen2_5OmniForConditionalGeneration, Qwen2_5OmniProcessor
    from qwen_omni_utils import process_mm_info
except ImportError:
    logger.warning("ML libraries not found. Qwen2_5OmniNode will not be available.")
    torch = None
    sf = None
    Qwen2_5OmniForConditionalGeneration = None
    Qwen2_5OmniProcessor = None
    process_mm_info = None

class Qwen2_5OmniNode(Node):
    """
    A node that uses the Qwen2.5-Omni model for multimodal generation.
    https://huggingface.co/Qwen/Qwen2.5-Omni-3B
    """

    def __init__(self,
                 model_id: str = "Qwen/Qwen2.5-Omni-3B",
                 device: Optional[str] = None,
                 torch_dtype: str = "auto",
                 attn_implementation: Optional[str] = None,
                 use_audio_in_video: bool = True,
                 **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.model_id = model_id
        self._requested_device = device
        self.torch_dtype_str = torch_dtype
        self.attn_implementation = attn_implementation
        self.use_audio_in_video = use_audio_in_video

        self.model = None
        self.processor = None
        self.device = None
        self.torch_dtype = None

    async def initialize(self) -> None:
        """
        Load the model and processor. This runs on the execution environment (local or remote).
        """
        if not all([torch, Qwen2_5OmniForConditionalGeneration, Qwen2_5OmniProcessor, process_mm_info]):
             raise NodeError("Required ML libraries (torch, transformers, soundfile, qwen_omni_utils) are not installed.")

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
            "device_map": self.device if self.device != "mps" else "auto"
        }

        if self.attn_implementation:
            model_kwargs["attn_implementation"] = self.attn_implementation
            logger.info(f"Using attn_implementation: {self.attn_implementation}")
        
        try:
            self.model = await asyncio.to_thread(
                Qwen2_5OmniForConditionalGeneration.from_pretrained,
                self.model_id,
                **model_kwargs
            )
            self.processor = await asyncio.to_thread(
                Qwen2_5OmniProcessor.from_pretrained,
                self.model_id
            )
            if self.device == "mps":
                self.model.to(self.device)
            logger.info("Qwen2.5-Omni model initialized successfully.")
        except Exception as e:
            raise NodeError(f"Failed to initialize Qwen2.5-Omni model: {e}")

    async def process(self, conversation: List[Dict[str, Any]]) -> Tuple[List[str], Optional[np.ndarray]]:
        """
        Processes a conversation and returns generated text and optionally audio.
        Args:
            conversation: A list of dictionaries representing the conversation,
                          following the Qwen-Omni format.
        Returns:
            A tuple containing:
            - A list of generated text responses.
            - A numpy array of the generated audio, or None if no audio was generated.
        """
        if not self.model or not self.processor:
            raise NodeError("Qwen2.5-Omni pipeline is not initialized.")
        
        try:
            def _inference():
                text = self.processor.apply_chat_template(conversation, add_generation_prompt=True, tokenize=False)
                audios, images, videos = process_mm_info(conversation, use_audio_in_video=self.use_audio_in_video)
                
                inputs = self.processor(text=text, audio=audios, images=images, videos=videos, return_tensors="pt", padding=True, use_audio_in_video=self.use_audio_in_video)
                inputs = inputs.to(self.model.device)
                if self.torch_dtype != 'auto':
                     inputs = inputs.to(self.torch_dtype)

                text_ids, audio_tensor = self.model.generate(**inputs, use_audio_in_video=self.use_audio_in_video)
                
                decoded_text = self.processor.batch_decode(text_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False)

                audio_np = None
                if audio_tensor is not None and audio_tensor.numel() > 0:
                    audio_np = audio_tensor.reshape(-1).detach().cpu().numpy()

                return decoded_text, audio_np

            result_text, result_audio = await asyncio.to_thread(_inference)
            return (result_text, result_audio)

        except Exception as e:
            logger.error(f"Error during Qwen2.5-Omni inference: {e}", exc_info=True)
            return None, None

    async def cleanup(self) -> None:
        """Cleans up the pipeline and associated resources."""
        logger.info(f"Cleaning up node '{self.name}'.")
        del self.model
        del self.processor
        self.model = None
        self.processor = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

__all__ = ["Qwen2_5OmniNode"] 