from __future__ import annotations

from uuid import uuid4

import httpx

from agents.evidence.prompts import EVIDENCE_SYSTEM
from agents.evidence.schemas import EvidenceLLMOutput
from agents.triage.evidence_intents import extract_triage_dict, normalize_evidence_intents
from libs.agent_runtime.llm import StructuredLLMError, get_llm_client
from libs.agent_runtime.settings import get_agent_runtime_settings
from libs.agent_runtime.tools import (
    tool_query_logs,
    tool_query_metrics,
    tool_query_topology,
    tool_recent_deployments,
)
from libs.agent_runtime.tracing import agent_span
from libs.contracts.models import ActionType, EvidenceEntry, IncidentRecord
from libs.observability.logging import get_logger

_logger = get_logger("evidence-agent")


class EvidenceAgent:
    def _record_tool(self, incident: IncidentRecord, tool: ActionType) -> None:
        if tool not in incident.tools_used:
            incident.tools_used.append(tool)

    def _resolve_intents(self, incident: IncidentRecord) -> list[str]:
        if incident.latest_router_decision and incident.latest_router_decision.tool_plan:
            items = incident.latest_router_decision.tool_plan.items
            keys: list[str] = []
            for it in items:
                mapping = {
                    ActionType.QUERY_METRICS: "metrics",
                    ActionType.QUERY_LOGS: "logs",
                    ActionType.GET_RECENT_DEPLOYMENTS: "recent_changes",
                    ActionType.GET_TOPOLOGY: "topology",
                }
                k = mapping.get(it.tool)
                if k and k not in keys:
                    keys.append(k)
            if keys:
                return keys
        triage = extract_triage_dict(incident.hypotheses)
        raw = triage.get("next_required_evidence") if triage else None
        if isinstance(raw, list):
            return normalize_evidence_intents([str(x) for x in raw])
        return normalize_evidence_intents(None)

    async def _collect_raw(self, incident: IncidentRecord, intents: list[str]) -> dict[str, str]:
        svc, res = incident.metadata.service, incident.metadata.resource
        raw: dict[str, str] = {}
        if "metrics" in intents:
            raw["metrics"] = await tool_query_metrics(svc, res)
            self._record_tool(incident, ActionType.QUERY_METRICS)
        if "logs" in intents:
            raw["logs"] = await tool_query_logs(svc, res)
            self._record_tool(incident, ActionType.QUERY_LOGS)
        if "recent_changes" in intents:
            raw["recent_changes"] = await tool_recent_deployments(svc)
            self._record_tool(incident, ActionType.GET_RECENT_DEPLOYMENTS)
        if "topology" in intents:
            raw["topology"] = await tool_query_topology(svc, res)
            self._record_tool(incident, ActionType.GET_TOPOLOGY)
        if not raw:
            raw["metrics"] = await tool_query_metrics(svc, res)
            raw["logs"] = await tool_query_logs(svc, res)
            self._record_tool(incident, ActionType.QUERY_METRICS)
            self._record_tool(incident, ActionType.QUERY_LOGS)
        return raw

    async def run(self, incident: IncidentRecord) -> list[EvidenceEntry]:
        with agent_span("evidence"):
            settings = get_agent_runtime_settings()
            intents = self._resolve_intents(incident)
            raw = await self._collect_raw(incident, intents)

            if not settings.agentic_enabled:
                return self._from_raw_dict(raw)

            metrics = raw.get("metrics", "")
            logs = raw.get("logs", "")
            try:
                client = get_llm_client()
                user = (
                    f"service={incident.metadata.service}\n"
                    f"resource={incident.metadata.resource}\n"
                    f"intents={intents}\n"
                    f"metrics={metrics}\nlogs={logs}\n"
                    f"other={ {k: v for k, v in raw.items() if k not in ('metrics', 'logs')} }\n"
                )
                out = await client.complete_json(
                    system=EVIDENCE_SYSTEM,
                    user=user,
                    response_model=EvidenceLLMOutput,
                    agent_name="evidence",
                )
                built = [
                    EvidenceEntry(
                        evidence_id=f"ev_{uuid4().hex[:10]}",
                        source=e.source,
                        kind=e.kind,
                        confidence=e.confidence,
                        summary=e.summary,
                    )
                    for e in out.entries
                ]
                if not built:
                    if not settings.agentic_stub_fallback:
                        raise StructuredLLMError("LLM returned no evidence entries")
                    return self._from_raw_dict(raw)
                return built
            except (StructuredLLMError, OSError, httpx.HTTPError, httpx.RequestError) as exc:
                if not settings.agentic_stub_fallback:
                    raise
                _logger.warning("evidence_llm_fallback", error=str(exc))
                return self._from_raw_dict(raw)

    def _from_raw_dict(self, raw: dict[str, str]) -> list[EvidenceEntry]:
        out: list[EvidenceEntry] = []
        if "metrics" in raw:
            out.append(
                EvidenceEntry(
                    evidence_id=f"ev_{uuid4().hex[:10]}",
                    source="metrics",
                    kind="timeseries",
                    confidence=0.82,
                    summary=raw["metrics"],
                )
            )
        if "logs" in raw:
            out.append(
                EvidenceEntry(
                    evidence_id=f"ev_{uuid4().hex[:10]}",
                    source="logs",
                    kind="log-sample",
                    confidence=0.74,
                    summary=raw["logs"],
                )
            )
        if "recent_changes" in raw:
            out.append(
                EvidenceEntry(
                    evidence_id=f"ev_{uuid4().hex[:10]}",
                    source="deployments",
                    kind="deployment-history",
                    confidence=0.7,
                    summary=raw["recent_changes"],
                )
            )
        if "topology" in raw:
            out.append(
                EvidenceEntry(
                    evidence_id=f"ev_{uuid4().hex[:10]}",
                    source="topology",
                    kind="graph",
                    confidence=0.68,
                    summary=raw["topology"],
                )
            )
        return out if out else self._from_raw_legacy(raw.get("metrics", ""), raw.get("logs", ""))

    def _from_raw_legacy(self, metrics: str, logs: str) -> list[EvidenceEntry]:
        return [
            EvidenceEntry(
                evidence_id=f"ev_{uuid4().hex[:10]}",
                source="metrics",
                kind="timeseries",
                confidence=0.82,
                summary=metrics,
            ),
            EvidenceEntry(
                evidence_id=f"ev_{uuid4().hex[:10]}",
                source="logs",
                kind="log-sample",
                confidence=0.74,
                summary=logs,
            ),
        ]
