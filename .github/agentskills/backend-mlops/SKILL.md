---
name: backend-mlops
description: Implement Model Arena's FastAPI services, model serving, rollout and canary control, queue processing, persistence, and DVC/MLflow lifecycle.
---

# Model Arena backend and MLOps

Use this skill for API or service changes, inference and routing, rollout policy, queue work, application persistence, training pipelines, or MLflow integration. Read `PLAN.md` and the affected service README first. The plan describes intended behavior; verify source before assuming it exists.

## Service boundaries

- FastAPI services run as ASGI applications under Uvicorn. Do not add Waitress or a WSGI server.
- Keep the MVP's rollout decision logic in `backend/control_api`; the worker may invoke the same policy module but must not maintain a separate implementation.
- The control API owns prediction routing and rollout state. A model-serving process loads one concrete model version and serves predictions; it does not choose traffic allocation. The worker handles asynchronous shadow comparisons and delayed feedback.
- Keep MLflow metadata separate from application state. Use the configured application database for rollout state, feedback links, and audit history; MLflow owns experiment/registry metadata and model artifacts.
- Add service boundaries only when they provide a real deployment, ownership, or reliability benefit. Keep service contracts versioned and typed.

## Model and pipeline lifecycle

- DVC describes reproducible stages, inputs, parameters, and outputs; MLflow records run parameters, metrics, artifacts, and registered model versions. Keep large/raw datasets outside ordinary Git history and follow the configured DVC remote.
- Gate registration/deployment on an explicit offline evaluation result. Record the dataset/split and evaluation context so candidate comparisons are reproducible.
- Every inference container loads a concrete pinned registry version such as `models:/wine-classifier/7`. Do not resolve `@latest`, mutable aliases, or tags on a request path. Record the serving version with prediction and metric evidence.
- Validate request payloads and model input shape at service boundaries. Apply explicit timeouts, readiness checks, and useful structured errors. Do not log raw features by default.

## Shadow and canary routing

- Shadow requests run against the candidate for comparison but return only the champion's result to the caller. Record linkage to the prediction and both concrete model versions.
- Canary assignment is stable within a rollout. Hash `rollout_id` together with `client_id`, falling back to the generated request ID, with a stable cryptographic hash (for example SHA-256); map it to a fixed bucket range and compare against a validated percentage. Do not use Python's process-randomized `hash()` or per-request random sampling.
- Validate rollout percentages and legal state transitions at the API boundary and in the policy module. Make traffic assignment reproducible and persist the chosen model version and stage with the prediction.
- Decision outcomes are `promote`, `hold`, or `rollback`, each with a reason and evidence snapshot. Hold when required minimum sample/evidence is missing. Separate immediately measurable service health from delayed, label-dependent model quality. Store thresholds and policy version used for each decision.
- Rollback must route new requests back to the known-good pinned champion and append a durable event. Do not claim that requests already in flight can be recalled.

## Queue processing and audit

- Give each event a stable `event_id` and enforce idempotency in storage. Expect redelivery. Commit the database transaction before acknowledging a RabbitMQ message; use bounded retries and a dead-letter path for poison messages.
- Keep the audit log append-only: no `UPDATE` or `DELETE` against audit-event records. Corrections and state changes append new events with actor, timestamp, rollout/model identifiers, reason, and relevant bounded evidence.
- Acknowledge only after durable processing succeeds. Keep queue messages versioned, validated, and minimal; avoid copying sensitive/raw inputs where a protected reference or synthetic class-demo input is enough.
- Use Alembic-managed schema changes and explicit transaction boundaries. Never mix MLflow schema management with application migrations.

## Before completing a change

Trace affected API schemas, callers, DB migrations, queue contracts, Docker configuration, and docs. Run only the checks requested or required by the repository task instructions; report precisely what was and was not verified. Do not describe planned scaffolding as a working feature.
