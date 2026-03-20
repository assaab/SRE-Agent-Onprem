from __future__ import annotations

from datetime import datetime

from libs.contracts.models import (
    ActionRequest,
    ActionType,
    IncidentEnvelope,
    IncidentRecord,
    PolicyClass,
    ResponsePlan,
)
from libs.policy.engine import PolicyEngine


def _base_plan() -> ResponsePlan:
    return ResponsePlan(
        plan_id="compute-performance-v1",
        workflow_family="compute-performance",
        policy_class=PolicyClass.REVIEW_REQUIRED,
        allowed_actions=[ActionType.RESTART_SERVICE, ActionType.ROLLBACK_DEPLOYMENT],
        denied_actions=[ActionType.RUN_SHELL],
        max_retries=2,
    )


def _restart_action() -> ActionRequest:
    return ActionRequest(
        action_id="act_test",
        action_type=ActionType.RESTART_SERVICE,
        target="k8s-checkout",
        parameters={"service": "s"},
        idempotency_key="k",
        dry_run=False,
    )


def test_approval_rule_requires_confidence_and_blast_radius() -> None:
    policy = PolicyEngine()
    plan = _base_plan()
    action = _restart_action()
    low = policy.evaluate(
        plan,
        action,
        autonomous=False,
        planner_confidence=0.5,
        blast_radius="single service",
        severity="sev2",
    )
    assert low.requires_approval is True

    high = policy.evaluate(
        plan,
        action,
        autonomous=False,
        planner_confidence=0.95,
        blast_radius="single service",
        severity="sev2",
    )
    assert high.requires_approval is False
    assert high.rule_id == "low-risk-autonomy-candidates"


def test_high_risk_rule_always_requires_approval() -> None:
    policy = PolicyEngine()
    plan = _base_plan()
    action = ActionRequest(
        action_id="act_rb",
        action_type=ActionType.ROLLBACK_DEPLOYMENT,
        target="k8s-checkout",
        parameters={"service": "s", "deployment": "d", "to_revision": "r1"},
        idempotency_key="k2",
        dry_run=False,
    )
    decision = policy.evaluate(
        plan,
        action,
        autonomous=False,
        planner_confidence=0.99,
        blast_radius="single service",
        severity="sev1",
    )
    assert decision.requires_approval is True
    assert decision.rule_id == "high-risk-writes-require-review"


def test_investigate_only_execute_blocked_when_flag_set(monkeypatch) -> None:
    from httpx import ASGITransport, AsyncClient

    from libs.contracts.models import IncidentState, RouterDecision
    from services.router.app import app as router_app

    monkeypatch.setenv("BLOCK_EXECUTE_WHEN_INVESTIGATE_ONLY", "true")

    incident = IncidentRecord(
        incident_id="inc_inv",
        metadata=IncidentEnvelope(
            source="t",
            severity="sev4",
            service="s",
            resource="k8s-x",
            symptom="latency",
            occurred_at=datetime.utcnow(),
            dedupe_key="dk",
        ),
        state=IncidentState.INVESTIGATING,
        response_plan=_base_plan(),
    )
    incident.latest_router_decision = RouterDecision(
        next_workflow="stop",
        investigate_only=True,
        decision_confidence=0.9,
    )

    async def _get(_id: str):
        return incident

    async def _upsert(_):
        return incident

    monkeypatch.setattr("services.router.app.repository.get", _get)
    monkeypatch.setattr("services.router.app.repository.upsert", _upsert)

    async def run():
        transport = ASGITransport(app=router_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/execute/inc_inv",
                json={
                    "action": {
                        "action_id": "a1",
                        "action_type": "RestartService",
                        "target": "k8s-x",
                        "parameters": {"service": "s"},
                        "idempotency_key": "id1",
                        "dry_run": True,
                    },
                    "autonomous": False,
                },
            )
        return resp

    import asyncio

    resp = asyncio.run(run())
    assert resp.status_code == 403
