import asyncio
import logging
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

try:
    from transformers import AutoTokenizer
except ImportError:
    AutoTokenizer = None

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
        prompt_template: Optional[str] = None,
        modalities: Optional[List[str]] = None,
        sampling_params: Optional[Dict[str, Any]] = None,
        use_chat_template: bool = False,
        
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
                           Used when `use_chat_template` is False.
            modalities: A list of modalities the model expects (e.g., ["image"]).
            sampling_params: A dictionary of parameters for vLLM's SamplingParams.
                           Can include 'stop_tokens' as a list of strings, which
                           will be converted to token IDs if using a chat template.
            use_chat_template: If True, uses the model's tokenizer to apply a
                               chat template to the input. The input data to this
                               node's `process` method should contain a 'messages' key.
            
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

        if use_chat_template and prompt_template:
            logger.warning("'prompt_template' is ignored when 'use_chat_template' is True.")
            prompt_template = None
        if not use_chat_template and not prompt_template:
            raise ValueError("Either 'prompt_template' must be provided or 'use_chat_template' must be True.")

        self.is_streaming = True
        self.use_chat_template = use_chat_template
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

        self._sampling_params_dict = {
            "temperature": 0.7,
            "max_tokens": 512,
        }
        if sampling_params:
            self._sampling_params_dict.update(sampling_params)

        self.engine: Optional[AsyncLLMEngine] = None
        self.tokenizer: Optional[AutoTokenizer] = None
        self.sampling_params_obj: Optional[SamplingParams] = None

    async def initialize(self) -> None:
        """Initializes the vLLM engine and, if needed, the tokenizer."""
        await super().initialize()
        if not AsyncLLMEngine:
            raise NodeError("vLLM is not installed. Please install with 'pip install vllm'.")
        if self.use_chat_template and not AutoTokenizer:
            raise NodeError("transformers is not installed. Please install with 'pip install transformers'.")

        logger.info(f"Initializing vLLM engine for model '{self._engine_args['model']}'...")
        try:
            # Initialize tokenizer first if needed for chat templates
            if self.use_chat_template:
                self.tokenizer = await asyncio.to_thread(
                    AutoTokenizer.from_pretrained,
                    self._engine_args.get("tokenizer", self._engine_args["model"]),
                    trust_remote_code=self._engine_args.get("trust_remote_code", True)
                )

            # Convert stop words to tokens if necessary
            if self.tokenizer and 'stop_tokens' in self._sampling_params_dict:
                stop_tokens = self._sampling_params_dict.pop('stop_tokens')
                self._sampling_params_dict['stop_token_ids'] = await asyncio.to_thread(
                    self.tokenizer.convert_tokens_to_ids, stop_tokens
                )

            engine_args_obj = AsyncEngineArgs(**self._engine_args)
            self.engine = await asyncio.to_thread(
                AsyncLLMEngine.from_engine_args, engine_args_obj
            )
            
            self.sampling_params_obj = SamplingParams(**self._sampling_params_dict)
            logger.info("vLLM engine initialized successfully.")
        except Exception as e:
            raise NodeError(f"Failed to initialize VLLMNode: {e}") from e

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
            
            prompt_text = None
            if self.use_chat_template:
                if 'messages' not in data:
                    logger.warning("VLLMNode in chat mode requires a 'messages' key in input data. Skipping.")
                    continue
                prompt_text = self.tokenizer.apply_chat_template(
                    data['messages'],
                    tokenize=False,
                    add_generation_prompt=True
                )
            else:
                 try:
                    prompt_text = self.prompt_template.format(**data)
                 except KeyError as e:
                    logger.warning(
                        f"Missing key {e} in input data for prompt template. Skipping."
                    )
                    continue

            if not prompt_text:
                continue

            multi_modal_data = {}
            for modality in self.modalities:
                if modality in data:
                    multi_modal_data[modality] = data[modality]
            
            llm_inputs = {"prompt": prompt_text}
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
        self.tokenizer = None
        self.sampling_params_obj = None
        logger.info("VLLMNode cleaned up.") 