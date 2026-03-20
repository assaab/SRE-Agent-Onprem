from __future__ import annotations

import os
from uuid import uuid4

import httpx

from agents.planner.prompts import PLANNER_SYSTEM
from agents.planner.schemas import PlannerLLMOutput
from libs.agent_runtime.llm import StructuredLLMError, get_llm_client
from libs.agent_runtime.settings import get_agent_runtime_settings
from libs.agent_runtime.tracing import agent_span

from libs.contracts.models import ActionGraph, ActionRequest, ActionType, IncidentRecord, PlanStep
from libs.memory.working_memory import search_incident_memory
from libs.observability.logging import get_logger

_logger = get_logger("planner-agent")


class RemediationPlannerAgent:
    async def run(self, incident: IncidentRecord) -> ActionGraph:
        with agent_span("planner"):
            settings = get_agent_runtime_settings()
            if incident.response_plan is None:
                if settings.agentic_enabled and not settings.agentic_stub_fallback:
                    raise StructuredLLMError("incident has no response_plan for planner")
                return self._stub_graph(incident)
            if not settings.agentic_enabled:
                return self._stub_graph(incident)
            try:
                client = get_llm_client()
                allowed = set(incident.response_plan.allowed_actions)
                user = await self._format_user(incident, allowed)
                out = await client.complete_json(
                    system=PLANNER_SYSTEM,
                    user=user,
                    response_model=PlannerLLMOutput,
                    agent_name="planner",
                )
                incident.last_planner_confidence = float(out.planner_confidence)
                actions = self._clamp_actions(incident, out.action_type_names, allowed)
                if not actions:
                    if not settings.agentic_stub_fallback:
                        raise StructuredLLMError("LLM produced no actions allowed by the response plan")
                    return self._stub_graph(incident)
                plan_steps = self._build_plan_steps(actions, out.blast_radius)
                graph = ActionGraph(
                    objective=out.objective or "Restore service stability while minimizing blast radius",
                    prerequisites=out.prerequisites or ["Recent backup validated"],
                    safety_checks=out.safety_checks or ["Confirm target allowlist"],
                    rollback_plan=out.rollback_plan or ["Roll back deployment", "Page human"],
                    blast_radius=out.blast_radius,
                    success_signal=out.success_signal or "Error rate and CPU return below threshold",
                    actions=actions,
                    plan_steps=plan_steps,
                )
                return graph
            except (StructuredLLMError, OSError, httpx.HTTPError, httpx.RequestError) as exc:
                if not settings.agentic_stub_fallback:
                    raise
                _logger.warning("planner_llm_fallback", error=str(exc))
                return self._stub_graph(incident)

    def _default_dry_run_for_plan(self) -> bool:
        return os.getenv("PLANNER_DEFAULT_DRY_RUN", "false").lower() == "true"

    def _build_plan_steps(self, actions: list[ActionRequest], blast_radius: str) -> list[PlanStep]:
        steps: list[PlanStep] = []
        for i, a in enumerate(actions):
            risk = "high" if a.action_type in {
                ActionType.ROLLBACK_DEPLOYMENT,
                ActionType.DRAIN_NODE,
                ActionType.RUN_ANSIBLE_JOB,
            } else "medium"
            steps.append(
                PlanStep(
                    step_id=f"ps_{uuid4().hex[:8]}",
                    order=i,
                    action_ref_id=a.action_id,
                    verification_signal="metrics_stable",
                    risk_tier=risk,
                    rollback_hint="rollback_plan" if risk == "high" else None,
                )
            )
        return steps

    def _clamp_actions(
        self,
        incident: IncidentRecord,
        names: list[str],
        allowed: set[ActionType],
    ) -> list[ActionRequest]:
        dry = self._default_dry_run_for_plan()
        actions: list[ActionRequest] = []
        for raw in names:
            try:
                at = ActionType(raw)
            except ValueError:
                continue
            if at not in allowed:
                continue
            actions.append(
                ActionRequest(
                    action_id=f"act_{uuid4().hex[:8]}",
                    action_type=at,
                    target=incident.metadata.resource,
                    parameters={"service": incident.metadata.service},
                    idempotency_key=f"{incident.incident_id}:{at.value}",
                    dry_run=dry,
                )
            )
        return actions

    async def _format_user(self, incident: IncidentRecord, allowed: set[ActionType]) -> str:
        allowed_names = sorted(a.value for a in allowed)
        mem = await search_incident_memory(incident.incident_id, incident.metadata.symptom, limit=3)
        mem_block = "\n".join(mem) if mem else ""
        return (
            f"incident_id={incident.incident_id}\n"
            f"symptom={incident.metadata.symptom}\n"
            f"allowed_action_types={allowed_names}\n"
            f"working_memory=\n{mem_block}\n"
        )

    def _stub_graph(self, incident: IncidentRecord) -> ActionGraph:
        dry = self._default_dry_run_for_plan()
        incident.last_planner_confidence = 0.88
        action_candidates = [
            ActionRequest(
                action_id=f"act_{uuid4().hex[:8]}",
                action_type=ActionType.RESTART_SERVICE,
                target=incident.metadata.resource,
                parameters={"service": incident.metadata.service},
                idempotency_key=f"{incident.incident_id}:restart",
                dry_run=dry,
            ),
            ActionRequest(
                action_id=f"act_{uuid4().hex[:8]}",
                action_type=ActionType.SCALE_WORKLOAD,
                target=incident.metadata.resource,
                parameters={"service": incident.metadata.service, "maxReplicas": 5},
                idempotency_key=f"{incident.incident_id}:scale",
                dry_run=dry,
            ),
        ]
        steps = self._build_plan_steps(action_candidates, "single service")
        return ActionGraph(
            objective="Restore service stability while minimizing blast radius",
            prerequisites=["Recent backup validated", "Operator channel notified"],
            safety_checks=["Confirm target allowlist", "Confirm error rate threshold"],
            rollback_plan=["Roll back deployment", "Scale down to prior size", "Page human"],
            blast_radius="single service",
            success_signal="Error rate and CPU return below threshold for 10 minutes",
            actions=action_candidates,
            plan_steps=steps,
        )
