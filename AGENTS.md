# Instructions for coding agents

Before changing code, configuration, documentation, or infrastructure:

1. Read this file and the relevant repository skill in `.github/agentskills/`.
2. Read the affected service's README and the matching section of `PLAN.md` when changing architecture or service contracts.
3. Preserve the boundary between implemented behavior and planned behavior. Do not claim a pipeline, deployment, metric, or control works until its implementation is present and verified.
4. Keep changes small but complete. Follow existing patterns, update every affected caller/configuration, and do not add dependencies or services without a concrete need.
5. Never commit credentials, `.env` files, raw datasets, or sensitive prediction payloads. Follow `SECURITY.md`.

## Skill routing

- Any frontend, interaction, styling, or dashboard UI change: read `.github/agentskills/frontend-ui/SKILL.md`.
- Any code change, refactor, bug fix, dependency choice, or review: follow `.github/agentskills/ponytail/SKILL.md`.
- API, routing, model lifecycle, rollout policy, queue, persistence, or DVC/MLflow work: read `.github/agentskills/backend-mlops/SKILL.md`.
- Prometheus, Grafana, logs, traces, or instrumentation work: read `.github/agentskills/observability/SKILL.md`.
- Secrets, GitGuardian, CI security, Docker exposure, or data handling work: read `.github/agentskills/repository-security/SKILL.md`.

For a task spanning areas, read each relevant skill. These repository instructions take precedence over a skill where they conflict. The user's explicit task and the current implementation take precedence over aspirational plans.
