"""Runtime identities shared by routing, evidence, and rollout initialization."""

import os
import re

CHAMPION_VERSION = os.getenv("CHAMPION_MODEL_URI", "models:/wine-classifier/1")
CANDIDATE_VERSION = os.getenv("CANDIDATE_MODEL_URI", "models:/wine-classifier/2")
PINNED_MODEL = re.compile(r"models:/[^/@]+/[1-9][0-9]*")


def demo_faults_enabled():
    return os.getenv("ENABLE_DEMO_FAULTS", "false").lower() == "true"


def validate_model_versions():
    if not all(PINNED_MODEL.fullmatch(v) for v in (CHAMPION_VERSION, CANDIDATE_VERSION)):
        raise ValueError("Configure concrete numbered Champion and Candidate model URIs")
    if CHAMPION_VERSION == CANDIDATE_VERSION:
        raise ValueError("Champion and Candidate must be different registered versions")
