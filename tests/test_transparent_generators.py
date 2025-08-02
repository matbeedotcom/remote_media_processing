"""
Test transparent generator handling with RemoteProxyClient.
"""

import asyncio
from remotemedia.core.node import RemoteExecutorConfig
from remotemedia.remote.proxy_client import RemoteProxyClient
from remotemedia.examples.test_method_types import GeneratorMethods, AsyncGeneratorMethods


async def main():
    config = RemoteExecutorConfig(host="localhost", port=50052, ssl_enabled=False)
    
    async with RemoteProxyClient(config) as client:
        print("=== Transparent Generator Handling ===\n")
        
        # Test regular generators
        print("1. Regular Generators:")
        gen_obj = GeneratorMethods()
        remote = await client.create_proxy(gen_obj)
        
        # This now returns a list directly, no need to check types
        numbers = await remote.count_up_to(5)
        print(f"   count_up_to(5) = {numbers}")
        print(f"   Type: {type(numbers)}")
        
        fib = await remote.fibonacci(10)
        print(f"   fibonacci(10) = {fib}")
        
        squares = await remote.get_squares()
        print(f"   get_squares() = {squares}")
        
        # Test async generators
        print("\n2. Async Generators:")
        async_gen_obj = AsyncGeneratorMethods()
        async_gen_obj.delay = 0.01  # Faster for testing
        remote_async = await client.create_proxy(async_gen_obj)
        
        # These also return lists directly
        async_nums = await remote_async.async_count(5)
        print(f"   async_count(5) = {async_nums}")
        print(f"   Type: {type(async_nums)}")
        
        processed = await remote_async.stream_data(['hello', 'world', 'test'])
        print(f"   stream_data() = {processed}")
        
        # You can iterate over the results like a normal list
        print("\n3. Using the results:")
        print("   Iterating over fibonacci results:")
        for i, val in enumerate(fib[:5]):  # First 5 values
            print(f"     fib[{i}] = {val}")
        
        print("\n✅ Generators are transparently converted to lists!")
        print("   - No need to check types")
        print("   - No need for special handling")
        print("   - Works exactly like a list")


if __name__ == "__main__":
    asyncio.run(main())