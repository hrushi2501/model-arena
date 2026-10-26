"""Train on a reproducible split, register both models, and export exact version identities."""

import json
import os
from pathlib import Path

import mlflow
import mlflow.sklearn
import yaml
from mlflow.models import infer_signature
from sklearn.datasets import load_wine
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score
from sklearn.model_selection import train_test_split

BASE = Path(__file__).resolve().parent.parent


def train_and_evaluate():
    params = yaml.safe_load((BASE / "params.yaml").read_text())
    wine = load_wine()
    x_train, x_test, y_train, y_test = train_test_split(
        wine.data,
        wine.target,
        test_size=params["dataset"]["test_size"],
        random_state=params["dataset"]["random_state"],
        stratify=wine.target,
    )
    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5001"))
    mlflow.set_experiment("wine-classifier")
    metrics, versions = {}, {}
    for role, estimator in (
        ("champion", RandomForestClassifier),
        ("candidate", GradientBoostingClassifier),
    ):
        model = estimator(**params[role]).fit(x_train, y_train)
        prediction = model.predict(x_test)
        result = {
            "accuracy": float(accuracy_score(y_test, prediction)),
            "macro_f1": float(f1_score(y_test, prediction, average="macro")),
        }
        with mlflow.start_run(run_name=f"{role}-{estimator.__name__}"):
            mlflow.log_params(params[role])
            mlflow.log_metrics(result)
            info = mlflow.sklearn.log_model(
                model,
                name="model",
                serialization_format="cloudpickle",
                input_example=x_test[:1],
                signature=infer_signature(x_test, prediction),
            )
            registered = mlflow.register_model(info.model_uri, "wine-classifier")
        versions[role] = f"models:/wine-classifier/{registered.version}"
        metrics[role] = {**result, "model_type": estimator.__name__, "model_uri": versions[role]}
    output = BASE / "models"
    output.mkdir(exist_ok=True)
    (output / "evaluation.json").write_text(
        json.dumps(
            [
                {"features": x.tolist(), "ground_truth_label": int(y)}
                for x, y in zip(x_test, y_test, strict=True)
            ],
            indent=2,
        )
        + "\n"
    )
    (BASE / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    temporary = output / "versions.env.tmp"
    temporary.write_text(
        "".join(f"{role.upper()}_MODEL_URI={uri}\n" for role, uri in versions.items())
    )
    temporary.replace(output / "versions.env")
    print(json.dumps(metrics, indent=2))
    print("Registered identities saved to backend/ml/models/versions.env")
    return metrics


if __name__ == "__main__":
    train_and_evaluate()
