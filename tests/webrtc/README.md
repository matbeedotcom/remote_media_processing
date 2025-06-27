# WebRTC Tests

This directory contains tests for the WebRTC functionality of the RemoteMedia SDK. These tests validate real-time audio/video streaming, processing pipelines, and data channel feedback mechanisms.

## Prerequisites

### 1. Install Test Dependencies

```bash
# From the project root
pip install -r requirements-dev.txt

# IMPORTANT: Use pytest-playwright-asyncio, NOT pytest-playwright
pip install pytest-playwright-asyncio
```

⚠️ **Critical**: The package name is `pytest-playwright-asyncio`, not `pytest-playwright`. Using the wrong package will cause plugin conflicts with the browser option.

### 2. Install Playwright Browser

```bash
# Install Chromium for Playwright
playwright install chromium

# If you encounter browser installation issues
playwright install-deps
```

### 3. Start the WebRTC Server

The WebRTC tests require the example server to be running:

```bash
# From the project root
python examples/webrtc_pipeline_server.py
```

The server should start on `http://127.0.0.1:8899`. You should see:
```
INFO:remotemedia.webrtc.server:WebRTC server listening on 127.0.0.1:8899
```

## Running the Tests

### Run All WebRTC Tests

```bash
# From the project root
pytest tests/webrtc/ -v
```

### Run Specific Tests

```bash
# Basic connection test
pytest tests/webrtc/test_webrtc_pipeline.py::test_webrtc_pipeline_e2e -v

# Connection stability test
pytest tests/webrtc/test_webrtc_pipeline.py::test_webrtc_connection_stability -v

# Full pipeline with feedback
pytest tests/webrtc/test_webrtc_pipeline.py::test_webrtc_pipeline_with_feedback -v
```

## M1 Mac Specific Configuration

The WebRTC tests are configured to work on M1 Macs with specific browser launch arguments. These are automatically applied by the `conftest.py` file:

- `--use-fake-device-for-media-stream`: Use fake media devices
- `--use-fake-ui-for-media-stream`: Don't prompt for media permissions
- `--use-file-for-fake-audio-capture`: Use a WAV file for fake audio
- `--loop-for-fake-audio-capture`: Loop the audio file continuously
- `--disable-dev-shm-usage`: Avoid shared memory issues
- `--no-sandbox`: Required for some environments
- `--disable-setuid-sandbox`: Additional sandbox bypass

## Test Descriptions

### `test_webrtc_pipeline_e2e`
- **Purpose**: Basic end-to-end test of WebRTC connection establishment
- **What it does**: Connects to the server, verifies connection status, then cleanly disconnects
- **Duration**: ~15 seconds

### `test_webrtc_connection_stability`
- **Purpose**: Ensures the WebRTC connection remains stable over time
- **What it does**: Establishes connection and monitors it for 10 seconds
- **Duration**: ~25 seconds

### `test_webrtc_pipeline_with_feedback`
- **Purpose**: Tests the full pipeline including data channel feedback
- **What it does**: Connects, waits for feedback messages via data channel
- **Duration**: ~30 seconds

### `test_webrtc_audio_processing.py`
- **Purpose**: Tests audio-specific processing capabilities
- **What it does**: Validates audio track handling, transformations, and pipeline processing

## Architecture Overview

The WebRTC tests use a client-server architecture:

1. **Server** (`examples/webrtc_pipeline_server.py`):
   - Runs a WebRTC signaling server on port 8899
   - Accepts WebRTC connections from test clients
   - Processes incoming audio/video streams through pipelines
   - Sends feedback via data channels

2. **Client** (Playwright-controlled browser):
   - Loads the test HTML page (`webrtc_client_with_datachannel.html`)
   - Establishes WebRTC connection with fake media
   - Creates data channel for feedback
   - Validates connection status and feedback messages

## Troubleshooting

### "Playwright browser is not found"

```bash
playwright install chromium
```

### "Future <Future pending> attached to a different loop"

This indicates an event loop conflict in the server. Ensure the server is using:
- `asyncio.create_task()` instead of `self._loop.create_task()`
- `asyncio.get_running_loop()` in callbacks instead of stored loop references

### "Locator expected to have text 'connected' Actual value: Not connected"

1. Check if the server is running on port 8899
2. Check browser console logs in the test output
3. Look for "Consent to send expired" errors - indicates missing continuous audio
4. Ensure fake audio is configured with `--loop-for-fake-audio-capture`

### "Connection lost after X seconds"

The WebRTC connection requires continuous media flow. If using fake media:
- Ensure `--loop-for-fake-audio-capture` is set
- Check that the audio file (`transcribe_demo.wav`) exists

### Data Channel Not Working

The current implementation requires:
1. Client creates the data channel (not the server)
2. Server listens for data channel via `@pc.on("datachannel")`
3. FeedbackSinkNode has its channel set after connection

### Test Hangs or Times Out

- Default timeout is 30 seconds for most operations
- Check server logs for errors
- Take a screenshot on failure (automatically saved as `test-failure-screenshot.png`)

## Development Tips

### Debugging Failed Tests

1. **Enable verbose logging**:
   ```bash
   pytest tests/webrtc/ -v -s --log-cli-level=DEBUG
   ```

2. **Check browser console**: Test output includes browser logs on failure

3. **Screenshots**: Failed tests save screenshots to help debug UI issues

4. **Server logs**: Run the server with debug logging:
   ```python
   logging.basicConfig(level=logging.DEBUG)
   ```

### Adding New Tests

1. Follow the existing test patterns in `test_webrtc_pipeline.py`
2. Use the `page` fixture from `conftest.py` for browser automation
3. Always clean up connections with the Stop button
4. Use appropriate timeouts for async operations

## Known Issues

1. **ICE Connection State**: May show "checking" even when media is flowing (cosmetic issue)
2. **First feedback message**: May be "server_ready" before actual pipeline output
3. **Audio quality**: Fake audio is mono 16kHz - sufficient for testing but not production quality

## CI/CD Considerations

For CI environments:
1. Ensure Playwright browsers are cached
2. May need additional flags: `--disable-gpu`, `--disable-software-rasterizer`
3. Consider using `xvfb-run` for headless environments without display
4. Increase timeouts for slower CI runners 