# Queue worker

Consumes JSON tasks containing `request_id`, `features`, `champion_pred`, and
`candidate_url` from durable `shadow_tasks`. It validates the task and destination,
posts `{"features": [...]}` to the Candidate with HTTPX, and requires an integer
`prediction` in the response. Redirects are disabled.

Each successful task commits a `model_comparisons` row containing `prediction_id`,
`champion_pred`, `candidate_pred`, `is_match`, and `timestamp` before acknowledging.
A conditional insert verifies the persisted Champion prediction, and PostgreSQL
`ON CONFLICT` prevents duplicates. Completed tasks are acknowledged without calling
the Candidate again, including redelivery after a commit followed by a lost ACK.
Accuracy counters are derived by the API from saved comparisons and feedback;
the worker does not maintain a second copy. The API owns schema creation and the
worker waits for its tables before consuming.

Failed HTTP/database work gets three immediate processing attempts, then moves to
durable `shadow_tasks.failed`. Malformed tasks and unconfigured destinations are
parked directly. Retry publication is confirmed before acknowledging the original;
a failed publication leaves it unacknowledged for redelivery after reconnect.
Retry headers are validated and capped. To replay a failed task after fixing its
cause, republish it to `shadow_tasks` with `x-shadow-retries` reset.

Configuration uses environment variables only:

- `RABBITMQ_URL`, default `amqp://rabbitmq:5672/`. If absent, Compose's separate
  `RABBITMQ_HOST`, `RABBITMQ_USER`, and `RABBITMQ_PASSWORD` are supported.
- `DATABASE_URL`, a shared PostgreSQL SQLAlchemy URL. Otherwise use Compose's
  `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB`, optionally `POSTGRES_HOST`
  (default `postgres`) and `POSTGRES_PORT` (default `5432`). Database connect,
  statement, and lock waits are bounded to five seconds.
- `CANDIDATE_URL`, default `http://model-candidate:8000/predict`. A base URL such as
  Compose's `http://model-candidate:8000` gets `/predict` appended. Match the API endpoint.

Use Python 3.12 and project/dev dependencies. From this directory, run
`python -m pytest -q` or start the worker with `python -m app.consumer`.
The loop reconnects after startup, broker, or database failures. Real inference
requires a Candidate exposing `POST /predict`; the current upstream serving app
is liveness-only. Integration tests use a controlled model HTTP stub.
