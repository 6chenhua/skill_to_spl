"""
Simplified LLM client for the minimal pipeline.
"""

from __future__ import annotations
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

# Try to import OpenAI, fallback to mock for testing
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

logger = logging.getLogger(__name__)


@dataclass
class LLMConfig:
    """Configuration for LLM API calls."""
    model: str = "gpt-4o"
    max_tokens: int = 16000
    temperature: float = 0.0
    api_key: Optional[str] = "sk-V0s4xmnT70wbwPPe160dBaCc96A74fB9Ae850fFc6dE6136b"
    base_url: Optional[str] = 'https://api.rcouyi.com/v1'


@dataclass
class TokenUsage:
    """Track token usage per step."""
    input_tokens: int = 0
    output_tokens: int = 0
    
    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass  
class SessionUsage:
    """Track token usage across the entire session."""
    by_step: dict[str, TokenUsage] = field(default_factory=dict)
    
    @property
    def total(self) -> TokenUsage:
        total_in = sum(u.input_tokens for u in self.by_step.values())
        total_out = sum(u.output_tokens for u in self.by_step.values())
        return TokenUsage(total_in, total_out)


class LLMClient:
    """Client for making LLM API calls."""
    
    def __init__(self, config: LLMConfig, session_usage: Optional[SessionUsage] = None):
        self.config = config
        self.session_usage = session_usage or SessionUsage()
        self._client = None
        
        if HAS_OPENAI and config.api_key:
            # Only initialize OpenAI client if API key is provided
            client_kwargs = {"api_key": config.api_key}
            if config.base_url:
                client_kwargs["base_url"] = config.base_url
            self._client = OpenAI(**client_kwargs)
    
    def call(
        self,
        step_name: str,
        system: str,
        user: str,
    ) -> str:
        """Make a text completion call to the LLM."""
        if not HAS_OPENAI or self._client is None:
            # Mock implementation for testing
            logger.warning(f"[MOCK] {step_name}: Returning empty response")
            return f"# Mock response for {step_name}"
        
        try:
            response = self._client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ],
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
            )
            
            # Track usage
            usage = response.usage
            if usage:
                self.session_usage.by_step[step_name] = TokenUsage(
                    input_tokens=usage.prompt_tokens,
                    output_tokens=usage.completion_tokens
                )
            
            result = response.choices[0].message.content or ""
            logger.info(f"[{step_name}] LLM call completed ({len(result)} chars)")
            return result
            
        except Exception as e:
            logger.error(f"[{step_name}] LLM call failed: {e}")
            raise
    
    def call_json(
        self,
        step_name: str,
        system: str,
        user: str,
    ) -> dict[str, Any]:
        """Make a JSON completion call to the LLM."""
        # Add JSON instruction to system prompt
        json_system = system + "\n\nRespond with valid JSON only. No markdown formatting, no explanation."
        
        text = self.call(step_name, json_system, user)
        
        # Clean up markdown fences if present
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove opening fence
            if lines[0].startswith("```"):
                lines = lines[1:]
            # Remove closing fence
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)
        
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"[{step_name}] Failed to parse JSON: {e}")
            logger.error(f"Response text: {text[:500]}...")
            # Return empty dict on parse failure
            return {}
