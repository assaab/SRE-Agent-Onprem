import { CSSProperties, useEffect, useMemo, useState } from "react";
import {
  executeIncidentAction,
  fetchIncident,
  planIncident,
  routeIncident,
  submitApproval
} from "../api";
import { formatDateTime, formatRelativeTime, humanizeSeverity, humanizeState } from "../format";
import { ActionRequest, AuditEvent, ExecuteResponse, IncidentRecord, ReplayScore } from "../types";

function pickPendingAction(inc: IncidentRecord): ActionRequest | null {
  const g = inc.pending_action_graph;
  if (!g?.actions?.length) {
    return null;
  }
  const want = inc.pending_approval_action_id;
  if (want) {
    const found = g.actions.find((a) => a.action_id === want);
    if (found) {
      return found;
    }
  }
  return g.actions[0] ?? null;
}

/** Action id for approval API: prefer graph match, else incident.pending_approval_action_id. */
function approvalActionId(inc: IncidentRecord): string | null {
  const act = pickPendingAction(inc);
  if (act) {
    return act.action_id;
  }
  const fallback = inc.pending_approval_action_id;
  return typeof fallback === "string" && fallback.length > 0 ? fallback : null;
}

function resolveApprovalIdForAction(inc: IncidentRecord, actionId: string): string | null {
  const chain = [...(inc.approvals ?? [])].reverse();
  const rec = chain.find((a) => a.approved && a.action_id === actionId);
  return rec?.approval_id ?? null;
}

type Props = {
  incidents: IncidentRecord[];
  auditEvents: AuditEvent[];
  score: ReplayScore | null;
  loading: boolean;
  onRefresh: () => void;
};

function stateStyles(state: string): { bg: string; fg: string } {
  const s = state.toLowerCase();
  if (s === "resolved") {
    return { bg: "var(--state-resolved-bg)", fg: "var(--state-resolved-fg)" };
  }
  if (s === "open") {
    return { bg: "var(--state-open-bg)", fg: "var(--state-open-fg)" };
  }
  if (s === "investigating" || s === "executing") {
    return { bg: "var(--state-investigating-bg)", fg: "var(--state-investigating-fg)" };
  }
  if (s === "waiting_approval" || s === "planned") {
    return { bg: "var(--state-waiting-bg)", fg: "var(--state-waiting-fg)" };
  }
  return { bg: "var(--state-default-bg)", fg: "var(--state-default-fg)" };
}

function severityStyles(sev: string): { bg: string; fg: string } {
  const s = sev.toLowerCase();
  if (s === "sev1" || s === "sev2") {
    return { bg: "var(--sev-high-bg)", fg: "var(--sev-high-fg)" };
  }
  if (s === "sev3") {
    return { bg: "var(--sev-mid-bg)", fg: "var(--sev-mid-fg)" };
  }
  return { bg: "var(--sev-low-bg)", fg: "var(--sev-low-fg)" };
}

function badge(text: string, palette: { bg: string; fg: string }): JSX.Element {
  return (
    <span
      style={{
        display: "inline-block",
        fontSize: 11,
        fontWeight: 600,
        letterSpacing: "0.04em",
        textTransform: "uppercase" as const,
        padding: "3px 10px",
        borderRadius: "var(--radius-pill)",
        background: palette.bg,
        color: palette.fg
      }}
    >
      {text}
    </span>
  );
}

function incidentAuditFilter(ev: AuditEvent, incidentId: string): boolean {
  const id = ev.payload.incident_id;
  return typeof id === "string" && id === incidentId;
}

const sectionTitle: CSSProperties = {
  fontSize: 14,
  fontWeight: 600,
  margin: "0 0 8px 0",
  color: "var(--text)"
};

export function IncidentWorkspace(props: Props): JSX.Element {
  const { incidents, auditEvents, score, loading, onRefresh } = props;
  const [query, setQuery] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showAllAudit, setShowAllAudit] = useState(false);
  const [routing, setRouting] = useState(false);
  const [routeError, setRouteError] = useState<string | null>(null);
  const [planning, setPlanning] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);
  const [approverName, setApproverName] = useState("on-call-operator");
  const [approving, setApproving] = useState(false);
  const [approveError, setApproveError] = useState<string | null>(null);
  const [executeDryRun, setExecuteDryRun] = useState(true);
  const [executing, setExecuting] = useState(false);
  const [executeError, setExecuteError] = useState<string | null>(null);
  const [executeResult, setExecuteResult] = useState<ExecuteResponse | null>(null);

  const sorted = useMemo(() => {
    return [...incidents].sort((a, b) => {
      const ta = a.updated_at ? Date.parse(a.updated_at) : 0;
      const tb = b.updated_at ? Date.parse(b.updated_at) : 0;
      return tb - ta;
    });
  }, [incidents]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) {
      return sorted;
    }
    return sorted.filter((inc) => {
      const hay = [
        inc.incident_id,
        inc.metadata.service,
        inc.metadata.resource,
        inc.metadata.symptom,
        inc.state
      ]
        .join(" ")
        .toLowerCase();
      return hay.includes(q);
    });
  }, [sorted, query]);

  useEffect(() => {
    if (selectedId === null && sorted.length > 0) {
      setSelectedId(sorted[0].incident_id);
    }
  }, [sorted, selectedId]);

  useEffect(() => {
    setExecuteResult(null);
    setExecuteError(null);
    setApproveError(null);
  }, [selectedId]);

  const selected = useMemo(
    () => incidents.find((i) => i.incident_id === selectedId) ?? null,
    [incidents, selectedId]
  );

  const timelineEvents = useMemo(() => {
    const list = [...auditEvents].sort(
      (a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)
    );
    if (showAllAudit || !selectedId) {
      return list;
    }
    return list.filter((ev) => incidentAuditFilter(ev, selectedId));
  }, [auditEvents, selectedId, showAllAudit]);

  return (
    <div className="incident-monitor-root">
      <div style={{ display: "contents" }}>
        {/* List */}
        <div className="panel-card panel-card--workspace">
          <div className="panel-card__header">
            <div className="panel-card__header-row">
              <div>
                <h2 className="panel-card__title">Queue</h2>
                <p className="panel-card__hint">Newest first. Select a row to open the detail inspector.</p>
              </div>
            </div>
            <label style={{ display: "block", marginTop: 12 }}>
              <span className="sr-only">Filter incidents</span>
              <input
                type="search"
                className="form-input"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search id, service, resource, symptom..."
              />
            </label>
            {selectedId !== null && query.trim() !== "" && !filtered.some((i) => i.incident_id === selectedId) && (
              <p className="text-warning-inline" style={{ margin: "10px 0 0", fontSize: 12 }}>
                The selected incident is hidden by this filter. Clear the filter or pick another row to match the detail
                panel.
              </p>
            )}
          </div>
          <div className="panel-card__body">
            {filtered.length === 0 && (
              <p style={{ padding: "12px 8px", color: "var(--text-secondary)", margin: 0 }}>
                No incidents match your filter. Ingest a payload via POST /ingest on port 8001 to create one.
              </p>
            )}
            {filtered.map((inc) => {
              const active = inc.incident_id === selectedId;
              const st = stateStyles(inc.state);
              return (
                <button
                  key={inc.incident_id}
                  type="button"
                  onClick={() => setSelectedId(inc.incident_id)}
                  style={{
                    width: "100%",
                    textAlign: "left",
                    display: "block",
                    padding: "12px 12px",
                    marginBottom: 8,
                    borderRadius: "var(--radius-md)",
                    border: active ? "1px solid var(--primary)" : "1px solid var(--border)",
                    background: active ? "var(--primary-soft)" : "var(--surface-subtle)",
                    color: "var(--text)",
                    cursor: "pointer",
                    boxShadow: active ? "var(--shadow-md)" : "var(--shadow-xs)",
                    transition: "border-color 0.15s ease, box-shadow 0.15s ease, background 0.15s ease"
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "flex-start" }}>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 600 }}>
                      {inc.incident_id}
                    </span>
                    {badge(humanizeState(inc.state), st)}
                  </div>
                  <div style={{ marginTop: 6, fontSize: 13, fontWeight: 600 }}>
                    {inc.metadata.service}
                    <span style={{ color: "var(--text-tertiary)", fontWeight: 500 }}> / </span>
                    <span style={{ fontWeight: 500 }}>{inc.metadata.resource}</span>
                  </div>
                  <div
                    style={{
                      marginTop: 4,
                      fontSize: 12,
                      color: "var(--text-secondary)",
                      lineHeight: 1.35,
                      maxHeight: 36,
                      overflow: "hidden"
                    }}
                  >
                    {inc.metadata.symptom}
                  </div>
                  <div
                    style={{
                      marginTop: 8,
                      display: "flex",
                      flexWrap: "wrap",
                      gap: 6,
                      alignItems: "center"
                    }}
                  >
                    {badge(humanizeSeverity(inc.metadata.severity), severityStyles(inc.metadata.severity))}
                    <span style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
                      v{inc.version}
                      {inc.updated_at ? ` · updated ${formatRelativeTime(inc.updated_at)}` : ""}
                    </span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Detail */}
        <div className="panel-card panel-card--workspace">
          <div className="panel-card__header">
            <div className="panel-card__header-row">
              <div>
                <h2 className="panel-card__title">Inspector</h2>
                <p className="panel-card__hint">Workflow, routing, evidence, and actions for the selected incident.</p>
              </div>
              {selected && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "flex-end" }}>
                  <button
                    type="button"
                    className="btn btn--primary"
                    disabled={routing || loading}
                    onClick={() => {
                      setRouteError(null);
                      setExecuteResult(null);
                      setRouting(true);
                      void routeIncident(selected.incident_id)
                        .then(() => onRefresh())
                        .catch((e: Error) => setRouteError(e.message))
                        .finally(() => setRouting(false));
                    }}
                  >
                    {routing ? "Routing..." : "Run agents (POST /route)"}
                  </button>
                  <button
                    type="button"
                    className="btn btn--secondary"
                    disabled={planning || loading || routing}
                    onClick={() => {
                      setPlanError(null);
                      setExecuteResult(null);
                      setPlanning(true);
                      void planIncident(selected.incident_id)
                        .then(() => onRefresh())
                        .catch((e: Error) => setPlanError(e.message))
                        .finally(() => setPlanning(false));
                    }}
                  >
                    {planning ? "Planning..." : "Create plan (POST /plan)"}
                  </button>
                </div>
              )}
            </div>
            {(routeError || planError) && (
              <p style={{ margin: "10px 0 0", fontSize: 12, color: "var(--danger)" }} role="alert">
                {[routeError, planError].filter(Boolean).join(" ")}
              </p>
            )}
          </div>
          <div className="panel-card__body panel-card__body--padded">
            {!selected && (
              <p style={{ color: "var(--text-secondary)", margin: 0 }}>Select an incident from the list.</p>
            )}
            {selected && (
              <>
                <div style={{ marginBottom: 20 }}>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center", marginBottom: 8 }}>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 18, fontWeight: 700 }}>
                      {selected.incident_id}
                    </span>
                    {badge(humanizeState(selected.state), stateStyles(selected.state))}
                    {badge(humanizeSeverity(selected.metadata.severity), severityStyles(selected.metadata.severity))}
                  </div>
                  <p style={{ color: "var(--text-secondary)", margin: "0 0 12px", fontSize: 13, lineHeight: 1.5 }}>
                    {selected.metadata.symptom}
                  </p>
                  <dl
                    style={{
                      display: "grid",
                      gridTemplateColumns: "140px 1fr",
                      gap: "6px 12px",
                      margin: 0,
                      fontSize: 13
                    }}
                  >
                    <dt style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Service</dt>
                    <dd style={{ margin: 0 }}>{selected.metadata.service}</dd>
                    <dt style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Resource</dt>
                    <dd style={{ margin: 0, wordBreak: "break-word" }}>{selected.metadata.resource}</dd>
                    <dt style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Source</dt>
                    <dd style={{ margin: 0 }}>{selected.metadata.source}</dd>
                    <dt style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Version</dt>
                    <dd style={{ margin: 0 }}>{selected.version}</dd>
                    <dt style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Updated</dt>
                    <dd style={{ margin: 0 }}>
                      {formatDateTime(selected.updated_at)}{" "}
                      {selected.updated_at ? `(${formatRelativeTime(selected.updated_at)})` : ""}
                    </dd>
                    <dt style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Response plan</dt>
                    <dd style={{ margin: 0 }}>
                      {selected.response_plan?.plan_id ?? (
                        <span style={{ color: "var(--text-tertiary)" }}>Not routed yet (call POST /route)</span>
                      )}
                    </dd>
                    {selected.response_plan?.policy_class && (
                      <>
                        <dt style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Policy class</dt>
                        <dd style={{ margin: 0 }}>{selected.response_plan.policy_class}</dd>
                      </>
                    )}
                    {typeof selected.evidence_coverage_score === "number" && (
                      <>
                        <dt style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Evidence coverage</dt>
                        <dd style={{ margin: 0 }}>{(selected.evidence_coverage_score * 100).toFixed(0)}%</dd>
                      </>
                    )}
                    {(selected.blocked_actions?.length ?? 0) > 0 && (
                      <>
                        <dt style={{ color: "var(--text-tertiary)", fontWeight: 500 }}>Blocked actions</dt>
                        <dd style={{ margin: 0 }}>{selected.blocked_actions?.join(", ")}</dd>
                      </>
                    )}
                  </dl>
                </div>

                {selected.state === "waiting_approval" && (
                  <section className="inspector-approval-prompt" aria-label="Human approval">
                    <div className="inspector-approval-prompt__head">
                      <span className="inspector-approval-prompt__badge">Action needed</span>
                      <h3 className="inspector-approval-prompt__title">Waiting for your approval</h3>
                      <p className="inspector-approval-prompt__desc">
                        Review the pending action below, then approve or deny. This posts to the approval API (port
                        8005) using the current incident version.
                      </p>
                    </div>
                    {(() => {
                      const actionId = approvalActionId(selected);
                      if (!actionId) {
                        return (
                          <p className="inspector-approval-prompt__warn" role="alert">
                            This incident is in <strong>waiting_approval</strong> but no action id was returned (no
                            pending graph and no <code className="code-inline">pending_approval_action_id</code>).
                            Refresh the dashboard or verify the incident store payload.
                          </p>
                        );
                      }
                      const act = pickPendingAction(selected);
                      return (
                        <>
                          <label className="inspector-approval-prompt__field">
                            Approver name
                            <input
                              className="form-input"
                              value={approverName}
                              onChange={(e) => setApproverName(e.target.value)}
                              autoComplete="name"
                            />
                          </label>
                          <p className="inspector-approval-prompt__action-line">
                            Action: <code className="code-inline">{actionId}</code>
                            {act ? (
                              <>
                                {" "}
                                ({act.action_type} on {act.target})
                              </>
                            ) : (
                              <span style={{ color: "var(--text-tertiary)" }}>
                                {" "}
                                (plan details not loaded; id from incident record)
                              </span>
                            )}
                          </p>
                          <div className="inspector-approval-prompt__buttons">
                            <button
                              type="button"
                              className="btn btn--primary"
                              disabled={approving}
                              onClick={() => {
                                setApproveError(null);
                                setApproving(true);
                                void submitApproval(selected.incident_id, {
                                  approver: approverName.trim() || "console",
                                  actionId,
                                  approved: true,
                                  expectedIncidentVersion: selected.version,
                                  planStepId: selected.pending_plan_step_id ?? null
                                })
                                  .then(() => onRefresh())
                                  .catch((e: Error) => setApproveError(e.message))
                                  .finally(() => setApproving(false));
                              }}
                            >
                              {approving ? "Submitting..." : "Approve"}
                            </button>
                            <button
                              type="button"
                              className="btn btn--secondary"
                              disabled={approving}
                              onClick={() => {
                                setApproveError(null);
                                setApproving(true);
                                void submitApproval(selected.incident_id, {
                                  approver: approverName.trim() || "console",
                                  actionId,
                                  approved: false,
                                  reason: "denied_from_console",
                                  expectedIncidentVersion: selected.version,
                                  planStepId: selected.pending_plan_step_id ?? null
                                })
                                  .then(() => onRefresh())
                                  .catch((e: Error) => setApproveError(e.message))
                                  .finally(() => setApproving(false));
                              }}
                            >
                              Deny
                            </button>
                          </div>
                        </>
                      );
                    })()}
                    {approveError && (
                      <p className="inspector-approval-prompt__error" role="alert">
                        {approveError}
                      </p>
                    )}
                  </section>
                )}

                {selected.latest_router_decision?.investigate_only &&
                  !selected.pending_action_graph &&
                  selected.state === "investigating" && (
                    <p
                      style={{
                        fontSize: 12,
                        color: "var(--text-secondary)",
                        margin: "0 0 16px",
                        lineHeight: 1.5
                      }}
                    >
                      Latest router decision is investigate-only. Run agents still enriches the incident. Use{" "}
                      <strong>Create plan</strong> when you want a remediation graph; execution stays policy-gated.
                    </p>
                  )}

                {selected.latest_router_decision && (
                  <section style={{ marginBottom: 20 }}>
                    <h3 style={sectionTitle}>Latest router decision</h3>
                    <ul style={{ margin: "0 0 8px", paddingLeft: 18, fontSize: 13, color: "var(--text)" }}>
                      <li>
                        Next workflow:{" "}
                        <code className="code-inline">{selected.latest_router_decision.next_workflow}</code>
                      </li>
                      {selected.latest_router_decision.stop_reason != null && (
                        <li>Stop reason: {String(selected.latest_router_decision.stop_reason)}</li>
                      )}
                      <li>Investigate only: {selected.latest_router_decision.investigate_only ? "yes" : "no"}</li>
                      <li>Confidence: {selected.latest_router_decision.decision_confidence?.toFixed(2) ?? "n/a"}</li>
                    </ul>
                    <details style={{ fontSize: 12 }}>
                      <summary style={{ cursor: "pointer", fontWeight: 600 }}>Raw JSON</summary>
                      <pre className="pre-json" style={{ marginTop: 8 }}>
                        {JSON.stringify(selected.latest_router_decision, null, 2)}
                      </pre>
                    </details>
                  </section>
                )}

                {(selected.decision_records?.length ?? 0) > 0 && (
                  <section style={{ marginBottom: 20 }}>
                    <h3 style={sectionTitle}>Decision history</h3>
                    <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: "0 0 8px" }}>
                      Last {(selected.decision_records ?? []).slice(-8).length} iterations (most recent last).
                    </p>
                    <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                      {(selected.decision_records ?? []).slice(-8).map((dr, idx) => (
                        <li key={dr.record_id ?? idx} style={{ marginBottom: 10 }}>
                          <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>
                            iter {dr.iteration ?? "?"}
                            {dr.step_executed ? ` · step ${dr.step_executed}` : ""}
                          </div>
                          <pre className="pre-json" style={{ margin: "4px 0 0", maxHeight: 160, overflow: "auto" }}>
                            {JSON.stringify(dr.router_decision ?? dr, null, 2)}
                          </pre>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}

                {(selected.hypotheses?.length ?? 0) > 0 && (
                  <section style={{ marginBottom: 20 }}>
                    <h3 style={sectionTitle}>Hypotheses and triage output</h3>
                    <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: "0 0 8px" }}>
                      Structured output from triage and RCA agents (JSON). Expand a row to view; long payloads scroll
                      inside the block.
                    </p>
                    <div className="inspector-hypotheses">
                      {(selected.hypotheses ?? []).map((h, i) => (
                        <details key={i} className="inspector-hypothesis-fold">
                          <summary>
                            <span>
                              Hypothesis {i + 1}
                              <span style={{ fontWeight: 400, color: "var(--text-tertiary)", marginLeft: 8 }}>
                                (triage / RCA)
                              </span>
                            </span>
                          </summary>
                          <pre className="pre-json pre-json--inspector-cap">{JSON.stringify(h, null, 2)}</pre>
                        </details>
                      ))}
                    </div>
                  </section>
                )}

                {(selected.hypothesis_links?.length ?? 0) > 0 && (
                  <section style={{ marginBottom: 20 }}>
                    <h3 style={sectionTitle}>Hypothesis links</h3>
                    <ul style={{ listStyle: "none", padding: 0, margin: 0, fontSize: 13 }}>
                      {(selected.hypothesis_links ?? []).map((hl) => (
                        <li
                          key={hl.hypothesis_id}
                          style={{
                            border: "1px solid var(--border)",
                            borderRadius: "var(--radius-md)",
                            padding: 10,
                            marginBottom: 8,
                            background: "var(--surface-subtle)"
                          }}
                        >
                          <div style={{ fontSize: 12, color: "var(--text-tertiary)" }}>{hl.hypothesis_id}</div>
                          <div style={{ marginTop: 4 }}>{hl.text}</div>
                          <div style={{ fontSize: 12, marginTop: 4, color: "var(--text-secondary)" }}>
                            confidence {(hl.confidence ?? 0).toFixed(2)}
                          </div>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}

                {((selected.execution_trace?.entries?.length ?? 0) > 0) && (
                  <section style={{ marginBottom: 20 }}>
                    <h3 style={sectionTitle}>Execution trace</h3>
                    <ol style={{ margin: 0, paddingLeft: 20, fontSize: 13 }}>
                      {(selected.execution_trace?.entries ?? []).map((e, i) => (
                        <li key={e.trace_id ?? i} style={{ marginBottom: 6 }}>
                          <span style={{ fontWeight: 600 }}>{e.phase}</span>
                          {e.action_id ? (
                            <>
                              {" "}
                              <code className="code-inline">{e.action_id}</code>
                            </>
                          ) : null}
                          {e.message ? ` — ${e.message}` : ""}
                          {typeof e.success === "boolean" ? ` (${e.success ? "ok" : "fail"})` : ""}
                        </li>
                      ))}
                    </ol>
                  </section>
                )}

                {selected.pending_action_graph && (
                  <section style={{ marginBottom: 20 }}>
                    <h3 style={sectionTitle}>Pending remediation plan</h3>
                    <p style={{ fontSize: 13, margin: "0 0 8px" }}>{selected.pending_action_graph.objective}</p>
                    <ul style={{ fontSize: 12, color: "var(--text-secondary)", margin: "0 0 8px", paddingLeft: 18 }}>
                      <li>Blast radius: {selected.pending_action_graph.blast_radius}</li>
                      <li>Success signal: {selected.pending_action_graph.success_signal}</li>
                      <li>
                        Pending action id:{" "}
                        <code className="code-inline">{selected.pending_approval_action_id ?? "n/a"}</code>
                      </li>
                    </ul>
                    <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                      {selected.pending_action_graph.actions.map((a) => (
                        <li
                          key={a.action_id}
                          style={{
                            border: "1px solid var(--border)",
                            padding: 8,
                            marginBottom: 6,
                            borderRadius: "var(--radius-md)",
                            fontSize: 13
                          }}
                        >
                          <code className="code-inline">{a.action_id}</code> · {a.action_type} on {a.target}
                        </li>
                      ))}
                    </ul>
                  </section>
                )}

                {selected.state === "planned" && pickPendingAction(selected) && (
                  <section style={{ marginBottom: 20 }}>
                    <h3 style={sectionTitle}>Execute pending action</h3>
                    <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: "0 0 8px" }}>
                      Calls <code className="code-inline">POST /execute</code> on the router. Policy may require a
                      matching approval record below.
                    </p>
                    {(() => {
                      const act = pickPendingAction(selected)!;
                      const aid = resolveApprovalIdForAction(selected, act.action_id);
                      return (
                        <>
                          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, marginBottom: 8 }}>
                            <input
                              type="checkbox"
                              checked={executeDryRun}
                              onChange={(e) => setExecuteDryRun(e.target.checked)}
                            />
                            Dry run (recommended first)
                          </label>
                          <p style={{ fontSize: 12, margin: "0 0 8px" }}>
                            Action <code className="code-inline">{act.action_id}</code>
                            {aid ? (
                              <>
                                {" "}
                                · approval <code className="code-inline">{aid}</code>
                              </>
                            ) : (
                              <span style={{ color: "var(--text-tertiary)" }}> · no matching approval id yet</span>
                            )}
                          </p>
                          <button
                            type="button"
                            className="btn btn--primary"
                            disabled={executing}
                            onClick={() => {
                              setExecuteError(null);
                              setExecuting(true);
                              void (async () => {
                                try {
                                  const latest = await fetchIncident(selected.incident_id);
                                  const actNow = pickPendingAction(latest);
                                  if (!actNow) {
                                    setExecuteError(
                                      "No pending action on the server. Refresh the dashboard and try again."
                                    );
                                    return;
                                  }
                                  const approvalId = resolveApprovalIdForAction(latest, actNow.action_id);
                                  const result = await executeIncidentAction(latest.incident_id, actNow, {
                                    approvalId,
                                    expectedVersion: latest.version,
                                    dryRun: executeDryRun
                                  });
                                  setExecuteResult(result);
                                  await onRefresh();
                                } catch (e) {
                                  setExecuteError(e instanceof Error ? e.message : String(e));
                                } finally {
                                  setExecuting(false);
                                }
                              })();
                            }}
                          >
                            {executing ? "Executing..." : "Execute"}
                          </button>
                        </>
                      );
                    })()}
                    {executeError && (
                      <p style={{ margin: "8px 0 0", fontSize: 12, color: "var(--danger)" }} role="alert">
                        {executeError}
                      </p>
                    )}
                    {executeResult && (
                      <div style={{ marginTop: 12 }}>
                        <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>Last execute result</div>
                        <pre className="pre-json">{JSON.stringify(executeResult, null, 2)}</pre>
                      </div>
                    )}
                  </section>
                )}

                <section style={{ marginBottom: 20 }}>
                  <h3 style={sectionTitle}>Workflow</h3>
                  <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: "0 0 8px" }}>
                    Steps recorded by the router during processing. Empty until an incident is routed.
                  </p>
                  {(selected.agent_path?.length ?? 0) === 0 ? (
                    <p style={{ color: "var(--text-secondary)", fontSize: 13, margin: 0 }}>
                      No steps yet. Route this incident with{" "}
                      <code className="code-inline">POST /route/{selected.incident_id}</code> on port 8003.
                    </p>
                  ) : (
                    <ol style={{ margin: 0, paddingLeft: 20, color: "var(--text)", fontSize: 13 }}>
                      {selected.agent_path?.map((step, i) => (
                        <li key={i} style={{ marginBottom: 4 }}>
                          {step}
                        </li>
                      ))}
                    </ol>
                  )}
                </section>

                <section style={{ marginBottom: 20 }}>
                  <h3 style={sectionTitle}>Evidence</h3>
                  {(selected.evidence?.length ?? 0) === 0 ? (
                    <p style={{ color: "var(--text-secondary)", fontSize: 13, margin: 0 }}>
                      No evidence items yet. Evidence appears after routing runs the evidence agents.
                    </p>
                  ) : (
                    <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                      {selected.evidence?.map((ev) => (
                        <li
                          key={ev.evidence_id}
                          style={{
                            border: "1px solid var(--border)",
                            borderRadius: "var(--radius-md)",
                            padding: 10,
                            marginBottom: 8,
                            background: "var(--surface-subtle)"
                          }}
                        >
                          <div style={{ fontSize: 12, color: "var(--text-tertiary)", marginBottom: 4 }}>
                            {ev.source} · {ev.kind} · confidence{" "}
                            {(ev.confidence * 100).toFixed(0)}%
                          </div>
                          <div style={{ fontSize: 13 }}>{ev.summary}</div>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>

                <section style={{ marginBottom: 20 }}>
                  <h3 style={sectionTitle}>Executed actions</h3>
                  {(selected.executed_actions?.length ?? 0) === 0 ? (
                    <p style={{ color: "var(--text-secondary)", fontSize: 13, margin: 0 }}>
                      No actions executed yet.
                    </p>
                  ) : (
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                      <thead>
                        <tr style={{ textAlign: "left", color: "var(--text-tertiary)", fontSize: 12 }}>
                          <th style={{ padding: "6px 8px", borderBottom: "1px solid var(--border)" }}>Action</th>
                          <th style={{ padding: "6px 8px", borderBottom: "1px solid var(--border)" }}>Result</th>
                          <th style={{ padding: "6px 8px", borderBottom: "1px solid var(--border)" }}>When</th>
                        </tr>
                      </thead>
                      <tbody>
                        {selected.executed_actions?.map((a) => (
                          <tr key={a.action_id}>
                            <td style={{ padding: "8px", borderBottom: "1px solid var(--border)", verticalAlign: "top" }}>
                              <code style={{ fontSize: 12, fontFamily: "var(--font-mono)" }}>{a.action_id}</code>
                            </td>
                            <td style={{ padding: "8px", borderBottom: "1px solid var(--border)", verticalAlign: "top" }}>
                              <span style={{ color: a.success ? "var(--success)" : "var(--danger)" }}>
                                {a.success ? "success" : "failed"}
                              </span>
                              <div style={{ fontSize: 12, color: "var(--text-secondary)", marginTop: 2 }}>{a.status_message}</div>
                            </td>
                            <td style={{ padding: "8px", borderBottom: "1px solid var(--border)", whiteSpace: "nowrap" }}>
                              {formatDateTime(a.finished_at)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </section>

                <section>
                  <h3 style={sectionTitle}>Approvals</h3>
                  {(selected.approvals?.length ?? 0) === 0 ? (
                    <p style={{ color: "var(--text-secondary)", fontSize: 13, margin: 0 }}>
                      No approval records on this incident.
                    </p>
                  ) : (
                    <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                      {selected.approvals?.map((ap) => (
                        <li
                          key={ap.approval_id}
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            gap: 8,
                            padding: "8px 0",
                            borderBottom: "1px solid var(--border)",
                            fontSize: 13
                          }}
                        >
                          <span>
                            <code style={{ fontSize: 12, fontFamily: "var(--font-mono)" }}>{ap.approval_id}</code> · {ap.approver}
                          </span>
                          <span style={{ color: ap.approved ? "var(--success)" : "var(--danger)" }}>
                            {ap.approved ? "approved" : "denied"}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              </>
            )}
          </div>
        </div>

        {/* Bottom row: activity + metrics */}
        <div className="panel-card" style={{ gridColumn: "1 / -1" }}>
          <div className="panel-card__header" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
            <div>
              <h2 className="panel-card__title">Activity and audit</h2>
              <p className="panel-card__hint">Immutable audit trail. Filter to the selected incident or show all services.</p>
            </div>
            <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, cursor: "pointer", fontWeight: 500, color: "var(--text-secondary)" }}>
              <input
                type="checkbox"
                checked={showAllAudit}
                onChange={(e) => setShowAllAudit(e.target.checked)}
              />
              Show all events
            </label>
          </div>
          <div className="activity-split">
            <div style={{ borderRight: "1px solid var(--border)", maxHeight: 320, overflowY: "auto", padding: 14 }}>
              {timelineEvents.length === 0 && (
                <p style={{ color: "var(--text-secondary)", margin: 0, fontSize: 13 }}>
                  No audit events yet. Routing and actions append events here.
                </p>
              )}
              {timelineEvents.map((ev, idx) => (
                <div
                  key={`${ev.created_at}-${idx}`}
                  style={{
                    borderLeft: "3px solid var(--primary)",
                    paddingLeft: 12,
                    marginBottom: 14,
                    marginLeft: 4
                  }}
                >
                  <div style={{ fontSize: 12, color: "var(--text-tertiary)", marginBottom: 4 }}>
                    {formatDateTime(ev.created_at)} · {formatRelativeTime(ev.created_at)}
                  </div>
                  <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 4 }}>{ev.event_type}</div>
                  <pre className="pre-json">{JSON.stringify(ev.payload, null, 2)}</pre>
                </div>
              ))}
            </div>
            <div style={{ padding: 16, background: "var(--surface-muted)" }}>
              <h3 style={{ ...sectionTitle, marginTop: 0 }}>Replay quality</h3>
              <p style={{ fontSize: 12, color: "var(--text-secondary)", margin: "0 0 8px" }}>
                Offline scoring from the router evaluation dataset (not live incident health).
              </p>
              {score && (
                <ul style={{ listStyle: "none", padding: 0, margin: 0, fontSize: 13 }}>
                  <li style={{ display: "flex", justifyContent: "space-between", padding: "4px 0" }}>
                    <span style={{ color: "var(--text-secondary)" }}>Routing precision</span>
                    <span style={{ fontWeight: 600 }}>{score.routing_precision.toFixed(2)}</span>
                  </li>
                  <li style={{ display: "flex", justifyContent: "space-between", padding: "4px 0" }}>
                    <span style={{ color: "var(--text-secondary)" }}>Evidence completeness</span>
                    <span style={{ fontWeight: 600 }}>{score.evidence_completeness.toFixed(2)}</span>
                  </li>
                  <li style={{ display: "flex", justifyContent: "space-between", padding: "4px 0" }}>
                    <span style={{ color: "var(--text-secondary)" }}>Duplicate call rate</span>
                    <span style={{ fontWeight: 600 }}>{score.duplicate_call_rate.toFixed(2)}</span>
                  </li>
                  <li style={{ display: "flex", justifyContent: "space-between", padding: "4px 0" }}>
                    <span style={{ color: "var(--text-secondary)" }}>Policy violations</span>
                    <span style={{ fontWeight: 600 }}>{score.policy_violations}</span>
                  </li>
                  <li style={{ display: "flex", justifyContent: "space-between", padding: "4px 0" }}>
                    <span style={{ color: "var(--text-secondary)" }}>Action correctness</span>
                    <span style={{ fontWeight: 600 }}>{score.action_correctness.toFixed(2)}</span>
                  </li>
                </ul>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
