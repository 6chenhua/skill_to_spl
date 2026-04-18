"""Unified exception handling module for the pipeline.

Provides consistent exception types and decorators for error handling
across the entire codebase.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Optional, TypeVar, cast

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
    """Base class for LLM client errors with structured context.

    Provides rich error context including step name, model, attempt info,
    and timestamp for debugging and retry strategies.
    """

    def __init__(
        self,
        message: str,
        *,
        step_name: Optional[str] = None,
        model: Optional[str] = None,
        attempt: Optional[int] = None,
        max_retries: Optional[int] = None,
        cause: Optional[Exception] = None,
    ):
        super().__init__(message)
        self.step_name = step_name
        self.model = model
        self.attempt = attempt
        self.max_retries = max_retries
        self.cause = cause
        self.timestamp = time.time()

    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary for logging/serialization."""
        return {
            "type": self.__class__.__name__,
            "message": str(self),
            "step_name": self.step_name,
            "model": self.model,
            "attempt": self.attempt,
            "max_retries": self.max_retries,
            "timestamp": self.timestamp,
            "cause": str(self.cause) if self.cause else None,
        }


class LLMParseError(LLMError):
    """Raised when the LLM response cannot be parsed."""

    def __init__(self, message: str, raw_response: str, **kwargs: Any):
        super().__init__(message, **kwargs)
        self.raw_response = raw_response

    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary including raw response."""
        result = super().to_dict()
        result["raw_response"] = self.raw_response
        return result


class LLMRateLimitError(LLMError):
    """Rate limit exceeded with retry-after information."""

    def __init__(
        self,
        *args: Any,
        retry_after: Optional[float] = None,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.retry_after = retry_after

    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary including retry_after."""
        result = super().to_dict()
        result["retry_after"] = self.retry_after
        return result


class LLMServerError(LLMError):
    """5xx server errors from LLM API."""
    pass


class LLMClientError(LLMError):
    """4xx client errors (not retried)."""
    pass


class LLMConnectionError(LLMError):
    """Network/connection errors when calling LLM API."""
    pass


class LLMRetryExhausted(LLMError):
    """All retry attempts exhausted with full error history."""

    def __init__(
        self,
        *args: Any,
        errors: Optional[list[Exception]] = None,
        **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)
        self.errors = errors or []

    def to_dict(self) -> dict[str, Any]:
        """Convert error to dictionary including error history."""
        result = super().to_dict()
        result["error_count"] = len(self.errors)
        serialized_errors: list[Any] = []
        for e in self.errors:
            if isinstance(e, LLMError):
                serialized_errors.append(e.to_dict())
            else:
                serialized_errors.append(str(e))
        result["errors"] = serialized_errors
        return result


@dataclass
class RetryPolicy:
    """Configurable retry policy for LLM calls.

    Provides exponential backoff with configurable parameters.
    """

    max_retries: int = 3
    base_delay: float = 2.0
    max_delay: float = 60.0
    exponential_base: float = 2.0

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for the given attempt (1-indexed).

        Args:
            attempt: The attempt number (1-indexed)

        Returns:
            Delay in seconds, capped at max_delay
        """
        delay = self.base_delay * (self.exponential_base ** (attempt - 1))
        return min(delay, self.max_delay)


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
        return cast(F, wrapper)
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
        return cast(F, wrapper)
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
