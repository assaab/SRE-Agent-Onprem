from __future__ import annotations

from datetime import datetime

import pytest

from libs.contracts.models import IncidentEnvelope, IncidentRecord
from services.router.hybrid_router import compute_router_decision, merge_router_allowed_with_plan
from services.router.response_plans import match_response_plan


def _incident_empty() -> IncidentRecord:
    return IncidentRecord(
        incident_id="hr1",
        metadata=IncidentEnvelope(
            source="t",
            severity="sev2",
            service="svc",
            resource="k8s-a",
            symptom="cpu spike and errors",
            occurred_at=datetime.utcnow(),
            dedupe_key="d1",
        ),
    )


@pytest.mark.asyncio
async def test_compute_router_starts_with_triage_when_empty() -> None:
    inc = _incident_empty()
    plan = match_response_plan(inc.metadata.severity, inc.metadata.symptom)
    d = await compute_router_decision(inc, plan)
    assert d.next_workflow == "triage"


@pytest.mark.asyncio
async def test_merge_router_filters_allowed_actions() -> None:
    inc = _incident_empty()
    plan = match_response_plan(inc.metadata.severity, inc.metadata.symptom)
    d = await compute_router_decision(inc, plan)
    d = merge_router_allowed_with_plan(d, plan)
    for a in d.allowed_actions:
        assert a in plan.allowed_actions


@pytest.mark.asyncio
async def test_router_evidence_step_has_tool_plan_after_triage() -> None:
    inc = _incident_empty()
    inc.hypotheses.append(
        {
            "triage": {
                "incident_type": "performance",
                "priority": "p1",
                "next_required_evidence": ["metrics"],
            }
        }
    )
    plan = match_response_plan(inc.metadata.severity, inc.metadata.symptom)
    d = await compute_router_decision(inc, plan)
    assert d.tool_plan is not None
    assert len(d.tool_plan.items) >= 1
