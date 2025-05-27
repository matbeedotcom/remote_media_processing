# Utility functions for the custom math library
import math

def helper_function(value):
    """A helper function that enhances values."""
    if isinstance(value, (int, float)):
        # Apply some enhancement (multiply by golden ratio and round)
        golden_ratio = (1 + math.sqrt(5)) / 2
        return round(value * golden_ratio, 4)
    return value

def format_result(result):
    """Format a result for display."""
    if isinstance(result, dict):
        return {k: round(v, 4) if isinstance(v, float) else v for k, v in result.items()}
    elif isinstance(result, (int, float)):
        return round(result, 4)
    return result