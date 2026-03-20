from __future__ import annotations

from uuid import uuid4

import httpx

from adapters.actions.change_feed import get_change_feed_client
from agents.change_correlation.prompts import CHANGE_CORRELATION_SYSTEM
from agents.change_correlation.schemas import ChangeCorrelationLLMOutput
from libs.agent_runtime.llm import StructuredLLMError, get_llm_client
from libs.agent_runtime.settings import get_agent_runtime_settings
from libs.agent_runtime.tracing import agent_span
from libs.contracts.models import EvidenceEntry, IncidentRecord
from libs.observability.logging import get_logger

_logger = get_logger("change-correlation-agent")


class ChangeCorrelationAgent:
    async def run(self, incident: IncidentRecord) -> EvidenceEntry:
        with agent_span("change_correlation"):
            client = get_change_feed_client()
            raw_deployments = await client.get_recent_deployments(incident.metadata.service)
            settings = get_agent_runtime_settings()
            if not settings.agentic_enabled:
                return self._stub_entry(raw_deployments)
            try:
                llm = get_llm_client()
                user = self._format_user(incident, raw_deployments)
                out = await llm.complete_json(
                    system=CHANGE_CORRELATION_SYSTEM,
                    user=user,
                    response_model=ChangeCorrelationLLMOutput,
                    agent_name="change_correlation",
                )
                return EvidenceEntry(
                    evidence_id=f"ev_{uuid4().hex[:10]}",
                    source="change-correlation",
                    kind=out.kind,
                    confidence=out.confidence,
                    summary=out.summary,
                )
            except (StructuredLLMError, OSError, httpx.HTTPError, httpx.RequestError) as exc:
                if not settings.agentic_stub_fallback:
                    raise
                _logger.warning("change_correlation_llm_fallback", error=str(exc))
                return self._stub_entry(raw_deployments)

    def _stub_entry(self, raw_deployments: str) -> EvidenceEntry:
        return EvidenceEntry(
            evidence_id=f"ev_{uuid4().hex[:10]}",
            source="change-correlation",
            kind="deployment-history",
            confidence=0.66,
            summary=raw_deployments,
        )

    def _format_user(self, incident: IncidentRecord, raw_deployments: str) -> str:
        m = incident.metadata
        return (
            f"incident_id={incident.incident_id}\n"
            f"symptom={m.symptom}\n"
            f"service={m.service}\n"
            f"resource={m.resource}\n"
            f"deployment_text={raw_deployments}\n"
        )
