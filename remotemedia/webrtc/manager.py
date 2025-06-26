"""
WebRTC Manager for real-time communication.
"""

import asyncio
import logging
from typing import Any, Optional, Dict, List
import uuid

from ..core.exceptions import NodeError
from ..core.pipeline import Pipeline
from .sink import PipelineTrack
from .sink import WebRTCSinkNode

logger = logging.getLogger(__name__)

try:
    from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription
    from aiortc.contrib.media import MediaStreamTrack
    from aiortc.rtcdatachannel import RTCDataChannel
    AIORTC_AVAILABLE = True
except ImportError:
    AIORTC_AVAILABLE = False
    # Dummy classes for type hinting
    class RTCPeerConnection: pass
    class RTCSessionDescription: pass
    class RTCConfiguration: pass
    class RTCIceServer: pass
    class MediaStreamTrack: pass
    class RTCDataChannel: pass


class WebRTCManager:
    """
    Manages the lifecycle of a single RTCPeerConnection, primarily for use in
    client-side applications or point-to-point connections.

    This class simplifies setting up a WebRTC connection by handling the
    creation of the peer connection, managing outbound tracks, and orchestrating
    the signaling (offer/answer) process.

    For server-side applications handling multiple clients, see `WebRTCServer`.
    """

    def __init__(
        self,
        ice_servers: Optional[List[Dict]] = None,
        send_audio: bool = True,
        send_video: bool = True,
        receive_audio: bool = True,
        receive_video: bool = True,
    ):
        """
        Initializes the WebRTCManager.

        Args:
            ice_servers: An optional list of dictionaries, each specifying
                         an ICE server (e.g., STUN or TURN).
            send_audio: If True, creates and adds an audio track for sending.
            send_video: If True, creates and adds a video track for sending.
            receive_audio: If True, creates a transceiver for receiving audio.
            receive_video: If True, creates a transceiver for receiving video.
        """
        if not AIORTC_AVAILABLE:
            raise NodeError("aiortc is not installed. Please install it to use WebRTCManager.")
        
        self.id = str(uuid.uuid4())[:8]
        logger.info(f"[{self.id}] Initializing WebRTCManager.")

        if ice_servers:
            ice_server_objs = [RTCIceServer(**server) for server in ice_servers]
            config = RTCConfiguration(iceServers=ice_server_objs)
            logger.info(f"[{self.id}] Configuring with {len(ice_server_objs)} ICE servers.")
            self.pc = RTCPeerConnection(configuration=config)
        else:
            logger.info(f"[{self.id}] Configuring without custom ICE servers.")
            self.pc = RTCPeerConnection()
            
        self._audio_track: Optional[PipelineTrack] = None
        self._video_track: Optional[PipelineTrack] = None
        self._data_channels: Dict[str, RTCDataChannel] = {}
        self._connected_event = asyncio.Event()
        self._ice_gathering_complete_event = asyncio.Event()

        @self.pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info(f"[{self.id}] Connection state is {self.pc.connectionState}")
            if self.pc.connectionState == "connected":
                logger.info(f"[{self.id}] Peer connection established.")
                self._connected_event.set()
            elif self.pc.connectionState in ["failed", "closed", "disconnected"]:
                logger.warning(f"[{self.id}] Peer connection is {self.pc.connectionState}.")
                # Unblock waiters if the connection fails or is closed prematurely
                self._connected_event.set()
                self._ice_gathering_complete_event.set()

        @self.pc.on("icegatheringstatechange")
        async def on_icegatheringstatechange():
            logger.info(f"[{self.id}] ICE gathering state is: {self.pc.iceGatheringState}")
            if self.pc.iceGatheringState == "complete":
                self._ice_gathering_complete_event.set()

        # Setup audio transceiver
        if send_audio:
            self._audio_track = PipelineTrack(kind="audio")
            direction = "sendrecv" if receive_audio else "sendonly"
            self.pc.addTransceiver(self._audio_track, direction=direction)
            logger.info(f"[{self.id}] Added audio transceiver with direction '{direction}'.")
        elif receive_audio:
            self.pc.addTransceiver("audio", direction="recvonly")
            logger.info(f"[{self.id}] Added audio transceiver with direction 'recvonly'.")

        # Setup video transceiver
        if send_video:
            self._video_track = PipelineTrack(kind="video")
            direction = "sendrecv" if receive_video else "sendonly"
            self.pc.addTransceiver(self._video_track, direction=direction)
            logger.info(f"[{self.id}] Added video transceiver with direction '{direction}'.")
        elif receive_video:
            self.pc.addTransceiver("video", direction="recvonly")
            logger.info(f"[{self.id}] Added video transceiver with direction 'recvonly'.")

    async def wait_for_connection(self):
        """Waits until the peer connection's state is 'connected'."""
        logger.info(f"[{self.id}] Waiting for peer connection...")
        await self._connected_event.wait()
        if self.pc.connectionState == "connected":
            logger.info(f"[{self.id}] Wait complete: connection is 'connected'.")
        else:
            logger.warning(f"[{self.id}] Wait complete: connection is now '{self.pc.connectionState}'.")
            raise NodeError(f"Connection ended with state: {self.pc.connectionState}")

    async def wait_for_ice_gathering(self):
        """Waits until ICE gathering is complete."""
        logger.info(f"[{self.id}] Waiting for ICE gathering to complete...")
        await self._ice_gathering_complete_event.wait()
        logger.info(f"[{self.id}] ICE gathering complete.")

    def add_data_channel(self, label: str, **kwargs) -> RTCDataChannel:
        """
        Creates a data channel on the peer connection.

        Args:
            label: The label for the data channel.
            **kwargs: Additional options for RTCDataChannel.

        Returns:
            The created RTCDataChannel instance.
        """
        if label in self._data_channels:
            raise NodeError(f"Data channel with label '{label}' already exists.")
        
        logger.info(f"[{self.id}] Creating data channel with label '{label}'.")
        channel = self.pc.createDataChannel(label, **kwargs)
        self._data_channels[label] = channel
        return channel

    async def create_offer(self) -> RTCSessionDescription:
        """
        Creates an SDP offer and sets it as the local description.

        Returns:
            The SDP offer.
        """
        logger.info(f"[{self.id}] Creating SDP offer...")
        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)
        logger.info(f"[{self.id}] SDP offer created and set as local description.")
        return offer

    async def handle_offer_and_create_answer(self, offer: RTCSessionDescription) -> RTCSessionDescription:
        """
        Handles a received offer, sets it as the remote description,
        creates an answer, and sets it as the local description.

        Args:
            offer: The received SDP offer.

        Returns:
            The SDP answer.
        """
        logger.info(f"[{self.id}] Received offer, setting as remote description.")
        await self.pc.setRemoteDescription(offer)
        logger.info(f"[{self.id}] Creating SDP answer...")
        answer = await self.pc.createAnswer()
        await self.pc.setLocalDescription(answer)
        logger.info(f"[{self.id}] SDP answer created and set as local description.")
        return answer

    async def handle_answer(self, answer: RTCSessionDescription):
        """
        Handles a received answer and sets it as the remote description.

        Args:
            answer: The received SDP answer.
        """
        logger.info(f"[{self.id}] Received answer, setting as remote description.")
        await self.pc.setRemoteDescription(answer)
        logger.info(f"[{self.id}] Remote description set from answer.")

    @property
    def audio_track(self) -> Optional[PipelineTrack]:
        return self._audio_track

    @property
    def video_track(self) -> Optional[PipelineTrack]:
        return self._video_track

    @property
    def data_channels(self) -> Dict[str, RTCDataChannel]:
        return self._data_channels

    async def close(self):
        """
        Closes the peer connection and cleans up resources.
        """
        logger.info(f"[{self.id}] Closing peer connection...")
        if self.pc.connectionState != "closed":
            await self.pc.close()
            logger.info(f"[{self.id}] RTCPeerConnection closed.")
        else:
            logger.info(f"[{self.id}] RTCPeerConnection was already closed.")

    def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close() 