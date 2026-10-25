# Model Arena

**Model Arena** is an MLOps platform for safely releasing Machine Learning models using **Shadow Testing**, **Canary Rollouts**, and **Automatic Rollback**.

---

## Architecture Overview

```text
[ Next.js UI (:3000) ] ──► [ Nginx (:8080) ] ──► [ FastAPI Control API (:8000) ]
                                                        │              │
                                                        ▼              ▼
                                                [ Model Serving ]  [ RabbitMQ ]
                                               (Champion/Candidate)    │
                                                        ▲              ▼
                                                        │         [ Worker ]
                                                [ MLflow / DB ]
```

- **Frontend (`frontend/`):** Next.js & Bun operator control panel for managing rollouts and observing decisions.
- **Control API (`backend/control_api/`):** FastAPI prediction gateway that deterministically splits canary traffic and coordinates release decisions.
- **Model Serving (`backend/model_serving/`):** Version-pinned container loading models from the MLflow registry.
- **Worker (`backend/worker/`):** RabbitMQ consumer handling asynchronous shadow comparisons and delayed ground-truth feedback.
- **ML Pipeline (`backend/ml/`):** DVC reproducible pipeline training Scikit-learn models on the Wine classification dataset.
- **Infrastructure (`infra/`):** Docker Compose orchestration with PostgreSQL, RabbitMQ, MLflow (SQLite store), Prometheus, and Grafana.

---

## Rollout Policy & Rules

Release decisions follow 3 deterministic rules (documented in [`docs/rollout-policy.md`](docs/rollout-policy.md)):
1. **HOLD:** When fewer than 20 requests or feedback samples have been collected.
2. **ROLLBACK:** Triggered automatically if error rate > 5%, p95 latency > 200ms, or candidate accuracy drops > 5% below champion.
3. **PROMOTE:** When sample thresholds are met, latency and error rates are healthy, and candidate accuracy meets or exceeds champion.

---

## Local Quickstart

### Prerequisites
- **Docker & Docker Compose**
- **Bun** (for the Next.js frontend)
- **Python 3.12** (managed with `uv`)

### 1. Environment Setup
```bash
cp .env.example .env
# Edit .env with your desired passwords if needed
```

### 2. Start Backend & Infrastructure
```bash
# Start all core services, model servers, and observability tools
make stack-full
# Or via docker compose directly:
docker compose --profile serving --profile observability up --build -d
```

### 3. Start Frontend Dashboard
```bash
bun install
bun run dev
```
Open [http://localhost:3000](http://localhost:3000) to view the control panel.

---

## Security

Secret scanning is automated via GitHub Actions with GitGuardian. See [`SECURITY.md`](SECURITY.md). Never commit real credentials or `.env` files.
