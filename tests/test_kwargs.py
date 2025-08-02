"""
Test script to verify keyword argument support in remote execution.
"""

import asyncio
import sys
import os

# Add the parent directory to path so we can import remotemedia
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from remotemedia.core.node import RemoteExecutorConfig
from remotemedia.remote.proxy_client import RemoteProxyClient


class TestClass:
    """Simple test class to verify kwargs work."""
    
    def method_with_kwargs(self, a, b=10, c=20):
        """Method that uses keyword arguments."""
        return {
            "a": a,
            "b": b,
            "c": c,
            "sum": a + b + c
        }
    
    async def async_method_with_kwargs(self, x, y=5, z=15):
        """Async method with keyword arguments."""
        await asyncio.sleep(0.1)
        return {
            "x": x,
            "y": y,
            "z": z,
            "product": x * y * z
        }
    
    def mixed_args(self, *args, **kwargs):
        """Method with both *args and **kwargs."""
        return {
            "args": args,
            "kwargs": kwargs,
            "args_count": len(args),
            "kwargs_count": len(kwargs)
        }


async def test_keyword_arguments():
    """Test that keyword arguments work correctly."""
    print("Testing Keyword Argument Support")
    print("=" * 50)
    
    config = RemoteExecutorConfig(host="localhost", port=50052, ssl_enabled=False)
    
    try:
        async with RemoteProxyClient(config) as client:
            # Create remote proxy
            test_obj = TestClass()
            remote_obj = await client.create_proxy(test_obj)
            
            # Test 1: Method with default kwargs
            print("\n1. Testing method with default kwargs:")
            result1 = await remote_obj.method_with_kwargs(5)
            print(f"   method_with_kwargs(5) = {result1}")
            assert result1["a"] == 5
            assert result1["b"] == 10  # default
            assert result1["c"] == 20  # default
            assert result1["sum"] == 35
            
            # Test 2: Override one kwarg
            print("\n2. Testing with one kwarg override:")
            result2 = await remote_obj.method_with_kwargs(5, b=100)
            print(f"   method_with_kwargs(5, b=100) = {result2}")
            assert result2["a"] == 5
            assert result2["b"] == 100
            assert result2["c"] == 20  # default
            assert result2["sum"] == 125
            
            # Test 3: Override all kwargs
            print("\n3. Testing with all kwargs:")
            result3 = await remote_obj.method_with_kwargs(5, b=100, c=200)
            print(f"   method_with_kwargs(5, b=100, c=200) = {result3}")
            assert result3["a"] == 5
            assert result3["b"] == 100
            assert result3["c"] == 200
            assert result3["sum"] == 305
            
            # Test 4: Async method with kwargs
            print("\n4. Testing async method with kwargs:")
            result4 = await remote_obj.async_method_with_kwargs(2, y=3, z=4)
            print(f"   async_method_with_kwargs(2, y=3, z=4) = {result4}")
            assert result4["x"] == 2
            assert result4["y"] == 3
            assert result4["z"] == 4
            assert result4["product"] == 24
            
            # Test 5: Mixed args and kwargs
            print("\n5. Testing mixed *args and **kwargs:")
            result5 = await remote_obj.mixed_args(1, 2, 3, foo="bar", baz="qux")
            print(f"   mixed_args(1, 2, 3, foo='bar', baz='qux') = {result5}")
            assert result5["args"] == (1, 2, 3)
            assert result5["kwargs"] == {"foo": "bar", "baz": "qux"}
            assert result5["args_count"] == 3
            assert result5["kwargs_count"] == 2
            
            print("\n✅ All keyword argument tests passed!")
            
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        print(f"   Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        print("\n⚠️  Make sure the remote server is running with the updated code!")


if __name__ == "__main__":
    asyncio.run(test_keyword_arguments())