import { ActionRequest, AuditEvent, DashboardLoad, ExecuteResponse, IncidentRecord, ReplayScore } from "./types";

/**
 * In dev, prefer same-origin `/api/*` proxies (see vite.config.ts) so requests are not blocked by CORS
 * when the UI is opened as http://127.0.0.1:5173 but backends use localhost (or vice versa).
 * Set VITE_*_URL in ui/console/.env to override.
 */
function baseFromEnvOrDevProxy(envUrl: string | undefined, devProxyPath: string, fallback: string): string {
  if (envUrl && envUrl.length > 0) {
    return envUrl;
  }
  if (import.meta.env.DEV) {
    return devProxyPath;
  }
  return fallback;
}

const incidentStoreBase = baseFromEnvOrDevProxy(
  import.meta.env.VITE_INCIDENT_STORE_URL,
  "/api/incidents-store",
  "http://localhost:8002"
);
const auditBase = baseFromEnvOrDevProxy(import.meta.env.VITE_AUDIT_URL, "/api/audit", "http://localhost:8006");
const routerBase = baseFromEnvOrDevProxy(import.meta.env.VITE_ROUTER_URL, "/api/router", "http://localhost:8003");
const approvalBase = baseFromEnvOrDevProxy(
  import.meta.env.VITE_APPROVAL_URL,
  "/api/approval",
  "http://localhost:8005"
);

const jsonHeaders = { "Content-Type": "application/json" };

const emptyScore: ReplayScore = {
  routing_precision: 0,
  evidence_completeness: 0,
  duplicate_call_rate: 0,
  policy_violations: 0,
  action_correctness: 0
};

export async function loadDashboard(): Promise<DashboardLoad> {
  const loadErrors: string[] = [];

  let incidents: IncidentRecord[] = [];
  try {
    const r = await fetch(`${incidentStoreBase}/incidents`);
    if (!r.ok) {
      loadErrors.push(`Incident store returned ${r.status}`);
    } else {
      incidents = (await r.json()) as IncidentRecord[];
    }
  } catch {
    loadErrors.push("Incident store unreachable (check port 8002)");
  }

  let auditEvents: AuditEvent[] = [];
  try {
    const r = await fetch(`${auditBase}/events`);
    if (!r.ok) {
      loadErrors.push(`Audit API returned ${r.status}`);
    } else {
      auditEvents = (await r.json()) as AuditEvent[];
    }
  } catch {
    loadErrors.push("Audit API unreachable (check port 8006)");
  }

  let score: ReplayScore | null = null;
  try {
    const r = await fetch(`${routerBase}/replay/score`);
    if (!r.ok) {
      loadErrors.push(`Router replay returned ${r.status}`);
      score = emptyScore;
    } else {
      score = (await r.json()) as ReplayScore;
    }
  } catch {
    loadErrors.push("Router unreachable (check port 8003)");
    score = emptyScore;
  }

  return { incidents, auditEvents, score, loadErrors };
}

/** Latest incident from the store (use before execute/approval to avoid stale version). */
export async function fetchIncident(incidentId: string): Promise<IncidentRecord> {
  const r = await fetch(`${incidentStoreBase}/incidents/${encodeURIComponent(incidentId)}`);
  if (!r.ok) {
    const detail = await r.text();
    throw new Error(`Failed to load incident (${r.status}): ${detail}`);
  }
  return (await r.json()) as IncidentRecord;
}

export async function routeIncident(incidentId: string): Promise<void> {
  const r = await fetch(`${routerBase}/route/${encodeURIComponent(incidentId)}`, {
    method: "POST",
    headers: jsonHeaders
  });
  if (!r.ok) {
    const detail = await r.text();
    throw new Error(`Route failed (${r.status}): ${detail}`);
  }
}

export async function planIncident(incidentId: string): Promise<void> {
  const r = await fetch(`${routerBase}/plan/${encodeURIComponent(incidentId)}`, {
    method: "POST",
    headers: jsonHeaders
  });
  if (!r.ok) {
    const detail = await r.text();
    throw new Error(`Plan failed (${r.status}): ${detail}`);
  }
}

export type ApprovalSubmit = {
  approver: string;
  actionId: string;
  approved: boolean;
  reason?: string;
  planStepId?: string | null;
  expectedIncidentVersion: number;
};

export async function submitApproval(incidentId: string, body: ApprovalSubmit): Promise<{ approval_id: string }> {
  const url = `${approvalBase}/incidents/${encodeURIComponent(incidentId)}/approvals`;
  let r: Response;
  try {
    r = await fetch(url, {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({
        approver: body.approver,
        action_id: body.actionId,
        approved: body.approved,
        reason: body.reason || undefined,
        plan_step_id: body.planStepId ?? undefined,
        expected_incident_version: body.expectedIncidentVersion
      })
    });
  } catch (e) {
    const hint =
      "Cannot reach the approval API. Start it on port 8005, or set VITE_APPROVAL_URL in ui/console/.env. " +
      "If the UI and API use different hostnames (localhost vs 127.0.0.1), use `npm run dev` proxies or " +
      "add your page origin to the API CORS_ALLOW_ORIGINS.";
    if (e instanceof TypeError) {
      throw new Error(`${e.message}. ${hint}`);
    }
    throw e;
  }
  if (!r.ok) {
    const detail = await r.text();
    throw new Error(`Approval failed (${r.status}): ${detail}`);
  }
  const data = (await r.json()) as { approval?: { approval_id?: string } };
  const id = data.approval?.approval_id;
  if (!id) {
    throw new Error("Approval response missing approval_id");
  }
  return { approval_id: id };
}

export async function executeIncidentAction(
  incidentId: string,
  action: ActionRequest,
  opts: { approvalId?: string | null; expectedVersion: number; dryRun: boolean }
): Promise<ExecuteResponse> {
  const payload = {
    action: {
      ...action,
      dry_run: opts.dryRun,
      timeout_seconds: action.timeout_seconds ?? 120
    },
    autonomous: false,
    approval_id: opts.approvalId ?? undefined,
    expected_incident_version: opts.expectedVersion
  };
  const r = await fetch(`${routerBase}/execute/${encodeURIComponent(incidentId)}`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify(payload)
  });
  if (!r.ok) {
    const detail = await r.text();
    throw new Error(`Execute failed (${r.status}): ${detail}`);
  }
  return (await r.json()) as ExecuteResponse;
}
