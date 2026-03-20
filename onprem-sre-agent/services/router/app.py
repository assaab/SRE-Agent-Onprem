from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Union
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agents.change_correlation.agent import ChangeCorrelationAgent
from agents.evidence.agent import EvidenceAgent
from agents.executor.agent import ExecutionAgent
from agents.planner.agent import RemediationPlannerAgent
from agents.rca.agent import RCAAgent
from agents.triage.agent import TriageAgent
from eval.scoring.scorecard import compute_score
from libs.agent_runtime.budgets import llm_budget_context
from libs.contracts.models import (
    ActionRequest,
    ExecutionTraceEntry,
    IncidentRecord,
    IncidentState,
    PolicyClass,
)
from libs.memory import RedisHotStateProvider
from libs.observability import get_logger, instrument_fastapi, set_request_id
from libs.policy.engine import PolicyEngine
from services.audit.store import audit_store
from services.incident_store.repository import repository
from services.router.response_plans import match_response_plan
from services.router.workflow import execute_route

app = FastAPI(title="router")
allowed_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:5173,http://localhost:5175").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
instrument_fastapi(app)
logger = get_logger("router-service")

triage_agent = TriageAgent()
evidence_agent = EvidenceAgent()
change_agent = ChangeCorrelationAgent()
rca_agent = RCAAgent()
planner_agent = RemediationPlannerAgent()
execution_agent = ExecutionAgent()
policy_engine = PolicyEngine()
AUTONOMY_KILL_SWITCH = os.getenv("AUTONOMY_KILL_SWITCH", "true").lower() == "true"
hot_state = RedisHotStateProvider()


def _apply_cors_response_headers(request: Request, response: Response) -> None:
    origin = request.headers.get("origin")
    if origin and origin in allowed_origins:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"


class ExecutePayload(BaseModel):
    action: ActionRequest
    autonomous: bool = False
    approval_id: Optional[str] = None
    expected_incident_version: Optional[int] = None


async def _write_checkpoint(incident: IncidentRecord, step: str) -> None:
    if step not in incident.agent_path:
        incident.agent_path.append(step)
    await repository.upsert(incident)
    await audit_store.append("workflow_checkpoint", {"incident_id": incident.incident_id, "step": step})


def _replay_dataset_path() -> Path:
    return Path(__file__).resolve().parents[2] / "eval" / "datasets" / "compute_performance_incidents.json"


def _effective_execute_dry_run(action: ActionRequest, autonomous: bool) -> bool:
    if os.getenv("EXECUTE_ACTION_DRY_RUN", "false").lower() == "true":
        return True
    if autonomous and not AUTONOMY_KILL_SWITCH:
        return False
    return action.dry_run


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/route/{incident_id}", response_model=IncidentRecord)
async def route_incident(incident_id: str, request: Request) -> IncidentRecord:
    set_request_id(request.headers.get("x-request-id", str(uuid4())))
    lock_token = f"token_{uuid4().hex}"
    lock_key = f"incident_lock:{incident_id}"
    if not await hot_state.acquire_lock(lock_key, lock_token, expire_seconds=30):
        raise HTTPException(status_code=423, detail="incident is currently being routed")
    incident = await repository.get(incident_id)
    if incident is None:
        await hot_state.release_lock(lock_key, lock_token)
        raise HTTPException(status_code=404, detail="incident not found")

    try:
        updated = await execute_route(
            incident,
            triage_agent.run,
            evidence_agent.run,
            change_agent.run,
            rca_agent.run,
            _write_checkpoint,
        )
        if updated.response_plan is None:
            raise HTTPException(status_code=500, detail="response plan missing after routing")
        await audit_store.append(
            "incident_routed",
            {"incident_id": incident_id, "response_plan": updated.response_plan.model_dump(mode="json")},
        )
        logger.info("incident_routed", incident_id=incident_id, response_plan=updated.response_plan.plan_id)
        return updated
    finally:
        await hot_state.release_lock(lock_key, lock_token)


@app.post("/plan/{incident_id}")
async def create_plan(incident_id: str, request: Request) -> dict[str, object]:
    set_request_id(request.headers.get("x-request-id", str(uuid4())))
    incident = await repository.get(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    with llm_budget_context():
        graph = await planner_agent.run(incident)
    incident.pending_action_graph = graph
    incident.pending_approval_action_id = graph.actions[0].action_id if graph.actions else None
    if graph.plan_steps:
        incident.pending_plan_step_id = graph.plan_steps[0].step_id
    incident.state = IncidentState.WAITING_APPROVAL
    await repository.upsert(incident)
    await audit_store.append("remediation_plan_created", {"incident_id": incident_id})
    return graph.model_dump(mode="json")


@app.post("/execute/{incident_id}")
async def execute_action(incident_id: str, payload: ExecutePayload, request: Request) -> dict[str, object]:
    set_request_id(request.headers.get("x-request-id", str(uuid4())))
    incident = await repository.get(incident_id)
    if incident is None or incident.response_plan is None:
        raise HTTPException(status_code=404, detail="incident or response plan not found")

    if payload.expected_incident_version is not None and payload.expected_incident_version != incident.version:
        raise HTTPException(status_code=409, detail="stale incident version")

    if (
        incident.latest_router_decision
        and incident.latest_router_decision.investigate_only
        and incident.pending_action_graph is None
        and os.getenv("BLOCK_EXECUTE_WHEN_INVESTIGATE_ONLY", "true").lower() == "true"
    ):
        await audit_store.append(
            "action_blocked",
            {
                "incident_id": incident_id,
                "action_id": payload.action.action_id,
                "reason": "investigate_only",
                "decision_id": incident.latest_router_decision.decision_id,
            },
        )
        if payload.action.action_type not in incident.blocked_actions:
            incident.blocked_actions.append(payload.action.action_type)
        await repository.upsert(incident)
        raise HTTPException(status_code=403, detail="execution blocked: investigate_only mode")

    if payload.autonomous and AUTONOMY_KILL_SWITCH:
        raise HTTPException(status_code=423, detail="autonomous mode is disabled by kill switch")

    blast = "single service"
    if incident.pending_action_graph is not None:
        blast = incident.pending_action_graph.blast_radius

    decision = policy_engine.evaluate(
        plan=incident.response_plan,
        action=payload.action,
        autonomous=payload.autonomous,
        planner_confidence=incident.last_planner_confidence,
        blast_radius=blast,
        severity=incident.metadata.severity,
        evidence_coverage=incident.evidence_coverage_score,
    )
    if not decision.allowed:
        if payload.action.action_type not in incident.blocked_actions:
            incident.blocked_actions.append(payload.action.action_type)
        await repository.upsert(incident)
        await audit_store.append(
            "action_blocked",
            {
                "incident_id": incident_id,
                "action_id": payload.action.action_id,
                "reason": decision.reason,
                "decision_id": decision.decision_id,
                "policy_rule_id": decision.rule_id,
                "deny_reason_code": decision.deny_reason_code,
            },
        )
        raise HTTPException(status_code=403, detail=decision.reason)

    if decision.requires_approval and not payload.autonomous:
        if payload.approval_id is None:
            raise HTTPException(status_code=412, detail="approval is required before execution")
        approval_record = next((item for item in incident.approvals if item.approval_id == payload.approval_id), None)
        if approval_record is None or not approval_record.approved:
            raise HTTPException(status_code=412, detail="approval record missing or denied")
        if approval_record.expires_at < datetime.utcnow():
            raise HTTPException(status_code=412, detail="approval has expired")
        if approval_record.action_id and approval_record.action_id != payload.action.action_id:
            raise HTTPException(status_code=412, detail="approval does not match action")
        if approval_record.plan_step_id and incident.pending_plan_step_id:
            if approval_record.plan_step_id != incident.pending_plan_step_id:
                raise HTTPException(status_code=412, detail="approval does not match plan step")

    dry = _effective_execute_dry_run(payload.action, payload.autonomous)
    run_action = payload.action.model_copy(update={"dry_run": dry})

    incident.state = IncidentState.EXECUTING
    incident.execution_trace.entries.append(
        ExecutionTraceEntry(phase="act", action_id=run_action.action_id, message="execute_start")
    )
    result = await execution_agent.run(run_action)
    incident.executed_actions.append(result)
    incident.execution_trace.entries.append(
        ExecutionTraceEntry(
            phase="observe",
            action_id=run_action.action_id,
            success=result.success,
            message=result.status_message,
            replan_requested=not result.success,
        )
    )
    if os.getenv("EXECUTE_POST_VERIFY_ENABLED", "true").lower() == "true":
        incident.execution_trace.entries.append(
            ExecutionTraceEntry(
                phase="verify",
                action_id=run_action.action_id,
                success=result.success,
                message="post_verify_stub",
            )
        )

    incident.state = IncidentState.RESOLVED if result.success else IncidentState.INVESTIGATING
    await repository.upsert(incident)
    await audit_store.append(
        "action_executed",
        {
            "incident_id": incident_id,
            "action_id": payload.action.action_id,
            "success": result.success,
            "autonomous": payload.autonomous,
            "policy_decision_id": decision.decision_id,
            "policy_rule_id": decision.rule_id,
        },
    )
    if not result.success and incident.response_plan.policy_class != PolicyClass.READ_ONLY:
        await audit_store.append(
            "execution_escalation_triggered",
            {
                "incident_id": incident_id,
                "action_id": payload.action.action_id,
                "decision_id": decision.decision_id,
            },
        )
    return {"policy": decision.model_dump(mode="json"), "result": result.model_dump(mode="json")}


@app.get("/replay/score")
async def replay_score(request: Request, response: Response) -> dict[str, Union[float, int]]:
    _apply_cors_response_headers(request, response)
    fixtures = json.loads(_replay_dataset_path().read_text(encoding="utf-8"))
    matches = 0
    evidence_items = 0
    duplicates = 0
    violations = 0
    seen = set()
    for incident in fixtures:
        plan = match_response_plan(incident["severity"], incident["symptom"])
        if plan.plan_id == incident["expected_route"]:
            matches += 1
        evidence_items += 3
        key = f"{incident['service']}:{incident['resource']}"
        if key in seen:
            duplicates += 1
        seen.add(key)
        if any(action.value == "RunShell" for action in plan.allowed_actions):
            violations += 1
    score = compute_score(matches, len(fixtures), evidence_items, duplicates, violations)
    return {
        "routing_precision": score.routing_precision,
        "evidence_completeness": score.evidence_completeness,
        "duplicate_call_rate": score.duplicate_call_rate,
        "policy_violations": score.policy_violations,
        "action_correctness": score.action_correctness,
    }
