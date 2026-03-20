from __future__ import annotations

from datetime import datetime

from libs.contracts.models import (
    ActionResult,
    ExecutionTraceEntry,
    IncidentEnvelope,
    IncidentRecord,
)


def test_execution_trace_marks_replan_on_failure() -> None:
    inc = IncidentRecord(
        incident_id="et1",
        metadata=IncidentEnvelope(
            source="t",
            severity="sev2",
            service="s",
            resource="r",
            symptom="x",
            occurred_at=datetime.utcnow(),
            dedupe_key="k",
        ),
    )
    inc.execution_trace.entries.append(
        ExecutionTraceEntry(
            phase="observe",
            action_id="a1",
            success=False,
            message="failed",
            replan_requested=True,
        )
    )
    assert inc.execution_trace.entries[-1].replan_requested is True


def test_action_result_links_to_trace_phases() -> None:
    ar = ActionResult(
        action_id="a1",
        success=False,
        status_message="err",
        started_at=datetime.utcnow(),
        finished_at=datetime.utcnow(),
    )
    assert ar.success is False
