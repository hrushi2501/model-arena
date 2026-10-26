# How Model Arena works

The authoritative implementation plan is [PLAN.md](PLAN.md); startup commands and
API contracts are in [README.md](README.md).

## Request and evidence paths

1. The Next.js operator UI sends same-origin requests through its gateway rewrite,
   Nginx, and the FastAPI control API. The API owns release policy and routing.
2. Champion and Candidate each load exactly one concrete numbered MLflow registry
   version. Failed loading stops startup. Readiness identifies the loaded model.
3. Successful predictions and failed requests are recorded in PostgreSQL. A failed
   model call produces an HTTP error with no predicted class. Returned model role
   and version must match the route that was selected.
4. In SHADOW, Champion remains the synchronous serving model. Its prediction and
   the exact shadow payload are written in a single database transaction. A separate
   dispatcher publishes pending events, retaining them until broker confirmation.
5. The RabbitMQ worker calls Candidate, validates its version, and conditionally
   inserts a comparison. It commits before acknowledging. Replayed completed work
   does not repeat inference. HTTP/database failures retry, then park in a durable
   failed queue rather than disappearing.
6. Ground truth arrives later through feedback. It is an independent dataset or
   operator label, not the model's own answer. The first label is immutable;
   duplicate identical submissions are harmless and conflicting labels are rejected.

## Release decisions

Evaluation starts READY, optionally enters SHADOW, and can start a 10% canary probe
once both configured model identities are ready. Requests stick to a deterministic
client/evaluation hash. Candidate share can advance through 25%, 50%, and 100%.

The API's five-second monitor and operator controls call one policy implementation.
Rollout row locks serialize changes. The current stage must have 20 Candidate
requests. Error rate over 5% or p95 over 200 ms triggers rollback. Progression also
requires 20 labeled examples for each model and a Candidate accuracy drop no greater
than five percentage points. Missing quality evidence produces HOLD. Each advance
starts a fresh stage; prior requests do not automatically approve the next one.

At 100% traffic the Candidate remains monitored. Earlier Champion labels in the
same evaluation provide its quality baseline. A rollback sets Candidate share to
zero and records an audit event. A new evaluation archives old evidence by retaining
it under its original time window; it does not delete history or unpublished work.

## Metrics in the UI

The control API computes JSON summaries from persisted evidence. The UI displays
request counts, p95, errors, labeled accuracies, model identities, shadow agreement,
and pending tasks. Empty accuracy is shown as awaiting evidence. Pending outbox
count is a delivery backlog, not a fabricated broker-health signal.

Agreement and accuracy answer different questions: two models can agree on a wrong
answer. Accuracy is measured only against independent labels. The demos use the
held-out labels exported by training, so a worse Candidate may correctly roll back.

## Durability and boundaries

Delivery is at least once. A crash before publishing leaves the outbox row pending;
a crash after broker confirmation but before deletion can publish twice. The worker
uses the prediction ID as its idempotency key, and the comparison primary key prevents
duplicate rows. PostgreSQL SKIP LOCKED lets independent dispatchers handle separate
rows. Outbox locks do not block feedback on the prediction row.

MLflow manages model tracking and artifacts; PostgreSQL manages application state.
The MLflow server has its own persistent SQLite/artifact volume in this local setup.
The UI, Nginx, API, model servers, queue, worker, and these stores match the intended
architecture. The UI is started with Bun; backend infrastructure runs in Compose.
