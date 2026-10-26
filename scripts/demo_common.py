"""Shared demo inputs: held-out dataset labels exported by training."""

import json
import os
import random
import uuid
from pathlib import Path

GATEWAY = os.getenv("GATEWAY_URL", "http://localhost:8080")
DATA = Path(__file__).resolve().parents[1] / "backend/ml/models/evaluation.json"


def examples():
    if not DATA.exists():
        raise SystemExit(
            "Run make train first to export held-out inputs and true dataset labels"
        )
    return json.loads(DATA.read_text())


def post(client, path, body=None):
    response = client.post(GATEWAY + "/api/v1" + path, json=body or {})
    response.raise_for_status()
    return response.json()


def active(client):
    response = client.get(GATEWAY + "/api/v1/rollouts/active")
    response.raise_for_status()
    return response.json()


def send(client, row, client_id=None, fault=False):
    response = client.post(
        GATEWAY + "/api/v1/predict",
        json={
            "client_id": client_id or str(uuid.uuid4()),
            "features": row["features"],
            "inject_fault": fault,
        },
    )
    data = response.json()
    if response.status_code == 200:
        post(
            client,
            "/feedback",
            {
                "prediction_id": data["request_id"],
                "ground_truth_label": row["ground_truth_label"],
            },
        )
    return response.status_code, data


def sample(rows):
    return random.choice(rows)
