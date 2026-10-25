import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("model_server")

MODEL_ROLE = os.getenv("MODEL_ROLE", "champion").lower()
DEFAULT_URI = "models:/wine-classifier/1" if MODEL_ROLE == "champion" else "models:/wine-classifier/2"
MODEL_URI = os.getenv("MODEL_URI") or DEFAULT_URI
MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")

# Global reference to loaded model
loaded_model: Any = None


def load_model_instance():
    """
    Attempts to load model from MLflow registry;
    falls back gracefully to local serialized joblib model or on-the-fly Wine model.
    """
    global loaded_model

    # 1. Attempt MLflow pyfunc loading
    try:
        import mlflow.pyfunc

        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        logger.info(f"Attempting to load model from MLflow: {MODEL_URI} ({MLFLOW_TRACKING_URI})")
        loaded_model = mlflow.pyfunc.load_model(MODEL_URI)
        logger.info(f"Successfully loaded model from MLflow: {MODEL_URI}")
        return loaded_model
    except Exception as exc:
        logger.info(f"MLflow load unsuccessful ({exc}); checking local serialized joblib models.")

    # 2. Attempt local .joblib loading
    base_dir = Path(__file__).resolve().parent
    candidate_paths = [
        base_dir / "models" / f"{MODEL_ROLE}.joblib",
        base_dir.parent / "models" / f"{MODEL_ROLE}.joblib",
        base_dir.parent.parent / "ml" / "models" / f"{MODEL_ROLE}.joblib",
    ]

    for p in candidate_paths:
        if p.exists():
            try:
                loaded_model = joblib.load(p)
                logger.info(f"Successfully loaded local model from {p}")
                return loaded_model
            except Exception as e:
                logger.warning(f"Failed to load {p}: {e}")

    # 3. Fallback: Quick in-memory Scikit-learn Wine classifier
    logger.info("Training lightweight in-memory fallback classifier on Wine dataset...")
    from sklearn.datasets import load_wine
    from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier

    wine = load_wine()
    if MODEL_ROLE == "candidate":
        model = GradientBoostingClassifier(n_estimators=50, random_state=42)
    else:
        model = RandomForestClassifier(n_estimators=50, random_state=42)
    model.fit(wine.data, wine.target)
    loaded_model = model
    logger.info(f"Fallback model trained and ready for role: {MODEL_ROLE}")
    return loaded_model


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_model_instance()
    yield


app = FastAPI(
    title=f"Model Arena Model Server ({MODEL_ROLE})",
    description="Loads and serves one explicitly configured model version for Wine classification.",
    version="0.1.0",
    lifespan=lifespan,
)


class PredictRequest(BaseModel):
    features: list[float] = Field(..., description="List of feature values (13 features for Wine dataset)")
    inject_fault: bool = Field(False, description="Fault injection toggle for automated rollback demonstration")


class PredictResponse(BaseModel):
    prediction: int
    probabilities: list[float] | None = None
    model_version: str
    model_role: str


@app.get("/health/live", tags=["health"])
def liveness() -> dict[str, str]:
    """Confirm that the model-server process is running."""
    return {"status": "alive"}


@app.get("/health/ready", tags=["health"])
def readiness() -> dict[str, Any]:
    """Confirm that the model is loaded and ready to serve inferences."""
    return {
        "ready": loaded_model is not None,
        "model_role": MODEL_ROLE,
        "model_version": MODEL_URI,
    }


@app.post("/predict", response_model=PredictResponse, tags=["inference"])
def predict(request: PredictRequest):
    """
    Executes model inference on incoming feature vector.
    Supports deliberate fault injection for rollback testing.
    """
    if request.inject_fault:
        logger.warning(f"Fault injected on {MODEL_ROLE} ({MODEL_URI}); raising HTTP 500 error.")
        raise HTTPException(
            status_code=500,
            detail=f"Injected fault error on {MODEL_ROLE} for automated rollback demonstration",
        )

    model = loaded_model or load_model_instance()
    if model is None:
        raise HTTPException(status_code=503, detail="Model is not yet loaded")

    features = np.array(request.features, dtype=float).reshape(1, -1)

    try:
        # Check predict_proba
        probabilities = None
        if hasattr(model, "predict_proba"):
            raw_probs = model.predict_proba(features)[0]
            probabilities = [round(float(p), 4) for p in raw_probs]

        # Check predict
        pred_val = model.predict(features)[0]
        prediction = int(pred_val)
    except Exception as e:
        logger.error(f"Inference computation error: {e}")
        raise HTTPException(status_code=400, detail=f"Inference error: {str(e)}")

    return PredictResponse(
        prediction=prediction,
        probabilities=probabilities,
        model_version=MODEL_URI,
        model_role=MODEL_ROLE,
    )
