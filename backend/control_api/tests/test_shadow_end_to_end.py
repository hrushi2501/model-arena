"""Opt-in RabbitMQ + PostgreSQL + real HTTP + worker-process integration test."""

import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import pika
import pytest

from app.db.models import AccuracyCounter, ModelComparison, Prediction
from app.schemas.schemas import FeedbackRequest
from app.services.feedback import record_feedback
from app.services.queue import publish_shadow_task


def test_broker_worker_database_and_delayed_feedback(postgres, monkeypatch):
    rabbit_url = os.getenv("TEST_RABBITMQ_URL")
    if not rabbit_url:
        pytest.skip("Set TEST_RABBITMQ_URL to an isolated RabbitMQ virtual host")
    engine, sessions = postgres
    requests = []

    class CandidateHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, body))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"prediction": 0}')

        def log_message(self, *args):
            pass

    http_server = ThreadingHTTPServer(("127.0.0.1", 0), CandidateHandler)
    thread = threading.Thread(target=http_server.serve_forever, daemon=True)
    thread.start()
    candidate_url = f"http://127.0.0.1:{http_server.server_port}/predict"
    prediction_id = str(uuid4())
    with sessions() as db:
        schema = db.connection().exec_driver_sql("SHOW search_path").scalar_one()
        db.add(
            Prediction(
                id=prediction_id,
                selected_version="models:/test/1",
                selected_role="champion",
                prediction=1,
                latency_ms=1.0,
                status_code=200,
            )
        )
        db.commit()
        # Label arrives before the queued candidate prediction.
        record_feedback(FeedbackRequest(prediction_id=prediction_id, ground_truth_label=0), db)

    database_url = engine.url.update_query_dict({"options": f"-csearch_path={schema}"})
    env = {
        **os.environ,
        "DATABASE_URL": database_url.render_as_string(hide_password=False),
        "RABBITMQ_URL": rabbit_url,
        "CANDIDATE_URL": candidate_url,
    }
    monkeypatch.setenv("RABBITMQ_URL", rabbit_url)
    # Suppress library logs: never expose connection URLs from integration credentials.
    worker = subprocess.Popen(
        [sys.executable, "-m", "app.consumer"],
        env=env,
        cwd=Path(__file__).resolve().parents[2] / "worker",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    connection = None
    try:
        assert publish_shadow_task(prediction_id, [1.0, 2.0], 1, candidate_url)
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            with sessions() as db:
                comparison = db.get(ModelComparison, prediction_id)
                if comparison is not None:
                    assert comparison.candidate_pred == 0
                    assert comparison.is_match is False
                    break
            assert worker.poll() is None, "Worker exited unexpectedly"
            time.sleep(0.05)
        else:
            pytest.fail("Worker did not persist the candidate prediction")
        # Redeliver the same task to exercise idempotency through a real broker.
        assert publish_shadow_task(prediction_id, [1.0, 2.0], 1, candidate_url)
        deadline = time.monotonic() + 10
        while len(requests) < 2 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert len(requests) == 2

        # Invalid JSON must survive in the failed queue instead of being dropped.
        connection = pika.BlockingConnection(pika.URLParameters(rabbit_url))
        channel = connection.channel()
        channel.queue_declare(queue="shadow_tasks.failed", durable=True)
        channel.confirm_delivery()
        channel.basic_publish(
            exchange="",
            routing_key="shadow_tasks",
            body=b"invalid JSON",
            properties=pika.BasicProperties(delivery_mode=2),
            mandatory=True,
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            method, _, body = channel.basic_get("shadow_tasks.failed", auto_ack=False)
            if method is not None:
                assert body == b"invalid JSON"
                channel.basic_ack(method.delivery_tag)
                break
            time.sleep(0.05)
        else:
            pytest.fail("Malformed task was not parked")
        assert requests[0] == ("/predict", {"features": [1.0, 2.0]})
        with sessions() as db:
            assert db.query(ModelComparison).count() == 1
            champion = db.get(AccuracyCounter, "champion")
            candidate = db.get(AccuracyCounter, "candidate")
            assert (champion.correct_count, champion.total_count) == (0, 1)
            assert (candidate.correct_count, candidate.total_count) == (1, 1)
    finally:
        if connection is not None and connection.is_open:
            connection.close()
        worker.terminate()
        worker.wait(timeout=10)
        http_server.shutdown()
        http_server.server_close()
        thread.join(timeout=5)
