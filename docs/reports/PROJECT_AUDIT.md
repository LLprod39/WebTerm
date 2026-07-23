# Project Audit Report

Last reviewed: 2026-06-15

This is the current audit snapshot for `C:\WebTrerm`. Older findings that were already fixed are kept only when they affect remaining work.

## Executive Summary

WebTerm is an ops control plane built from Django/Channels, a React/Vite SPA, SSH terminal tooling, Studio pipelines, MCP/skills, server agents, and layered server memory.

Current architecture is much healthier than the older audit described: most backend view groups have been split into focused modules, the old `servers.mcp_tool_runtime` shim is gone, and the `passwords/` compatibility package is gone. Import boundaries currently pass through `import-linter`.

The main open risks are now narrower:

1. Dangerous execution paths still need one shared policy/audit/redaction contract across SSH, MCP, webhooks, files, and pipeline nodes.
2. Egress redaction still needs to be made uniform across logs, activity records, pipeline excerpts, MCP args, reports, memory, and prompt context.
3. Several legacy-large files remain pinned and should shrink over time.

## Current Architecture Evidence

| Area | Current state |
| --- | --- |
| Import boundaries | `import-linter` passed on 2026-06-15. Contracts live in `.importlinter`. |
| Size guard | Green on 2026-06-15. `frontend/src/lib/api.ts`, `servers/consumers/ssh_terminal.py`, `Servers.tsx`, and `PipelineEditorPage.tsx` remain on reduced baselines; `studio/executor/nodes/ops.py`, `SettingsPage.tsx`, and `LinuxUiPanel.tsx` are below the standard limit. |
| Backend views | `core_ui/views/`, `servers/views/`, and `studio/views/` are split into focused modules with compatibility shims. |
| MCP runtime | Server agents use `MCPRuntimeProvider`; concrete implementation lives in `studio.mcp_runtime_adapter` / `studio.mcp_tool_runtime`. |
| Passwords shim | No `passwords/` folder exists; only historical/migration references remain. |
| Server sharing | Capability fields exist for connect, execute, read files, and write files; view-only negative tests cover terminal, files, Linux UI, reveal-secret, and share administration. |
| Shell safety | `app/tools/safety.py` now normalizes common shell obfuscations and detects chained dangerous commands, pipe-to-shell, command/process substitution, quoted executables, `bash -c` encoded payloads, and inline base64 exec. |
| Execution policy audit | `app.execution_policy` now builds shared redacted policy metadata for `PermissionEngine`, direct SSH/server tools, MCP argument log previews, and Studio graph policy decisions saved into pipeline run summaries. |
| Egress redaction | Canonical helpers live in `app.egress_redaction`; pipeline text/context/output redaction is centralized in `studio/pipeline_redaction.py`. AI WebSocket events, `UserActivityLog` description/metadata, agent tool-argument previews, MCP argument logs, pipeline webhook payload/header/output previews, provider API error bodies, MCP HTTP errors, terminal/multi-agent parse snippets, and `ops/http_check` excerpts pass through redaction before leaving runtime boundaries. |
| Pipeline executor | `studio/pipeline_executor.py` is now a thin run lifecycle wrapper and registry dispatch point under the standard architecture limit. Executable node handlers are registered in `studio/executor/nodes/`; 26 node types are currently in the registry. Shared notification helpers live in `studio/pipeline_notifications.py`, Telegram polling/reply routing lives in `studio/pipeline_telegram.py`, interactive approval/input helpers live in `studio/pipeline_interactions.py`, pipeline redaction helpers live in `studio/pipeline_redaction.py`, routing helpers live in `studio/pipeline_routing.py`, context helpers live in `studio/pipeline_context.py`, run-state/event helpers live in `studio/pipeline_run_state.py`, run setup helpers live in `studio/pipeline_run_setup.py`, run loop/finalization helpers live in `studio/pipeline_run_loop.py`, direct MCP agent helpers live in `studio/pipeline_agent_mcp.py`, direct LLM agent helpers live in `studio/pipeline_agent_llm.py`, server-backed agent runtime helpers live in `studio/pipeline_agent_runtime.py`, output compatibility helpers live in `studio/pipeline_outputs.py`, and simple logic helpers live in `studio/pipeline_logic.py`. |
| Studio templates | Built-in pipeline templates are grouped under `studio/pipeline_templates/`; `studio/templates_data.py` remains the compatibility export for `PIPELINE_TEMPLATES`. |
| MARS worker | `mars/worker.py` owns the orchestration flow; CLI command prefixing, process streaming, Codex/Gemini phases, verification, stop checks, and save helpers live in `mars/worker_phases.py`. |
| Production worker topology | `docker-compose.production.yml` now defines dedicated `scheduled-pipelines`, `scheduled-agents`, `monitor`, and `ops-supervisor` services; `telegram-bot` is profile-only. `render.yaml` includes Redis Key Value plus starter worker services for the same background features. |
| Test config | `pyproject.toml` points pytest to `web_ui.settings.test`, which isolates tests on SQLite and in-memory services. |

## Findings

### P0: Execution Policy Is Still Cross-Cutting

SSH commands, MCP calls, file writes, outbound webhooks, pipeline execution, terminal AI, and server agents all represent potentially mutating operations. Shared audit metadata now exists for runtime tool decisions and Studio graph decisions, but Studio graph validation and runtime tool permission decisions are still separate gate layers.

Impact: gate behavior can still diverge between runtime paths even though audit evidence now uses the same shape.

Recommended fix: continue converging Studio graph guardrails and runtime tool permission decisions onto one contract and make bypass tests cover every mutating node/tool family.

### P1: Secret Redaction Needs More Egress Coverage

Canonical egress redaction now exists, pipeline output nodes share `studio/pipeline_redaction.py`, and activity records/AI events/MCP argument logs/pipeline webhook payloads/provider error bodies/ops HTTP excerpts use redaction, but remaining report/logger sinks should keep being audited as new runtime paths are added.

Impact: operational logs and reports can become a leakage path even when prompts are sanitized.

Recommended fix: keep replacing ad hoc redaction at new pipeline/MCP/report/logger output points and add targeted tests with token/password/private-key/high-entropy samples.

### P1: Legacy-Large Files Remain

The repository still carries large pinned files such as `frontend/src/pages/PipelineEditorPage.tsx`, `frontend/src/lib/api.ts`, `servers/consumers/ssh_terminal.py`, and others in `pyproject.toml`.

Impact: changes are harder to review and regression risk remains high.

Recommended fix: continue one-domain-at-a-time extraction, and remove baseline entries once files fall below the standard limit.

## Completed Since Older Audits

- Architecture guard is green again: `python scripts/check_architecture_sizes.py --strict-new` passes.
- `servers.mcp_tool_runtime` shim removed.
- `passwords/` package removed.
- Backend view monolith split is largely done.
- Server sharing is capability-based; view-only shares cannot execute commands, open terminal, read/write files, use Linux UI actions, reveal saved secrets, or administer shares.
- Server access is SSH-only: no secondary GUI transport, templates, server type choice, share capability, or memory policy remains in active code.
- Shell safety detection covers the listed audit cases for chained commands, shell pipes/substitution, quoted executables, `bash -c`, and encoded script execution.
- Pipeline execution dispatches registered node handlers through `studio/executor/nodes/`; output, logic, agent, and ops node handlers are no longer separate branches in `_execute_node`.
- Shared notification defaults, recipient normalization, sender resolution, Telegram target resolution, and Telegram send helpers are centralized in `studio/pipeline_notifications.py`; legacy import names are preserved for pipeline executor and node modules.
- Telegram approval polling and operator-reply routing are centralized in `studio/pipeline_telegram.py`; legacy import names remain available from `studio.pipeline_executor`.
- `app.egress_redaction` is the shared redaction module for runtime egress; activity log description/metadata and outbound AI events use it.
- `studio/pipeline_redaction.py` centralizes pipeline text, context, and node-output redaction for executor compatibility paths plus output email/report/webhook/Telegram node modules.
- `studio/pipeline_routing.py` centralizes graph construction, route queue release, routing port calculation, routing-state serialization, reachability, and merge-source helpers used by the run orchestrator.
- `studio/pipeline_context.py` centralizes template rendering, enriched node context, pipeline actor context, role/permission normalization, compact output context, and pipeline tool/ops prompt helpers.
- `studio/pipeline_run_state.py` centralizes pipeline run event callbacks, node-state persistence, routing-state persistence, run status persistence, activity logging, and Channels notifications.
- `studio/pipeline_run_setup.py` centralizes run context normalization, graph validation, entry trigger checks, execution-policy summary capture, and initial run snapshot persistence.
- `studio/pipeline_run_loop.py` centralizes batch execution, route continuation, abort/stop handling, and final run status updates.
- `studio/pipeline_agent_mcp.py` centralizes direct MCP agent execution, MCP argument coercion, skill policy application, permission/sandbox checks, and MCP result formatting.
- `studio/pipeline_agent_llm.py` centralizes direct LLM agent query execution, provider/model resolution, server memory loading, operational recipe context, and streaming callbacks.
- `studio/pipeline_agent_runtime.py` centralizes server-backed `agent/react`, `agent/multi`, and `agent/ssh_cmd` execution, including SSH command logging and server-agent runtime calls.
- `studio/pipeline_outputs.py` centralizes compatibility helpers for email, report, webhook, and Telegram output execution.
- `studio/pipeline_logic.py` centralizes simple `logic/condition`, `logic/wait`, and `logic/merge` compatibility helpers used by registry nodes and legacy import aliases.
- `studio/pipeline_interactions.py` centralizes `logic/human_approval`, `logic/telegram_input`, and Telegram target resolution used by registry nodes and legacy import aliases.
- `studio/pipeline_executor.py` is below the standard architecture limit and was removed from legacy size baselines.
- `servers/adapters/django_memory_store.py` is below the standard architecture limit and was removed from legacy size baselines; snapshot, dream, manual-knowledge, and snapshot-action delegates live in `servers/adapters/django_memory_store_mixins.py`.
- `servers/monitor.py` is below the standard architecture limit and was removed from legacy size baselines; pure monitor output parsers live in `servers/monitor_parsing.py`.
- `studio/templates_data.py` is below the standard architecture limit and was removed from legacy size baselines; grouped built-in pipeline templates live under `studio/pipeline_templates/`.
- Below-limit compatibility shims and frontend pages no longer carry stale legacy size baselines: `app/agent_kernel/memory/store.py`, `core_ui/views/_views_all.py`, `studio/views/_views_all.py`, `frontend/src/pages/MCPHubPage.tsx`, `frontend/src/pages/MarsPage.tsx`, and `frontend/src/pages/PipelineRunsPage.tsx`.
- `servers/linux_ui.py` is below the standard architecture limit and was removed from legacy size baselines; command constants, pure parsers/validators, SSH runtime/capabilities, and resource snapshots live in focused `servers/linux_ui_*` modules.
- `servers/consumers/ssh_terminal.py` has started shrinking; marker filtering, exit-future resolution, bounded sanitized output buffers, manual command state, Nova/session context helpers, report/memory/policy compatibility helpers, and terminal-input aliases now delegate to focused services.
- `frontend/src/lib/api.ts` has started shrinking; Linux UI, SFTP/server-file, MARS, server-memory, monitoring/admin dashboard, and agents/runs/schedules API calls/types live under `frontend/src/api/`, with compatibility re-export from the legacy API module.
- `frontend/src/components/terminal/LinuxUiPanel.tsx` is below the standard architecture limit; overview, processes, workspace chrome/apps, services, logs, disk, network, Docker, package-manager UI, and shared summary cards live under `frontend/src/components/terminal/linux-ui/`, and the old desktop/window-shell interaction model is no longer present in the active Linux UI panel.
- `frontend/src/pages/PipelineEditorPage.tsx` has started shrinking; palette, assistant panel, run monitor, run dialog, flow summary bar, presentation helpers, graph helpers, cron helpers, JSON schema helpers, trigger config sections, `NodeConfigPanel`, and node-config sections live under `frontend/src/pages/pipeline-editor/`.
- `frontend/src/pages/Servers.tsx` has started shrinking; page-local types, playbook helpers and panel, server list tab, memory snapshot helpers, server form helpers, rules/env helpers, group dialog, and formatters live under `frontend/src/pages/servers/`.
- `frontend/src/pages/SettingsPage.tsx` is below the standard architecture limit; settings constants, provider selector, section card, AI settings form/panels, memory settings panel, memory card leaf components, access navigation, logging controls, activity log table, and memory overview panels live under `frontend/src/pages/settings-page/`.
- `studio/services/pipeline_template_recommendations.py` is below the standard architecture limit; recommendation data, placeholder handling, argument binding, and text helpers live in focused `studio/services/pipeline_template_*` modules.
- `studio/executor/nodes/ops.py` is below the standard architecture limit and no longer pinned; pure ops command/argument helpers, context helpers, action helpers, alert-update helpers, and HTTP-check execution helpers live in focused `studio/executor/nodes/ops_*` modules.
- `servers/multi_agent_engine.py` has started shrinking; task construction, plan/decision parsing, and task-table report helpers live in `servers/multi_agent_plan_helpers.py`.
- Studio graph policy decisions now include `audit_metadata` generated by `app.execution_policy.build_execution_policy_audit_metadata`; pipeline run `trigger_data.execution_policy.items[*]` carries that shared evidence shape.
- Provider error-body logs, MCP HTTP errors, Terminal AI parse-failure snippets, multi-agent plan parse snippets, Telegram polling error bodies, and `ops/http_check` response excerpts are redacted before logging or pipeline output persistence.
- `web_ui.settings` is a compatibility shim; explicit settings modules exist.
- Frontend app is clearly under `frontend/`.
- `frontend/src/pages/MarsPage.tsx` has been split into a controller plus `frontend/src/pages/mars/` step/sidebar/utils modules so the MARS route no longer grows as one legacy-large page.
- `mars/worker.py` has been split so process streaming and Codex/Gemini/verification phase helpers live in `mars/worker_phases.py`.
- MARS interview and worker CLI subprocess execution now has Windows-safe fallback coverage for Selector event loops.
- Test settings isolate DB/email/Celery/channel layer.
- `.dockerignore` and `.gitignore` cover key generated and secret-prone paths.
- Production worker topology is explicit in compose/Render: HTTP, Redis/Channels, scheduled pipelines, scheduled agents, monitor, watchers, memory dreams, and agent execution plane have named processes.

## Recommended Next Order

1. Add shared execution policy/audit/redaction contract.
2. Normalize egress redaction across logs/activity/pipeline/MCP.
3. Continue frontend API/page decomposition.
