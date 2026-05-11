"""
Centralized logging configuration with rotation, structured formatting, and severity levels.

This module provides:
- Log rotation to prevent unbounded log file growth
- Structured log formatting with contextual information
- Proper severity levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Console and file handlers with appropriate filtering
- Graceful handling of missing stdout/stderr in PyInstaller frozen apps
"""

import os
import sys
import logging
import logging.handlers
from typing import Optional

# Constants for log configuration
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MB per log file
LOG_BACKUP_COUNT = 5              # Keep 5 backup files
LOG_ENCODING = 'utf-8'
LOG_DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

# Console formatter (simpler, for user-facing output)
CONSOLE_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'

# File formatter (detailed, for debugging)
FILE_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s'


def setup_logger(
    logger_name: str,
    log_file_path: str,
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
    enable_console: bool = True,
    enable_file: bool = True
) -> logging.Logger:
    """
    Configure a logger with rotation, proper formatting, and dual output (console + file).
    
    Args:
        logger_name: Name of the logger (e.g., "OverlayTranslate")
        log_file_path: Full path to the log file
        console_level: Minimum level for console output (default: INFO)
        file_level: Minimum level for file output (default: DEBUG)
        enable_console: Whether to add console handler
        enable_file: Whether to add file handler
        
    Returns:
        Configured logger instance
        
    Example:
        >>> logger = setup_logger("MyApp", "/path/to/app.log")
        >>> logger.info("Application started")
        >>> logger.debug("Debug info") # Only in file, not console
    """
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)  # Capture everything, filter at handler level
    
    # Prevent duplicate handlers if logger is reconfigured
    if logger.handlers:
        logger.debug(f"Logger '{logger_name}' already has handlers, skipping setup")
        return logger
    
    # Console Handler
    if enable_console and _has_console():
        try:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(console_level)
            console_formatter = logging.Formatter(CONSOLE_FORMAT, datefmt=LOG_DATE_FORMAT)
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)
            logger.debug(f"Console handler added to logger '{logger_name}' (level: {logging.getLevelName(console_level)})")
        except Exception as e:
            # Fallback: print to stderr if stdout handler fails
            print(f"WARNING: Could not set up console logging for '{logger_name}': {e}", file=sys.stderr)
    
    # File Handler with Rotation
    if enable_file:
        try:
            # Ensure log directory exists
            log_dir = os.path.dirname(log_file_path)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
            
            file_handler = logging.handlers.RotatingFileHandler(
                log_file_path,
                maxBytes=LOG_MAX_BYTES,
                backupCount=LOG_BACKUP_COUNT,
                encoding=LOG_ENCODING
            )
            file_handler.setLevel(file_level)
            file_formatter = logging.Formatter(FILE_FORMAT, datefmt=LOG_DATE_FORMAT)
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
            logger.debug(f"File handler added to logger '{logger_name}' at '{log_file_path}' (level: {logging.getLevelName(file_level)})")
        except Exception as e:
            # Critical failure: can't write to log file
            print(f"CRITICAL: Error setting up file logging to '{log_file_path}': {e}", file=sys.stderr)
    
    return logger


def _has_console() -> bool:
    """
    Check if console (stdout) is available.
    
    In PyInstaller frozen apps without console window, sys.stdout may be None.
    """
    return sys.stdout is not None


def add_rotating_file_handler(
    logger: logging.Logger,
    log_file_path: str,
    level: int = logging.DEBUG,
    max_bytes: int = LOG_MAX_BYTES,
    backup_count: int = LOG_BACKUP_COUNT
) -> Optional[logging.handlers.RotatingFileHandler]:
    """
    Add a rotating file handler to an existing logger.
    
    Useful for adding additional log files (e.g., separate error log).
    
    Args:
        logger: Logger instance to add handler to
        log_file_path: Full path to the log file
        level: Minimum logging level for this handler
        max_bytes: Maximum size per log file
        backup_count: Number of backup files to keep
        
    Returns:
        The created handler, or None if creation failed
    """
    try:
        log_dir = os.path.dirname(log_file_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        
        handler = logging.handlers.RotatingFileHandler(
            log_file_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding=LOG_ENCODING
        )
        handler.setLevel(level)
        formatter = logging.Formatter(FILE_FORMAT, datefmt=LOG_DATE_FORMAT)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.debug(f"Added rotating file handler to '{log_file_path}' (level: {logging.getLevelName(level)})")
        return handler
    except Exception as e:
        logger.error(f"Failed to add rotating file handler to '{log_file_path}': {e}", exc_info=True)
        return None


def shutdown_logging():
    """
    Gracefully shutdown logging system, flushing all buffers and closing handlers.
    
    Should be called during application shutdown to ensure all logs are written.
    """
    try:
        logging.shutdown()
    except Exception as e:
        # Last resort: print to stderr if logging system is broken
        print(f"Error during logging shutdown: {e}", file=sys.stderr)


def set_logger_level(logger_name: str, level: int):
    """
    Change the logging level of a specific logger at runtime.
    
    Args:
        logger_name: Name of the logger to modify
        level: New logging level (logging.DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    logger = logging.getLogger(logger_name)
    old_level = logger.level
    logger.setLevel(level)
    logger.info(f"Logger '{logger_name}' level changed from {logging.getLevelName(old_level)} to {logging.getLevelName(level)}")


def get_logger(name: str = "OverlayTranslate") -> logging.Logger:
    """
    Get a logger instance with the given name.
    
    This is a convenience function for accessing pre-configured loggers.
    
    Args:
        name: Logger name (default: "OverlayTranslate")
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)
