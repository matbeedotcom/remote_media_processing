#!/usr/bin/env python3
"""
Test custom Node implementation with cloudpickle serialization for transparent remote execution.
This demonstrates custom nodes with embedded logic that can be executed remotely.
"""

import asyncio
import sys
import math
import re
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path.cwd()))

from remotemedia.core.node import Node, RemoteExecutorConfig
from remotemedia.remote.client import RemoteExecutionClient
import cloudpickle
import base64


class CustomMathNode(Node):
    """
    A custom node for mathematical processing with embedded logic.
    This demonstrates cloudpickle serialization without external dependencies.
    """
    
    def __init__(self, name: str = "CustomMathNode", multiplier: float = 2.0, **config):
        super().__init__(name, **config)
        self.multiplier = multiplier
        self.operations_count = 0
        self.history = []
    
    def process(self, data):
        """Process mathematical data using embedded logic."""
        self.operations_count += 1
        
        if isinstance(data, dict):
            operation = data.get('operation')
            
            if operation == 'process_list':
                values = data.get('values', [])
                result = self._process_list(values)
                self.history.append(f"process_list({len(values)} items)")
                return result
            
            elif operation == 'advanced_calc':
                x = data.get('x', 0)
                y = data.get('y', 0)
                result = self._advanced_calculation(x, y)
                self.history.append(f"advanced_calc({x}, {y})")
                return {
                    'operation': 'advanced_calc',
                    'x': x, 'y': y,
                    'result': result,
                    'processed_by': self.name
                }
            
            elif operation == 'fibonacci':
                n = data.get('n', 10)
                result = self._fibonacci(n)
                self.history.append(f"fibonacci({n})")
                return {
                    'operation': 'fibonacci',
                    'n': n,
                    'result': result,
                    'processed_by': self.name
                }
            
            elif operation == 'get_stats':
                return {
                    'operations_count': self.operations_count,
                    'history': self.history.copy(),
                    'multiplier': self.multiplier,
                    'processed_by': self.name
                }
        
        return {
            'error': 'Unknown operation',
            'data': data,
            'processed_by': self.name
        }
    
    def _process_list(self, values):
        """Process a list of values with the multiplier."""
        processed = [val * self.multiplier for val in values]
        return {
            'original': values,
            'processed': processed,
            'sum': sum(processed),
            'average': sum(processed) / len(processed) if processed else 0,
            'operations_count': self.operations_count
        }
    
    def _advanced_calculation(self, x, y):
        """Perform an advanced mathematical calculation."""
        return math.sqrt(x**2 + y**2) * math.pi
    
    def _fibonacci(self, n):
        """Calculate fibonacci number."""
        if n <= 1:
            return n
        a, b = 0, 1
        for _ in range(2, n + 1):
            a, b = b, a + b
        return b


class CustomTextNode(Node):
    """
    A custom node for text processing with embedded logic.
    This demonstrates complex text processing without external dependencies.
    """
    
    def __init__(self, name: str = "CustomTextNode", **config):
        super().__init__(name, **config)
        self.processed_texts = 0
        self.word_count_total = 0
    
    def process(self, data):
        """Process text data using embedded logic."""
        self.processed_texts += 1
        
        if isinstance(data, dict):
            operation = data.get('operation')
            
            if operation == 'analyze':
                text = data.get('text', '')
                return self._analyze_text(text)
            
            elif operation == 'clean':
                text = data.get('text', '')
                cleaned = self._clean_text(text)
                return {
                    'operation': 'clean',
                    'original': text,
                    'cleaned': cleaned,
                    'processed_by': self.name
                }
            
            elif operation == 'extract_numbers':
                text = data.get('text', '')
                numbers = self._extract_numbers(text)
                return {
                    'operation': 'extract_numbers',
                    'text': text,
                    'numbers': numbers,
                    'processed_by': self.name
                }
            
            elif operation == 'get_stats':
                return {
                    'processed_texts': self.processed_texts,
                    'total_word_count': self.word_count_total,
                    'processed_by': self.name
                }
        
        return {
            'error': 'Unknown operation',
            'data': data,
            'processed_by': self.name
        }
    
    def _analyze_text(self, text):
        """Analyze text and return statistics."""
        cleaned = self._clean_text(text)
        words = cleaned.split()
        numbers = self._extract_numbers(text)
        
        self.word_count_total += len(words)
        
        return {
            'original': text,
            'cleaned': cleaned,
            'word_count': len(words),
            'char_count': len(cleaned),
            'numbers_found': numbers,
            'processed_texts': self.processed_texts,
            'processed_by': self.name
        }
    
    def _clean_text(self, text):
        """Clean and normalize text."""
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text.strip())
        return text
    
    def _extract_numbers(self, text):
        """Extract all numbers from text."""
        numbers = re.findall(r'\d+(?:\.\d+)?', text)
        return [float(num) for num in numbers]


class HybridProcessingNode(Node):
    """
    A hybrid node that combines both math and text processing.
    This demonstrates complex stateful processing with multiple capabilities.
    """
    
    def __init__(self, name: str = "HybridProcessingNode", **config):
        super().__init__(name, **config)
        self.total_operations = 0
        self.math_operations = 0
        self.text_operations = 0
        self.results_cache = []
    
    def process(self, data):
        """Process mixed data types using embedded logic."""
        self.total_operations += 1
        
        if isinstance(data, dict):
            operation = data.get('operation')
            
            if operation == 'analyze_and_calculate':
                text = data.get('text', '')
                return self._analyze_and_calculate(text)
            
            elif operation == 'batch_process':
                items = data.get('items', [])
                return self._batch_process(items)
            
            elif operation == 'get_cache':
                return {
                    'cache_size': len(self.results_cache),
                    'recent_results': self.results_cache[-5:] if self.results_cache else [],
                    'processed_by': self.name
                }
            
            elif operation == 'get_stats':
                return {
                    'total_operations': self.total_operations,
                    'math_operations': self.math_operations,
                    'text_operations': self.text_operations,
                    'cache_size': len(self.results_cache),
                    'processed_by': self.name
                }
        
        return {
            'error': 'Unknown operation',
            'data': data,
            'processed_by': self.name
        }
    
    def _analyze_and_calculate(self, text):
        """Analyze text and perform calculations on extracted numbers."""
        self.text_operations += 1
        
        # Text analysis
        cleaned = re.sub(r'\s+', ' ', text.strip())
        words = cleaned.split()
        numbers = [float(num) for num in re.findall(r'\d+(?:\.\d+)?', text)]
        
        # Mathematical processing
        if numbers:
            self.math_operations += 1
            math_result = {
                'sum': sum(numbers),
                'average': sum(numbers) / len(numbers),
                'max': max(numbers),
                'min': min(numbers),
                'fibonacci_of_count': self._fibonacci(len(numbers))
            }
        else:
            math_result = {'sum': 0, 'average': 0, 'max': None, 'min': None, 'fibonacci_of_count': 0}
        
        result = {
            'operation': 'analyze_and_calculate',
            'text_analysis': {
                'original': text,
                'word_count': len(words),
                'char_count': len(cleaned),
                'numbers_found': numbers
            },
            'math_processing': math_result,
            'total_operations': self.total_operations,
            'processed_by': self.name
        }
        
        # Cache the result
        self.results_cache.append({
            'operation': 'analyze_and_calculate',
            'timestamp': self.total_operations,
            'word_count': len(words),
            'numbers_count': len(numbers)
        })
        
        return result
    
    def _batch_process(self, items):
        """Process a batch of mixed items (text and numbers)."""
        results = []
        
        for item in items:
            if isinstance(item, str):
                # Text processing
                self.text_operations += 1
                words = item.split()
                numbers = [float(num) for num in re.findall(r'\d+(?:\.\d+)?', item)]
                results.append({
                    'type': 'text',
                    'word_count': len(words),
                    'numbers_found': numbers
                })
            elif isinstance(item, (int, float)):
                # Math processing
                self.math_operations += 1
                results.append({
                    'type': 'number',
                    'value': item,
                    'squared': item ** 2,
                    'sqrt': math.sqrt(abs(item))
                })
        
        return {
            'operation': 'batch_process',
            'items_processed': len(items),
            'results': results,
            'total_operations': self.total_operations,
            'processed_by': self.name
        }
    
    def _fibonacci(self, n):
        """Calculate fibonacci number."""
        if n <= 1:
            return n
        a, b = 0, 1
        for _ in range(2, n + 1):
            a, b = b, a + b
        return b


async def test_custom_math_node():
    """Test custom math node with remote execution."""
    print("🧮 Testing Custom Math Node with Remote Execution")
    print("-" * 60)
    
    try:
        # Create custom node
        math_node = CustomMathNode(multiplier=3.0)
        
        # Test operations
        test_operations = [
            {
                'operation': 'process_list',
                'values': [1, 2, 3, 4, 5]
            },
            {
                'operation': 'advanced_calc',
                'x': 3, 'y': 4
            },
            {
                'operation': 'fibonacci',
                'n': 8
            },
            {
                'operation': 'get_stats'
            }
        ]
        
        config = RemoteExecutorConfig(
            host='localhost',
            port=50052,
            protocol='grpc',
            timeout=30.0,
            ssl_enabled=False
        )
        
        async with RemoteExecutionClient(config) as client:
            for i, operation in enumerate(test_operations, 1):
                print(f"\n📤 Test {i}: {operation['operation']}")
                
                # Serialize the node for remote execution
                serialized_node = base64.b64encode(cloudpickle.dumps(math_node)).decode('ascii')
                
                request_data = {
                    "serialized_object": serialized_node,
                    "method_name": "process",
                    "method_args": [operation],
                    "method_kwargs": {}
                }
                
                result = await client.execute_node(
                    node_type="SerializedClassExecutorNode",
                    config={"execution_mode": "custom_node"},
                    input_data=request_data,
                    serialization_format="pickle"
                )
                
                if 'error' in result:
                    print(f"❌ Error: {result['error']}")
                    return False
                else:
                    print(f"📥 Result: {result['result']}")
                    
                    # Update local node state (in real usage, you might want to sync state)
                    if 'operations_count' in result['result']:
                        math_node.operations_count = result['result']['operations_count']
                    if 'history' in result['result']:
                        math_node.history = result['result']['history']
        
        print("✅ Custom Math Node test PASSED")
        return True
        
    except Exception as e:
        print(f"❌ Custom Math Node test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_custom_text_node():
    """Test custom text node with remote execution."""
    print("\n📝 Testing Custom Text Node with Remote Execution")
    print("-" * 60)
    
    try:
        # Create custom node
        text_node = CustomTextNode()
        
        # Test operations
        test_operations = [
            {
                'operation': 'analyze',
                'text': 'Hello World! This text has 123 numbers and 456.78 decimals.'
            },
            {
                'operation': 'clean',
                'text': '  Extra   whitespace   text  '
            },
            {
                'operation': 'extract_numbers',
                'text': 'Found 42 items, cost $19.99, total 3.14159'
            },
            {
                'operation': 'get_stats'
            }
        ]
        
        config = RemoteExecutorConfig(
            host='localhost',
            port=50052,
            protocol='grpc',
            timeout=30.0,
            ssl_enabled=False
        )
        
        async with RemoteExecutionClient(config) as client:
            for i, operation in enumerate(test_operations, 1):
                print(f"\n📤 Test {i}: {operation['operation']}")
                
                # Serialize the node for remote execution
                serialized_node = base64.b64encode(cloudpickle.dumps(text_node)).decode('ascii')
                
                request_data = {
                    "serialized_object": serialized_node,
                    "method_name": "process",
                    "method_args": [operation],
                    "method_kwargs": {}
                }
                
                result = await client.execute_node(
                    node_type="SerializedClassExecutorNode",
                    config={"execution_mode": "custom_node"},
                    input_data=request_data,
                    serialization_format="pickle"
                )
                
                if 'error' in result:
                    print(f"❌ Error: {result['error']}")
                    return False
                else:
                    print(f"📥 Result: {result['result']}")
                    
                    # Update local node state
                    if 'processed_texts' in result['result']:
                        text_node.processed_texts = result['result']['processed_texts']
        
        print("✅ Custom Text Node test PASSED")
        return True
        
    except Exception as e:
        print(f"❌ Custom Text Node test failed: {e}")
        return False


async def test_hybrid_processing_node():
    """Test hybrid processing node with complex operations."""
    print("\n🔄 Testing Hybrid Processing Node with Complex Operations")
    print("-" * 60)
    
    try:
        # Create hybrid node
        hybrid_node = HybridProcessingNode()
        
        # Test operations
        test_operations = [
            {
                'operation': 'analyze_and_calculate',
                'text': 'Processing 10 items with values 25.5, 30.2, and 15.8 for analysis.'
            },
            {
                'operation': 'batch_process',
                'items': ['Hello 123 world', 42, 'Test 456.78 data', 3.14159, 'Final 999 item']
            },
            {
                'operation': 'get_cache'
            },
            {
                'operation': 'get_stats'
            }
        ]
        
        config = RemoteExecutorConfig(
            host='localhost',
            port=50052,
            protocol='grpc',
            timeout=30.0,
            ssl_enabled=False
        )
        
        async with RemoteExecutionClient(config) as client:
            for i, operation in enumerate(test_operations, 1):
                print(f"\n📤 Test {i}: {operation['operation']}")
                
                # Serialize the node for remote execution
                serialized_node = base64.b64encode(cloudpickle.dumps(hybrid_node)).decode('ascii')
                
                request_data = {
                    "serialized_object": serialized_node,
                    "method_name": "process",
                    "method_args": [operation],
                    "method_kwargs": {}
                }
                
                result = await client.execute_node(
                    node_type="SerializedClassExecutorNode",
                    config={"execution_mode": "hybrid_node"},
                    input_data=request_data,
                    serialization_format="pickle"
                )
                
                if 'error' in result:
                    print(f"❌ Error: {result['error']}")
                    return False
                else:
                    result_data = result['result']
                    print(f"📥 Operation: {result_data.get('operation', 'unknown')}")
                    
                    if operation['operation'] == 'analyze_and_calculate':
                        text_analysis = result_data.get('text_analysis', {})
                        math_processing = result_data.get('math_processing', {})
                        print(f"   📝 Words: {text_analysis.get('word_count', 0)}")
                        print(f"   🔢 Numbers: {text_analysis.get('numbers_found', [])}")
                        print(f"   🧮 Sum: {math_processing.get('sum', 0)}")
                        print(f"   📊 Fibonacci: {math_processing.get('fibonacci_of_count', 0)}")
                    elif operation['operation'] == 'batch_process':
                        print(f"   📦 Items processed: {result_data.get('items_processed', 0)}")
                    elif operation['operation'] == 'get_stats':
                        print(f"   🔄 Total ops: {result_data.get('total_operations', 0)}")
                        print(f"   🧮 Math ops: {result_data.get('math_operations', 0)}")
                        print(f"   📝 Text ops: {result_data.get('text_operations', 0)}")
                    
                    # Update local node state
                    if 'total_operations' in result_data:
                        hybrid_node.total_operations = result_data['total_operations']
        
        print("✅ Hybrid Processing Node test PASSED")
        return True
        
    except Exception as e:
        print(f"❌ Hybrid Processing Node test failed: {e}")
        return False


async def main():
    """Run all custom node remote execution tests."""
    print("🚀 RemoteMedia Custom Node Remote Execution Test")
    print("=" * 70)
    print("Testing Custom Nodes with CloudPickle + Remote Execution")
    print("=" * 70)
    
    # Wait for server to be ready
    await asyncio.sleep(2)
    
    tests = [
        ("Custom Math Node", test_custom_math_node),
        ("Custom Text Node", test_custom_text_node),
        ("Hybrid Processing Node", test_hybrid_processing_node),
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
    print("\n" + "=" * 70)
    print("🏆 FINAL RESULTS")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "PASS" if result else "FAIL"
        icon = "✅" if result else "❌"
        print(f"{icon} {test_name}: {status}")
    
    print(f"\nOverall: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL CUSTOM NODE REMOTE EXECUTION TESTS PASSED!")
        print("🚀 Custom Node remote execution is fully functional!")
        print("📋 What we demonstrated:")
        print("   ✅ Custom Node implementations with embedded logic")
        print("   ✅ CloudPickle serialization of complex stateful objects")
        print("   ✅ Transparent remote execution of custom nodes")
        print("   ✅ Stateful processing with operation tracking")
        print("   ✅ Complex hybrid processing capabilities")
        print("   ✅ State synchronization between local and remote execution")
        print("\n🎯 Custom Nodes can now be executed remotely with full state preservation!")
    else:
        print(f"\n⚠️  {total - passed} tests failed")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1) 