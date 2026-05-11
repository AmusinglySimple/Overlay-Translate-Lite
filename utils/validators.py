"""
Input validation utilities for security and data integrity.

This module provides validators for:
- API endpoints and URLs
- File paths and existence checks
- Language codes
- Numeric ranges (opacity, font size, etc.)
- Text inputs (sanitization for injection attacks)
"""

import os
import re
import logging
from typing import Optional, Tuple, List
from urllib.parse import urlparse

logger = logging.getLogger("OverlayTranslate")

# --- URL/Endpoint Validation ---

ALLOWED_URL_SCHEMES = {'http', 'https'}
ALLOWED_LOCALHOST_PATTERNS = [
    'localhost',
    '127.0.0.1',
    '::1',
    '0.0.0.0'
]

def validate_url(url: str, allow_localhost: bool = True) -> Tuple[bool, Optional[str]]:
    """
    Validate a URL/endpoint for security and format correctness.
    
    Args:
        url: URL to validate
        allow_localhost: Whether to allow localhost/127.0.0.1 addresses
        
    Returns:
        Tuple of (is_valid, error_message)
        
    Example:
        >>> valid, error = validate_url("https://api.openai.com/v1/chat")
        >>> if not valid:
        ...     print(f"Invalid URL: {error}")
    """
    if not url or not isinstance(url, str):
        return False, "URL cannot be empty"
    
    url = url.strip()
    
    try:
        parsed = urlparse(url)
        
        # Check scheme
        if parsed.scheme not in ALLOWED_URL_SCHEMES:
            return False, f"URL scheme must be http or https, got: {parsed.scheme}"
        
        # Check netloc exists
        if not parsed.netloc:
            return False, "URL must have a valid host/domain"
        
        # Check for localhost if not allowed
        if not allow_localhost:
            hostname = parsed.hostname or ""
            if any(pattern in hostname.lower() for pattern in ALLOWED_LOCALHOST_PATTERNS):
                return False, "Localhost URLs are not allowed for this endpoint"
        
        # Check for dangerous patterns
        dangerous_patterns = ['..', '<', '>', '"', "'", '\\x', '%00']
        for pattern in dangerous_patterns:
            if pattern in url:
                return False, f"URL contains potentially dangerous pattern: {pattern}"
        
        return True, None
        
    except Exception as e:
        return False, f"Invalid URL format: {str(e)}"


def sanitize_url(url: str) -> str:
    """
    Sanitize a URL by removing dangerous characters and normalizing.
    
    Args:
        url: URL to sanitize
        
    Returns:
        Sanitized URL
    """
    if not url:
        return ""
    
    # Remove control characters and common injection attempts
    url = url.strip()
    url = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', url)  # Remove control chars
    url = url.replace('<', '').replace('>', '')
    
    return url


# --- File Path Validation ---

def validate_file_path(
    file_path: str,
    must_exist: bool = False,
    allowed_extensions: Optional[List[str]] = None,
    max_path_length: int = 260
) -> Tuple[bool, Optional[str]]:
    """
    Validate a file path for security and correctness.
    
    Args:
        file_path: Path to validate
        must_exist: Whether the file must already exist
        allowed_extensions: List of allowed extensions (e.g., ['.png', '.jpg'])
        max_path_length: Maximum allowed path length (default 260 for Windows)
        
    Returns:
        Tuple of (is_valid, error_message)
        
    Example:
        >>> valid, error = validate_file_path("/path/to/image.png", 
        ...                                   must_exist=True, 
        ...                                   allowed_extensions=['.png', '.jpg'])
    """
    if not file_path or not isinstance(file_path, str):
        return False, "File path cannot be empty"
    
    file_path = file_path.strip()
    
    # Check path length
    if len(file_path) > max_path_length:
        return False, f"File path too long (max {max_path_length} characters)"
    
    # Check for path traversal attempts
    dangerous_patterns = ['../', '..\\', '%2e%2e', '%252e']
    for pattern in dangerous_patterns:
        if pattern in file_path.lower():
            return False, f"File path contains dangerous pattern: {pattern}"
    
    # Check for null bytes
    if '\x00' in file_path:
        return False, "File path contains null byte"
    
    # Validate extension if specified
    if allowed_extensions:
        _, ext = os.path.splitext(file_path)
        if ext.lower() not in [e.lower() for e in allowed_extensions]:
            return False, f"File extension must be one of: {', '.join(allowed_extensions)}"
    
    # Check existence if required
    if must_exist and not os.path.exists(file_path):
        return False, f"File does not exist: {file_path}"
    
    # Check if path is absolute (safer)
    if not os.path.isabs(file_path):
        logger.debug(f"File path is relative, converting to absolute: {file_path}")
    
    return True, None


def sanitize_file_path(file_path: str) -> str:
    """
    Sanitize a file path by removing dangerous characters.
    
    Args:
        file_path: Path to sanitize
        
    Returns:
        Sanitized path
    """
    if not file_path:
        return ""
    
    # Remove null bytes and control characters
    file_path = file_path.replace('\x00', '')
    file_path = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', file_path)
    
    # Normalize path separators
    file_path = os.path.normpath(file_path)
    
    return file_path


# --- Language Code Validation ---

# Comprehensive list of valid language codes
VALID_LANGUAGE_CODES = {
    # Common languages
    'en', 'es', 'fr', 'de', 'it', 'pt', 'ru', 'ja', 'zh', 'ko',
    'ar', 'hi', 'bn', 'pa', 'te', 'ta', 'tr', 'vi', 'th', 'nl',
    'pl', 'uk', 'ro', 'el', 'cs', 'sv', 'hu', 'fi', 'da', 'no',
    'he', 'id', 'ms', 'fil', 'fa', 'ur', 'sw', 'am', 'ne', 'si',
    # Additional codes (lowercase — validate_language_code() lowercases input)
    'auto', 'zh-cn', 'zh-tw', 'pt-br', 'pt-pt',
    # PaddleOCR specific
    'ch', 'korean', 'japan', 'chinese_cht', 'ka', 'latin', 'arabic',
    'cyrillic', 'devanagari'
}

def validate_language_code(lang_code: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a language code.
    
    Args:
        lang_code: Language code to validate (e.g., 'en', 'es', 'auto')
        
    Returns:
        Tuple of (is_valid, error_message)
        
    Example:
        >>> valid, error = validate_language_code("en")
        >>> if not valid:
        ...     print(f"Invalid language: {error}")
    """
    if not lang_code or not isinstance(lang_code, str):
        return False, "Language code cannot be empty"
    
    lang_code = lang_code.strip().lower()
    
    # Check length (language codes are typically 2-10 chars)
    if len(lang_code) < 2 or len(lang_code) > 15:
        return False, f"Language code has invalid length: {len(lang_code)}"
    
    # Check for valid characters (alphanumeric, dash, underscore only)
    if not re.match(r'^[a-z0-9_-]+$', lang_code):
        return False, f"Language code contains invalid characters: {lang_code}"
    
    # Check against known valid codes
    if lang_code not in VALID_LANGUAGE_CODES:
        logger.warning(f"Unknown language code (may still be valid): {lang_code}")
        # Don't fail - language might be valid but not in our list
    
    return True, None


# --- Numeric Range Validation ---

def validate_numeric_range(
    value: any,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
    value_name: str = "value",
    allow_none: bool = False
) -> Tuple[bool, Optional[str]]:
    """
    Validate a numeric value is within specified range.
    
    Args:
        value: Value to validate
        min_value: Minimum allowed value (inclusive)
        max_value: Maximum allowed value (inclusive)
        value_name: Name of the value for error messages
        allow_none: Whether None is acceptable
        
    Returns:
        Tuple of (is_valid, error_message)
        
    Example:
        >>> valid, error = validate_numeric_range(0.5, 0.0, 1.0, "opacity")
        >>> valid, error = validate_numeric_range(150, 8, 72, "font_size")
    """
    if value is None:
        if allow_none:
            return True, None
        return False, f"{value_name} cannot be None"
    
    # Try to convert to float
    try:
        numeric_value = float(value)
    except (ValueError, TypeError):
        return False, f"{value_name} must be a number, got: {type(value).__name__}"
    
    # Check for NaN and infinity
    if not (-float('inf') < numeric_value < float('inf')):
        return False, f"{value_name} must be a finite number"
    
    # Check min value
    if min_value is not None and numeric_value < min_value:
        return False, f"{value_name} must be >= {min_value}, got: {numeric_value}"
    
    # Check max value
    if max_value is not None and numeric_value > max_value:
        return False, f"{value_name} must be <= {max_value}, got: {numeric_value}"
    
    return True, None


def validate_opacity(opacity: any) -> Tuple[bool, Optional[str]]:
    """Validate opacity value (0.0 to 1.0)."""
    return validate_numeric_range(opacity, 0.0, 1.0, "opacity")


def validate_font_size(font_size: any) -> Tuple[bool, Optional[str]]:
    """Validate font size (8 to 200 pixels)."""
    return validate_numeric_range(font_size, 8, 200, "font_size")


def validate_port(port: any) -> Tuple[bool, Optional[str]]:
    """Validate network port number (1-65535)."""
    valid, error = validate_numeric_range(port, 1, 65535, "port")
    if not valid:
        return valid, error
    
    # Check if integer
    try:
        if int(port) != float(port):
            return False, "Port must be an integer"
    except (ValueError, TypeError):
        return False, "Port must be an integer"
    
    return True, None


# --- Text Input Sanitization ---

def sanitize_text_input(
    text: str,
    max_length: Optional[int] = None,
    allow_newlines: bool = True,
    strip_html: bool = True
) -> str:
    """
    Sanitize user text input by removing dangerous characters.
    
    Args:
        text: Text to sanitize
        max_length: Maximum allowed length (truncate if exceeded)
        allow_newlines: Whether to preserve newlines
        strip_html: Whether to strip HTML tags
        
    Returns:
        Sanitized text
        
    Example:
        >>> safe_text = sanitize_text_input("<script>alert('xss')</script>Hello")
        >>> # Returns: "Hello"
    """
    if not text:
        return ""
    
    # Remove null bytes
    text = text.replace('\x00', '')
    
    # Strip HTML tags if requested
    if strip_html:
        text = re.sub(r'<[^>]+>', '', text)
    
    # Remove other control characters (except newlines if allowed)
    if allow_newlines:
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    else:
        text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
    
    # Truncate if too long
    if max_length and len(text) > max_length:
        text = text[:max_length]
        logger.debug(f"Text truncated to {max_length} characters")
    
    return text


def validate_json_safe_string(text: str, max_length: int = 10000) -> Tuple[bool, Optional[str]]:
    """
    Validate that a string is safe for JSON serialization.
    
    Args:
        text: Text to validate
        max_length: Maximum allowed length
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(text, str):
        return False, f"Text must be a string, got: {type(text).__name__}"
    
    if len(text) > max_length:
        return False, f"Text too long (max {max_length} characters)"
    
    # Check for null bytes (not JSON safe)
    if '\x00' in text:
        return False, "Text contains null bytes"
    
    return True, None


# --- Configuration Value Validation ---

def validate_config_value(
    value: any,
    expected_type: type,
    allowed_values: Optional[List[any]] = None,
    value_name: str = "value"
) -> Tuple[bool, Optional[str]]:
    """
    Validate a configuration value against expected type and allowed values.
    
    Args:
        value: Value to validate
        expected_type: Expected Python type
        allowed_values: List of allowed values (if applicable)
        value_name: Name of the value for error messages
        
    Returns:
        Tuple of (is_valid, error_message)
        
    Example:
        >>> valid, error = validate_config_value("OpenAI", str, 
        ...                                      ["OpenAI", "Google Gemini", "Ollama"],
        ...                                      "provider")
    """
    # Check type
    if not isinstance(value, expected_type):
        return False, f"{value_name} must be {expected_type.__name__}, got: {type(value).__name__}"
    
    # Check allowed values
    if allowed_values is not None and value not in allowed_values:
        return False, f"{value_name} must be one of: {', '.join(map(str, allowed_values))}"
    
    return True, None
