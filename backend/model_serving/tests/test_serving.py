import pytest
from fastapi.testclient import TestClient

from app.main import app, load_model_instance


@pytest.fixture(scope="module", autouse=True)
def init_model():
    load_model_instance()


def test_liveness():
    client = TestClient(app)
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readiness():
    client = TestClient(app)
    response = client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["ready"] is True
    assert "model_role" in data
    assert "model_version" in data


def test_predict_success():
    client = TestClient(app)
    # Standard 13-feature vector for Wine dataset
    wine_sample = [13.2, 1.78, 2.14, 11.2, 100.0, 2.65, 2.76, 0.26, 1.28, 4.38, 1.05, 3.4, 1050.0]

    response = client.post("/predict", json={"features": wine_sample, "inject_fault": False})
    assert response.status_code == 200
    data = response.json()
    assert "prediction" in data
    assert data["prediction"] in [0, 1, 2]
    assert "probabilities" in data
    assert len(data["probabilities"]) == 3
    assert abs(sum(data["probabilities"]) - 1.0) < 0.05
    assert "model_role" in data
    assert "model_version" in data


def test_predict_fault_injection():
    client = TestClient(app)
    wine_sample = [13.2, 1.78, 2.14, 11.2, 100.0, 2.65, 2.76, 0.26, 1.28, 4.38, 1.05, 3.4, 1050.0]

    # Deliberate fault injection should trigger HTTP 500
    response = client.post("/predict", json={"features": wine_sample, "inject_fault": True})
    assert response.status_code == 500
    assert "Injected fault" in response.json()["detail"]
