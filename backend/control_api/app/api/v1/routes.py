import json
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, Prediction, Rollout, ShadowOutbox
from app.db.session import get_db
from app.schemas.schemas import (
    AdvanceRolloutRequest,
    AuditEventResponse,
    EvaluateResponse,
    MetricsSummaryResponse,
    PredictionRequest,
    PredictionResponse,
    RollbackRequest,
    RolloutStatusResponse,
)
from app.services.decision_engine import evaluate_rollout, execute_advance, execute_rollback
from app.services.feedback import accuracy_summary
from app.services.routing import CANDIDATE_URL, determine_serving_role, forward_prediction

router = APIRouter()


def get_or_create_active_rollout(db: Session) -> Rollout:
    """Retrieves the active rollout configuration or creates a default one if empty."""
    rollout = db.query(Rollout).order_by(Rollout.id.desc()).first()
    if not rollout:
        rollout = Rollout(
            champion_version="models:/wine-classifier/1",
            candidate_version="models:/wine-classifier/2",
            state="READY",
            canary_percentage=0.0,
        )
        db.add(rollout)
        db.commit()
        db.refresh(rollout)
    return rollout


@router.post("/predict", response_model=PredictionResponse)
async def predict(request: PredictionRequest, db: Session = Depends(get_db)):
    """
    Routes an incoming prediction request deterministically to Champion or Candidate.
    Records the prediction, latency, and chosen version in PostgreSQL for auditing.
    """
    rollout = get_or_create_active_rollout(db)
    shadow_enabled = rollout.state == "SHADOW"
    role, target_url = determine_serving_role(request.client_id, rollout)
    selected_version = rollout.candidate_version if role == "candidate" else rollout.champion_version

    result = await forward_prediction(role, target_url, request.features, selected_version)

    pred_id = str(uuid.uuid4())
    db_pred = Prediction(
        id=pred_id,
        client_id=request.client_id,
        selected_version=selected_version,
        selected_role=role,
        prediction=result["prediction"],
        probabilities_json=json.dumps(result.get("probabilities", [])),
        latency_ms=result.get("latency_ms", 1.0),
        status_code=200,
    )
    db.add(db_pred)
    if shadow_enabled:
        db.flush()  # Insert the parent before its outbox FK, without committing.
        db.add(ShadowOutbox(prediction_id=pred_id, payload_json=json.dumps({
            "request_id": pred_id,
            "features": request.features,
            "champion_pred": result["prediction"],
            "candidate_url": CANDIDATE_URL,
        }, allow_nan=False)))
    db.commit()

    return PredictionResponse(
        prediction=result["prediction"],
        probabilities=result.get("probabilities"),
        model_version=selected_version,
        model_role=role,
        latency_ms=result.get("latency_ms", 1.0),
        request_id=pred_id,
    )


@router.get("/rollouts/active", response_model=RolloutStatusResponse)
def get_active_rollout(db: Session = Depends(get_db)):
    """Returns the current active rollout status and canary traffic split."""
    rollout = get_or_create_active_rollout(db)
    return RolloutStatusResponse(
        id=rollout.id,
        champion_version=rollout.champion_version,
        candidate_version=rollout.candidate_version,
        state=rollout.state,
        canary_percentage=rollout.canary_percentage,
        updated_at=rollout.updated_at,
    )


@router.post("/rollouts/advance", response_model=RolloutStatusResponse)
def advance_rollout(request: AdvanceRolloutRequest, db: Session = Depends(get_db)):
    """Advances canary traffic percentage (e.g. 10% -> 25% -> 50% -> 100% PROMOTED)."""
    rollout = get_or_create_active_rollout(db)
    updated = execute_advance(db, rollout, request.canary_percentage)
    return RolloutStatusResponse(
        id=updated.id,
        champion_version=updated.champion_version,
        candidate_version=updated.candidate_version,
        state=updated.state,
        canary_percentage=updated.canary_percentage,
        updated_at=updated.updated_at,
    )


@router.post("/rollouts/rollback", response_model=RolloutStatusResponse)
def rollback_rollout(request: RollbackRequest, db: Session = Depends(get_db)):
    """Instantly reverts candidate traffic back to 0% and logs the reason."""
    rollout = get_or_create_active_rollout(db)
    updated = execute_rollback(db, rollout, reason=request.reason)
    return RolloutStatusResponse(
        id=updated.id,
        champion_version=updated.champion_version,
        candidate_version=updated.candidate_version,
        state=updated.state,
        canary_percentage=updated.canary_percentage,
        updated_at=updated.updated_at,
    )


@router.post("/rollouts/evaluate", response_model=EvaluateResponse)
def evaluate_active_rollout(db: Session = Depends(get_db)):
    """
    Executes the 3-rule deterministic decision engine:
    1. HOLD: <20 candidate requests
    2. ROLLBACK: error rate > 5%, p95 latency > 200ms, or accuracy drop > 5%
    3. PROMOTE: healthy thresholds satisfied
    """
    rollout = get_or_create_active_rollout(db)
    decision, reason, stats = evaluate_rollout(db, rollout)

    if decision == "ROLLBACK":
        execute_rollback(db, rollout, reason=reason, details=stats)
    elif decision == "PROMOTE":
        execute_advance(db, rollout)

    return EvaluateResponse(
        decision=decision,
        reason=reason,
        stats=stats,
        rollout_state=rollout.state,
        canary_percentage=rollout.canary_percentage,
    )


@router.get("/audit", response_model=list[AuditEventResponse])
def get_audit_trail(limit: int = 50, db: Session = Depends(get_db)):
    """Returns append-only audit trail of rollout decisions and stage transitions."""
    events = db.query(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit).all()
    results = []
    for e in events:
        details_parsed = None
        if e.details_json:
            try:
                details_parsed = json.loads(e.details_json)
            except Exception:
                details_parsed = e.details_json
        results.append(
            AuditEventResponse(
                id=e.id,
                timestamp=e.timestamp,
                event_type=e.event_type,
                reason=e.reason,
                details=details_parsed,
            )
        )
    return results


@router.get("/metrics", response_model=MetricsSummaryResponse)
def get_metrics_summary(db: Session = Depends(get_db)):
    """Returns aggregated summary metrics for candidate vs champion."""
    rollout = get_or_create_active_rollout(db)
    all_preds = db.query(Prediction).all()
    cand_preds = [p for p in all_preds if p.selected_role == "candidate"]
    champ_preds = [p for p in all_preds if p.selected_role == "champion"]

    cand_count = len(cand_preds)
    champ_count = len(champ_preds)

    # p95 latency
    cand_latencies = sorted([p.latency_ms for p in cand_preds])
    p95_idx = int(0.95 * len(cand_latencies))
    cand_p95 = cand_latencies[p95_idx] if cand_latencies else 0.0

    # error rate
    cand_errors = sum(1 for p in cand_preds if p.status_code >= 500)
    cand_error_rate = (cand_errors / cand_count) if cand_count > 0 else 0.0

    accuracy = accuracy_summary(db)

    return MetricsSummaryResponse(
        total_predictions=len(all_preds),
        champion_requests=champ_count,
        candidate_requests=cand_count,
        candidate_canary_percentage=rollout.canary_percentage,
        rollout_state=rollout.state,
        candidate_p95_latency_ms=round(cand_p95, 2),
        candidate_error_rate=round(cand_error_rate, 4),
        candidate_accuracy=accuracy["candidate"]["accuracy"],
        champion_accuracy=accuracy["champion"]["accuracy"],
        champion_labeled_count=accuracy["champion"]["total"],
        candidate_labeled_count=accuracy["candidate"]["total"],
    )
