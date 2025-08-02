# Streaming Generator Support Design

## Overview

This document outlines the design for supporting true streaming of async generators in the RemoteProxyClient system. Currently, generators are materialized into lists on the server, losing streaming capabilities. This design proposes a solution that preserves the streaming nature of generators while maintaining the transparent proxy interface.

## Current Limitations

1. **Full Materialization**: Generators are converted to lists using `list(generator)` or `[item async for item in async_gen]`
2. **No Streaming**: Entire result set must be generated before returning
3. **No Early Termination**: Cannot stop iteration midway
4. **High Memory Usage**: Large generators consume memory on the server

## Proposed Solution

### 1. Generator Session Management

Add a new session type for managing generator state on the server:

```python
class GeneratorSession:
    def __init__(self, generator, session_id: str):
        self.generator = generator
        self.session_id = session_id
        self.created_at = time.time()
        self.last_accessed = time.time()
        self.is_exhausted = False
        self.lock = asyncio.Lock()
```

### 2. New gRPC Service Methods

Add generator-specific methods to the proto file:

```proto
service RemoteExecutionService {
    // Existing methods...
    
    // Generator streaming support
    rpc InitGenerator(InitGeneratorRequest) returns (InitGeneratorResponse);
    rpc GetNextBatch(GetNextBatchRequest) returns (GetNextBatchResponse);
    rpc CloseGenerator(CloseGeneratorRequest) returns (CloseGeneratorResponse);
}

message InitGeneratorRequest {
    string session_id = 1;           // Object session ID
    string method_name = 2;          // Generator method name
    bytes method_args_data = 3;      // Serialized arguments
    string serialization_format = 4;
}

message InitGeneratorResponse {
    ExecutionStatus status = 1;
    string generator_id = 2;         // Unique generator session ID
    string error_message = 3;
}

message GetNextBatchRequest {
    string generator_id = 1;         // Generator session ID
    int32 batch_size = 2;           // Number of items to fetch
    string serialization_format = 3;
}

message GetNextBatchResponse {
    ExecutionStatus status = 1;
    repeated bytes items = 2;        // Serialized items
    bool has_more = 3;              // More items available
    string error_message = 4;
}

message CloseGeneratorRequest {
    string generator_id = 1;
}

message CloseGeneratorResponse {
    ExecutionStatus status = 1;
}
```

### 3. Server-Side Implementation

#### Generator Detection and Session Creation

```python
# In server.py ExecuteObjectMethod
if request.method_name == "__init__":
    result = None
else:
    attr = getattr(obj, request.method_name)
    
    if callable(attr):
        if asyncio.iscoroutinefunction(attr):
            result = await attr(*method_args)
        else:
            result = attr(*method_args)
        
        # NEW: Check if result is a generator
        if inspect.isgenerator(result) or inspect.isasyncgen(result):
            # Create generator session instead of materializing
            generator_id = str(uuid.uuid4())
            self.generator_sessions[generator_id] = GeneratorSession(
                generator=result,
                session_id=generator_id
            )
            # Return special marker
            result = {"__generator__": True, "generator_id": generator_id}
```

#### New RPC Handlers

```python
async def InitGenerator(self, request, context):
    """Initialize a new generator from an object method."""
    try:
        # Get object from session
        if request.session_id not in self.object_sessions:
            raise ValueError("Session not found")
        
        obj = self.object_sessions[request.session_id]['object']
        
        # Deserialize arguments
        serializer = self._get_serializer(request.serialization_format)
        method_args = serializer.deserialize(request.method_args_data)
        
        # Call method to get generator
        attr = getattr(obj, request.method_name)
        if asyncio.iscoroutinefunction(attr):
            result = await attr(*method_args)
        else:
            result = attr(*method_args)
        
        # Verify it's a generator
        if not (inspect.isgenerator(result) or inspect.isasyncgen(result)):
            raise ValueError(f"Method {request.method_name} did not return a generator")
        
        # Create generator session
        generator_id = str(uuid.uuid4())
        self.generator_sessions[generator_id] = GeneratorSession(
            generator=result,
            session_id=generator_id
        )
        
        return InitGeneratorResponse(
            status=types_pb2.EXECUTION_STATUS_SUCCESS,
            generator_id=generator_id
        )
    except Exception as e:
        return InitGeneratorResponse(
            status=types_pb2.EXECUTION_STATUS_ERROR,
            error_message=str(e)
        )

async def GetNextBatch(self, request, context):
    """Get next batch of items from a generator."""
    try:
        if request.generator_id not in self.generator_sessions:
            raise ValueError("Generator session not found")
        
        session = self.generator_sessions[request.generator_id]
        session.last_accessed = time.time()
        
        async with session.lock:
            if session.is_exhausted:
                return GetNextBatchResponse(
                    status=types_pb2.EXECUTION_STATUS_SUCCESS,
                    items=[],
                    has_more=False
                )
            
            serializer = self._get_serializer(request.serialization_format)
            items = []
            
            for _ in range(request.batch_size):
                try:
                    if inspect.isasyncgen(session.generator):
                        item = await session.generator.__anext__()
                    else:
                        item = next(session.generator)
                    
                    items.append(serializer.serialize(item))
                except (StopIteration, StopAsyncIteration):
                    session.is_exhausted = True
                    break
            
            return GetNextBatchResponse(
                status=types_pb2.EXECUTION_STATUS_SUCCESS,
                items=items,
                has_more=not session.is_exhausted
            )
    except Exception as e:
        return GetNextBatchResponse(
            status=types_pb2.EXECUTION_STATUS_ERROR,
            error_message=str(e)
        )

async def CloseGenerator(self, request, context):
    """Close and cleanup a generator session."""
    try:
        if request.generator_id in self.generator_sessions:
            session = self.generator_sessions[request.generator_id]
            
            # Close generator if it has close method
            if hasattr(session.generator, 'aclose'):
                await session.generator.aclose()
            elif hasattr(session.generator, 'close'):
                session.generator.close()
            
            del self.generator_sessions[request.generator_id]
        
        return CloseGeneratorResponse(
            status=types_pb2.EXECUTION_STATUS_SUCCESS
        )
    except Exception as e:
        return CloseGeneratorResponse(
            status=types_pb2.EXECUTION_STATUS_ERROR
        )
```

### 4. Client-Side Implementation

#### Generator Proxy Class

```python
class RemoteGeneratorProxy:
    """Proxy for remote generators that preserves streaming behavior."""
    
    def __init__(self, client, generator_id: str, is_async: bool = False):
        self._client = client
        self._generator_id = generator_id
        self._is_async = is_async
        self._exhausted = False
    
    def __aiter__(self):
        if not self._is_async:
            raise TypeError("Use __iter__ for sync generators")
        return self
    
    def __iter__(self):
        if self._is_async:
            raise TypeError("Use __aiter__ for async generators")
        return self
    
    async def __anext__(self):
        """Async iteration for async generators."""
        if self._exhausted:
            raise StopAsyncIteration
        
        # Fetch next item (batch size 1 for true streaming)
        response = await self._client._stub.GetNextBatch(
            execution_pb2.GetNextBatchRequest(
                generator_id=self._generator_id,
                batch_size=1,
                serialization_format=self._client._serialization_format
            )
        )
        
        if response.status != types_pb2.EXECUTION_STATUS_SUCCESS:
            raise RuntimeError(f"Generator error: {response.error_message}")
        
        if not response.items:
            self._exhausted = True
            # Cleanup
            await self._client._stub.CloseGenerator(
                execution_pb2.CloseGeneratorRequest(generator_id=self._generator_id)
            )
            raise StopAsyncIteration
        
        # Deserialize and return item
        serializer = self._client._get_serializer()
        return serializer.deserialize(response.items[0])
    
    def __next__(self):
        """Sync iteration (runs async code in sync context)."""
        # This is tricky - we need to run async code in sync context
        # One option is to use asyncio.run_coroutine_threadsafe
        # For now, we'll raise an error
        raise NotImplementedError(
            "Sync iteration of remote generators not yet supported. "
            "Use async iteration instead."
        )
    
    async def aclose(self):
        """Close the generator."""
        await self._client._stub.CloseGenerator(
            execution_pb2.CloseGeneratorRequest(generator_id=self._generator_id)
        )
```

#### Modified ProxyObject

```python
class ProxyObject:
    """Proxy object that forwards method calls to remote execution."""
    
    async def _handle_method_call(self, method_name: str, args: list):
        """Handle a method call, with special handling for generators."""
        result = await self._client._execute_remote_method(
            session_id=self._session_id,
            method_name=method_name,
            method_args=args
        )
        
        # Check if result is a generator marker
        if isinstance(result, dict) and result.get("__generator__"):
            # Return a generator proxy instead of the marker
            generator_id = result["generator_id"]
            # Determine if it's async based on method inspection
            # (would need to track this information)
            return RemoteGeneratorProxy(
                self._client, 
                generator_id,
                is_async=True  # TODO: Detect from method signature
            )
        
        return result
```

### 5. Alternative: Streaming with Batched Fetching

For better performance, we can fetch items in batches while still preserving the generator interface:

```python
class BatchedRemoteGeneratorProxy:
    """Generator proxy that fetches items in batches for efficiency."""
    
    def __init__(self, client, generator_id: str, batch_size: int = 10):
        self._client = client
        self._generator_id = generator_id
        self._batch_size = batch_size
        self._buffer = []
        self._exhausted = False
    
    async def __anext__(self):
        if not self._buffer and not self._exhausted:
            # Fetch next batch
            response = await self._client._stub.GetNextBatch(
                execution_pb2.GetNextBatchRequest(
                    generator_id=self._generator_id,
                    batch_size=self._batch_size,
                    serialization_format=self._client._serialization_format
                )
            )
            
            if response.status != types_pb2.EXECUTION_STATUS_SUCCESS:
                raise RuntimeError(f"Generator error: {response.error_message}")
            
            if response.items:
                serializer = self._client._get_serializer()
                self._buffer = [
                    serializer.deserialize(item) 
                    for item in response.items
                ]
            
            if not response.has_more:
                self._exhausted = True
        
        if self._buffer:
            return self._buffer.pop(0)
        else:
            # Cleanup
            await self._client._stub.CloseGenerator(
                execution_pb2.CloseGeneratorRequest(generator_id=self._generator_id)
            )
            raise StopAsyncIteration
```

## Benefits

1. **True Streaming**: Items are fetched as needed, not all at once
2. **Early Termination**: Client can stop iteration at any time
3. **Memory Efficient**: Server only holds one batch in memory
4. **Transparent**: Works with standard Python iteration protocols
5. **Configurable**: Batch size can be tuned for performance

## Implementation Plan

1. **Phase 1**: Add proto definitions and server-side generator session management
2. **Phase 2**: Implement server RPC handlers for generator operations
3. **Phase 3**: Create client-side generator proxy classes
4. **Phase 4**: Integrate with existing ProxyObject
5. **Phase 5**: Add comprehensive tests
6. **Phase 6**: Update documentation

## Considerations

1. **Session Cleanup**: Need periodic cleanup of abandoned generator sessions
2. **Error Handling**: Generators that raise exceptions need proper handling
3. **Sync Generators**: Supporting sync generators in async client is complex
4. **Performance**: Batching is important for network efficiency
5. **State Management**: Generator state must be thread-safe on server

## Example Usage

```python
# After implementation
async with RemoteProxyClient(config) as client:
    processor = DataProcessor()
    remote = await client.create_proxy(processor)
    
    # Generators work transparently!
    async for chunk in remote.read_large_file("data.bin"):
        print(f"Processing chunk: {chunk}")
        # Can stop early
        if should_stop():
            break  # Generator cleaned up automatically
    
    # Batched iteration for performance
    async for item in remote.process_stream(source, batch_size=50):
        handle(item)
```