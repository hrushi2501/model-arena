# Simplified Model Arena architecture

The operator UI on port 3000 sends requests through Nginx on 8080 to the control
API on internal port 8000. The API routes to version-pinned Champion/Candidate
servers and stores predictions, labels, rollout state, and an outbox in PostgreSQL.
The outbox publishes to RabbitMQ. The worker calls Candidate and commits comparisons
before acknowledging. MLflow provides the registered models. The UI reads JSON
metrics from the API.

## Implementation and acceptance checks

- [x] Remove unused external monitoring services, exporters, links, configuration, and documentation.
- [x] Return real inference failures; validate served model identity; keep SHADOW Champion-only.
- [x] Scope evidence to the active evaluation/stage; require genuine labels for quality decisions.
- [x] Run serialized automatic release checks inside the control API; gate manual advancement too.
- [x] Load only the configured registered model and expose honest readiness/model metadata.
- [x] Register training outputs explicitly and pass their concrete versions to all services.
- [x] Use dataset labels in demos; report the actual decision and actual completed shadow work.
- [x] Wire UI controls, metrics, model readiness, shadow comparisons, prediction, and feedback.
- [x] Preserve pending outbox events and historical audit evidence when starting a new evaluation.
- [x] Verify migrations, unit/integration tests, frontend build, and the running stack/browser.

## Verified locally (2026-10-26)

- 56 API tests, including real PostgreSQL/RabbitMQ concurrency and process-kill recovery; 33 worker tests; 10 serving tests; 2 dataset-label demo tests.
- Ruff and TypeScript checks passed. Production frontend built with `cd frontend && bun run build --webpack` (the sandbox prevented Turbopack's internal listener).
- Trained and registered models 1/2 in live MLflow; all eight Docker services run with model identities ready. Docker installs service dependencies from committed uv lockfiles.
- Real SHADOW demo completed 20 comparisons with Champion-only responses and no unpublished events remaining.
- Real canary demo advanced 10% -> 25% -> 50%, then automatically rolled back on measured accuracy loss. Opt-in HTTP faults separately triggered automatic rollback. Demo faults restored to disabled.
- Stopping Champion returned HTTP 503/null through Next.js and Nginx, persisted the failure, rejected its feedback, then recovered after restart. Genuine feedback updated the scoped counters.
- Dashboard rendered in Chrome with real model metadata, evidence, controls, comparison tables, prediction results, and audit events.

This records local runtime evidence. Hosted deployment and production load testing are outside this change.
