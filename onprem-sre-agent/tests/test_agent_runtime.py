from __future__ import annotations

import pytest

from libs.agent_runtime.budgets import LLMBudget
from libs.agent_runtime.redaction import redact_for_logging
from libs.agent_runtime.settings import AgentRuntimeSettings


def test_llm_budget_enforces_max_calls() -> None:
    b = LLMBudget(max_calls=1, max_tokens=1000)
    b.record_call(10)
    with pytest.raises(RuntimeError, match="budget"):
        b.record_call(10)


def test_redact_for_logging_masks_bearer() -> None:
    s = "Authorization: Bearer secret_token_value_here"
    out = redact_for_logging(s)
    assert "secret_token" not in out
    assert "[REDACTED]" in out


def test_settings_defaults(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Avoid picking up repo `.env` (developers often set AGENTIC_ENABLED=true there).
    monkeypatch.chdir(tmp_path)
    s = AgentRuntimeSettings()
    assert s.agentic_enabled is False
    assert s.agentic_stub_fallback is True
