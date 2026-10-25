"use client";

import { useEffect, useState, useCallback } from "react";
import {
  checkApiHealth,
  getActiveRollout,
  getAuditEvents,
  getRecentPredictions,
} from "@/lib/api";
import { RolloutInfo, AuditEvent, RecentPrediction } from "@/lib/types";

const STANDBY_ROLLOUT: RolloutInfo = {
  id: "1",
  champion_version: "models:/wine-classifier/1",
  candidate_version: "models:/wine-classifier/2",
  state: "READY",
  canary_percentage: 0.0,
  updated_at: "2026-10-25T12:00:00Z",
};

function formatISTTime(dateStr: string | null | undefined): string {
  if (!dateStr) return "Just now";

  // Check if it is a full ISO timestamp
  const d = new Date(dateStr);
  if (!isNaN(d.getTime())) {
    return d.toLocaleTimeString("en-US", {
      timeZone: "Asia/Kolkata",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  }

  // Handle bare UTC time strings like "HH:MM:SS"
  const parts = dateStr.split(":");
  if (parts.length === 3) {
    const hours = parseInt(parts[0], 10);
    const minutes = parseInt(parts[1], 10);
    const seconds = parseInt(parts[2], 10);
    if (!isNaN(hours) && !isNaN(minutes) && !isNaN(seconds)) {
      const now = new Date();
      const utcDate = new Date(
        Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), hours, minutes, seconds)
      );
      return utcDate.toLocaleTimeString("en-US", {
        timeZone: "Asia/Kolkata",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    }
  }

  return dateStr;
}

export default function OperatorControlPage() {
  const [mounted, setMounted] = useState<boolean>(false);
  const [isOnline, setIsOnline] = useState<boolean | null>(null);
  const [rollout, setRollout] = useState<RolloutInfo>(STANDBY_ROLLOUT);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [recentPredictions, setRecentPredictions] = useState<RecentPrediction[]>([]);

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
      if (audits) {
        setAuditEvents(audits);
      }
      const preds = await getRecentPredictions();
      if (preds) {
        setRecentPredictions(preds);
      }
    }
  }, []);

  // Silent live auto-refresh every 3 seconds
  useEffect(() => {
    fetchData();
    const interval = setInterval(() => {
      fetchData();
    }, 3000);
    return () => clearInterval(interval);
  }, [fetchData]);

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
      {/* Clean Top Navigation */}
      <nav className="navbar">
        <div className="nav-brand">
          <span style={{ fontSize: "16px", fontWeight: 700 }}>Model Arena</span>
          <span style={{ color: "var(--text-dim)", fontWeight: 400, fontSize: "13px" }}>
            Safe Live Release Operations
          </span>
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
            href="http://localhost:5001"
            target="_blank"
            rel="noreferrer"
            className="nav-link"
          >
            MLflow
          </a>
        </div>
      </nav>

      {/* Top Grid: Active Rollout & Decision Engine Rules */}
      <div className="layout-split" style={{ gridTemplateColumns: "1.3fr 1fr", gap: "20px", marginBottom: "24px" }}>
        {/* Left: Active Rollout & Models */}
        <section className="panel">
          <div className="panel-header">
            <div>
              <h2 className="panel-title">Active Release Rollout</h2>
              <span
                className="mono-cell"
                style={{ fontSize: "11px", color: "var(--text-muted)" }}
                suppressHydrationWarning
              >
                Rollout ID: {String(rollout.id)} • Updated:{" "}
                {mounted ? formatISTTime(rollout.updated_at) : "Active"}
              </span>
            </div>
            <div>{getStatusBadge(rollout.state)}</div>
          </div>

          <div className="panel-body">
            {/* Model Comparison Cards */}
            <div className="model-spec-grid">
              {/* Champion Card */}
              <div className="model-spec-box">
                <div className="model-role-caption" style={{ color: "#6B46C1" }}>
                  ● Champion (Baseline)
                </div>
                <div className="model-heading">RandomForestClassifier</div>
                <div className="model-version-code">
                  URI: {rollout.champion_version}
                </div>
                <div className="model-weight">
                  <span>Production Share</span>
                  <strong style={{ fontSize: "16px", color: "#6B46C1" }}>{championPct}%</strong>
                </div>
              </div>

              {/* Candidate Card */}
              <div className="model-spec-box">
                <div className="model-role-caption" style={{ color: "#2E7D32" }}>
                  ● Candidate (Canary)
                </div>
                <div className="model-heading">GradientBoostingClassifier</div>
                <div className="model-version-code">
                  URI: {rollout.candidate_version}
                </div>
                <div className="model-weight">
                  <span>Production Share</span>
                  <strong style={{ fontSize: "16px", color: "#2E7D32" }}>{candidatePct}%</strong>
                </div>
              </div>
            </div>

            {/* Traffic Split Track */}
            <div className="traffic-track-container" style={{ marginTop: "16px" }}>
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

        {/* Right: Automated Safety Rules & Explanations */}
        <section className="panel">
          <div className="panel-header">
            <h2 className="panel-title">Decision Engine Guardrails</h2>
            <span className="mono-cell" style={{ fontSize: "11px", color: "var(--text-muted)" }}>
              Safety Thresholds
            </span>
          </div>

          <div className="panel-body">
            <ul style={{ paddingLeft: "18px", margin: 0, display: "flex", flexDirection: "column", gap: "10px", fontSize: "12px", lineHeight: "1.5", color: "var(--text-main)" }}>
              <li>
                <strong>Error Rate:</strong> Automatically roll back to Champion if Candidate HTTP error rate exceeds 5%.
              </li>
              <li>
                <strong>P95 Latency:</strong> Automatically roll back if 95% of requests take longer than 200ms.
              </li>
              <li>
                <strong>Model Accuracy:</strong> Automatically roll back if Candidate accuracy drops by more than 5% compared to Champion.
              </li>
              <li>
                <strong>Minimum Requests:</strong> Require at least 20 evaluation requests before advancing traffic or promoting.
              </li>
            </ul>
          </div>
        </section>
      </div>

      {/* Live User Requests Table */}
      <section className="panel" style={{ marginBottom: "24px" }}>
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Live User Requests &amp; Routing</h2>
            <span className="mono-cell" style={{ fontSize: "11px", color: "var(--text-muted)" }}>
              Real-time traffic showing model routing for each client
            </span>
          </div>
          <span className="mono-cell" style={{ fontSize: "11px" }}>
            {recentPredictions.length} requests recorded
          </span>
        </div>

        <div className="table-container" style={{ maxHeight: "380px", overflowY: "auto" }}>
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: "100px" }}>Time</th>
                <th style={{ width: "180px" }}>Client ID</th>
                <th style={{ width: "150px" }}>Routed Model</th>
                <th style={{ width: "220px" }}>Model Version</th>
                <th style={{ width: "110px" }}>Predicted</th>
                <th style={{ width: "120px" }}>Latency</th>
              </tr>
            </thead>
            <tbody>
              {recentPredictions.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: "center", padding: "20px", color: "var(--text-dim)" }}>
                    No predictions recorded yet. Run a demo script to see live user traffic appear here.
                  </td>
                </tr>
              ) : (
                recentPredictions.map((req) => (
                  <tr key={req.id}>
                    <td className="mono-cell" suppressHydrationWarning style={{ fontSize: "11px" }}>
                      {mounted ? formatISTTime(req.created_at) : "Just now"}
                    </td>
                    <td className="mono-cell" style={{ fontWeight: 600 }}>
                      {req.client_id}
                    </td>
                    <td>
                      <span
                        style={{
                          display: "inline-block",
                          padding: "2px 8px",
                          borderRadius: "4px",
                          fontSize: "11px",
                          fontWeight: 600,
                          backgroundColor: req.selected_role === "candidate" ? "#E8F5E9" : "#F3E8FF",
                          color: req.selected_role === "candidate" ? "#2E7D32" : "#6B46C1",
                          border: `1px solid ${req.selected_role === "candidate" ? "#A5D6A7" : "#D8B4FE"}`,
                        }}
                      >
                        {req.selected_role === "candidate" ? "Candidate" : "Champion"}
                      </span>
                    </td>
                    <td className="mono-cell" style={{ fontSize: "11px", color: "var(--text-muted)" }}>
                      {req.selected_version}
                    </td>
                    <td style={{ fontWeight: 600 }}>
                      Class {req.prediction}
                    </td>
                    <td className="mono-cell" style={{ fontSize: "11px" }}>
                      {req.latency_ms} ms
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {/* Audit Log Table */}
      <section className="panel">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Audit Trail &amp; Release Decisions</h2>
            <span className="mono-cell" style={{ fontSize: "11px", color: "var(--text-muted)" }}>
              Append-only compliance log from /api/v1/audit
            </span>
          </div>
          <span className="mono-cell" style={{ fontSize: "11px" }}>{auditEvents.length} records</span>
        </div>

        <div className="table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: "140px" }}>Timestamp</th>
                <th style={{ width: "140px" }}>Event</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              {auditEvents.map((evt) => (
                <tr key={evt.id}>
                  <td className="mono-cell" suppressHydrationWarning style={{ fontSize: "11px" }}>
                    {mounted ? formatISTTime(evt.timestamp) : "12:00:00"}
                  </td>
                  <td>{getEventBadge(evt.event_type)}</td>
                  <td style={{ fontWeight: 500 }}>{evt.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
