#!/usr/bin/env python3
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path.cwd()))

from remotemedia.core.node import RemoteExecutorConfig
from remotemedia.remote.client import RemoteExecutionClient

async def test():
    print("Testing connection...")
    config = RemoteExecutorConfig(
        host='localhost', 
        port=50052, 
        protocol='grpc', 
        timeout=30.0, 
        ssl_enabled=False
    )
    
    try:
        async with RemoteExecutionClient(config) as client:
            print("Connected successfully!")
            
            status = await client.get_status()
            print(f"Status: {status}")
            
            nodes = await client.list_available_nodes()
            print(f"Available nodes: {len(nodes)}")
            
            # Test simple node execution
            test_data = {"message": "test", "value": 42}
            result = await client.execute_node(
                node_type="PassThroughNode",
                config={},
                input_data=test_data,
                serialization_format="pickle"
            )
            print(f"Node execution result: {result}")
            
            return True
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    result = asyncio.run(test())
    print(f"Test result: {result}") 