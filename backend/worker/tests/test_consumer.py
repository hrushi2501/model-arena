import json
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pika
import pytest
from sqlalchemy.exc import OperationalError

from app import consumer


@pytest.fixture
def message(monkeypatch):
    monkeypatch.setenv("CANDIDATE_URL", "http://model-candidate:8000")
    body = json.dumps(
        {
            "request_id": "pred-1",
            "features": [1.0, 2.0],
            "champion_pred": 1,
            "candidate_url": "http://model-candidate:8000/predict",
        }
    ).encode()
    return Mock(), SimpleNamespace(delivery_tag=42), pika.BasicProperties(message_id="pred-1"), body


@pytest.fixture(autouse=True)
def store(monkeypatch):
    store = Mock()
    store.completed.return_value = False
    monkeypatch.setattr(consumer, "get_store", lambda: store)
    return store


def http_client(monkeypatch, response=None, error=None):
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.post.side_effect = error
    client.post.return_value = httpx.Response(
        200,
        json=response
        if response is not None
        else {
            "prediction": 0,
            "model_role": "candidate",
            "model_version": "models:/wine-classifier/2",
        },
        request=httpx.Request("POST", "http://model-candidate:8000/predict"),
    )
    monkeypatch.setattr(consumer.httpx, "Client", Mock(return_value=client))
    return client


def test_candidate_payload_and_commit_before_ack(message, monkeypatch, store):
    channel, _, _, _ = message
    client = http_client(monkeypatch)
    events = []
    store.save.side_effect = lambda task, prediction: events.append(("committed", prediction))
    channel.basic_ack.side_effect = lambda **kwargs: events.append(("ack", kwargs["delivery_tag"]))
    consumer.process_shadow_task(*message)
    client.post.assert_called_once_with(
        "http://model-candidate:8000/predict", json={"features": [1.0, 2.0]}
    )
    assert events == [("committed", 0), ("ack", 42)]
    channel.basic_publish.assert_not_called()


@pytest.mark.parametrize(
    "retries,target", [(0, "shadow_tasks"), (1, "shadow_tasks"), (2, "shadow_tasks.failed")]
)
def test_candidate_failure_retries_then_parks(message, monkeypatch, store, retries, target):
    channel, method, properties, body = message
    properties.headers = {"x-shadow-retries": retries}
    http_client(monkeypatch, error=httpx.ConnectError("unavailable"))
    consumer.process_shadow_task(*message)
    store.save.assert_not_called()
    args = channel.basic_publish.call_args.kwargs
    assert args["routing_key"] == target
    assert args["body"] == body
    assert args["properties"].headers["x-shadow-retries"] == retries + 1
    channel.basic_ack.assert_called_once_with(delivery_tag=method.delivery_tag)


def test_database_failure_does_not_ack_as_success(message, monkeypatch, store):
    channel, _, _, _ = message
    http_client(monkeypatch)
    store.save.side_effect = OperationalError(None, None, Exception("database unavailable"))
    events = []
    channel.basic_publish.side_effect = lambda **kwargs: events.append("retry-confirmed")
    channel.basic_ack.side_effect = lambda **kwargs: events.append("ack")
    consumer.process_shadow_task(*message)
    assert events == ["retry-confirmed", "ack"]


def test_failed_retry_publish_leaves_original_unacknowledged(message, monkeypatch):
    channel, _, _, _ = message
    http_client(monkeypatch, error=httpx.ReadTimeout("timeout"))
    channel.basic_publish.side_effect = pika.exceptions.UnroutableError([])
    with pytest.raises(pika.exceptions.UnroutableError):
        consumer.process_shadow_task(*message)
    channel.basic_ack.assert_not_called()


@pytest.mark.parametrize(
    "body",
    [
        b"not JSON",
        b"{}",
        json.dumps(
            {
                "request_id": "pred-1",
                "features": [1.0],
                "champion_pred": 1,
                "candidate_url": "http://unconfigured/predict",
            }
        ).encode(),
    ],
)
def test_malformed_or_unconfigured_destination_is_parked(message, monkeypatch, body):
    channel, method, properties, _ = message
    client = http_client(monkeypatch)
    consumer.process_shadow_task(channel, method, properties, body)
    client.post.assert_not_called()
    assert channel.basic_publish.call_args.kwargs["routing_key"] == "shadow_tasks.failed"


@pytest.mark.parametrize("value", [True, "1", 1.2])
def test_invalid_candidate_prediction_is_not_persisted(message, monkeypatch, store, value):
    channel, _, _, _ = message
    http_client(monkeypatch, response={"prediction": value})
    consumer.process_shadow_task(*message)
    store.save.assert_not_called()
    assert channel.basic_publish.call_args.kwargs["routing_key"] == "shadow_tasks"


def test_rabbitmq_compose_credentials_are_read_from_environment(monkeypatch):
    import secrets

    monkeypatch.delenv("RABBITMQ_URL", raising=False)
    monkeypatch.setenv("RABBITMQ_USER", "test-worker")
    password = secrets.token_urlsafe()
    monkeypatch.setenv("RABBITMQ_PASSWORD", password)
    parameters = consumer.rabbitmq_parameters()
    assert parameters.credentials.username == "test-worker"
    assert parameters.credentials.password == password


def test_commit_then_lost_ack_does_not_repeat_candidate_inference(message, monkeypatch, store):
    channel, method, properties, body = message
    client = http_client(monkeypatch)
    store.save.side_effect = lambda *args: setattr(store.completed, "return_value", True)
    channel.basic_ack.side_effect = pika.exceptions.StreamLostError("connection lost")
    with pytest.raises(pika.exceptions.StreamLostError):
        consumer.process_shadow_task(*message)
    # The broker redelivers after reconnect, while the Candidate may be offline.
    client.post.side_effect = httpx.ConnectError("candidate unavailable")
    reconnected = Mock()
    consumer.process_shadow_task(reconnected, method, properties, body)
    assert client.post.call_count == 1
    assert store.save.call_count == 1
    reconnected.basic_ack.assert_called_once_with(delivery_tag=method.delivery_tag)
    reconnected.basic_publish.assert_not_called()


def test_database_unavailable_before_inference_retries_without_http(message, monkeypatch, store):
    channel, _, _, _ = message
    client = http_client(monkeypatch)
    store.completed.side_effect = OperationalError(None, None, Exception("unavailable"))
    consumer.process_shadow_task(*message)
    client.post.assert_not_called()
    assert channel.basic_publish.call_args.kwargs["routing_key"] == "shadow_tasks"


@pytest.mark.parametrize("retries", [-1, True, "2", None, 1.5, 2**63 - 1])
def test_bad_retry_headers_are_parked_without_overflow(message, retries):
    channel, method, properties, body = message
    properties.headers = {"x-shadow-retries": retries}
    consumer.retry_or_park(channel, method, properties, body, permanent=False)
    args = channel.basic_publish.call_args.kwargs
    assert args["routing_key"] == "shadow_tasks.failed"
    assert args["properties"].headers["x-shadow-retries"] == consumer.MAX_ATTEMPTS


@pytest.mark.parametrize("payload", [{}, [], {"prediction": None}, {"prediction": [1]}])
def test_invalid_candidate_payloads_are_retried(message, monkeypatch, store, payload):
    channel, _, _, _ = message
    http_client(monkeypatch, response=payload)
    consumer.process_shadow_task(*message)
    store.save.assert_not_called()
    assert channel.basic_publish.call_args.kwargs["routing_key"] == "shadow_tasks"


@pytest.mark.parametrize("status", [301, 400, 404, 429, 500, 503])
def test_candidate_http_failures_are_not_recorded(message, monkeypatch, store, status):
    channel, _, _, _ = message
    client = http_client(monkeypatch)
    client.post.return_value = httpx.Response(
        status, request=httpx.Request("POST", "http://model-candidate:8000/predict")
    )
    consumer.process_shadow_task(*message)
    store.save.assert_not_called()
    assert channel.basic_publish.call_args.kwargs["routing_key"] == "shadow_tasks"


@pytest.mark.parametrize(
    "role,version",
    [("champion", "models:/wine-classifier/2"), ("candidate", "models:/wine-classifier/99")],
)
def test_wrong_candidate_identity_is_never_persisted(message, monkeypatch, store, role, version):
    http_client(
        monkeypatch, response={"prediction": 1, "model_role": role, "model_version": version}
    )
    consumer.process_shadow_task(*message)
    store.save.assert_not_called()
