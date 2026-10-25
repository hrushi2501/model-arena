"""Train Champion and Candidate classifiers on Scikit-learn Wine dataset,
evaluate performance metrics, serialize models locally, and log to MLflow.
"""

import json
import logging
import os
from pathlib import Path
import joblib
import yaml
from sklearn.datasets import load_wine
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ml_train")

BASE_DIR = Path(__file__).resolve().parent.parent
PARAMS_PATH = BASE_DIR / "params.yaml"
METRICS_PATH = BASE_DIR / "metrics.json"
MODELS_DIR = BASE_DIR / "models"
SERVING_MODELS_DIR = BASE_DIR.parent / "model_serving" / "models"


def load_params() -> dict:
    if PARAMS_PATH.exists():
        with open(PARAMS_PATH, "r") as f:
            return yaml.safe_load(f)
    return {
        "dataset": {"test_size": 0.2, "random_state": 42},
        "champion": {"n_estimators": 100, "random_state": 42},
        "candidate": {"n_estimators": 100, "random_state": 42},
    }


def train_and_evaluate():
    params = load_params()
    ds_params = params.get("dataset", {})
    champ_params = params.get("champion", {})
    cand_params = params.get("candidate", {})

    test_size = float(ds_params.get("test_size", 0.2))
    random_state = int(ds_params.get("random_state", 42))

    logger.info("Loading Scikit-learn Wine dataset...")
    data = load_wine()
    X, y = data.data, data.target
    feature_names = data.feature_names
    target_names = [str(t) for t in data.target_names]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=test_size, random_state=random_state, stratify=y
    )
    logger.info(f"Dataset split: {len(X_train)} train samples, {len(X_test)} test samples, 13 features.")

    # 1. Train Champion: Random Forest
    logger.info("Training Champion model (RandomForestClassifier)...")
    champion = RandomForestClassifier(
        n_estimators=int(champ_params.get("n_estimators", 100)),
        random_state=int(champ_params.get("random_state", 42)),
    )
    champion.fit(X_train, y_train)
    champ_preds = champion.predict(X_test)
    champ_acc = float(accuracy_score(y_test, champ_preds))
    champ_f1 = float(f1_score(y_test, champ_preds, average="macro"))
    logger.info(f"Champion -> Accuracy: {champ_acc:.4f}, Macro-F1: {champ_f1:.4f}")

    # 2. Train Candidate: Gradient Boosting
    logger.info("Training Candidate model (GradientBoostingClassifier)...")
    candidate = GradientBoostingClassifier(
        n_estimators=int(cand_params.get("n_estimators", 100)),
        random_state=int(cand_params.get("random_state", 42)),
    )
    candidate.fit(X_train, y_train)
    cand_preds = candidate.predict(X_test)
    cand_acc = float(accuracy_score(y_test, cand_preds))
    cand_f1 = float(f1_score(y_test, cand_preds, average="macro"))
    logger.info(f"Candidate -> Accuracy: {cand_acc:.4f}, Macro-F1: {cand_f1:.4f}")

    # 3. Save serialized models locally (.joblib) for offline & docker fallback
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    SERVING_MODELS_DIR.mkdir(parents=True, exist_ok=True)

    joblib.dump(champion, MODELS_DIR / "champion.joblib")
    joblib.dump(candidate, MODELS_DIR / "candidate.joblib")
    joblib.dump(champion, SERVING_MODELS_DIR / "champion.joblib")
    joblib.dump(candidate, SERVING_MODELS_DIR / "candidate.joblib")
    logger.info(f"Serialized models saved to {MODELS_DIR} and {SERVING_MODELS_DIR}")

    # 4. Save evaluation metrics
    metrics = {
        "champion": {
            "model_type": "random_forest",
            "accuracy": round(champ_acc, 4),
            "macro_f1": round(champ_f1, 4),
            "n_estimators": int(champ_params.get("n_estimators", 100)),
        },
        "candidate": {
            "model_type": "gradient_boosting",
            "accuracy": round(cand_acc, 4),
            "macro_f1": round(cand_f1, 4),
            "n_estimators": int(cand_params.get("n_estimators", 100)),
        },
        "dataset": {
            "name": "wine",
            "train_samples": len(X_train),
            "test_samples": len(X_test),
            "features_count": len(feature_names),
        },
    }
    with open(METRICS_PATH, "w") as f:
        json.dump(metrics, f, indent=2)
    logger.info(f"Metrics saved to {METRICS_PATH}")

    # 5. MLflow Tracking & Registry (graceful if MLflow server is offline)
    try:
        import mlflow
        import mlflow.sklearn

        tracking_uri = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment("wine-classifier")

        # Log Champion run
        with mlflow.start_run(run_name="champion-random-forest"):
            mlflow.log_params(champ_params)
            mlflow.log_metric("accuracy", champ_acc)
            mlflow.log_metric("macro_f1", champ_f1)
            mlflow.sklearn.log_model(
                sk_model=champion,
                name="model",
                serialization_format="cloudpickle",
                registered_model_name="wine-classifier",
            )
        logger.info("Champion logged and registered to MLflow as wine-classifier")

        # Log Candidate run
        with mlflow.start_run(run_name="candidate-gradient-boosting"):
            mlflow.log_params(cand_params)
            mlflow.log_metric("accuracy", cand_acc)
            mlflow.log_metric("macro_f1", cand_f1)
            mlflow.sklearn.log_model(
                sk_model=candidate,
                name="model",
                serialization_format="cloudpickle",
                registered_model_name="wine-classifier",
            )
        logger.info("Candidate logged and registered to MLflow as wine-classifier")
    except Exception as e:
        logger.info(f"MLflow server not reachable ({e}). Local training and joblib artifacts succeeded.")

    return metrics


if __name__ == "__main__":
    train_and_evaluate()
