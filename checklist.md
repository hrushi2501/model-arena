# Model Arena development checklist

This is the execution checklist for the MVP in [PLAN.md](PLAN.md). [progress.md](progress.md) records actual status and evidence. An unchecked item is planned work, even when its directories or dependencies already exist. This document assigns work; it does not implement the contracts below.

## Scope and development order

Build one reproducible classification release workflow: version data, train/evaluate two models, register concrete MLflow versions, serve predictions, collect shadow comparisons and delayed labels, progress through canary stages, then promote or roll back with durable evidence. The local Compose demo is the primary acceptance target. Hosted deployment is a separate final phase.

Use the existing Next.js/Bun/Biome frontend, FastAPI/Uvicorn services, PostgreSQL, RabbitMQ, DVC, MLflow, Prometheus and Grafana. Keep Kubernetes, automatic retraining, multi-region infrastructure, a model marketplace and additional microservices outside this MVP.

Dependency order:

```text
P0 shared contracts
  ├─ P1-A data/training + P2-A serving
  ├─ P1-B persistence/policy skeleton + P2-B prediction routing
  ├─ P1-C UI foundation + P2-C model/overview integration
  └─ P1-D infrastructure/queue skeleton + P2-D runtime integration
            ↓
P3 shadow and delayed feedback → P4 canary decisions
            ↓
P5 observability and operator integration → P6 clean demo/CI
            ↓
P7 hosted deployment and final handoff
```

Phases are integration gates, not a requirement for every developer to wait. Start independent work once its named contract is frozen; merge a phase only when its exit evidence exists. For example, C can build layouts while A trains and B builds migrations, and D can provision dashboards before live panel validation.

## Four development lanes

These branch names are assignments, not a claim that the branches exist. Only `Hrushi` is created as part of this planning setup. Other developers create their branch from the updated `origin/main`.

| Lane / branch | Primary responsibility and owned files | Handoffs |
| --- | --- | --- |
| A / `dev/ml-serving` | `backend/ml/**`, `backend/model_serving/**`, ML/serving tests and service lockfiles; MLflow artifact requirements | Dataset/schema, offline reports, model signature, two concrete URIs, serving/readiness contract to B/D |
| B / `Hrushi` | `backend/control_api/**`, `database/**`, API/DB/policy tests; integration coordination and shared contract documents | API schemas, migrations, durable routing state, policy decisions and audit contract to A/C/D |
| C / `dev/frontend` | `frontend/**`, frontend tests; UI/API adapter types derived from B's contract | Operator console and same-origin Next.js proxy; error/empty/stale/confirmation behavior |
| D / `dev/worker-infra` | `backend/worker/**`, `infra/**`, `compose.yaml`, `.github/workflows/**`, `Makefile`, `.env.example`; runtime/queue/monitoring checks | Reliable queue consumption, scheduled evaluation trigger, working stack, monitoring and CI |

Each lane owns its service README and dependency lockfile. D owns `infra/mlflow/**`; A supplies the artifact/bootstrap requirements. B owns shared contract changes in `PLAN.md`, `docs/architecture.md`, `docs/rollout-policy.md` and the future `docs/contracts.md`; D owns `docs/demo-runbook.md`. `AGENTS.md`, skills, root `README.md`, root `package.json`/`bun.lock`, `progress.md` and this checklist are shared: the PR author proposes the smallest required edit, and B coordinates cross-lane conflicts. C coordinates JS dependency/lockfile changes with D's CI work.

Instrumentation inside a service stays with its owner: A instruments serving, B instruments the API, D instruments the worker and owns scrape/dashboard configuration. D agrees names and units with them before building panels. D must not independently change another lane's application code to satisfy a dashboard.

## Branch and integration rules

1. Branch from current `origin/main`; one developer per development branch. Make focused PRs into `main`, with task IDs, checks, evidence and matching progress updates. Work on the lane's next unblocked item rather than taking another lane's files silently.
2. Agree shared contracts in P0 before writing integrations. Each producer owns its contract and tests; consumers use reviewed examples until the producer is ready. Fixtures remain clearly marked as fixtures and never appear as live UI data.
3. A change to an API field, event schema, migration, model signature, policy input or metric meaning requires review by affected consumers and updates to their callers in the same coordinated change. Version incompatible event contracts explicitly.
4. Rebase or merge current `origin/main` into development branches before integration; avoid rewriting published branches that others are using. Keep migrations ordered and exclusively owned by B. D requests schema needs from B rather than creating competing migration histories.
5. Update only the task/status entries relevant to a PR. Preserve other developers' progress entries and resolve documentation conflicts by retaining both sets of evidence. A task is complete only when its acceptance checks pass; record blockers and unrun checks explicitly.
6. B coordinates integration, but each owner validates their boundary. No lane can declare another lane's runtime behavior complete based only on a mock, image build, README, passing secret scan or pushed commit.

## P0 — Agree contracts and unblock parallel development

**Owners:** B coordinates; A/C/D review. **Exit:** one reviewed contract revision with examples and named owners; no application feature is claimed complete by this gate.

- [ ] **P0-01 (all):** Claim lanes/branches in `progress.md`; record local prerequisites and service-specific check commands. Check Python 3.12, Bun, Docker/Compose and required ports without committing local secrets.
- [ ] **P0-02 (A → B/C/D):** Select the small classification dataset (Wine is the proposed default), feature names/order/types, valid classes, finite-value rules and signature version. Fix seed and train/validation/test split strategy; keep test data out of training/tuning and labels out of prediction requests.
- [ ] **P0-03 (B + C):** Write `docs/contracts.md` with versioned request/response/error examples for predict, feedback, models, active rollout, create/advance/pause/resume/abort and paginated audit. Define request/prediction IDs, no-active-rollout response, timestamps, unavailable metrics and conflict statuses. Add the missing resume route to the API proposal in `PLAN.md` when this contract is agreed.
- [ ] **P0-04 (A + B + D):** Freeze internal serving inference/readiness fields, timeouts, signature checks and concrete version identity; define deployment registration/bootstrap and how B verifies the endpoint actually serves the expected URI.
- [ ] **P0-05 (B + D):** Define queue envelopes (`schema_version`, stable `event_id`, event type/time, prediction/rollout/version links), feedback deduplication/correction rules, retry/dead-letter behavior and minimal safe payloads. Define shared DB write ownership and a durable publish-recovery design (for example, a transactional outbox).
- [ ] **P0-06 (B + D):** Specify state transitions, pause/resume traffic semantics, one-active-rollout invariant, policy version/evidence windows and scheduler ownership. D triggers B's single policy implementation through an agreed internal interface; never duplicate the decision engine in the worker.
- [ ] **P0-07 (A + B + D):** Specify logical champion/candidate to physical endpoint mapping. Preserve the previous pinned champion for rollback, define the promotion point and recovery after restart, and stage the next candidate only in an inactive slot. Document manual Compose activation steps; no Docker socket or container-control permission in the public API.
- [ ] **P0-08 (B + C + D):** Agree a minimal operator authentication/authorization boundary for mutations and its server-side Next.js forwarding; keep demo traffic separate from privileged controls. Define hosted HTTPS/access requirements before exposing the stack, without adding an auth service by default.
- [ ] **P0-09 (all):** Freeze bounded metric names, units, label values, quality/sample semantics and data retention. Resolve lifetime growth of model-version labels before broad use. Keep prediction/rollout IDs in DB/logs rather than metric labels.

## P1 — Build independent foundations

**Entry:** relevant P0 contracts agreed. **Exit:** reproducible model artifacts, working migrations, UI shell and queue/runtime foundations independently verified.

- [ ] **P1-A1 (A):** Initialize DVC in the ML area with explicit working-directory commands, data references, deterministic preparation and local development remote. Track data/output metadata and `dvc.lock`; keep raw data, caches and model binaries outside Git. Document remote access for each developer and prove retrieval/reproduction on another developer's machine without relying on the original cache.
- [ ] **P1-A2 (A):** Implement prepare/features/train/evaluate stages in `dvc.yaml`, driven by `params.yaml`. Reuse the fitted preprocessing pipeline at inference; retain feature signature and split/dataset identifiers. Produce distinct baseline/candidate artifacts using the same evaluation split.
- [ ] **P1-A3 (A):** Log MLflow parameters, metrics, artifacts, signature, code/data/split references and run IDs. Implement an explicit offline gate and register eligible concrete versions. Define registration retry/idempotency so no-op DVC runs and retries do not unintentionally create duplicate deployable versions. Preserve failed runs with rejection evidence; they must not become eligible serving deployments.
- [ ] **P1-A4 (A):** Create service `uv.lock` files and focused reproducibility/signature/offline-gate checks; add missing dev tools only as required. Evidence includes rerun commands, run IDs, concrete version URIs and measured reports, not just configured stages.
- [ ] **P1-B1 (B):** Implement settings, DB engine/session wiring, initial Alembic configuration/migrations and repeatable demo seeds. Cover deployments, rollouts, predictions, feedback, comparisons, append-only audit and the agreed deduplication/outbox state. Migrate application DB only; leave MLflow schema to MLflow.
- [ ] **P1-B2 (B):** Implement repositories and transaction boundaries, validated model/deployment identity, one-active-rollout constraint and durable state bootstrap. Verify restart persistence, unique event/feedback handling and migrations against real PostgreSQL.
- [ ] **P1-B3 (B):** Implement typed API/error schemas and the shared rollout state/policy module with versioned configuration and thresholds. Define valid transitions, minimum sample/label counts, comparable cohorts, latency/error limits and non-inferiority margin before tuning demo outcomes.
- [ ] **P1-C1 (C):** Replace the current tinted/gradient scaffold with shared true-black/white tokens, responsive navigation and Overview/Models/Rollouts/Audit shells. Implement a visible keyboard-accessible, persistent dark-first theme toggle with no hydration flash and reduced-motion support.
- [ ] **P1-C2 (C):** Build typed API/proxy helpers and clearly separated development fixtures for agreed contracts. Provide loading, error, empty, unavailable and stale states; labels, focus states, units, sample counts and time windows. No fabricated live metrics or successful actions.
- [ ] **P1-D1 (D):** Verify core Compose services, DB bootstrap assumptions, persistent MLflow artifacts and inter-container connectivity. Add real readiness/dependency sequencing and migration commands as producers become available; preserve loopback admin ports and internal service networking.
- [ ] **P1-D2 (D):** Build worker entrypoint/configuration/container skeleton with durable exchanges/queues, retry/dead-letter topology, bounded prefetch and graceful shutdown. Use contract fixtures until P3 DB/serving integration; do not enable an empty consumer as a completed service.
- [ ] **P1-D3 (D):** Establish path-appropriate CI for frontend lint/type/build, service lint/type/tests where configured, locked dependencies and container builds. Keep GitGuardian active. Coordinate lockfiles/build contexts rather than assuming current pip-based images use future uv locks.

## P2 — Serve a real champion through the API

**Entry:** A's registered artifacts and B's deployment/prediction contracts. **Exit:** a validated prediction travels through the real gateway and returns a durable prediction ID and verified model version.

- [ ] **P2-A1 (A):** Load exactly one numeric MLflow registry version at process startup; reject missing/alias/latest URIs and signature mismatches. Keep `/health/live` separate from `/health/ready`; readiness remains false on artifact/load failure.
- [ ] **P2-A2 (A):** Implement internal prediction with shape/type/finite-value validation, deterministic class/probability encoding, version metadata, bounded errors and inference metrics agreed with D. Check actual artifact access from both model containers.
- [ ] **P2-B1 (B):** Implement model/deployment list and bootstrap/selection flow. Validate offline eligibility, readiness, schema and endpoint/version identity; store pinned versions and mapping. A registry alias is descriptive metadata, not the routing authority.
- [ ] **P2-B2 (B):** Implement `POST /api/v1/predict` with request IDs, champion routing, explicit deadlines and validated response identity; persist result/status/latency/rollout metadata. Define duplicate request behavior and failure semantics. Avoid raw feature logging/storage by default.
- [ ] **P2-B3 (B):** Expose active-rollout and audit reads, readiness and dependency errors. Add operator authorization at mutation boundaries per P0; demonstrate unauthorized actions are rejected when those routes arrive.
- [ ] **P2-C1 (C):** Implement same-origin server routes for available read/prediction APIs using server-only `MODEL_ARENA_API_URL`. Connect Models/Overview to real data; preserve upstream errors and present missing evidence honestly.
- [ ] **P2-D1 (D + A):** Wire champion/candidate internal URLs, model URIs, settings and readiness through Compose/Nginx and safe example env names. Verify MLflow artifact upload/download from host-side training and both serving containers; a configured volume alone is insufficient. Update Make targets/run instructions; verify model version changes do not require rebuilding the API image.
- [ ] **P2-X1 (A/B/C/D):** Run a real request through Next.js → Nginx → API → champion; link response, stored prediction and concrete MLflow version. Exercise invalid features, wrong serving version, model unavailable and timeout cases. Record which tests use fixtures versus real services.

## P3 — Shadow comparison and delayed feedback

**Entry:** persisted champion predictions, candidate readiness and durable event/DB contracts. **Exit:** candidate comparisons and late labels survive failure/replay while callers receive only champion results in shadow mode.

- [ ] **P3-B1 (B):** Implement rollout creation/start-shadow with offline/readiness gates and audit transaction; record immutable champion/candidate identities and policy. Publish shadow work through the agreed durable recovery path; define queue outage behavior without accidentally returning candidate output.
- [ ] **P3-D1 (D):** Consume shadow work, call the pinned candidate with deadlines and validate version/output; store comparison/error summary idempotently. Commit durable work before ACK, retry transient failures, dead-letter poison messages and recover unprocessed work after restart.
- [ ] **P3-B2 (B):** Implement feedback ingestion linked to a known prediction/version; validate labels and correction/duplicate rules. Persist accepted feedback and publish work durably; unknown IDs and conflicting duplicates return explicit errors.
- [ ] **P3-D2 (D):** Process delayed labels and maintain quality evidence for the agreed comparable cohort, including candidate predictions for shadow examples. Support out-of-order comparison/feedback arrival and late evidence without silently attributing labels to the wrong version/stage.
- [ ] **P3-A1 (A):** Supply deterministic demo request/label inputs and expected evaluation interpretation; generate labels separately from prediction payloads. Define handling for comparison failures and missing candidate output.
- [ ] **P3-C1 (C):** Connect shadow start, comparison/sample state and feedback evidence to real APIs; show pending/insufficient evidence. Display per-action results only after server confirmation.
- [ ] **P3-X1 (B/D, A/C review):** Prove duplicate delivery, crash after DB commit before ACK, DB outage, queue publish interruption, delayed labels and poison-message handling. Verify one durable effect per event, inspect dead-letter/replay, and show champion-only shadow responses.

## P4 — Canary, hold, promotion and rollback

**Entry:** durable rollout state and correctly linked health/quality evidence. **Exit:** both successful promotion and automatic rollback work through the same audited transition service.

- [ ] **P4-B1 (B):** Implement SHA-256 bucketing of rollout ID + client ID (request ID fallback); validate percentages and persist chosen version/stage. Verify assignment stability across processes/restarts and boundary percentages; inspect aggregate traffic over many distinct clients rather than expecting exact shares from tiny samples.
- [ ] **P4-B2 (B):** Implement advance/pause/resume/abort and automatic transitions through one state-transition service. Persist pause origin/traffic semantics; atomically check current revision/state and prevent two active rollouts or concurrent double-advance.
- [ ] **P4-B3 (B):** Implement evidence-window evaluation: rollback on configured safety breach, hold on insufficient/invalid/stale evidence, and advance/promote only after required gates pass. Separate immediate health from delayed label quality; record measured values, denominators, thresholds, policy version, actor and reason.
- [ ] **P4-D1 (D + B):** Add the agreed periodic evaluator trigger with bounded retry and single logical scheduling ownership; restart/replay cannot duplicate decisions. Call B's shared engine/internal service; no second policy implementation.
- [ ] **P4-B4 (B + A/D):** Make promotion update durable logical champion mapping atomically while retaining a known-good rollback target. Verify rollback affects new requests, restart restores mappings, and a subsequent candidate can be staged without replacing the active serving slot.
- [ ] **P4-C1 (C):** Connect rollout forms, stage/share display and advance/pause/resume/abort controls. Respect server-validated transitions, show hold/rollback reasons and confirmation for abort; handle stale-state conflicts and failed requests by refreshing authoritative state.
- [ ] **P4-A1 (A + D):** Provide explicit demo-only, repeatable health-failure injection and reset instructions (for example, candidate timeout/unavailability). Keep the passing candidate's offline evaluation real and record the injected fault; do not falsify metrics to force a decision.
- [ ] **P4-X1 (all):** Verify zero/missing-label hold, pass/advance/promote, unhealthy-candidate rollback, manual abort, pause/resume, concurrent operator/evaluator requests, controller restart and next-rollout slot reuse. Match returned traffic selection and append-only audit events.

## P5 — Monitoring and complete operator console

**Entry:** stable instrumentation/API meanings. **Exit:** console, dashboards and audit agree on actual rollout state and evidence.

- [ ] **P5-B1 (B):** Instrument API requests, latency, invalid predictions, feedback and decisions once per durable event; provide truthful overview/evidence summaries. Preserve stable route/status/decision labels and units; keep raw payloads out of logs.
- [ ] **P5-A1 (A):** Finish serving health/inference instrumentation and verify endpoint version metadata agrees with labels. Handle inactive/retired versions according to the agreed cardinality budget.
- [ ] **P5-D1 (D):** Instrument queue depth/retries/dead letters/processing outcomes and worker readiness. Make Prometheus targets match active Compose profiles; scrape actual `/metrics` endpoints rather than treating missing endpoints as zero traffic.
- [ ] **P5-D2 (D):** Add provisioned Grafana JSON for traffic share, rate/errors/invalid output, latency, shadow comparisons, labeled quality/sample counts and current decisions. Use accurate units/windows/no-data states. Expose DB-derived evidence through an agreed bounded exporter/API rather than putting per-request audit records in Prometheus.
- [ ] **P5-C1 (C):** Complete Overview/Models/Rollouts/Audit, filters/pagination, MLflow/Grafana links and evidence detail. Show version, time window, sample counts, stale/no-data/error state and backend-confirmed action outcomes; keep all backend secrets/origins server-side.
- [ ] **P5-X1 (all):** Compare a single scenario's DB audit, API, frontend and Grafana. Check keyboard navigation, small-screen layout, light/dark contrast, reduced motion, unavailable backend and scrape failure in the actual browser.

## P6 — Clean local demo and quality gate

**Entry:** P2–P5 acceptance evidence. **Exit:** another developer can run both scenarios from a fresh checkout with documented inputs and checks.

- [ ] **P6-D1 (D):** Verify clean locked installs, lint/type/build/test jobs and all custom images in CI. Use real PostgreSQL/RabbitMQ integration checks for persistence/replay and targeted browser checks for operator actions. A green secret scan alone is insufficient release evidence.
- [ ] **P6-X1 (all; D runbook):** Replace the placeholder demo runbook with exact bootstrap, DVC retrieval/reproduction, training/registration, migration, pinned URI activation, stack start, traffic/feedback, fault injection/reset and non-destructive shutdown commands. Explain profile selection and volume retention.
- [ ] **P6-X2 (all):** Run promotion and forced-health-rollback scenarios from clean setup, plus an insufficient-label hold. Capture request/feedback counts, model/run/data/policy identities, decision reasons and matching UI/Grafana/audit evidence. Record hardware/environment and demo-only thresholds.
- [ ] **P6-X3 (B/D):** Verify rollback/restart persistence, duplicate/out-of-order events, bounded retries/dead letters, publish recovery and operator access rules. Document known limitations and recovery steps rather than declaring production reliability.
- [ ] **P6-X4 (all):** Reconcile service READMEs, `PLAN.md`, checklist and progress with implemented behavior. Prepare assignment architecture/results/screenshots from collected evidence. Local pre-commit scanning is complete only after someone verifies authenticated hook installation/execution separately.

## P7 — Hosted deployment and handoff

**Entry:** reproducible local MVP. **Exit:** verified hosted behavior, or an explicit local-only delivery with hosted work still unchecked.

- [ ] **P7-D1 (D + B):** Select a Docker-capable backend host and configure HTTPS ingress, operator protection, secret injection, persistent volumes, backups/restore and restricted admin access. Add image publishing/release identity and a documented rollback procedure if hosted delivery is selected.
- [ ] **P7-C1 (C + D):** Configure Vercel's server-only backend HTTPS origin and verify browser → Next.js → hosted API requests, model/rollout/audit pages and authorized actions. A frontend deployment or CI pass alone does not verify backend reachability.
- [ ] **P7-X1 (all):** Re-run the agreed hosted smoke/demo, record image/commit/model/data/policy identities, and reconcile evidence after restore/restart. Keep untested hosted scenarios marked unverified.

## Completion rule

Check an item only when its deliverable and stated acceptance evidence exist. Add its ID, owner, branch/PR or commit, source/artifact links, check commands and limits to `progress.md`. Partial work remains unchecked with its next step recorded. Do not mark P1–P7 complete because this plan was written.
