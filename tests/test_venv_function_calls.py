"""Test function calling and responses with custom venv proxies."""

import asyncio
import sys
import os
import numpy as np
from datetime import datetime
from typing import List, Dict, Any, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from remotemedia.core.node import RemoteExecutorConfig
from remotemedia.remote.proxy_client import RemoteProxyClient


class DataProcessor:
    """Test class with various method types and return values."""
    
    def __init__(self, name: str = "DataProcessor"):
        self.name = name
        self.state = {"initialized": True, "call_count": 0}
    
    # Simple return types
    def return_string(self) -> str:
        """Return a simple string."""
        import emoji
        self.state["call_count"] += 1
        return emoji.emojize("Hello from :snake: Python!")
    
    def return_number(self, x: float, y: float) -> float:
        """Return a calculated number."""
        import numpy as np
        self.state["call_count"] += 1
        return float(np.sqrt(x**2 + y**2))
    
    def return_list(self, size: int) -> List[float]:
        """Return a list of random numbers."""
        import numpy as np
        self.state["call_count"] += 1
        return np.random.rand(size).tolist()
    
    def return_dict(self) -> Dict[str, Any]:
        """Return a complex dictionary."""
        import pandas as pd
        self.state["call_count"] += 1
        df = pd.DataFrame({'A': [1, 2, 3], 'B': [4, 5, 6]})
        return {
            "dataframe_info": df.to_dict(),
            "shape": df.shape,
            "mean": df.mean().to_dict(),
            "state": self.state.copy()
        }
    
    # Complex data types
    def process_numpy_array(self, data: List[float]) -> Dict[str, Any]:
        """Process numpy array and return statistics."""
        import numpy as np
        from scipy import stats
        
        arr = np.array(data)
        return {
            "mean": float(np.mean(arr)),
            "std": float(np.std(arr)),
            "median": float(np.median(arr)),
            "skewness": float(stats.skew(arr)),
            "kurtosis": float(stats.kurtosis(arr))
        }
    
    def process_dataframe(self, data: List[Dict]) -> Dict[str, Any]:
        """Process pandas DataFrame."""
        import pandas as pd
        
        df = pd.DataFrame(data)
        return {
            "columns": df.columns.tolist(),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "summary": df.describe().to_dict() if len(df.select_dtypes(include=[np.number]).columns) > 0 else {},
            "missing": df.isnull().sum().to_dict()
        }
    
    # State management
    def get_state(self) -> Dict[str, Any]:
        """Get current state."""
        return self.state.copy()
    
    def update_state(self, key: str, value: Any) -> Dict[str, Any]:
        """Update state and return new state."""
        self.state[key] = value
        return self.state.copy()
    
    # Error handling
    def raise_error(self, message: str):
        """Test error propagation."""
        raise ValueError(f"Intentional error: {message}")
    
    # Large data handling
    def generate_large_data(self, size_mb: int) -> Dict[str, Any]:
        """Generate large data to test serialization."""
        import numpy as np
        
        # Generate approximately size_mb of data
        elements = int(size_mb * 1024 * 1024 / 8)  # 8 bytes per float64
        data = np.random.rand(elements)
        
        return {
            "size_bytes": data.nbytes,
            "shape": data.shape,
            "sample": data[:10].tolist(),
            "mean": float(data.mean())
        }
    
    # Async method
    async def async_process(self, delay: float) -> Dict[str, Any]:
        """Async method with delay."""
        import asyncio
        start = datetime.now()
        await asyncio.sleep(delay)
        end = datetime.now()
        
        return {
            "delay_requested": delay,
            "actual_duration": (end - start).total_seconds(),
            "timestamp": end.isoformat()
        }
    
    # Generator method
    def generate_batches(self, total: int, batch_size: int):
        """Generator that yields batches."""
        import numpy as np
        
        for i in range(0, total, batch_size):
            batch = np.arange(i, min(i + batch_size, total))
            yield {
                "batch_index": i // batch_size,
                "batch_data": batch.tolist(),
                "batch_sum": int(np.sum(batch))
            }
    
    # Method with external API call
    def fetch_external_data(self, url: str) -> Dict[str, Any]:
        """Fetch data from external API."""
        import requests
        
        response = requests.get(url, timeout=5)
        return {
            "status_code": response.status_code,
            "content_type": response.headers.get('content-type'),
            "content_length": len(response.content),
            "json": response.json() if 'json' in response.headers.get('content-type', '') else None
        }


async def test_basic_calls():
    """Test basic function calls and returns."""
    print("\n" + "="*60)
    print("TEST: Basic Function Calls")
    print("="*60)
    
    config = RemoteExecutorConfig(
        host="localhost",
        port=50052,
        ssl_enabled=False,
        pip_packages=["emoji", "numpy", "pandas", "scipy"]
    )
    
    async with RemoteProxyClient(config) as client:
        processor = DataProcessor("TestProcessor")
        remote = await client.create_proxy(processor)
        
        # Test string return
        result = await remote.return_string()
        print(f"String return: {result}")
        assert "Hello from" in result
        
        # Test number return with args
        result = await remote.return_number(3.0, 4.0)
        print(f"Number return: {result}")
        assert result == 5.0
        
        # Test list return
        result = await remote.return_list(5)
        print(f"List return: {result}")
        assert len(result) == 5
        assert all(isinstance(x, float) for x in result)
        
        # Test dict return
        result = await remote.return_dict()
        print(f"Dict keys: {list(result.keys())}")
        assert "dataframe_info" in result
        assert result["state"]["call_count"] == 4  # Should track calls
        
        print("✅ Basic calls passed!")


async def test_complex_data():
    """Test complex data processing."""
    print("\n" + "="*60)
    print("TEST: Complex Data Processing")
    print("="*60)
    
    config = RemoteExecutorConfig(
        host="localhost",
        port=50052,
        ssl_enabled=False,
        pip_packages=["numpy", "pandas", "scipy"]
    )
    
    async with RemoteProxyClient(config) as client:
        processor = DataProcessor()
        remote = await client.create_proxy(processor)
        
        # Test numpy array processing
        data = [1.5, 2.3, 3.7, 4.1, 5.9, 6.2, 7.8, 8.4, 9.1, 10.5]
        result = await remote.process_numpy_array(data)
        print(f"Array stats: mean={result['mean']:.2f}, std={result['std']:.2f}")
        assert "skewness" in result
        assert "kurtosis" in result
        
        # Test DataFrame processing
        df_data = [
            {"name": "Alice", "age": 25, "score": 85.5},
            {"name": "Bob", "age": 30, "score": 92.0},
            {"name": "Charlie", "age": 35, "score": 78.5}
        ]
        result = await remote.process_dataframe(df_data)
        print(f"DataFrame columns: {result['columns']}")
        print(f"Data types: {result['dtypes']}")
        assert set(result['columns']) == {"name", "age", "score"}
        
        print("✅ Complex data processing passed!")


async def test_state_persistence():
    """Test state persistence across calls."""
    print("\n" + "="*60)
    print("TEST: State Persistence")
    print("="*60)
    
    config = RemoteExecutorConfig(
        host="localhost",
        port=50052,
        ssl_enabled=False,
        pip_packages=["numpy"]
    )
    
    async with RemoteProxyClient(config) as client:
        processor = DataProcessor()
        remote = await client.create_proxy(processor)
        
        # Get initial state
        state1 = await remote.get_state()
        print(f"Initial state: {state1}")
        
        # Make some calls to update state
        await remote.return_string()
        await remote.return_number(5, 12)
        
        # Check state updated
        state2 = await remote.get_state()
        print(f"After 2 calls: {state2}")
        assert state2["call_count"] == 2
        
        # Update state manually
        state3 = await remote.update_state("custom_value", "test123")
        print(f"After manual update: {state3}")
        assert state3["custom_value"] == "test123"
        assert state3["call_count"] == 2  # Should persist
        
        print("✅ State persistence passed!")


async def test_error_handling():
    """Test error propagation."""
    print("\n" + "="*60)
    print("TEST: Error Handling")
    print("="*60)
    
    config = RemoteExecutorConfig(
        host="localhost",
        port=50052,
        ssl_enabled=False,
        pip_packages=[]
    )
    
    async with RemoteProxyClient(config) as client:
        processor = DataProcessor()
        remote = await client.create_proxy(processor)
        
        try:
            await remote.raise_error("This is a test error")
            assert False, "Should have raised an error"
        except Exception as e:
            print(f"✅ Error properly propagated: {str(e)}")
            assert "Intentional error" in str(e)


async def test_large_data():
    """Test large data serialization."""
    print("\n" + "="*60)
    print("TEST: Large Data Handling")
    print("="*60)
    
    config = RemoteExecutorConfig(
        host="localhost",
        port=50052,
        ssl_enabled=False,
        pip_packages=["numpy"]
    )
    
    async with RemoteProxyClient(config) as client:
        processor = DataProcessor()
        remote = await client.create_proxy(processor)
        
        # Test with 1MB of data
        result = await remote.generate_large_data(1)
        print(f"Generated {result['size_bytes']:,} bytes")
        print(f"Mean value: {result['mean']:.4f}")
        assert result['size_bytes'] > 900000  # Should be close to 1MB
        
        print("✅ Large data handling passed!")


async def test_async_methods():
    """Test async method execution."""
    print("\n" + "="*60)
    print("TEST: Async Methods")
    print("="*60)
    
    config = RemoteExecutorConfig(
        host="localhost",
        port=50052,
        ssl_enabled=False,
        pip_packages=[]
    )
    
    async with RemoteProxyClient(config) as client:
        processor = DataProcessor()
        remote = await client.create_proxy(processor)
        
        # Test async method
        start = datetime.now()
        result = await remote.async_process(0.5)
        duration = (datetime.now() - start).total_seconds()
        
        print(f"Requested delay: {result['delay_requested']}s")
        print(f"Actual duration: {duration:.2f}s")
        assert duration >= 0.5
        assert "timestamp" in result
        
        print("✅ Async methods passed!")


async def test_generators():
    """Test generator methods."""
    print("\n" + "="*60)
    print("TEST: Generator Methods")
    print("="*60)
    
    config = RemoteExecutorConfig(
        host="localhost",
        port=50052,
        ssl_enabled=False,
        pip_packages=["numpy"]
    )
    
    async with RemoteProxyClient(config) as client:
        processor = DataProcessor()
        remote = await client.create_proxy(processor)
        
        # Test generator
        generator = await remote.generate_batches(10, 3)
        
        # Collect all batches
        batches = []
        async for batch in generator:
            batches.append(batch)
            print(f"Batch {batch['batch_index']}: {batch['batch_data']}")
        
        assert len(batches) == 4  # 10 items in batches of 3 = 4 batches
        assert batches[0]['batch_sum'] == 0 + 1 + 2  # First batch sum
        assert batches[-1]['batch_data'] == [9]  # Last batch has 1 item
        
        print("✅ Generator methods passed!")


async def test_external_api():
    """Test external API calls."""
    print("\n" + "="*60)
    print("TEST: External API Calls")
    print("="*60)
    
    config = RemoteExecutorConfig(
        host="localhost",
        port=50052,
        ssl_enabled=False,
        pip_packages=["requests"]
    )
    
    async with RemoteProxyClient(config) as client:
        processor = DataProcessor()
        remote = await client.create_proxy(processor)
        
        # Test API call
        result = await remote.fetch_external_data("https://httpbin.org/json")
        print(f"Status code: {result['status_code']}")
        print(f"Content type: {result['content_type']}")
        assert result['status_code'] == 200
        assert result['json'] is not None
        
        print("✅ External API calls passed!")


async def test_concurrent_calls():
    """Test concurrent method calls."""
    print("\n" + "="*60)
    print("TEST: Concurrent Calls")
    print("="*60)
    
    config = RemoteExecutorConfig(
        host="localhost",
        port=50052,
        ssl_enabled=False,
        pip_packages=["numpy", "emoji"]
    )
    
    async with RemoteProxyClient(config) as client:
        processor = DataProcessor()
        remote = await client.create_proxy(processor)
        
        # Make multiple concurrent calls
        tasks = [
            remote.return_string(),
            remote.return_number(3, 4),
            remote.return_list(10),
            remote.process_numpy_array([1, 2, 3, 4, 5])
        ]
        
        start = datetime.now()
        results = await asyncio.gather(*tasks)
        duration = (datetime.now() - start).total_seconds()
        
        print(f"Completed {len(results)} concurrent calls in {duration:.2f}s")
        assert len(results) == 4
        assert isinstance(results[0], str)
        assert isinstance(results[1], float)
        assert isinstance(results[2], list)
        assert isinstance(results[3], dict)
        
        print("✅ Concurrent calls passed!")


async def main():
    """Run all tests."""
    print("\nTESTING FUNCTION CALLS WITH VENV PROXIES")
    print("=" * 80)
    
    tests = [
        ("Basic Function Calls", test_basic_calls),
        ("Complex Data Processing", test_complex_data),
        ("State Persistence", test_state_persistence),
        ("Error Handling", test_error_handling),
        ("Large Data Handling", test_large_data),
        ("Async Methods", test_async_methods),
        ("Generator Methods", test_generators),
        ("External API Calls", test_external_api),
        ("Concurrent Calls", test_concurrent_calls),
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
    print(f"SUMMARY: {passed}/{len(tests)} tests passed")
    print('='*80)
    
    if failed == 0:
        print("✅ All function call tests with venv proxies passed!")
    else:
        print(f"⚠️  {failed} tests failed.")


if __name__ == "__main__":
    asyncio.run(main())