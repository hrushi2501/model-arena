import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.api.v1 import routes
from app.db.models import AuditEvent, Feedback, Prediction, Rollout, ShadowOutbox
from app.main import app
from app.services import routing
from app.services.decision_engine import evaluate_rollout, monitor_once
from tests.test_outbox import seed_event

FEATURES = [1.0] * 13


def evidence(sessions, labels=True, failures=0, candidate_label=1):
    with sessions.begin() as db:
        rollout = db.query(Rollout).order_by(Rollout.id.desc()).first()
        rollout.state, rollout.canary_percentage = "CANARY", 0.1
    with sessions.begin() as db:
        for role in ("champion", "candidate"):
            for i in range(20):
                pid = f"{role}-{i}"
                failed = role == "candidate" and i < failures
                db.add(
                    Prediction(
                        id=pid,
                        selected_role=role,
                        selected_version=f"models:/wine-classifier/{1 if role == 'champion' else 2}",
                        prediction=None if failed else 1,
                        latency_ms=10,
                        status_code=503 if failed else 200,
                    )
                )
                if labels and not failed:
                    db.add(
                        Feedback(
                            prediction_id=pid,
                            ground_truth_label=candidate_label if role == "candidate" else 1,
                        )
                    )


@pytest.mark.parametrize(
    "labels,failures,label,expected",
    [
        (False, 0, 1, "HOLD"),
        (True, 0, 1, "PROMOTE"),
        (True, 0, 0, "ROLLBACK"),
        (False, 2, 1, "ROLLBACK"),
    ],
)
def test_policy_needs_labels_but_health_rollback_does_not(
    database, labels, failures, label, expected
):
    _, sessions = database
    evidence(sessions, labels, failures, label)
    with sessions() as db:
        decision, _, stats = evaluate_rollout(db, db.query(Rollout).first())
        assert decision == expected
        if not labels:
            assert stats["candidate_accuracy"] is None


def test_monitor_promotes_once_then_requires_new_stage_evidence(database):
    _, sessions = database
    evidence(sessions)
    monitor_once(sessions)
    monitor_once(sessions)
    with sessions() as db:
        assert db.query(Rollout).first().canary_percentage == 0.25
        assert db.query(AuditEvent).filter_by(event_type="STAGE_CHANGE").count() == 1
        assert evaluate_rollout(db, db.query(Rollout).first())[0] == "HOLD"


def test_old_and_wrong_version_requests_do_not_advance_stage(database):
    _, sessions = database
    evidence(sessions)
    with sessions.begin() as db:
        for prediction in db.query(Prediction):
            prediction.created_at = datetime.now(UTC) - timedelta(days=1)
        db.query(Prediction).filter_by(selected_role="candidate").update(
            {"selected_version": "models:/wine-classifier/99"}
        )
    with sessions() as db:
        decision, _, stats = evaluate_rollout(db, db.query(Rollout).first())
        assert decision == "HOLD" and stats["sample_count"] == 0


def test_new_evaluation_preserves_history_and_pending_outbox(database):
    _, sessions = database
    seed_event(sessions)
    before = TestClient(app).get("/api/v1/rollouts/active").json()["id"]
    result = TestClient(app).post("/api/v1/rollouts/reset")
    assert result.status_code == 200 and result.json()["id"] > before
    with sessions() as db:
        assert db.query(Prediction).count() == 1
        assert db.query(ShadowOutbox).count() == 1
    assert TestClient(app).get("/api/v1/metrics").json()["total_predictions"] == 0


@pytest.mark.parametrize("state", ["READY", "SHADOW", "ROLLED_BACK", "PROMOTED"])
def test_demo_fault_cannot_force_candidate_routing(database, monkeypatch, state):
    _, sessions = database
    with sessions.begin() as db:
        db.query(Rollout).first().state = state
    monkeypatch.setenv("ENABLE_DEMO_FAULTS", "true")
    result = TestClient(app).post(
        "/api/v1/predict", json={"features": FEATURES, "inject_fault": True}
    )
    assert result.status_code == 409
    with sessions() as db:
        assert db.query(Prediction).count() == 0 and db.query(ShadowOutbox).count() == 0


def test_no_body_can_start_probe_but_cannot_skip_stage(database, monkeypatch):
    async def ready(*args):
        return {"ready": True}

    monkeypatch.setattr(routes, "model_status", ready)
    client = TestClient(app)
    assert (
        client.post("/api/v1/rollouts/advance", json={"canary_percentage": 0.5}).status_code == 409
    )
    assert client.post("/api/v1/rollouts/advance").json()["canary_percentage"] == 0.1
    assert client.post("/api/v1/rollouts/advance", json={}).status_code == 409


@pytest.mark.parametrize(
    "scenario,code",
    [("network", 503), ("timeout", 504), ("status", 502), ("identity", 502), ("malformed", 502)],
)
def test_upstream_failures_never_fabricate_prediction(monkeypatch, scenario, code):
    def handler(request):
        if scenario == "network":
            raise httpx.ConnectError("unavailable", request=request)
        if scenario == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        body = {
            "prediction": 1,
            "model_role": "candidate",
            "model_version": "models:/wine-classifier/99",
        }
        return httpx.Response(
            500 if scenario == "status" else 200, json={} if scenario == "malformed" else body
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(routing.httpx, "AsyncClient", Mock(return_value=client))
    result = asyncio.run(
        routing.forward_prediction(
            "candidate", "http://candidate/predict", FEATURES, "models:/wine-classifier/2"
        )
    )
    assert result["status_code"] == code
    assert result["prediction"] is None and result["error"]


def test_api_persists_failure_and_rejects_feedback(database, monkeypatch):
    async def unavailable(*args, **kwargs):
        return {
            "prediction": None,
            "latency_ms": 10.0,
            "status_code": 503,
            "error": "Model server unavailable",
        }

    monkeypatch.setattr(routes, "forward_prediction", unavailable)
    client = TestClient(app)
    result = client.post("/api/v1/predict", json={"features": FEATURES})
    assert result.status_code == 503 and result.json()["prediction"] is None
    assert (
        client.post(
            "/api/v1/feedback",
            json={"prediction_id": result.json()["request_id"], "ground_truth_label": 0},
        ).status_code
        == 409
    )


def test_startup_upgrades_legacy_nonnullable_prediction_without_data_loss(tmp_path):
    from sqlalchemy import create_engine, inspect
    from sqlalchemy.orm import Session

    from app.db.migrate import initialize_schema
    from app.db.session import Base

    engine = create_engine("sqlite:///" + str(tmp_path / "legacy.db"))
    column = Prediction.__table__.c.prediction
    column.nullable = False
    try:
        Base.metadata.create_all(engine)
    finally:
        column.nullable = True
    with Session(engine) as db:
        db.add(
            Prediction(
                id="existing",
                selected_role="champion",
                selected_version="models:/wine-classifier/1",
                prediction=1,
                latency_ms=1.0,
            )
        )
        db.commit()
    initialize_schema(engine)
    initialize_schema(engine)
    assert next(c for c in inspect(engine).get_columns("predictions") if c["name"] == "prediction")[
        "nullable"
    ]
    with Session(engine) as db:
        assert db.get(Prediction, "existing").prediction == 1
    engine.dispose()
