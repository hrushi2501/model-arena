import json
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from app.api.v1 import routes
from app.db.models import Prediction, Rollout, ShadowOutbox
from app.main import app
from app.services import outbox
from tests.test_shadow_and_feedback import add_prediction


def seed_event(sessions, prediction_id="pred-1"):
    add_prediction(sessions, prediction_id)
    payload = json.dumps(
        {
            "request_id": prediction_id,
            "features": [1.0],
            "champion_pred": 1,
            "candidate_url": routes.CANDIDATE_URL,
        }
    )
    with sessions.begin() as db:
        db.add(
            ShadowOutbox(
                prediction_id=prediction_id,
                payload_json=payload,
                available_at=datetime(2000, 1, 1, tzinfo=UTC),
            )
        )
    return payload


@pytest.mark.parametrize("table", ["predictions", "shadow_outbox"])
def test_prediction_and_outbox_roll_back_together(database, monkeypatch, table):
    engine, sessions = database
    with sessions.begin() as db:
        db.add(Rollout(state="SHADOW"))

    async def forward(*args):
        return {"prediction": 1, "latency_ms": 1.0}

    monkeypatch.setattr(routes, "forward_prediction", forward)

    def fail_insert(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO " + table):
            raise OperationalError(None, None, Exception("injected write failure"))

    event.listen(engine, "before_cursor_execute", fail_insert)
    try:
        with pytest.raises(OperationalError):
            TestClient(app).post("/api/v1/predict", json={"features": [1.0]})
    finally:
        event.remove(engine, "before_cursor_execute", fail_insert)
    with sessions() as db:
        assert db.query(Prediction).count() == 0
        assert db.query(ShadowOutbox).count() == 0


def test_unconfirmed_event_survives_and_is_retried_by_new_dispatch(database, monkeypatch):
    _, sessions = database
    payload = seed_event(sessions)
    publish = Mock(return_value=False)
    monkeypatch.setattr(outbox, "publish_shadow_task", publish)
    assert outbox.dispatch_once(sessions)
    assert outbox.dispatch_once(sessions) is False  # backoff, not a tight retry loop
    with sessions.begin() as db:
        pending = db.get(ShadowOutbox, "pred-1")
        assert pending.payload_json == payload
        pending.available_at = datetime.now(UTC) - timedelta(seconds=1)
    publish.return_value = True
    assert outbox.dispatch_once(sessions)
    assert publish.call_args_list[0] == publish.call_args_list[1]
    with sessions() as db:
        assert db.query(ShadowOutbox).count() == 0


@pytest.mark.parametrize("failure", ["after_publish", "during_delete"])
def test_confirmed_publish_followed_by_crash_replays_same_event(database, monkeypatch, failure):
    engine, sessions = database
    payload = seed_event(sessions)
    publish = Mock(return_value=True)
    monkeypatch.setattr(outbox, "publish_shadow_task", publish)

    def fail_delete(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("DELETE FROM shadow_outbox"):
            raise OperationalError(None, None, Exception("injected delete failure"))

    if failure == "after_publish":
        publish.side_effect = SystemExit("process died after broker acceptance")
        error = SystemExit
    else:
        event.listen(engine, "before_cursor_execute", fail_delete)
        error = OperationalError
    try:
        with pytest.raises(error):
            outbox.dispatch_once(sessions)
    finally:
        if failure == "during_delete":
            event.remove(engine, "before_cursor_execute", fail_delete)
    with sessions() as db:
        assert db.get(ShadowOutbox, "pred-1").payload_json == payload
    publish.side_effect = None
    assert outbox.dispatch_once(sessions)
    assert publish.call_args_list[0] == publish.call_args_list[1]
    assert outbox.dispatch_once(sessions) is False


def test_failed_event_does_not_block_other_due_events(database, monkeypatch):
    _, sessions = database
    seed_event(sessions, "first")
    seed_event(sessions, "second")
    publish = Mock(side_effect=[False, True])
    monkeypatch.setattr(outbox, "publish_shadow_task", publish)
    assert outbox.dispatch_once(sessions)
    assert outbox.dispatch_once(sessions)
    with sessions() as db:
        assert [row.prediction_id for row in db.query(ShadowOutbox).all()] == ["first"]


def test_lifespan_starts_and_stops_dispatcher(database, monkeypatch):
    import importlib
    import threading

    main = importlib.import_module("app.main")
    engine, sessions = database
    payload = seed_event(sessions)
    published = threading.Event()

    def publish(prediction_id, body):
        assert prediction_id == "pred-1" and body == payload
        published.set()
        return True

    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(main, "SessionLocal", sessions)
    monkeypatch.setattr(outbox, "publish_shadow_task", publish)
    with TestClient(app) as client:
        assert published.wait(timeout=5)
        assert client.get("/health/live").status_code == 200
    assert not any(t.name == "shadow-outbox" and t.is_alive() for t in threading.enumerate())
    with sessions() as db:
        assert db.query(ShadowOutbox).count() == 0
