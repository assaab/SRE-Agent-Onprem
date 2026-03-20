"""Verify agents invoke the LLM client when AGENTIC_ENABLED=true (no network)."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from agents.triage.agent import TriageAgent
from agents.triage.schemas import TriageLLMOutput
from libs.agent_runtime.llm import clear_llm_client_cache
from libs.agent_runtime.settings import clear_agent_runtime_settings_cache
from libs.contracts.models import IncidentEnvelope, IncidentRecord


@pytest.mark.asyncio
async def test_triage_calls_llm_when_agentic_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_agent_runtime_settings_cache()
    clear_llm_client_cache()
    monkeypatch.setenv("AGENTIC_ENABLED", "true")
    monkeypatch.setenv("LLM_API_KEY", "test-key-not-used-network")
    clear_agent_runtime_settings_cache()
    clear_llm_client_cache()

    llm_out = TriageLLMOutput(
        incident_type="performance",
        priority="p1",
        probable_domains=["compute"],
        next_required_evidence=["metrics"],
    )
    mock_client = AsyncMock()
    mock_client.complete_json = AsyncMock(return_value=llm_out)

    envelope = IncidentEnvelope(
        source="test",
        severity="critical",
        service="svc",
        resource="r1",
        symptom="cpu high",
        occurred_at=datetime.utcnow(),
        dedupe_key="d1",
    )
    incident = IncidentRecord(incident_id="inc-1", metadata=envelope)

    with patch("agents.triage.agent.get_llm_client", return_value=mock_client):
        agent = TriageAgent()
        result = await agent.run(incident)

    mock_client.complete_json.assert_awaited_once()
    assert result["incident_type"] == "performance"
    assert result["priority"] == "p1"


@pytest.mark.asyncio
async def test_triage_stub_when_agentic_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_agent_runtime_settings_cache()
    clear_llm_client_cache()
    monkeypatch.setenv("AGENTIC_ENABLED", "false")
    clear_agent_runtime_settings_cache()
    clear_llm_client_cache()

    mock_client = AsyncMock()
    envelope = IncidentEnvelope(
        source="test",
        severity="critical",
        service="svc",
        resource="r1",
        symptom="cpu spike",
        occurred_at=datetime.utcnow(),
        dedupe_key="d2",
    )
    incident = IncidentRecord(incident_id="inc-2", metadata=envelope)

    with patch("agents.triage.agent.get_llm_client", return_value=mock_client):
        agent = TriageAgent()
        result = await agent.run(incident)

    mock_client.complete_json.assert_not_called()
    assert result["incident_type"] == "performance"
