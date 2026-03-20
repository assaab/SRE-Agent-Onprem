from __future__ import annotations

import os
from typing import Awaitable, Callable

from libs.agent_runtime.budgets import llm_budget_context
from libs.contracts.models import (
    DecisionRecord,
    EvidenceEntry,
    ExecutionTraceEntry,
    HypothesisLink,
    IncidentRecord,
    IncidentState,
    RouterDecision,
)
from libs.memory.working_memory import index_incident_snippet
from libs.observability.logging import get_logger
from services.audit.store import audit_store
from services.incident_store.repository import repository
from services.router.hybrid_router import compute_router_decision, merge_router_allowed_with_plan
from services.router.response_plans import match_response_plan

_logger = get_logger("router-workflow")


def _router_loop_enabled() -> bool:
    return os.getenv("ROUTER_DECISION_LOOP_ENABLED", "false").lower() == "true"


def _max_iterations() -> int:
    return max(1, int(os.getenv("ROUTER_MAX_ITERATIONS", "12")))


def _append_trace(incident: IncidentRecord, phase: str, message: str, **kwargs: object) -> None:
    entry = ExecutionTraceEntry(phase=phase, message=message, **kwargs)
    incident.execution_trace.entries.append(entry)


async def _persist_decision(
    incident: IncidentRecord,
    decision: RouterDecision,
    step: str | None,
    policy_id: str | None,
) -> None:
    incident.latest_router_decision = decision
    rec = DecisionRecord(
        iteration=incident.workflow_iteration,
        router_decision=decision,
        step_executed=step,
        policy_decision_id=policy_id,
    )
    incident.decision_records.append(rec)
    await audit_store.append(
        "router_decision",
        {
            "incident_id": incident.incident_id,
            "decision_id": decision.decision_id,
            "next_workflow": decision.next_workflow,
            "stop_reason": decision.stop_reason,
            "investigate_only": decision.investigate_only,
            "iteration": incident.workflow_iteration,
        },
    )


async def run_linear_route(
    incident: IncidentRecord,
    triage_fn: Callable[[IncidentRecord], Awaitable[dict]],
    evidence_fn: Callable[[IncidentRecord], Awaitable[list[EvidenceEntry]]],
    change_fn: Callable[[IncidentRecord], Awaitable[EvidenceEntry]],
    rca_fn: Callable[[IncidentRecord], Awaitable[list[dict]]],
    write_checkpoint: Callable[[IncidentRecord, str], Awaitable[None]],
) -> IncidentRecord:
    """Legacy fixed order: triage -> evidence -> change -> RCA."""
    incident.response_plan = match_response_plan(
        severity=incident.metadata.severity,
        symptom=incident.metadata.symptom,
    )
    incident.allowed_actions = list(incident.response_plan.allowed_actions)
    incident.state = IncidentState.INVESTIGATING
    await write_checkpoint(incident, "match")

    triage_result = await triage_fn(incident)
    incident.hypotheses.append({"triage": triage_result})
    await write_checkpoint(incident, "triage")

    evidence = await evidence_fn(incident)
    incident.evidence.extend(evidence)
    await write_checkpoint(incident, "evidence")

    incident.evidence.append(await change_fn(incident))
    await write_checkpoint(incident, "change")

    incident.hypotheses.extend(await rca_fn(incident))
    await write_checkpoint(incident, "rca")

    incident.control_plane_version = "v1"
    return await repository.upsert(incident)


async def run_decision_loop_route(
    incident: IncidentRecord,
    triage_fn: Callable[[IncidentRecord], Awaitable[dict]],
    evidence_fn: Callable[[IncidentRecord], Awaitable[list[EvidenceEntry]]],
    change_fn: Callable[[IncidentRecord], Awaitable[EvidenceEntry]],
    rca_fn: Callable[[IncidentRecord], Awaitable[list[dict]]],
    write_checkpoint: Callable[[IncidentRecord, str], Awaitable[None]],
) -> IncidentRecord:
    """Control loop: observe -> router decision -> single step -> repeat."""
    incident.response_plan = match_response_plan(
        severity=incident.metadata.severity,
        symptom=incident.metadata.symptom,
    )
    incident.allowed_actions = list(incident.response_plan.allowed_actions)
    incident.state = IncidentState.INVESTIGATING
    incident.workflow_iteration = 0
    await write_checkpoint(incident, "match")

    assert incident.response_plan is not None
    plan = incident.response_plan

    for _ in range(_max_iterations()):
        incident.workflow_iteration += 1
        raw_decision = await compute_router_decision(incident, plan)
        decision = merge_router_allowed_with_plan(raw_decision, plan)

        if decision.investigate_only and decision.next_workflow in {"planner", "execute"}:
            decision = decision.model_copy(
                update={
                    "next_workflow": "stop",
                    "stop_reason": "investigate_only",
                }
            )

        await _persist_decision(incident, decision, None, None)
        _append_trace(
            incident,
            "decide",
            f"next={decision.next_workflow}",
        )
        await index_incident_snippet(
            incident.incident_id,
            f"iter {incident.workflow_iteration} next {decision.next_workflow}",
        )

        step = decision.next_workflow
        if step == "stop" or decision.stop_reason:
            _append_trace(incident, "stop", decision.stop_reason or "complete")
            break

        if step == "triage":
            triage_result = await triage_fn(incident)
            incident.hypotheses.append({"triage": triage_result})
            await write_checkpoint(incident, "triage")
        elif step == "evidence":
            evidence = await evidence_fn(incident)
            incident.evidence.extend(evidence)
            incident.evidence_coverage_score = min(1.0, len(incident.evidence) / 5.0)
            await write_checkpoint(incident, "evidence")
        elif step == "change":
            incident.evidence.append(await change_fn(incident))
            await write_checkpoint(incident, "change")
        elif step == "rca":
            rca_hyps = await rca_fn(incident)
            incident.hypotheses.extend(rca_hyps)
            for i, h in enumerate(rca_hyps):
                if isinstance(h, dict) and "hypothesis" in h:
                    hid = f"hyp_{incident.incident_id}_{i}"
                    incident.hypothesis_links.append(
                        HypothesisLink(
                            hypothesis_id=hid,
                            text=str(h.get("hypothesis", "")),
                            confidence=float(h.get("confidence", 0.0)),
                            supporting_evidence_ids=list(h.get("supporting_evidence_ids", [])),
                        )
                    )
            await write_checkpoint(incident, "rca")
        elif step == "planner":
            from agents.planner.agent import RemediationPlannerAgent

            planner = RemediationPlannerAgent()
            graph = await planner.run(incident)
            incident.pending_action_graph = graph
            if graph.actions:
                incident.pending_approval_action_id = graph.actions[0].action_id
                if graph.plan_steps:
                    incident.pending_plan_step_id = graph.plan_steps[0].step_id
            incident.state = IncidentState.WAITING_APPROVAL
            await write_checkpoint(incident, "planned")
            _append_trace(incident, "plan", "remediation graph created")
            break
        elif step == "verify":
            _append_trace(incident, "verify", "post_action_verify_stub")
            break
        else:
            _logger.warning("unknown_router_step", step=step)
            break

        await repository.upsert(incident)

    incident.control_plane_version = "v1"
    return await repository.upsert(incident)


async def execute_route(
    incident: IncidentRecord,
    triage_fn: Callable[[IncidentRecord], Awaitable[dict]],
    evidence_fn: Callable[[IncidentRecord], Awaitable[list[EvidenceEntry]]],
    change_fn: Callable[[IncidentRecord], Awaitable[EvidenceEntry]],
    rca_fn: Callable[[IncidentRecord], Awaitable[list[dict]]],
    write_checkpoint: Callable[[IncidentRecord, str], Awaitable[None]],
) -> IncidentRecord:
    with llm_budget_context():
        if _router_loop_enabled():
            return await run_decision_loop_route(
                incident,
                triage_fn,
                evidence_fn,
                change_fn,
                rca_fn,
                write_checkpoint,
            )
        return await run_linear_route(
            incident,
            triage_fn,
            evidence_fn,
            change_fn,
            rca_fn,
            write_checkpoint,
        )
