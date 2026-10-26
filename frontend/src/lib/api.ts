import type { Dashboard, PredictionResult, RolloutInfo } from "./types";

export class ApiError extends Error {
  constructor(message: string, readonly status: number) { super(message); }
}

async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    method: body === undefined ? "GET" : "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    cache: "no-store", signal: AbortSignal.timeout(5000),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = typeof data?.detail === "string" ? data.detail : data?.error;
    throw new ApiError(detail || `Request failed (HTTP ${response.status})`, response.status);
  }
  return data as T;
}

export async function getDashboard(): Promise<Dashboard> {
  const [rollout, metrics, shadow, audit, predictions, models] = await Promise.all([
    request<Dashboard["rollout"]>("/rollouts/active"), request<Dashboard["metrics"]>("/metrics"),
    request<Dashboard["shadow"]>("/shadow/summary"), request<Dashboard["audit"]>("/audit"),
    request<Dashboard["predictions"]>("/predictions/recent"), request<Dashboard["models"]>("/models"),
  ]);
  return { rollout, metrics, shadow, audit, predictions, models };
}

export const changeRollout = (action: "shadow" | "advance" | "rollback" | "reset" | "evaluate") =>
  request<RolloutInfo & { decision?: string; reason?: string }>(`/rollouts/${action}`,
    action === "rollback" ? { reason: "Manual operator rollback" } : {});

export const predict = (features: number[], client_id: string) =>
  request<PredictionResult>("/predict", { features, client_id });

export const feedback = (prediction_id: string, ground_truth_label: number) =>
  request("/feedback", { prediction_id, ground_truth_label });
