from __future__ import annotations

import httpx

from agents.triage.prompts import TRIAGE_SYSTEM
from agents.triage.schemas import TriageLLMOutput
from libs.agent_runtime.llm import StructuredLLMError, get_llm_client
from libs.agent_runtime.settings import get_agent_runtime_settings
from libs.agent_runtime.tracing import agent_span
from libs.contracts.models import IncidentRecord
from libs.observability.logging import get_logger

_logger = get_logger("triage-agent")


class TriageAgent:
    async def run(self, incident: IncidentRecord) -> dict[str, object]:
        with agent_span("triage"):
            settings = get_agent_runtime_settings()
            if not settings.agentic_enabled:
                return self._stub_run(incident)
            try:
                client = get_llm_client()
                user = self._format_user(incident)
                out = await client.complete_json(
                    system=TRIAGE_SYSTEM,
                    user=user,
                    response_model=TriageLLMOutput,
                    agent_name="triage",
                )
                return out.model_dump()
            except (StructuredLLMError, OSError, httpx.HTTPError, httpx.RequestError) as exc:
                if not settings.agentic_stub_fallback:
                    raise
                _logger.warning("triage_llm_fallback", error=str(exc))
                return self._stub_run(incident)

    def _stub_run(self, incident: IncidentRecord) -> dict[str, object]:
        symptom = incident.metadata.symptom.lower()
        probable_domains = ["compute"] if "cpu" in symptom else ["application"]
        priority = "p1" if incident.metadata.severity in {"sev1", "sev2"} else "p2"
        return {
            "incident_type": "performance" if "cpu" in symptom else "general",
            "priority": priority,
            "probable_domains": probable_domains,
            "next_required_evidence": ["metrics", "logs", "recent_changes"],
        }

    def _format_user(self, incident: IncidentRecord) -> str:
        m = incident.metadata
        return (
            f"incident_id={incident.incident_id}\n"
            f"severity={m.severity}\n"
            f"service={m.service}\n"
            f"resource={m.resource}\n"
            f"symptom={m.symptom}\n"
            f"source={m.source}\n"
        )
