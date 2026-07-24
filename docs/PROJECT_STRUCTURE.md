# Project Structure

Last reviewed: 2026-05-27

This repository is a Django + Channels backend, React/Vite SPA, and Studio automation layer. The root is intentionally kept for entry points that tools expect at the repository top level.

## Root Entry Points

| Path | Role |
| --- | --- |
| `README.md` | Public project overview and quickstart. |
| `manage.py` | Django management entry point. |
| `pyproject.toml` | Python metadata, pytest config, ruff config, architecture baselines. |
| `.importlinter` | Import-boundary contracts for the main Python packages. |
| `requirements*.txt` | Python dependency sets: default, mini, and full. |
| `docker-compose*.yml`, `render.yaml` | Local, production, smoke, and Render deployment entry points. |
| `.env.example`, `.env.production.example`, `.notification_config.example.json` | Versioned environment/config templates only. |

## Active Application Areas

| Path | Current responsibility |
| --- | --- |
| `web_ui/` | Django project shell: settings, URLs, ASGI/WSGI, Celery, WebSocket routing. `web_ui/settings.py` is a compatibility shim; prefer `web_ui.settings.development`, `.production`, or `.test`. |
| `core_ui/` | Auth/session APIs, settings/access/admin endpoints, audit/activity, shared UI redirects and middleware. |
| `servers/` | Server inventory, SSH terminal flows, SFTP/file actions, monitoring, alerts, watcher drafts, server memory, snapshots, and server-bound agents. |
| `studio/` | Pipelines, triggers, runs, MCP registry, reusable agents, skill authoring, pipeline templates, notifications. |
| `mars/` | MARS guided agent workflow, personal workspaces, run orchestration, worker phases, and live run APIs. |
| `app/` | Shared LLM/runtime/safety/agent-kernel code. Keep this layer as independent from Django feature apps as possible. |
| `frontend/` | React 18 + Vite + TypeScript SPA, TanStack Query, Tailwind/Radix local components, Vitest and Playwright tests. |
| `docker/` | Dockerfiles, nginx configs, and operational smoke scripts. |
| `config/` | Versioned config that should not live in the root, for example Keycloak profiles. |
| `scripts/` | Maintained maintenance scripts such as architecture-size checks and setup helpers. |
| `tests/` | Backend, integration, policy, terminal, memory, Studio, and API tests. |
| `docs/` | Current documentation, QA plans, reports, and ignored local-only docs. |

## Important Internal Boundaries

- `core_ui` should not accumulate server or Studio business logic. Cross-context exceptions are documented in `.importlinter`.
- `servers` and `studio` should not import each other directly except for explicitly tracked legacy exceptions.
- `app.agent_kernel` should remain pure Python/domain logic and avoid Django ORM dependencies.
- Large legacy files are pinned in `[tool.architecture.legacy_baselines]`; they may shrink, but they should not grow.
- `studio/pipeline_executor.py` is still the active run lifecycle wrapper and registry dispatch point, but it is below the standard architecture limit. Current executable node handlers dispatch through `studio/executor/nodes/`; shared notification, Telegram polling, interactive approval/input, pipeline redaction, routing, context, run-state/event, run setup, run loop/finalization, direct MCP agent helpers, direct LLM agent helpers, server-backed agent runtime helpers, output compatibility helpers, and simple logic helpers live outside the executor.

## Generated, Local, and Ignored Paths

These paths are intentionally not documentation sources of truth:

| Path | Treatment |
| --- | --- |
| `.venv-wsl/`, `.venv-windows/`, `node_modules/`, `frontend/node_modules/` | OS-specific local dependency installs. Ignored. Never share one virtual environment between Windows and WSL. |
| `frontend/dist/`, `frontend/playwright-report/`, `frontend/test-results/` | Generated frontend artifacts. Ignored. |
| `runtime_logs/`, `logs/`, `mars_logs/`, `.codex-logs/` | Runtime and agent logs. Ignored. |
| `agent_projects/` | Generated/local agent project storage. Ignored. |
| `db.sqlite3`, `*.sqlite`, `*.db`, `media/` | Local runtime data. Ignored. |
| `docs/local/` | Local-only internal docs. Ignored by git, but still useful in this workspace. |

## Historical Cleanup Already Reflected

- Root Vite wrapper files are no longer the active frontend source. Frontend commands run from `frontend/`.
- Old root copies of internal docs were moved under `docs/local/` and are ignored.
- Backend view monoliths now mostly act as compatibility shims while focused modules own endpoint groups.
- The old `servers.mcp_tool_runtime` shim and `passwords/` compatibility package are no longer present in this checkout; MCP runtime ownership is now under `studio.mcp_tool_runtime` with an app-level `MCPRuntimeProvider` bridge.
