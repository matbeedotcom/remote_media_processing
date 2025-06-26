import asyncio
import json
import logging
from fractions import Fraction

import aiohttp
import pytest
from aiortc import RTCSessionDescription
from av import AudioFrame

from remote_service.src.signaling_server import app as signaling_app
from remotemedia.core.pipeline import Pipeline
from remotemedia.webrtc import WebRTCManager

# Mark all tests in this file as asyncio
pytestmark = pytest.mark.asyncio

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def create_dummy_audio_frame() -> AudioFrame:
    """Creates a blank, silent audio frame for testing purposes."""
    frame = AudioFrame(format="s16", layout="stereo", samples=1024)
    frame.pts = 0
    frame.sample_rate = 48000
    # The time_base is essential for aiortc to calculate the RTP timestamp.
    # It must be a fractions.Fraction object.
    frame.time_base = Fraction(1, frame.sample_rate)
    for p in frame.planes:
        p.update(bytes(p.buffer_size))
    return frame


@pytest.fixture
async def signaling_server(aiohttp_server):
    """Fixture to run the signaling server."""
    server = await aiohttp_server(signaling_app)
    return server


async def exchange_sdp(session, url, offer):
    """Helper function to perform the offer/answer exchange."""
    async with session.post(url, json={"sdp": offer.sdp, "type": offer.type}) as response:
        response.raise_for_status()
        answer_data = await response.json()
        return RTCSessionDescription(sdp=answer_data["sdp"], type=answer_data["type"]), answer_data.get("id")


async def test_webrtc_with_aiohttp_signaling(signaling_server):
    """
    Tests the full WebRTC loop using an aiohttp server for signaling.
    """
    offerer_manager = WebRTCManager(send_audio=True)
    result_received = asyncio.Event()
    received_result_data = None

    # The offerer pipeline is minimal, just to keep the manager's tracks alive.
    offerer_pipeline = Pipeline([offerer_manager.create_source_node()])

    # Create a data channel for the server to send the result back
    result_channel = offerer_manager.add_data_channel("result-channel")

    @result_channel.on("message")
    def on_message(message):
        nonlocal received_result_data
        logger.info(f"Client received result via data channel: {message}")
        received_result_data = json.loads(message)
        result_received.set()

    async with offerer_pipeline.managed_execution():
        try:
            # 1. Create offer
            offer = await offerer_manager.create_offer()
            await offerer_manager.wait_for_ice_gathering()
            offer_with_candidates = offerer_manager.pc.localDescription

            # 2. Exchange SDP with the server
            async with aiohttp.ClientSession() as session:
                server_url = f"http://{signaling_server.host}:{signaling_server.port}"
                answer, peer_id = await exchange_sdp(session, f"{server_url}/offer", offer_with_candidates)
                assert peer_id is not None, "Server did not return a peer ID"

                # 3. Set remote description and wait for connection
                await offerer_manager.handle_answer(answer)
                await offerer_manager.wait_for_connection()

                # 4. Send a frame from the offerer.
                dummy_frame = create_dummy_audio_frame()
                logger.info(f"Offerer sending frame (pts={dummy_frame.pts})")
                await offerer_manager.audio_track.put_frame(dummy_frame)
                await asyncio.sleep(1) # Give server time to process and send result
                
                # 5. Wait for the result from the server via the data channel
                logger.info(f"Client waiting for result via data channel...")
                await asyncio.wait_for(result_received.wait(), timeout=10)

                # 6. Assert that the received data is correct.
                assert received_result_data is not None
                assert received_result_data["status"] == "ok"
                assert received_result_data["pts"] == dummy_frame.pts
                assert received_result_data["sample_rate"] == dummy_frame.sample_rate
                assert received_result_data["samples"] == dummy_frame.samples

        except Exception as e:
            pytest.fail(f"Test failed with exception: {e}")
        finally:
            await offerer_manager.close() 