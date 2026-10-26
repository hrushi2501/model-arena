from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app import main

FEATURES = [13.2, 1.78, 2.14, 11.2, 100., 2.65, 2.76, .26, 1.28, 4.38, 1.05, 3.4, 1050.]


@pytest.fixture
def client(monkeypatch):
    model = Mock()
    model.predict.return_value = [1]
    model.predict_proba.return_value = __import__("numpy").array([[.1, .8, .1]])
    monkeypatch.setattr(main.mlflow.sklearn, "load_model", Mock(return_value=model))
    with TestClient(main.app) as client:
        yield client
    monkeypatch.setattr(main, "loaded_model", None)


def test_real_identity_and_probabilities(client):
    ready = client.get("/health/ready").json()
    assert ready["model_version"] == main.MODEL_URI
    assert ready["ready"] is True
    result = client.post("/predict", json={"features": FEATURES})
    assert result.status_code == 200
    assert result.json()["prediction"] == 1
    assert result.json()["probabilities"] == [.1, .8, .1]
    assert result.json()["model_version"] == main.MODEL_URI


def test_missing_registry_model_fails_startup_without_training(monkeypatch):
    monkeypatch.setattr(main.mlflow.sklearn, "load_model", Mock(side_effect=RuntimeError("unavailable")))
    with pytest.raises(RuntimeError, match="could not be loaded"):
        main.load_model_instance()
    assert main.loaded_model is None
    assert TestClient(main.app).get("/health/ready").status_code == 503
    assert TestClient(main.app).post("/predict", json={"features": FEATURES}).status_code == 503


@pytest.mark.parametrize("uri", ["models:/wine-classifier/latest", "models:/wine-classifier@champion", "", "models:/wine-classifier/0"])
def test_mutable_or_missing_model_identity_rejected(monkeypatch, uri):
    monkeypatch.setattr(main, "MODEL_URI", uri)
    with pytest.raises(ValueError):
        main.load_model_instance()


def test_faults_require_opt_in_and_candidate(client, monkeypatch):
    assert client.post("/predict", json={"features": FEATURES, "inject_fault": True}).status_code == 403
    monkeypatch.setenv("ENABLE_DEMO_FAULTS", "true")
    assert client.post("/predict", json={"features": FEATURES, "inject_fault": True}).status_code == 403
    monkeypatch.setattr(main, "MODEL_ROLE", "candidate")
    assert client.post("/predict", json={"features": FEATURES, "inject_fault": True}).status_code == 500


@pytest.mark.parametrize("features", [[], [1.], [1.] * 14])
def test_invalid_feature_lengths_are_rejected(client, features):
    assert client.post("/predict", json={"features": features}).status_code == 422
