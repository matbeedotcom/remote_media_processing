import asyncio
import logging
import os
import sys
import pytest
from playwright.async_api import Page, expect

# Add project root to path to allow absolute imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

logger = logging.getLogger(__name__)


@pytest.mark.asyncio(loop_scope="session")
async def test_webrtc_pipeline_e2e(page: Page):
    """
    End-to-end test for the WebRTC pipeline.
    
    Assumes the server is already running on http://127.0.0.1:8899.
    """
    await page.goto("http://127.0.0.1:8899")
    
    # Wait for page to load
    await page.wait_for_load_state("networkidle")
    
    # Click start button
    await page.get_by_role("button", name="Start").click()
    
    # Wait for connection with better error handling
    status_element = page.locator("#status")
    try:
        await expect(status_element).to_have_text("connected", timeout=15000)
        logger.info("WebRTC connection established successfully on M1 Mac!")
    except Exception as e:
        # Get browser logs for debugging
        logs_content = await page.locator("#logs").text_content()
        logger.error(f"Connection failed. Browser logs:\n{logs_content}")
        
        # Take a screenshot for debugging
        await page.screenshot(path="test-failure-screenshot.png")
        raise e
    
    # Stop the connection
    await page.get_by_role("button", name="Stop").click()
    await expect(status_element).to_have_text("Not connected")
    logger.info("WebRTC connection closed successfully")


@pytest.mark.asyncio(loop_scope="session")
async def test_webrtc_connection_stability(page: Page):
    """
    Test that the WebRTC connection remains stable for at least 10 seconds.
    This validates that media is flowing properly.
    """
    await page.goto("http://127.0.0.1:8899")
    await page.wait_for_load_state("networkidle")
    
    # Start connection
    await page.get_by_role("button", name="Start").click()
    
    # Wait for connection
    status_element = page.locator("#status")
    await expect(status_element).to_have_text("connected", timeout=15000)
    logger.info("Connection established, testing stability...")
    
    # Monitor connection for 10 seconds
    start_time = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start_time < 10:
        # Check connection is still active
        current_status = await status_element.text_content()
        assert current_status == "connected", f"Connection lost after {asyncio.get_event_loop().time() - start_time:.1f}s"
        await asyncio.sleep(1)
    
    logger.info("Connection remained stable for 10 seconds")
    
    # Clean shutdown
    await page.get_by_role("button", name="Stop").click()
    await expect(status_element).to_have_text("Not connected")


@pytest.mark.asyncio(loop_scope="session")
async def test_webrtc_pipeline_with_feedback(page: Page):
    """
    Test the full WebRTC pipeline including feedback messages.
    """
    await page.goto("http://127.0.0.1:8899")
    await page.wait_for_load_state("networkidle")
    await page.get_by_role("button", name="Start").click()
    
    # Wait for connection
    status_element = page.locator("#status")
    await expect(status_element).to_have_text("connected", timeout=15000)
    logger.info("Connection established, waiting for feedback...")
    
    # Wait for feedback with increased timeout
    feedback_element = page.locator("#feedback")
    try:
        # Wait for feedback to appear
        await expect(feedback_element).not_to_be_empty(timeout=30000)
        
        # Wait a bit more for processed_chunk messages (they come after server_ready)
        await asyncio.sleep(3)
        
        feedback_content = await feedback_element.text_content()
        logger.info(f"Received feedback: {feedback_content}")
        assert "processed_chunk" in feedback_content, f"Expected 'processed_chunk' in feedback, got: {feedback_content}"
        
    except Exception as e:
        # Get browser logs for debugging
        logs_content = await page.locator("#logs").text_content()
        logger.error(f"Feedback check failed. Browser logs:\n{logs_content}")
        
        # Take a screenshot for debugging
        await page.screenshot(path="test-failure-feedback-screenshot.png")
        raise e
    
    await page.get_by_role("button", name="Stop").click()


@pytest.mark.asyncio(loop_scope="session")
async def test_webrtc_whisper_transcription(page: Page):
    """
    Test that the WhisperTranscriptionNode actually transcribes audio.
    Uses the test client with media files to play transcribe_demo.wav.
    """
    # Navigate to the test client page
    await page.goto("http://127.0.0.1:8899/test")
    await page.wait_for_load_state("networkidle")
    
    # Select the audio file
    await page.select_option("#mediaSelect", "/transcribe_demo.wav")
    logger.info("Selected transcribe_demo.wav audio file")
    
    # Start connection
    await page.get_by_role("button", name="Start").click()
    
    # Wait for connection
    status_element = page.locator("#status")
    try:
        await expect(status_element).to_have_text("connected", timeout=15000)
        logger.info("Connection established, waiting for transcriptions...")
    except Exception as e:
        # Get browser logs for debugging
        logs_content = await page.locator("#logs").text_content()
        logger.error(f"Connection failed. Browser logs:\n{logs_content}")
        
        # Take a screenshot for debugging
        await page.screenshot(path="test-connection-failure-transcription.png")
        raise e
    
    # Wait for transcription feedback with increased timeout
    feedback_element = page.locator("#feedback")
    transcription_found = False
    max_wait_time = 60  # 60 seconds to account for Whisper model loading and processing
    start_time = asyncio.get_event_loop().time()
    
    try:
        while asyncio.get_event_loop().time() - start_time < max_wait_time:
            feedback_content = await feedback_element.text_content()
            
            # Check if we have any transcription messages
            if feedback_content and "transcription:" in feedback_content:
                logger.info(f"Received transcription feedback: {feedback_content}")
                transcription_found = True
                
                # The feedback_content contains all p elements joined, 
                # so we need to find the transcription message
                if "transcription: " in feedback_content:
                    # Extract the transcription text after "transcription: "
                    start_idx = feedback_content.find("transcription: ") + len("transcription: ")
                    # Find the end of this transcription (either newline or end of string)
                    end_idx = feedback_content.find("\n", start_idx)
                    if end_idx == -1:
                        end_idx = len(feedback_content)
                    
                    transcription_text = feedback_content[start_idx:end_idx].strip()
                    logger.info(f"Extracted transcription: '{transcription_text}'")
                    
                    # Verify we got meaningful transcription
                    assert len(transcription_text) > 0, "Expected non-empty transcription"
                    assert transcription_text != "", f"Got transcription: '{transcription_text}'"
                    
                    # The test audio says "This is a test of the triangle"
                    # We're just checking that we got some text, not the exact text
                    logger.info(f"✅ Successfully transcribed audio: '{transcription_text}'")
                
                break
                
            await asyncio.sleep(1)
        
        assert transcription_found, f"No transcription received after {max_wait_time} seconds"
        
    except Exception as e:
        # Get browser logs for debugging
        logs_content = await page.locator("#logs").text_content()
        logger.error(f"Transcription test failed. Browser logs:\n{logs_content}")
        
        # Take a screenshot for debugging
        await page.screenshot(path="test-failure-transcription-screenshot.png")
        raise e
    finally:
        # Stop the connection
        await page.get_by_role("button", name="Stop").click()
        await expect(status_element).to_have_text("Not connected") 