"use client";

import { useEffect, useState, useCallback } from "react";
import {
  checkApiHealth,
  getActiveRollout,
  advanceRollout,
  rollbackRollout,
  getAuditEvents,
} from "@/lib/api";
import { RolloutInfo, AuditEvent } from "@/lib/types";

const STANDBY_ROLLOUT: RolloutInfo = {
  id: "rollout-default",
  champion_version: "wine-classifier:1",
  candidate_version: "wine-classifier:2",
  state: "READY",
  canary_percentage: 0.0,
  updated_at: "2026-10-25T12:00:00Z",
};

const SAMPLE_AUDIT: AuditEvent[] = [
  {
    id: 1,
    timestamp: "2026-10-25T12:00:00Z",
    event_type: "STAGE_CHANGE",
    reason: "Rollout initialized in READY state",
    details_json: JSON.stringify({
      champion: "wine-classifier:1",
      candidate: "wine-classifier:2",
    }),
  },
];

export default function OperatorControlPage() {
  const [mounted, setMounted] = useState<boolean>(false);
  const [isOnline, setIsOnline] = useState<boolean | null>(null);
  const [rollout, setRollout] = useState<RolloutInfo>(STANDBY_ROLLOUT);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>(SAMPLE_AUDIT);
  const [loadingAction, setLoadingAction] = useState<string | null>(null);
  const [actionFeedback, setActionFeedback] = useState<{
    text: string;
    isError: boolean;
  } | null>(null);
  const [autoRefresh, setAutoRefresh] = useState<boolean>(true);

  useEffect(() => {
    setMounted(true);
  }, []);

  const fetchData = useCallback(async () => {
    const online = await checkApiHealth();
    setIsOnline(online);

    if (online) {
      const active = await getActiveRollout();
      if (active) {
        setRollout(active);
      }
      const audits = await getAuditEvents();
      if (audits && audits.length > 0) {
        setAuditEvents(audits);
      }
    }
  }, []);

  useEffect(() => {
    fetchData();
    if (!autoRefresh) return;

    const interval = setInterval(() => {
      fetchData();
    }, 4000);

    return () => clearInterval(interval);
  }, [fetchData, autoRefresh]);

  const handleAdvance = async () => {
    setLoadingAction("advance");
    setActionFeedback(null);
    const result = await advanceRollout();
    setLoadingAction(null);
    setActionFeedback({
      text: result.message,
      isError: !result.success,
    });
    fetchData();
  };

  const handleRollback = async () => {
    setLoadingAction("rollback");
    setActionFeedback(null);
    const result = await rollbackRollout("Manual operator intervention");
    setLoadingAction(null);
    setActionFeedback({
      text: result.message,
      isError: !result.success,
    });
    fetchData();
  };

  const championPct = Math.round((1 - rollout.canary_percentage) * 100);
  const candidatePct = Math.round(rollout.canary_percentage * 100);

  const getStatusBadge = (state: string) => {
    const label =
      state === "CANARY"
        ? `CANARY ${candidatePct}%`
        : state.replace("_", " ");

    const className = `status-pill status-pill-${state.toLowerCase()}`;
    return <span className={className}>{label}</span>;
  };

  const getEventBadge = (type: string) => {
    let cls = "event-stage";
    if (type === "ROLLBACK") cls = "event-rollback";
    else if (type === "PROMOTE") cls = "event-promote";
    else if (type === "DECISION") cls = "event-decision";

    return <span className={`event-label ${cls}`}>{type}</span>;
  };

  return (
    <div className="page-container">
      {/* Top Navigation */}
      <nav className="navbar">
        <div className="nav-brand">
          <span>Model Arena</span>
        </div>

        <div className="nav-links">
          <a
            href="http://localhost:3001"
            target="_blank"
            rel="noreferrer"
            className="nav-link"
          >
            Grafana
          </a>
          <a
            href="http://localhost:9090"
            target="_blank"
            rel="noreferrer"
            className="nav-link"
          >
            Prometheus
          </a>
          <a
            href="http://localhost:5000"
            target="_blank"
            rel="noreferrer"
            className="nav-link"
          >
            MLflow
          </a>
          <span className="nav-brand-tag">LOCAL</span>
        </div>
      </nav>

      {/* Status Bar */}
      <div className="header-strip">
        <div className="system-status">
          <span
            className={`status-dot ${
              isOnline ? "status-dot-active" : "status-dot-standby"
            }`}
          />
          <span>
            Control Gateway:{" "}
            <strong style={{ color: "var(--text-main)" }}>
              {isOnline === null
                ? "Connecting..."
                : isOnline
                ? "Active (http://localhost:8080)"
                : "Standby / Offline"}
            </strong>
          </span>
        </div>

        <div className="header-tools">
          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
            />
            <span>Auto-poll (4s)</span>
          </label>
          <button
            onClick={() => fetchData()}
            className="btn btn-subtle"
            style={{ padding: "3px 8px", fontSize: "11px" }}
          >
            Refresh
          </button>
        </div>
      </div>

      {/* Layout Split: Overview & Controls */}
      <div className="layout-split">
        {/* Left Panel: Active Rollout & Models */}
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2 className="panel-title">Active Release Rollout</h2>
              <span
                className="mono-cell"
                style={{ fontSize: "11px" }}
                suppressHydrationWarning
              >
                ID: {String(rollout.id)} • Last checked:{" "}
                {mounted && rollout.updated_at
                  ? new Date(rollout.updated_at).toLocaleTimeString()
                  : "Standby"}
              </span>
            </div>
            <div>{getStatusBadge(rollout.state)}</div>
          </div>

          <div className="panel-body">
            {/* Model Comparison Grid */}
            <div className="model-spec-grid">
              {/* Champion Card */}
              <div className="model-spec-box">
                <div className="model-role-caption">Champion Role</div>
                <div className="model-heading">RandomForestClassifier</div>
                <div className="model-version-code">
                  URI: {rollout.champion_version}
                </div>
                <div className="model-weight">
                  <span>Current share</span>
                  <strong>{championPct}%</strong>
                </div>
              </div>

              {/* Candidate Card */}
              <div className="model-spec-box">
                <div className="model-role-caption">Candidate Role</div>
                <div className="model-heading">GradientBoostingClassifier</div>
                <div className="model-version-code">
                  URI: {rollout.candidate_version}
                </div>
                <div className="model-weight">
                  <span>Current share</span>
                  <strong>{candidatePct}%</strong>
                </div>
              </div>
            </div>

            {/* Linear Split Track */}
            <div className="traffic-track-container">
              <div className="traffic-track-header">
                <span>Champion ({championPct}%)</span>
                <span>Candidate ({candidatePct}%)</span>
              </div>
              <div className="traffic-track-bar">
                <div
                  className="traffic-segment-champion"
                  style={{ width: `${championPct}%` }}
                />
                <div
                  className="traffic-segment-candidate"
                  style={{ width: `${candidatePct}%` }}
                />
              </div>
            </div>
          </div>
        </section>

        {/* Right Panel: Manual Operator Actions */}
        <section className="panel">
          <div className="panel-header">
            <h2 className="panel-title">Release Controls</h2>
            <span className="mono-cell" style={{ fontSize: "11px" }}>
              Manual Override
            </span>
          </div>

          <div className="panel-body">
            <div className="action-stack">
              <button
                onClick={handleAdvance}
                disabled={loadingAction !== null || rollout.state === "PROMOTED"}
                className="btn btn-primary"
              >
                {loadingAction === "advance"
                  ? "Advancing..."
                  : rollout.state === "READY"
                  ? "Start Shadow Testing"
                  : rollout.state === "SHADOW"
                  ? "Begin Canary (10%)"
                  : rollout.state === "CANARY" && candidatePct < 50
                  ? "Advance Canary (50%)"
                  : rollout.state === "CANARY"
                  ? "Promote Candidate (100%)"
                  : "Advance Rollout"}
              </button>

              <button
                onClick={handleRollback}
                disabled={
                  loadingAction !== null || rollout.state === "ROLLED_BACK"
                }
                className="btn btn-danger"
              >
                {loadingAction === "rollback"
                  ? "Executing rollback..."
                  : "Trigger Emergency Rollback"}
              </button>

              {actionFeedback && (
                <div
                  className={`feedback-box ${
                    actionFeedback.isError ? "feedback-err" : "feedback-ok"
                  }`}
                >
                  {actionFeedback.text}
                </div>
              )}
            </div>

            <div className="policy-box">
              <div className="policy-box-title">Automated Safety Rules</div>
              <ul className="policy-list">
                <li>Rollback if HTTP error rate exceeds 5%</li>
                <li>Rollback if p95 latency exceeds 200ms</li>
                <li>Promotion requires minimum 20 evaluation requests</li>
              </ul>
            </div>
          </div>
        </section>
      </div>

      {/* Audit Log Table */}
      <section className="panel">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Audit Trail &amp; Release Decisions</h2>
            <span className="mono-cell" style={{ fontSize: "11px" }}>
              Synchronized events from /api/v1/audit
            </span>
          </div>
          <span className="mono-cell">{auditEvents.length} records</span>
        </div>

        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: "130px" }}>Timestamp</th>
                <th style={{ width: "120px" }}>Event</th>
                <th>Reason</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {auditEvents.map((evt) => (
                <tr key={evt.id}>
                  <td className="mono-cell" suppressHydrationWarning>
                    {mounted
                      ? new Date(evt.timestamp).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                          second: "2-digit",
                        })
                      : "12:00:00"}
                  </td>
                  <td>{getEventBadge(evt.event_type)}</td>
                  <td>{evt.reason}</td>
                  <td
                    className="mono-cell"
                    style={{
                      maxWidth: "360px",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {typeof evt.details_json === "string"
                      ? evt.details_json
                      : JSON.stringify(evt.details_json || {})}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Sober Footer */}
      <footer className="footer">
        <span>Model Arena • Safe Live Release System</span>
        <span>Metrics scraped via Prometheus :9090 • Provisioned in Grafana :3001</span>
      </footer>
    </div>
  );
}
