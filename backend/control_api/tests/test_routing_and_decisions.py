import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import AuditEvent, Feedback, Prediction, Rollout
from app.db.session import Base, get_db
from app.main import app
from app.services.decision_engine import evaluate_rollout, execute_advance, execute_rollback
from app.services.routing import determine_serving_role

# In-memory SQLite database with StaticPool for fast, isolated test execution
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


def test_deterministic_routing():
    rollout = Rollout(
        champion_version="models:/wine-classifier/1",
        candidate_version="models:/wine-classifier/2",
        state="CANARY",
        canary_percentage=0.25,
    )

    # Consistent hashing: same client_id must always map to the same role
    role_1, _ = determine_serving_role("user-alice-123", rollout)
    role_2, _ = determine_serving_role("user-alice-123", rollout)
    assert role_1 == role_2

    # In READY state, always champion
    rollout.state = "READY"
    role_ready, _ = determine_serving_role("user-alice-123", rollout)
    assert role_ready == "champion"

    # In PROMOTED state, always candidate
    rollout.state = "PROMOTED"
    role_promoted, _ = determine_serving_role("user-alice-123", rollout)
    assert role_promoted == "candidate"


def test_decision_engine_rules():
    db = TestingSessionLocal()
    rollout = Rollout(
        champion_version="models:/wine-classifier/1",
        candidate_version="models:/wine-classifier/2",
        state="CANARY",
        canary_percentage=0.25,
    )
    db.add(rollout)
    db.commit()

    # Rule 1: Insufficient samples (< 20) -> HOLD
    for i in range(10):
        db.add(
            Prediction(
                id=f"pred-{i}",
                selected_version="models:/wine-classifier/2",
                selected_role="candidate",
                prediction=1,
                latency_ms=25.0,
                status_code=200,
            )
        )
    db.commit()

    decision, reason, stats = evaluate_rollout(db, rollout)
    assert decision == "HOLD"
    assert stats["sample_count"] == 10

    # Rule 2: High error rate (> 5%) -> ROLLBACK
    for i in range(10, 25):
        # Add 5 errors out of 25 = 20% error rate
        status = 500 if i >= 20 else 200
        db.add(
            Prediction(
                id=f"pred-{i}",
                selected_version="models:/wine-classifier/2",
                selected_role="candidate",
                prediction=1,
                latency_ms=30.0,
                status_code=status,
            )
        )
    db.commit()

    decision, reason, stats = evaluate_rollout(db, rollout)
    assert decision == "ROLLBACK"
    assert "error rate" in reason.lower()

    # Test Rollback execution
    rolled_back = execute_rollback(db, rollout, reason)
    assert rolled_back.state == "ROLLED_BACK"
    assert rolled_back.canary_percentage == 0.0

    # Verify audit event logged
    audit = db.query(AuditEvent).filter(AuditEvent.event_type == "ROLLBACK").first()
    assert audit is not None
    assert audit.reason == reason

    db.close()


def test_decision_engine_promote():
    db = TestingSessionLocal()
    rollout = Rollout(
        champion_version="models:/wine-classifier/1",
        candidate_version="models:/wine-classifier/2",
        state="CANARY",
        canary_percentage=0.50,
    )
    db.add(rollout)
    db.commit()

    # Add 25 healthy candidate predictions
    for i in range(25):
        db.add(
            Prediction(
                id=f"cand-healthy-{i}",
                selected_version="models:/wine-classifier/2",
                selected_role="candidate",
                prediction=1,
                latency_ms=20.0,
                status_code=200,
            )
        )
    db.commit()

    decision, reason, stats = evaluate_rollout(db, rollout)
    assert decision == "PROMOTE"
    assert stats["sample_count"] >= 20

    # Advance to 100% promotes candidate
    promoted = execute_advance(db, rollout, target_percentage=1.0)
    assert promoted.state == "PROMOTED"
    assert promoted.canary_percentage == 1.0

    db.close()


def test_api_full_workflow():
    client = TestClient(app)

    # 1. Health check
    res = client.get("/health/live")
    assert res.status_code == 200
    assert res.json() == {"status": "alive"}

    # 2. Active rollout
    res = client.get("/api/v1/rollouts/active")
    assert res.status_code == 200
    data = res.json()
    assert data["state"] == "READY"
    assert data["canary_percentage"] == 0.0

    # 3. Predict endpoint (fallback generates valid output without running model servers)
    wine_sample = [13.2, 1.78, 2.14, 11.2, 100.0, 2.65, 2.76, 0.26, 1.28, 4.38, 1.05, 3.4, 1050.0]
    res = client.post("/api/v1/predict", json={"features": wine_sample, "client_id": "client-user-1"})
    assert res.status_code == 200
    pred_data = res.json()
    assert "prediction" in pred_data
    assert pred_data["model_role"] == "champion"
    assert "latency_ms" in pred_data
    assert "request_id" in pred_data

    # 4. Advance rollout
    res = client.post("/api/v1/rollouts/advance", json={"canary_percentage": 0.25})
    assert res.status_code == 200
    assert res.json()["canary_percentage"] == 0.25
    assert res.json()["state"] == "CANARY"

    # 5. Record feedback
    res = client.post(
        "/api/v1/feedback",
        json={"prediction_id": pred_data["request_id"], "ground_truth_label": pred_data["prediction"]},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "recorded"

    # 6. Audit trail
    res = client.get("/api/v1/audit")
    assert res.status_code == 200
    assert len(res.json()) >= 1
    assert res.json()[0]["event_type"] in ["STAGE_CHANGE", "DECISION", "ROLLBACK", "PROMOTE"]

    # 7. Metrics summary
    res = client.get("/api/v1/metrics")
    assert res.status_code == 200
    metrics = res.json()
    assert metrics["total_predictions"] >= 1
    assert metrics["champion_requests"] >= 1
