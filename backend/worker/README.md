# Queue worker

Consumes persistent JSON events from the durable `shadow_tasks` RabbitMQ queue.
Each task contains `request_id`, `features`, `champion_pred`, and `candidate_url`.
The worker validates the task, posts `{"features": [...]}` to the configured
Candidate inference endpoint using HTTPX, and expects an integer `prediction` in
the JSON response. Redirects are disabled and destinations must match `CANDIDATE_URL`.

The worker commits one PostgreSQL `model_comparisons` row per prediction, containing
`prediction_id`, `champion_pred`, `candidate_pred`, `is_match`, and `timestamp`,
then acknowledges the RabbitMQ delivery. The primary key and a lock on the
prediction row make redelivery idempotent. If a ground-truth label already exists,
the same transaction updates the Candidate accuracy counter. The API owns table
creation; the worker waits for those tables before consuming.

Candidate or database failures get up to three processing attempts. Malformed
messages and exhausted tasks are published to durable `shadow_tasks.failed` for
inspection. The worker confirms the retry/failed publication before acknowledging
the original; a failed re-publication leaves the original unacknowledged and
reconnects. Retries are immediate and bounded; this is not a delayed backoff queue.
After fixing a failed task's cause, an operator can republish it to `shadow_tasks`
with its `x-shadow-retries` header reset. Replaying a completed prediction does not
duplicate comparisons or accuracy counts.

Configuration uses only environment variables:

- `RABBITMQ_URL`, default `amqp://rabbitmq:5672/`. When absent, the current Compose
  variables `RABBITMQ_HOST`, `RABBITMQ_USER`, and `RABBITMQ_PASSWORD` are supported.
- `DATABASE_URL`, a shared PostgreSQL SQLAlchemy URL. When absent, use Compose's
  `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB`, with optional
  `POSTGRES_HOST` (default `postgres`) and `POSTGRES_PORT` (default `5432`). There
  is no embedded database password or silent SQLite fallback in the worker.
- `CANDIDATE_URL`, default `http://model-candidate:8000/predict`. The Compose value
  `http://model-candidate:8000` is also accepted and gets `/predict` appended.
  Configure the same endpoint on the API and worker.

Use Python 3.12, install project/dev dependencies, and run from this directory:

```sh
python -m pytest -q
python -m app.consumer
```

The service loop reconnects after broker or database startup failures. Inference
requires a Candidate exposing `POST /predict`; the current upstream serving app
is liveness-only. Tests use a controlled HTTP model stub to verify messaging and
persistence independently of training/model-serving implementation.
