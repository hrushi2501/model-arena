"""Release policy shared by operator actions and the automatic API monitor."""

import json

from fastapi import HTTPException
from sqlalchemy import func

from app.db.models import AuditEvent, Rollout
from app.services.evidence import collect_evidence
from app.settings import CANDIDATE_VERSION, CHAMPION_VERSION

MIN_SAMPLE_THRESHOLD = 20
MAX_ERROR_RATE_THRESHOLD = 0.05
MAX_P95_LATENCY_MS = 200.0
ACCURACY_DROP_LIMIT = 0.05
STEPS = (0.10, 0.25, 0.50, 1.0)


def get_or_create_active_rollout(db, lock=False):
    rollout = db.query(Rollout).order_by(Rollout.id.desc()).first()
    if rollout is None or (rollout.champion_version, rollout.candidate_version) != (
        CHAMPION_VERSION,
        CANDIDATE_VERSION,
    ):
        rollout = Rollout(champion_version=CHAMPION_VERSION, candidate_version=CANDIDATE_VERSION)
        db.add(rollout)
        db.commit()
        db.refresh(rollout)
    if lock:
        rollout = db.query(Rollout).filter_by(id=rollout.id).with_for_update().one()
    return rollout


def evaluate_rollout(db, rollout):
    stats = collect_evidence(db, rollout, stage=True)
    stats["sample_count"] = stats["candidate_requests"]
    stats["error_rate"] = stats["candidate_error_rate"]
    stats["p95_latency_ms"] = stats["candidate_p95_latency_ms"]
    if rollout.state not in ("CANARY", "PROMOTED"):
        return "HOLD", "Start a canary probe to collect live evidence.", stats
    if stats["sample_count"] < MIN_SAMPLE_THRESHOLD:
        stats["required"] = MIN_SAMPLE_THRESHOLD
        return "HOLD", "Need at least 20 Candidate requests in this stage.", stats
    if stats["error_rate"] > MAX_ERROR_RATE_THRESHOLD:
        return "ROLLBACK", "Candidate error rate exceeds 5%.", stats
    if stats["p95_latency_ms"] > MAX_P95_LATENCY_MS:
        return "ROLLBACK", "Candidate p95 latency exceeds 200 ms.", stats
    if rollout.state == "PROMOTED":
        # The Champion baseline was collected before traffic reached 100%.
        stats.update(
            {
                k: v
                for k, v in collect_evidence(db, rollout).items()
                if k.endswith(("accuracy", "labeled_count"))
            }
        )
    if (
        min(stats["champion_labeled_count"], stats["candidate_labeled_count"])
        < MIN_SAMPLE_THRESHOLD
    ):
        return "HOLD", "Need 20 genuine labels for each model; missing accuracy is unknown.", stats
    if stats["candidate_accuracy"] < stats["champion_accuracy"] - ACCURACY_DROP_LIMIT:
        return "ROLLBACK", "Candidate accuracy dropped by more than 5 percentage points.", stats
    if rollout.state == "PROMOTED":
        return "HOLD", "Promoted model remains within safety thresholds.", stats
    return "PROMOTE", "Stage health and labeled quality thresholds satisfied.", stats


def execute_rollback(db, rollout, reason, details=None):
    rollout.state, rollout.canary_percentage = "ROLLED_BACK", 0.0
    db.add(AuditEvent(event_type="ROLLBACK", reason=reason, details_json=json.dumps(details or {})))
    db.commit()
    db.refresh(rollout)
    return rollout


def execute_advance(db, rollout, target_percentage=None):
    target = (
        target_percentage
        if target_percentage is not None
        else next((step for step in STEPS if step > rollout.canary_percentage), 1.0)
    )
    rollout.state = "PROMOTED" if target == 1.0 else "CANARY"
    rollout.canary_percentage = target
    db.add(
        AuditEvent(
            event_type="PROMOTE" if target == 1.0 else "STAGE_CHANGE",
            reason=f"Candidate traffic advanced to {target:.0%}.",
            details_json=json.dumps({"canary_percentage": target}),
        )
    )
    db.commit()
    db.refresh(rollout)
    return rollout


def apply_evaluation(db, rollout):
    decision, reason, stats = evaluate_rollout(db, rollout)
    if decision == "ROLLBACK":
        execute_rollback(db, rollout, reason, stats)
    elif decision == "PROMOTE":
        execute_advance(db, rollout)
    return decision, reason, stats


def advance_safely(db, rollout, target=None):
    expected = next((step for step in STEPS if step > rollout.canary_percentage), None)
    if rollout.state in ("READY", "SHADOW"):
        expected = 0.10
    elif rollout.state != "CANARY":
        raise HTTPException(409, "Start a new evaluation before advancing")
    if expected is None or (target is not None and target != expected):
        raise HTTPException(409, "Only the next release stage is allowed")
    if rollout.state == "CANARY":
        decision, reason, _ = evaluate_rollout(db, rollout)
        if decision != "PROMOTE":
            raise HTTPException(409, reason)
    return execute_advance(db, rollout, expected)


def monitor_once(sessions):
    with sessions() as db:
        active_id = db.query(func.max(Rollout.id)).scalar()
        rollout = (
            db.query(Rollout).filter_by(id=active_id).with_for_update(skip_locked=True).first()
        )
        if rollout is not None and rollout.state in ("CANARY", "PROMOTED"):
            apply_evaluation(db, rollout)
