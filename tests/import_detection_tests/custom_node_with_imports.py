# Custom node that imports from local library
from custom_math import AdvancedCalculator, StatisticsEngine, helper_function
from custom_math.utils import format_result

class CustomNodeWithImports:
    def __init__(self):
        self.calculator = AdvancedCalculator()
        self.stats_engine = StatisticsEngine()
        self.operations_count = 0
    
    def process_data(self, operation, data):
        """Process data using custom library functions."""
        self.operations_count += 1
        
        if operation == 'complex_calc':
            x, y = data.get('x', 0), data.get('y', 0)
            result = self.calculator.complex_calculation(x, y)
            return format_result({
                'operation': 'complex_calc',
                'input': {'x': x, 'y': y},
                'result': result,
                'operations_count': self.operations_count
            })
        
        elif operation == 'matrix_op':
            matrix = data.get('matrix', [])
            result = self.calculator.matrix_operation(matrix)
            return format_result({
                'operation': 'matrix_op',
                'result': result,
                'operations_count': self.operations_count
            })
        
        elif operation == 'statistics':
            dataset = data.get('dataset', [])
            result = self.stats_engine.analyze_dataset(dataset)
            return format_result({
                'operation': 'statistics',
                'result': result,
                'operations_count': self.operations_count
            })
        
        elif operation == 'correlation':
            x_data = data.get('x_data', [])
            y_data = data.get('y_data', [])
            result = self.stats_engine.correlation(x_data, y_data)
            return format_result({
                'operation': 'correlation',
                'result': result,
                'operations_count': self.operations_count
            })
        
        else:
            return {'error': f'Unknown operation: {operation}'}
