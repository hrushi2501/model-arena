export type RolloutState =
  | "READY"
  | "SHADOW"
  | "CANARY"
  | "PROMOTED"
  | "ROLLED_BACK";

export interface RolloutInfo {
  id: string | number;
  champion_version: string;
  candidate_version: string;
  state: RolloutState;
  canary_percentage: number;
  created_at?: string;
  updated_at?: string;
}

export type AuditEventType =
  | "STAGE_CHANGE"
  | "DECISION"
  | "ROLLBACK"
  | "PROMOTE";

export interface AuditEvent {
  id: number;
  timestamp: string;
  event_type: AuditEventType;
  reason: string;
  details_json?: string;
}

export interface RecentPrediction {
  id: string;
  client_id: string;
  selected_role: "champion" | "candidate";
  selected_version: string;
  prediction: number;
  latency_ms: number;
  status_code: number;
  created_at: string;
}
