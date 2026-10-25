# Agent rules for Lane A (ML and model serving)

These rules govern all coding agent execution for Lane A (`backend/ml/**` and `backend/model_serving/**`).

- **R1:** Read `AGENTS.md` and only needed skills (`backend-mlops`, `ponytail`, etc.) before making changes.
- **R2:** Scope is strictly `backend/ml/**` and `backend/model_serving/**`; all other directories are read-only (report needed changes to coordinating owners).
- **R3:** Build only what `PLAN.md` and `checklist.md` require; avoid speculative features or unrequested dependencies.
- **R4:** Planned is not implemented; never claim unrun checks or assume planned scaffolding is functional.
- **R5:** Report real exit codes for all commands; never print full code blocks or expose secrets.
- **R6:** Two-failure rule: after two failed attempts at any operation, report the exact error and continue independent work.
- **R7:** Conflict with contract, plan decision, or security control: STOP and ask. Never weaken a check.
- **R8:** Never commit `.env` files, raw datasets, DVC cache, model binaries, or credentials. Follow `SECURITY.md`.
- **R9:** Git read-only: do not stage, commit, push, or branch without explicit scope and authorization.
- **R10:** Update `progress.md` with task ID, branch, evidence, and limits; tick `checklist.md` boxes only with verified acceptance evidence.
- **R11:** Concrete numeric model URIs only (e.g. `models:/wine-classifier/1`); never resolve `@latest`, mutable aliases, or tags on request paths.
- **R12:** Follow REPORT RULE format: compact summary only (changed files with line counts, commands with real exit codes, Deviations, NOT RUN; no printed code).
