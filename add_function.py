"""Simple addition utility function."""


def add(a: float | int, b: float | int) -> float | int:
    """Add two numbers and return their sum.
    
    Args:
        a: First number (int or float)
        b: Second number (int or float)
        
    Returns:
        Sum of a and b
        
    Raises:
        TypeError: If inputs are not numeric types
    """
    if not isinstance(a, (int, float)) or isinstance(a, bool):
        raise TypeError(f"First argument must be int or float, got {type(a).__name__}")
    if not isinstance(b, (int, float)) or isinstance(b, bool):
        raise TypeError(f"Second argument must be int or float, got {type(b).__name__}")
    
    return a + b
