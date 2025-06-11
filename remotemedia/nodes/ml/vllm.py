import asyncio
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from remotemedia.core.exceptions import NodeError
from remotemedia.core.node import Node

logger = logging.getLogger(__name__)

try:
    from vllm.engine.arg_utils import AsyncEngineArgs
    from vllm.engine.async_llm_engine import AsyncLLMEngine
    from vllm.sampling_params import SamplingParams
except ImportError:
    logger.warning("vLLM library not found. VLLMNode will not be available.")
    AsyncLLMEngine, AsyncEngineArgs, SamplingParams = None, None, None


class VLLMNode(Node):
    """
    A node that uses vLLM for high-throughput inference on Large Language Models.
    This node can handle text, image, and audio modalities depending on the
    model and configuration, and it can stream token responses.
    """

    def __init__(
        self,
        model_id: str,
        prompt_template: str,
        modalities: Optional[List[str]] = None,
        engine_args: Optional[Dict[str, Any]] = None,
        sampling_params: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ):
        """
        Initializes the VLLMNode.

        Args:
            model_id: The ID of the model to load from HuggingFace.
            prompt_template: A string template for the prompt, with placeholders
                           for data from the input stream (e.g., "{text}").
                           It should also include multimodal placeholders like
                           "<image>" if modalities are used.
            modalities: A list of modalities the model expects (e.g., ["image"]).
                        The node will look for these keys in the input data.
            engine_args: A dictionary of arguments for vLLM's AsyncEngineArgs.
            sampling_params: A dictionary of parameters for vLLM's SamplingParams.
        """
        super().__init__(**kwargs)
        self.is_streaming = True

        self.model_id = model_id
        self.prompt_template = prompt_template
        self.modalities = modalities or []

        self._engine_args = {
            "model": self.model_id,
            "trust_remote_code": True,
        }
        if engine_args:
            self._engine_args.update(engine_args)

        self._sampling_params = {
            "temperature": 0.7,
            "max_tokens": 512,
        }
        if sampling_params:
            self._sampling_params.update(sampling_params)

        self.engine: Optional[AsyncLLMEngine] = None
        self.sampling_params_obj: Optional[SamplingParams] = None

    async def initialize(self) -> None:
        """Initializes the vLLM engine."""
        await super().initialize()
        if not AsyncLLMEngine:
            raise NodeError("vLLM is not installed. Please install with 'pip install vllm'.")

        logger.info(f"Initializing vLLM engine for model '{self.model_id}'...")
        try:
            engine_args_obj = AsyncEngineArgs(**self._engine_args)
            self.engine = AsyncLLMEngine.from_engine_args(engine_args_obj)
            self.sampling_params_obj = SamplingParams(**self._sampling_params)
            logger.info("vLLM engine initialized successfully.")
        except Exception as e:
            raise NodeError(f"Failed to initialize vLLM engine: {e}") from e

    async def process(
        self, data_stream: AsyncGenerator[Any, None]
    ) -> AsyncGenerator[Any, None]:
        """
        Processes an incoming stream of data dictionaries, generates responses
        using vLLM, and streams back the generated tokens.
        """
        if not self.engine or not self.sampling_params_obj:
            raise NodeError("vLLM engine is not initialized.")

        async for data in data_stream:
            if not isinstance(data, dict):
                logger.warning(
                    f"VLLMNode expects dictionary input, but got {type(data)}. Skipping."
                )
                continue

            try:
                prompt = self.prompt_template.format(**data)
            except KeyError as e:
                logger.warning(
                    f"Missing key {e} in input data for prompt template. Skipping."
                )
                continue

            multi_modal_data = {}
            for modality in self.modalities:
                if modality in data:
                    multi_modal_data[modality] = data[modality]
                else:
                    logger.warning(
                        f"Modality '{modality}' specified but not found in "
                        "input data. It will be omitted."
                    )

            request_id = f"vllm-node-{time.time()}-{id(data)}"

            results_generator = self.engine.generate(
                prompt,
                self.sampling_params_obj,
                request_id,
                multi_modal_data=multi_modal_data or None,
            )

            previous_text = ""
            async for result in results_generator:
                output = result.outputs[0]
                new_text = output.text[len(previous_text) :]
                if new_text:
                    yield new_text
                previous_text = output.text

    async def cleanup(self) -> None:
        """Cleans up the node's resources."""
        self.engine = None
        self.sampling_params_obj = None
        logger.info("VLLMNode cleaned up.") 