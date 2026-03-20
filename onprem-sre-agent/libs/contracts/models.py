from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class PolicyClass(str, Enum):
    READ_ONLY = "read_only"
    REVIEW_REQUIRED = "review_required"
    PRIVILEGED = "privileged"


class IncidentState(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    PLANNED = "planned"
    WAITING_APPROVAL = "waiting_approval"
    EXECUTING = "executing"
    RESOLVED = "resolved"
    REOPENED = "reopened"


class ActionType(str, Enum):
    QUERY_METRICS = "QueryMetrics"
    QUERY_LOGS = "QueryLogs"
    GET_RECENT_DEPLOYMENTS = "GetRecentDeployments"
    GET_TOPOLOGY = "GetTopology"
    RESTART_SERVICE = "RestartService"
    SCALE_WORKLOAD = "ScaleWorkload"
    ROLLBACK_DEPLOYMENT = "RollbackDeployment"
    DRAIN_NODE = "DrainNode"
    OPEN_TICKET = "OpenTicket"
    PAGE_HUMAN = "PageHuman"
    RUN_ANSIBLE_JOB = "RunAnsibleJob"
    RUN_SHELL = "RunShell"


class EvidenceEntry(BaseModel):
    evidence_id: str
    source: str
    kind: str
    confidence: float = Field(ge=0.0, le=1.0)
    summary: str
    reference: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ApprovalRecord(BaseModel):
    approval_id: str
    action_id: Optional[str] = None
    plan_step_id: Optional[str] = None
    approval_scope: str = "action"
    expected_incident_version_at_grant: Optional[int] = None
    approver: str
    approved: bool
    approval_token: str
    expires_at: datetime
    reason: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ActionRequest(BaseModel):
    action_id: str
    action_type: ActionType
    target: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str
    dry_run: bool = True
    timeout_seconds: int = 120


class ActionResult(BaseModel):
    action_id: str
    success: bool
    status_message: str
    started_at: datetime
    finished_at: datetime
    rollback_action: Optional[ActionRequest] = None


class PlanStep(BaseModel):
    """Ordered remediation step with execution intent separate from dry-run policy."""

    step_id: str
    order: int = 0
    action_ref_id: Optional[str] = None
    preconditions: list[str] = Field(default_factory=list)
    verification_signal: str = ""
    rollback_hint: Optional[str] = None
    execute_intent: str = "execute"
    risk_tier: str = "medium"


class ActionGraph(BaseModel):
    objective: str
    prerequisites: list[str]
    safety_checks: list[str]
    rollback_plan: list[str]
    blast_radius: str
    success_signal: str
    actions: list[ActionRequest]
    plan_steps: list[PlanStep] = Field(default_factory=list)
    graph_version: str = "v1"


class ToolPlanItem(BaseModel):
    """Single validated tool invocation for evidence or read-only collection."""

    tool: ActionType
    target: str = ""
    parameters: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class ToolPlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: f"tp_{uuid4().hex[:10]}")
    items: list[ToolPlanItem] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class RouterDecision(BaseModel):
    """First-class routing output persisted each workflow iteration."""

    decision_id: str = Field(default_factory=lambda: f"rd_{uuid4().hex[:10]}")
    next_workflow: str = "stop"
    allowed_actions: list[ActionType] = Field(default_factory=list)
    stop_reason: Optional[str] = None
    decision_confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    rule_ids_applied: list[str] = Field(default_factory=list)
    investigate_only: bool = False
    tool_plan: Optional[ToolPlan] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DecisionRecord(BaseModel):
    """Audit trail for observe-decide-act transitions."""

    record_id: str = Field(default_factory=lambda: f"dr_{uuid4().hex[:10]}")
    iteration: int = 0
    router_decision: Optional[RouterDecision] = None
    step_executed: Optional[str] = None
    policy_decision_id: Optional[str] = None
    notes: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ExecutionTraceEntry(BaseModel):
    """One observe or act step in the closed loop."""

    trace_id: str = Field(default_factory=lambda: f"et_{uuid4().hex[:10]}")
    phase: str
    action_id: Optional[str] = None
    success: Optional[bool] = None
    message: str = ""
    replan_requested: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ExecutionTrace(BaseModel):
    entries: list[ExecutionTraceEntry] = Field(default_factory=list)


class HypothesisLink(BaseModel):
    """Structured link from hypothesis to evidence and downstream actions."""

    hypothesis_id: str
    text: str = ""
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    related_action_ids: list[str] = Field(default_factory=list)


class ResponsePlan(BaseModel):
    plan_id: str
    workflow_family: str
    policy_class: PolicyClass
    allowed_actions: list[ActionType]
    denied_actions: list[ActionType]
    max_retries: int = 2


class IncidentEnvelope(BaseModel):
    version: str = "v1"
    source: str
    severity: str
    service: str
    resource: str
    symptom: str
    occurred_at: datetime
    dedupe_key: str
    raw_payload_ref: Optional[str] = None


class IncidentRecord(BaseModel):
    incident_id: str
    metadata: IncidentEnvelope
    state: IncidentState = IncidentState.OPEN
    hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[EvidenceEntry] = Field(default_factory=list)
    tools_used: list[ActionType] = Field(default_factory=list)
    blocked_actions: list[ActionType] = Field(default_factory=list)
    allowed_actions: list[ActionType] = Field(default_factory=list)
    response_plan: Optional[ResponsePlan] = None
    agent_path: list[str] = Field(default_factory=list)
    approvals: list[ApprovalRecord] = Field(default_factory=list)
    executed_actions: list[ActionResult] = Field(default_factory=list)
    final_diagnosis: Optional[str] = None
    final_resolution: Optional[str] = None
    lessons_learned: list[str] = Field(default_factory=list)
    pending_action_graph: Optional[ActionGraph] = None
    pending_approval_action_id: Optional[str] = None
    pending_plan_step_id: Optional[str] = None
    latest_router_decision: Optional[RouterDecision] = None
    decision_records: list[DecisionRecord] = Field(default_factory=list)
    execution_trace: ExecutionTrace = Field(default_factory=ExecutionTrace)
    hypothesis_links: list[HypothesisLink] = Field(default_factory=list)
    workflow_iteration: int = 0
    control_plane_version: str = "v1"
    decision_schema_version: str = "v1"
    last_planner_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    evidence_coverage_score: float = Field(ge=0.0, le=1.0, default=0.0)
    version: int = 1
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class PolicyDecision(BaseModel):
    decision_id: str = Field(default_factory=lambda: f"pd_{uuid4().hex[:10]}")
    allowed: bool
    policy_class: PolicyClass
    reason: str
    requires_approval: bool
    policy_version: str = "v1"
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)
    rule_id: Optional[str] = None
    deny_reason_code: Optional[str] = None
    requires_approval_scope: str = "action"
