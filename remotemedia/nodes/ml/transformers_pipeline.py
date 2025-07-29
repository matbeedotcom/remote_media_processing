import asyncio
import logging
from typing import Optional, Any, Dict

from remotemedia.core.node import Node
from remotemedia.core.exceptions import NodeError

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


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


__all__ = ["TransformersPipelineNode"] 