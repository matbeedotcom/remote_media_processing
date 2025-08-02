"""Test edge cases and complex scenarios with venv proxies."""

import asyncio
import sys
import os
from typing import Any, Optional, Union
import base64

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from remotemedia.core.node import RemoteExecutorConfig
from remotemedia.remote.proxy_client import RemoteProxyClient


class EdgeCaseProcessor:
    """Test edge cases in remote execution."""
    
    def __init__(self):
        self.cache = {}
    
    # Special argument types
    def handle_none(self, value: Optional[str]) -> str:
        """Test None handling."""
        return f"Received: {value}" if value is not None else "Received: None"
    
    def handle_kwargs(self, *args, **kwargs) -> dict:
        """Test args and kwargs."""
        return {
            "args": list(args),
            "kwargs": kwargs,
            "args_count": len(args),
            "kwargs_count": len(kwargs)
        }
    
    def handle_binary_data(self, data: bytes) -> dict:
        """Test binary data handling."""
        import hashlib
        return {
            "size": len(data),
            "type": str(type(data)),
            "md5": hashlib.md5(data).hexdigest(),
            "sample": data[:20].hex() if len(data) > 0 else ""
        }
    
    # Nested data structures
    def handle_deeply_nested(self, data: dict) -> dict:
        """Test deeply nested structures."""
        def count_depth(obj, current_depth=0):
            if isinstance(obj, dict):
                if not obj:
                    return current_depth
                return max(count_depth(v, current_depth + 1) for v in obj.values())
            elif isinstance(obj, list) and obj:
                return max(count_depth(item, current_depth + 1) for item in obj)
            return current_depth
        
        return {
            "depth": count_depth(data),
            "keys_at_root": list(data.keys()) if isinstance(data, dict) else None,
            "total_items": sum(1 for _ in self._iterate_all(data))
        }
    
    def _iterate_all(self, obj):
        """Helper to iterate all items in nested structure."""
        if isinstance(obj, dict):
            for k, v in obj.items():
                yield (k, v)
                yield from self._iterate_all(v)
        elif isinstance(obj, list):
            for item in obj:
                yield item
                yield from self._iterate_all(item)
    
    # Package-specific functionality
    def use_multiple_packages(self) -> dict:
        """Use multiple packages together."""
        import numpy as np
        import pandas as pd
        from faker import Faker
        import emoji
        import pytz
        from datetime import datetime
        
        fake = Faker()
        
        # Generate fake data
        data = {
            'names': [fake.name() for _ in range(5)],
            'emails': [fake.email() for _ in range(5)],
            'scores': np.random.rand(5) * 100
        }
        
        # Create DataFrame
        df = pd.DataFrame(data)
        
        # Add timezone-aware timestamp
        tz = pytz.timezone('US/Eastern')
        now = datetime.now(tz)
        
        return {
            "dataframe_shape": df.shape,
            "mean_score": float(df['scores'].mean()),
            "emoji_text": emoji.emojize("Data processed :thumbs_up:"),
            "timestamp": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
            "sample_name": df['names'].iloc[0]
        }
    
    # Caching and memoization
    def cached_computation(self, key: str, value: Any) -> dict:
        """Test caching across calls."""
        if key in self.cache:
            return {
                "cached": True,
                "key": key,
                "value": self.cache[key],
                "cache_size": len(self.cache)
            }
        else:
            self.cache[key] = value
            return {
                "cached": False,
                "key": key,
                "value": value,
                "cache_size": len(self.cache)
            }
    
    # Properties (not methods)
    @property
    def computed_property(self) -> dict:
        """Test property access."""
        import platform
        return {
            "platform": platform.system(),
            "python_version": platform.python_version(),
            "cache_items": len(self.cache)
        }
    
    # Exception types
    def raise_custom_error(self, error_type: str):
        """Test different error types."""
        if error_type == "import":
            import nonexistent_module
        elif error_type == "key":
            return {}["missing_key"]
        elif error_type == "index":
            return [][10]
        elif error_type == "type":
            return "string" + 123
        elif error_type == "custom":
            class CustomError(Exception):
                pass
            raise CustomError("This is a custom error")
        else:
            raise ValueError(f"Unknown error type: {error_type}")
    
    # Circular references
    def create_circular_reference(self) -> dict:
        """Test circular reference handling."""
        # Note: This might fail with standard pickle
        obj = {"name": "root"}
        obj["self"] = obj  # Circular reference
        return {"has_circular": True, "name": obj["name"]}
    
    # File-like operations
    def process_file_content(self, content: str, filename: str) -> dict:
        """Process file-like content."""
        import io
        import mimetypes
        
        # Guess MIME type
        mime_type, _ = mimetypes.guess_type(filename)
        
        # Process based on type
        lines = content.splitlines()
        
        return {
            "filename": filename,
            "mime_type": mime_type,
            "size_bytes": len(content.encode()),
            "line_count": len(lines),
            "first_line": lines[0] if lines else None,
            "last_line": lines[-1] if lines else None
        }


async def test_special_arguments():
    """Test special argument handling."""
    print("\n" + "="*60)
    print("TEST: Special Arguments")
    print("="*60)
    
    config = RemoteExecutorConfig(
        host="localhost",
        port=50052,
        ssl_enabled=False,
        pip_packages=[]
    )
    
    async with RemoteProxyClient(config) as client:
        processor = EdgeCaseProcessor()
        remote = await client.create_proxy(processor)
        
        # Test None
        result = await remote.handle_none(None)
        print(f"None handling: {result}")
        assert result == "Received: None"
        
        # Test args and kwargs
        result = await remote.handle_kwargs(1, 2, 3, name="test", value=42)
        print(f"Args/kwargs: {result}")
        assert result["args_count"] == 3
        assert result["kwargs_count"] == 2
        assert result["kwargs"]["name"] == "test"
        
        # Test binary data
        binary = b"Hello, binary world!"
        result = await remote.handle_binary_data(binary)
        print(f"Binary data: size={result['size']}, md5={result['md5']}")
        assert result["size"] == len(binary)
        
        print("✅ Special arguments passed!")


async def test_nested_structures():
    """Test deeply nested data structures."""
    print("\n" + "="*60)
    print("TEST: Nested Structures")
    print("="*60)
    
    config = RemoteExecutorConfig(
        host="localhost",
        port=50052,
        ssl_enabled=False,
        pip_packages=[]
    )
    
    async with RemoteProxyClient(config) as client:
        processor = EdgeCaseProcessor()
        remote = await client.create_proxy(processor)
        
        # Create deeply nested structure
        nested = {
            "level1": {
                "level2": {
                    "level3": {
                        "level4": {
                            "data": [1, 2, 3, {"inner": "value"}]
                        }
                    }
                },
                "array": [[1, 2], [3, [4, 5]]]
            }
        }
        
        result = await remote.handle_deeply_nested(nested)
        print(f"Nested structure: depth={result['depth']}, total_items={result['total_items']}")
        assert result["depth"] >= 4
        
        print("✅ Nested structures passed!")


async def test_multiple_packages():
    """Test using multiple packages together."""
    print("\n" + "="*60)
    print("TEST: Multiple Package Integration")
    print("="*60)
    
    config = RemoteExecutorConfig(
        host="localhost",
        port=50052,
        ssl_enabled=False,
        pip_packages=["numpy", "pandas", "faker", "emoji", "pytz"]
    )
    
    async with RemoteProxyClient(config) as client:
        processor = EdgeCaseProcessor()
        remote = await client.create_proxy(processor)
        
        result = await remote.use_multiple_packages()
        print(f"Multi-package result: {result}")
        assert result["dataframe_shape"] == (5, 3)
        assert "👍" in result["emoji_text"] or "thumbs_up" in result["emoji_text"]
        assert "EDT" in result["timestamp"] or "EST" in result["timestamp"]
        
        print("✅ Multiple package integration passed!")


async def test_caching():
    """Test caching across multiple calls."""
    print("\n" + "="*60)
    print("TEST: Caching Behavior")
    print("="*60)
    
    config = RemoteExecutorConfig(
        host="localhost",
        port=50052,
        ssl_enabled=False,
        pip_packages=[]
    )
    
    async with RemoteProxyClient(config) as client:
        processor = EdgeCaseProcessor()
        remote = await client.create_proxy(processor)
        
        # First call - should not be cached
        result1 = await remote.cached_computation("key1", "value1")
        print(f"First call: {result1}")
        assert result1["cached"] == False
        
        # Second call with same key - should be cached
        result2 = await remote.cached_computation("key1", "value2")
        print(f"Second call: {result2}")
        assert result2["cached"] == True
        assert result2["value"] == "value1"  # Should return cached value
        
        # Third call with different key
        result3 = await remote.cached_computation("key2", "value2")
        print(f"Third call: {result3}")
        assert result3["cached"] == False
        assert result3["cache_size"] == 2
        
        print("✅ Caching behavior passed!")


async def test_property_access():
    """Test property access (not methods)."""
    print("\n" + "="*60)
    print("TEST: Property Access")
    print("="*60)
    
    config = RemoteExecutorConfig(
        host="localhost",
        port=50052,
        ssl_enabled=False,
        pip_packages=[]
    )
    
    async with RemoteProxyClient(config) as client:
        processor = EdgeCaseProcessor()
        remote = await client.create_proxy(processor)
        
        # Access property (note: properties are returned as coroutines)
        result = await remote.computed_property
        print(f"Property result: {result}")
        assert "platform" in result
        assert "python_version" in result
        
        print("✅ Property access passed!")


async def test_error_types():
    """Test different error types."""
    print("\n" + "="*60)
    print("TEST: Error Types")
    print("="*60)
    
    config = RemoteExecutorConfig(
        host="localhost",
        port=50052,
        ssl_enabled=False,
        pip_packages=[]
    )
    
    async with RemoteProxyClient(config) as client:
        processor = EdgeCaseProcessor()
        remote = await client.create_proxy(processor)
        
        error_types = ["import", "key", "index", "type", "custom"]
        
        for error_type in error_types:
            try:
                await remote.raise_custom_error(error_type)
                assert False, f"Should have raised error for {error_type}"
            except Exception as e:
                print(f"✅ {error_type} error: {type(e).__name__} - {str(e)[:50]}...")


async def test_file_operations():
    """Test file-like operations."""
    print("\n" + "="*60)
    print("TEST: File Operations")
    print("="*60)
    
    config = RemoteExecutorConfig(
        host="localhost",
        port=50052,
        ssl_enabled=False,
        pip_packages=[]
    )
    
    async with RemoteProxyClient(config) as client:
        processor = EdgeCaseProcessor()
        remote = await client.create_proxy(processor)
        
        # Test with different file types
        content = """import numpy as np
import pandas as pd

def process_data(data):
    return np.mean(data)
"""
        
        result = await remote.process_file_content(content, "example.py")
        print(f"File processing: {result}")
        assert result["mime_type"] == "text/x-python"
        assert result["line_count"] == 5
        assert "import numpy" in result["first_line"]
        
        print("✅ File operations passed!")


async def main():
    """Run all edge case tests."""
    print("\nTESTING EDGE CASES WITH VENV PROXIES")
    print("=" * 80)
    
    tests = [
        ("Special Arguments", test_special_arguments),
        ("Nested Structures", test_nested_structures),
        ("Multiple Package Integration", test_multiple_packages),
        ("Caching Behavior", test_caching),
        ("Property Access", test_property_access),
        ("Error Types", test_error_types),
        ("File Operations", test_file_operations),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            await test_func()
            passed += 1
        except Exception as e:
            print(f"\n❌ {name} failed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print(f"\n{'='*80}")
    print(f"SUMMARY: {passed}/{len(tests)} edge case tests passed")
    print('='*80)
    
    if failed == 0:
        print("✅ All edge case tests passed!")
    else:
        print(f"⚠️  {failed} tests failed.")


if __name__ == "__main__":
    asyncio.run(main())