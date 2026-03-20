import { useCallback, useEffect, useMemo, useState } from "react";
import { loadDashboard } from "./api";
import { IncidentWorkspace } from "./components/IncidentWorkspace";
import "./index.css";
import { DashboardLoad, IncidentRecord } from "./types";

function IconIncidents(): JSX.Element {
  return (
    <svg className="sidebar__link-icon" viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        d="M4 5.5h6a1.5 1.5 0 011.5 1.5v5A1.5 1.5 0 0110 13.5H4A1.5 1.5 0 012.5 12V7A1.5 1.5 0 014 5.5zm10 0h6A1.5 1.5 0 0121.5 7v5a1.5 1.5 0 01-1.5 1.5h-6A1.5 1.5 0 0112.5 12V7A1.5 1.5 0 0114 5.5zM4 15.5h6a1.5 1.5 0 011.5 1.5v3A1.5 1.5 0 0110 21.5H4A1.5 1.5 0 012.5 20v-3A1.5 1.5 0 014 15.5zm10 0h6a1.5 1.5 0 011.5 1.5v3a1.5 1.5 0 01-1.5 1.5h-6a1.5 1.5 0 01-1.5-1.5v-3a1.5 1.5 0 011.5-1.5z"
      />
    </svg>
  );
}

function IconMetricTotal(): JSX.Element {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        d="M4 4h4v16H4V4zm6 4h4v12h-4V8zm6-6h4v18h-4V2z"
      />
    </svg>
  );
}

function IconMetricOpen(): JSX.Element {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"
      />
    </svg>
  );
}

function IconMetricActive(): JSX.Element {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        d="M13 3c-4.97 0-9 4.03-9 9H1l3.89 3.89.07.14L9 12H6c0-3.87 3.13-7 7-7s7 3.13 7 7-3.13 7-7 7c-1.93 0-3.68-.79-4.94-2.06l-1.42 1.42C8.27 19.99 10.51 21 13 21c4.97 0 9-4.03 9-9s-4.03-9-9-9zm-1 5v5l4.28 2.54.72-1.21-3.5-2.08V8H12z"
      />
    </svg>
  );
}

function IconMetricApproval(): JSX.Element {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true">
      <path
        fill="currentColor"
        d="M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm-2 16l-3.5-3.5 1.41-1.41L10 14.17l6.18-6.18L17.5 9L10 16.5z"
      />
    </svg>
  );
}

function computeIncidentStats(incidents: IncidentRecord[]): {
  total: number;
  open: number;
  inProgress: number;
  awaitingApproval: number;
} {
  let open = 0;
  let inProgress = 0;
  let awaitingApproval = 0;
  for (const inc of incidents) {
    const s = inc.state.toLowerCase();
    if (s === "open" || s === "reopened") {
      open++;
    } else if (s === "waiting_approval") {
      awaitingApproval++;
    } else if (s === "investigating" || s === "executing" || s === "planned") {
      inProgress++;
    }
  }
  return { total: incidents.length, open, inProgress, awaitingApproval };
}

export function App(): JSX.Element {
  const [data, setData] = useState<DashboardLoad>({
    incidents: [],
    auditEvents: [],
    score: null,
    loadErrors: []
  });
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (): Promise<void> => {
    setError(null);
    setLoading(true);
    try {
      const next = await loadDashboard();
      setData(next);
      if (next.loadErrors.length > 0) {
        setError(next.loadErrors.join(" "));
      }
    } catch {
      setError("Failed to load dashboard data.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const interval = window.setInterval(() => {
      void refresh();
    }, 10000);
    return () => window.clearInterval(interval);
  }, [refresh]);

  const stats = useMemo(() => computeIncidentStats(data.incidents), [data.incidents]);

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary">
        <div className="sidebar__brand">
          <div className="sidebar__logo" aria-hidden="true" />
          <div>
            <div className="sidebar__title">SRE Console</div>
            <div className="sidebar__subtitle">On-prem control plane</div>
          </div>
        </div>
        <nav className="sidebar__nav">
          <button type="button" className="sidebar__link sidebar__link--active" aria-current="page">
            <IconIncidents />
            Incidents
          </button>
        </nav>
        <div className="sidebar__footer">
          <details className="sidebar__help">
            <summary>Agent setup</summary>
            <div className="sidebar__help-body">
              On the server, set <code>AGENTIC_ENABLED=true</code> and a compatible <code>LLM_BASE_URL</code> (see
              README). This console calls <code>POST /route</code> to run agents.
            </div>
          </details>
        </div>
      </aside>

      <div className="app-main">
        <header className="topbar">
          <div>
            <p className="breadcrumb">Dashboard / Incidents</p>
            <h1 className="topbar__title">Incident monitoring</h1>
            <p className="topbar__desc">
              Track routing, workflow steps, evidence, and audit in one place. Data syncs every 10 seconds.
            </p>
          </div>
          <div className="topbar__actions">
            {loading && (
              <span
                style={{
                  fontSize: 12,
                  fontWeight: 600,
                  color: "var(--text-tertiary)",
                  padding: "8px 12px",
                  background: "var(--surface)",
                  borderRadius: "var(--radius-pill)",
                  border: "1px solid var(--border)"
                }}
              >
                Syncing...
              </span>
            )}
            <button type="button" className="btn btn--secondary" onClick={() => void refresh()} disabled={loading}>
              {loading ? "Refreshing..." : "Refresh now"}
            </button>
          </div>
        </header>

        <section className="metric-strip" aria-label="Incident summary">
          <div className="metric-card">
            <div className="metric-card__icon metric-card__icon--total" aria-hidden="true">
              <IconMetricTotal />
            </div>
            <div>
              <p className="metric-card__label">Total incidents</p>
              <p className="metric-card__value">{stats.total}</p>
              <p className="metric-card__hint">All records in the queue</p>
            </div>
          </div>
          <div className="metric-card">
            <div className="metric-card__icon metric-card__icon--open" aria-hidden="true">
              <IconMetricOpen />
            </div>
            <div>
              <p className="metric-card__label">Open</p>
              <p className="metric-card__value">{stats.open}</p>
              <p className="metric-card__hint">Not yet triaged</p>
            </div>
          </div>
          <div className="metric-card">
            <div className="metric-card__icon metric-card__icon--active" aria-hidden="true">
              <IconMetricActive />
            </div>
            <div>
              <p className="metric-card__label">In progress</p>
              <p className="metric-card__value">{stats.inProgress}</p>
              <p className="metric-card__hint">Routing, planning, or executing</p>
            </div>
          </div>
          <div className="metric-card">
            <div className="metric-card__icon metric-card__icon--approval" aria-hidden="true">
              <IconMetricApproval />
            </div>
            <div>
              <p className="metric-card__label">Awaiting approval</p>
              <p className="metric-card__value">{stats.awaitingApproval}</p>
              <p className="metric-card__hint">Needs human sign-off</p>
            </div>
          </div>
        </section>

        {error && (
          <div className="alert-banner" role="alert">
            {error}
          </div>
        )}

        <div className="app-main__body">
          <IncidentWorkspace
            incidents={data.incidents}
            auditEvents={data.auditEvents}
            score={data.score}
            loading={loading}
            onRefresh={() => {
              void refresh();
            }}
          />
        </div>
      </div>
    </div>
  );
}
