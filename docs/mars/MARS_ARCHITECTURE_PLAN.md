# MARS Architecture Review And Migration Plan

Last reviewed: 2026-05-27

This plan is the current architecture migration map after the MARS refactor work. Older statements about deleted shims or completed splits were rechecked against this checkout.

## Goal

Keep WebTerm modular enough for safe ops automation:

- `core_ui` owns auth, access, settings, admin, and shared UI redirects.
- `servers` owns server inventory, terminal/RDP/SFTP/Linux UI, monitoring, alerts, memory, snapshots, and server agents.
- `studio` owns pipelines, triggers, runs, MCP registry, reusable agent configs, skills, templates, and notifications.
- `app` owns shared runtime, LLM, policy, safety, and agent-kernel abstractions.
- `web_ui` wires the Django project, settings, URLs, ASGI/WSGI, Channels, and Celery.
- `frontend` owns the SPA.

## Current Verified Facts

- `servers.mcp_tool_runtime` does not exist.
- `passwords/` does not exist.
- `studio.mcp_tool_runtime` is the concrete MCP runtime owner.
- Server agents depend on `MCPRuntimeProvider`.
- `servers.adapters.memory_store` is the canonical memory store import path.
- Import boundaries pass.
- Architecture size guard currently fails only on `key_mcp.py` legacy growth.
- `studio/pipeline_executor.py` remains active production execution logic.
- `studio/executor/` is the target node-registry architecture.

## Target Dependency Direction

```mermaid
flowchart TD
    web_ui --> core_ui
    web_ui --> servers
    web_ui --> studio
    core_ui --> app
    servers --> app
    studio --> app
    frontend --> core_ui
    frontend --> servers
    frontend --> studio
    app -. no feature-app imports .-> app
```

Rules:

- `app.core` and `app.agent_kernel` should avoid feature-app dependencies.
- `servers` and `studio` should communicate through explicit app-level ports, services, signals, or API boundaries.
- Cross-context exceptions must be listed in `.importlinter`.
- New files should stay below the architecture standard size limit.

## Current Hotspots

| File/area | Why it matters |
| --- | --- |
| `key_mcp.py` | Currently breaks the size guard by growing past baseline. |
| `studio/pipeline_executor.py` | Still centralizes most node-specific runtime logic. |
| `frontend/src/lib/api.ts` | Large compatibility API surface while domain modules exist. |
| `frontend/src/pages/PipelineEditorPage.tsx` | Large route component with graph/editor/run orchestration. |
| `frontend/src/components/terminal/LinuxUiPanel.tsx` | Large operational UI component. |
| `servers/consumers/ssh_terminal.py` | Smaller than old state but still a large protocol adapter/queue runner. |
| `servers/adapters/django_memory_store.py` | Facade remains large even after many extractions. |

## Migration Roadmap

### Phase 0: Restore Green Guardrails

- Shrink or intentionally re-pin `key_mcp.py`.
- Run `python scripts/check_architecture_sizes.py --strict-new`.
- Keep import-linter green.

### Phase 1: Finish Studio Node Registry

- Ensure migrated nodes are auto-registered.
- Route `output/report` and `output/webhook` through registry.
- Migrate `logic/condition`.
- Migrate `logic/merge`.
- Continue one node type per change.

Acceptance:

- `studio/pipeline_executor.py` loses node-specific branches incrementally.
- `tests/test_studio_node_executors.py`, `tests/test_studio_pipeline_v2.py`, and all-node smoke stay green.

### Phase 2: Tighten Execution Policy

- Add one execution policy/audit decision model.
- Apply it to SSH, MCP, files, webhooks, terminal AI, server agents, and pipeline nodes.
- Make redaction mandatory at egress points.

Acceptance:

- Risky operations have consistent plan/approval/apply/verify/audit behavior.

### Phase 3: Capability-Based Server Sharing

- Define view/connect/execute/file-read/file-write/RDP/context/admin capabilities.
- Enforce capabilities in views, consumers, and tools.
- Add negative tests for shared users.

### Phase 4: Continue Frontend Decomposition

- Finish moving calls out of `frontend/src/lib/api.ts`.
- Extract controller hooks from large route components.
- Keep visual redesign separate from decomposition.

### Phase 5: Production Operability

- Document required worker processes.
- Align `docker-compose.production.yml` and `render.yaml` with background features.
- Add visible worker heartbeat/status where useful.

## Public Interfaces Between Contexts

| Context | Stable interface |
| --- | --- |
| `core_ui` | URL/API endpoints and auth/session/access services. |
| `servers` | `servers/urls.py`, WebSocket consumers, server services, memory adapter. |
| `studio` | `studio/urls.py`, pipeline models, trigger dispatcher, MCP runtime provider. |
| `app` | LLM/runtime/policy/safety abstractions and protocols. |
| `frontend` | API clients under `frontend/src/api/` and route components. |

## Testing Strategy

- Architecture: `python scripts/check_architecture_sizes.py --strict-new`.
- Backend smoke: `python -m pytest tests/test_core_ui_api_smoke.py tests/test_servers_api_smoke.py tests/test_studio_api_smoke.py`.
- Studio runtime: `python -m pytest tests/test_studio_pipeline_v2.py tests/test_studio_node_executors.py tests/test_studio_all_nodes_smoke.py`.
- Frontend: `npm run test`, `npm run build`, and targeted Playwright specs from `frontend/`.

## Definition Of Done

- Architecture guard is green.
- Legacy-large files stop growing.
- Pipeline node behavior is mostly registry-owned.
- Dangerous operations share one policy/audit/redaction contract.
- Server sharing is capability-based.
- Production docs and config identify every required background worker.
