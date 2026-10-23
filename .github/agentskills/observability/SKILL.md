---
name: observability
description: Instrument Model Arena services with Prometheus metrics and configure truthful Grafana dashboards, service logs, and health visibility.
---

# Model Arena observability

Use this skill for metrics, health instrumentation, Grafana provisioning, or service observability. Read the existing Prometheus/Grafana configuration and `docs/rollout-policy.md` before changing metric semantics.

## Metrics

- Keep labels bounded and predictable. Never label metrics with request IDs, client IDs, raw inputs, prediction values, arbitrary exception text, or other unbounded values.
- Use finite labels such as concrete `model_version`, route template, HTTP status class, rollout stage, comparison result, decision, and normalized reason code. Do not label by values that can grow without bound.
- Reuse or extend the project's planned metric vocabulary where it matches implementation:
  - `model_arena_requests_total{model_version,status}`
  - `model_arena_request_duration_seconds{model_version}` (histogram)
  - `model_arena_shadow_comparisons_total{result}`
  - `model_arena_rollout_decisions_total{decision,reason}`
- Instrument success, failure, latency, and rollout outcomes at the service boundary with consistent units and semantics. Avoid duplicate metrics for the same event and do not include sensitive feature data.
- A missing metric is not zero. Dashboard panels must show the selected time range and communicate no-data or scrape failure clearly.

## Grafana and Prometheus

- Keep scrape configuration and provisioned dashboard JSON in the existing `infra/` tree. Dashboards should load automatically in the local Compose setup where provisioning is configured.
- Prefer panels that answer operator questions: is each service healthy, how are latency/errors changing by serving version, how much traffic reached candidate, and what decision/evidence triggered a hold or rollback?
- Use labels/units/thresholds consistently with the backend policy. Avoid thresholds that imply a production SLO when the project has only demo data.
- Keep dashboards useful at different widths and time ranges. Do not present synthetic or empty data as live measurements.

## Logs versus metrics

Metrics show bounded aggregate behavior; the application database audit log records individual rollout decisions and their evidence. Do not use Prometheus as an audit store or put high-cardinality identifiers into metric labels. Logs should be structured and should omit secrets and raw feature payloads by default.
