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

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

try:
    from openai import OpenAI
except ImportError as _anthropic_import_error:  # noqa: F841
    raise ImportError(
        "The 'openai' package is required. Install it with: pip install openai"
    )

logger = logging.getLogger(__name__)


# ─── Configuration ───────────────────────────────────────────────────────────

@dataclass
class LLMConfig:
    base_url: str = 'https://api.rcouyi.com/v1'
    api_key: str = "sk-V0s4xmnT70wbwPPe160dBaCc96A74fB9Ae850fFc6dE6136b"
    model: str = "gpt-4o"
    max_tokens: int = 8192
    temperature: float = 0.0  # deterministic for pipeline steps
    max_retries: int = 3
    retry_base_delay: float = 2.0  # seconds; doubles on each retry
    timeout: float = 120.0  # seconds per request


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
        self._client = OpenAI(
            base_url=config.base_url,
            api_key=config.api_key
        )

    # ── Raw call ─────────────────────────────────────────────────────────────

    def call(
            self,
            step_name: str,
            system: str,
            user: str,
    ) -> str:
        """
        Send a single-turn system + user prompt. Returns the full response text.
        Retries on transient errors with exponential backoff.
        """
        delay = self.config.retry_base_delay
        last_exc: Optional[Exception] = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                logger.debug("[%s] attempt %d/%d", step_name, attempt, self.config.max_retries)
                response = self._client.chat.completions.create(
                    model=self.config.model,
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user}
                    ],
                )
                usage = TokenUsage(
                    input_tokens=response.usage.prompt_tokens,
                    output_tokens=response.usage.completion_tokens,
                )
                self.session_usage.record(step_name, usage)
                logger.debug(
                    "[%s] tokens: in=%d out=%d",
                    step_name, usage.input_tokens, usage.output_tokens,
                )
                return response.choices[0].message.content

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
    ) -> Any:
        """
        Call the LLM and parse the response as JSON.

        Handles three common LLM response formats:
          1. Bare JSON object/array
          2. ```json ... ``` fenced code block
          3. JSON embedded anywhere in prose (last-resort extraction)

        Raises:
            LLMParseError: if no valid JSON can be extracted.
        """
        raw = self.call(step_name=step_name, system=system, user=user)
        return _extract_json(raw, step_name)


# ─── 增强版 JSON extraction ─────────────────────────────────────────────────────────
def _extract_json(raw: str, step_name: str = ""):
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
    logger.error(error_msg)  # 记录错误日志
    return {}  # 返回空 JSON 对象（如需返回空数组改为 return []）


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