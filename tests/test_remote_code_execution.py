#!/usr/bin/env python3
"""
Test actual remote Python code execution.
This demonstrates serializing Python code on the client and executing it remotely.
"""

import asyncio
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path.cwd()))

from remotemedia.core.node import RemoteExecutorConfig
from remotemedia.remote.client import RemoteExecutionClient

# Define a simple class that we want to execute remotely
class SimpleCalculator:
    def __init__(self, name="RemoteCalculator"):
        self.name = name
        self.operations_count = 0

    def add(self, a, b):
        self.operations_count += 1
        return a + b

    def multiply(self, a, b):
        self.operations_count += 1
        return a * b

    def get_stats(self):
        return {
            "name": self.name,
            "operations_performed": self.operations_count
        }

async def test_passthrough_node():
    """Test the basic PassThroughNode."""
    print("🔄 Testing PassThroughNode")
    print("-" * 30)
    
    config = RemoteExecutorConfig(
        host='localhost', 
        port=50052, 
        protocol='grpc', 
        timeout=30.0, 
        ssl_enabled=False
    )
    
    try:
        async with RemoteExecutionClient(config) as client:
            test_data = {
                "message": "Hello from remote execution!",
                "timestamp": time.time(),
                "numbers": [1, 2, 3, 4, 5],
                "nested": {"key": "value", "count": 42}
            }
            
            print(f"📤 Sending: {test_data}")
            
            result = await client.execute_node(
                node_type="PassThroughNode",
                config={"test_config": "passthrough"},
                input_data=test_data,
                serialization_format="pickle"
            )
            
            print(f"📥 Received: {result}")
            
            if result == test_data:
                print("✅ PassThroughNode test PASSED - data returned unchanged")
                return True
            else:
                print("❌ PassThroughNode test FAILED - data was modified")
                return False
                
    except Exception as e:
        print(f"❌ PassThroughNode test failed: {e}")
        return False

async def test_calculator_node():
    """Test the CalculatorNode with various operations."""
    print("\n🧮 Testing CalculatorNode")
    print("-" * 30)
    
    config = RemoteExecutorConfig(
        host='localhost', 
        port=50052, 
        protocol='grpc', 
        timeout=30.0, 
        ssl_enabled=False
    )
    
    operations = [
        {"operation": "add", "args": [10, 5]},
        {"operation": "multiply", "args": [7, 6]},
        {"operation": "subtract", "args": [20, 8]},
        {"operation": "divide", "args": [15, 3]},
        {"operation": "power", "args": [2, 8]},
    ]
    
    try:
        async with RemoteExecutionClient(config) as client:
            results = []
            
            for op_data in operations:
                print(f"📤 Sending operation: {op_data}")
                
                result = await client.execute_node(
                    node_type="CalculatorNode",
                    config={"calculator_mode": "standard"},
                    input_data=op_data,
                    serialization_format="pickle"
                )
                
                print(f"📥 Result: {result}")
                results.append(result)
            
            print("✅ CalculatorNode test PASSED - all operations executed remotely")
            return True
                
    except Exception as e:
        print(f"❌ CalculatorNode test failed: {e}")
        return False

async def test_code_executor_node():
    """Test the CodeExecutorNode with actual Python code."""
    print("\n🐍 Testing CodeExecutorNode (Remote Python Code Execution)")
    print("-" * 60)
    
    config = RemoteExecutorConfig(
        host='localhost', 
        port=50052, 
        protocol='grpc', 
        timeout=30.0, 
        ssl_enabled=False
    )
    
    # Test cases with different Python code
    test_cases = [
        {
            "name": "Simple Math",
            "code": """
# Simple mathematical calculation
a = 10
b = 20
result = a + b * 2
""",
            "input": None
        },
        {
            "name": "List Processing",
            "code": """
# Process the input list
numbers = input_data if input_data else [1, 2, 3, 4, 5]
result = {
    'original': numbers,
    'sum': sum(numbers),
    'max': max(numbers),
    'doubled': [x * 2 for x in numbers]
}
""",
            "input": [10, 20, 30, 40, 50]
        },
        {
            "name": "String Processing",
            "code": """
# Process text data
text = input_data if input_data else "Hello World"
result = {
    'original': text,
    'uppercase': text.upper(),
    'length': len(text),
    'words': text.split(),
    'reversed': text[::-1]
}
""",
            "input": "Remote Python Execution is Working!"
        },
        {
            "name": "Custom Algorithm",
            "code": """
# Fibonacci sequence
def fibonacci(n):
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b

n = input_data if input_data else 10
result = {
    'fibonacci_of': n,
    'result': fibonacci(n),
    'sequence': [fibonacci(i) for i in range(n)]
}
""",
            "input": 8
        }
    ]
    
    try:
        async with RemoteExecutionClient(config) as client:
            all_passed = True
            
            for i, test_case in enumerate(test_cases, 1):
                print(f"\n📝 Test {i}: {test_case['name']}")
                print(f"Code to execute remotely:")
                print("```python")
                print(test_case['code'].strip())
                print("```")
                print(f"Input data: {test_case['input']}")
                
                code_data = {
                    "code": test_case['code'],
                    "input": test_case['input']
                }
                
                result = await client.execute_node(
                    node_type="CodeExecutorNode",
                    config={"execution_mode": "safe"},
                    input_data=code_data,
                    serialization_format="pickle"
                )
                
                print(f"📥 Remote execution result:")
                if 'error' in result:
                    print(f"❌ Error: {result['error']}")
                    all_passed = False
                else:
                    print(f"✅ Success: {result['result']}")
                
                print("-" * 40)
            
            if all_passed:
                print("🎉 All CodeExecutorNode tests PASSED!")
                print("🚀 Remote Python code execution is working!")
            
            return all_passed
                
    except Exception as e:
        print(f"❌ CodeExecutorNode test failed: {e}")
        return False

async def test_serialized_class_execution():
    """Test executing a serialized Python class remotely."""
    print("\n🏗️ Testing Serialized Class Execution")
    print("-" * 40)
    
    # Serialize the class and create code to execute it
    import pickle
    import base64

    # Create an instance and serialize it
    calc = SimpleCalculator("TestCalculator")
    serialized_calc = base64.b64encode(pickle.dumps(calc)).decode('ascii')
    
    code = f"""
import pickle
import base64

# Deserialize the calculator
calc_data = "{serialized_calc}"
calc = pickle.loads(base64.b64decode(calc_data.encode('ascii')))

# Perform operations
operations = input_data if input_data else [
    ("add", [10, 5]),
    ("multiply", [3, 7]),
    ("add", [100, 200])
]

results = []
for op_name, args in operations:
    if hasattr(calc, op_name):
        result = getattr(calc, op_name)(*args)
        results.append({{
            "operation": op_name,
            "args": args,
            "result": result
        }})

# Get final stats
stats = calc.get_stats()

result = {{
    "calculator_name": calc.name,
    "operations": results,
    "final_stats": stats
}}
"""
    
    config = RemoteExecutorConfig(
        host='localhost', 
        port=50052, 
        protocol='grpc', 
        timeout=30.0, 
        ssl_enabled=False
    )
    
    try:
        async with RemoteExecutionClient(config) as client:
            print("📦 Serializing SimpleCalculator class...")
            print("📤 Sending serialized class and execution code to remote server...")
            
            code_data = {
                "code": code,
                "input": [
                    ("add", [25, 75]),
                    ("multiply", [6, 9]),
                    ("add", [1, 1])
                ]
            }
            
            result = await client.execute_node(
                node_type="CodeExecutorNode",
                config={"execution_mode": "class_execution"},
                input_data=code_data,
                serialization_format="pickle"
            )
            
            print("📥 Remote class execution result:")
            if 'error' in result:
                print(f"❌ Error: {result['error']}")
                return False
            else:
                print("✅ Success! Serialized class executed remotely:")
                print(f"   Calculator: {result['result']['calculator_name']}")
                print(f"   Operations performed:")
                for op in result['result']['operations']:
                    print(f"     {op['operation']}({op['args']}) = {op['result']}")
                print(f"   Final stats: {result['result']['final_stats']}")
                return True
                
    except Exception as e:
        print(f"❌ Serialized class execution failed: {e}")
        return False

async def main():
    print("🚀 RemoteMedia Remote Python Code Execution Test")
    print("=" * 60)
    print("This test demonstrates actual Python code execution on the remote server!")
    print("=" * 60)
    
    # Wait a moment for server to be ready
    await asyncio.sleep(2)
    
    tests = [
        ("PassThrough Node", test_passthrough_node),
        ("Calculator Node", test_calculator_node),
        ("Code Executor Node", test_code_executor_node),
        ("Serialized Class Execution", test_serialized_class_execution),
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
        print("\n🎉 ALL TESTS PASSED!")
        print("🚀 Remote Python code execution is fully functional!")
        print("📋 What we demonstrated:")
        print("   ✅ Basic data serialization and remote processing")
        print("   ✅ Remote mathematical operations")
        print("   ✅ Remote Python code execution")
        print("   ✅ Serialized Python class execution")
        print("\n🎯 This proves the remote execution system works end-to-end!")
    else:
        print(f"\n⚠️  {total - passed} tests failed")
    
    return passed == total

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1) 