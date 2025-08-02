"""
Test streaming generators with RemoteProxyClient.
Shows both materialized (current) and streaming (desired) behavior.
"""

import asyncio
import time
from remotemedia.core.node import RemoteExecutorConfig
from remotemedia.remote.proxy_client import RemoteProxyClient
from remotemedia.examples.test_method_types import AsyncGeneratorMethods


class StreamingDataSource:
    """Example class with streaming methods."""
    
    def __init__(self):
        self.chunk_size = 1024
        self.total_chunks = 10
    
    def read_file_chunks(self, filename="large_file.txt"):
        """Simulate reading a large file in chunks."""
        print(f"[Server] Starting to read {filename} in chunks...")
        for i in range(self.total_chunks):
            # Simulate reading a chunk
            time.sleep(0.1)  # Simulate I/O delay
            chunk = f"Chunk {i+1}/{self.total_chunks} from {filename} (bytes {i*self.chunk_size}-{(i+1)*self.chunk_size})"
            print(f"[Server] Yielding chunk {i+1}")
            yield chunk
        print(f"[Server] Finished reading {filename}")
    
    async def stream_realtime_data(self, source_id="sensor_1"):
        """Simulate streaming real-time data."""
        print(f"[Server] Starting real-time stream from {source_id}")
        for i in range(self.total_chunks):
            await asyncio.sleep(0.1)  # Simulate real-time delay
            data = {
                "timestamp": time.time(),
                "source": source_id,
                "value": i * 10.5,
                "sequence": i
            }
            print(f"[Server] Streaming data point {i}")
            yield data
        print(f"[Server] Stream from {source_id} complete")
    
    async def process_stream(self, items):
        """Process items one by one as they arrive."""
        print("[Server] Starting stream processing")
        async for item in items:
            await asyncio.sleep(0.05)  # Simulate processing
            result = f"Processed: {item}"
            print(f"[Server] Processed item: {item}")
            yield result
        print("[Server] Stream processing complete")


async def test_current_behavior():
    """Test current behavior where generators are materialized."""
    print("=== Current Behavior: Generators Materialized to Lists ===\n")
    
    config = RemoteExecutorConfig(host="localhost", port=50052, ssl_enabled=False)
    async with RemoteProxyClient(config) as client:
        source = StreamingDataSource()
        source.total_chunks = 5  # Fewer chunks for demo
        remote = await client.create_proxy(source)
        
        print("1. Testing file chunk reading (sync generator):")
        start = time.time()
        chunks = await remote.read_file_chunks("data.bin")
        print(f"   Got all chunks at once: {type(chunks)}")
        print(f"   Time to receive: {time.time() - start:.2f}s")
        print(f"   Number of chunks: {len(chunks)}")
        print(f"   First chunk: {chunks[0][:50]}...")
        
        print("\n2. Testing real-time data stream (async generator):")
        start = time.time()
        data_points = await remote.stream_realtime_data("temperature_sensor")
        print(f"   Got all data at once: {type(data_points)}")
        print(f"   Time to receive: {time.time() - start:.2f}s")
        print(f"   Number of data points: {len(data_points)}")
        print(f"   First data point: {data_points[0]}")
        
        print("\n⚠️  Notice: All data is received at once after full generation")
        print("   - Must wait for entire stream to complete")
        print("   - No ability to process items as they arrive")
        print("   - High memory usage for large streams")


async def test_desired_behavior():
    """Demonstrate desired streaming behavior."""
    print("\n\n=== Desired Behavior: True Streaming ===\n")
    
    # This is pseudocode showing what we want to achieve
    print("1. What we want for file chunks:")
    print("""
    # Should work like this:
    async for chunk in remote.read_file_chunks("large_file.txt"):
        print(f"Processing chunk as it arrives: {chunk[:30]}...")
        # Process each chunk immediately without waiting for all
        await process_chunk(chunk)
    """)
    
    print("\n2. What we want for real-time streams:")
    print("""
    # Should support early termination:
    async for data in remote.stream_realtime_data("sensor"):
        print(f"Got data: {data}")
        if data["value"] > threshold:
            print("Threshold reached, stopping early")
            break  # Should stop the remote generator
    """)
    
    print("\n3. What we want for pipeline processing:")
    print("""
    # Should support chaining generators:
    async def input_stream():
        for i in range(1000):
            yield f"item_{i}"
    
    # Process items as they flow through, not all at once
    async for result in remote.process_stream(input_stream()):
        print(f"Got processed result: {result}")
    """)
    
    print("\n✅ Benefits of true streaming:")
    print("   - Process items as they arrive")
    print("   - Low memory usage (don't store entire stream)")
    print("   - Can stop early if needed")
    print("   - Support for infinite streams")
    print("   - Real-time processing capability")


async def demonstrate_workaround():
    """Show a possible workaround using current system."""
    print("\n\n=== Workaround: Chunked Processing ===\n")
    
    config = RemoteExecutorConfig(host="localhost", port=50052, ssl_enabled=False)
    async with RemoteProxyClient(config) as client:
        # Instead of generators, use methods that process chunks
        class ChunkedProcessor:
            def __init__(self):
                self.buffer = []
            
            def process_chunk(self, chunk):
                """Process one chunk at a time."""
                result = f"Processed: {chunk}"
                self.buffer.append(result)
                return result
            
            def get_buffer(self):
                """Get accumulated results."""
                return self.buffer
        
        processor = ChunkedProcessor()
        remote_proc = await client.create_proxy(processor)
        
        print("Processing chunks one at a time:")
        for i in range(5):
            chunk = f"Chunk {i}"
            result = await remote_proc.process_chunk(chunk)
            print(f"   {result}")
        
        buffer = await remote_proc.get_buffer()
        print(f"\nFinal buffer: {buffer}")
        
        print("\n⚠️  This works but requires manual chunking")


async def main():
    """Run all demonstrations."""
    await test_current_behavior()
    await test_desired_behavior()
    await demonstrate_workaround()


if __name__ == "__main__":
    asyncio.run(main())