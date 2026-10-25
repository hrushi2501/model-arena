"""Opt-in integration tests. TEST_DATABASE_URL must point to a disposable database."""

import threading
from concurrent.futures import ThreadPoolExecutor

from app.db.models import AccuracyCounter, Feedback, ModelComparison, Prediction
from app.schemas.schemas import FeedbackRequest
from app.services.feedback import record_feedback
from tests.test_shadow_and_feedback import task, worker_storage


def test_feedback_and_worker_races_do_not_double_count(postgres):
    engine, sessions = postgres
    store = worker_storage.ComparisonStore(engine)
    _ = store.tables  # reflect once before the threads race
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
        champion = db.get(AccuracyCounter, "champion")
        candidate = db.get(AccuracyCounter, "candidate")
        assert (champion.correct_count, champion.total_count) == (0, count)
        assert (candidate.correct_count, candidate.total_count) == (count, count)
