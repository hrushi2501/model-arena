"""One source of rollout-scoped operational and labeled evidence."""

import math

from sqlalchemy import and_, or_

from app.db.models import Prediction
from app.services.feedback import accuracy_summary


def prediction_query(db, rollout, stage=False):
    return db.query(Prediction).filter(
        Prediction.created_at >= (rollout.updated_at if stage else rollout.created_at),
        or_(
            and_(
                Prediction.selected_role == "champion",
                Prediction.selected_version == rollout.champion_version,
            ),
            and_(
                Prediction.selected_role == "candidate",
                Prediction.selected_version == rollout.candidate_version,
            ),
        ),
    )


def collect_evidence(db, rollout, stage=False):
    predictions = prediction_query(db, rollout, stage).all()
    candidate = [p for p in predictions if p.selected_role == "candidate"]
    latency = sorted(p.latency_ms for p in candidate)
    accuracy = accuracy_summary(db, rollout, rollout.updated_at if stage else rollout.created_at)
    return {
        "total_predictions": len(predictions),
        "champion_requests": len(predictions) - len(candidate),
        "candidate_requests": len(candidate),
        "candidate_p95_latency_ms": latency[max(0, math.ceil(len(latency) * 0.95) - 1)]
        if latency
        else None,
        "candidate_error_rate": sum(p.status_code >= 400 for p in candidate) / len(candidate)
        if candidate
        else None,
        "champion_accuracy": accuracy["champion"]["accuracy"],
        "candidate_accuracy": accuracy["candidate"]["accuracy"],
        "champion_labeled_count": accuracy["champion"]["total"],
        "candidate_labeled_count": accuracy["candidate"]["total"],
    }
