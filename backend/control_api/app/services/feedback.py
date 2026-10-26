"""Idempotent delayed labels and database-backed accuracy counters."""

from fastapi import HTTPException
from sqlalchemy import DateTime, String, bindparam, text
from sqlalchemy.orm import Session

from app.db.models import Feedback, Prediction, Rollout
from app.schemas.schemas import FeedbackRequest


def accuracy_summary(db: Session, rollout=None, since=None) -> dict:
    """Count committed evidence in one snapshot; no duplicated mutable counters."""
    summary = {
        role: {"correct": 0, "total": 0, "accuracy": None} for role in ("champion", "candidate")
    }
    rows = db.execute(
        text("""
        WITH labels AS (
            SELECT p.id, p.selected_role, p.prediction, f.ground_truth_label
            FROM predictions p JOIN feedback f ON f.prediction_id = p.id
            WHERE f.id IN (SELECT MIN(id) FROM feedback GROUP BY prediction_id)
              AND p.status_code = 200 AND p.prediction IS NOT NULL
              AND (:since IS NULL OR p.created_at >= :since)
              AND (:champion IS NULL OR
                   (p.selected_role = 'champion' AND p.selected_version = :champion) OR
                   (p.selected_role = 'candidate' AND p.selected_version = :candidate))
        ), evidence AS (
            SELECT selected_role AS role, prediction = ground_truth_label AS correct
            FROM labels
            UNION ALL
            SELECT 'candidate', c.candidate_pred = l.ground_truth_label
            FROM labels l JOIN model_comparisons c ON c.prediction_id = l.id
            WHERE l.selected_role = 'champion'
        )
        SELECT role, SUM(CASE WHEN correct THEN 1 ELSE 0 END), COUNT(*)
        FROM evidence GROUP BY role
    """).bindparams(
            bindparam("since", type_=DateTime(timezone=True)),
            bindparam("champion", type_=String()),
            bindparam("candidate", type_=String()),
        ),
        {
            "since": since,
            "champion": rollout.champion_version if rollout else None,
            "candidate": rollout.candidate_version if rollout else None,
        },
    )
    for role, correct, total in rows:
        summary[role] = {"correct": correct, "total": total, "accuracy": round(correct / total, 4)}
    return summary


def record_feedback(request: FeedbackRequest, db: Session) -> dict:
    try:
        prediction = (
            db.query(Prediction)
            .filter(Prediction.id == request.prediction_id)
            .with_for_update()
            .first()
        )
        if prediction is None:
            raise HTTPException(status_code=404, detail="Prediction not found")
        if prediction.status_code != 200 or prediction.prediction is None:
            raise HTTPException(status_code=409, detail="Cannot label an unsuccessful inference")

        existing = (
            db.query(Feedback).filter_by(prediction_id=prediction.id).order_by(Feedback.id).first()
        )
        if existing:
            if existing.ground_truth_label != request.ground_truth_label:
                raise HTTPException(
                    status_code=409, detail="Prediction already has a different label"
                )
            status = "already_recorded"
        else:
            label = request.ground_truth_label
            db.add(Feedback(prediction_id=prediction.id, ground_truth_label=label))
            status = "recorded"
        db.commit()
    except Exception:
        db.rollback()
        raise
    active = db.query(Rollout).order_by(Rollout.id.desc()).first()
    return {
        "status": status,
        "prediction_id": request.prediction_id,
        "accuracy": accuracy_summary(db, active, active.created_at if active else None),
    }
