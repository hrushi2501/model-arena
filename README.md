# Model Arena

**Model Arena** is an enterprise-grade MLOps platform for safely releasing Machine Learning models into production using **Shadow Testing**, **Deterministic Canary Rollouts**, and **Autonomous Evidence-Based Rollback**.

---

## 🏛️ System Architecture

```text
                               ┌────────────────────────────────────────────────┐
                               │             Next.js UI (Port 3000)             │
                               └───────────────────────┬────────────────────────┘
                                                       │
                                                       ▼
                               ┌────────────────────────────────────────────────┐
                               │            Nginx Gateway (Port 8080)           │
                               └───────────────────────┬────────────────────────┘
                                                       │
                                                       ▼
                               ┌────────────────────────────────────────────────┐
                               │          FastAPI Control API (Port 8000)       │
                               │  - Deterministic Canary Traffic Splitter       │
                               │  - Safe Release Decision Engine                │
                               │  - Transactional Outbox Pattern                │
                               └───┬─────────────┬─────────────┬─────────────┬──┘
                                   │             │             │             │
                    Canary Traffic │             │ Shadow Copy │             │
                                   ▼             │             ▼             │
             ┌───────────────────────────┐       │      ┌──────────────┐     │
             │   Model Serving Runtimes  │       │      │   RabbitMQ   │     │
             │                           │       │      │ (Port 15672) │     │
             │  ┌─────────────────────┐  │       │      └──────┬───────┘     │
             │  │   Champion Model    │  │       │             │             │
             │  │   (Random Forest)   │  │       │             ▼             │
             │  └─────────────────────┘  │       │      ┌──────────────┐     │
             │  ┌─────────────────────┐  │       │      │ Shadow Queue │     │
             │  │   Candidate Model   │  │       │      │    Worker    │     │
             │  │ (Gradient Boosting) │  │       │      └──────┬───────┘     │
             │  └─────────────────────┘  │       │             │             │
             └─────────────┬─────────────┘       │             │             │
                           │                     ▼             ▼             │
                           │           ┌───────────────────────────────┐     │
                           │           │      PostgreSQL (Port 5433)   │     │
                           │           │  - Predictions & Feedback     │     │
                           │           │  - Comparisons & Audit Trail  │     │
                           │           └───────────────────────────────┘     │
                           ▼                                                 ▼
             ┌───────────────────────────┐                     ┌───────────────────────────┐
             │     MLflow Model Store    │                     │  Prometheus (9090) and    │
             │        (Port 5001)        │                     │   Grafana (Port 3001)     │
             └───────────────────────────┘                     └───────────────────────────┘
```

---

## 📦 Services and Components

| Service | Directory | Technology | Host Port | Description |
| :--- | :--- | :--- | :--- | :--- |
| **Frontend** | `frontend/` | Next.js 16, React 19, Bun | `3000` | Real-time operator dashboard to monitor rollouts, accuracy, and audit trails |
| **Control API** | `backend/control_api/` | FastAPI, Python 3.12, Uvicorn | `8000` | Gateway performing deterministic client routing, delayed feedback recording, and safety decisions |
| **Model Serving** | `backend/model_serving/` | FastAPI, Scikit-learn, Joblib | Internal | Version-pinned runtimes serving Champion (v1) and Candidate (v2) with fault injection support |
| **Shadow Worker**| `backend/worker/` | Python 3.12, HTTPX, Pika | Internal | Consumes shadow queue tasks, runs candidate inference asynchronously, records comparisons |
| **ML Pipeline** | `backend/ml/` | Scikit-learn, MLflow, DVC | N/A | Reproducible Wine dataset training script logging metrics & registering versioned models |
| **PostgreSQL** | Docker | Postgres 16 Alpine | `5433` | Persistence for predictions, delayed ground-truth feedback, comparisons, and audit log |
| **RabbitMQ** | Docker | RabbitMQ 3 Management Alpine | `15672` | Message broker decoupling user predictions from shadow candidate inference |
| **MLflow** | `infra/mlflow/` | MLflow 2.15 | `5001` | Artifact and model registry tracking experiments and artifact versions |
| **Prometheus** | Docker | Prometheus v3 | `9090` | Timeseries scraper pulling application metrics from `/metrics` |
| **Grafana** | `infra/grafana/` | Grafana 11 | `3001` | Pre-provisioned dashboards visualizing traffic rate, latency, error spikes, and canary share |

---

## 🚦 Release Policy & Decision Rules

The Release Decision Engine evaluates live health every request and makes one of 3 autonomous decisions:

1. **HOLD (Insufficient Evidence):**
   - Less than **20 predictions or labels** collected.
   - Traffic allocation remains frozen while data accumulates.
2. **ROLLBACK (Safety or Performance Breach):**
   - Automatically triggered if **Candidate Error Rate > 5%**, OR
   - **Candidate p95 Latency > 200 ms**, OR
   - **Candidate Accuracy drops > 5% below Champion**.
   - Instantly resets traffic to **0% Candidate** (100% Champion fallback) and creates an immutable audit record.
3. **PROMOTE (Safe & Confirmed Superiority):**
   - Triggered when minimum sample thresholds are satisfied, latency and error rates are healthy, and Candidate accuracy meets or exceeds Champion.
   - Candidate transitions to **100% traffic** and becomes the new baseline.

---

## 🚀 Quickstart Guide

### 1. Prerequisites
- **Docker & Docker Compose** (Desktop running)
- **Bun** (for Next.js frontend: `curl -fsSL https://bun.sh/install | bash`)
- **Python 3.12** (managed with `uv`)

### 2. Environment Setup
```bash
# Copy template and fill passwords
cp .env.example .env
```

### 3. Start Core Services
```bash
# Start all containers in background
docker compose --profile serving --profile observability up --build -d
```
*(Or use shortcut `make stack-full`)*

### 4. Start Next.js Frontend
```bash
bun install
bun run dev
```
Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## 📡 Key Endpoints & Usage

### 1. Predict (Inference Gateway)
```bash
curl -X POST http://localhost:8000/api/v1/predict \
  -H "Content-Type: application/json" \
  -d '{
    "client_id": "user-42",
    "features": [13.2, 1.78, 2.14, 11.2, 100.0, 2.65, 2.76, 0.26, 1.28, 4.38, 1.05, 3.4, 1050.0]
  }'
```
Response:
```json
{
  "request_id": "18f92b77-...",
  "prediction": 0,
  "served_by": "candidate",
  "probabilities": [0.94, 0.04, 0.02]
}
```

### 2. Submit Ground-Truth Feedback
```bash
curl -X POST http://localhost:8000/api/v1/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "prediction_id": "18f92b77-...",
    "ground_truth_label": 0
  }'
```

### 3. Advance Rollout (Canary Traffic Step)
```bash
curl -X POST http://localhost:8000/api/v1/rollouts/advance \
  -H "Content-Type: application/json" \
  -d '{"target_canary_percentage": 25.0}'
```

### 4. Trigger Instant Rollback
```bash
curl -X POST http://localhost:8000/api/v1/rollouts/rollback \
  -H "Content-Type: application/json" \
  -d '{"reason": "Manual operator intervention or regression detected"}'
```

---

## 🧪 Running Automated Tests

```bash
# Control API routing and decision engine unit tests
uv run pytest backend/control_api/tests/test_routing_and_decisions.py -v

# Model Serving verification tests
uv run pytest backend/model_serving/tests/test_serving.py -v

# Worker queue tests
uv run pytest backend/worker/tests/test_consumer.py -v
```

---

## 🎬 Live Demonstration Scripts

We provide two end-to-end Python demo scripts in `scripts/`:

```bash
# 1. Gradual Rollout Happy Path (5% -> 15% -> 50% -> 100% Full Promotion)
uv run --with httpx python3 scripts/demo_gradual_rollout.py

# 2. Safety & Fault Injection Auto-Rollback (Triggers 500 errors and auto-rollback)
uv run --with httpx python3 scripts/demo_traffic.py
```

---

## 📖 In-Depth Project Documentation

For a comprehensive A-to-Z explanation of every design decision, mathematical formula, Grafana panel interpretation, and the exact oral presentation walkthrough for tomorrow's demo, see:
👉 **[PROJECT_EXPLAINED.md](PROJECT_EXPLAINED.md)**
