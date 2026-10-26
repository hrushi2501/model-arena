import asyncio
import json
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import Integer, cast, func
from sqlalchemy.orm import Session

from app.db.models import AuditEvent, ModelComparison, Prediction, Rollout, ShadowOutbox
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
from app.services.decision_engine import (
    advance_safely,
    apply_evaluation,
    execute_rollback,
    get_or_create_active_rollout,
)
from app.services.evidence import collect_evidence, prediction_query
from app.services.routing import (
    CANDIDATE_URL,
    CHAMPION_URL,
    determine_serving_role,
    forward_prediction,
    model_status,
)
from app.settings import demo_faults_enabled

router = APIRouter()


def status(rollout):
    return RolloutStatusResponse.model_validate(rollout, from_attributes=True)


async def models(rollout):
    return await asyncio.gather(
        model_status("champion", CHAMPION_URL, rollout.champion_version),
        model_status("candidate", CANDIDATE_URL, rollout.candidate_version),
    )


async def require_models(rollout):
    if not all(m["ready"] for m in await models(rollout)):
        raise HTTPException(503, "Both configured model versions must be ready")


@router.post("/predict", response_model=PredictionResponse)
async def predict(
    request: PredictionRequest, response: Response, db: Annotated[Session, Depends(get_db)]
):
    rollout = get_or_create_active_rollout(db)
    shadow = rollout.state == "SHADOW"
    prediction_id = str(uuid.uuid4())
    role, url = determine_serving_role(request.client_id or prediction_id, rollout)
    version = rollout.candidate_version if role == "candidate" else rollout.champion_version
    if request.inject_fault:
        if not demo_faults_enabled():
            raise HTTPException(403, "Demo faults are disabled")
        if role != "candidate" or rollout.state != "CANARY":
            raise HTTPException(409, "Demo faults require a naturally routed Candidate in CANARY")
    result = await forward_prediction(
        role, url, request.features, version, inject_fault=request.inject_fault
    )
    code = result.get("status_code", 200)
    db.add(
        Prediction(
            id=prediction_id,
            client_id=request.client_id,
            selected_version=version,
            selected_role=role,
            prediction=result["prediction"],
            probabilities_json=json.dumps(result.get("probabilities")),
            latency_ms=result.get("latency_ms", 0),
            status_code=code,
        )
    )
    if shadow and code == 200:
        db.flush()
        db.add(
            ShadowOutbox(
                prediction_id=prediction_id,
                payload_json=json.dumps(
                    {
                        "request_id": prediction_id,
                        "features": request.features,
                        "champion_pred": result["prediction"],
                        "candidate_url": CANDIDATE_URL,
                        "candidate_version": rollout.candidate_version,
                    },
                    allow_nan=False,
                ),
            )
        )
    db.commit()
    response.status_code = code
    return PredictionResponse(
        prediction=result["prediction"],
        probabilities=result.get("probabilities"),
        model_version=version,
        model_role=role,
        latency_ms=result.get("latency_ms", 0),
        request_id=prediction_id,
        status_code=code,
        error=result.get("error"),
    )


@router.get("/rollouts/active", response_model=RolloutStatusResponse)
def active(db: Annotated[Session, Depends(get_db)]):
    return status(get_or_create_active_rollout(db))


@router.get("/models")
async def get_models(db: Annotated[Session, Depends(get_db)]):
    return await models(get_or_create_active_rollout(db))


@router.post("/rollouts/advance", response_model=RolloutStatusResponse)
async def advance(
    db: Annotated[Session, Depends(get_db)], request: AdvanceRolloutRequest | None = None
):
    rollout = get_or_create_active_rollout(db, lock=True)
    await require_models(rollout)
    return status(advance_safely(db, rollout, request.canary_percentage if request else None))


@router.post("/rollouts/rollback", response_model=RolloutStatusResponse)
def rollback(request: RollbackRequest, db: Annotated[Session, Depends(get_db)]):
    return status(execute_rollback(db, get_or_create_active_rollout(db, lock=True), request.reason))


@router.post("/rollouts/reset", response_model=RolloutStatusResponse)
def new_evaluation(db: Annotated[Session, Depends(get_db)]):
    previous = get_or_create_active_rollout(db, lock=True)
    rollout = Rollout(
        champion_version=previous.champion_version, candidate_version=previous.candidate_version
    )
    db.add(rollout)
    db.add(
        AuditEvent(
            event_type="RESET", reason="Started a new evaluation; historical evidence retained."
        )
    )
    db.commit()
    db.refresh(rollout)
    return status(rollout)


@router.post("/rollouts/shadow", response_model=RolloutStatusResponse)
async def shadow(db: Annotated[Session, Depends(get_db)]):
    rollout = get_or_create_active_rollout(db, lock=True)
    if rollout.state not in ("READY", "SHADOW"):
        raise HTTPException(409, "Start a new evaluation before entering SHADOW")
    await require_models(rollout)
    if rollout.state != "SHADOW":
        rollout.state, rollout.canary_percentage = "SHADOW", 0.0
        db.add(
            AuditEvent(event_type="STAGE_CHANGE", reason="Enabled asynchronous SHADOW comparison.")
        )
        db.commit()
        db.refresh(rollout)
    return status(rollout)


@router.post("/rollouts/evaluate", response_model=EvaluateResponse)
def evaluate(db: Annotated[Session, Depends(get_db)]):
    rollout = get_or_create_active_rollout(db, lock=True)
    decision, reason, stats = apply_evaluation(db, rollout)
    return EvaluateResponse(
        decision=decision,
        reason=reason,
        stats=stats,
        rollout_state=rollout.state,
        canary_percentage=rollout.canary_percentage,
    )


@router.get("/metrics", response_model=MetricsSummaryResponse)
def metrics(db: Annotated[Session, Depends(get_db)]):
    rollout = get_or_create_active_rollout(db)
    evidence = collect_evidence(db, rollout)
    stage = collect_evidence(db, rollout, stage=True)
    return {
        **evidence,
        "candidate_canary_percentage": rollout.canary_percentage,
        "rollout_state": rollout.state,
        "stage_candidate_requests": stage["candidate_requests"],
        "stage_champion_labeled_count": stage["champion_labeled_count"],
        "stage_candidate_labeled_count": stage["candidate_labeled_count"],
    }


@router.get("/shadow/summary")
def shadow_summary(db: Annotated[Session, Depends(get_db)]):
    rollout = get_or_create_active_rollout(db)
    ids = prediction_query(db, rollout).with_entities(Prediction.id)
    comparisons = db.query(ModelComparison).filter(ModelComparison.prediction_id.in_(ids))
    total, matches = comparisons.with_entities(
        func.count(), func.sum(cast(ModelComparison.is_match, Integer))
    ).one()
    matches = matches or 0
    return {
        "total_shadow_evaluations": total,
        "matching_predictions": matches,
        "divergent_predictions": total - matches,
        "agreement_rate": round(matches / total, 4) if total else None,
        "pending_tasks": db.query(ShadowOutbox).filter(ShadowOutbox.prediction_id.in_(ids)).count(),
        "recent_comparisons": [
            {
                "prediction_id": c.prediction_id,
                "champion_pred": c.champion_pred,
                "candidate_pred": c.candidate_pred,
                "is_match": c.is_match,
            }
            for c in comparisons.order_by(ModelComparison.timestamp.desc()).limit(15)
        ],
    }


@router.get("/predictions/recent")
def predictions(
    db: Annotated[Session, Depends(get_db)], limit: Annotated[int, Query(ge=1, le=200)] = 100
):
    rollout = get_or_create_active_rollout(db)
    return [
        {
            "id": p.id,
            "client_id": p.client_id or "anonymous",
            "selected_role": p.selected_role,
            "selected_version": p.selected_version,
            "prediction": p.prediction,
            "latency_ms": round(p.latency_ms, 1),
            "status_code": p.status_code,
            "created_at": p.created_at.isoformat(),
        }
        for p in prediction_query(db, rollout).order_by(Prediction.created_at.desc()).limit(limit)
    ]


@router.get("/audit", response_model=list[AuditEventResponse])
def audit(db: Annotated[Session, Depends(get_db)], limit: Annotated[int, Query(ge=1, le=200)] = 50):
    return [
        AuditEventResponse(
            id=e.id,
            timestamp=e.timestamp,
            event_type=e.event_type,
            reason=e.reason,
            details=parse_details(e.details_json),
        )
        for e in db.query(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)
    ]


def parse_details(value):
    if not value:
        return None
    try:
        return json.loads(value)
    except ValueError:
        return value
