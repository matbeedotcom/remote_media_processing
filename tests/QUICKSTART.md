# Test Quick Start Guide

Quick reference for running RemoteMedia SDK tests.

## Most Common Commands

```bash
# Run all tests
pytest tests/ -v

# Run tests without remote service
pytest tests/ -v -k "not remote"

# Run only WebRTC tests (requires setup - see tests/webrtc/README.md)
pytest tests/webrtc/ -v

# Run with output visible
pytest tests/ -v -s

# Run specific test file
pytest tests/test_pipeline.py -v

# Run specific test function
pytest tests/test_pipeline.py::test_basic_pipeline -v
```

## Before Running Tests

### 1. Basic Setup
```bash
pip install -e .
pip install -r requirements-dev.txt
```

### 2. For WebRTC Tests
```bash
pip install pytest-playwright-asyncio
playwright install chromium

# Start the server in another terminal
python examples/webrtc_pipeline_server.py
```

### 3. For Remote Execution Tests
```bash
# Start remote service in another terminal
cd remote_service && ./scripts/run.sh
```

### 4. For ML Tests
```bash
pip install -r requirements-ml.txt
```

## Debugging

```bash
# See all output
pytest tests/test_specific.py -v -s

# Stop on first failure
pytest tests/ -v -x

# Run last failed tests
pytest tests/ --lf

# With debug logging
pytest tests/ -v --log-cli-level=DEBUG
```

## Quick Test Categories

```bash
# Core functionality (fast, no external deps)
pytest tests/test_pipeline.py tests/test_audio_nodes.py -v

# Remote tests only
pytest tests/test_remote*.py -v

# Skip slow tests
pytest tests/ -v -m "not slow"
```

## Coverage

```bash
# Run with coverage
pytest tests/ --cov=remotemedia

# Generate HTML report
pytest tests/ --cov=remotemedia --cov-report=html
open htmlcov/index.html
```

For more details, see [Full Test README](README.md) 