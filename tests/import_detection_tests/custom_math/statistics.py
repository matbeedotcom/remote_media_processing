# Statistical operations
import math
from .utils import helper_function

class StatisticsEngine:
    def __init__(self):
        self.samples_processed = 0
    
    def analyze_dataset(self, data):
        """Analyze a dataset with statistics."""
        if not data:
            return {}
        
        self.samples_processed += len(data)
        
        mean = sum(data) / len(data)
        variance = sum((x - mean) ** 2 for x in data) / len(data)
        std_dev = math.sqrt(variance)
        
        # Use helper function for enhanced processing
        enhanced_mean = helper_function(mean)
        
        return {
            'count': len(data),
            'mean': mean,
            'variance': variance,
            'std_dev': std_dev,
            'enhanced_mean': enhanced_mean,
            'samples_processed': self.samples_processed
        }
    
    def correlation(self, x_data, y_data):
        """Calculate correlation between two datasets."""
        if len(x_data) != len(y_data) or not x_data:
            return 0
        
        n = len(x_data)
        sum_x = sum(x_data)
        sum_y = sum(y_data)
        sum_xy = sum(x * y for x, y in zip(x_data, y_data))
        sum_x2 = sum(x * x for x in x_data)
        sum_y2 = sum(y * y for y in y_data)
        
        numerator = n * sum_xy - sum_x * sum_y
        denominator = math.sqrt((n * sum_x2 - sum_x**2) * (n * sum_y2 - sum_y**2))
        
        correlation = numerator / denominator if denominator != 0 else 0
        return helper_function(correlation)