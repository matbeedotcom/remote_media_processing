import asyncio
import logging
import soundfile as sf
import os

from remotemedia.nodes.ml import Qwen2_5OmniNode

# Configure basic logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def main():
    """
    This example demonstrates how to use the Qwen2_5OmniNode to generate
    text and audio from a multimodal conversation.
    """
    # For machines with limited resources, you might want to use a smaller model
    # or adjust torch_dtype and attn_implementation.
    # According to a memory from a past conversation, mps is preferred over cpu.
    qwen_node = Qwen2_5OmniNode(
        name="QwenAssistant",
        model_id="Qwen/Qwen2.5-Omni-3B",
        device="mps",
        torch_dtype="bfloat16"
        # attn_implementation="flash_attention_2", # for CUDA
    )

    try:
        # Initialize the node
        await qwen_node.initialize()

        # Define a conversation with multimodal inputs
        conversation = [
            {
                "role": "system",
                "content": [
                    {"type": "text", "text": "You are Qwen, a virtual human developed by the Qwen Team, Alibaba Group, capable of perceiving auditory and visual inputs, as well as generating text and speech."}
                ],
            },
            {
                "role": "user",
                "content": [
                    # You can use local file paths for audio, video, and images
                    {"type": "video", "video": "https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen2.5-Omni/draw.mp4"},
                    # {"type": "audio", "audio": "path/to/your/audio.wav"},
                    # {"type": "image", "image": "path/to/your/image.jpg"},
                ],
            },
        ]

        logger.info("Processing conversation with Qwen2.5-Omni...")
        text_responses, audio_response = await qwen_node.process(conversation)

        if text_responses:
            for i, response in enumerate(text_responses):
                logger.info(f"Generated Text Response {i+1}: {response}")

        if audio_response is not None:
            output_filename = "qwen_output.wav"
            sf.write(output_filename, audio_response, samplerate=24000)
            logger.info(f"Generated audio saved to {os.path.abspath(output_filename)}")

    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
    finally:
        # Clean up the node
        await qwen_node.cleanup()

if __name__ == "__main__":
    asyncio.run(main()) 