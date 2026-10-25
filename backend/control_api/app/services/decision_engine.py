import json
import logging
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.db.models import AuditEvent, Feedback, Prediction, Rollout

logger = logging.getLogger("decision_engine")

MIN_SAMPLE_THRESHOLD = 20
MAX_ERROR_RATE_THRESHOLD = 0.05  # 5%
MAX_P95_LATENCY_MS = 200.0  # 200ms
ACCURACY_DROP_LIMIT = 0.05  # 5% max allowed drop


def evaluate_rollout(db: Session, rollout: Rollout) -> tuple[str, str, dict]:
    """
    Evaluates candidate metrics against the 3 deterministic rules:
    - HOLD: Fewer than 20 candidate requests.
    - ROLLBACK: Error rate > 5%, p95 latency > 200ms, or accuracy drop > 5%.
    - PROMOTE: Healthy error rate, latency, and equal/better accuracy.
    """
    candidate_preds = db.query(Prediction).filter(Prediction.selected_role == "candidate").all()
    sample_count = len(candidate_preds)

    if sample_count < MIN_SAMPLE_THRESHOLD:
        reason = f"Insufficient sample count ({sample_count}/{MIN_SAMPLE_THRESHOLD} required)."
        stats = {"sample_count": sample_count, "required": MIN_SAMPLE_THRESHOLD}
        return "HOLD", reason, stats

    # 1. Error rate check
    error_count = sum(1 for p in candidate_preds if p.status_code >= 500)
    error_rate = error_count / sample_count

    # 2. Latency check (p95)
    latencies = sorted([p.latency_ms for p in candidate_preds])
    p95_index = int(0.95 * len(latencies))
    p95_latency = latencies[p95_index] if latencies else 0.0

    # 3. Accuracy check from feedback
    candidate_feedback = (
        db.query(Feedback, Prediction)
        .join(Prediction, Feedback.prediction_id == Prediction.id)
        .filter(Prediction.selected_role == "candidate")
        .all()
    )
    champion_feedback = (
        db.query(Feedback, Prediction)
        .join(Prediction, Feedback.prediction_id == Prediction.id)
        .filter(Prediction.selected_role == "champion")
        .all()
    )

    candidate_acc = 1.0
    champion_acc = 1.0
    if candidate_feedback:
        cand_correct = sum(1 for fb, pred in candidate_feedback if fb.ground_truth_label == pred.prediction)
        candidate_acc = cand_correct / len(candidate_feedback)
    if champion_feedback:
        champ_correct = sum(1 for fb, pred in champion_feedback if fb.ground_truth_label == pred.prediction)
        champion_acc = champ_correct / len(champion_feedback)

    stats = {
        "sample_count": sample_count,
        "error_rate": round(error_rate, 4),
        "p95_latency_ms": round(p95_latency, 2),
        "candidate_accuracy": round(candidate_acc, 4),
        "champion_accuracy": round(champion_acc, 4),
    }

    # Evaluate Rollback triggers
    if error_rate > MAX_ERROR_RATE_THRESHOLD:
        reason = f"Safety breach: candidate error rate ({error_rate:.1%}) exceeds threshold ({MAX_ERROR_RATE_THRESHOLD:.1%})."
        return "ROLLBACK", reason, stats

    if p95_latency > MAX_P95_LATENCY_MS:
        reason = f"Latency breach: candidate p95 latency ({p95_latency:.1f}ms) exceeds threshold ({MAX_P95_LATENCY_MS:.1f}ms)."
        return "ROLLBACK", reason, stats

    if candidate_feedback and champion_feedback and (candidate_acc < champion_acc - ACCURACY_DROP_LIMIT):
        reason = f"Accuracy degradation: candidate accuracy ({candidate_acc:.1%}) dropped below champion ({champion_acc:.1%}) by > {ACCURACY_DROP_LIMIT:.1%}."
        return "ROLLBACK", reason, stats

    # Promote trigger
    reason = f"All thresholds satisfied (samples={sample_count}, error_rate={error_rate:.1%}, p95_latency={p95_latency:.1f}ms, acc={candidate_acc:.1%})."
    return "PROMOTE", reason, stats


def execute_rollback(db: Session, rollout: Rollout, reason: str, details: dict | None = None) -> Rollout:
    """Instantly reverts 100% traffic to champion and records an append-only audit event."""
    rollout.state = "ROLLED_BACK"
    rollout.canary_percentage = 0.0

    audit = AuditEvent(
        event_type="ROLLBACK",
        reason=reason,
        details_json=json.dumps(details or {"action": "automatic_rollback"}),
    )
    db.add(audit)
    db.commit()
    db.refresh(rollout)
    logger.warning(f"ROLLBACK executed for rollout {rollout.id}: {reason}")
    return rollout


def execute_advance(db: Session, rollout: Rollout, target_percentage: float | None = None) -> Rollout:
    """Advances canary traffic or marks the candidate as PROMOTED when 100% is reached."""
    if target_percentage is not None:
        new_percentage = target_percentage
    else:
        # Step sequence: 0.10 -> 0.25 -> 0.50 -> 1.0
        steps = [0.10, 0.25, 0.50, 1.0]
        current = rollout.canary_percentage
        next_steps = [s for s in steps if s > current]
        new_percentage = next_steps[0] if next_steps else 1.0

    if new_percentage >= 1.0:
        rollout.state = "PROMOTED"
        rollout.canary_percentage = 1.0
        event_type = "PROMOTE"
        reason = "Candidate promoted to 100% production traffic."
    else:
        rollout.state = "CANARY"
        rollout.canary_percentage = new_percentage
        event_type = "STAGE_CHANGE"
        reason = f"Canary traffic advanced to {new_percentage:.0%}."

    audit = AuditEvent(
        event_type=event_type,
        reason=reason,
        details_json=json.dumps({"canary_percentage": new_percentage}),
    )
    db.add(audit)
    db.commit()
    db.refresh(rollout)
    logger.info(f"Rollout {rollout.id} advanced: {reason}")
    return rollout
