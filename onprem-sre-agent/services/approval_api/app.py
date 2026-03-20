from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from libs.contracts.models import ApprovalRecord, IncidentState
from libs.observability import instrument_fastapi, set_request_id
from services.audit.store import audit_store
from services.incident_store.repository import repository

app = FastAPI(title="approval-api")
_default_cors = (
    "http://localhost:5173,http://localhost:5175,"
    "http://127.0.0.1:5173,http://127.0.0.1:5175"
)
allowed_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOW_ORIGINS", _default_cors).split(",")
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


class ApprovalPayload(BaseModel):
    approver: str
    action_id: str
    approved: bool
    reason: Optional[str] = None
    ttl_seconds: int = 900
    plan_step_id: Optional[str] = None
    approval_scope: str = "action"
    expected_incident_version: Optional[int] = None


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/incidents/{incident_id}/approvals")
async def record_approval(incident_id: str, payload: ApprovalPayload, request: Request) -> dict[str, object]:
    set_request_id(request.headers.get("x-request-id", str(uuid4())))
    incident = await repository.get(incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    if incident.state != IncidentState.WAITING_APPROVAL:
        raise HTTPException(status_code=409, detail="incident is not waiting for approval")
    if incident.pending_action_graph is None:
        raise HTTPException(status_code=409, detail="no pending action graph for approval")

    step_id = payload.plan_step_id or incident.pending_plan_step_id
    exp_ver = payload.expected_incident_version if payload.expected_incident_version is not None else incident.version

    record = ApprovalRecord(
        approval_id=f"apr_{uuid4().hex[:10]}",
        action_id=payload.action_id,
        plan_step_id=step_id,
        approval_scope=payload.approval_scope,
        expected_incident_version_at_grant=exp_ver,
        approver=payload.approver,
        approved=payload.approved,
        approval_token=f"token_{uuid4().hex}",
        expires_at=datetime.utcnow() + timedelta(seconds=payload.ttl_seconds),
        reason=payload.reason,
        created_at=datetime.utcnow(),
    )
    incident.approvals.append(record)
    incident.state = IncidentState.PLANNED if payload.approved else IncidentState.WAITING_APPROVAL
    await repository.upsert(incident)
    await audit_store.append(
        "approval_recorded",
        {
            "incident_id": incident_id,
            "approval_id": record.approval_id,
            "action_id": record.action_id,
            "plan_step_id": record.plan_step_id,
            "approval_scope": record.approval_scope,
            "expected_incident_version_at_grant": record.expected_incident_version_at_grant,
            "approved": record.approved,
        },
    )
    return {"incident_id": incident_id, "approval": record.model_dump(mode="json")}
