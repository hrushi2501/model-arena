# Model Arena: Complete Project Deep-Dive & Architecture Guide

> **Safe Live Release of Machine Learning Models Using Shadow Testing, Deterministic Canary Rollouts, and Automated Rollback**

---

## Table of Contents
1. [The Core Problem: Why Does Model Arena Exist?](#1-the-core-problem-why-does-model-arena-exist)
2. [High-Level Architecture & Lifecycle Flow](#2-high-level-architecture--lifecycle-flow)
3. [The Core Mechanics: What, Why, and How](#3-the-core-mechanics-what-why-and-how)
   - [Phase 1: Multi-Version Model Serving & MLflow Registry](#phase-1-multi-version-model-serving--mlflow-registry)
   - [Phase 2: Asynchronous Shadow Testing (0% Blast Radius)](#phase-2-asynchronous-shadow-testing-0-blast-radius)
   - [Phase 3: Deterministic Canary Traffic Splitting](#phase-3-deterministic-canary-traffic-splitting)
   - [Phase 4: Autonomous Release Decision Engine (The 3 Rules)](#phase-4-autonomous-release-decision-engine-the-3-rules)
   - [Phase 5: Instant Automatic Rollback](#phase-5-instant-automatic-rollback)
   - [Phase 6: Delayed Ground-Truth Feedback Loop](#phase-6-delayed-ground-truth-feedback-loop)
   - [Phase 7: Immutable Audit Trail & Compliance](#phase-7-immutable-audit-trail--compliance)
4. [Component-by-Component Technical Breakdown](#4-component-by-component-technical-breakdown)
5. [Understanding the Outputs: What Each Metric & Screen Depicts](#5-understanding-the-outputs-what-each-metric--screen-depicts)
   - [API JSON Responses](#api-json-responses)
   - [Next.js Web UI Dashboard](#nextjs-web-ui-dashboard)
   - [Grafana Observability Dashboard](#grafana-observability-dashboard)
   - [MLflow Model Registry](#mlflow-model-registry)
6. [Tomorrow's Live Presentation & Demo Script](#6-tomorrows-live-presentation--demo-script)
7. [Frequently Asked Questions (Viva / Evaluation Q&A)](#7-frequently-asked-questions-viva--evaluation-qa)

---

## 1. The Core Problem: Why Does Model Arena Exist?

### The Traditional Software vs. Machine Learning Dilemma
In traditional software engineering, rolling out a new release (e.g., version 2.0 of an API) can be validated with deterministic unit tests, syntax linters, and integration suites. If the code compiles, passes tests, and doesn't crash, it usually works.

**In Machine Learning, code is only half the story.** 
A newly trained model might:
- Have a 99% accuracy score in offline Jupyter Notebook validation.
- Yet fail catastrophically in production due to **data distribution drift**, subtle feature scaling mismatches, or high latency spikes on complex inputs.
- Fail silently: Unlike normal software that throws a `500 Internal Server Error`, a degraded ML model continues to output clean `200 OK` JSON responses with garbage predictions.
- Suffer from sudden latency regressions (e.g., a deep gradient boosting tree taking 400ms instead of 10ms), degrading end-user experience.

### The Dangers of "All-at-Once" (Blue/Green) Deployment
If an organization swaps 100% of production traffic to a new model overnight:
1. 100% of users are exposed to potential errors immediately.
2. If the model misclassifies critical data, business loss is immediate.
3. Rolling back manually requires an engineer to detect the problem, debug dashboards, and push a rollback deployment, which can take hours.

### The Model Arena Solution
**Model Arena** solves this by establishing a **zero-risk, automated release pipeline**:
1. **Never blind-swap:** Models first run in **Shadow Mode** (duplicated traffic in the background without user impact).
2. **Deterministic Canary:** Traffic is shifted gradually (5% → 15% → 50% → 100%) so that a single user consistently interacts with the same model version.
3. **Automated Evidence-Based Decisions:** An autonomous engine continuously calculates error rates, p95 latency, and ground-truth accuracy.
4. **Sub-Second Auto-Rollback:** If latency spikes above 200ms or error rates exceed 5%, the system immediately pulls the candidate and returns 100% of traffic to the champion within milliseconds.

---

## 2. High-Level Architecture & Lifecycle Flow

```text
               ┌────────────────────────────────────────────────────────┐
               │                 Incoming User Request                  │
               │         {"client_id": "u-12", "features": [...]}       │
               └───────────────────────────┬────────────────────────────┘
                                           │
                                           ▼
               ┌────────────────────────────────────────────────────────┐
               │               Control API Gateway (:8000)              │
               │   1. Inspect Rollout State (READY, SHADOW, CANARY)     │
               │   2. Deterministic Hash Bucketing: SHA256(client_id)   │
               └───────────┬────────────────────────────────┬───────────┘
                           │                                │
            Served Traffic │                 Shadow Traffic │ (Only in SHADOW mode)
                           ▼                                ▼
         ┌──────────────────────────────────┐   ┌───────────────────────────────┐
         │     Model Serving Containers     │   │   Transactional Outbox DB     │
         │  ┌────────────────────────────┐  │   │   (Committed in same ACID tx) │
         │  │ Champion: RandomForest (v1)│  │   └───────────────┬───────────────┘
         │  └────────────────────────────┘  │                   │
         │  ┌────────────────────────────┐  │                   ▼
         │  │ Candidate: GradBoost (v2)  │  │   ┌───────────────────────────────┐
         │  └────────────────────────────┘  │   │       RabbitMQ Broker         │
         └─────────────────┬────────────────┘   │        `shadow_tasks`         │
                           │                    └───────────────┬───────────────┘
                           ▼                                    │
         ┌──────────────────────────────────┐                   ▼
         │    Immediate Prediction to User  │   ┌───────────────────────────────┐
         │     {"prediction": 0, ...}       │   │      Shadow Queue Worker      │
         └─────────────────┬────────────────┘   │  - Evaluates Candidate async  │
                           │                    │  - Records comparison in DB   │
                           │                    └───────────────┬───────────────┘
                           ▼                                    │
         ┌──────────────────────────────────┐                   │
         │       Delayed Feedback API       │                   │
         │   {"prediction_id": "...",       │                   │
         │    "ground_truth_label": 0}      │                   │
         └─────────────────┬────────────────┘                   │
                           │                                    │
                           ▼                                    ▼
         ┌──────────────────────────────────────────────────────────────┐
         │             PostgreSQL 16 Database Storage                   │
         │  - Predictions, Feedback, Comparisons, Audit Events          │
         └──────────────────────────────┬───────────────────────────────┘
                                        │
                                        ▼
         ┌──────────────────────────────────────────────────────────────┐
         │              Autonomous Decision Engine                      │
         │  Evaluates: Samples >= 20, Error Rate, p95 Latency, Accuracy │
         │  Output: HOLD ──► PROMOTE ──► Or Instant ROLLBACK            │
         └──────────────────────────────┬───────────────────────────────┘
                                        │
                         ┌──────────────┴──────────────┐
                         ▼                             ▼
         ┌──────────────────────────────┐ ┌─────────────────────────────┐
         │     Prometheus & Grafana     │ │      Next.js Frontend       │
         │   Live Real-Time Telemetry   │ │   Operator Control Panel    │
         └──────────────────────────────┘ └─────────────────────────────┘
```

---

## 3. The Core Mechanics: What, Why, and How

### Phase 1: Multi-Version Model Serving & MLflow Registry
- **What is done:** Two isolated model instances run simultaneously in Docker:
  - `model-champion`: Runs Model Version 1 (Random Forest Classifier, 100 trees, 97.2% offline accuracy).
  - `model-candidate`: Runs Model Version 2 (Gradient Boosting Classifier, 100 trees, 94.4% offline accuracy).
- **Why it is done:** Traditional setups replace the server image. Model Arena decouples models into independent, containerized microservices. Neither model can crash the other.
- **How it is done:** Each model container runs FastAPI. It loads its pinned weights from disk/MLflow on startup. It exposes:
  - `GET /health/live`: Fast process liveness check.
  - `GET /health/ready`: Confirms weights are loaded in memory.
  - `POST /predict`: Ingests features and returns class and probability distributions.
  - `inject_fault`: A parameter allowing engineers to simulate latency or 500 errors to test failover.

---

### Phase 2: Asynchronous Shadow Testing (0% Blast Radius)
- **What is done:** When a model is in `SHADOW` state:
  1. The user request is sent directly to the Champion.
  2. The Champion's prediction is returned immediately to the user (zero added latency).
  3. A duplicate of the request payload is saved to the PostgreSQL `shadow_outbox` table in the *same ACID transaction* as the prediction.
  4. An asynchronous outbox dispatcher publishes the payload to RabbitMQ (`shadow_tasks`).
  5. The `worker` background process consumes the message, calls the Candidate model, and logs whether Champion and Candidate agreed into `model_comparisons`.
- **Why it is done:** 
  - Zero user-facing blast radius: If the candidate crashes, times out, or hallucinates, the real user never sees it.
  - We verify candidate inference latency under actual production traffic patterns before trusting it with a single real user.
- **Why the Transactional Outbox Pattern?** 
  If the API published directly to RabbitMQ inside the HTTP request handler, a broker network glitch would either crash the user's prediction or lose the shadow task. The Transactional Outbox pattern guarantees **at-least-once durable delivery**.

---

### Phase 3: Deterministic Canary Traffic Splitting
- **What is done:** When a rollout advances to `CANARY` (e.g., 25% traffic share):
  - 25% of requests go to Candidate.
  - 75% go to Champion.
- **Why not simple random splitting (`random.random() < 0.25`)?**
  **Random splitting is dangerous in production.** If a single user makes 5 consecutive API calls, random splitting might route call 1 to Candidate, call 2 to Champion, call 3 to Candidate. If the models produce differing outputs, the user experiences jarring UI flicker and inconsistent behavior.
- **How it is done (Deterministic Client Bucketing):**
  We use cryptographic SHA-256 hash bucketing:
  $$\text{bucket} = \frac{\text{int}(\text{SHA256}(\text{client\_id})[0:8], 16) \pmod{10000}}{100.0}$$
  - This maps any string `client_id` (e.g., `"user-42"`) to a deterministic number between `0.00` and `99.99`.
  - If the canary threshold is `25.0%`, all clients with a bucket value `< 25.0` are routed to Candidate.
  - **Result:** `"user-42"` will *always* talk to Candidate, while `"user-108"` will *always* talk to Champion throughout that stage.

---

### Phase 4: Autonomous Release Decision Engine (The 3 Rules)
Every time traffic passes through the gateway, or when ground-truth labels arrive, the **Decision Engine** evaluates the safety of the candidate model. It enforces **3 deterministic rules**:

```text
                                  ┌───────────────────────────┐
                                  │   Evaluate Active State   │
                                  └─────────────┬─────────────┘
                                                │
                                                ▼
                                   [ Total Samples < 20? ]
                                   ├─── YES ───► Decision: HOLD (Gathering data)
                                   │
                                   └─── NO
                                        │
                                        ▼
             [ Error Rate > 5% OR p95 Latency > 200ms OR Candidate Acc < Champion Acc - 5%? ]
             ├─── YES ───► Decision: ROLLBACK (Safety Breach Detected!)
             │
             └─── NO
                  │
                  ▼
             [ Candidate Accuracy >= Champion Accuracy AND Health Clean? ]
             ├─── YES ───► Decision: PROMOTE (Candidate is Superior/Equal)
             │
             └─── NO ───► Decision: HOLD (Keep monitoring)
```

#### Detailed Rule Breakdown:
1. **Rule 1: HOLD (Insufficient Evidence)**
   - **Condition:** Total candidate predictions $< 20$ OR total labeled feedback samples $< 20$.
   - **Reasoning:** In statistical testing, small sample sizes suffer from high variance. Deciding on 3 samples would cause false alarms.
2. **Rule 2: ROLLBACK (Safety or Performance Breach)**
   - **Breach 1 (Error Rate):** $\frac{\text{HTTP 500 or Exceptions}}{\text{Total Candidate Requests}} > 0.05$ (5%).
   - **Breach 2 (Latency Breach):** 95th-percentile inference latency $> 200\text{ ms}$.
   - **Breach 3 (Accuracy Regression):** $\text{Acc}_{\text{candidate}} < \text{Acc}_{\text{champion}} - 0.05$ (Candidate is $>5\%$ worse than Champion).
   - **Action:** Instantly execute `ROLLBACK`. Set Candidate traffic to `0%`. Route 100% back to Champion. Log immutable audit entry.
3. **Rule 3: PROMOTE (Candidate Approved)**
   - **Condition:** Samples $\ge 20$, Error Rate $\le 5\%$, Latency acceptable, and $\text{Acc}_{\text{candidate}} \ge \text{Acc}_{\text{champion}}$.
   - **Action:** Candidate is promoted. When reaching 100%, the Candidate officially becomes the new Champion!

---

### Phase 5: Instant Automatic Rollback
- **What is done:** If a rollback condition is triggered, the rollback executes in **< 1 millisecond** in code without waiting for human intervention.
- **Why it is done:** In production ML (credit scoring, autonomous systems, medical diagnosis, e-commerce pricing), an error state continuing for 10 minutes can cause irreparable business damage.
- **How it is done:** The Decision Engine writes an atomic update to PostgreSQL:
  - Sets rollout status to `ROLLED_BACK`.
  - Sets canary percentage to `0.0`.
  - Records an append-only row in `audit_events` with the exact trigger reason and timestamp.
  - Emits Prometheus metric `model_arena_rollback_events_total`.

---

### Phase 6: Delayed Ground-Truth Feedback Loop
- **What is done:** Machine Learning accuracy cannot be determined at inference time because the real-world answer (ground truth) is not yet known!
  - Example: An ML model predicts whether a loan will default. We only know if the loan defaulted months later.
  - Example: A recommendation system predicts what a user will buy. We only know when the user actually checks out.
- **How Model Arena handles it:**
  1. Every prediction returns a unique `request_id` (UUID).
  2. When ground-truth arrives later, the external system calls `POST /api/v1/feedback`:
     ```json
     {"prediction_id": "18f92b77-...", "ground_truth_label": 0}
     ```
  3. The system matches the label to the historical prediction and updates the running accuracy counters for Champion and Candidate.

---

### Phase 7: Immutable Audit Trail & Compliance
- **What is done:** Every administrative action, rollout advance, traffic split change, and automated rollback is written to an immutable `audit_events` table.
- **Why it is done:** Essential for regulatory compliance (EU AI Act, financial audits, SOC 2). An auditor can inspect the exact second a model was promoted or rolled back and see the mathematical metrics that caused the decision.

---

## 4. Component-by-Component Technical Breakdown

| Component | Tech Stack | Role in System |
| :--- | :--- | :--- |
| `backend/control_api` | FastAPI, Python 3.12, SQLAlchemy | Central gateway. Handles HTTP routing, SHA-256 traffic splitting, Decision Engine, and Outbox. |
| `backend/model_serving` | FastAPI, Scikit-learn, Joblib | Serves pinned `.joblib` model binaries. One container for Champion, one for Candidate. |
| `backend/worker` | Python 3.12, Pika, HTTPX | Consumes RabbitMQ `shadow_tasks`. Executes candidate inference in background, saves comparisons. |
| `backend/ml` | Scikit-learn, MLflow, DVC | Trains Random Forest and Gradient Boosting models on the 13-feature Wine dataset and logs to MLflow. |
| `frontend` | Next.js 16 (App Router), React 19, Bun | Live web dashboard displaying active rollout progress, accuracy charts, and audit events. |
| `infra/nginx` | Nginx Alpine | Reverse proxy on port `8080` routing frontend and API calls. |
| `infra/mlflow` | MLflow 2.15 | Tracking server on port `5001`. Stores model runs, metrics, parameters, and model artifacts. |
| `infra/prometheus` | Prometheus v3 | Pulls metrics every 15s from `control-api:8000/metrics`. |
| `infra/grafana` | Grafana 11 | Visualizes latency histograms, request rates, error spikes, and canary traffic on port `3001`. |
| `postgres` | PostgreSQL 16 Alpine | Relational database on port `5433` (mapped from 5432 to prevent macOS port conflicts). |
| `rabbitmq` | RabbitMQ 3 Management | Queue broker on ports `5672` (AMQP) and `15672` (Web UI). |

---

## 5. Understanding the Outputs: What Each Metric & Screen Depicts

### API JSON Responses

#### 1. Prediction Output (`POST /api/v1/predict`)
```json
{
  "request_id": "8f89e27c-0b86-4f40-8bca-f0331070624e",
  "prediction": 0,
  "served_by": "candidate",
  "probabilities": [0.9412, 0.0381, 0.0207]
}
```
- `request_id`: Unique UUID representing this inference event. Used later to submit ground-truth feedback.
- `prediction`: The predicted wine class (Class 0, 1, or 2).
- `served_by`: Explains which model actually answered the user (`"champion"` or `"candidate"`).
- `probabilities`: The model's confidence distribution across the 3 wine classes.

#### 2. Rollout Status Output (`GET /api/v1/rollouts/status`)
```json
{
  "status": "CANARY",
  "canary_percentage": 25.0,
  "champion_model_uri": "models:/wine-classifier/1",
  "candidate_model_uri": "models:/wine-classifier/2",
  "metrics": {
    "total_predictions": 84,
    "candidate_requests": 21,
    "champion_requests": 63,
    "champion_accuracy": 0.968,
    "candidate_accuracy": 0.952,
    "candidate_error_rate": 0.0,
    "candidate_p95_latency_ms": 12.4
  },
  "recommendation": "PROMOTE"
}
```
- `status`: Current lifecycle phase (`READY`, `SHADOW`, `CANARY`, `PROMOTED`, or `ROLLED_BACK`).
- `canary_percentage`: The exact share of live user traffic currently reaching the candidate.
- `metrics`: Live operational measurements aggregated across the database.
- `recommendation`: What the Decision Engine currently recommends (`HOLD`, `PROMOTE`, or `ROLLBACK`).

---

### Next.js Web UI Dashboard (`http://localhost:3000`)
- **Rollout Status Header:** Displays active badge (`CANARY - 25% Traffic`).
- **Live Traffic Split Bar:** A visual horizontal bar showing purple (Champion %) vs. green (Candidate %).
- **Accuracy Comparison Cards:** Live cards showing Champion Accuracy (e.g. 96.8%) vs. Candidate Accuracy (e.g. 95.2%).
- **Recent Shadow Comparisons Table:** Shows the latest background requests, displaying whether Champion and Candidate predictions matched (`MATCH` or `DIFF`).
- **Immutable Audit Trail:** An append-only log showing timestamped records of every transition, rollout step, and rollback trigger.

---

### Grafana Observability Dashboard (`http://localhost:3001`)

| Panel Name | What it Displays | What to Understand From It |
| :--- | :--- | :--- |
| **Request Throughput (req/s)** | Line chart of incoming `/predict` requests per second. | Shows traffic volume and confirms live load is reaching the cluster. |
| **P95 Latency (ms)** | 95th-percentile inference response time. | Normal healthy latency is **8ms – 25ms**. If this line climbs above **200ms**, the Decision Engine triggers a latency rollback. |
| **Candidate Error Rate (%)** | Fraction of candidate requests failing. | Stays at **0%** during normal operations. When faults are injected, spikes to **100%**, demonstrating why rollback was triggered. |
| **Canary Traffic Percentage** | Gauge showing current traffic share (0% → 100%). | Visually steps up (5% → 15% → 50% → 100%) during promotion, or drops instantly to 0% during rollback. |

---

### MLflow Model Registry (`http://localhost:5001`)
- **Experiment `wine-classifier`:** Contains all historical model training runs.
- **Run Details:** Shows offline training parameters (`n_estimators=100`, `max_depth=5`) and validation metrics (`accuracy=0.972`, `f1_score=0.971`).
- **Models Tab (`wine-classifier`):**
  - **Version 1:** Pinned as the production **Champion**.
  - **Version 2:** Pinned as the release **Candidate**.

---

## 6. Tomorrow's Live Presentation & Demo Script

Follow this step-by-step walkthrough in front of your professor or evaluator.

### Step 0: Pre-Flight Check (2 minutes before presentation)
Ensure all 10 Docker containers and the frontend are running:
```bash
docker compose ps
```
Open three browser tabs:
1. **Frontend UI:** `http://localhost:3000`
2. **Grafana Dashboard:** `http://localhost:3001` (login: `admin` / password from `.env`)
3. **MLflow Registry:** `http://localhost:5001`

---

### Step 1: Introduction & System Tour (3 minutes)
1. **Explain the Motivation:**
   > *"Professor, deploying ML models directly into production is risky because models can suffer from silent degradation or latency spikes. We built **Model Arena**—a local-first MLOps platform that safely releases models using Shadow Testing, Deterministic Canary Rollouts, and Autonomous Rollback."*
2. **Show the MLflow Registry (`http://localhost:5001`):**
   - Point out the `wine-classifier` model registry.
   - Show **Version 1** (Champion - Random Forest) and **Version 2** (Candidate - Gradient Boosting).
3. **Show the UI Dashboard (`http://localhost:3000`):**
   - Point out the current rollout state, model URIs, and the live audit log.

---

### Step 2: Demonstrate Happy Path — Gradual Canary Rollout to 100% (4 minutes)
1. Tell the professor:
   > *"Now, we will demonstrate a safe rollout where the candidate performs well. Traffic will be gradually diverted: 5% → 15% → 50% → 100% (Full Promotion)."*
2. In your terminal, run the gradual rollout script:
   ```bash
   uv run --with httpx python3 scripts/demo_gradual_rollout.py
   ```
3. **What to show in the UI:**
   - Watch the traffic bar move: 5% → 15% → 50% → 100%.
   - Explain deterministic hashing:
     > *"Notice that each client ID consistently reaches the same model. We use SHA-256 client bucketing, not random assignment, so individual users never experience flip-flopping predictions."*
   - Show the final state: **PROMOTED (100% Traffic)**.

---

### Step 3: Demonstrate Safety Failure & Automatic Instant Rollback (4 minutes)
1. Tell the professor:
   > *"Now we will demonstrate the core safety mechanism. What happens if the candidate model starts throwing internal server errors or latency regressions?"*
2. In your terminal, run the traffic fault injection script:
   ```bash
   uv run --with httpx python3 scripts/demo_traffic.py
   ```
3. **What happens during this script:**
   - The script sets canary traffic to 35%.
   - It sends healthy requests to establish baseline data.
   - It then injects simulated faults (`"inject_fault": true`) into the candidate model.
   - The candidate error rate jumps to > 5%.
   - **The Decision Engine triggers an instant automatic rollback!**
4. **What to show on screen:**
   - **Frontend UI:** The status badge instantly switches to **`ROLLED_BACK`**, and canary traffic drops to **0%**.
   - **Audit Log Table:** Point out the new immutable audit event:
     `"Automatic rollback triggered: Candidate error rate breached 5.0% threshold"`.
   - **Grafana (`http://localhost:3001`):** Point to the Error Rate spike and the canary traffic gauge dropping to 0.
   - Highlight the key point:
     > *"No human had to wake up or press a button. The system protected users automatically in milliseconds."*

---

## 7. Frequently Asked Questions (Viva / Evaluation Q&A)

### Q1: Why did you use PostgreSQL instead of SQLite in production?
> **Answer:** SQLite locks the entire database file during writes, which bottlenecks concurrent web traffic. PostgreSQL provides row-level locking (`FOR UPDATE SKIP LOCKED`) and ACID transactions, which allows our API to commit user predictions and shadow outbox events in a single atomic transaction without deadlocks.

### Q2: Why is the shadow worker asynchronous through RabbitMQ?
> **Answer:** If we called the candidate model synchronously during the user's prediction request, any delay or crash in the candidate would slow down or fail the real user's response. By publishing the shadow request to RabbitMQ via the Transactional Outbox pattern, user latency remains unaffected (0% blast radius).

### Q3: Why is random traffic splitting bad for canary releases?
> **Answer:** If a user makes 5 requests in a row, random splitting might send request 1 to Candidate, request 2 to Champion, and request 3 to Candidate. If the models differ, the user experiences jarring inconsistencies. We use deterministic SHA-256 hash bucketing so each client ID is deterministically assigned to one model for the duration of the rollout stage.

### Q4: On what exact basis is a model promoted or rolled back?
> **Answer:** Our Decision Engine enforces three rules:
> 1. **HOLD:** When sample count is $< 20$ (prevents decisions on statistically insignificant data).
> 2. **ROLLBACK:** When Candidate error rate $> 5\%$, p95 latency $> 200\text{ ms}$, or Candidate accuracy drops $> 5\%$ below Champion.
> 3. **PROMOTE:** When sample count $\ge 20$, health metrics are clean, and Candidate accuracy meets or exceeds Champion.

### Q5: How do you measure accuracy in real-time when labels aren't available at prediction time?
> **Answer:** Predictions return a unique UUID `request_id`. Later, when ground truth is known, the feedback service matches the label against the recorded prediction ID and updates accuracy counters dynamically without mutating past prediction records.

### Q6: What happens if RabbitMQ or the Worker crashes?
> **Answer:** We implemented the **Transactional Outbox pattern**. The shadow event is saved directly into PostgreSQL alongside the prediction. If RabbitMQ is down, the events wait safely in the database. When RabbitMQ reconnects, the outbox dispatcher automatically drains and publishes pending events. No data is lost.
