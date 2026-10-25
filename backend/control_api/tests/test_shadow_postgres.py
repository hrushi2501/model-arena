"""Opt-in integration tests. TEST_DATABASE_URL must point to a disposable database."""

import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.db.models import Feedback, ModelComparison, Prediction, ShadowOutbox
from app.schemas.schemas import FeedbackRequest
from app.services import outbox
from app.services.feedback import accuracy_summary, record_feedback
from tests.test_outbox import seed_event
from tests.test_shadow_and_feedback import task, worker_storage


def test_feedback_and_worker_races_do_not_double_count(postgres):
    engine, sessions = postgres
    store = worker_storage.ComparisonStore(engine)
    store.check_schema()
    count = 20
    with sessions() as db:
        db.add_all(
            [
                Prediction(
                    id=f"pred-{i}",
                    selected_version="models:/wine/1",
                    selected_role="champion",
                    prediction=1,
                    latency_ms=1,
                    status_code=200,
                )
                for i in range(count)
            ]
        )
        db.commit()

    def run_race(i):
        barrier = threading.Barrier(4)

        def feedback():
            barrier.wait(timeout=10)
            with sessions() as db:
                return record_feedback(
                    FeedbackRequest(prediction_id=f"pred-{i}", ground_truth_label=0), db
                )

        def comparison():
            barrier.wait(timeout=10)
            store.save(task(f"pred-{i}"), 0)

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(feedback),
                executor.submit(comparison),
                executor.submit(feedback),
                executor.submit(comparison),
            ]
            for future in futures:
                future.result(timeout=15)

    for i in range(count):
        run_race(i)
    with sessions() as db:
        assert db.query(Feedback).count() == count
        assert db.query(ModelComparison).count() == count
        accuracy = accuracy_summary(db)
        assert accuracy["champion"] == {"correct": 0, "total": count, "accuracy": 0.0}
        assert accuracy["candidate"] == {"correct": count, "total": count, "accuracy": 1.0}


def test_concurrent_dispatchers_skip_locked_rows_without_blocking_feedback(postgres, monkeypatch):
    _, sessions = postgres
    seed_event(sessions, "first")
    seed_event(sessions, "second")
    claimed, release = threading.Event(), threading.Event()
    published = []

    def publish(prediction_id, payload):
        published.append(prediction_id)
        if prediction_id == "first":
            claimed.set()
            assert release.wait(timeout=10)
        return True

    monkeypatch.setattr(outbox, "publish_shadow_task", publish)

    def feedback():
        with sessions() as db:
            return record_feedback(FeedbackRequest(prediction_id="first", ground_truth_label=1), db)

    with ThreadPoolExecutor(max_workers=3) as executor:
        first = executor.submit(outbox.dispatch_once, sessions)
        try:
            assert claimed.wait(timeout=3)
            assert executor.submit(outbox.dispatch_once, sessions).result(timeout=3)
            assert executor.submit(feedback).result(timeout=3)["status"] == "recorded"
        finally:
            release.set()
        assert first.result(timeout=3)
    assert sorted(published) == ["first", "second"]
    with sessions() as db:
        assert db.query(ShadowOutbox).count() == 0


def test_process_death_releases_outbox_claim(postgres, process_environment, monkeypatch):
    _, sessions = postgres
    seed_event(sessions)
    crashed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import os; from app.services import outbox; "
                "outbox.publish_shadow_task = lambda *args: os._exit(17); outbox.dispatch_once()"
            ),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=process_environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
        check=False,
    )
    assert crashed.returncode == 17
    with sessions() as db:
        assert db.get(ShadowOutbox, "pred-1") is not None
    monkeypatch.setattr(outbox, "publish_shadow_task", lambda *args: True)
    deadline = time.monotonic() + 3
    while not outbox.dispatch_once(sessions):
        assert time.monotonic() < deadline, "Dead process left the event claimed"
        time.sleep(0.01)
    with sessions() as db:
        assert db.query(ShadowOutbox).count() == 0
