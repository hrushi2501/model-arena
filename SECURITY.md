# Security scanning

Model Arena uses GitGuardian in two places:

- `.pre-commit-config.yaml` defines a local `ggshield` scan before commits.
- `.github/workflows/gitguardian.yml` scans repository changes in GitHub Actions.

## Enable the GitHub Actions scan

1. Create a GitGuardian token with the `scan` scope. A personal access token works for a personal/free workspace. A service-account token can be used when your workspace plan supports service accounts.
2. In GitHub, open **Settings → Secrets and variables → Actions** for this repository.
3. Add a repository secret named `GITGUARDIAN_API_KEY` with the token as its value.
4. Paste the token value only: no `Token` prefix, quotes, or surrounding whitespace. If replacing the value, delete and recreate the Actions secret; GitHub does not reveal an existing secret value.
5. The workflow defaults to the GitGuardian US instance. For an EU or self-hosted workspace, add a repository variable named `GITGUARDIAN_INSTANCE` with that workspace's dashboard URL (for example, `https://dashboard.eu1.gitguardian.com`).
6. Push a commit or run **GitGuardian secret scan** from the Actions tab.
7. After the first successful run, consider requiring the `Scan for exposed secrets` check in branch protection.

If the action reports `Invalid GitGuardian API key`, replace the secret with a newly generated token that has the `scan` scope, and confirm the instance variable matches the workspace where that token was created. Do not paste the token into an issue, chat, workflow file, or command that will be saved in shell history.
If `GITGUARDIAN_API_KEY` is unavailable in an untrusted `pull_request` context (for example, from forks), the workflow logs a warning and skips the scan for that run. Pushes and manual dispatches still require the secret and fail fast when it is missing.

Never commit the token or put it in `.env.example`.

## Enable the local pre-commit hook

Install `ggshield` and `pre-commit`, authenticate `ggshield` with `ggshield auth login`, then run:

```sh
pre-commit install
```

The GitGuardian scan uses the public API. The API key is needed for scanning; it must remain in the developer's local GitGuardian configuration or environment, not in the repository.

## Connect repository monitoring

For GitGuardian dashboard monitoring and historical repository scans, install the GitGuardian GitHub integration from the GitGuardian workspace and grant it access to the `model-arena` repository. This account-level connection is separate from the CLI and GitHub Actions configuration above.

If a real credential is detected, revoke or rotate it at its provider before removing it from the source history.
