# Control API & Safe Release Decision Engine (Member 2)

Owns prediction routing, deterministic canary traffic splitting, the 3-rule automated decision engine, database models, and the audit trail API.

## Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Redirects directly to `/docs` (Interactive Swagger UI) |
| `GET` | `/health/live` | Process liveness check |
| `POST` | `/api/v1/predict` | Routes prediction request deterministically to Champion/Candidate |
| `GET` | `/api/v1/rollouts/active` | Retrieves current rollout status and canary traffic percentage |
| `POST` | `/api/v1/rollouts/advance` | Steps up canary traffic percentage (10% -> 25% -> 50% -> 100%) |
| `POST` | `/api/v1/rollouts/rollback` | Emergency/automatic rollback reverting canary to 0% |
| `POST` | `/api/v1/rollouts/evaluate` | Evaluates metrics against the 3 deterministic rules |
| `POST` | `/api/v1/feedback` | Ingests ground-truth labels for real-time accuracy evaluation |
| `GET` | `/api/v1/audit` | Append-only audit trail of rollout transitions |
| `GET` | `/api/v1/metrics` | Real-time aggregate metrics for the dashboard |

## Safe Release Decision Engine Rules

1. **HOLD**: If candidate requests < 20, wait for statistical confidence.
2. **ROLLBACK**: If candidate error rate > 5%, p95 latency > 200ms, or accuracy drop > 5%, immediately revert canary traffic to 0% and write an audit event.
3. **PROMOTE**: If candidate error rate <= 5%, p95 latency <= 200ms, and accuracy is maintained, advance traffic towards 100%.

## Running Tests

```bash
uv run --with pytest --with fastapi --with httpx --with sqlalchemy pytest backend/control_api/tests -v
```
