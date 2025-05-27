"""
Code Executor node for executing Python code.

WARNING: This node executes arbitrary Python code and is INSECURE!
Only use in trusted environments with proper sandboxing.
"""

from typing import Any, Dict
import logging

from ..core.node import Node

logger = logging.getLogger(__name__)


class CodeExecutorNode(Node):
    """
    Code Executor node - executes arbitrary Python code.
    
    WARNING: This is INSECURE and should only be used in trusted environments!
    
    Expects input data in the format:
    {
        "code": "python_code_string",
        "input": optional_input_data
    }
    """
    
    def process(self, data: Any) -> Any:
        """
        Execute Python code from input data.
        
        Args:
            data: Dictionary with code and optional input
            
        Returns:
            Dictionary with execution result or error
        """
        logger.warning(f"CodeExecutorNode '{self.name}': Executing user code - THIS IS INSECURE!")
        
        if not isinstance(data, dict):
            return {
                "error": "Input must be a dictionary",
                "input": data,
                "processed_by": f"CodeExecutorNode[{self.name}]"
            }
        
        if 'code' not in data:
            return {
                "error": "Input must contain 'code' key",
                "input": data,
                "processed_by": f"CodeExecutorNode[{self.name}]"
            }
        
        code = data['code']
        input_data = data.get('input', None)
        
        try:
            result = self._execute_code(code, input_data)
            
            return {
                'executed_code': code,
                'input': input_data,
                'result': result,
                'processed_by': f'CodeExecutorNode[{self.name}]',
                'node_config': self.config
            }
            
        except Exception as e:
            logger.error(f"CodeExecutorNode '{self.name}': execution failed: {e}")
            return {
                'error': str(e),
                'code': code,
                'input': input_data,
                'processed_by': f'CodeExecutorNode[{self.name}]'
            }
    
    def _execute_code(self, code: str, input_data: Any) -> Any:
        """
        Execute Python code in a restricted environment.
        
        Args:
            code: Python code to execute
            input_data: Input data available as 'input_data' variable
            
        Returns:
            Value of 'result' variable after execution
            
        Raises:
            Exception: Any exception from code execution
        """
        # Create a restricted globals environment
        safe_globals = {
            '__builtins__': {
                # Basic types
                'len': len,
                'str': str,
                'int': int,
                'float': float,
                'bool': bool,
                'list': list,
                'dict': dict,
                'tuple': tuple,
                'set': set,
                
                # Basic functions
                'print': print,
                'range': range,
                'enumerate': enumerate,
                'zip': zip,
                'sorted': sorted,
                'reversed': reversed,
                
                # Math functions
                'sum': sum,
                'max': max,
                'min': min,
                'abs': abs,
                'round': round,
                
                # String methods
                'ord': ord,
                'chr': chr,
                
                # Type checking
                'isinstance': isinstance,
                'hasattr': hasattr,
                'getattr': getattr,
                'setattr': setattr,
            }
        }
        
        # Add safe modules if enabled in config
        if self.config.get('enable_safe_imports', False):
            safe_globals.update(self._get_safe_modules())
        
        # Execute the code
        local_vars = {'input_data': input_data}
        exec(code, safe_globals, local_vars)
        
        # Return the result
        return local_vars.get('result', 'No result variable set')
    
    def _get_safe_modules(self) -> Dict[str, Any]:
        """Get safe modules that can be imported."""
        safe_modules = {}
        
        # Math module
        try:
            import math
            safe_modules['math'] = math
        except ImportError:
            pass
        
        # JSON module
        try:
            import json
            safe_modules['json'] = json
        except ImportError:
            pass
        
        # Base64 module (for serialization)
        try:
            import base64
            safe_modules['base64'] = base64
        except ImportError:
            pass
        
        # Pickle module (for serialization) - DANGEROUS but needed for some tests
        if self.config.get('enable_pickle', False):
            try:
                import pickle
                safe_modules['pickle'] = pickle
            except ImportError:
                pass
        
        # Cloudpickle module (for advanced serialization) - needed for Phase 3
        if self.config.get('enable_cloudpickle', False):
            try:
                import cloudpickle
                safe_modules['cloudpickle'] = cloudpickle
            except ImportError:
                pass
        
        return safe_modules
    
    def get_security_info(self) -> Dict[str, Any]:
        """Get information about security settings."""
        return {
            "security_level": "MINIMAL - INSECURE",
            "safe_imports_enabled": self.config.get('enable_safe_imports', False),
            "pickle_enabled": self.config.get('enable_pickle', False),
            "cloudpickle_enabled": self.config.get('enable_cloudpickle', False),
            "warning": "This node executes arbitrary code and is NOT SECURE!"
        }


__all__ = ["CodeExecutorNode"] 