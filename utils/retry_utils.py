# utils/retry_utils.py
"""
Retry utilities for handling transient failures with exponential backoff.
Provides decorators and helper functions for implementing robust error recovery.
"""

import time
import logging
import threading
from functools import wraps
from typing import Callable, Type, Tuple, Optional

logger = logging.getLogger("OverlayTranslate")


def retry_with_backoff(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 30.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int, float], None]] = None
):
    """
    Decorator that retries a function with exponential backoff on failure.
    
    Args:
        max_attempts: Maximum number of attempts (including first try)
        initial_delay: Initial delay in seconds before first retry
        backoff_factor: Multiplier for delay after each retry
        max_delay: Maximum delay between retries in seconds
        exceptions: Tuple of exception types to catch and retry
        on_retry: Optional callback function(exception, attempt, delay) called before each retry
    
    Example:
        @retry_with_backoff(max_attempts=3, initial_delay=1.0, exceptions=(ConnectionError, TimeoutError))
        def fetch_data():
            return requests.get("https://api.example.com/data")
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    if attempt == max_attempts:
                        # Final attempt failed, re-raise the exception
                        logger.error(
                            f"{func.__name__} failed after {max_attempts} attempts: {e}",
                            exc_info=True
                        )
                        raise
                    
                    # Calculate next delay with exponential backoff
                    current_delay = min(delay, max_delay)
                    
                    logger.warning(
                        f"{func.__name__} attempt {attempt}/{max_attempts} failed: {e}. "
                        f"Retrying in {current_delay:.1f}s..."
                    )
                    
                    # Call the retry callback if provided
                    if on_retry:
                        try:
                            on_retry(e, attempt, current_delay)
                        except Exception as callback_error:
                            logger.warning(f"Retry callback error: {callback_error}")
                    
                    # Wait before retry
                    time.sleep(current_delay)
                    
                    # Increase delay for next iteration
                    delay *= backoff_factor
            
            # Should never reach here, but just in case
            if last_exception:
                raise last_exception
                
        return wrapper
    return decorator


def retry_operation(
    func: Callable,
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    error_message_prefix: str = "Operation"
) -> any:
    """
    Helper function to retry an operation without using a decorator.
    Useful for one-off retry logic or when decorators aren't practical.
    
    Args:
        func: Function to retry
        max_attempts: Maximum number of attempts
        initial_delay: Initial delay in seconds
        backoff_factor: Multiplier for delay
        exceptions: Tuple of exception types to catch
        error_message_prefix: Prefix for log messages
    
    Returns:
        Result of the function call
    
    Raises:
        The last exception if all attempts fail
    
    Example:
        result = retry_operation(
            lambda: risky_api_call(),
            max_attempts=3,
            exceptions=(ConnectionError,)
        )
    """
    delay = initial_delay
    last_exception = None
    
    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except exceptions as e:
            last_exception = e
            
            if attempt == max_attempts:
                logger.error(
                    f"{error_message_prefix} failed after {max_attempts} attempts: {e}",
                    exc_info=True
                )
                raise
            
            current_delay = min(delay, 30.0)  # Max 30s delay
            logger.warning(
                f"{error_message_prefix} attempt {attempt}/{max_attempts} failed: {e}. "
                f"Retrying in {current_delay:.1f}s..."
            )
            
            time.sleep(current_delay)
            delay *= backoff_factor
    
    if last_exception:
        raise last_exception


class CircuitBreaker:
    """
    Circuit breaker pattern implementation to prevent cascading failures.
    Tracks failures and temporarily disables operations after threshold is reached.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Failure threshold exceeded, requests fail fast
    - HALF_OPEN: Testing if service recovered, limited requests allowed
    
    Example:
        breaker = CircuitBreaker(failure_threshold=5, timeout=60)
        
        @breaker.call
        def risky_operation():
            return external_api_call()
    """
    
    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: float = 60.0,
        expected_exceptions: Tuple[Type[Exception], ...] = (Exception,)
    ):
        """
        Args:
            failure_threshold: Number of failures before opening circuit
            timeout: Seconds to wait before attempting recovery (OPEN -> HALF_OPEN)
            expected_exceptions: Exceptions that count as failures
        """
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.expected_exceptions = expected_exceptions
        
        self._lock = threading.Lock()
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func: Callable) -> Callable:
        """Decorator to wrap a function with circuit breaker logic."""
        @wraps(func)
        def wrapper(*args, **kwargs):
            with self._lock:
                if self.state == "OPEN":
                    # Check if timeout has passed
                    if time.time() - self.last_failure_time >= self.timeout:
                        logger.info(f"Circuit breaker entering HALF_OPEN state for {func.__name__}")
                        self.state = "HALF_OPEN"
                    else:
                        # Fail fast
                        raise Exception(
                            f"Circuit breaker is OPEN for {func.__name__}. "
                            f"Service unavailable, try again later."
                        )
            
            try:
                result = func(*args, **kwargs)
                
                # Success - reset if we were in HALF_OPEN
                with self._lock:
                    if self.state == "HALF_OPEN":
                        logger.info(f"Circuit breaker closing for {func.__name__} - service recovered")
                        self._reset_unlocked()
                
                return result
                
            except self.expected_exceptions as e:
                self._record_failure_locked()
                with self._lock:
                    count = self.failure_count
                logger.warning(
                    f"Circuit breaker recorded failure for {func.__name__}: {e}. "
                    f"Count: {count}/{self.failure_threshold}"
                )
                raise
        
        return wrapper
    
    def _record_failure_locked(self):
        """Record a failure and open circuit if threshold exceeded (thread-safe)."""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                logger.error(
                    f"Circuit breaker OPENED after {self.failure_count} failures. "
                    f"Will attempt recovery in {self.timeout}s"
                )
    
    def record_failure(self):
        """Record a failure and open circuit if threshold exceeded."""
        self._record_failure_locked()
    
    def _reset_unlocked(self):
        """Reset state (caller must hold self._lock)."""
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"
    
    def reset(self):
        """Reset the circuit breaker to CLOSED state."""
        with self._lock:
            self._reset_unlocked()
