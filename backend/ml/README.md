# ML Training Pipeline (Member 1)

Trains Champion (`RandomForestClassifier`, 100 estimators) and Candidate (`GradientBoostingClassifier`, 100 estimators) models on the Scikit-learn Wine classification dataset.

## Running Training

```bash
uv run --with scikit-learn --with joblib --with pyyaml --with numpy python3 backend/ml/src/train.py
```

Outputs:
- Serialized local model binaries: `backend/ml/models/champion.joblib` and `backend/ml/models/candidate.joblib`
- Copied for model serving: `backend/model_serving/app/models/`
- Evaluation metrics: `backend/ml/metrics.json`
- Registered in MLflow Model Registry as `wine-classifier` (Version 1 = Champion, Version 2 = Candidate) when MLflow is reachable.
