export type RolloutState = "READY" | "SHADOW" | "CANARY" | "PROMOTED" | "ROLLED_BACK";
export interface RolloutInfo {
  id: number; champion_version: string; candidate_version: string;
  state: RolloutState; canary_percentage: number; updated_at: string | null;
}
export interface AuditEvent {
  id: number; timestamp: string; event_type: string; reason: string; details?: unknown;
}
export interface RecentPrediction {
  id: string; client_id: string; selected_role: "champion" | "candidate";
  selected_version: string; prediction: number | null; latency_ms: number;
  status_code: number; created_at: string;
}
export interface PredictionResult {
  request_id: string; prediction: number | null; model_role: string;
  model_version: string; latency_ms: number; status_code: number; error: string | null;
}
export interface Metrics {
  total_predictions: number; champion_requests: number; candidate_requests: number;
  candidate_p95_latency_ms: number | null; candidate_error_rate: number | null;
  candidate_accuracy: number | null; champion_accuracy: number | null;
  champion_labeled_count: number; candidate_labeled_count: number;
  stage_candidate_requests: number; stage_champion_labeled_count: number;
  stage_candidate_labeled_count: number;
}
export interface Shadow {
  total_shadow_evaluations: number; matching_predictions: number; divergent_predictions: number;
  agreement_rate: number | null; pending_tasks: number;
  recent_comparisons: { prediction_id: string; champion_pred: number; candidate_pred: number; is_match: boolean }[];
}
export interface ModelStatus {
  role: "champion" | "candidate"; expected_version: string; ready: boolean;
  model_version: string | null; model_type: string | null;
}
export interface Dashboard {
  rollout: RolloutInfo; metrics: Metrics; shadow: Shadow;
  audit: AuditEvent[]; predictions: RecentPrediction[]; models: ModelStatus[];
}
