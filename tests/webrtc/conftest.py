import pytest
import logging
import os

logger = logging.getLogger(__name__)


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "webrtc: mark test as a WebRTC test"
    )


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """
    Override the default browser context args to add WebRTC permissions.
    """
    return {
        **browser_context_args,
        "permissions": ["microphone", "camera"],
        "ignore_https_errors": True,
        "viewport": {"width": 1280, "height": 720}
    }


@pytest.fixture(scope="session") 
def browser_type_launch_args(browser_type_launch_args):
    """
    Override browser launch arguments for M1 Mac compatibility.
    """
    # Get absolute path to audio file
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    audio_file = os.path.join(project_root, 'examples', 'transcribe_demo.wav')
    
    return {
        **browser_type_launch_args,
        "args": [
            "--use-fake-device-for-media-stream",
            "--use-fake-ui-for-media-stream", 
            f"--use-file-for-fake-audio-capture={audio_file}",  # Use actual audio file
            "--loop-for-fake-audio-capture",  # Loop the audio file
            "--enable-experimental-web-platform-features",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-web-security",
            "--allow-file-access-from-files",
            "--autoplay-policy=no-user-gesture-required"
        ],
        "headless": False  # Set to True for CI/CD
    } 