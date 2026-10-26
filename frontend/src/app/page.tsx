"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { changeRollout, feedback, getDashboard, predict } from "@/lib/api";
import type { Dashboard, PredictionResult } from "@/lib/types";

const sample = [13.2, 1.78, 2.14, 11.2, 100, 2.65, 2.76, .26, 1.28, 4.38, 1.05, 3.4, 1050];
const percent = (value: number | null) => value === null ? "Awaiting evidence" : `${(value * 100).toFixed(1)}%`;
const time = (value: string | null) => value ? new Date(value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value) ? value : value + "Z").toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata" }) : "—";

function Panel({ title, children, note }: { title: string; children: ReactNode; note?: string }) {
  return <section className="panel"><div className="panel-header"><h2 className="panel-title">{title}</h2>{note && <span className="mono-cell">{note}</span>}</div><div className="panel-body">{children}</div></section>;
}

export default function OperatorControlPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [updated, setUpdated] = useState<string | null>(null);
  const [input, setInput] = useState(JSON.stringify(sample));
  const [client, setClient] = useState("operator");
  const [result, setResult] = useState<PredictionResult | null>(null);
  const [label, setLabel] = useState("");
  const [predictionId, setPredictionId] = useState("");
  const sequence = useRef(0);

  const refresh = useCallback(async () => {
    const requestId = ++sequence.current;
    try {
      const next = await getDashboard();
      if (requestId !== sequence.current) return;
      setData(next); setError(""); setUpdated(new Date().toISOString());
    } catch (cause) {
      if (requestId === sequence.current) setError(cause instanceof Error ? cause.message : "Gateway unavailable");
    }
  }, []);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      await refresh();
      if (!stopped) timer = setTimeout(poll, 3000);
    }
    void poll();
    return () => { stopped = true; clearTimeout(timer); sequence.current++; };
  }, [refresh]);

  async function run(action: () => Promise<void>) {
    setBusy(true); setMessage("");
    try { await action(); await refresh(); }
    catch (cause) { setMessage(cause instanceof Error ? cause.message : "Action failed"); }
    finally { setBusy(false); }
  }

  function rolloutAction(action: Parameters<typeof changeRollout>[0]) {
    void run(async () => {
      const outcome = await changeRollout(action);
      setMessage(outcome.reason || "Release state updated.");
      if (action === "reset") { setResult(null); setLabel(""); setPredictionId(""); }
    });
  }

  const disabled = busy || !data || !!error;
  const rollout = data?.rollout;
  const share = rollout ? Math.round(rollout.canary_percentage * 100) : 0;
  const modelsReady = data?.models.every(model => model.ready) ?? false;

  return <main className="page-container">
    <nav className="navbar"><div className="nav-brand">Model Arena <span className="nav-brand-tag">Release operations</span></div>
      <a className="nav-link" href={process.env.NEXT_PUBLIC_MLFLOW_URL || "http://localhost:5001"} target="_blank" rel="noreferrer">MLflow registry ↗</a>
    </nav>
    <div className="header-strip" role="status"><span>{error ? `Gateway unavailable: ${error}. Showing last received data.` : data ? "Connected through Nginx" : "Connecting to gateway…"}</span><span className="mono-cell">Last received {time(updated)} IST</span></div>
    {message && <p className="feedback-box" role="status">{message}</p>}
    {!data ? <p>{error ? "Start the backend stack and retry." : "Loading live release data…"}</p> : <>
      <div className="layout-split">
        <Panel title="Active release" note={`Evaluation ${data.rollout.id}`}>
          <div className="release-heading"><span className={`status-pill status-pill-${data.rollout.state.toLowerCase()}`}>{data.rollout.state.replaceAll("_", " ")}</span><span className="mono-cell">Updated {time(data.rollout.updated_at)} IST</span></div>
          <div className="model-spec-grid">{data.models.map(model => <div className="model-spec-box" key={model.role}>
            <div className="model-role-caption">{model.role}</div><div className="model-heading">{model.model_type || "Model unavailable"}</div>
            <p className="model-version-code">Expected: {model.expected_version}</p><p className="model-version-code">Loaded: {model.model_version || "Not reported"}</p>
            <strong>{model.ready ? "Ready · identity verified" : "Not ready · check model registration"}</strong>
            <div className="model-weight"><span>Live traffic</span><strong>{model.role === "candidate" ? share : 100 - share}%</strong></div>
          </div>)}</div>
          <div className="traffic-track-bar"><div className="traffic-segment-champion" style={{ width: `${100 - share}%` }} /><div className="traffic-segment-candidate" style={{ width: `${share}%` }} /></div>
          <p className="mono-cell">SHADOW returns Champion results while Candidate is compared asynchronously.</p>
        </Panel>
        <Panel title="Release controls">
          <div className="action-stack">
            <button className="btn btn-subtle" disabled={disabled || !modelsReady || !["READY", "SHADOW"].includes(data.rollout.state)} onClick={() => rolloutAction("shadow")}>Start shadow testing</button>
            <button className="btn btn-primary" disabled={disabled || !modelsReady || !["READY", "SHADOW", "CANARY"].includes(data.rollout.state)} onClick={() => rolloutAction("advance")}>{data.rollout.state === "CANARY" ? "Advance with evidence" : "Start 10% canary probe"}</button>
            <button className="btn btn-subtle" disabled={disabled} onClick={() => rolloutAction("evaluate")}>Evaluate now</button>
            <button className="btn btn-danger" disabled={disabled || ["READY", "ROLLED_BACK"].includes(data.rollout.state)} onClick={() => rolloutAction("rollback")}>Roll back to Champion</button>
            <button className="btn btn-subtle" disabled={disabled} onClick={() => rolloutAction("reset")}>New evaluation · retain history</button>
          </div>
          <div className="policy-box">Automatic checks run every 5 seconds. Each stage requires 20 Candidate requests and 20 genuine labels for each model before advancing. Roll back above 5% errors, p95 above 200 ms, or an accuracy drop over 5 percentage points.</div>
          <p className="mono-cell">Current stage: {data.metrics.stage_candidate_requests}/20 Candidate requests; labels {data.metrics.stage_champion_labeled_count}/20 Champion, {data.metrics.stage_candidate_labeled_count}/20 Candidate.</p>
        </Panel>
      </div>
      <div className="metric-grid" aria-label="Live metrics">
        {[ ["Requests this evaluation", data.metrics.total_predictions], ["Candidate p95", data.metrics.candidate_p95_latency_ms === null ? "Awaiting traffic" : `${data.metrics.candidate_p95_latency_ms.toFixed(1)} ms`], ["Candidate errors", percent(data.metrics.candidate_error_rate)], ["Champion accuracy", percent(data.metrics.champion_accuracy)], ["Candidate accuracy", percent(data.metrics.candidate_accuracy)], ["Awaiting publication", data.shadow.pending_tasks] ].map(([name, value]) => <div className="model-spec-box" key={name}><div className="model-role-caption">{name}</div><strong className="metric-value">{value}</strong></div>)}
      </div>
      <div className="layout-split">
        <Panel title="Try a prediction" note="Wine · 13 features">
          <form onSubmit={event => { event.preventDefault(); void run(async () => {
            const features: unknown = JSON.parse(input);
            if (!Array.isArray(features) || features.length !== 13 || features.some(value => typeof value !== "number" || !Number.isFinite(value))) throw new Error("Enter exactly 13 finite numbers.");
            setResult(null); setLabel(""); setPredictionId("");
            const prediction = await predict(features, client);
            setResult(prediction); setPredictionId(prediction.request_id); setMessage(`Prediction ${prediction.request_id} returned by ${prediction.model_role}.`);
          }); }}>
            <label className="field-label">Client ID<input value={client} onChange={event => setClient(event.target.value)} maxLength={255} /></label>
            <label className="field-label">Features (JSON array)<textarea value={input} onChange={event => setInput(event.target.value)} rows={4} /></label>
            <button className="btn btn-primary" disabled={disabled}>Predict</button>
          </form>
          {result && <div className="feedback-box"><strong>Class {result.prediction}</strong> · {result.model_role} · {result.latency_ms.toFixed(1)} ms<br /><span className="model-version-code">{result.model_version}<br />{result.request_id}</span></div>}
        </Panel>
        <Panel title="Delayed ground-truth feedback">
          <p>Submit the known label for a prediction ID. Select it from your source data; the model prediction is not ground truth.</p>
          <form onSubmit={event => { event.preventDefault(); if (!predictionId.trim() || label === "") return; void run(async () => { await feedback(predictionId.trim(), Number(label)); setMessage("Ground-truth label recorded."); }); }}>
            <label className="field-label">Prediction ID<input value={predictionId} onChange={event => setPredictionId(event.target.value)} maxLength={64} required /></label>
            <label className="field-label">Known class<select value={label} onChange={event => setLabel(event.target.value)}><option value="">Select known label</option>{[0, 1, 2].map(value => <option key={value} value={value}>Class {value}</option>)}</select></label>
            <button className="btn btn-primary" disabled={disabled || !predictionId.trim() || label === ""}>Submit feedback</button>
          </form>
          <p className="mono-cell">Labeled evidence: {data.metrics.champion_labeled_count} Champion, {data.metrics.candidate_labeled_count} Candidate. Missing labels stay unknown.</p>
        </Panel>
      </div>
      <Panel title="Shadow comparisons" note={`${data.shadow.total_shadow_evaluations} completed · ${percent(data.shadow.agreement_rate)} agreement`}>
        <p>{data.shadow.matching_predictions} matching · {data.shadow.divergent_predictions} divergent. Agreement measures consistency; accuracy requires labels.</p>
        <div className="table-container"><table className="data-table"><thead><tr><th>Prediction ID</th><th>Champion</th><th>Candidate</th><th>Comparison</th></tr></thead><tbody>{data.shadow.recent_comparisons.map(item => <tr key={item.prediction_id}><td className="mono-cell">{item.prediction_id}</td><td>{item.champion_pred}</td><td>{item.candidate_pred}</td><td>{item.is_match ? "Match" : "Divergent"}</td></tr>)}</tbody></table></div>
        {!data.shadow.total_shadow_evaluations && <p className="mono-cell">No completed shadow comparisons in this evaluation.</p>}
      </Panel>
      <Panel title="Live requests" note={`${data.predictions.length} recent requests`}>
        <div className="table-container"><table className="data-table"><thead><tr><th>Time (IST)</th><th>Client</th><th>Model</th><th>Version</th><th>Prediction</th><th>Latency</th><th>Status</th></tr></thead><tbody>{data.predictions.map(item => <tr key={item.id}><td>{time(item.created_at)}</td><td>{item.client_id}</td><td>{item.selected_role}</td><td className="mono-cell">{item.selected_version}</td><td>{item.prediction === null ? "Unavailable" : `Class ${item.prediction}`}</td><td>{item.latency_ms.toFixed(1)} ms</td><td>{item.status_code}</td></tr>)}</tbody></table></div>
        {!data.predictions.length && <p className="mono-cell">No requests in this evaluation.</p>}
      </Panel>
      <Panel title="Audit trail"><div className="table-container"><table className="data-table"><thead><tr><th>Time (IST)</th><th>Event</th><th>Reason</th></tr></thead><tbody>{data.audit.map(item => <tr key={item.id}><td>{time(item.timestamp)}</td><td>{item.event_type}</td><td>{item.reason}</td></tr>)}</tbody></table></div></Panel>
    </>}
  </main>;
}
