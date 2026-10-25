# Control API

Owns prediction routing, rollout control endpoints, delayed feedback, and the audit API.

When the active rollout is `SHADOW`, `POST /api/v1/predict` persists and returns the
Champion result. A FastAPI background task then publishes a persistent JSON event
to the durable RabbitMQ queue `shadow_tasks` using publisher confirms. Candidate
inference never runs on the client response path. Other rollout states do not
publish shadow tasks.

The message contains `request_id`, `features`, `champion_pred`, and `candidate_url`.
Use the response's `request_id` as `prediction_id` when posting feedback:

```json
{"prediction_id": "<request_id from predict>", "ground_truth_label": 1}
```

`POST /api/v1/feedback` checks that the prediction exists (404 otherwise), records
the first label, and updates PostgreSQL `accuracy_counters` for the served model
and any completed shadow Candidate. Repeating the same label returns
`already_recorded`; changing it returns 409. If feedback arrives before the
comparison, the worker updates the Candidate counter when it commits the result.
Both paths lock the prediction row, preventing duplicate accounting under retries
and concurrent requests. PostgreSQL is required for these concurrency guarantees;
SQLite is supported for sequential local development and unit tests.

Feedback responses include correct/total/accuracy for each role. `GET /api/v1/metrics`
exposes these accuracies plus `champion_labeled_count` and `candidate_labeled_count`.
Missing labels produce `null` accuracy. Counters cover the lifetime of this database;
shadow comparisons do not increase the user-facing `candidate_requests` count.
The existing rollout decision engine remains unchanged and uses its own served
prediction queries.

Configuration comes from environment variables:

- `DATABASE_URL`: shared PostgreSQL SQLAlchemy URL (`postgresql+psycopg` driver).
- `RABBITMQ_URL`: defaults to `amqp://rabbitmq:5672/`; supply credentials through
  the environment for an authenticated broker. The current Compose API wiring does this.
- `CANDIDATE_URL`: full inference endpoint, default `http://model-candidate:8000/predict`.

The API startup creates the new `model_comparisons` and `accuracy_counters` tables
using the existing SQLAlchemy startup mechanism. For an existing database with
feedback, stop API and worker writes, create tables using the updated image, and
run the repeatable backfill before resuming:

```sh
docker compose stop control-api worker
docker compose build control-api worker
docker compose run --rm --no-deps control-api python -c 'import app.db.models; from app.db.session import Base, engine; Base.metadata.create_all(engine)'
docker compose run --rm --no-deps control-api python -m app.db.backfill_accuracy
docker compose up -d control-api worker
```

Historical duplicate feedback uses the earliest label. Fresh databases need no backfill.

The publisher is best effort after the HTTP response: broker errors are logged by
exception type and do not change the prediction response. An API crash before
publishing, or an unavailable broker, can lose a shadow task; there is no durable
outbox in this change. Do not treat a successful prediction as proof of a completed
comparison. Enable real model servers exposing `POST /predict` to collect actual
model evidence; the upstream serving app currently exposes liveness only, and the
gateway still has its pre-existing development prediction fallback.

Run tests from this directory with Python 3.12 and the project/dev dependencies:

```sh
python -m pytest -q
```

Set `TEST_DATABASE_URL` to a disposable PostgreSQL database to enable the concurrency
test. It creates and removes a unique schema. Also set `TEST_RABBITMQ_URL` to an
isolated broker/vhost to enable the real worker-process/HTTP integration test; it
uses the fixed `shadow_tasks` and `shadow_tasks.failed` queues, so do not use a
shared application vhost. These integration tests skip when their variables are absent.
