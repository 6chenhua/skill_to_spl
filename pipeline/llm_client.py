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
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from pipeline.exceptions import (
    ConfigurationError, 
    suppress_exceptions,
    get_required_env, 
    get_optional_env,
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


# ─── Errors ──────────────────────────────────────────────────────────────────

class LLMError(Exception):
    """Base class for LLM client errors."""


class LLMParseError(LLMError):
    """Raised when the LLM response cannot be parsed as expected JSON."""

    def __init__(self, message: str, raw_response: str):
        super().__init__(message)
        self.raw_response = raw_response


class LLMRetryExhausted(LLMError):
    """Raised when all retry attempts are exhausted."""


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
        # Create httpx client that bypasses proxy to avoid SSL issues
        self._http_client = httpx.Client(proxy=None)
        self._client = OpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            http_client=self._http_client
        )
        # Create async client for parallel calls
        self._async_http_client = httpx.AsyncClient(proxy=None)
        self._async_client = AsyncOpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
            http_client=self._async_http_client
        )

    @suppress_exceptions
    def close(self) -> None:
        """Close HTTP clients to prevent Windows asyncio cleanup warnings."""
        if self._closed:
            return
        self._closed = True

        # Close sync client
        try:
            self._http_client.close()
        except Exception as e:
            logger.debug("Failed to close sync HTTP client: %s", e)

        # Close async client - must be done carefully on Windows
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
            logger.debug("Failed to close async HTTP client: %s", e)

    @suppress_exceptions
    def __del__(self) -> None:
        """Cleanup on garbage collection - suppress all errors on Windows."""
        self.close()

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
        effective_model = model or self.config.model
        delay = self.config.retry_base_delay
        last_exc: Optional[Exception] = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                logger.debug("[%s] attempt %d/%d", step_name, attempt, self.config.max_retries)
                response = self._client.chat.completions.create(
                    model=effective_model,
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user}
                    ],
                )
                # Handle None usage gracefully
                if response.usage:
                    usage = TokenUsage(
                        input_tokens=response.usage.prompt_tokens or 0,
                        output_tokens=response.usage.completion_tokens or 0,
                    )
                else:
                    usage = TokenUsage(input_tokens=0, output_tokens=0)
                    logger.warning("[%s] Response usage is None, token tracking disabled", step_name)
                self.session_usage.record(step_name, usage)
                logger.debug(
                    "[%s] tokens: in=%d out=%d",
                    step_name, usage.input_tokens, usage.output_tokens,
                )
                content = response.choices[0].message.content
                return content if content is not None else ""

            except Exception as exc:
                import openai
                if openai and isinstance(exc, openai.RateLimitError):
                    last_exc = exc
                    logger.warning("[%s] rate limit, retrying in %.1fs (attempt %d)", step_name, delay, attempt)
                    time.sleep(delay)
                    delay *= 2
                elif openai and isinstance(exc, openai.APIStatusError) and exc.status_code >= 500:
                    last_exc = exc
                    logger.warning("[%s] server error %d, retrying in %.1fs", step_name, exc.status_code, delay)
                    time.sleep(delay)
                    delay *= 2
                elif openai and isinstance(exc, openai.APIStatusError):
                    raise  # 4xx not retried
                elif openai and isinstance(exc, openai.APIConnectionError):
                    last_exc = exc
                    logger.warning("[%s] connection error, retrying in %.1fs", step_name, delay)
                    time.sleep(delay)
                    delay *= 2
                else:
                    raise

        raise LLMRetryExhausted(
            f"[{step_name}] all {self.config.max_retries} attempts failed"
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
        effective_model = model or self.config.model
        delay = self.config.retry_base_delay
        last_exc: Optional[Exception] = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                logger.debug("[%s] async attempt %d/%d", step_name, attempt, self.config.max_retries)
                response = await self._async_client.chat.completions.create(
                    model=effective_model,
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user}
                    ],
                )
                usage = TokenUsage(
                    input_tokens=response.usage.prompt_tokens if response.usage else 0,
                    output_tokens=response.usage.completion_tokens if response.usage else 0,
                )
                self.session_usage.record(step_name, usage)
                logger.debug(
                    "[%s] async tokens: in=%d out=%d",
                    step_name, usage.input_tokens, usage.output_tokens,
                )
                content = response.choices[0].message.content
                if content is None:
                    return ""
                return content

            except Exception as exc:
                import openai
                if openai and isinstance(exc, openai.RateLimitError):
                    last_exc = exc
                    logger.warning("[%s] async rate limit, retrying in %.1fs (attempt %d)", step_name, delay, attempt)
                    await asyncio.sleep(delay)
                    delay *= 2
                elif openai and isinstance(exc, openai.APIStatusError) and exc.status_code >= 500:
                    last_exc = exc
                    logger.warning("[%s] async server error %d, retrying in %.1fs", step_name, exc.status_code, delay)
                    await asyncio.sleep(delay)
                    delay *= 2
                elif openai and isinstance(exc, openai.APIStatusError):
                    raise  # 4xx not retried
                elif openai and isinstance(exc, openai.APIConnectionError):
                    last_exc = exc
                    logger.warning("[%s] async connection error, retrying in %.1fs", step_name, delay)
                    await asyncio.sleep(delay)
                    delay *= 2
                else:
                    raise

        raise LLMRetryExhausted(
            f"[{step_name}] async all {self.config.max_retries} attempts failed"
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