# Training pipeline

DVC owns dataset references and reproducible prepare/train/evaluate stages. MLflow records runs, metrics, artifacts, and registered model versions. The MLflow server runs from `infra/mlflow/`; serving deployments should resolve an alias to a concrete version and record that version.

Add the first stages to `dvc.yaml` when the dataset and evaluation metrics have been selected. Keep source data and trained artifacts out of Git; configure a DVC remote and MLflow artifact store for the chosen environment.
