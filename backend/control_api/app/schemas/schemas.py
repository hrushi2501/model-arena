from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, FiniteFloat


class PredictionRequest(BaseModel):
    features: list[FiniteFloat] = Field(..., min_length=13, max_length=13)
    client_id: str | None = Field(
        None, description="Optional unique client ID for deterministic canary routing"
    )
    inject_fault: bool = Field(
        False, description="Simulate an inference failure on the model server"
    )


class PredictionResponse(BaseModel):
    prediction: int | None
    probabilities: list[float] | None = None
    model_version: str
    model_role: str  # champion or candidate
    latency_ms: float
    request_id: str
    status_code: int = 200
    error: str | None = None


class RolloutStatusResponse(BaseModel):
    id: int
    champion_version: str
    candidate_version: str
    state: str
    canary_percentage: float
    updated_at: datetime | None = None


class AdvanceRolloutRequest(BaseModel):
    canary_percentage: float | None = Field(
        None, ge=0.0, le=1.0, description="Optional explicit percentage step (e.g. 0.25)"
    )


class RollbackRequest(BaseModel):
    reason: str = Field(
        "Manual emergency rollback", description="Reason for triggering the rollback"
    )


class FeedbackRequest(BaseModel):
    prediction_id: str = Field(min_length=1, max_length=64)
    ground_truth_label: int = Field(strict=True, ge=0, le=2)


class AuditEventResponse(BaseModel):
    id: int
    timestamp: datetime
    event_type: str
    reason: str
    details: Any = None


class EvaluateResponse(BaseModel):
    decision: str  # HOLD, ROLLBACK, PROMOTE
    reason: str
    stats: dict[str, Any]
    rollout_state: str
    canary_percentage: float


class MetricsSummaryResponse(BaseModel):
    total_predictions: int
    champion_requests: int
    candidate_requests: int
    candidate_canary_percentage: float
    rollout_state: str
    candidate_p95_latency_ms: float | None
    candidate_error_rate: float | None
    candidate_accuracy: float | None
    champion_accuracy: float | None
    champion_labeled_count: int = 0
    candidate_labeled_count: int = 0
    stage_candidate_requests: int = 0
    stage_champion_labeled_count: int = 0
    stage_candidate_labeled_count: int = 0
