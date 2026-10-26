"""Deterministic routing and honest, identity-checked model responses."""

import hashlib
import os
import time
import uuid
from typing import Literal

import httpx
from pydantic import BaseModel, Field, FiniteFloat

CHAMPION_URL = os.getenv("CHAMPION_URL", "http://model-champion:8000/predict")
CANDIDATE_URL = os.getenv("CANDIDATE_URL", "http://model-candidate:8000/predict")


class ModelResult(BaseModel):
    prediction: int = Field(strict=True, ge=0, le=2)
    probabilities: list[FiniteFloat] | None = None
    model_version: str
    model_role: Literal["champion", "candidate"]


def determine_serving_role(client_id, rollout):
    if rollout.state == "PROMOTED":
        return "candidate", CANDIDATE_URL
    if rollout.state == "CANARY":
        key = f"{rollout.id}:{client_id or uuid.uuid4()}"
        fraction = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big") / 2**64
        if fraction < rollout.canary_percentage:
            return "candidate", CANDIDATE_URL
    return "champion", CHAMPION_URL


async def forward_prediction(role, target_url, features, model_version, inject_fault=False):
    start = time.perf_counter()
    error, status = None, 200
    result = {
        "prediction": None,
        "probabilities": None,
        "model_version": model_version,
        "model_role": role,
    }
    try:
        async with httpx.AsyncClient(timeout=2.0, follow_redirects=False) as client:
            response = await client.post(
                target_url, json={"features": features, "inject_fault": inject_fault}
            )
            response.raise_for_status()
            model = ModelResult.model_validate(response.json())
            if model.model_version != model_version or model.model_role != role:
                raise ValueError("Model identity mismatch")
            result = model.model_dump()
    except httpx.TimeoutException:
        error, status = "Model inference timed out", 504
    except httpx.HTTPStatusError:
        error, status = "Model server rejected inference", 502
    except httpx.RequestError:
        error, status = "Model server unavailable", 503
    except ValueError:
        error, status = "Invalid model response or model identity mismatch", 502
    return {
        **result,
        "status_code": status,
        "error": error,
        "latency_ms": round((time.perf_counter() - start) * 1000, 2),
    }


async def model_status(role, url, expected_version):
    status = {
        "role": role,
        "expected_version": expected_version,
        "ready": False,
        "model_version": None,
        "model_type": None,
    }
    try:
        async with httpx.AsyncClient(timeout=2.0, follow_redirects=False) as client:
            response = await client.get(url.rsplit("/", 1)[0] + "/health/ready")
            response.raise_for_status()
            data = response.json()
            status.update(
                model_version=data.get("model_version"), model_type=data.get("model_type")
            )
            status["ready"] = (
                data.get("ready") is True
                and data.get("model_role") == role
                and data.get("model_version") == expected_version
            )
    except (httpx.HTTPError, ValueError, AttributeError):
        pass
    return status
