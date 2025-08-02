"""Test numpy installation in remote execution."""

import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from remotemedia.core.node import RemoteExecutorConfig
from remotemedia.remote.proxy_client import RemoteProxyClient


class SimpleNumpyTest:
    def test_numpy(self):
        import numpy as np
        arr = np.array([1, 2, 3, 4, 5])
        return {
            "mean": float(np.mean(arr)),
            "sum": float(np.sum(arr)),
            "array": arr.tolist()
        }


async def main():
    config = RemoteExecutorConfig(
        host="localhost", 
        port=50052, 
        ssl_enabled=False,
        pip_packages=["numpy"]
    )
    
    try:
        async with RemoteProxyClient(config) as client:
            test = SimpleNumpyTest()
            remote_test = await client.create_proxy(test)
            
            print("Testing numpy on remote server...")
            result = await remote_test.test_numpy()
            print(f"Result: {result}")
            print("✅ Success! Numpy was installed and used on the remote server.")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(main())