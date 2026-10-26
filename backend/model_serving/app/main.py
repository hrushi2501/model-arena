"""Serve exactly one numbered MLflow model version; no synthetic or retrained fallback."""

import os
import re
from contextlib import asynccontextmanager
from typing import Literal

import mlflow
import mlflow.sklearn
import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, FiniteFloat

MODEL_ROLE = os.getenv("MODEL_ROLE", "champion")
MODEL_URI = os.getenv(
    "MODEL_URI",
    "models:/wine-classifier/1" if MODEL_ROLE == "champion" else "models:/wine-classifier/2",
)
loaded_model = None


def load_model_instance():
    global loaded_model
    loaded_model = None
    if MODEL_ROLE not in ("champion", "candidate") or not re.fullmatch(
        r"models:/[^/@]+/[1-9][0-9]*", MODEL_URI
    ):
        raise ValueError("Configure a role and a concrete numbered MLflow model URI")
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
    try:
        loaded_model = mlflow.sklearn.load_model(MODEL_URI)
    except Exception as exc:  # noqa: BLE001 - loading failures must stop startup without exposing credentials
        raise RuntimeError(f"Registered model could not be loaded ({type(exc).__name__})") from None
    return loaded_model


@asynccontextmanager
async def lifespan(app):
    load_model_instance()
    yield


app = FastAPI(title=f"Model Arena {MODEL_ROLE}", lifespan=lifespan)


class PredictRequest(BaseModel):
    features: list[FiniteFloat] = Field(min_length=13, max_length=13)
    inject_fault: bool = False


class PredictResponse(BaseModel):
    prediction: int
    probabilities: list[float] | None
    model_version: str
    model_role: Literal["champion", "candidate"]


@app.get("/health/live")
def liveness():
    return {"status": "alive"}


@app.get("/health/ready")
def readiness():
    if loaded_model is None:
        raise HTTPException(503, "Configured model is not loaded")
    return {
        "ready": True,
        "model_role": MODEL_ROLE,
        "model_version": MODEL_URI,
        "model_type": type(loaded_model).__name__,
    }


@app.post("/predict", response_model=PredictResponse)
def predict(request: PredictRequest):
    if request.inject_fault:
        if os.getenv("ENABLE_DEMO_FAULTS", "false").lower() != "true" or MODEL_ROLE != "candidate":
            raise HTTPException(403, "Demo faults are disabled for this server")
        raise HTTPException(500, "Injected Candidate fault")
    if loaded_model is None:
        raise HTTPException(503, "Configured model is not loaded")
    features = np.asarray(request.features).reshape(1, -1)
    try:
        prediction = int(loaded_model.predict(features)[0])
        probabilities = (
            loaded_model.predict_proba(features)[0].tolist()
            if hasattr(loaded_model, "predict_proba")
            else None
        )
    except (ValueError, TypeError):
        raise HTTPException(400, "Invalid model input") from None
    return PredictResponse(
        prediction=prediction,
        probabilities=probabilities,
        model_version=MODEL_URI,
        model_role=MODEL_ROLE,
    )
