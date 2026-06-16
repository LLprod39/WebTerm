# Project Review Action Plan

Last reviewed: 2026-06-15

This is the current implementation backlog after refreshing the docs against the codebase. It replaces the older 2026-05-19 action list.

## Checks Performed During This Refresh

- Reviewed current docs under `docs/`.
- Reviewed current project files with `rg --files`.
- Checked pipeline node contract against `studio/pipeline_validation.py`, `studio/models.py`, `studio/pipeline_executor.py`, `studio/trigger_dispatch.py`, `studio/executor/`, and frontend node metadata.
- Ran `python scripts\check_architecture_sizes.py --strict-new`.
  - Import boundaries: passed.
  - File-size guard: passed.

Full test suites were not run during the documentation refresh.

## Current Product Summary

WebTerm is a web-first ops platform:

- Django/Channels backend for API, auth, access, WebSockets, and background orchestration.
- React/Vite SPA in `frontend/`.
- Servers domain for inventory, SSH, SFTP, Linux UI, monitoring, alerts, memory, snapshots, and server agents.
- Studio domain for pipelines, triggers, runs, MCP registry, skills, reusable agents, templates, and notifications.
- `app/` for shared LLM/runtime/safety/agent-kernel services.

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

Current state:

- `app.execution_policy` builds shared redacted policy audit metadata.
- `PermissionEngine` decisions include `execution_policy` metadata with operation kind, target, policy mode, risk categories, and redacted preview.
- Direct `ssh_execute` / `server_execute` activity logs include that metadata.
- MCP argument logger previews now use the shared redaction helper.
- Studio graph policy decisions now attach the same shared `audit_metadata` shape, and pipeline run summaries persist it under `trigger_data.execution_policy.items[*].audit_metadata`.

Recommended task:

1. Converge Studio graph validation and runtime tool permission decisions onto one enforcement contract.
2. Wire newly added mutating pipeline/report/file sinks into the same metadata as they are introduced.
3. Add tests proving every mutating node/tool family cannot bypass policy.

Acceptance:

- Dangerous command/tool/webhook paths share a common gate.
- Redacted evidence is available for audit.

## Completed: Capability-Based Shared Server Access

Scope:

- `servers/models.py`
- `servers/views/server_helpers.py`
- `servers/views/server_crud.py`
- `servers/views/server_files.py`
- `servers/views/server_ops.py`
- `servers/views/server_shares.py`
- `servers/consumers/ssh_terminal.py`
- `tests/test_servers_api_smoke.py`

Status:

- `ServerShare` has explicit capability fields for terminal connect, command execution, and file read/write.
- Risky endpoints use capability checks instead of broad server visibility.
- View-only shared users cannot execute commands, open terminal, access/write files, reveal saved secrets, or administer shares.
- Regression coverage lives in `tests/test_server_share_capabilities.py` and `tests/test_terminal_access_service.py`.

## Completed: SSH Terminal Stream-State Extraction

Scope:

- `servers/consumers/ssh_terminal.py`
- `servers/services/terminal_stream_state.py`

Status:

- Marker filtering, AI exit-future resolution, and bounded sanitized output buffers now live in a focused service module.
- The WebSocket consumer remains the compatibility owner for existing private methods and async persistence hooks.
- The legacy size baseline for `servers/consumers/ssh_terminal.py` was lowered from 4097 to 3189 lines.

## P0: Egress Redaction

Scope:

- `app/agent_kernel/memory/redaction.py`
- `servers/services/egress_redaction.py`
- logger/activity/event writes under `core_ui/`, `servers/`, `studio/`, `app/`
- `tests/test_egress_redaction.py`
- `tests/test_memory_redaction.py`

Problem:

Redaction needs to be consistently applied before data leaves runtime boundaries: logs, activity records, MCP args, pipeline outputs, reports, and prompt context.

Current state:

- `app.egress_redaction` is the canonical helper.
- `studio.pipeline_redaction` centralizes pipeline text/context/node-output redaction for executor compatibility code and output node modules.
- AI WebSocket text events use it through `servers/services/egress_redaction.py`.
- `UserActivityLog.description` and `metadata` are redacted before persistence.
- Agent tool-argument previews and MCP argument logger previews use redacted payload previews.
- Pipeline webhook payloads, templated context-derived headers, and returned webhook URLs are redacted.
- Provider API error bodies, MCP HTTP errors, Telegram polling error bodies, terminal/multi-agent parse-failure snippets, and `ops/http_check` body/URL/error excerpts are redacted before logging or persistence.

Recommended task:

1. Continue auditing newly added pipeline/MCP/report/logger output points.
2. Add high-entropy fallback with conservative false-positive controls.
3. Add regression tests with token/password/bearer/private-key examples at each remaining sink.

Acceptance:

- No raw test secret appears in logs, activity payloads, pipeline node excerpts, or memory/report output.

## P1: Pipeline Executor Orchestration Cleanup

Scope:

- `studio/pipeline_executor.py`
- `studio/executor/`
- `studio/pipeline_validation.py`
- `tests/test_studio_node_executors.py`
- `tests/test_studio_pipeline_v2.py`
- `tests/test_studio_all_nodes_smoke.py`

Current state:

- Target registry exists and current executable node handlers are registered in `studio/executor/nodes/`.
- `PipelineExecutor._execute_node` dispatches registered node types through the registry.
- Shared email/Telegram notification helpers were extracted to `studio/pipeline_notifications.py` while preserving compatibility imports for existing tests and management commands.
- Telegram approval polling and operator-reply routing were extracted to `studio/pipeline_telegram.py`; `run_telegram_bot` now imports reply routing from that module directly.
- Pipeline text/context/output redaction was extracted to `studio/pipeline_redaction.py`; output email/report/webhook/Telegram nodes now use the shared helpers.
- Routing helpers, graph construction, and route queue release were extracted to `studio/pipeline_routing.py`; `pipeline_executor.py` keeps compatibility aliases for internal call sites.
- Context helpers were extracted to `studio/pipeline_context.py`; template rendering, enriched node context, actor context, role/permission normalization, compact output context, and pipeline tool/ops prompt helpers are centralized.
- Run-state helpers were extracted to `studio/pipeline_run_state.py`; node/run/routing state persistence, activity logging, and Channels notifications no longer live directly in the orchestrator.
- Run setup helpers were extracted to `studio/pipeline_run_setup.py`; context normalization, graph validation, entry trigger checks, execution-policy summary capture, and initial run snapshot persistence no longer live directly in the orchestrator.
- Run loop/finalization helpers were extracted to `studio/pipeline_run_loop.py`; batch execution, routing continuation, abort/stop handling, and final run status updates no longer live directly in the orchestrator.
- Direct MCP agent helpers were extracted to `studio/pipeline_agent_mcp.py`; argument coercion, skill policy application, permission/sandbox checks, MCP calls, and result formatting no longer live directly in the orchestrator.
- Direct LLM agent helpers were extracted to `studio/pipeline_agent_llm.py`; provider/model resolution, server memory loading, operational recipe context, response generation, and streaming callbacks no longer live directly in the orchestrator.
- Server-backed agent runtime helpers were extracted to `studio/pipeline_agent_runtime.py`; `agent/react`, `agent/multi`, direct SSH command execution, SSH activity logging, and server-agent runtime calls no longer live directly in the orchestrator.
- Output compatibility helpers were extracted to `studio/pipeline_outputs.py`; email, report, webhook, and Telegram output helper implementations no longer live directly in the orchestrator.
- Simple logic compatibility helpers were extracted to `studio/pipeline_logic.py`; `logic/condition`, `logic/wait`, and `logic/merge` implementations are shared by registry nodes and legacy aliases.
- Interactive approval/input helpers were extracted to `studio/pipeline_interactions.py`; `logic/human_approval`, `logic/telegram_input`, and Telegram target resolution are shared by registry nodes and legacy aliases.
- `studio/pipeline_executor.py` is below the standard architecture limit and has been removed from the legacy baseline.
- `servers/adapters/django_memory_store.py` is below the standard architecture limit and has been removed from the legacy baseline; snapshot, dream, manual-knowledge, and snapshot-action delegates live in `servers/adapters/django_memory_store_mixins.py`.

Recommended task:

Continue shrinking the remaining legacy-large frontend, terminal, and API files one slice at a time. Keep behavior stable and add focused tests.

Acceptance:

- `studio/pipeline_executor.py` stays below the standard architecture limit without re-centralizing node-specific execution logic.

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
- `frontend/src/pages/MarsPage.tsx` is split into a controller plus MARS step/sidebar/utils modules.
- `frontend/src/pages/PipelineEditorPage.tsx` is reduced to 1289 lines; extracted palette, assistant, run-monitor, run dialog, flow summary bar, presentation, graph, cron, JSON schema, trigger config, `NodeConfigPanel`, and node-config modules live under `frontend/src/pages/pipeline-editor/`.
- `frontend/src/pages/Servers.tsx` is reduced to 2336 lines; extracted page-local types, playbook helpers/panel, server list tab, memory snapshot helpers, server form helpers, rules/env helpers, group dialog, and formatters live under `frontend/src/pages/servers/`.
- `frontend/src/pages/SettingsPage.tsx` is reduced to 425 lines and removed from legacy baselines; extracted settings constants, provider selector, section card, AI settings form/panels, memory settings panel, memory card leaf components, access navigation, logging controls, activity log table, and memory overview panels live under `frontend/src/pages/settings-page/`.
- `frontend/src/components/terminal/LinuxUiPanel.tsx` is reduced to 431 lines and removed from legacy baselines; overview, processes, workspace chrome/apps, services, logs, disk, network, Docker, package-manager UI, and shared summary cards live under `frontend/src/components/terminal/linux-ui/`, and the inactive desktop/window-shell model has been removed from the active panel.
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

## Completed Or Demoted Items

| Item | Current status |
| --- | --- |
| `servers.mcp_tool_runtime` shim | Done. Deleted. Studio owns the concrete MCP runtime; server agents use `MCPRuntimeProvider`. |
| `passwords/` package | Done. Folder is gone; only migration/historical references remain. |
| Backend view monolith split | Mostly done. Focused modules exist; `_views_all.py` files are compatibility shims. |
| Root frontend ambiguity | Mostly done. Active app is `frontend/`; docs point there. |
| Old docs drift | Addressed in this refresh under `docs/`. |
| Capability-based shared server access | Done. View-only shares are restricted by explicit capabilities and covered by negative tests. |
| Shell safety parser listed cases | Done for the current audit slice. Chained dangerous commands, pipe-to-shell, command/process substitution, quoted executables, `bash -c` encoded payloads, and inline base64 exec are covered. |
| Pipeline node registry dispatch | Done for current executable node types. `_execute_node` dispatches registered handlers from `studio/executor/nodes/`. |
| Notification helper extraction | Done. Shared notification config/defaults, email address normalization, and Telegram send helpers live in `studio/pipeline_notifications.py`. |
| Telegram polling extraction | Done. Approval callback polling and operator reply routing live in `studio/pipeline_telegram.py`. |
| Pipeline redaction helper extraction | Done. Pipeline text/context/node-output redaction helpers live in `studio/pipeline_redaction.py`. |
| Pipeline routing helper extraction | Done. Graph construction, route queue release, routing port calculation, routing-state serialization, reachability, and merge-source helpers live in `studio/pipeline_routing.py`. |
| Pipeline context helper extraction | Done. Template rendering, enriched node context, actor context, role/permission normalization, compact output context, and pipeline tool/ops prompt helpers live in `studio/pipeline_context.py`. |
| Pipeline run-state helper extraction | Done. Run/node/routing state persistence and pipeline run WebSocket event callbacks live in `studio/pipeline_run_state.py`. |
| Pipeline run setup helper extraction | Done. Context normalization, graph validation, entry trigger checks, execution-policy summary capture, and initial run snapshot persistence live in `studio/pipeline_run_setup.py`. |
| Pipeline run loop helper extraction | Done. Batch execution, routing continuation, abort/stop handling, and final run status updates live in `studio/pipeline_run_loop.py`. |
| Pipeline MCP agent helper extraction | Done. Direct MCP agent execution, argument coercion, skill policy application, permission/sandbox checks, MCP calls, and result formatting live in `studio/pipeline_agent_mcp.py`. |
| Pipeline LLM agent helper extraction | Done. Direct LLM agent execution, provider/model resolution, server memory loading, operational recipe context, response generation, and streaming callbacks live in `studio/pipeline_agent_llm.py`. |
| Pipeline server agent runtime extraction | Done. `agent/react`, `agent/multi`, direct SSH command execution, SSH activity logging, and server-agent runtime calls live in `studio/pipeline_agent_runtime.py`. |
| Pipeline output helper extraction | Done. Email, report, webhook, and Telegram output compatibility helpers live in `studio/pipeline_outputs.py`. |
| Pipeline simple logic helper extraction | Done. `logic/condition`, `logic/wait`, and `logic/merge` compatibility helpers live in `studio/pipeline_logic.py`. |
| Pipeline interaction helper extraction | Done. `logic/human_approval`, `logic/telegram_input`, and Telegram target resolution live in `studio/pipeline_interactions.py`. |
| Pipeline executor baseline removal | Done. `studio/pipeline_executor.py` is below the standard architecture limit and no longer appears in `[tool.architecture.legacy_baselines]`. |
| Server memory store baseline removal | Done. `servers/adapters/django_memory_store.py` is below the standard architecture limit and no longer appears in `[tool.architecture.legacy_baselines]`; snapshot, dream, manual-knowledge, and snapshot-action delegates live in `servers/adapters/django_memory_store_mixins.py`. |
| Server monitor baseline removal | Done. `servers/monitor.py` is below the standard architecture limit and no longer appears in `[tool.architecture.legacy_baselines]`; pure monitor output parsers live in `servers/monitor_parsing.py`. |
| Studio template data split | Done. `studio/templates_data.py` is now a thin compatibility export; grouped built-in pipeline templates live under `studio/pipeline_templates/`, and the legacy baseline entry was removed. |
| Stale baseline cleanup | Done for below-limit compatibility shims and frontend pages: memory exports, `_views_all.py` shims, `MCPHubPage`, `MarsPage`, and `PipelineRunsPage`. |
| Linux UI facade baseline removal | Done. `servers/linux_ui.py` is below the standard architecture limit and no longer appears in `[tool.architecture.legacy_baselines]`; runtime/capabilities and resource snapshots live in `servers/linux_ui_runtime.py` and `servers/linux_ui_resources.py`. |
| Keycloak MCP helper extraction | Done for this slice. Declarative MCP tool schemas live in `key_mcp_tools.py`, JSON-RPC response helpers live in `key_mcp_protocol.py`, summary helpers live in `key_mcp_summaries.py`, config/profile helpers live in `key_mcp_config.py`, MCP transport helpers live in `key_mcp_server.py`, role-management helpers live in `key_mcp_roles.py`; `key_mcp.py` keeps runtime/client behavior and its baseline was lowered to the current size. |
| Frontend API extraction | Done for this slice. Linux UI API calls/types live in `frontend/src/api/linux-ui.ts` and `frontend/src/api/linux-ui-types.ts`; SFTP/server-file API calls/types live in `frontend/src/api/server-files.ts`; MARS API calls/types live in `frontend/src/api/mars.ts`; server-memory API calls/types live in `frontend/src/api/server-memory.ts`; monitoring/admin dashboard API calls/types live in `frontend/src/api/monitoring.ts`; agents/runs/schedules API calls/types live in `frontend/src/api/agents.ts`; `frontend/src/lib/api.ts` re-exports them for compatibility and its baseline was lowered to the current size. |
| Studio template recommendation split | Done. `studio/services/pipeline_template_recommendations.py` is below the standard architecture limit; recommendation data, placeholder handling, argument binding, and text helpers live in focused modules. |
| Ops node helper extraction | Done for this slice. Pure ops command/argument helpers, context helpers, action helpers, alert-update helpers, and HTTP-check execution helpers live in focused `studio/executor/nodes/ops_*` modules; `studio/executor/nodes/ops.py` is below the standard limit and no longer pinned. |
| MARS worker phase extraction | Done. CLI command prefixing, process streaming, Codex/Gemini phases, verification, stop checks, and save helpers live in `mars/worker_phases.py`. |
| MARS Windows subprocess fallback | Done. Interview capture uses `mars/subprocess_compat.py`; worker streaming falls back to threaded `subprocess.Popen` when the active Windows event loop cannot create async subprocess transports. |
| Production worker topology | Done for current deploy configs. Compose has dedicated scheduler/agent/monitor/ops-supervisor workers and profile-only Telegram bot. Render has Key Value Redis plus starter worker services for scheduled pipelines, scheduled agents, monitor, and ops-supervisor. |

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
