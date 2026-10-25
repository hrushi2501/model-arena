# Model Arena

**Model Arena** is a class MVP for safer machine-learning releases using shadow testing, canary traffic, and automatic rollback.

See [`PLAN.md`](PLAN.md) for the architecture, full model lifecycle, service responsibilities, rollout policy, deployment plan, and implementation milestones.

Use [`checklist.md`](checklist.md) for phased tasks, four development lanes, dependencies and acceptance gates. Read [`progress.md`](progress.md) for the current implementation status, verified evidence, blockers and ownership. Developers and agents update progress with each meaningful change.

## Agent guidance

Repository-level instructions live in [`AGENTS.md`](AGENTS.md); coding agents should read it before making changes. The project skills in [`.github/agentskills/`](.github/agentskills/) cover frontend UI, minimal complete implementation (Ponytail), backend/MLOps, observability, and repository security. Claude Code, GitHub Copilot, and Cursor entrypoint files point back to the same guidance.

## Repository areas

- `frontend/`: Next.js, TypeScript, Bun, and Biome control panel; deployed separately to Vercel.
- `backend/control_api/`: FastAPI prediction gateway and rollout control API.
- `backend/model_serving/`: one version-pinned model server image, run once per active model version.
- `backend/worker/`: planned RabbitMQ consumer for shadow comparisons and delayed labels.
- `backend/ml/`: DVC pipeline and MLflow experiment/model registration workflow.
- `database/`: migration and seed-data ownership.
- `infra/`: local proxy and monitoring configuration.
- `compose.yaml`: local multi-container stack (to be completed as services are implemented).

## Local setup

1. Install Bun, Python 3.12, Docker, and Docker Compose.
2. Copy `.env.example` to `.env` and replace the local database password.
3. Run `bun install` from the repository root, then `bun run dev` for the frontend.
4. Run `make stack` for the API and core infrastructure. Run `make stack-full` to also start the model-server and observability profiles.

The current frontend is a static starter screen. The API and model server expose liveness routes only. Training stages, inference, persistence, queue processing, canary decisions, Prometheus scraping, and the worker remain to be implemented.

## Security

See [`SECURITY.md`](SECURITY.md) for GitGuardian scanning setup. Never commit `.env` or real credentials.
