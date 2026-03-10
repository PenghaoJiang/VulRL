"""Logging utilities for Worker Router."""

import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def setup_logger(log_dir: str, log_file: str, level: str = "INFO") -> logging.Logger:
    """Setup file logger with custom format.
    
    Args:
        log_dir: Directory for log files
        log_file: Log file name
        level: Logging level
        
    Returns:
        Configured logger
    """
    # Create log directory
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    # Create logger
    logger = logging.getLogger("worker_router")
    logger.setLevel(getattr(logging, level.upper()))
    
    # File handler
    file_handler = logging.FileHandler(log_path / log_file)
    file_handler.setLevel(getattr(logging, level.upper()))
    
    # Simple formatter (we'll use custom format in log_request/log_response)
    formatter = logging.Formatter('%(message)s')
    file_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    
    # Also log to console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger


def log_request(logger: logging.Logger, entry_point: str, request_data: Any):
    """Log incoming request.
    
    Format: time <timestamp>; request entry point: <function>; request: <input>
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    
    # Convert request_data to JSON string if possible
    if hasattr(request_data, 'dict'):
        request_str = json.dumps(request_data.dict())
    elif isinstance(request_data, dict):
        request_str = json.dumps(request_data)
    else:
        request_str = str(request_data)
    
    log_msg = f"time {timestamp}; request entry point: {entry_point}; request: {request_str}"
    logger.info(log_msg)


def log_response(logger: logging.Logger, entry_point: str, request_data: Any, response_data: Any):
    """Log response before return.
    
    Format: time <timestamp>; request entry point: <function>; request: <input>; return: <output>
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    
    # Convert to JSON strings
    if hasattr(request_data, 'dict'):
        request_str = json.dumps(request_data.dict())
    elif isinstance(request_data, dict):
        request_str = json.dumps(request_data)
    else:
        request_str = str(request_data)
    
    if hasattr(response_data, 'dict'):
        response_str = json.dumps(response_data.dict())
    elif isinstance(response_data, dict):
        response_str = json.dumps(response_data)
    else:
        response_str = str(response_data)
    
    log_msg = f"time {timestamp}; request entry point: {entry_point}; request: {request_str}; return: {response_str}"
    logger.info(log_msg)
