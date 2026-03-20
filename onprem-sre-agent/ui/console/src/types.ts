export type EvidenceEntry = {
  evidence_id: string;
  source: string;
  kind: string;
  confidence: number;
  summary: string;
  reference?: string | null;
  created_at?: string;
};

export type ActionResult = {
  action_id: string;
  success: boolean;
  status_message: string;
  started_at?: string;
  finished_at?: string;
};

export type ActionRequest = {
  action_id: string;
  action_type: string;
  target: string;
  parameters: Record<string, unknown>;
  idempotency_key: string;
  dry_run?: boolean;
  timeout_seconds?: number;
};

export type PlanStep = {
  step_id: string;
  order?: number;
  action_ref_id?: string | null;
};

export type ActionGraph = {
  objective: string;
  prerequisites: string[];
  safety_checks: string[];
  rollback_plan: string[];
  blast_radius: string;
  success_signal: string;
  actions: ActionRequest[];
  plan_steps?: PlanStep[];
  graph_version?: string;
};

export type RouterDecision = {
  decision_id?: string;
  next_workflow?: string;
  stop_reason?: string | null;
  decision_confidence?: number;
  investigate_only?: boolean;
  rule_ids_applied?: string[];
  created_at?: string;
};

export type DecisionRecord = {
  record_id?: string;
  iteration?: number;
  router_decision?: RouterDecision | null;
  step_executed?: string | null;
  created_at?: string;
};

export type ExecutionTraceEntry = {
  trace_id?: string;
  phase: string;
  action_id?: string | null;
  success?: boolean | null;
  message?: string;
  replan_requested?: boolean;
  created_at?: string;
};

export type ExecutionTrace = {
  entries: ExecutionTraceEntry[];
};

export type HypothesisLink = {
  hypothesis_id: string;
  text?: string;
  confidence?: number;
  supporting_evidence_ids?: string[];
};

export type ApprovalRecord = {
  approval_id: string;
  action_id?: string | null;
  plan_step_id?: string | null;
  approver: string;
  approved: boolean;
  created_at: string;
  reason?: string | null;
};

export type ResponsePlanInfo = {
  plan_id: string;
  policy_class: string;
  workflow_family?: string;
};

export type IncidentRecord = {
  incident_id: string;
  version: number;
  state: string;
  created_at?: string;
  updated_at?: string;
  metadata: {
    source: string;
    severity: string;
    service: string;
    resource: string;
    symptom: string;
    occurred_at?: string;
    dedupe_key?: string;
  };
  response_plan?: ResponsePlanInfo | null;
  hypotheses?: Record<string, unknown>[];
  evidence?: EvidenceEntry[];
  agent_path?: string[];
  approvals?: ApprovalRecord[];
  executed_actions?: ActionResult[];
  final_diagnosis?: string | null;
  final_resolution?: string | null;
  pending_action_graph?: ActionGraph | null;
  pending_approval_action_id?: string | null;
  pending_plan_step_id?: string | null;
  latest_router_decision?: RouterDecision | null;
  decision_records?: DecisionRecord[];
  execution_trace?: ExecutionTrace;
  hypothesis_links?: HypothesisLink[];
  blocked_actions?: string[];
  evidence_coverage_score?: number;
};

export type ReplayScore = {
  routing_precision: number;
  evidence_completeness: number;
  duplicate_call_rate: number;
  policy_violations: number;
  action_correctness: number;
};

export type AuditEvent = {
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type DashboardLoad = {
  incidents: IncidentRecord[];
  auditEvents: AuditEvent[];
  score: ReplayScore | null;
  loadErrors: string[];
};

export type ExecuteResponse = {
  policy: Record<string, unknown>;
  result: ActionResult & Record<string, unknown>;
};
