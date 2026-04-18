"""
LLM client abstraction.

Wraps the Anthropic API with:
- Retry logic with exponential backoff
- JSON extraction from responses
- Token usage tracking
- Structured error types

All pipeline LLM calls go through this module. Swap the underlying client here
without touching pipeline code.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from pipeline.exceptions import (
    ConfigurationError,
    suppress_exceptions,
    get_required_env,
    get_optional_env,
    # Structured LLM exceptions
    LLMError,
    LLMParseError,
    LLMRateLimitError,
    LLMServerError,
    LLMClientError,
    LLMConnectionError,
    LLMRetryExhausted,
    RetryPolicy,
)

try:
    from openai import AsyncOpenAI, OpenAI
    import httpx
except ImportError as _anthropic_import_error: # noqa: F841
    raise ImportError(
        "The 'openai' package is required. Install it with: pip install openai"
    )

logger = logging.getLogger(__name__)


# ─── Configuration ───────────────────────────────────────────────────────────

@dataclass
class ConnectionPoolConfig:
    """HTTP connection pool configuration.

    Configures httpx connection pool limits and timeouts for optimal
    concurrent performance with LLM API calls.

    Environment variable overrides:
    - LLM_POOL_MAX_CONNECTIONS: max_connections
    - LLM_POOL_MAX_KEEPALIVE: max_keepalive_connections
    - LLM_POOL_CONNECT_TIMEOUT: connect_timeout
    - LLM_POOL_READ_TIMEOUT: read_timeout
    - LLM_POOL_WRITE_TIMEOUT: write_timeout
    - LLM_POOL_POOL_TIMEOUT: pool_timeout
    - LLM_POOL_KEEPALIVE_EXPIRY: keepalive_expiry
    - LLM_POOL_HTTP2: http2 (set to "true" or "1" to enable)
    """

    # Pool limits
    max_connections: int = 100
    max_keepalive_connections: int = 20

    # Timeouts
    connect_timeout: float = 5.0
    read_timeout: float = 120.0
    write_timeout: float = 10.0
    pool_timeout: float = 5.0

    # Keepalive
    keepalive_expiry: float = 30.0

    # HTTP/2
    http2: bool = False

    def __post_init__(self):
        """Apply environment variable overrides."""

        def _env_int(name: str, default: int) -> int:
            val = os.getenv(name)
            return int(val) if val is not None else default

        def _env_float(name: str, default: float) -> float:
            val = os.getenv(name)
            return float(val) if val is not None else default

        def _env_bool(name: str, default: bool) -> bool:
            val = os.getenv(name, "").lower()
            return val in ("true", "1", "yes") if val else default

        self.max_connections = _env_int("LLM_POOL_MAX_CONNECTIONS", self.max_connections)
        self.max_keepalive_connections = _env_int("LLM_POOL_MAX_KEEPALIVE", self.max_keepalive_connections)
        self.connect_timeout = _env_float("LLM_POOL_CONNECT_TIMEOUT", self.connect_timeout)
        self.read_timeout = _env_float("LLM_POOL_READ_TIMEOUT", self.read_timeout)
        self.write_timeout = _env_float("LLM_POOL_WRITE_TIMEOUT", self.write_timeout)
        self.pool_timeout = _env_float("LLM_POOL_POOL_TIMEOUT", self.pool_timeout)
        self.keepalive_expiry = _env_float("LLM_POOL_KEEPALIVE_EXPIRY", self.keepalive_expiry)
        self.http2 = _env_bool("LLM_POOL_HTTP2", self.http2)


@dataclass
class LLMConfig:
    """LLM配置类 - 从环境变量读取敏感信息。

    Required environment variables:
    LLM_API_KEY: API密钥（必填）

    Optional environment variables:
    LLM_BASE_URL: API基础URL（默认: https://api.rcouyi.com/v1）
    LLM_MODEL: 默认模型（默认: gpt-4o）
    """
    # 必填配置（通过__post_init__从环境变量读取）
    api_key: str = field(default="")
    base_url: str = field(default="")

    # 默认配置
    model: str = "gpt-4o"
    max_tokens: int = 8192
    temperature: float = 0.0  # deterministic for pipeline steps
    max_retries: int = 3
    retry_base_delay: float = 2.0  # seconds; doubles on each retry
    timeout: float = 120.0  # seconds per request
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    connection_pool: ConnectionPoolConfig = field(default_factory=ConnectionPoolConfig)

    def __post_init__(self):
        """验证和加载配置。"""
        # API密钥：优先使用传入值，否则从环境变量读取
        if not self.api_key:
            try:
                self.api_key = get_required_env("LLM_API_KEY")
            except ConfigurationError as e:
                # 提供更有帮助的错误信息
                raise ConfigurationError(
                    f"{e}\n\n"
                    "To fix this:\n"
                    "1. Copy .env.example to .env\n"
                    "2. Fill in your actual API key in .env\n"
                    "3. Or set LLM_API_KEY environment variable"
                ) from e
        
        # Base URL：优先使用传入值，否则从环境变量读取，最后使用默认值
        if not self.base_url:
            self.base_url = get_optional_env(
                "LLM_BASE_URL", 
                "https://api.rcouyi.com/v1"
            )
        
        # 验证URL格式
        if not self.base_url.startswith(("http://", "https://")):
            raise ConfigurationError(
                f"Invalid LLM_BASE_URL: {self.base_url}. "
                "Must start with http:// or https://"
            )


@dataclass
class StepLLMConfig:
    """Configuration for per-step LLM model overrides.

    Allows different pipeline steps to use different models.
    If a step is not specified, falls back to the default model.
    """
    step_models: dict[str, str] = field(default_factory=dict)

    def get_model(self, step_name: str, default: str) -> str:
        """Get the model for a step, or the default if not configured."""
        return self.step_models.get(step_name, default)


# ─── Usage tracking ──────────────────────────────────────────────────────────

@dataclass
class TokenUsage:
    input_tokens: int = 0
    output_tokens: int = 0

    def add(self, other: "TokenUsage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass
class SessionUsage:
    """Accumulates token usage across all LLM calls in a pipeline run."""
    by_step: dict[str, TokenUsage] = field(default_factory=dict)

    def record(self, step_name: str, usage: TokenUsage) -> None:
        if step_name not in self.by_step:
            self.by_step[step_name] = TokenUsage()
        self.by_step[step_name].add(usage)

    @property
    def total(self) -> TokenUsage:
        t = TokenUsage()
        for u in self.by_step.values():
            t.add(u)
        return t


@dataclass
class ResourceMetrics:
    """Track resource usage for leak detection."""
    client_created_at: float = field(default_factory=time.time)
    total_calls: int = 0
    active_calls: int = 0
    connections_opened: int = 0
    connections_closed: int = 0

    @property
    def connections_in_flight(self) -> int:
        return self.connections_opened - self.connections_closed

    def record_call_start(self) -> None:
        self.total_calls += 1
        self.active_calls += 1

    def record_call_end(self) -> None:
        self.active_calls -= 1


# ─── Errors ──────────────────────────────────────────────────────────────────
# NOTE: Exception classes are imported from pipeline.exceptions
# These aliases maintain backward compatibility for existing code

# Backward compatibility aliases
LLMError = LLMError
LLMParseError = LLMParseError
LLMRetryExhausted = LLMRetryExhausted


# ─── Client ──────────────────────────────────────────────────────────────────

class LLMClient:
    """
    Thin wrapper around the Anthropic client for pipeline use.

    Usage:
        client = LLMClient()
        response = client.call(step_name="p2", system=SYSTEM, user=USER)
        data = client.call_json(step_name="step1", system=SYSTEM, user=USER)
    """

    def __init__(
        self,
        config: Optional[LLMConfig] = None,
        session_usage: Optional[SessionUsage] = None,
    ):
        self.config = config or LLMConfig()
        self.session_usage = session_usage or SessionUsage()
        self._closed = False  # Track if already closed
        self._metrics = ResourceMetrics()
        self._lock = threading.Lock()

        # Create configured httpx clients with connection pool settings
        pool_config = self.config.connection_pool

        # Configure connection pool limits
        limits = httpx.Limits(
            max_connections=pool_config.max_connections,
            max_keepalive_connections=pool_config.max_keepalive_connections,
            keepalive_expiry=pool_config.keepalive_expiry,
        )

        # Configure timeouts
        timeout = httpx.Timeout(
            connect=pool_config.connect_timeout,
            read=pool_config.read_timeout,
            write=pool_config.write_timeout,
            pool=pool_config.pool_timeout,
        )

        # Create sync httpx client with connection pool configuration
        self._http_client = httpx.Client(
            limits=limits,
            timeout=timeout,
            http2=pool_config.http2,
            proxy=None,  # Keep proxy disabled to avoid SSL issues
        )
        self._metrics.connections_opened += 1
        self._client = OpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            http_client=self._http_client
        )

        # Create async httpx client with same connection pool configuration
        self._async_http_client = httpx.AsyncClient(
            limits=limits,
            timeout=timeout,
            http2=pool_config.http2,
            proxy=None,  # Keep proxy disabled to avoid SSL issues
        )
        self._metrics.connections_opened += 1
        self._async_client = AsyncOpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            http_client=self._async_http_client
        )

    def _check_not_closed(self) -> None:
        """Raise error if client is already closed."""
        if self._closed:
            raise RuntimeError("LLMClient has been closed")

    def _close_async_client(self, timeout: float) -> None:
        """Close async HTTP client with timeout handling."""
        try:
            import asyncio
            # Try to get a running loop
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    # We're inside an async context, schedule cleanup
                    loop.call_soon_threadsafe(
                        lambda: asyncio.create_task(self._async_http_client.aclose())
                    )
                else:
                    # Loop exists but not running, run the close coroutine
                    loop.run_until_complete(self._async_http_client.aclose())
            except RuntimeError:
                # No running loop, need to create one
                try:
                    asyncio.run(self._async_http_client.aclose())
                except RuntimeError:
                    # Event loop is closed, log and continue
                    logger.debug("Event loop already closed, skipping async client cleanup")
        except Exception as e:
            logger.warning("Error closing async HTTP client: %s", e)

    @suppress_exceptions
    def close(self, timeout: float = 30.0) -> None:
        """Close HTTP clients gracefully.

        Args:
            timeout: Maximum time to wait for async client cleanup (seconds).

        This method is idempotent - calling it multiple times is safe.
        """
        with self._lock:
            if self._closed:
                return
            self._closed = True

        logger.debug("Closing LLMClient...")

        # Close sync client
        try:
            self._http_client.close()
            self._metrics.connections_closed += 1
            logger.debug("Sync HTTP client closed")
        except Exception as e:
            logger.warning("Error closing sync HTTP client: %s", e)

        # Close async client
        self._close_async_client(timeout)

        logger.debug(
            "LLMClient closed. Total calls: %d, Active calls: %d",
            self._metrics.total_calls,
            self._metrics.active_calls
        )

    @suppress_exceptions
    def __del__(self) -> None:
        """Cleanup on garbage collection - suppress all errors on Windows."""
        self.close()

    # ── Context manager support ───────────────────────────────────────────────

    def __enter__(self) -> "LLMClient":
        """Context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any]
    ) -> bool:
        """Context manager exit - ensures cleanup."""
        self.close()
        return False

    async def __aenter__(self) -> "LLMClient":
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any]
    ) -> bool:
        """Async context manager exit."""
        self.close()
        return False

    # ── Core helper methods (shared between sync/async) ─────────────────────

    def _create_messages(self, system: str, user: str) -> Any:
        """Create message list - pure logic, no IO."""
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ]

    def _should_retry(self, exc: Exception) -> tuple[bool, float]:
        """
        Determine if the exception should trigger a retry.
        Returns (should_retry, new_delay_multiplier).

        Maps OpenAI exceptions to appropriate retry behavior:
        - RateLimitError: retry with exponential backoff
        - APIStatusError (5xx): retry (server errors)
        - APIStatusError (4xx): don't retry (client errors)
        - APIConnectionError: retry (network issues)
        """
        import openai
        if isinstance(exc, openai.RateLimitError):
            return True, 2.0
        elif isinstance(exc, openai.APIStatusError) and exc.status_code >= 500:
            return True, 2.0
        elif isinstance(exc, openai.APIStatusError):
            return False, 0.0  # 4xx errors are not retried
        elif isinstance(exc, openai.APIConnectionError):
            return True, 2.0
        return False, 0.0

    def _wrap_exception(
        self,
        exc: Exception,
        step_name: str,
        model: str,
        attempt: int,
        max_retries: int,
    ) -> Exception:
        """Wrap OpenAI exceptions into structured LLMError types.

        Args:
            exc: The original exception from OpenAI
            step_name: Name of the pipeline step
            model: Model being used
            attempt: Current attempt number
            max_retries: Maximum retry attempts

        Returns:
            Structured LLMError subclass instance
        """
        import openai

        if isinstance(exc, openai.RateLimitError):
            # Extract retry_after if available from response headers
            retry_after: Optional[float] = None
            try:
                # RateLimitError may have response.headers
                if hasattr(exc, 'response') and exc.response is not None:
                    headers = getattr(exc.response, 'headers', None)
                    if headers:
                        retry_after_header = headers.get('retry-after')
                        if retry_after_header:
                            retry_after = float(retry_after_header)
            except (ValueError, TypeError, AttributeError):
                pass
            return LLMRateLimitError(
                str(exc),
                step_name=step_name,
                model=model,
                attempt=attempt,
                max_retries=max_retries,
                cause=exc,
                retry_after=retry_after,
            )
        elif isinstance(exc, openai.APIStatusError):
            if exc.status_code >= 500:
                return LLMServerError(
                    str(exc),
                    step_name=step_name,
                    model=model,
                    attempt=attempt,
                    max_retries=max_retries,
                    cause=exc,
                )
            else:
                return LLMClientError(
                    str(exc),
                    step_name=step_name,
                    model=model,
                    attempt=attempt,
                    max_retries=max_retries,
                    cause=exc,
                )
        elif isinstance(exc, openai.APIConnectionError):
            return LLMConnectionError(
                str(exc),
                step_name=step_name,
                model=model,
                attempt=attempt,
                max_retries=max_retries,
                cause=exc,
            )
        else:
            # Generic LLM error for unknown exception types
            return LLMError(
                str(exc),
                step_name=step_name,
                model=model,
                attempt=attempt,
                max_retries=max_retries,
                cause=exc,
            )

    def _record_usage(self, step_name: str, usage_obj: Any) -> TokenUsage:
        """Record token usage - unified handling of None cases."""
        if usage_obj:
            usage = TokenUsage(
                input_tokens=usage_obj.prompt_tokens or 0,
                output_tokens=usage_obj.completion_tokens or 0,
            )
        else:
            usage = TokenUsage(input_tokens=0, output_tokens=0)
            logger.warning("[%s] Response usage is None", step_name)
        self.session_usage.record(step_name, usage)
        return usage

    # ── Raw call ─────────────────────────────────────────────────────────────

    def call(
        self,
        step_name: str,
        system: str,
        user: str,
        model: Optional[str] = None,
    ) -> str:
        """
        Send a single-turn system + user prompt. Returns the full response text.
        Retries on transient errors with exponential backoff.

        Args:
            step_name: Name of the pipeline step for logging/tracking.
            system: System prompt content.
            user: User prompt content.
            model: Optional model override. If None, uses config default.
        """
        self._check_not_closed()
        self._metrics.record_call_start()
        try:
            return self._call_impl(step_name, system, user, model)
        finally:
            self._metrics.record_call_end()

    def _call_impl(
        self,
        step_name: str,
        system: str,
        user: str,
        model: Optional[str] = None,
    ) -> str:
        """Internal implementation of call()."""
        effective_model = model or self.config.model
        # Use retry_policy if available, fall back to legacy config values
        retry_policy = self.config.retry_policy
        delay = retry_policy.base_delay
        last_exc: Optional[Exception] = None

        errors: list[Exception] = []
        for attempt in range(1, retry_policy.max_retries + 1):
            try:
                logger.debug("[%s] attempt %d/%d", step_name, attempt, self.config.max_retries)
                response = self._client.chat.completions.create(
                    model=effective_model,
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                    messages=self._create_messages(system, user),
                )
                usage = self._record_usage(step_name, response.usage)
                logger.debug(
                    "[%s] tokens: in=%d out=%d",
                    step_name, usage.input_tokens, usage.output_tokens,
                )
                content = response.choices[0].message.content
                return content if content is not None else ""

            except Exception as exc:
                errors.append(exc)
                should_retry, _ = self._should_retry(exc)
                if should_retry:
                    last_exc = exc
                    # Use retry_policy for delay calculation
                    delay = retry_policy.calculate_delay(attempt)
                    logger.warning("[%s] %s, retrying in %.1fs (attempt %d/%d)",
                        step_name, type(exc).__name__, delay, attempt, retry_policy.max_retries)
                    time.sleep(delay)
                else:
                    # Wrap non-retryable exceptions with structured error info
                    wrapped = self._wrap_exception(
                        exc, step_name, effective_model, attempt, retry_policy.max_retries
                    )
                    raise wrapped from exc

        # All retries exhausted - raise with full error history
        raise LLMRetryExhausted(
            f"[{step_name}] all {retry_policy.max_retries} attempts failed",
            step_name=step_name,
            model=effective_model,
            max_retries=retry_policy.max_retries,
            errors=errors,
        ) from last_exc

    # ── JSON call ────────────────────────────────────────────────────────────

    def call_json(
        self,
        step_name: str,
        system: str,
        user: str,
        model: Optional[str] = None,
    ) -> Any:
        """
        Call the LLM and parse the response as JSON.

        Handles three common LLM response formats:
        1. Bare JSON object/array
        2. ```json ... ``` fenced code block
        3. JSON embedded anywhere in prose (last-resort extraction)

        Args:
            step_name: Name of the pipeline step for logging/tracking.
            system: System prompt content.
            user: User prompt content.
            model: Optional model override. If None, uses config default.

        Raises:
            LLMParseError: if no valid JSON can be extracted.
        """
        raw = self.call(step_name=step_name, system=system, user=user, model=model)
        return self._extract_json(raw, step_name)


    # ── Async call ────────────────────────────────────────────────────────────

    async def async_call(
        self,
        step_name: str,
        system: str,
        user: str,
        model: Optional[str] = None,
    ) -> str:
        """
        Async version of call(). Send a single-turn system + user prompt.
        Returns the full response text. Retries on transient errors.

        Args:
            step_name: Name of the pipeline step for logging/tracking.
            system: System prompt content.
            user: User prompt content.
            model: Optional model override. If None, uses config default.
        """
        self._check_not_closed()
        self._metrics.record_call_start()
        try:
            return await self._async_call_impl(step_name, system, user, model)
        finally:
            self._metrics.record_call_end()

    async def _async_call_impl(
        self,
        step_name: str,
        system: str,
        user: str,
        model: Optional[str] = None,
    ) -> str:
        """Internal implementation of async_call()."""
        effective_model = model or self.config.model
        # Use retry_policy if available, fall back to legacy config values
        retry_policy = self.config.retry_policy
        delay = retry_policy.base_delay
        last_exc: Optional[Exception] = None
        errors: list[Exception] = []

        for attempt in range(1, retry_policy.max_retries + 1):
            try:
                logger.debug("[%s] async attempt %d/%d", step_name, attempt, retry_policy.max_retries)
                response = await self._async_client.chat.completions.create(
                    model=effective_model,
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                    messages=self._create_messages(system, user),
                )
                usage = self._record_usage(step_name, response.usage)
                logger.debug(
                    "[%s] async tokens: in=%d out=%d",
                    step_name, usage.input_tokens, usage.output_tokens,
                )
                content = response.choices[0].message.content
                return content if content is not None else ""

            except Exception as exc:
                errors.append(exc)
                should_retry, _ = self._should_retry(exc)
                if should_retry:
                    last_exc = exc
                    # Use retry_policy for delay calculation
                    delay = retry_policy.calculate_delay(attempt)
                    logger.warning("[%s] async %s, retrying in %.1fs (attempt %d/%d)",
                                  step_name, type(exc).__name__, delay, attempt, retry_policy.max_retries)
                    await asyncio.sleep(delay)
                else:
                    # Wrap non-retryable exceptions with structured error info
                    wrapped = self._wrap_exception(
                        exc, step_name, effective_model, attempt, retry_policy.max_retries
                    )
                    raise wrapped from exc

        raise LLMRetryExhausted(
            f"[{step_name}] async all {retry_policy.max_retries} attempts failed",
            step_name=step_name,
            model=effective_model,
            max_retries=retry_policy.max_retries,
            errors=errors,
        ) from last_exc

    async def async_call_json(
        self,
        step_name: str,
        system: str,
        user: str,
        model: Optional[str] = None,
    ) -> Any:
        """
        Async version of call_json(). Call the LLM and parse the response as JSON.

        Args:
            step_name: Name of the pipeline step for logging/tracking.
            system: System prompt content.
            user: User prompt content.
            model: Optional model override. If None, uses config default.
        """
        raw = await self.async_call(step_name=step_name, system=system, user=user, model=model)
        return self._extract_json(raw, step_name)


    def _extract_json(self, raw: str, step_name: str = ""):
        """Extract JSON from LLM response."""
        text = raw.strip()
        step_tag = f"[{step_name}]" if step_name else ""

        # 1 direct
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 2 fenced block
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.I)
        if fence:
            try:
                return json.loads(fence.group(1))
            except json.JSONDecodeError:
                pass

        # 3 bracket scan
        for candidate in _scan_json_candidates(text):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

        # ==================== 增强逻辑：失败记录日志 + 返回空 JSON ====================
        error_msg = f"{step_tag} 未提取到有效JSON结构 | 原始文本：{repr(raw)}"
        logger.error(error_msg) # 记录错误日志
        return {} # 返回空 JSON 对象（如需返回空数组改为 return [])


def _scan_json_candidates(text: str):
    stack = []
    start = None

    for i, ch in enumerate(text):
        if ch in "{[":
            if not stack:
                start = i
            stack.append(ch)

        elif ch in "}]":
            if stack:
                stack.pop()
                if not stack and start is not None:
                    yield text[start:i + 1]