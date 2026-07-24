# Contributing to WebTerm

Thank you for improving WebTerm. This file is the complete contributor entry point for the supported development path.

## Supported workstation path

Release evidence is produced on Linux. On Windows, run the backend in WSL and keep the native Windows environment separate.

Prerequisites:

- Python 3.11;
- Node.js 22.23.1 and npm 10.9.8;
- Docker with Compose for PostgreSQL/Redis integration checks;
- WSL 2 when developing from Windows.

From the repository root in WSL:

```bash
./bootstrap-linux.sh --no-docker
source .venv-wsl/bin/activate
python manage.py check --settings=web_ui.settings.test
```

The bootstrap installs the hashed `requirements-dev.lock` with `--require-hashes` and the frontend with `npm ci`. Do not reuse `.venv-wsl` from native Windows; the Windows helper deliberately uses `.venv-windows`.

## Make a focused change

1. Branch from `test`; `main` is the promotion target.
2. Keep one responsibility per change. Do not combine architecture, redesign and behavior changes.
3. Preserve public imports with a facade when splitting a module.
4. Add a regression or contract test before changing behavior.
5. Never commit `.env`, credentials, logs, generated evidence or local agent files.

## Required local checks

Backend and repository contracts:

```bash
ruff format --check .
ruff check .
python scripts/verify_runtime_contract.py
python scripts/verify_release_identity.py
python scripts/verify_docs_contract.py
python scripts/check_architecture_sizes.py --strict-new
lint-imports
python manage.py check --settings=web_ui.settings.test
python manage.py makemigrations --check --dry-run --settings=web_ui.settings.test
python -m pytest tests app core_ui servers studio kubernetes_ops plugin_marketplace mars
```

Frontend:

```bash
cd frontend
npm ci
npm run lint
npm run typecheck
npm run test:coverage
npm run build:budget
npm run test:e2e
```

PostgreSQL/Redis integration and production checks run in CI. If your change touches those surfaces, run the matching Compose flow from the [release checklist](docs/releases/V0_1_RELEASE_CHECKLIST.md).

## Pull request evidence

Describe the user-visible outcome, tests run, migration or rollback needs, and security impact. Link the Linear issue. A green local command is evidence for the commit, not approval for release.

Security reports follow [SECURITY.md](SECURITY.md). Community behavior follows [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
