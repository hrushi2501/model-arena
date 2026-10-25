---
name: repository-security
description: Protect Model Arena source, CI, containers, data, and Git history from credential leaks and unsafe exposure. Use when changing security controls or handling secrets/data.
---

# Model Arena repository security

Follow the required progress workflow in root `AGENTS.md`: read [progress.md](../../../progress.md) and [checklist.md](../../../checklist.md), respect lane ownership, and update task status and verification evidence in the same meaningful change. Check tasks only when their acceptance evidence exists; preserve other lanes' updates.

Use this skill for GitGuardian/GitHub Actions, environment variables, credentials, Docker exposure, dependency security, or dataset/payload handling. Read `SECURITY.md`, `.gitguardian.yaml`, and the relevant CI/container configuration before editing.

## Secrets and GitGuardian

- Never place real tokens, passwords, private keys, or production URLs with credentials in source, examples, tests, build arguments, logs, screenshots, or command output. `.env` stays ignored; document variable names and safe placeholders in `.env.example`.
- Resolve GitGuardian credentials from GitHub Actions secrets. Do not print, echo, interpolate into diagnostics, or commit a credential. An “Invalid API key” is an account/configuration issue to fix by verifying the correct active token, secret name, and dashboard instance; do not weaken or disable scanning to make the workflow green.
- Before rewriting history or removing a leaked secret from remote history, treat the credential as compromised: rotate/revoke it first and follow the repository's authorized cleanup process. Do not include secret values in the final response.
- Keep scans scoped to intended commits/refs and preserve the workflow's failure behavior for real findings and invalid credentials.

## Data, audit, and runtime boundaries

- Git tracks code and small metadata. DVC tracks dataset versions and pipeline outputs through its configured storage; do not add raw datasets, caches, generated model binaries, or private prediction payloads to Git.
- Minimize feature data in logs, queues, and audit events. Use synthetic examples for class demos. Where payload retention is genuinely required, document access and retention and store only a protected reference when feasible.
- Keep application database and MLflow database ownership distinct. Do not expose PostgreSQL, RabbitMQ, or internal model-serving ports publicly by default; expose only the intended Nginx/API entry point for local stack access.
- Do not mount the Docker socket into application containers. Run containers as non-root where supported, use multi-stage images, pin the model version, and avoid putting secrets in image layers or build arguments.
- Protect rollout control routes with the auth mechanism actually implemented; do not imply that a control endpoint is secured when it is not.

## Safe change workflow

Inspect `.gitignore`, `.dockerignore`, CI, Compose, and deployment settings affected by the change. Preserve scanners and fail-closed controls. Use placeholder-only examples and report any required operator configuration without exposing credentials.
