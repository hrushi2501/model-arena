"""Opt-in RabbitMQ + PostgreSQL + real HTTP + worker-process integration test."""

import json
import os
import socket
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

import httpx
import pika
import pytest

from app.db.models import ModelComparison, Prediction, Rollout, ShadowOutbox
from app.schemas.schemas import FeedbackRequest
from app.services.feedback import accuracy_summary, record_feedback
from app.services.outbox import dispatch_once
from app.services.queue import publish_shadow_task


@pytest.fixture
def model_server(request):
    candidate_failures = getattr(request, "param", 0)
    requests = []

    class CandidateHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, body))
            self.send_response(503 if len(requests) <= candidate_failures else 200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            role = "champion" if self.path.startswith("/champion") else "candidate"
            self.wfile.write(
                json.dumps(
                    {
                        "prediction": 0,
                        "probabilities": [1.0, 0.0, 0.0],
                        "model_role": role,
                        "model_version": "models:/wine-classifier/"
                        + ("1" if role == "champion" else "2"),
                    }
                ).encode()
            )

        def log_message(self, *args):
            pass

    http_server = ThreadingHTTPServer(("127.0.0.1", 0), CandidateHandler)
    thread = threading.Thread(target=http_server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{http_server.server_port}/predict", requests, candidate_failures
    finally:
        http_server.shutdown()
        http_server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("model_server", [0, 1], indirect=True)
def test_broker_worker_database_and_delayed_feedback(
    postgres, process_environment, monkeypatch, model_server
):
    rabbit_url = os.getenv("TEST_RABBITMQ_URL")
    if not rabbit_url:
        pytest.skip("Set TEST_RABBITMQ_URL to an isolated RabbitMQ virtual host")
    _, sessions = postgres
    candidate_url, requests, candidate_failures = model_server
    prediction_id = str(uuid4())
    with sessions() as db:
        db.add(
            Prediction(
                id=prediction_id,
                selected_version="models:/wine-classifier/1",
                selected_role="champion",
                prediction=1,
                latency_ms=1.0,
                status_code=200,
            )
        )
        db.commit()
        # Label arrives before the queued candidate prediction.
        record_feedback(FeedbackRequest(prediction_id=prediction_id, ground_truth_label=0), db)

    env = {
        **process_environment,
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
    payload = json.dumps(
        {
            "request_id": prediction_id,
            "features": [1.0] * 13,
            "champion_pred": 1,
            "candidate_url": candidate_url,
        }
    )
    try:
        with sessions.begin() as db:
            db.add(ShadowOutbox(prediction_id=prediction_id, payload_json=payload))
        assert dispatch_once(sessions)
        with sessions() as db:
            assert db.query(ShadowOutbox).count() == 0
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
        assert publish_shadow_task(prediction_id, payload)

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
        assert requests == [("/predict", {"features": [1.0] * 13})] * (candidate_failures + 1)
        with sessions() as db:
            assert db.query(ModelComparison).count() == 1
            accuracy = accuracy_summary(db)
            assert accuracy["champion"] == {"correct": 0, "total": 1, "accuracy": 0.0}
            assert accuracy["candidate"] == {"correct": 1, "total": 1, "accuracy": 1.0}
    finally:
        if connection is not None and connection.is_open:
            connection.close()
        worker.terminate()
        worker.wait(timeout=10)


@contextmanager
def running_api(env):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    api = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "error",
        ],
        env=env,
        cwd=Path(__file__).resolve().parents[1],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=3) as client:
            deadline = time.monotonic() + 10
            while True:
                try:
                    if client.get("/health/live").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                assert api.poll() is None, "API exited during startup"
                assert time.monotonic() < deadline, "API did not start"
                time.sleep(0.05)
            yield api, client
    finally:
        if api.poll() is None:
            api.terminate()
        api.wait(timeout=15)


def test_outbox_survives_broker_outage_and_api_kill(postgres, process_environment, model_server):
    rabbit_url = os.getenv("TEST_RABBITMQ_URL")
    if not rabbit_url:
        pytest.skip("Set TEST_RABBITMQ_URL to an isolated RabbitMQ virtual host")
    _, sessions = postgres
    model_url, requests, _ = model_server
    env = {
        **process_environment,
        "RABBITMQ_URL": rabbit_url,
        "CHAMPION_URL": model_url.rsplit("/", 1)[0] + "/champion/predict",
        "CANDIDATE_URL": model_url,
    }
    with sessions.begin() as db:
        db.add(Rollout(state="SHADOW"))
    # Port 1 has no broker: the real dispatcher fails while inference still succeeds.
    with running_api({**env, "RABBITMQ_URL": "amqp://127.0.0.1:1/"}) as (api, client):
        response = client.post("/api/v1/predict", json={"features": [1.0] * 13})
        assert response.status_code == 200
        prediction_id = response.json()["request_id"]
        deadline = time.monotonic() + 5
        while True:
            with sessions() as db:
                pending = db.get(ShadowOutbox, prediction_id)
                assert pending is not None
                payload = pending.payload_json
                if pending.available_at > datetime.now(UTC):
                    break  # A real failed publish has scheduled a retry.
            assert time.monotonic() < deadline, "Dispatcher did not retain the failed event"
            time.sleep(0.05)
        api.kill()  # No shutdown hooks or background-task cleanup.
        api.wait(timeout=5)
    with sessions() as db:
        assert db.get(Prediction, prediction_id) is not None
        assert db.get(ShadowOutbox, prediction_id).payload_json == payload

    worker = subprocess.Popen(
        [sys.executable, "-m", "app.consumer"],
        env=env,
        cwd=Path(__file__).resolve().parents[2] / "worker",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        with running_api(env):  # Fresh API/dispatcher recovers the committed task.
            deadline = time.monotonic() + 20
            while True:
                with sessions() as db:
                    comparison = db.get(ModelComparison, prediction_id)
                    pending = db.get(ShadowOutbox, prediction_id)
                    if comparison is not None and pending is None:
                        assert comparison.champion_pred == comparison.candidate_pred == 0
                        assert comparison.is_match is True
                        assert db.query(ModelComparison).count() == 1
                        break
                assert worker.poll() is None, "Worker exited unexpectedly"
                assert time.monotonic() < deadline, "Restart did not recover the pending task"
                time.sleep(0.05)
        assert len(requests) == 2  # Champion before the crash, Candidate after recovery.
    finally:
        worker.terminate()
        worker.wait(timeout=10)
