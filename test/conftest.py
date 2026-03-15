"""
Shared pytest fixtures for the Skill-to-SPL pipeline unit tests.

Directory layout expected:
    tests/
        conftest.py             ← this file
        fixtures/               ← real mcp-builder files (copied from repo)
            SKILL.md
            LICENSE.txt
            reference/
                evaluation.md
                mcp_best_practices.md
                node_mcp_server.md
                python_mcp_server.md
            scripts/
                connections.py
                evaluation.py
                example_evaluation.xml
                requirements.txt
        test_p1_*.py
        test_p2_*.py
        ...

Run all tests:
    pytest tests/

Run live-LLM tests (calls real API):
    LIVE_LLM=1 pytest tests/ -m live_llm
"""

import os
import json
import pathlib
import pytest

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


# ── live-LLM marker ──────────────────────────────────────────────────────────

def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "live_llm: tests that call the real LLM API (skipped unless LIVE_LLM=1)",
    )


def pytest_collection_modifyitems(config, items):
    if os.environ.get("LIVE_LLM") != "1":
        skip = pytest.mark.skip(reason="Set LIVE_LLM=1 to run live LLM tests")
        for item in items:
            if "live_llm" in item.keywords:
                item.add_marker(skip)


# ── fixture: raw file contents ────────────────────────────────────────────────

@pytest.fixture(scope="session")
def fixture_files():
    """Return dict of relative_path → file content (str) for all fixture files."""
    result = {}
    for path in FIXTURES_DIR.rglob("*"):
        if path.is_file():
            rel = str(path.relative_to(FIXTURES_DIR))
            try:
                result[rel] = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                result[rel] = path.read_bytes().decode("latin-1")
    return result


# ── LLM client stub (used by live tests) ─────────────────────────────────────

class _LLMClient:
    """Thin wrapper around the real Anthropic client for test calls."""

    def __init__(self):
        import anthropic
        self._client = anthropic.Anthropic()

    def call(self, *, system: str, user: str, model: str = "claude-sonnet-4-6") -> str:
        response = self._client.messages.create(
            model=model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text


@pytest.fixture(scope="session")
def llm_client():
    return _LLMClient()


# ── helper: load a fixture file ───────────────────────────────────────────────

def read_fixture(relative_path: str) -> str:
    return (FIXTURES_DIR / relative_path).read_text(encoding="utf-8")
