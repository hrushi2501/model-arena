"""Idempotent delayed labels and database-backed accuracy counters."""

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.models import AccuracyCounter, Feedback, ModelComparison, Prediction
from app.schemas.schemas import FeedbackRequest


def increment_accuracy(db: Session, role: str, prediction: int, label: int) -> None:
    # PostgreSQL and SQLite both support this atomic upsert. Row locks on the
    # prediction serialize feedback with the shadow worker for this request.
    db.execute(
        text("""
            INSERT INTO accuracy_counters (model_role, correct_count, total_count)
            VALUES (:role, :correct, 1)
            ON CONFLICT (model_role) DO UPDATE SET
                correct_count = accuracy_counters.correct_count + :correct,
                total_count = accuracy_counters.total_count + 1
        """),
        {"role": role, "correct": int(prediction == label)},
    )


def accuracy_summary(db: Session) -> dict:
    counters = {counter.model_role: counter for counter in db.query(AccuracyCounter).all()}
    summary = {}
    for role in ("champion", "candidate"):
        counter = counters.get(role)
        total = counter.total_count if counter else 0
        correct = counter.correct_count if counter else 0
        summary[role] = {
            "correct": correct,
            "total": total,
            "accuracy": round(correct / total, 4) if total else None,
        }
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
            increment_accuracy(db, prediction.selected_role, prediction.prediction, label)
            comparison = db.get(ModelComparison, prediction.id)
            if comparison is not None:
                increment_accuracy(db, "candidate", comparison.candidate_pred, label)
            status = "recorded"
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {
        "status": status,
        "prediction_id": request.prediction_id,
        "accuracy": accuracy_summary(db),
    }
