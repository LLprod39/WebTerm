# Project Structure

This repository keeps only convention-required files in the root.

## Root

- `.git/` - local Git database; do not move or edit manually.
- `.github/` - GitHub Actions, GitHub command configs, and README images; must stay at the root for GitHub.
- `.env*`, `.model_config.json`, `.notification_config.json`, `db.sqlite3` - local runtime state and secrets; ignored by Git.
- `.importlinter`, `.pre-commit-config.yaml`, `pyproject.toml` - architecture and Python tooling entry points.
- `docker-compose*.yml`, `render.yaml` - deployment entry points that common tools expect at the root.
- `requirements*.txt`, `manage.py` - backend setup and Django entry points.

## Main Folders

- `frontend/` - React/Vite SPA.
- `web_ui/`, `core_ui/`, `servers/`, `studio/`, `app/` - Django backend and agent/runtime modules.
- `desktop/` - Windows desktop client.
- `docker/` - Dockerfiles and deployment helper scripts.
- `config/` - versioned config files that do not need root placement.
- `docs/` - markdown reports, MARS artifacts, QA plans, and local-only internal notes.
- `scripts/` - reusable maintenance scripts only.
- `tests/` - automated test suites.

## Removed From Root

- `ai-server-terminal-main/` was renamed to `frontend/`.
- `passwords/` was removed; it was a deprecated compatibility shim.
- `.windsurf/` was removed; it only contained editor workflow notes.
- `agent_projects/` was removed and ignored; it is runtime/generated storage.
- Root Vite wrapper files were removed; frontend commands now run from `frontend/`.
