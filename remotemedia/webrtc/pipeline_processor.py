"""
Pipeline Processor for WebRTC streams integration.
"""

import asyncio
import logging
import numpy as np
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass
import json

from aiortc import MediaStreamTrack
from aiortc.mediastreams import AudioStreamTrack, VideoStreamTrack
from av import AudioFrame, VideoFrame

from ..core.pipeline import Pipeline
from ..core.node import Node
from ..nodes.source import AudioTrackSource

logger = logging.getLogger(__name__)


@dataclass
class StreamMetadata:
    """Metadata for a WebRTC stream."""
    track_id: str
    kind: str  # 'audio' or 'video'
    label: Optional[str] = None
    enabled: bool = True


class WebRTCStreamSource(Node):
    """
    Node that serves as a source for WebRTC audio/video streams.
    
    This node receives frames from WebRTC tracks and converts them
    to the pipeline's internal format.
    """
    
    def __init__(self, track: MediaStreamTrack, **kwargs):
        super().__init__(**kwargs)
        self.track = track
        self.is_streaming = True
        self._frame_queue = asyncio.Queue(maxsize=100)
        self._processing_task: Optional[asyncio.Task] = None
        
    async def initialize(self):
        """Initialize the stream source."""
        await super().initialize()
        self._processing_task = asyncio.create_task(self._frame_reader())
        
    async def cleanup(self):
        """Clean up the stream source."""
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
        await super().cleanup()
        
    async def _frame_reader(self):
        """Read frames from the WebRTC track and queue them."""
        try:
            while True:
                try:
                    frame = await self.track.recv()
                    if not self._frame_queue.full():
                        await self._frame_queue.put(frame)
                    else:
                        logger.warning(f"Frame queue full for track {self.track.id}, dropping frame")
                except Exception as e:
                    logger.error(f"Error reading frame from track {self.track.id}: {e}")
                    break
        except asyncio.CancelledError:
            logger.debug(f"Frame reader cancelled for track {self.track.id}")
        
    async def process(self, data_stream):
        """Generate frames from the WebRTC track."""
        try:
            while True:
                try:
                    frame = await asyncio.wait_for(self._frame_queue.get(), timeout=1.0)
                    converted_frame = await self._convert_frame(frame)
                    if converted_frame is not None:
                        yield converted_frame
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Error processing frame: {e}")
                    break
        except asyncio.CancelledError:
            logger.debug(f"Stream source processing cancelled for track {self.track.id}")
            
    async def _convert_frame(self, frame):
        """Convert WebRTC frame to pipeline format."""
        if isinstance(frame, AudioFrame):
            return await self._convert_audio_frame(frame)
        elif isinstance(frame, VideoFrame):
            return await self._convert_video_frame(frame)
        else:
            logger.warning(f"Unknown frame type: {type(frame)}")
            return None
            
    async def _convert_audio_frame(self, frame: AudioFrame):
        """Convert audio frame to pipeline format."""
        try:
            # Convert to numpy array
            audio_array = frame.to_ndarray()
            
            # Ensure correct shape (channels, samples)
            if audio_array.ndim == 1:
                audio_array = audio_array.reshape(1, -1)
            elif audio_array.ndim == 2:
                # If shape is (samples, channels), transpose to (channels, samples)
                if audio_array.shape[1] > audio_array.shape[0]:
                    audio_array = audio_array.T
                    
            return (audio_array, frame.sample_rate)
            
        except Exception as e:
            logger.error(f"Error converting audio frame: {e}")
            return None
            
    async def _convert_video_frame(self, frame: VideoFrame):
        """Convert video frame to pipeline format."""
        try:
            # Convert to numpy array (RGB format)
            video_array = frame.to_ndarray(format='rgb24')
            
            return {
                'frame': video_array,
                'width': frame.width,
                'height': frame.height,
                'format': 'rgb24',
                'pts': frame.pts,
                'time_base': frame.time_base
            }
            
        except Exception as e:
            logger.error(f"Error converting video frame: {e}")
            return None


class WebRTCStreamSink(Node):
    """
    Node that serves as a sink for processed data back to WebRTC.
    
    This node receives processed data from the pipeline and can
    send it back through WebRTC data channels or create new tracks.
    """
    
    def __init__(self, connection_id: str, output_callback: Optional[Callable] = None, **kwargs):
        super().__init__(**kwargs)
        self.connection_id = connection_id
        self.output_callback = output_callback
        self.is_streaming = True
        
    async def process(self, data_stream):
        """Process data and forward to WebRTC output."""
        async for data in data_stream:
            try:
                # Send data back through callback if available
                if self.output_callback:
                    await self.output_callback(data)
                    
                # Forward data through pipeline
                yield data
                
            except Exception as e:
                logger.error(f"Error in WebRTC sink: {e}")
                continue


class WebRTCDataChannelNode(Node):
    """
    Node for handling WebRTC data channel messages.
    
    This node can both receive and send data through WebRTC data channels.
    """
    
    def __init__(self, channel_name: str, connection_id: str, **kwargs):
        super().__init__(**kwargs)
        self.channel_name = channel_name
        self.connection_id = connection_id
        self.is_streaming = True
        self._message_queue = asyncio.Queue(maxsize=1000)
        self._send_callback: Optional[Callable] = None
        
    def set_send_callback(self, callback: Callable[[str, Any], None]):
        """Set callback for sending data through the data channel."""
        self._send_callback = callback
        
    async def add_message(self, message: Any):
        """Add a message to the processing queue."""
        if not self._message_queue.full():
            await self._message_queue.put(message)
        else:
            logger.warning(f"Message queue full for channel {self.channel_name}")
            
    async def process(self, data_stream):
        """Process data channel messages and pipeline data."""
        # Create concurrent tasks for both data sources
        async def message_generator():
            while True:
                try:
                    message = await asyncio.wait_for(self._message_queue.get(), timeout=0.1)
                    yield {"type": "datachannel", "channel": self.channel_name, "data": message}
                except asyncio.TimeoutError:
                    continue
                    
        async def pipeline_data_processor():
            async for data in data_stream:
                # Send processed data back through data channel if callback is set
                if self._send_callback:
                    try:
                        serialized_data = json.dumps(data) if isinstance(data, (dict, list)) else str(data)
                        self._send_callback(self.channel_name, serialized_data)
                    except Exception as e:
                        logger.error(f"Error sending data through channel {self.channel_name}: {e}")
                
                yield data
                
        # Process both streams concurrently
        async for item in self._merge_streams(message_generator(), pipeline_data_processor()):
            yield item
            
    async def _merge_streams(self, *streams):
        """Merge multiple async generators."""
        tasks = [asyncio.create_task(stream.__anext__()) for stream in streams]
        
        while tasks:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            
            for task in done:
                try:
                    result = task.result()
                    yield result
                    
                    # Get the stream index and create a new task for it
                    stream_idx = tasks.index(task)
                    tasks[stream_idx] = asyncio.create_task(streams[stream_idx].__anext__())
                    
                except StopAsyncIteration:
                    # Remove completed stream
                    stream_idx = tasks.index(task)
                    tasks.remove(task)
                    streams = streams[:stream_idx] + streams[stream_idx+1:]
                except Exception as e:
                    logger.error(f"Error in stream merge: {e}")
                    stream_idx = tasks.index(task)
                    tasks.remove(task)
                    streams = streams[:stream_idx] + streams[stream_idx+1:]


class WebRTCPipelineProcessor:
    """
    Main processor that integrates WebRTC streams with RemoteMedia pipelines.
    
    This class manages the connection between WebRTC tracks/data channels
    and the pipeline processing system.
    """
    
    def __init__(self, pipeline: Pipeline, connection_id: str):
        self.pipeline = pipeline
        self.connection_id = connection_id
        self.active_tracks: Dict[str, MediaStreamTrack] = {}
        self.stream_sources: Dict[str, WebRTCStreamSource] = {}
        self.data_channels: Dict[str, WebRTCDataChannelNode] = {}
        self.stream_sink: Optional[WebRTCStreamSink] = None
        self._processing_task: Optional[asyncio.Task] = None
        self._initialized = False
        
    async def initialize(self):
        """Initialize the pipeline processor."""
        if self._initialized:
            return
            
        # Add a stream sink to the pipeline for output handling
        self.stream_sink = WebRTCStreamSink(
            connection_id=self.connection_id,
            output_callback=self._handle_pipeline_output,
            name=f"WebRTCSink_{self.connection_id}"
        )
        
        # Don't start processing until tracks are added
        self._initialized = True
        
        logger.info(f"Pipeline processor initialized for connection {self.connection_id}")
        
    async def cleanup(self):
        """Clean up the pipeline processor."""
        if self._processing_task:
            self._processing_task.cancel()
            try:
                await self._processing_task
            except asyncio.CancelledError:
                pass
                
        # Clean up stream sources
        for source in self.stream_sources.values():
            await source.cleanup()
        self.stream_sources.clear()
        
        # Clean up data channels
        self.data_channels.clear()
        
        # Clean up pipeline
        if hasattr(self.pipeline, 'cleanup'):
            await self.pipeline.cleanup()
            
        self._initialized = False
        logger.info(f"Pipeline processor cleaned up for connection {self.connection_id}")
        
    async def add_track(self, track: MediaStreamTrack):
        """Add a WebRTC track to the pipeline."""
        track_id = f"{track.kind}_{track.id}"
        self.active_tracks[track_id] = track
        
        # Create a stream source for this track
        source = WebRTCStreamSource(
            track=track,
            name=f"WebRTCSource_{track_id}"
        )
        self.stream_sources[track_id] = source
        
        # Add the source to the pipeline
        self.pipeline.add_node(source)
        
        await source.initialize()
        
        # Start pipeline processing if this is the first track and we haven't started yet
        if not self._processing_task and self._initialized:
            self._processing_task = asyncio.create_task(self._process_pipeline())
            logger.info(f"Started pipeline processing for connection {self.connection_id}")
        
        logger.info(f"Added {track.kind} track {track.id} to pipeline for connection {self.connection_id}")
        
    async def remove_track(self, track: MediaStreamTrack):
        """Remove a WebRTC track from the pipeline."""
        track_id = f"{track.kind}_{track.id}"
        
        if track_id in self.active_tracks:
            del self.active_tracks[track_id]
            
        if track_id in self.stream_sources:
            await self.stream_sources[track_id].cleanup()
            del self.stream_sources[track_id]
            
        logger.info(f"Removed {track.kind} track {track.id} from pipeline for connection {self.connection_id}")
        
    async def process_data_message(self, channel_name: str, message: Any):
        """Process a data channel message through the pipeline."""
        if channel_name not in self.data_channels:
            # Create a new data channel node
            channel_node = WebRTCDataChannelNode(
                channel_name=channel_name,
                connection_id=self.connection_id,
                name=f"DataChannel_{channel_name}_{self.connection_id}"
            )
            self.data_channels[channel_name] = channel_node
            self.pipeline.add_node(channel_node)
            
        # Add message to the channel's queue
        await self.data_channels[channel_name].add_message(message)
        
    async def _process_pipeline(self):
        """Process the pipeline continuously."""
        try:
            # Add the sink node to the end of the pipeline
            self.pipeline.add_node(self.stream_sink)
            
            # Start pipeline processing
            async with self.pipeline.managed_execution():
                async for result in self.pipeline.process():
                    logger.debug(f"Pipeline result for {self.connection_id}: {type(result)}")
                    
        except asyncio.CancelledError:
            logger.debug(f"Pipeline processing cancelled for connection {self.connection_id}")
        except Exception as e:
            logger.error(f"Error in pipeline processing for {self.connection_id}: {e}")
            
    async def _handle_pipeline_output(self, data: Any):
        """Handle output from the pipeline."""
        try:
            # This is where you can implement custom handling for pipeline output
            # For example, sending results back through data channels,
            # creating new media tracks, or logging results
            
            logger.debug(f"Pipeline output for {self.connection_id}: {type(data)}")
            
            # Example: If data contains audio, you could create an audio track
            # and send it back to the client
            
        except Exception as e:
            logger.error(f"Error handling pipeline output for {self.connection_id}: {e}")
            
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the pipeline processor."""
        return {
            "connection_id": self.connection_id,
            "active_tracks": len(self.active_tracks),
            "stream_sources": len(self.stream_sources),
            "data_channels": len(self.data_channels),
            "initialized": self._initialized,
            "pipeline_nodes": len(self.pipeline.nodes) if hasattr(self.pipeline, 'nodes') else 0
        }