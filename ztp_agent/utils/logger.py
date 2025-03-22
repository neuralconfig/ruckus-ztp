"""
Logging utilities for ZTP Agent.
"""
import os
import logging
from typing import Dict, Any, Optional

def setup_logging(config: Dict[str, Any]) -> logging.Logger:
    """
    Set up logging configuration.
    
    Args:
        config: Configuration dictionary.
        
    Returns:
        Logger instance.
    """
    # Get logging configuration
    log_level = config.get('log_level', 'INFO').upper()
    log_file = config.get('log_file', '~/.ztp_agent.log')
    
    # Expand log file path
    log_file = os.path.expanduser(log_file)
    
    # Create log directory if it doesn't exist
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    # Set up logging
    numeric_level = getattr(logging, log_level, None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {log_level}")
    
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file)
        ]
    )
    
    # Return logger for main module
    logger = logging.getLogger('ztp_agent')
    logger.info(f"Logging initialized with level {log_level}")
    
    return logger
