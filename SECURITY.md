# Security scanning

Model Arena uses GitGuardian in two places:

- `.pre-commit-config.yaml` defines a local `ggshield` scan before commits.
- `.github/workflows/gitguardian.yml` scans repository changes in GitHub Actions.

## Enable the GitHub Actions scan

1. Create a GitGuardian API key with the `scan` scope. A service-account token is suitable for CI.
2. In GitHub, open **Settings → Secrets and variables → Actions** for this repository.
3. Add a repository secret named `GITGUARDIAN_API_KEY` with the token as its value.
4. Push a commit or run **GitGuardian secret scan** from the Actions tab.
5. After the first successful run, consider requiring the `Scan for exposed secrets` check in branch protection.

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
