# MARS Architecture Refactoring Status

Last reviewed: 2026-06-15

This folder now records the current status of the MARS-driven refactor history. It is not the live queue source of truth; live MARS queue/debug state, when needed, lives outside this docs folder.

## Current Summary

| Area | Status |
| --- | --- |
| Import boundaries | Green. `import-linter` passed during `python scripts\check_architecture_sizes.py --strict-new`. |
| Size guard | Green. `key_mcp.py`, `frontend/src/lib/api.ts`, and remaining large route/consumer files are pinned to reduced baselines; several formerly pinned service files are now below the standard limit. |
| Memory store import path | Done. Callers use `servers.adapters.memory_store.DjangoServerMemoryStore`. |
| MCP runtime ownership | Done. `servers.mcp_tool_runtime` is deleted; server agents use `MCPRuntimeProvider`; Studio owns concrete MCP runtime. |
| `passwords/` package | Done. Folder is absent. |
| Backend view split | Mostly done. Focused modules own endpoint groups; `_views_all.py` files are compatibility shims. |
| Terminal service extraction | Substantial progress. Many terminal input, lifecycle, AI, event, snapshot, preference, stream-state, Nova/session context, report, memory, and policy services exist; Linux UI command constants, pure parsers, runtime helpers, and resource snapshots are split out of `servers/linux_ui.py`; SSH consumer compatibility helpers now delegate to focused service functions. |
| Server share capabilities | Done. Shared access is capability-based for terminal, command, files, context, secret reveal, and share administration. |
| Shell safety parser | Current audit cases covered for chained commands, shell pipes/substitution, quoted executables, `bash -c` encoded payloads, and inline base64 exec. |
| Egress redaction | In progress. Canonical helper covers AI WebSocket events and activity log description/metadata; pipeline/MCP/report/logger sinks still need targeted audit. |
| Studio node registry | Done for current executable node handlers. Notification, Telegram polling, interactive approval/input, redaction, routing, context, run-state, run setup, run loop/finalization, direct MCP agent helpers, direct LLM agent helpers, server-backed agent runtime helpers, output compatibility helpers, and simple logic helpers are extracted; `studio/pipeline_executor.py` is below the standard architecture limit. |
| Studio template data split | Done. Built-in pipeline template groups live under `studio/pipeline_templates/`; `studio/templates_data.py` stays as the compatibility export. |
| Frontend decomposition | In progress. Domain API modules exist; MARS page, Pipeline Editor, Servers page helpers/panels, Settings page AI/memory helpers, Linux UI overview/process/workspace/apps/service/log/disk/network/docker/package components, SFTP/server-file API modules, MARS API modules, server-memory API modules, monitoring/admin dashboard API modules, and agents/runs/schedules API modules are split into focused modules; other large route/components remain pinned. |
| MARS worker decomposition | Done for current size guard. `mars/worker.py` owns orchestration flow; process and CLI phase helpers live in `mars/worker_phases.py`. |
| MARS subprocess compatibility | Done. Interview capture uses `mars/subprocess_compat.py`; worker streaming falls back to threaded `subprocess.Popen` when the active Windows event loop cannot create async subprocess transports. |

## Completed Refactor Themes

- Architecture guard restored to green.
- Architecture checker and import-linter contracts were added.
- Django memory store implementation moved behind `servers.adapters.memory_store`.
- Many memory workflows moved into focused `servers/adapters/django_memory_*.py` modules.
- `core_ui`, `servers`, and `studio` view endpoint groups were split into focused modules.
- Terminal services were extracted for command parsing, connection records, command history, preferences, report generation, memory extraction, planning, decisions, output explanation, access, connection options, events, lifecycle, plan items, and snapshotting.
- Linux UI command constants, pure parsers/validators, SSH runtime/capabilities, and resource snapshots were extracted to focused `servers/linux_ui_*` modules.
- SSH terminal stream marker filtering, exit-future resolution, and bounded sanitized output buffers were extracted to `servers/services/terminal_stream_state.py`.
- SSH terminal manual command output/finalization state was extracted to `servers/services/terminal_manual_command_state.py`.
- SSH terminal Nova/session context helpers were extracted to `servers/services/terminal_nova_context.py`.
- Keycloak MCP tool schema metadata, JSON-RPC response helpers, summary-shaping helpers, config/profile helpers, MCP transport helpers, and role-management helpers were extracted to focused `key_mcp_*` modules, reducing `key_mcp.py` while preserving private compatibility entrypoints.
- MCP runtime bridge was inverted through `MCPRuntimeProvider`.
- Server share permissions were converted to explicit capabilities with negative tests.
- Shell safety detection was expanded beyond raw regex matching for the listed audit evasions.
- Egress redaction was centralized in `app.egress_redaction` and applied to activity logs plus outbound AI events.
- Pipeline node handlers were routed through the registry; current executable node types live under `studio/executor/nodes/`.
- Pipeline Editor palette, assistant panel, run monitor, run dialog, flow summary bar, and pure helper utilities were extracted under `frontend/src/pages/pipeline-editor/`.
- Pipeline Editor trigger configuration sections were extracted under `frontend/src/pages/pipeline-editor/TriggerConfigSections.tsx`.
- Pipeline Editor node configuration UI was extracted to `frontend/src/pages/pipeline-editor/NodeConfigPanel.tsx` and focused `node-config/` section modules.
- Servers page-local types, playbook helpers/panel, server list tab, memory snapshot helpers, server form helpers, rules/env helpers, and formatters were extracted under `frontend/src/pages/servers/`.
- Settings page constants, AI settings form/panels, memory settings panel, leaf UI components, access navigation, logging controls, activity log table, and memory overview panels were extracted under `frontend/src/pages/settings-page/`.
- Linux UI overview, processes, workspace chrome/apps, services, logs, disk, network, Docker, shared summary cards, and package-manager window UI were extracted under `frontend/src/components/terminal/linux-ui/`, and the inactive desktop/window-shell interaction model was removed from the active panel.
- SFTP/server-file API calls and types were extracted to `frontend/src/api/server-files.ts`.
- MARS API calls and types were extracted to `frontend/src/api/mars.ts`.
- Server-memory API calls and types were extracted to `frontend/src/api/server-memory.ts`.
- Monitoring/admin dashboard API calls and types were extracted to `frontend/src/api/monitoring.ts`.
- Agents/runs/schedules API calls and types were extracted to `frontend/src/api/agents.ts`.
- Multi-agent task construction, plan/decision parsing, and final-report task-table helpers were extracted to `servers/multi_agent_plan_helpers.py`.
- Built-in Studio pipeline templates were split into grouped modules under `studio/pipeline_templates/`, with the public `PIPELINE_TEMPLATES` export preserved.
- Studio template recommendation data, placeholder handling, argument binding, and text helpers were extracted under `studio/services/pipeline_template_*`, bringing `pipeline_template_recommendations.py` below the standard limit.
- Ops node command/argument helpers, context helpers, action helpers, alert-update helpers, and HTTP-check execution helpers were extracted to focused `studio/executor/nodes/ops_*` modules, bringing `studio/executor/nodes/ops.py` below the standard limit.
- MARS interview and worker CLI subprocess execution now has Windows-safe fallback coverage for Selector event loops.

## Open Refactor Themes

- Continue shrinking legacy-large files.
- Keep `studio/pipeline_executor.py` below the standard architecture limit without moving node logic back into it.
- Continue frontend API/controller decomposition.
- Keep production worker topology explicit in docs and deploy config.

## How To Resume Refactor Work

1. Check `git status --short`.
2. Run the architecture guard.
3. Pick one narrow task from `docs/mars/MARS_TODO_LIST.md`.
4. Update tests for that task only.
5. Update this status file if the refactor status changes.
