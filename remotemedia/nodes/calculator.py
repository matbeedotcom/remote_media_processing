"""
Calculator node for mathematical operations.
"""

from typing import Any, Dict
import logging

from ..core.node import Node

logger = logging.getLogger(__name__)


class CalculatorNode(Node):
    """
    Calculator node - performs mathematical operations.
    
    Expects input data in the format:
    {
        "operation": "add|multiply|subtract|divide|power|modulo",
        "args": [number1, number2, ...]
    }
    """
    
    def process(self, data: Any) -> Any:
        """
        Perform mathematical operations on input data.
        
        Args:
            data: Dictionary with operation and args
            
        Returns:
            Dictionary with operation result
        """
        logger.info(f"CalculatorNode '{self.name}': processing {data}")
        
        if not isinstance(data, dict):
            return {
                "error": "Input must be a dictionary",
                "input": data,
                "processed_by": f"CalculatorNode[{self.name}]"
            }
        
        if 'operation' not in data or 'args' not in data:
            return {
                "error": "Input must contain 'operation' and 'args' keys",
                "input": data,
                "processed_by": f"CalculatorNode[{self.name}]"
            }
        
        operation = data['operation']
        args = data['args']
        
        try:
            result = self._perform_operation(operation, args)
            
            return {
                'operation': operation,
                'args': args,
                'result': result,
                'processed_by': f'CalculatorNode[{self.name}]',
                'node_config': self.config
            }
            
        except Exception as e:
            logger.error(f"CalculatorNode '{self.name}': operation failed: {e}")
            return {
                "error": str(e),
                "operation": operation,
                "args": args,
                "processed_by": f"CalculatorNode[{self.name}]"
            }
    
    def _perform_operation(self, operation: str, args: list) -> Any:
        """
        Perform the specified mathematical operation.
        
        Args:
            operation: Operation name
            args: List of arguments
            
        Returns:
            Operation result
            
        Raises:
            ValueError: If operation is unknown or args are invalid
        """
        if len(args) < 2:
            raise ValueError(f"Operation '{operation}' requires at least 2 arguments")
        
        a, b = args[0], args[1]
        
        if operation == 'add':
            return a + b
        elif operation == 'multiply':
            return a * b
        elif operation == 'subtract':
            return a - b
        elif operation == 'divide':
            if b == 0:
                raise ValueError("Division by zero")
            return a / b
        elif operation == 'power':
            return a ** b
        elif operation == 'modulo':
            if b == 0:
                raise ValueError("Modulo by zero")
            return a % b
        else:
            raise ValueError(f"Unknown operation: {operation}")
    
    def get_supported_operations(self) -> list:
        """Get list of supported operations."""
        return ['add', 'multiply', 'subtract', 'divide', 'power', 'modulo']


__all__ = ["CalculatorNode"] 