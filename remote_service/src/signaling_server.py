import asyncio
import logging
import json
from fractions import Fraction

from aiohttp import web
from aiortc import RTCSessionDescription
from av import AudioFrame

from remotemedia import Pipeline
from remotemedia.webrtc import WebRTCManager
from remotemedia.core.node import Node

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EchoNode(Node):
    """A node that echoes audio/video frames back to the sender."""
    def __init__(self, webrtc_manager: WebRTCManager, **kwargs):
        super().__init__(**kwargs)
        self.webrtc_manager = webrtc_manager
        self.video_track = self.webrtc_manager.video_track
        self.audio_track = self.webrtc_manager.audio_track

    async def process(self, data):
        if not data:
            return None
        if "audio" in data and self.audio_track:
            logger.info(f"[{self.webrtc_manager.id}] Echoing audio frame")
            await self.audio_track.put_frame(data["audio"])
        if "video" in data and self.video_track:
            logger.info(f"[{self.webrtc_manager.id}] Echoing video frame")
            await self.video_track.put_frame(data["video"])
        return data # Pass data along to the next node in the pipeline


class CatcherNode(Node):
    """A simple node that sends a confirmation message over a data channel."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.data_channel = None
        self._confirmation_sent = False

    async def process(self, data):
        logger.info(f"CatcherNode received data: {data.keys()}")
        if self.data_channel and self.data_channel.readyState == "open" and not self._confirmation_sent:
            # The original data from the client has been echoed back.
            # Now, just send a simple confirmation.
            result = {
                "status": "ok",
                "message": "data processing complete"
            }
            self.data_channel.send(json.dumps(result))
            logger.info("CatcherNode sent result over data channel.")
            self._confirmation_sent = True
        return None

async def offer(request):
    """
    Handles an incoming WebRTC offer from a client.
    """
    params = await request.json()
    offer_sdp = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    # 1. Create the "answerer" peer on the server side.
    ice_servers = [{"urls": ["stun:stun.l.google.com:19302"]}]
    answerer_manager = WebRTCManager(
        ice_servers=ice_servers,
        send_audio=True, 
        send_video=True, 
        receive_audio=True, 
        receive_video=True
    )
    request.app["pcs"].add(answerer_manager.pc)
    
    # The pipeline on the server will just receive the frame and send a result back.
    catcher_node = CatcherNode(name=f"Catcher_{answerer_manager.id}")
    echo_node = EchoNode(answerer_manager, name=f"Echo_{answerer_manager.id}")
    pipeline = Pipeline([
        answerer_manager.create_source_node(),
        echo_node,
        catcher_node
    ])

    @answerer_manager.pc.on("datachannel")
    def on_datachannel(channel):
        logger.info(f"Data channel '{channel.label}' received.")
        if channel.label == "result-channel":
            catcher_node.data_channel = channel
            logger.info("Result data channel set on CatcherNode.")

    async def run_pipeline():
        logger.info(f"[{answerer_manager.id}] Starting server-side pipeline...")
        try:
            async with pipeline.managed_execution():
                async for _ in pipeline.process():
                    pass # Keep pipeline running
        except asyncio.CancelledError:
            pass # Task was cancelled on shutdown
        except Exception as e:
            logger.error(f"[{answerer_manager.id}] Server-side pipeline error: {e}", exc_info=True)
        finally:
            logger.info(f"[{answerer_manager.id}] Server-side pipeline finished.")

    # Store the pipeline task to be retrieved later for cleanup.
    request.app[answerer_manager.id] = {
        "task": asyncio.create_task(run_pipeline())
    }
    
    # 2. Handle the offer and create an answer.
    await answerer_manager.handle_offer_and_create_answer(offer_sdp)
    await answerer_manager.wait_for_ice_gathering()
    
    answer_sdp = answerer_manager.pc.localDescription

    # 3. Send the answer back to the client.
    return web.Response(
        content_type="application/json",
        text=json.dumps({
            "sdp": answer_sdp.sdp, 
            "type": answer_sdp.type,
            "id": answerer_manager.id
        }),
    )

async def on_shutdown(app):
    # Close all peer connections
    logger.info("Shutting down signaling server and closing all peer connections...")
    # Clean up any running pipeline tasks
    for peer_id, data in app.items():
        if isinstance(data, dict) and "task" in data:
            data["task"].cancel()
            logger.info(f"Cancelled pipeline task for peer {peer_id}")

    coros = [pc.close() for pc in app["pcs"]]
    await asyncio.gather(*coros, return_exceptions=True)
    app["pcs"].clear()
    logger.info("All peer connections closed.")


def create_app():
    """Creates and configures the aiohttp application."""
    app = web.Application()
    # In-memory storage for the test
    # In a real application, you would use a more robust solution like Redis.
    app["pcs"] = set()
    app.on_shutdown.append(on_shutdown)
    app.router.add_post("/offer", offer)
    return app


def run():
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=8765)


if __name__ == "__main__":
    run() 