# Control API

When a rollout is `SHADOW`, `POST /api/v1/predict` commits the Champion prediction
and its pending event in one PostgreSQL transaction, then returns the result.
The HTTP handler never connects to RabbitMQ or waits for Candidate inference.
A separate dispatcher publishes the saved event to durable `shadow_tasks`.
Other rollout states create no shadow event. Events contain `request_id`,
`features`, `champion_pred`, and `candidate_url`.

Use the prediction response's `request_id` as the feedback `prediction_id`:

```json
{"prediction_id": "<request_id from predict>", "ground_truth_label": 1}
```

`POST /api/v1/feedback` returns 404 for unknown predictions. The first label is
immutable: an identical retry returns `already_recorded`, and a different label
returns 409. PostgreSQL prediction row locks serialize concurrent feedback writes.
SQLite supports sequential development and unit tests.

Feedback responses include correct/total/accuracy for Champion and Candidate.
`GET /api/v1/metrics` exposes the same accuracies and labeled counts. A single SQL
query computes the running counters from committed predictions, first feedback
labels, and shadow comparisons. This includes historical feedback automatically,
handles either arrival order, and excludes duplicate legacy labels and unlabeled
comparisons. There is no mutable counter table or backfill job. Counters cover the
database's lifetime; shadow work does not increase served `candidate_requests`.
The existing rollout decision engine still uses its own served-prediction queries.

Configuration comes from environment variables:

- `DATABASE_URL`: shared PostgreSQL SQLAlchemy URL (`postgresql+psycopg` driver).
- `RABBITMQ_URL`: defaults to `amqp://rabbitmq:5672/`. Supply authenticated broker
  credentials through the environment; Compose already wires these for the API.
- `CANDIDATE_URL`: full endpoint, default `http://model-candidate:8000/predict`.
  Use the same endpoint on the worker.

API startup creates `model_comparisons` and `shadow_outbox` through the existing
SQLAlchemy mechanism and starts a dispatcher thread. Pending events survive broker
outages and API crashes. Failed publication is rescheduled after five seconds,
without a retry limit; restart resumes from the database. PostgreSQL
`FOR UPDATE SKIP LOCKED` lets multiple API processes dispatch different rows
without locking prediction rows or blocking feedback.

The dispatcher deletes an outbox row only after RabbitMQ confirms acceptance of
the persistent, routable message. A crash after confirmation but before deletion
causes a safe replay with the same prediction ID; the consumer already handles
duplicates. Delivery is at least once. Shutdown signals the dispatcher to stop;
abrupt process death rolls back its open transaction and releases the claim. You can also
run `python -m app.services.outbox` as a standalone dispatcher. Inspect pending
delivery with `SELECT prediction_id, available_at FROM shadow_outbox`.

A successful prediction proves that its shadow event was committed, not that the
Candidate comparison has completed. The database and RabbitMQ volumes must be
retained for durable recovery. An event parked in `shadow_tasks.failed` still needs
the operator replay described in the worker README.
The upstream serving app is currently liveness-only, so collecting real model
results requires a separate `POST /predict` implementation. The gateway's existing
development prediction fallback remains unchanged.

With Python 3.12 and project/dev dependencies installed, run `python -m pytest -q`
from this directory. Optional integration variables:

- `TEST_DATABASE_URL`: disposable PostgreSQL database; tests create/remove unique schemas.
- `TEST_RABBITMQ_URL`: isolated broker/vhost for real worker-process/HTTP tests.
  Tests use fixed `shadow_tasks` and `shadow_tasks.failed` queues.

Unset integration variables skip those tests. Use isolated services rather than
an application database/vhost. Model HTTP responses in tests are controlled stubs.
