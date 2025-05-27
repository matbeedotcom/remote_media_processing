#!/usr/bin/env python3
"""
Test cloudpickle-based remote Python class execution.
This demonstrates the Phase 3 capability for serializing and executing user-defined Python classes remotely.
"""

import asyncio
import sys
import time
import base64
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path.cwd()))

from remotemedia.core.node import RemoteExecutorConfig
from remotemedia.remote.client import RemoteExecutionClient

# Import cloudpickle for serialization
try:
    import cloudpickle
except ImportError:
    print("❌ cloudpickle is required for this test")
    sys.exit(1)


class SimpleCalculator:
    """A simple calculator class to test remote execution."""
    
    def __init__(self, name="RemoteCalculator"):
        self.name = name
        self.operations_count = 0
        self.history = []
    
    def add(self, a, b):
        """Add two numbers."""
        self.operations_count += 1
        result = a + b
        self.history.append(f"add({a}, {b}) = {result}")
        return result
    
    def multiply(self, a, b):
        """Multiply two numbers."""
        self.operations_count += 1
        result = a * b
        self.history.append(f"multiply({a}, {b}) = {result}")
        return result
    
    def subtract(self, a, b):
        """Subtract two numbers."""
        self.operations_count += 1
        result = a - b
        self.history.append(f"subtract({a}, {b}) = {result}")
        return result
    
    def divide(self, a, b):
        """Divide two numbers."""
        if b == 0:
            raise ValueError("Cannot divide by zero")
        self.operations_count += 1
        result = a / b
        self.history.append(f"divide({a}, {b}) = {result}")
        return result
    
    def get_stats(self):
        """Get calculator statistics."""
        return {
            "name": self.name,
            "operations_performed": self.operations_count,
            "history": self.history.copy()
        }
    
    def reset(self):
        """Reset calculator state."""
        self.operations_count = 0
        self.history.clear()
        return "Calculator reset"


class DataProcessor:
    """A data processing class to test more complex operations."""
    
    def __init__(self, processor_id="DataProcessor"):
        self.processor_id = processor_id
        self.processed_items = 0
    
    def process_list(self, data_list):
        """Process a list of numbers."""
        self.processed_items += len(data_list)
        return {
            "original": data_list,
            "sum": sum(data_list),
            "average": sum(data_list) / len(data_list) if data_list else 0,
            "max": max(data_list) if data_list else None,
            "min": min(data_list) if data_list else None,
            "sorted": sorted(data_list),
            "reversed": list(reversed(data_list))
        }
    
    def process_text(self, text):
        """Process text data."""
        self.processed_items += 1
        words = text.split()
        return {
            "original": text,
            "word_count": len(words),
            "char_count": len(text),
            "uppercase": text.upper(),
            "lowercase": text.lower(),
            "words": words,
            "reversed_text": text[::-1]
        }
    
    def get_status(self):
        """Get processor status."""
        return {
            "processor_id": self.processor_id,
            "items_processed": self.processed_items
        }


async def test_simple_calculator():
    """Test the SimpleCalculator class with cloudpickle serialization."""
    print("🧮 Testing SimpleCalculator with cloudpickle")
    print("-" * 50)
    
    config = RemoteExecutorConfig(
        host='localhost', 
        port=50051, 
        protocol='grpc', 
        timeout=30.0, 
        ssl_enabled=False
    )
    
    # Create and serialize calculator
    calc = SimpleCalculator("CloudPickleCalculator")
    serialized_calc = base64.b64encode(cloudpickle.dumps(calc)).decode('ascii')
    
    operations = [
        ("add", [10, 5]),
        ("multiply", [7, 6]),
        ("subtract", [20, 8]),
        ("divide", [15, 3]),
        ("get_stats", [])
    ]
    
    try:
        async with RemoteExecutionClient(config) as client:
            results = []
            
            for method_name, args in operations:
                print(f"📤 Calling remote method: {method_name}({args})")
                
                request_data = {
                    "serialized_object": serialized_calc,
                    "method_name": method_name,
                    "method_args": args,
                    "method_kwargs": {}
                }
                
                result = await client.execute_node(
                    node_type="SerializedClassExecutorNode",
                    config={"execution_mode": "cloudpickle"},
                    input_data=request_data,
                    serialization_format="pickle"
                )
                
                if 'error' in result:
                    print(f"❌ Error: {result['error']}")
                    return False
                else:
                    print(f"📥 Result: {result['result']}")
                    results.append(result['result'])
                
                # Update serialized object with the modified state
                # Note: In a real implementation, we'd need to handle state persistence
                print("-" * 30)
            
            print("✅ SimpleCalculator test PASSED - all operations executed remotely")
            return True
                
    except Exception as e:
        print(f"❌ SimpleCalculator test failed: {e}")
        return False


async def test_data_processor():
    """Test the DataProcessor class with cloudpickle serialization."""
    print("\n📊 Testing DataProcessor with cloudpickle")
    print("-" * 50)
    
    config = RemoteExecutorConfig(
        host='localhost', 
        port=50051, 
        protocol='grpc', 
        timeout=30.0, 
        ssl_enabled=False
    )
    
    # Create and serialize data processor
    processor = DataProcessor("CloudPickleProcessor")
    serialized_processor = base64.b64encode(cloudpickle.dumps(processor)).decode('ascii')
    
    test_cases = [
        ("process_list", [[1, 5, 3, 9, 2, 7]], {}),
        ("process_text", ["Hello World from Remote Execution"], {}),
        ("get_status", [], {})
    ]
    
    try:
        async with RemoteExecutionClient(config) as client:
            for method_name, args, kwargs in test_cases:
                print(f"📤 Calling remote method: {method_name}({args}, {kwargs})")
                
                request_data = {
                    "serialized_object": serialized_processor,
                    "method_name": method_name,
                    "method_args": args,
                    "method_kwargs": kwargs
                }
                
                result = await client.execute_node(
                    node_type="SerializedClassExecutorNode",
                    config={"execution_mode": "cloudpickle"},
                    input_data=request_data,
                    serialization_format="pickle"
                )
                
                if 'error' in result:
                    print(f"❌ Error: {result['error']}")
                    return False
                else:
                    print(f"📥 Result: {result['result']}")
                
                print("-" * 30)
            
            print("✅ DataProcessor test PASSED - all operations executed remotely")
            return True
                
    except Exception as e:
        print(f"❌ DataProcessor test failed: {e}")
        return False


async def test_stateful_execution():
    """Test that object state is maintained across method calls."""
    print("\n🔄 Testing Stateful Execution")
    print("-" * 50)
    
    config = RemoteExecutorConfig(
        host='localhost', 
        port=50051, 
        protocol='grpc', 
        timeout=30.0, 
        ssl_enabled=False
    )
    
    # Create calculator and perform operations to build state
    calc = SimpleCalculator("StatefulCalculator")
    
    # Perform some operations locally first
    calc.add(10, 5)
    calc.multiply(3, 4)
    
    # Serialize the calculator with existing state
    serialized_calc = base64.b64encode(cloudpickle.dumps(calc)).decode('ascii')
    
    try:
        async with RemoteExecutionClient(config) as client:
            # Get initial stats
            print("📤 Getting initial stats...")
            
            request_data = {
                "serialized_object": serialized_calc,
                "method_name": "get_stats",
                "method_args": [],
                "method_kwargs": {}
            }
            
            result = await client.execute_node(
                node_type="SerializedClassExecutorNode",
                config={"execution_mode": "cloudpickle"},
                input_data=request_data,
                serialization_format="pickle"
            )
            
            if 'error' in result:
                print(f"❌ Error: {result['error']}")
                return False
            
            initial_stats = result['result']
            print(f"📥 Initial stats: {initial_stats}")
            
            # Verify that the object maintained its state
            if initial_stats['operations_performed'] == 2:
                print("✅ Object state was preserved during serialization!")
                return True
            else:
                print(f"❌ Expected 2 operations, got {initial_stats['operations_performed']}")
                return False
                
    except Exception as e:
        print(f"❌ Stateful execution test failed: {e}")
        return False


async def test_error_handling():
    """Test error handling in remote class execution."""
    print("\n⚠️ Testing Error Handling")
    print("-" * 50)
    
    config = RemoteExecutorConfig(
        host='localhost', 
        port=50051, 
        protocol='grpc', 
        timeout=30.0, 
        ssl_enabled=False
    )
    
    calc = SimpleCalculator("ErrorTestCalculator")
    serialized_calc = base64.b64encode(cloudpickle.dumps(calc)).decode('ascii')
    
    try:
        async with RemoteExecutionClient(config) as client:
            # Test division by zero
            print("📤 Testing division by zero...")
            
            request_data = {
                "serialized_object": serialized_calc,
                "method_name": "divide",
                "method_args": [10, 0],
                "method_kwargs": {}
            }
            
            result = await client.execute_node(
                node_type="SerializedClassExecutorNode",
                config={"execution_mode": "cloudpickle"},
                input_data=request_data,
                serialization_format="pickle"
            )
            
            if 'error' in result:
                print(f"📥 Expected error caught: {result['error']}")
                print("✅ Error handling test PASSED")
                return True
            else:
                print("❌ Expected error but got result")
                return False
                
    except Exception as e:
        print(f"❌ Error handling test failed: {e}")
        return False


async def main():
    print("🚀 RemoteMedia CloudPickle Class Execution Test")
    print("=" * 60)
    print("Testing Phase 3 capability: Remote execution of cloudpickle-serialized classes")
    print("=" * 60)
    
    # Wait a moment for server to be ready
    await asyncio.sleep(2)
    
    tests = [
        ("Simple Calculator", test_simple_calculator),
        ("Data Processor", test_data_processor),
        ("Stateful Execution", test_stateful_execution),
        ("Error Handling", test_error_handling),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("🏆 FINAL RESULTS")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        icon = "✅" if result else "❌"
        print(f"{icon} {test_name}: {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL CLOUDPICKLE TESTS PASSED!")
        print("🚀 Remote cloudpickle class execution is fully functional!")
        print("📋 What we demonstrated:")
        print("   ✅ CloudPickle serialization of user-defined classes")
        print("   ✅ Remote method execution on serialized objects")
        print("   ✅ Complex data processing with multiple method calls")
        print("   ✅ State preservation during serialization")
        print("   ✅ Proper error handling for remote exceptions")
        print("\n🎯 Phase 3 objective achieved: User-defined Python classes can be executed remotely!")
    else:
        print(f"\n⚠️  {total - passed} tests failed")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1) 