import asyncio
import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, Mock

import httpx
import pika
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1 import routes
from app.db.models import Feedback, ModelComparison, Prediction, Rollout
from app.db.session import Base, get_db
from app.main import app
from app.services import queue
from app.services.feedback import accuracy_summary

# The worker is a separate deployable package with its own `app` namespace.
spec = importlib.util.spec_from_file_location(
    "worker_storage", Path(__file__).resolve().parents[2] / "worker/app/storage.py"
)
worker_storage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker_storage)


@pytest.fixture
def database():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    old_override = app.dependency_overrides.get(get_db)

    def dependency():
        with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = dependency
    yield engine, sessions
    if old_override is not None:
        app.dependency_overrides[get_db] = old_override
    else:
        app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def add_prediction(sessions, prediction_id="pred-1", role="champion", label=1):
    with sessions() as db:
        db.add(
            Prediction(
                id=prediction_id,
                selected_version="models:/wine/1",
                selected_role=role,
                prediction=label,
                latency_ms=1.0,
                status_code=200,
            )
        )
        db.commit()


def task(prediction_id="pred-1"):
    from types import SimpleNamespace

    return SimpleNamespace(request_id=prediction_id, champion_pred=1)


@pytest.mark.parametrize("feedback_first", [False, True])
def test_feedback_and_comparison_arrival_orders_are_idempotent(database, feedback_first):
    engine, sessions = database
    add_prediction(sessions)
    store = worker_storage.ComparisonStore(engine)
    client = TestClient(app)
    payload = {"prediction_id": "pred-1", "ground_truth_label": 0}
    if feedback_first:
        first = client.post("/api/v1/feedback", json=payload)
        assert first.json()["accuracy"]["candidate"]["total"] == 0
    store.save(task(), 0)
    # Simulate a redelivery after DB commit but before RabbitMQ received ACK.
    store.save(task(), 2)
    result = client.post("/api/v1/feedback", json=payload)
    assert result.status_code == 200
    assert result.json()["accuracy"] == {
        "champion": {"correct": 0, "total": 1, "accuracy": 0.0},
        "candidate": {"correct": 1, "total": 1, "accuracy": 1.0},
    }
    assert client.post("/api/v1/feedback", json=payload).json()["status"] == "already_recorded"
    conflicting = {**payload, "ground_truth_label": 1}
    assert client.post("/api/v1/feedback", json=conflicting).status_code == 409
    metrics = client.get("/api/v1/metrics").json()
    assert metrics["candidate_accuracy"] == 1.0
    assert metrics["candidate_labeled_count"] == 1
    assert metrics["candidate_requests"] == 0  # shadow never becomes served traffic
    with sessions() as db:
        assert db.query(Feedback).count() == 1
        comparison = db.get(ModelComparison, "pred-1")
        assert comparison.candidate_pred == 0
        assert comparison.is_match is False
        assert comparison.timestamp is not None


def test_feedback_validation_and_served_candidate(database):
    _, sessions = database
    client = TestClient(app)
    assert (
        client.post(
            "/api/v1/feedback", json={"prediction_id": "missing", "ground_truth_label": 1}
        ).status_code
        == 404
    )
    for invalid in [True, 1.2, "1"]:
        assert (
            client.post(
                "/api/v1/feedback", json={"prediction_id": "missing", "ground_truth_label": invalid}
            ).status_code
            == 422
        )
    add_prediction(sessions, role="candidate", label=0)
    result = client.post(
        "/api/v1/feedback", json={"prediction_id": "pred-1", "ground_truth_label": 0}
    ).json()
    assert result["accuracy"]["candidate"]["total"] == 1
    assert result["accuracy"]["champion"]["accuracy"] is None


@pytest.mark.parametrize("state", ["SHADOW", "READY", "CANARY", "PROMOTED"])
@pytest.mark.parametrize("transition_during_inference", [False, True])
def test_shadow_publish_runs_after_response_only_in_shadow(
    database, monkeypatch, state, transition_during_inference
):
    _, sessions = database
    with sessions() as db:
        db.add(Rollout(state=state, canary_percentage=1.0))
        db.commit()
    events = []

    async def forward(role, target_url, features, selected_version):
        events.append(role)
        if transition_during_inference:
            with sessions() as db:
                rollout = db.query(Rollout).first()
                rollout.state = "READY" if state == "SHADOW" else "SHADOW"
                db.commit()
        return {"prediction": 1, "latency_ms": 1.0}

    def publish(request_id, features, champion_pred, candidate_url):
        assert events == ["champion", "response"]
        with sessions() as db:
            assert db.get(Prediction, request_id) is not None
        assert features == [1.0, 2.0]
        assert champion_pred == 1
        assert candidate_url == routes.CANDIDATE_URL
        events.append("published")

    monkeypatch.setattr(routes, "forward_prediction", forward)
    monkeypatch.setattr(routes, "publish_shadow_task", publish)

    async def observed_app(scope, receive, send):
        async def observed_send(message):
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                events.append("response")
            await send(message)

        await app(scope, receive, observed_send)

    async def request():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=observed_app), base_url="http://test"
        ) as client:
            return await client.post("/api/v1/predict", json={"features": [1.0, 2.0]})

    result = asyncio.run(request())
    assert result.status_code == 200
    if state == "SHADOW":
        assert result.json()["model_role"] == "champion"
        assert events == ["champion", "response", "published"]
    else:
        assert "published" not in events


def test_publisher_contract_and_broker_failure(monkeypatch):
    import json

    monkeypatch.setenv("RABBITMQ_URL", "amqp://rabbitmq:5672/")
    connection = MagicMock()
    connection.__enter__.return_value = connection
    monkeypatch.setattr(queue.pika, "BlockingConnection", Mock(return_value=connection))
    assert queue.publish_shadow_task("req-1", [1.0], 2, "http://model-candidate:8000/predict")
    channel = connection.channel.return_value
    channel.confirm_delivery.assert_called_once()
    args = channel.basic_publish.call_args.kwargs
    assert args["routing_key"] == "shadow_tasks"
    assert args["mandatory"] is True
    assert args["properties"].delivery_mode == 2
    assert json.loads(args["body"]) == {
        "request_id": "req-1",
        "features": [1.0],
        "champion_pred": 2,
        "candidate_url": "http://model-candidate:8000/predict",
    }
    connection.__exit__.assert_called_once()
    channel.basic_publish.side_effect = pika.exceptions.UnroutableError([])
    assert (
        queue.publish_shadow_task("req-1", [1.0], 2, "http://model-candidate:8000/predict") is False
    )


def test_existing_duplicate_feedback_counts_first_label_without_backfill(database):
    _, sessions = database
    add_prediction(sessions)
    with sessions() as db:
        db.add_all(
            [
                Feedback(prediction_id="pred-1", ground_truth_label=1),
                Feedback(prediction_id="pred-1", ground_truth_label=0),
            ]
        )
        db.commit()
        assert accuracy_summary(db)["champion"] == {"correct": 1, "total": 1, "accuracy": 1.0}


@pytest.mark.parametrize(
    "role,champion,exists", [("champion", 2, True), ("candidate", 1, True), ("champion", 1, False)]
)
def test_worker_rejects_unknown_or_mismatched_prediction(database, role, champion, exists):
    engine, sessions = database
    if exists:
        add_prediction(sessions, role=role, label=champion)
    store = worker_storage.ComparisonStore(engine)
    with pytest.raises(ValueError, match="Unknown or mismatched"):
        store.save(task(), 0)
    assert store.completed("pred-1") is False
    with sessions() as db:
        assert db.query(ModelComparison).count() == 0


def test_accuracy_combines_served_and_shadow_labels_without_double_counting(database):
    engine, sessions = database
    add_prediction(sessions, "shadow")
    add_prediction(sessions, "champion-only")
    add_prediction(sessions, "candidate", role="candidate", label=0)
    add_prediction(sessions, "unlabeled")
    store = worker_storage.ComparisonStore(engine)
    store.save(task("shadow"), 0)
    store.save(task("unlabeled"), 0)
    client = TestClient(app)
    for prediction_id in ("shadow", "champion-only", "candidate"):
        assert (
            client.post(
                "/api/v1/feedback", json={"prediction_id": prediction_id, "ground_truth_label": 0}
            ).status_code
            == 200
        )
    with sessions() as db:
        assert accuracy_summary(db) == {
            "champion": {"correct": 0, "total": 2, "accuracy": 0.0},
            "candidate": {"correct": 2, "total": 2, "accuracy": 1.0},
        }


def test_publisher_authentication_error_does_not_log_credentials(monkeypatch, caplog):
    import secrets

    secret = secrets.token_urlsafe()
    monkeypatch.setattr(
        queue.pika,
        "BlockingConnection",
        Mock(side_effect=pika.exceptions.ProbableAuthenticationError(secret)),
    )
    assert (
        queue.publish_shadow_task("req-1", [1.0], 1, "http://model-candidate:8000/predict") is False
    )
    assert "ProbableAuthenticationError" in caplog.text
    assert secret not in caplog.text
