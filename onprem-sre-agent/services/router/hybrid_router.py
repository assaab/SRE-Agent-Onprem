from __future__ import annotations

import os
from typing import Optional

import httpx

from agents.triage.evidence_intents import extract_triage_dict, normalize_evidence_intents
from libs.agent_runtime.llm import StructuredLLMError, get_llm_client
from libs.agent_runtime.settings import get_agent_runtime_settings
from libs.contracts.models import (
    ActionType,
    IncidentRecord,
    ResponsePlan,
    RouterDecision,
    ToolPlan,
    ToolPlanItem,
)
from pydantic import BaseModel, Field

from services.router.response_plans import match_response_plan


class RouterLLMOutput(BaseModel):
    next_workflow: str = "evidence"
    investigate_only: bool = False
    decision_confidence: float = Field(ge=0.0, le=1.0, default=0.85)
    stop_reason: Optional[str] = None


ROUTER_SYSTEM = (
    "You route on-call incidents. Output strict JSON matching the schema. "
    "If severity is low or symptom is vague, set investigate_only true and next_workflow evidence. "
    "If compute-like CPU/error spikes on critical tiers, next_workflow may be rca after evidence. "
    "Never invent tools."
)


def _deterministic_next_step(
    incident: IncidentRecord,
    plan: ResponsePlan,
) -> RouterDecision:
    triage = extract_triage_dict(incident.hypotheses) or {}
    incident_type = str(triage.get("incident_type", "")).lower()
    priority = str(triage.get("priority", "p2")).lower()

    allowed = list(plan.allowed_actions)
    rule_ids = ["deterministic_base"]

    investigate_only = plan.policy_class.value == "read_only"
    next_workflow = "stop"
    stop_reason: Optional[str] = None

    if not incident.hypotheses:
        next_workflow = "triage"
    elif not incident.evidence:
        next_workflow = "evidence"
    elif len([e for e in incident.evidence if e.source == "change-correlation"]) == 0:
        next_workflow = "change"
    elif not any("hypothesis" in h or "confidence" in h for h in incident.hypotheses):
        next_workflow = "rca"
    else:
        if investigate_only or priority == "p3":
            next_workflow = "stop"
            stop_reason = "investigate_only_or_read_only"
            rule_ids.append("read_only_investigate")
        elif incident_type == "performance" and priority in {"p1", "p2"}:
            next_workflow = "planner"
            rule_ids.append("performance_escalate_plan")
        else:
            next_workflow = "stop"
            stop_reason = "baseline_complete"

    conf = 0.92 if next_workflow != "stop" else 0.75
    intents = normalize_evidence_intents(triage.get("next_required_evidence") if isinstance(triage.get("next_required_evidence"), list) else None)
    tool_items = _tool_plan_from_intents(incident, intents)

    return RouterDecision(
        next_workflow=next_workflow,
        allowed_actions=allowed,
        stop_reason=stop_reason,
        decision_confidence=conf,
        rule_ids_applied=rule_ids,
        investigate_only=bool(investigate_only and stop_reason == "investigate_only_or_read_only"),
        tool_plan=tool_items,
    )


def _tool_plan_from_intents(incident: IncidentRecord, intents: list[str]) -> ToolPlan:
    items: list[ToolPlanItem] = []
    resource = incident.metadata.resource
    service = incident.metadata.service
    for key in intents:
        if key == "metrics":
            items.append(
                ToolPlanItem(
                    tool=ActionType.QUERY_METRICS,
                    target=resource,
                    parameters={"service": service},
                    reason="metrics_intent",
                )
            )
        elif key == "logs":
            items.append(
                ToolPlanItem(
                    tool=ActionType.QUERY_LOGS,
                    target=resource,
                    parameters={"service": service},
                    reason="logs_intent",
                )
            )
        elif key == "recent_changes":
            items.append(
                ToolPlanItem(
                    tool=ActionType.GET_RECENT_DEPLOYMENTS,
                    target=resource,
                    parameters={"service": service},
                    reason="deployments_intent",
                )
            )
        elif key == "topology":
            items.append(
                ToolPlanItem(
                    tool=ActionType.GET_TOPOLOGY,
                    target=resource,
                    parameters={"service": service},
                    reason="topology_intent",
                )
            )
    return ToolPlan(items=items)


async def compute_router_decision(incident: IncidentRecord, plan: Optional[ResponsePlan] = None) -> RouterDecision:
    base_plan = plan or match_response_plan(incident.metadata.severity, incident.metadata.symptom)
    decision = _deterministic_next_step(incident, base_plan)

    use_llm = os.getenv("ROUTER_LLM_ENABLED", "false").lower() == "true"
    settings = get_agent_runtime_settings()
    if not use_llm or not settings.agentic_enabled:
        return decision

    try:
        client = get_llm_client()
        user = (
            f"severity={incident.metadata.severity}\n"
            f"symptom={incident.metadata.symptom}\n"
            f"policy_class={base_plan.policy_class.value}\n"
            f"deterministic_next={decision.next_workflow}\n"
        )
        out = await client.complete_json(
            system=ROUTER_SYSTEM,
            user=user,
            response_model=RouterLLMOutput,
            agent_name="router",
        )
        merged = decision.model_copy(update={
            "next_workflow": out.next_workflow if out.next_workflow else decision.next_workflow,
            "investigate_only": out.investigate_only,
            "decision_confidence": out.decision_confidence,
            "stop_reason": out.stop_reason or decision.stop_reason,
            "rule_ids_applied": list(decision.rule_ids_applied) + ["llm_router"],
        })
        return merged
    except (StructuredLLMError, OSError, httpx.HTTPError, httpx.RequestError):
        return decision


def merge_router_allowed_with_plan(decision: RouterDecision, plan: ResponsePlan) -> RouterDecision:
    allowed_set = set(plan.allowed_actions)
    filtered = [a for a in decision.allowed_actions if a in allowed_set]
    if not filtered:
        filtered = list(plan.allowed_actions)
    return decision.model_copy(update={"allowed_actions": filtered})
