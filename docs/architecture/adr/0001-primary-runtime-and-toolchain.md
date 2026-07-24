# ADR-0001: Primary runtime and toolchain

- Status: Accepted
- Date: 2026-07-22
- Decision owners: backend and frontend maintainers
- Applies to: development, CI, container builds and release evidence

## Context

WebTerm previously allowed Python 3.10+, built the backend with Python 3.11, built the frontend with Node 20, and relied on whatever Node/npm/Python happened to be installed locally. Test tools were mixed into the production dependency input. A Windows-created `.venv` had also been reused from WSL. Those combinations make results difficult to reproduce and can produce a false green result.

## Decision

The primary supported development and release runtime is Linux/WSL2:

| Surface | Supported value |
|---|---|
| Python source compatibility | `>=3.11,<3.13` |
| Canonical Python minor | `3.11` |
| Backend container | `python:3.11.15-slim-bookworm` |
| Django | `5.2.16` |
| Ruff target | `py311` |
| Node.js | `22.23.1` |
| npm | `10.9.8` |
| Frontend container | `node:22.23.1-bookworm-slim` |
| Canonical WSL environment | `.venv-wsl` |
| Native Windows compatibility environment | `.venv-windows` |

`requirements.lock` contains only production runtime packages. `requirements-dev.lock` contains that exact runtime, constrained by `requirements.lock`, plus test, lint, coverage, architecture and pre-commit tools. Both locks include hashes and are resolved for Python 3.11 on Linux. `frontend/package-lock.json` is installed with `npm ci`; `npm install` is not a release-evidence command.

Native Windows backend execution remains a compatibility convenience. It uses a separate environment and does not count as release evidence. Release evidence must come from a clean Linux/WSL2 or Linux CI checkout using the pinned toolchain.

## Enforcement

Run from the repository root:

```bash
python scripts/verify_runtime_contract.py
```

The verifier checks the project metadata, both Python locks, Docker base images, `.python-version`, `.nvmrc`, package metadata, the Playwright workflow, bootstrap instructions and the environment separation rule.

Regenerate locks only with the pinned resolver command documented in `README.md`. A lock change must include the input change and a passing runtime-contract check in the same pull request.

## Consequences

- Local Python 3.10, 3.13, 3.14 and Node 20/24 results can help diagnose problems but cannot approve a release.
- A feature that only works in the native Windows helper is not supported for the first release.
- CI will be migrated to the same versions before it becomes a required gate.
- Python 3.12 remains source-compatible but must be tested separately before it can replace 3.11 as the release runtime.
