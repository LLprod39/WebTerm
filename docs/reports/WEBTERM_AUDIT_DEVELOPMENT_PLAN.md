# WebTerm Audit Development Plan

Last reviewed: 2026-06-15

This roadmap turns the current audit into implementation-sized work. It is intentionally shorter than the old report: completed cleanup is recorded, and open work is ordered by risk.

## Current Status

| Area | Status |
| --- | --- |
| Import boundaries | Green on 2026-05-27. |
| Architecture size guard | Green on 2026-06-15. |
| Backend view split | Mostly complete; compatibility shims remain. |
| MCP runtime shim | Complete; `servers.mcp_tool_runtime` no longer exists. |
| `passwords/` compatibility package | Complete; folder no longer exists. |
| Pipeline node registry | Complete for current executable node handlers; 26 registered node types dispatch through `studio/executor/nodes/`. |
| Frontend decomposition | In progress; domain API modules exist, MARS page is split into controller/sections/sidebar/utils, Linux UI, SFTP/server-file, MARS, server-memory, monitoring/admin dashboard, and agents/runs/schedules API calls/types live under `frontend/src/api/`, Pipeline Editor slices live under `frontend/src/pages/pipeline-editor/`, Servers page helpers live under `frontend/src/pages/servers/`, Settings page helpers live under `frontend/src/pages/settings-page/`, Linux UI overview/process/workspace/apps/services/logs/disk/network/docker/package components live under `frontend/src/components/terminal/linux-ui/`, and other legacy-large files remain. |
| Retired stale size baselines | Complete for current below-limit files. Memory compatibility exports, `_views_all.py` shims, `MCPHubPage`, `MarsPage`, and `PipelineRunsPage` no longer have legacy baseline entries. |
| Linux UI service split | Complete for current architecture guard. Shell command constants, pure parsers/validators, SSH runtime/capabilities, and resource snapshots live in focused `servers/linux_ui_*` modules; `servers/linux_ui.py` is now the public facade. |
| SSH terminal stream state split | In progress. Marker filtering, AI exit-future resolution, bounded sanitized output buffers, manual command state, Nova/session context, report/memory/policy helpers, and compatibility aliases delegate to focused services; `servers/consumers/ssh_terminal.py` remains pinned but reduced to 3189 lines. |
| MARS worker decomposition | Complete for current size guard. `mars/worker.py` owns orchestration flow; CLI phase/process helpers live in `mars/worker_phases.py`. |
| MARS subprocess compatibility | Complete for current Windows runtime. Interview capture and worker streaming have fallbacks when the active event loop cannot create async subprocess transports. |
| Shared server permission matrix | Complete for current SSH endpoints; negative tests cover terminal, command, file, Linux UI, reveal-secret, and share-admin denial. |
| Shell safety parser | Current audit cases covered; keep extending catalogue as new evasions are found. |
| Egress redaction | In progress. Canonical helpers cover AI WebSocket events, activity log description/metadata, MCP/tool previews, provider error bodies, parse-failure snippets, pipeline text/context/output payloads, webhooks, reports, and selected ops excerpts. |
| Security policy unification | In progress. Runtime tool decisions and Studio graph decisions now share audit metadata; gate enforcement is still layered. |
| Pipeline notification helpers | Complete. Shared email/Telegram config/defaults and send helpers live in `studio/pipeline_notifications.py`. |
| Pipeline Telegram polling | Complete. Approval callback polling and operator reply routing live in `studio/pipeline_telegram.py`. |
| Pipeline redaction helpers | Complete. Pipeline text/context/node-output redaction lives in `studio/pipeline_redaction.py`. |
| Pipeline routing helpers | Complete. Graph construction, route queue release, routing port calculation, routing-state serialization, reachability, and merge-source helpers live in `studio/pipeline_routing.py`. |
| Pipeline context helpers | Complete. Template rendering, enriched node context, actor context, role/permission normalization, compact output context, and pipeline tool/ops prompt helpers live in `studio/pipeline_context.py`. |
| Pipeline run-state helpers | Complete. Run/node/routing state persistence and pipeline run WebSocket event callbacks live in `studio/pipeline_run_state.py`. |
| Pipeline run setup helpers | Complete. Context normalization, graph validation, entry trigger checks, execution-policy summary capture, and initial run snapshot persistence live in `studio/pipeline_run_setup.py`. |
| Pipeline run loop helpers | Complete. Batch execution, routing continuation, abort/stop handling, and final run status updates live in `studio/pipeline_run_loop.py`. |
| Pipeline MCP agent helper | Complete. Direct `agent/mcp_call` execution, argument coercion, skill policy application, permission/sandbox checks, and MCP result formatting live in `studio/pipeline_agent_mcp.py`. |
| Pipeline LLM agent helper | Complete. Direct `agent/llm_query` execution, provider/model resolution, server memory loading, operational recipe context, and streaming callbacks live in `studio/pipeline_agent_llm.py`. |
| Pipeline server agent runtime | Complete. `agent/react`, `agent/multi`, and `agent/ssh_cmd` execution helpers live in `studio/pipeline_agent_runtime.py`; `pipeline_executor.py` keeps compatibility aliases. |
| Pipeline output helpers | Complete. Compatibility helpers for email, report, webhook, and Telegram output execution live in `studio/pipeline_outputs.py`. |
| Pipeline simple logic helpers | Complete. `logic/condition`, `logic/wait`, and `logic/merge` compatibility helpers live in `studio/pipeline_logic.py`. |
| Pipeline interaction helpers | Complete. `logic/human_approval`, `logic/telegram_input`, and Telegram target resolution live in `studio/pipeline_interactions.py`. |
| Pipeline executor orchestration | Complete for current architecture guard. `studio/pipeline_executor.py` is under the standard size limit and no longer has a legacy baseline entry. |
| Server memory store facade | Complete for current architecture guard. Snapshot, dream, manual-knowledge, and snapshot-action delegates live in `servers/adapters/django_memory_store_mixins.py`; `servers/adapters/django_memory_store.py` is under the standard size limit and no longer has a legacy baseline entry. |
| Server monitor parsing | Complete for current architecture guard. Pure monitor output parsers live in `servers/monitor_parsing.py`; `servers/monitor.py` is under the standard size limit and no longer has a legacy baseline entry. |
| Studio template data split | Complete for current architecture guard. `studio/templates_data.py` preserves the public `PIPELINE_TEMPLATES` export while grouped templates live in `studio/pipeline_templates/`. |
| Production worker topology | Complete for current compose/Render configs. |

## Phase 1: Security And Safety

### A1. Shared Server Permission Matrix

Status: complete for current server endpoints.

Goal: replace broad shared-server access with capability checks.

Capabilities:

- `view`
- `connect_terminal`
- `execute_command`
- `read_files`
- `write_files`
- `view_context`
- `admin_share`

Done when:

- Shared view-only user cannot execute, write files, reveal secrets, or administer shares.
- Owner behavior is unchanged.
- Regression tests cover negative cases.

Evidence:

- `tests/test_server_share_capabilities.py`
- `tests/test_terminal_access_service.py`

### A2. Unified Execution Policy Gate

Goal: one policy/audit decision for SSH, MCP, file writes, webhooks, pipeline nodes, terminal AI, and server agents.

Decision fields:

- actor/user
- operation kind
- target
- redacted preview
- risk categories
- policy mode
- approval requirement
- audit evidence payload

Done when:

- Pipeline nodes and terminal/server tools use the same decision shape.
- Tests prove direct nodes cannot bypass the gate.

Current evidence:

- `app.execution_policy.build_execution_policy_audit_metadata` is the shared audit metadata builder.
- `PermissionEngine`, direct SSH/server tools, and Studio graph policy decisions now emit that metadata shape.
- `PipelineRun.trigger_data.execution_policy.items[*].audit_metadata` preserves redacted Studio graph evidence for runtime audit.

### A3. Shell Safety Parser Upgrade

Status: complete for the listed required cases.

Goal: improve `app/tools/safety.py` beyond regex-only detection.

Required cases:

- chained commands
- pipes to shell
- command substitution
- quoted executable names
- `bash -c`
- encoded script execution

Done when:

- Existing safe commands still pass.
- Obfuscated dangerous commands are detected.

Evidence:

- `tests/test_command_safety.py`

### A4. Versioned Credential Encryption

Goal: introduce versioned encrypted payloads without breaking old secrets.

Done when:

- Legacy payloads decrypt.
- New payloads store version/kdf metadata.
- Rotation command reports counts without printing values.

### A5. Egress Redaction

Status: in progress.

Goal: apply redaction before logs, activity records, pipeline excerpts, MCP args, reports, memory, and prompt context.

Done when:

- Unit tests prove token/password/private-key/high-entropy samples are redacted at all egress points.

Current evidence:

- `app.egress_redaction` owns the canonical helper.
- `studio/pipeline_redaction.py` owns pipeline text/context/node-output redaction used by executor compatibility code and output node modules.
- `servers/services/egress_redaction.py` applies it to AI WebSocket events.
- `core_ui/activity.py` applies it to `UserActivityLog.description` and `metadata`.
- Provider API error bodies, MCP HTTP errors, terminal/multi-agent parse-failure snippets, Telegram polling error bodies, pipeline webhook output, report output, and `ops/http_check` excerpts are redacted before logging or persistence.
- `tests/test_egress_redaction.py`, `tests/test_memory_redaction.py`, and `tests/test_core_ui_api_smoke.py::test_log_user_activity_redacts_description_and_metadata_secrets` cover this slice.

## Phase 2: Architecture And Legacy Cleanup

### B1. Shrink Pipeline Executor Orchestration

Current:

- `studio/executor/registry.py`, `BaseNode`, and concrete node handlers exist.
- `PipelineExecutor._execute_node` dispatches registered node types through the registry.
- Shared notification helpers have been extracted to `studio/pipeline_notifications.py`.
- Telegram polling/reply routing has been extracted to `studio/pipeline_telegram.py`.
- Pipeline redaction helpers have been extracted to `studio/pipeline_redaction.py`.
- Routing helpers, graph construction, and route queue release have been extracted to `studio/pipeline_routing.py`.
- Context helpers have been extracted to `studio/pipeline_context.py`.
- Run-state persistence and run event callbacks have been extracted to `studio/pipeline_run_state.py`.
- Run setup and validation helpers have been extracted to `studio/pipeline_run_setup.py`.
- Run loop and finalization helpers have been extracted to `studio/pipeline_run_loop.py`.
- Direct MCP agent execution helpers have been extracted to `studio/pipeline_agent_mcp.py`.
- Direct LLM agent query helpers have been extracted to `studio/pipeline_agent_llm.py`.
- Server-backed agent execution helpers have been extracted to `studio/pipeline_agent_runtime.py`.
- Output compatibility helpers have been extracted to `studio/pipeline_outputs.py`.
- Simple logic compatibility helpers have been extracted to `studio/pipeline_logic.py`.
- Interactive approval/input helpers have been extracted to `studio/pipeline_interactions.py`.
- `studio/pipeline_executor.py` is below the standard architecture limit and has been removed from the legacy baseline.

Next:

1. Keep node handlers inside `studio/executor/nodes/`.
2. Continue shrinking remaining legacy-large frontend, terminal, and API files.

Done when:

- `studio/pipeline_executor.py` stays below the standard architecture limit without moving node-specific behavior back into the orchestrator.

### B2. Continue Frontend API And Controller Split

Current:

- `frontend/src/api/auth.ts`, `servers.ts`, `settings.ts`, `studio.ts`, and `agents.ts` exist.
- `frontend/src/pages/MarsPage.tsx` is now a controller page; large MARS wizard UI sections live under `frontend/src/pages/mars/`.
- `frontend/src/pages/PipelineEditorPage.tsx` is reduced to 1289 lines; extracted helpers/components, run dialog, flow summary bar, trigger config sections, `NodeConfigPanel`, and focused node-config sections live under `frontend/src/pages/pipeline-editor/`.
- `frontend/src/pages/Servers.tsx` is reduced to 2336 lines; extracted helpers, playbook panel, server list tab, and the server group dialog live under `frontend/src/pages/servers/`.
- `frontend/src/pages/SettingsPage.tsx` is reduced to 425 lines and removed from legacy baselines; extracted constants, AI settings form/panels, memory settings panel, leaf components, access navigation, logging controls, activity log table, and memory overview panels live under `frontend/src/pages/settings-page/`.
- `frontend/src/components/terminal/LinuxUiPanel.tsx` is reduced to 431 lines and removed from legacy baselines; overview, processes, workspace chrome/apps, services, logs, disk, network, Docker, package-manager UI, and shared summary cards live under `frontend/src/components/terminal/linux-ui/`, and the inactive desktop/window-shell model has been removed from the active panel.
- `frontend/src/lib/api.ts` is reduced to 2580 lines; SFTP/server-file, MARS, server-memory, monitoring/admin dashboard, and agents/runs/schedules API calls/types now live in focused `frontend/src/api/` modules with compatibility re-export from the legacy module.

Next:

1. Finish moving auth/server/studio API callers to domain modules.
2. Extract controller hooks from large pages only when behavior is covered.
3. Keep UI redesign out of pure decomposition tasks.

Done when:

- Large pinned frontend files shrink without changing behavior.

### B3. Reduce Legacy-Large Backend Files

Targets:

- `servers/consumers/ssh_terminal.py`
- `servers/multi_agent_engine.py`
- `servers/models.py`

Done when:

- Files shrink below pinned baselines.
- Baseline entries are removed once below the standard limit.

## Phase 3: Operations And Deployment

### C1. Worker Topology

Status: complete for the current deployment files.

Document and configure:

- backend HTTP
- Redis channel layer
- scheduled pipelines
- scheduled agents
- server monitor
- watchers
- memory dreams
- agent execution plane

Done when:

- Production compose/Render docs do not imply background features run inside the HTTP process unless that is explicitly true.

Evidence:

- `docker-compose.production.yml` defines dedicated `scheduled-pipelines`, `scheduled-agents`, `monitor`, and `ops-supervisor` services; `telegram-bot` is profile-only.
- `render.yaml` defines Redis Key Value plus starter worker services for scheduled pipelines, scheduled agents, monitor, and ops-supervisor.

### C2. Time-Series Metrics

Start with operational metrics:

- CPU
- RAM
- disk
- network/load
- service status
- container health

Then add AI-memory health metrics:

- event count
- episode count
- dream duration
- compaction failures
- revalidation queue size

Done when:

- UI can render useful 1h/24h/7d operational history.

## Phase 4: Product Expansion

### D1. Kubernetes Read-Only First

Do not start with free-form `kubectl apply/delete`.

MVP:

- attach cluster
- list namespaces/workloads/pods/services/ingress
- logs/events/describe
- AI read-only diagnosis

Mutations come later through plan, dry-run, approval, apply, verify.

### D2. GitOps / PR-Based Remediation

Default for non-incident changes:

- create branch
- patch file
- run configured checks
- create PR/MR
- attach verification and rollback note

Direct SSH writes remain for incident/break-glass workflows.

### D3. CI/CD Visibility

Read-only first:

- GitHub Actions / GitLab pipeline status
- failed job summary
- relevant log excerpts
- Studio run context integration

## Recommended Work Order

1. Unified execution policy.
2. Egress redaction.
3. Versioned encryption.
4. Frontend decomposition.
5. Worker/deploy topology.
6. Metrics.
8. Kubernetes read-only.
9. GitOps remediation.
10. CI/CD visibility.

## Definition Of Done

- Architecture guard is green.
- Dangerous operations share one policy/audit/redaction contract.
- Shared server access is capability-based.
- Large files shrink over time instead of growing baselines by default.
- Production docs explain which worker process owns each background feature.
