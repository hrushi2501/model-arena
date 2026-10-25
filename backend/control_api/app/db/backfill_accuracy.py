"""Rebuild counters from existing labels while API and worker writes are stopped."""

from sqlalchemy import func

from app.db.models import AccuracyCounter, Feedback, ModelComparison, Prediction
from app.db.session import SessionLocal


def rebuild_accuracy(db):
    # Older versions accepted duplicate feedback. Keep the earliest label,
    # matching the new endpoint's immutable first-label policy.
    first_labels = (
        db.query(func.min(Feedback.id).label("id")).group_by(Feedback.prediction_id).subquery()
    )
    counts = {role: [0, 0] for role in ("champion", "candidate")}
    for feedback, prediction, comparison in (
        db.query(Feedback, Prediction, ModelComparison)
        .join(first_labels, Feedback.id == first_labels.c.id)
        .join(Prediction, Feedback.prediction_id == Prediction.id)
        .outerjoin(ModelComparison, ModelComparison.prediction_id == Prediction.id)
        .all()
    ):
        correct, total = counts[prediction.selected_role]
        counts[prediction.selected_role] = [
            correct + int(prediction.prediction == feedback.ground_truth_label),
            total + 1,
        ]
        if comparison is not None and prediction.selected_role == "champion":
            counts["candidate"][0] += int(comparison.candidate_pred == feedback.ground_truth_label)
            counts["candidate"][1] += 1
    db.query(AccuracyCounter).delete()
    for role, (correct, total) in counts.items():
        db.add(AccuracyCounter(model_role=role, correct_count=correct, total_count=total))
    db.commit()


if __name__ == "__main__":
    with SessionLocal() as db:
        rebuild_accuracy(db)
