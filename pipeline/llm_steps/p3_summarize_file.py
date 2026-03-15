from __future__ import annotations

import dataclasses
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

from pipeline.llm_client import LLMClient, LLMParseError
from prompts import templates

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# P3 — LLM summarize_fn factory
# ─────────────────────────────────────────────────────────────────────────────

_P3_SUMMARIZE_SYSTEM = """\
You are a technical documentation summarizer.
Given the content of a file from a software skill package, write a concise
summary of 2-3 sentences that captures:
  - what this file does / what it contains
  - what inputs it expects and what it produces (if applicable)
  - any important constraints or notes

Output only the summary sentences. No headers, no lists, no markdown.
"""

def make_p3_summarize_fn(client: LLMClient):
    """
    Return a summarize_fn(rel_path, content) -> str for use in P3.

    Called only when a priority-2 file has empty head_lines.
    Produces a 2-3 sentence LLM summary from up to 4000 chars of file content.
    """
    def summarize(rel_path: str, content: str) -> str:
        user = f"File: {rel_path}\n\n{content}"
        return client.call(
            step_name=f"p3_summarize_{Path(rel_path).name}",
            system=_P3_SUMMARIZE_SYSTEM,
            user=user,
        )
    return summarize