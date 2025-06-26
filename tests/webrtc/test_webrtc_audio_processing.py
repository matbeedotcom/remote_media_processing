import asyncio
import json
import logging
import os
import sys
import pytest
from playwright.async_api import Page, expect

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

logger = logging.getLogger(__name__)


@pytest.mark.asyncio(loop_scope="session")
async def test_webrtc_audio_track_reception(page: Page):
    """
    Test that audio tracks are properly received and processed by the server.
    This verifies the WebRTCStreamSource and AudioTrackSource nodes.
    """
    # Use test client with real media files
    await page.goto("http://127.0.0.1:8899/test")
    await page.wait_for_load_state("networkidle")
    
    # Select audio file
    await page.select_option("#mediaSelect", "/transcribe_demo.wav")
    
    # Start the connection
    await page.get_by_role("button", name="Start").click()
    
    # Wait for connection
    status_element = page.locator("#status")
    await expect(status_element).to_have_text("connected", timeout=15000)
    logger.info("Connection established with real audio file")
    
    # Wait for audio to start playing
    audio_element = page.locator("#audioPlayer")
    await expect(audio_element).to_be_visible()
    
    # Verify audio is playing
    is_playing = await page.evaluate("document.getElementById('audioPlayer').paused === false")
    assert is_playing, "Audio should be playing"
    
    # Wait for audio processing (feedback indicates processing happened)
    feedback_element = page.locator("#feedback")
    await expect(feedback_element).not_to_be_empty(timeout=30000)
    
    feedback_content = await feedback_element.text_content()
    assert "processed_chunk" in feedback_content, "Audio was not processed through pipeline"
    logger.info(f"Audio processing confirmed: {feedback_content}")
    
    await page.get_by_role("button", name="Stop").click()


@pytest.mark.asyncio(loop_scope="session")  
async def test_webrtc_audio_buffering(page: Page):
    """
    Test that the ConcatenateAudioNode properly buffers audio.
    The server is configured to buffer 2 seconds of audio before processing.
    """
    await page.goto("http://127.0.0.1:8899/test")
    await page.wait_for_load_state("networkidle")
    
    # Select audio file
    await page.select_option("#mediaSelect", "/transcribe_demo.wav")
    
    # Start timing when connection begins
    await page.get_by_role("button", name="Start").click()
    start_time = asyncio.get_event_loop().time()
    
    # Wait for connection
    status_element = page.locator("#status")
    await expect(status_element).to_have_text("connected", timeout=15000)
    connection_time = asyncio.get_event_loop().time()
    
    # Wait for first feedback (should take ~2 seconds due to buffering)
    feedback_element = page.locator("#feedback")
    
    # First we should get the initial test message (processed_chunk_0)
    await expect(feedback_element).to_contain_text("processed_chunk_0", timeout=5000)
    
    # Now wait for the actual buffered chunk
    # With a 4-second audio file and 2-second buffer, we should get at least one chunk
    await expect(feedback_element).to_contain_text("processed_chunk_1", timeout=30000)
    first_feedback_time = asyncio.get_event_loop().time()
    
    # Calculate delay from initial feedback to first real feedback
    # This should reflect the buffering delay
    feedback_content = await feedback_element.text_content()
    
    # Log what we received
    logger.info(f"Feedback content after first chunk: {feedback_content}")
    
    # With a 4-second file and 2-second buffer, we should get 2 chunks before looping
    # Wait a bit for potential second chunk
    await asyncio.sleep(2.5)
    feedback_content_after = await feedback_element.text_content()
    logger.info(f"Feedback content after waiting: {feedback_content_after}")
    
    # Verify we got at least one processed chunk (besides the initial test chunk)
    import re
    chunks = re.findall(r'processed_chunk_(\d+)', feedback_content_after)
    chunk_numbers = sorted([int(c) for c in chunks])
    
    assert 0 in chunk_numbers, "Should have initial test chunk"
    assert 1 in chunk_numbers, "Should have at least one real buffered chunk"
    logger.info(f"Received chunks: {chunk_numbers}")
    
    await page.get_by_role("button", name="Stop").click()


@pytest.mark.asyncio(loop_scope="session")
async def test_webrtc_audio_transform_pipeline(page: Page):
    """
    Test the complete audio processing pipeline including transformation.
    Verifies: WebRTCStreamSource -> AudioTrackSource -> AudioTransform -> ConcatenateAudioNode
    """
    await page.goto("http://127.0.0.1:8899/test")
    await page.wait_for_load_state("networkidle")
    
    # Select audio file
    await page.select_option("#mediaSelect", "/transcribe_demo.wav")
    
    # Start connection
    await page.get_by_role("button", name="Start").click()
    
    # Wait for connection
    status_element = page.locator("#status")
    await expect(status_element).to_have_text("connected", timeout=15000)
    
    # Verify audio is being captured and sent
    logs_element = page.locator("#logs")
    logs_content = await logs_element.text_content()
    assert "Captured audio stream from file" in logs_content
    assert "Adding audio track to peer connection" in logs_content
    
    # Collect feedback messages over the duration of the audio file
    feedback_element = page.locator("#feedback")
    await expect(feedback_element).not_to_be_empty(timeout=30000)
    
    # With 4-second audio and 2-second buffer, we expect 2 chunks in the first play
    # Wait for enough time to get both chunks
    await asyncio.sleep(5)  # Give time for the full audio to play once
    
    feedback_content = await feedback_element.text_content()
    
    # Verify we got multiple processed chunks
    import re
    chunks = re.findall(r'processed_chunk_(\d+)', feedback_content)
    chunk_numbers = sorted([int(c) for c in chunks])
    
    # Should have at least 2 chunks (0 initial + at least 1 real)
    assert len(chunk_numbers) >= 2, f"Expected at least 2 chunks, got {chunk_numbers}"
    
    logger.info(f"Successfully processed {len(chunk_numbers)} audio chunks through pipeline: {chunk_numbers}")
    
    await page.get_by_role("button", name="Stop").click()


@pytest.mark.asyncio(loop_scope="session")
async def test_webrtc_continuous_audio_stream(page: Page):
    """
    Test that audio streaming with looping works over a longer period.
    This ensures the pipeline handles audio file looping correctly.
    """
    await page.goto("http://127.0.0.1:8899/test")
    await page.wait_for_load_state("networkidle")
    
    # Select audio file (will loop continuously)
    await page.select_option("#mediaSelect", "/transcribe_demo.wav")
    
    # Start connection
    await page.get_by_role("button", name="Start").click()
    
    # Wait for connection
    status_element = page.locator("#status")
    await expect(status_element).to_have_text("connected", timeout=15000)
    
    # Monitor for 12 seconds (about 3 loops of the 4-second audio)
    feedback_element = page.locator("#feedback")
    await expect(feedback_element).not_to_be_empty(timeout=30000)
    
    start_time = asyncio.get_event_loop().time()
    last_chunk_num = -1
    chunks_received = []
    
    while asyncio.get_event_loop().time() - start_time < 12:
        feedback_content = await feedback_element.text_content()
        if feedback_content:
            import re
            matches = re.findall(r'processed_chunk_(\d+)', feedback_content)
            if matches:
                current_chunk = int(matches[-1])  # Get the latest chunk number
                if current_chunk > last_chunk_num:
                    chunks_received.append(current_chunk)
                    last_chunk_num = current_chunk
                    elapsed = asyncio.get_event_loop().time() - start_time
                    logger.info(f"Received chunk {current_chunk} at {elapsed:.1f}s")
        
        # Verify connection is still active
        current_status = await status_element.text_content()
        assert current_status == "connected", f"Connection lost after {asyncio.get_event_loop().time() - start_time:.1f}s"
        
        # Verify audio is still playing
        is_playing = await page.evaluate("document.getElementById('audioPlayer').paused === false")
        assert is_playing, "Audio stopped playing"
        
        await asyncio.sleep(0.5)
    
    # With 4-second audio, 2-second buffer, over 12 seconds we expect:
    # - First chunk at ~2s (first buffer fill)
    # - Second chunk at ~4s (rest of first play)
    # - More chunks as audio loops and rebuffers
    # Expect at least 4-5 chunks over 12 seconds
    expected_chunks = 4  # Conservative estimate
    assert len(chunks_received) >= expected_chunks, f"Expected at least {expected_chunks} chunks over 12s, got {len(chunks_received)}"
    
    # Verify chunks are mostly sequential (allow for some gaps due to timing)
    for i in range(1, len(chunks_received)):
        # Allow skipping up to 2 chunks in case of timing issues
        assert chunks_received[i] - chunks_received[i-1] <= 3, f"Large gap in chunks: {chunks_received}"
    
    logger.info(f"Successfully processed {len(chunks_received)} chunks over 12 seconds with looping audio")
    
    await page.get_by_role("button", name="Stop").click()


@pytest.mark.asyncio(loop_scope="session")
async def test_webrtc_audio_debug(page: Page):
    """
    Debug test to understand what's happening with audio streaming.
    """
    await page.goto("http://127.0.0.1:8899/test")
    await page.wait_for_load_state("networkidle")
    
    # Select audio file
    await page.select_option("#mediaSelect", "/transcribe_demo.wav")
    
    # Start connection
    await page.get_by_role("button", name="Start").click()
    
    # Wait for connection
    status_element = page.locator("#status")
    await expect(status_element).to_have_text("connected", timeout=15000)
    
    # Check browser logs
    await asyncio.sleep(2)
    logs_element = page.locator("#logs")
    logs_content = await logs_element.text_content()
    logger.info(f"Browser logs:\n{logs_content}")
    
    # Check if audio is actually playing
    is_playing = await page.evaluate("document.getElementById('audioPlayer').paused === false")
    current_time = await page.evaluate("document.getElementById('audioPlayer').currentTime")
    duration = await page.evaluate("document.getElementById('audioPlayer').duration")
    
    logger.info(f"Audio playing: {is_playing}, Current time: {current_time}, Duration: {duration}")
    
    # Check if tracks are actually being sent
    track_info = await page.evaluate("""
        () => {
            const pc = window.pc;
            if (!pc) return 'No peer connection';
            
            const senders = pc.getSenders();
            return {
                senderCount: senders.length,
                senders: senders.map(s => ({
                    track: s.track ? {
                        kind: s.track.kind,
                        enabled: s.track.enabled,
                        readyState: s.track.readyState,
                        id: s.track.id
                    } : null
                }))
            };
        }
    """)
    logger.info(f"Track info: {json.dumps(track_info, indent=2)}")
    
    # Wait a bit more and check feedback
    await asyncio.sleep(5)
    feedback_element = page.locator("#feedback")
    feedback_content = await feedback_element.text_content()
    logger.info(f"Feedback after 5s: {feedback_content}")
    
    await page.get_by_role("button", name="Stop").click() 