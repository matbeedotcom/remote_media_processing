# M1 Mac Troubleshooting Guide

This guide addresses specific issues encountered when running RemoteMedia SDK tests on Apple Silicon (M1/M2) Macs.

## WebRTC Tests

### Issue: "Playwright browser is not found"

**Solution:**
```bash
# Install Chromium specifically
playwright install chromium

# If that fails, try with deps
playwright install-deps chromium
```

### Issue: "pytest: error: unrecognized arguments: --browser"

**Symptom:** 
```
ERROR: usage: pytest [options] [file_or_dir] [file_or_dir] [...]
pytest: error: unrecognized arguments: --browser
```

**Solution:**
Install the correct pytest plugin:
```bash
# WRONG - Don't use this
pip uninstall pytest-playwright

# CORRECT - Use this instead
pip install pytest-playwright-asyncio
```

The package name [[memory:2427620517992630141]] is `pytest-playwright-asyncio`, not `pytest-playwright`.

### Issue: WebRTC Connection Fails - "Not connected"

**Symptoms:**
- Test fails with "Locator expected to have text 'connected' Actual value: Not connected"
- Server logs show "Consent to send expired" after ~30 seconds

**Solutions:**

1. **Use continuous fake audio:**
   The M1 Mac browser args in `tests/webrtc/conftest.py` should include:
   ```python
   "--use-file-for-fake-audio-capture=examples/transcribe_demo.wav",
   "--loop-for-fake-audio-capture",  # Critical for continuous audio
   ```

2. **Check audio file exists:**
   ```bash
   ls examples/transcribe_demo.wav
   # If missing, any WAV file will work
   ```

### Issue: "Future attached to a different loop"

**Symptom:**
```
RuntimeError: Task <Task pending name='Task-5' coro=<WebRTCServer._process_signaling()>> 
got Future <Future pending> attached to a different loop
```

**Solution:**
In the WebRTC server code, use:
```python
# WRONG
self._loop.create_task(...)

# CORRECT
asyncio.create_task(...)
```

## PyTorch Issues

### Issue: "Bus error" when using PyTorch

**Symptom:**
```
[1]    12345 bus error  python your_script.py
```

**Solution:**
Use MPS backend [[memory:3965437357383901367]] instead of CPU:
```python
# WRONG
device = torch.device("cpu")

# CORRECT - Use MPS for M1 Macs
device = torch.device("mps")
```

## General Python Issues

### Issue: Rosetta warnings

**Symptom:**
```
WARNING: You are using an x86_64 version of Python on an arm64 machine.
```

**Solution:**
Install native ARM64 Python:
```bash
# Using Homebrew
brew install python@3.11

# Or use Miniforge for conda
wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-MacOSX-arm64.sh
bash Miniforge3-MacOSX-arm64.sh
```

## Performance Issues

### Issue: Tests run slowly

**Solutions:**

1. **Use native dependencies:**
   ```bash
   # Force reinstall with no binary wheels to compile natively
   pip install --no-binary :all: --force-reinstall numpy
   ```

2. **Check Activity Monitor:**
   - Look for processes running under Rosetta
   - Native processes show as "Apple" in the Kind column

3. **Use MPS acceleration:**
   ```python
   # For PyTorch operations
   if torch.backends.mps.is_available():
       device = torch.device("mps")
   ```

## Browser-Specific Issues

### Issue: Chromium crashes or hangs

**Solutions:**

1. **Add M1-specific flags:**
   ```python
   browser_args = [
       "--disable-gpu",  # Sometimes helps with stability
       "--disable-software-rasterizer",
       "--disable-dev-shm-usage",
       "--no-sandbox",
   ]
   ```

2. **Use headless mode for stability:**
   ```python
   browser = await playwright.chromium.launch(headless=True)
   ```

## Development Environment

### Recommended Setup for M1 Macs

1. **Python:** Use native ARM64 Python 3.11+
2. **Virtual Environment:** 
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```
3. **IDE:** VS Code with Apple Silicon version
4. **Terminal:** Native Terminal.app or iTerm2 (not under Rosetta)

### Checking Your Setup

```bash
# Check Python architecture
python -c "import platform; print(platform.machine())"
# Should output: arm64

# Check if running under Rosetta
sysctl sysctl.proc_translated
# Should output: sysctl.proc_translated: 0
```

## Quick Fixes Checklist

When encountering issues on M1 Mac:

1. ✅ Using `pytest-playwright-asyncio` not `pytest-playwright`
2. ✅ Browser args include `--loop-for-fake-audio-capture`
3. ✅ Using `asyncio.create_task()` not `self._loop.create_task()`
4. ✅ PyTorch using `mps` device not `cpu`
5. ✅ Running native ARM64 Python not x86_64 under Rosetta
6. ✅ Audio file exists for fake audio capture
7. ✅ Remote service is running if needed

## Still Having Issues?

1. Check the [WebRTC README](webrtc/README.md) for WebRTC-specific details
2. Enable debug logging: `pytest -v -s --log-cli-level=DEBUG`
3. Take screenshots on failure for UI tests
4. Check browser console logs in test output
5. File an issue with:
   - macOS version: `sw_vers`
   - Python version: `python --version`
   - Architecture: `uname -m`
   - Full error output 