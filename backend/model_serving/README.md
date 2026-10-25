# Model Serving Service (Member 1)

Loads and serves a pinned model version for Scikit-learn Wine classification. Build this image once and run multiple instances configured with `MODEL_ROLE` (`champion` or `candidate`) and `MODEL_URI` (e.g. `models:/wine-classifier/1` or `models:/wine-classifier/2`).

## Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health/live` | Process liveness check (`{"status": "alive"}`) |
| `GET` | `/health/ready` | Readiness check confirming the model is loaded in memory |
| `POST` | `/predict` | Ingests 13 Wine features and returns predicted class and probabilities |

## Fault Injection (For Auto-Rollback Demo)

Send `"inject_fault": true` in the `POST /predict` JSON body:
```json
{
  "features": [13.2, 1.78, 2.14, 11.2, 100.0, 2.65, 2.76, 0.26, 1.28, 4.38, 1.05, 3.4, 1050.0],
  "inject_fault": true
}
```
This triggers an immediate **HTTP 500 error**, raising the candidate error rate above 5% and activating the automated rollback decision engine!

## Running Tests

```bash
uv run --with pytest --with fastapi --with httpx --with scikit-learn --with joblib --with numpy pytest backend/model_serving/tests -v
```
