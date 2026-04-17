"""Unified exception handling module for the pipeline.

Provides consistent exception types and decorators for error handling
across the entire codebase.
"""
from __future__ import annotations

import logging
from functools import wraps
from typing import Callable, Any, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


# ═══════════════════════════════════════════════════════════════════════════════
# Base Exception Hierarchy
# ═══════════════════════════════════════════════════════════════════════════════


class PipelineError(Exception):
    """Base exception for all pipeline errors."""
    pass


class ConfigurationError(PipelineError):
    """Configuration-related errors (missing env vars, invalid config, etc.)."""
    pass


class LLMError(PipelineError):
    """LLM API call failures."""
    pass


class LLMParseError(LLMError):
    """Raised when the LLM response cannot be parsed."""
    
    def __init__(self, message: str, raw_response: str):
        super().__init__(message)
        self.raw_response = raw_response


class LLMRetryExhausted(LLMError):
    """Raised when all retry attempts are exhausted."""
    pass


class PreprocessingError(PipelineError):
    """Errors during preprocessing stages (P1-P3)."""
    pass


class ValidationError(PipelineError):
    """Validation failures."""
    pass


# ═══════════════════════════════════════════════════════════════════════════════
# Error Handling Decorators
# ═══════════════════════════════════════════════════════════════════════════════


def log_exception(
    level: int = logging.WARNING,
    reraise: bool = True,
    default_return: Any = None,
) -> Callable[[F], F]:
    """Decorator: Log exceptions with specified level.
    
    Args:
        level: Logging level (default: WARNING)
        reraise: Whether to re-raise the exception (default: True)
        default_return: Value to return if reraise=False (default: None)
    
    Example:
        @log_exception(level=logging.ERROR)
        def risky_operation():
            raise ValueError("Something went wrong")
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.log(
                    level,
                    "Exception in %s: %s",
                    func.__name__,
                    e,
                    exc_info=level <= logging.DEBUG,
                )
                if reraise:
                    raise
                return default_return
        return wrapper
    return decorator


def suppress_exceptions(func: F) -> F:
    """Decorator: Suppress all exceptions (for cleanup functions only).
    
    Use ONLY for cleanup/__del__ methods where exceptions must not propagate.
    Logs at DEBUG level.
    
    Example:
        class Resource:
            @suppress_exceptions
            def __del__(self):
                self.cleanup()
    """
    return log_exception(level=logging.DEBUG, reraise=False)(func)


def require_non_empty(
    message: str = "Value cannot be empty",
) -> Callable[[F], F]:
    """Decorator: Require function return value to be non-empty.
    
    Args:
        message: Error message if result is empty
    
    Example:
        @require_non_empty("Config must not be empty")
        def load_config() -> dict:
            return {}
    """
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            result = func(*args, **kwargs)
            if not result:
                raise ValueError(message)
            return result
        return wrapper
    return decorator


# ═══════════════════════════════════════════════════════════════════════════════
# Helper Functions
# ═══════════════════════════════════════════════════════════════════════════════


def get_required_env(key: str) -> str:
    """Get required environment variable.
    
    Args:
        key: Environment variable name
    
    Returns:
        The environment variable value
    
    Raises:
        ConfigurationError: If the variable is not set
    
    Example:
        api_key = get_required_env("LLM_API_KEY")
    """
    import os
    value = os.getenv(key)
    if not value:
        raise ConfigurationError(
            f"{key} environment variable is required. "
            f"Set it via: export {key}=your_value"
        )
    return value


def get_optional_env(key: str, default: str = "") -> str:
    """Get optional environment variable with default value.
    
    Args:
        key: Environment variable name
        default: Default value if not set
    
    Returns:
        The environment variable value or default
    
    Example:
        base_url = get_optional_env("LLM_BASE_URL", "https://default.com")
    """
    import os
    return os.getenv(key, default)
