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
    Its constructor is designed to mirror the common arguments of `vllm.LLM`
    for familiarity and ease of use.
    """

    def __init__(
        self,
        # --- Node-specific arguments ---
        model: str,
        prompt_template: str,
        modalities: Optional[List[str]] = None,
        sampling_params: Optional[Dict[str, Any]] = None,
        
        # --- Common vLLM Engine arguments (mirrored from vllm.LLM) ---
        tokenizer: Optional[str] = None,
        tokenizer_mode: str = 'auto',
        trust_remote_code: bool = True,
        tensor_parallel_size: int = 1,
        dtype: str = 'auto',
        quantization: Optional[str] = None,
        gpu_memory_utilization: float = 0.90,
        enforce_eager: bool = False,
        max_model_len: Optional[int] = None,
        max_num_seqs: Optional[int] = None,
        
        # --- Catch-all for other engine arguments ---
        **engine_kwargs: Any,
    ):
        """
        Initializes the VLLMNode.

        Args:
            model: The ID of the model to load from HuggingFace.
            prompt_template: A string template for the prompt, with placeholders
                           for data from the input stream (e.g., "{text}").
                           It should also include multimodal placeholders like
                           "<image>" if modalities are used.
            modalities: A list of modalities the model expects (e.g., ["image"]).
            sampling_params: A dictionary of parameters for vLLM's SamplingParams.
            
            tokenizer: The name or path of the tokenizer to use.
            tokenizer_mode: The mode of the tokenizer ('auto', 'slow', or 'fast').
            trust_remote_code: Whether to trust remote code from HuggingFace.
            tensor_parallel_size: The number of GPUs to use for tensor parallelism.
            dtype: The data type for the model weights ('auto', 'half', 'float16', 'bfloat16', 'float', 'float32').
            quantization: The quantization method to use (e.g., 'awq', 'squeezellm').
            gpu_memory_utilization: The fraction of GPU memory to reserve for the model.
            enforce_eager: Whether to enforce eager execution.
            max_model_len: The maximum sequence length for the model.
            max_num_seqs: The maximum number of sequences to process in a batch.
            engine_kwargs: Any other keyword arguments to be passed directly to
                         the vLLM `AsyncEngineArgs`. This can include arguments
                         like `hf_overrides`.
        """
        # Separate the 'name' kwarg for the base Node class
        node_name = engine_kwargs.pop('name', None)
        super().__init__(name=node_name)

        self.is_streaming = True

        self.prompt_template = prompt_template
        self.modalities = modalities or []

        # Collect all engine arguments into a single dictionary
        self._engine_args = {
            "model": model,
            "tokenizer": tokenizer,
            "tokenizer_mode": tokenizer_mode,
            "trust_remote_code": trust_remote_code,
            "tensor_parallel_size": tensor_parallel_size,
            "dtype": dtype,
            "quantization": quantization,
            "gpu_memory_utilization": gpu_memory_utilization,
            "enforce_eager": enforce_eager,
            "max_model_len": max_model_len,
            "max_num_seqs": max_num_seqs,
            **engine_kwargs
        }
        # Filter out None values so we don't pass them if they are not set
        self._engine_args = {k: v for k, v in self._engine_args.items() if v is not None}

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

        logger.info(f"Initializing vLLM engine for model '{self._engine_args['model']}'...")
        try:
            engine_args_obj = AsyncEngineArgs(**self._engine_args)
            # The from_engine_args method is synchronous and can block the event
            # loop while it initializes the engine and its workers.
            # Running it in a separate thread prevents blocking and helps with
            # CUDA context initialization in multiprocess environments.
            self.engine = await asyncio.to_thread(
                AsyncLLMEngine.from_engine_args, engine_args_obj
            )
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

            # For AsyncLLMEngine, multimodal data is passed as part of a
            # dictionary to the 'prompt' argument.
            llm_inputs = {"prompt": prompt}
            if multi_modal_data:
                llm_inputs["multi_modal_data"] = multi_modal_data

            request_id = f"vllm-node-{time.time()}-{id(data)}"

            results_generator = self.engine.generate(
                llm_inputs,
                self.sampling_params_obj,
                request_id,
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