# Model Arena architecture

## Planned request path

`Next.js control panel → Nginx → FastAPI control API → selected model server`

The control API owns the current champion/candidate versions and canary percentage. The model-server image is run as two containers with different pinned MLflow model versions. A Python worker consumes RabbitMQ events for shadow comparisons and delayed labels.

## State ownership

- PostgreSQL stores rollout state, prediction metadata, feedback, and append-only audit events.
- MLflow stores experiment metadata and registered model versions; its metadata database is separate from the application database.
- DVC tracks data references and reproducible training stages.
- Prometheus stores time-series metrics; Grafana dashboards are provisioned from this repository.

## Current scaffold

The API and model server currently expose liveness routes only. The worker, database integration, DVC stages, MLflow server, metrics, and rollout state machine remain to be implemented.
