"""
Remote Execution Proxy Client that transparently captures and executes methods remotely.
"""

import asyncio
import logging
from typing import Any, Optional, Dict, List
from functools import wraps

from .client import RemoteExecutionClient
from ..core.node import RemoteExecutorConfig
from ..packaging.code_packager import CodePackager

logger = logging.getLogger(__name__)


class RemoteProxy:
    """
    Proxy wrapper that captures method calls and executes them remotely.
    """
    
    def __init__(self, client: 'RemoteProxyClient', obj: Any, session_id: str):
        self._client = client
        self._obj = obj
        self._session_id = session_id
    
    def __getattr__(self, name: str) -> Any:
        """
        Capture attribute access and create remote method wrappers.
        """
        # Check if the attribute exists on the original object
        if not hasattr(self._obj, name):
            raise AttributeError(f"'{type(self._obj).__name__}' object has no attribute '{name}'")
        
        attr = getattr(self._obj, name)
        
        # If it's a method, wrap it for remote execution
        if callable(attr):
            @wraps(attr)
            async def remote_method(*args, **kwargs):
                """Execute the method remotely."""
                # Combine args and kwargs for remote execution
                method_args = list(args)
                if kwargs:
                    method_args.append(kwargs)
                
                result = await self._client._execute_remote_method(
                    session_id=self._session_id,
                    method_name=name,
                    method_args=method_args
                )
                return result
            
            # Always return async wrapper - caller should await
            return remote_method
        else:
            # For non-callable attributes, we might want to fetch them remotely
            # For now, just return the local attribute
            return attr
    
    def __repr__(self):
        return f"<RemoteProxy({type(self._obj).__name__}) at {self._session_id}>"


class RemoteProxyClient:
    """
    Client that creates proxy objects for transparent remote execution.
    
    Usage:
        async with RemoteProxyClient(config) as client:
            # Create a remote proxy for any object
            counter = Counter()
            remote_counter = await client.create_proxy(counter)
            
            # All method calls are automatically executed remotely
            await remote_counter.increment()
            value = await remote_counter.get_value()
    """
    
    def __init__(self, config: RemoteExecutorConfig):
        """
        Initialize the proxy client.
        
        Args:
            config: Remote executor configuration
        """
        self.config = config
        self.client = RemoteExecutionClient(config)
        self._sessions: Dict[str, Any] = {}  # Track active sessions
    
    async def connect(self) -> None:
        """Connect to the remote execution service."""
        await self.client.connect()
    
    async def disconnect(self) -> None:
        """Disconnect from the remote execution service."""
        await self.client.disconnect()
    
    async def create_proxy(self, obj: Any, serialization_format: str = "pickle") -> RemoteProxy:
        """
        Create a proxy object that executes all methods remotely.
        
        Args:
            obj: The object to create a proxy for
            serialization_format: Serialization format to use
            
        Returns:
            A RemoteProxy that forwards all method calls to the remote service
        """
        # Execute initial object creation remotely and get session ID
        # Use a dummy method to establish the session
        result = await self.client.execute_object_method(
            obj=obj,
            method_name="__class__",  # This is a safe attribute that always exists
            method_args=[],
            serialization_format=serialization_format
        )
        
        session_id = result["session_id"]
        self._sessions[session_id] = obj
        
        return RemoteProxy(self, obj, session_id)
    
    async def _execute_remote_method(
        self,
        session_id: str,
        method_name: str,
        method_args: List[Any],
        serialization_format: str = "pickle"
    ) -> Any:
        """
        Internal method to execute a method remotely using an existing session.
        
        Args:
            session_id: The session ID for the remote object
            method_name: Name of the method to execute
            method_args: Arguments for the method
            serialization_format: Serialization format to use
            
        Returns:
            The result of the remote method execution
        """
        result = await self.client.execute_object_method(
            obj=None,  # We're using session_id instead
            method_name=method_name,
            method_args=method_args,
            serialization_format=serialization_format,
            session_id=session_id
        )
        
        return result["result"]
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()


def remote_class(cls):
    """
    Decorator that automatically creates remote proxies for a class.
    
    Usage:
        @remote_class
        class MyProcessor:
            def process(self, data):
                return expensive_operation(data)
        
        # When instantiated with a RemoteProxyClient, it's automatically remote
        async with RemoteProxyClient(config) as client:
            processor = MyProcessor(_remote_client=client)
            result = await processor.process(data)
    """
    original_init = cls.__init__
    
    @wraps(original_init)
    def new_init(self, *args, _remote_client=None, **kwargs):
        if _remote_client is not None:
            # Create a temporary instance for proxying
            temp_instance = object.__new__(cls)
            original_init(temp_instance, *args, **kwargs)
            
            # Create remote proxy (this is async, so we store it for later)
            self._remote_client = _remote_client
            self._temp_instance = temp_instance
            self._proxy_future = asyncio.create_task(
                _remote_client.create_proxy(temp_instance)
            )
        else:
            # Normal local initialization
            original_init(self, *args, **kwargs)
    
    def __getattribute__(self, name):
        # Check if this is a remote instance
        try:
            remote_client = object.__getattribute__(self, '_remote_client')
            if remote_client is not None:
                proxy_future = object.__getattribute__(self, '_proxy_future')
                
                # Get the proxy (will wait if not ready)
                if asyncio.iscoroutine(proxy_future):
                    proxy = asyncio.get_event_loop().run_until_complete(proxy_future)
                else:
                    proxy = proxy_future
                
                # Forward to proxy
                return getattr(proxy, name)
        except AttributeError:
            pass
        
        # Normal attribute access
        return object.__getattribute__(self, name)
    
    cls.__init__ = new_init
    cls.__getattribute__ = __getattribute__
    
    return cls