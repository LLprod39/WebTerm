# Project Review Action Plan

Last reviewed: 2026-05-27

This is the current implementation backlog after refreshing the docs against the codebase. It replaces the older 2026-05-19 action list.

## Checks Performed During This Refresh

- Reviewed current docs under `docs/`.
- Reviewed current project files with `rg --files`.
- Checked pipeline node contract against `studio/pipeline_validation.py`, `studio/models.py`, `studio/pipeline_executor.py`, `studio/trigger_dispatch.py`, `studio/executor/`, and frontend node metadata.
- Ran `python scripts\check_architecture_sizes.py --strict-new`.
  - Import boundaries: passed.
  - File-size guard: failed on `key_mcp.py` because it grew from pinned baseline `2089` to `2094` lines.

Full test suites were not run during the documentation refresh.

## Current Product Summary

WebTerm is a web-first ops platform:

- Django/Channels backend for API, auth, access, desktop API, WebSockets, and background orchestration.
- React/Vite SPA in `frontend/`.
- Servers domain for inventory, SSH/RDP, SFTP, Linux UI, monitoring, alerts, memory, snapshots, and server agents.
- Studio domain for pipelines, triggers, runs, MCP registry, skills, reusable agents, templates, and notifications.
- `app/` for shared LLM/runtime/safety/agent-kernel services.
- Optional WinUI desktop client under `desktop/`.

## P0: Fix The Broken Architecture Guard

Scope:

- `key_mcp.py`
- `pyproject.toml`
- `scripts/check_architecture_sizes.py`

Problem:

The guard fails because `key_mcp.py` is a legacy-pinned file and grew by 5 lines.

Recommended task:

1. Inspect recent growth in `key_mcp.py`.
2. Prefer extracting/shrinking code below the pinned baseline.
3. If growth is intentional and unavoidable, update the baseline with a short note.
4. Re-run `python scripts\check_architecture_sizes.py --strict-new`.

Acceptance:

- Architecture check is green.
- Import boundaries remain green.

## P0: Shared Execution Policy

Scope:

- `app/agent_kernel/permissions/engine.py`
- `app/tools/safety.py`
- `app/tools/ssh_tools.py`
- `app/tools/server_tools.py`
- `servers/services/terminal_ai/`
- `studio/pipeline_executor.py`
- `studio/mcp_client.py`
- `tests/test_agent_and_pipeline_policy_enforcement.py`
- `tests/test_command_safety.py`

Problem:

Mutating execution paths exist across SSH, MCP, webhooks, file operations, pipeline nodes, terminal AI, and server agents. They need the same decision/audit model.

Recommended task:

1. Define a shared `ExecutionPolicyDecision` shape.
2. Include user, operation kind, target, redacted preview, risk categories, policy mode, approval requirement, and audit event metadata.
3. Wire it into pipeline SSH/MCP/webhook outputs and terminal/server tool paths.
4. Add tests proving direct pipeline nodes cannot bypass policy.

Acceptance:

- Dangerous command/tool/webhook paths share a common gate.
- Redacted evidence is available for audit.

## P0: Capability-Based Shared Server Access

Scope:

- `servers/models.py`
- `servers/views/server_helpers.py`
- `servers/views/server_crud.py`
- `servers/views/server_files.py`
- `servers/views/server_ops.py`
- `servers/views/server_shares.py`
- `servers/consumers/ssh_terminal.py`
- `servers/consumers/rdp_terminal.py`
- `tests/test_servers_api_smoke.py`

Problem:

Server sharing should distinguish viewing metadata from connecting, executing, writing files, using RDP, and administering shares.

Recommended task:

1. Add or derive explicit capabilities.
2. Add `require_server_access(user, server, capability)` helper.
3. Replace broad accessible-server checks in risky endpoints.
4. Add negative tests for shared users.

Acceptance:

- View-only shared users cannot execute commands, open RDP, upload/write/delete/chmod/chown files, or reveal/administer secrets.
- Owners keep full access.

## P0: Egress Redaction

Scope:

- `app/agent_kernel/memory/redaction.py`
- `servers/services/egress_redaction.py`
- logger/activity/event writes under `core_ui/`, `servers/`, `studio/`, `app/`
- `tests/test_egress_redaction.py`
- `tests/test_memory_redaction.py`

Problem:

Redaction needs to be consistently applied before data leaves runtime boundaries: logs, activity records, MCP args, pipeline outputs, reports, and prompt context.

Recommended task:

1. Make one egress redaction helper canonical.
2. Add high-entropy fallback with conservative false-positive controls.
3. Replace ad hoc redaction at logging/report/event output points.
4. Add regression tests with token/password/bearer/private-key examples.

Acceptance:

- No raw test secret appears in logs, activity payloads, pipeline node excerpts, or memory/report output.

## P1: Continue Pipeline Executor Migration

Scope:

- `studio/pipeline_executor.py`
- `studio/executor/`
- `studio/pipeline_validation.py`
- `tests/test_studio_node_executors.py`
- `tests/test_studio_pipeline_v2.py`
- `tests/test_studio_all_nodes_smoke.py`

Current state:

- Target registry exists.
- `output/report` and `output/webhook` have registry implementations.
- Production execution still mostly goes through `studio/pipeline_executor.py`.

Recommended task:

Migrate one node type per change, starting with low-risk logic/output nodes. Keep behavior stable and add node-level tests.

Acceptance:

- Node-specific logic moves out of the monolithic executor without changing pipeline run behavior.

## P1: Frontend Decomposition

Scope:

- `frontend/src/lib/api.ts`
- `frontend/src/api/`
- `frontend/src/pages/PipelineEditorPage.tsx`
- `frontend/src/pages/Servers.tsx`
- `frontend/src/components/terminal/LinuxUiPanel.tsx`
- relevant page/component tests

Current state:

- Domain API modules exist under `frontend/src/api/`.
- Some large compatibility entry points remain.

Recommended task:

Move API calls and controller state by domain, keeping exports compatible until callers are migrated.

Acceptance:

- Large frontend files shrink.
- Tests/build pass.
- No redesign is bundled with pure decomposition work.

## P1: Settings And AI Memory Consolidation

Scope:

- `frontend/src/pages/SettingsPage.tsx`
- `frontend/src/pages/settings/SettingsMemoryPage.tsx`
- `servers/views/server_memory.py`
- `servers/services/memory_service.py`

Problem:

Settings and memory-related UI/service paths have evolved through several iterations. Keep one canonical route and payload contract.

Acceptance:

- One supported AI Memory settings surface.
- Payload fields match backend contract exactly.

## P1: Production Worker Topology

Scope:

- `docker-compose.production.yml`
- `render.yaml`
- `servers/management/commands/`
- `studio/management/commands/`
- `docs/`

Recommended task:

Document and configure production processes for:

- HTTP backend
- Channels/Redis
- scheduled pipelines
- scheduled agents
- monitor
- watchers
- memory dreams
- agent execution plane

Acceptance:

- A deployer can see which features require which process.
- Missing worker mode is explicit, not silent.

## Completed Or Demoted Items

| Item | Current status |
| --- | --- |
| `servers.mcp_tool_runtime` shim | Done. Deleted. Studio owns the concrete MCP runtime; server agents use `MCPRuntimeProvider`. |
| `passwords/` package | Done. Folder is gone; only migration/historical references remain. |
| Backend view monolith split | Mostly done. Focused modules exist; `_views_all.py` files are compatibility shims. |
| Root frontend ambiguity | Mostly done. Active app is `frontend/`; docs point there. |
| Old docs drift | Addressed in this refresh under `docs/`. |

## Agent Task Template

```text
Task type: discovery | implementation | tests | docs
Scope: <paths>
Goal: <one concrete objective>
Constraints:
- Do not commit or push.
- Do not touch unrelated files.
- Do not print secret values.
- Preserve compatibility unless removal is explicitly in scope.
Return:
- summary
- files inspected
- files changed
- tests/checks run
- risks/open questions
```
