# Advanced mathematical operations
import math
from .utils import helper_function

class AdvancedCalculator:
    def __init__(self):
        self.precision = 10
        self.operations_log = []
    
    def complex_calculation(self, x, y):
        """Perform a complex calculation using helper function."""
        base_result = math.sqrt(x**2 + y**2)
        enhanced_result = helper_function(base_result)
        self.operations_log.append(f"complex_calc({x}, {y}) = {enhanced_result}")
        return enhanced_result
    
    def matrix_operation(self, matrix):
        """Perform matrix-like operations."""
        if not matrix:
            return []
        
        # Simple matrix operations
        result = []
        for row in matrix:
            row_sum = sum(row)
            row_avg = row_sum / len(row) if row else 0
            result.append({
                'original': row,
                'sum': row_sum,
                'average': row_avg,
                'enhanced': helper_function(row_sum)
            })
        
        self.operations_log.append(f"matrix_op({len(matrix)} rows)")
        return result