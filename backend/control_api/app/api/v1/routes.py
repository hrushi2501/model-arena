import json
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, Feedback, ModelComparison, Prediction, Rollout, ShadowOutbox
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
from app.metrics import CANARY_PERCENTAGE, REQUEST_DURATION_SECONDS, REQUESTS_TOTAL, ROLLBACK_EVENTS_TOTAL
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
    CANARY_PERCENTAGE.set(rollout.canary_percentage)
    return rollout


@router.post("/predict", response_model=PredictionResponse)
async def predict(request: PredictionRequest, db: Session = Depends(get_db)):
    """
    Routes an incoming prediction request deterministically to Champion or Candidate.
    Records the prediction, latency, and chosen version in PostgreSQL for auditing.
    """
    rollout = get_or_create_active_rollout(db)
    shadow_enabled = rollout.state == "SHADOW"
    if request.inject_fault:
        role, target_url = "candidate", CANDIDATE_URL
    else:
        role, target_url = determine_serving_role(request.client_id, rollout)
    selected_version = rollout.candidate_version if role == "candidate" else rollout.champion_version

    try:
        result = await forward_prediction(role, target_url, request.features, selected_version, inject_fault=request.inject_fault)
    except TypeError:
        result = await forward_prediction(role, target_url, request.features, selected_version)

    pred_id = str(uuid.uuid4())
    status_code = result.get("status_code", 200)
    db_pred = Prediction(
        id=pred_id,
        client_id=request.client_id,
        selected_version=selected_version,
        selected_role=role,
        prediction=result["prediction"],
        probabilities_json=json.dumps(result.get("probabilities", [])),
        latency_ms=result.get("latency_ms", 1.0),
        status_code=status_code,
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

    # Record Prometheus metrics for Grafana
    status_label = "500" if result.get("status_code", 200) >= 500 else "200"
    REQUESTS_TOTAL.labels(role=role, status=status_label).inc()
    latency_sec = max(result.get("latency_ms", 1.0) / 1000.0, 0.001)
    REQUEST_DURATION_SECONDS.observe(latency_sec)

    return PredictionResponse(
        prediction=result["prediction"],
        probabilities=result.get("probabilities"),
        model_version=selected_version,
        model_role=role,
        latency_ms=result.get("latency_ms", 1.0),
        request_id=pred_id,
        status_code=status_code,
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
    CANARY_PERCENTAGE.set(updated.canary_percentage)
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
    CANARY_PERCENTAGE.set(0.0)
    ROLLBACK_EVENTS_TOTAL.inc()
    return RolloutStatusResponse(
        id=updated.id,
        champion_version=updated.champion_version,
        candidate_version=updated.candidate_version,
        state=updated.state,
        canary_percentage=updated.canary_percentage,
        updated_at=updated.updated_at,
    )


@router.post("/rollouts/reset", response_model=RolloutStatusResponse)
def reset_rollout(db: Session = Depends(get_db)):
    """Resets the rollout to READY (0% canary) and cleans historical test data for a fresh demo."""
    db.query(Feedback).delete()
    db.query(ModelComparison).delete()
    db.query(ShadowOutbox).delete()
    db.query(Prediction).delete()

    rollout = get_or_create_active_rollout(db)
    rollout.state = "READY"
    rollout.canary_percentage = 0.0
    db.commit()
    db.refresh(rollout)
    CANARY_PERCENTAGE.set(0.0)
    return RolloutStatusResponse(
        id=rollout.id,
        champion_version=rollout.champion_version,
        candidate_version=rollout.candidate_version,
        state=rollout.state,
        canary_percentage=rollout.canary_percentage,
        updated_at=rollout.updated_at,
    )


@router.post("/rollouts/shadow", response_model=RolloutStatusResponse)
def enable_shadow_mode(db: Session = Depends(get_db)):
    """Enables shadow testing mode (0% candidate traffic, 100% champion, background shadow replication via RabbitMQ)."""
    rollout = get_or_create_active_rollout(db)
    rollout.state = "SHADOW"
    rollout.canary_percentage = 0.0
    audit = AuditEvent(
        event_type="STAGE_CHANGE",
        reason="Enabled 100% Shadow Testing mode (asynchronous background replay via RabbitMQ).",
        details_json=json.dumps({"state": "SHADOW", "canary_percentage": 0.0}),
    )
    db.add(audit)
    db.commit()
    db.refresh(rollout)
    CANARY_PERCENTAGE.set(0.0)
    return RolloutStatusResponse(
        id=rollout.id,
        champion_version=rollout.champion_version,
        candidate_version=rollout.candidate_version,
        state=rollout.state,
        canary_percentage=rollout.canary_percentage,
        updated_at=rollout.updated_at,
    )


@router.get("/shadow/summary")
def get_shadow_summary(db: Session = Depends(get_db)):
    """Returns shadow testing comparison statistics between Champion and Candidate."""
    comps = db.query(ModelComparison).all()
    total = len(comps)
    matches = sum(1 for c in comps if c.is_match)
    agreement_rate = (matches / total) if total > 0 else 0.0
    return {
        "total_shadow_evaluations": total,
        "matching_predictions": matches,
        "divergent_predictions": total - matches,
        "agreement_rate": round(agreement_rate, 4),
        "recent_comparisons": [
            {
                "prediction_id": c.prediction_id,
                "champion_pred": c.champion_pred,
                "candidate_pred": c.candidate_pred,
                "is_match": c.is_match,
            }
            for c in comps[-15:]
        ],
    }


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
        CANARY_PERCENTAGE.set(0.0)
        ROLLBACK_EVENTS_TOTAL.inc()
    elif decision == "PROMOTE":
        execute_advance(db, rollout)
        CANARY_PERCENTAGE.set(rollout.canary_percentage)

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


@router.get("/predictions/recent")
def get_recent_predictions(limit: int = 100, db: Session = Depends(get_db)):
    """Returns all recent incoming user prediction requests and their routing destination."""
    preds = db.query(Prediction).order_by(Prediction.created_at.desc()).limit(limit).all()
    return [
        {
            "id": p.id,
            "client_id": p.client_id or "anonymous",
            "selected_role": p.selected_role,
            "selected_version": p.selected_version,
            "prediction": p.prediction,
            "latency_ms": round(p.latency_ms, 1),
            "status_code": p.status_code,
            "created_at": p.created_at.isoformat() if p.created_at else "",
        }
        for p in preds
    ]
