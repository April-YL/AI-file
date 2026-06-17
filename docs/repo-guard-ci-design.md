# Repository Guard CI Design

This document defines the CI integration design for the repository guard.

This is a design document only. It does not add a GitHub Actions workflow, change source code, change guard behavior, or introduce new checks.

## CI v1 Principle

CI v1 must call the same local validation entrypoint used by developers and agents:

```bash
python scripts/check_repo_guard.py
```

`scripts/check_repo_guard.py` is the single source of validation result.

CI must not reinterpret child check output, parse warning text, or run child guards separately.

## Decision Rule

CI v1 must use only the process exit code from `scripts/check_repo_guard.py`:

- exit code `0`: pass
- non-zero exit code: fail

Warnings are allowed in CI v1 as long as the final repository guard exit code is `0`.

This matches the current architecture guard rollout model:

- existing legacy exceptions are reported as `WARN`
- new hard violations are reported as `FAIL`
- only `FAIL` blocks the pipeline

## Scope Of CI v1

CI v1 should run only:

```bash
python scripts/check_repo_guard.py
```

It should not run:

- `pytest`
- lint
- formatter checks
- direct architecture sub-checks
- direct secret sub-checks
- cleanup scripts
- runtime QC report generation

Those checks may be added later as separate CI jobs after the guard baseline is stable.

## Recommended GitHub Actions Shape

The future workflow should be minimal:

```yaml
name: Repository Guard

on:
  pull_request:
  push:
    branches:
      - architecture-baseline

jobs:
  repo-guard:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Run repository guard
        run: python scripts/check_repo_guard.py
```

This snippet is illustrative. It is not applied by this document.

## Current Secret Guard Limitation In CI

`scripts/check_staged_no_secrets.py` checks staged local changes.

In CI, there is no normal developer staging area, so this check may pass without examining a pull request diff in the same way it does locally.

This is acceptable for CI v1 because the goal is to reuse the local guard entrypoint without changing behavior.

Future CI hardening may add a CI-specific committed-diff secret check, such as:

- checking changed files in a pull request
- checking the latest commit diff
- scanning tracked files for forbidden environment files or obvious API key patterns

That should be added as a separate explicit change, not hidden inside CI v1.

## Future Expansion Boundaries

Future CI expansion may add:

- GitHub Actions workflow file under `.github/workflows/`
- CI-specific secret diff checks
- pytest jobs
- lint or formatting jobs
- architecture guard strict mode after legacy exceptions are reduced

Future CI expansion must still preserve this rule:

```text
check_repo_guard.py remains the single source of repository guard validation result.
```

CI jobs may add additional independent checks later, but they must not reinterpret repository guard warnings as failures unless the guard itself changes its exit code policy.
