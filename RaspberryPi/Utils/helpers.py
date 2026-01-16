"""
Helper functions for Pi Hub
"""

from datetime import datetime


def get_timestamp() -> str:
    """Get current ISO format timestamp"""
    return datetime.now().isoformat()


def log_info(service: str, message: str):
    """Log info message with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{service}] INFO: {message}")


def log_error(service: str, message: str):
    """Log error message with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{service}] ERROR: {message}")


def log_warning(service: str, message: str):
    """Log warning message with timestamp"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] [{service}] WARNING: {message}")


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp a value between min and max"""
    return max(min_val, min(max_val, value))


def map_range(value: float, in_min: float, in_max: float, out_min: float, out_max: float) -> float:
    """Map a value from one range to another"""
    return (value - in_min) * (out_max - out_min) / (in_max - in_min) + out_min
