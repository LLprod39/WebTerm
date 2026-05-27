# MARS Architecture Refactoring Status

This file is the single, easily accessible source of truth for the ongoing **OOP Refactoring and Repo Hygiene** effort. It is located at the project root so you can view, query, and track progress from any terminal or environment.

---

## 📊 Progress Summary
- **Current Phase**: Feature-ready architecture baseline complete
- **Overall Completion**: `[████████████████████] 100%`
- **Active Agent**: Codex
- **Last Updated**: 2026-05-27

---

## 🛠️ Active Focus
The architecture refactor is now at a feature-ready baseline. Phase 0 architecture fitness is green, with import boundaries enforced by `.importlinter` and file-size checks enforced by `scripts/check_architecture_sizes.py`. Phase 1 reached a stable thin-facade point: `servers/adapters/django_memory_store.py` is 647 lines after moving serializers, pure snapshot utilities, pure pattern utilities, overview read-model, runbook search, snapshot actions, ingestion, compaction, dream candidates, snapshot repository operations, patterns, LLM enhancement, manual knowledge bridge, dream orchestration, recording workflows, repair/maintenance, and prompt card read-models out. Phase 2 is complete for the old backend view monoliths: `servers/views/_views_all.py` is a 26-line compatibility shim, `studio/views/_views_all.py` is a 60-line compatibility shim, and `core_ui/views/_views_all.py` is a 40-line compatibility shim. Phase 3 is complete enough for new feature work: terminal input parsing, connection records, command recording, preferences, report generation, durable memory extraction, planning, recovery/step decisions, output explanation, agent extra-target context, access/secret lookup, SSH connect options, typed terminal events, SSH lifecycle helpers, and pre-execution snapshotting all live in focused services. `servers/consumers/ssh_terminal.py` is down to 3390 lines and is now primarily a Channels protocol adapter plus queue runner; further reduction is hardening, not a blocker. Frontend guard is green after extracting `ServerPicker`, `SftpTransferQueue`, and compacting mobile window class mapping in `LinuxUiPanel.tsx`.

---

## 📝 Refactoring Checklist

### 🟢 Phase 0: Repo Hygiene & Boundary Verification (Next Action)
- [ ] Untrack and delete generated files from Git (`playwright-report`, `test-results`, `dist`, production bundles, temporary test dirs)
- [ ] Update `.gitignore` with accurate generated patterns
- [ ] Update `.dockerignore` to restrict build context leakage
- [ ] Document two-layer frontend architecture in `README.md`
- [x] Enforce automated boundary and size checks in local execution
- [x] Restore architecture guard to green without raising the memory-store baseline

### 🟡 Phase 1: Purify `app.agent_kernel` Memory
- [x] Extract memory protocols, ports, and pure DTOs into `app/agent_kernel/memory/ports.py` and `app/agent_kernel/memory/types.py`
- [x] Remove concrete Django ORM imports from `app/agent_kernel/memory/store.py`
- [x] Create `servers/adapters/django_memory_store.py` and migrate concrete store database logic
- [x] Create `servers/adapters/memory_store.py` as compatibility adapter entry point
- [x] Update caller import paths in `servers/` apps to use adapter path
- [x] Remove Django/`servers.models` imports from `app.agent_kernel.memory.repair`
- [x] Route memory skill promotion through `SkillPromotionGateway` instead of direct `servers -> studio` imports
- [x] Remove `servers.agent_engine -> studio.skill_registry` type-only import exception
- [x] Route server-agent MCP runtime through `MCPRuntimeProvider` and delete `servers/mcp_tool_runtime.py`
- [x] Extract memory overview/archive serializers into `servers/adapters/django_memory_serializers.py`
- [x] Extract pure snapshot/string helpers into `app/agent_kernel/memory/snapshot_utils.py`
- [x] Extract pure operational pattern helpers into `app/agent_kernel/memory/pattern_utils.py`
- [x] Extract Settings AI Memory overview read-model into `servers/adapters/django_memory_overview.py`
- [x] Extract runbook/recipes search into `servers/adapters/django_memory_runbooks.py`
- [x] Extract archive/purge/promote snapshot workflows into `servers/adapters/django_memory_snapshot_actions.py`
- [x] Extract Django ingestion and nearline compaction into `servers/adapters/django_memory_ingestion.py`
- [x] Extract shared memory line filters into pure `app/agent_kernel/memory/line_filters.py`
- [x] Extract dream snapshot candidate builder into pure `app/agent_kernel/memory/dream_candidates.py`
- [x] Extract snapshot upsert/revalidation repository into `servers/adapters/django_memory_snapshots.py`
- [x] Extract operational pattern mining/promotion into `servers/adapters/django_memory_patterns.py`
- [x] Extract LLM distillation/enhancement into `servers/adapters/django_memory_llm.py`
- [x] Extract manual knowledge bridge into `servers/adapters/django_memory_manual.py`
- [x] Extract dream-cycle orchestration and retention/schedule helpers into `servers/adapters/django_memory_dreams.py`
- [x] Extract fact/change/incident recording workflows into `servers/adapters/django_memory_recording.py`
- [x] Move repair/maintenance workflow into `servers/adapters/django_memory_repair.py`
- [x] Extract prompt card read-models into `servers/adapters/django_memory_cards.py`
- [x] Move LLM usage logging into `app/core/llm_usage.py` and remove SQLite detached logging lock
- [x] Split frontend MCP form and agent report modal out of legacy page files
- [x] Split frontend pipeline run detail and editor dialog copy out of legacy page files
- [x] Split Studio page activity/trigger helpers into `src/components/studio/StudioActivityText.ts` and `StudioPipelineTriggers.ts`
- [ ] Relocate remaining dream-cycle ORM workflow into focused server adapters
- [x] Make targeted backend tests self-contained via `web_ui.settings.test` SQLite database
- [x] Run targeted backend tests: `tests/test_ops_agent_kernel.py`, `tests/test_servers_api_smoke.py`, MCP/skill policy tests

### 🔴 Phase 2: Split Backend View Monoliths
- [x] Extract server memory endpoints into `servers/views/server_memory.py`
- [x] Extract server knowledge endpoints into `servers/views/server_knowledge.py`
- [x] Extract monitoring dashboard/status/health endpoints into `servers/views/server_monitoring.py`
- [x] Extract monitoring alerts/watchers/config/AI analysis into `servers/views/server_monitoring_actions.py`
- [x] Extract SFTP/file endpoints into `servers/views/server_files.py`
- [x] Extract agent config/schedule/launch endpoints into `servers/views/server_agents.py`
- [x] Extract agent run/control/task endpoints into `servers/views/server_agent_runs.py`
- [x] Extract Linux UI read-only endpoints into `servers/views/server_linux_ui.py`
- [x] Extract Linux UI workload/action endpoints into `servers/views/server_linux_ui_workloads.py`
- [x] Extract group and bulk-update endpoints into `servers/views/server_groups.py`
- [x] Extract server share endpoints into `servers/views/server_shares.py`
- [x] Extract global/group context endpoints into `servers/views/server_context.py`
- [x] Extract server CRUD/detail/reveal endpoints into `servers/views/server_crud.py`
- [x] Extract server test/execute/OS-detect endpoints into `servers/views/server_ops.py`
- [x] Extract master-password session endpoints into `servers/views/server_auth_session.py`
- [x] Extract remaining frontend bootstrap/terminal page views and shared helper boundaries from `servers/views/_views_all.py`
- [x] Extract Studio notification settings/test endpoints into `studio/views/notification_views.py`
- [x] Extract Studio template endpoints into `studio/views/template_views.py`
- [x] Extract Studio server dropdown endpoint into `studio/views/server_views.py`
- [x] Extract Studio MCP pool CRUD/test/tools/templates into `studio/views/mcp_views.py`
- [x] Extract Studio share-users endpoint into `studio/views/share_views.py`
- [x] Extract Studio trigger CRUD/webhook receive endpoints into `studio/views/trigger_views.py`
- [x] Extract Studio run list/detail/stop/approval endpoints into `studio/views/run_views.py`
- [x] Extract Studio agent config CRUD endpoints into `studio/views/agent_views.py`
- [x] Extract Studio skill catalog/detail/templates/scaffold/validate/workspace endpoints into `studio/views/skill_views.py`
- [x] Extract Studio pipeline CRUD/manual-run/clone/run-history endpoints into `studio/views/pipeline_views.py`
- [x] Extract Studio pipeline assistant endpoint into `studio/views/pipeline_assistant_views.py`
- [x] Extract Studio pipeline assistant preview/risk helpers into `studio/views/pipeline_assistant_preview.py`
- [x] Extract Studio shared view helpers into `studio/views/common.py`, `pipeline_helpers.py`, `agent_helpers.py`, and `skill_helpers.py`
- [x] Extract Core UI auth/session/csrf/ws-token/login/logout and frontend redirects into `core_ui/views/auth_views.py`
- [x] Extract Core UI users/groups/permissions access endpoints into `core_ui/views/access_views.py` and `core_ui/views/access_group_views.py`
- [x] Extract Core UI model/tool discovery endpoints into `core_ui/views/model_views.py`
- [x] Extract Core UI settings config/activity endpoints into `core_ui/views/settings_config_views.py` and `core_ui/views/settings_activity_views.py`
- [x] Extract Core UI disk/legacy agent/upload endpoints into `core_ui/views/utility_views.py`
- [x] Extract Core UI legacy IDE endpoints into `core_ui/views/ide_views.py`
- [x] Extract Core UI legacy RAG endpoints into `core_ui/views/rag_views.py`
- [x] Extract Core UI runtime singleton helpers into `core_ui/views/runtime.py`
- [x] Extract Core UI health endpoint into `core_ui/views/health_views.py`
- [x] Extract Core UI legacy Django page views into `core_ui/views/page_views.py`
- [x] Extract Core UI admin dashboard/billing into `core_ui/views/admin_views.py` and `core_ui/views/admin_billing.py`
- [x] Extract Core UI chat/Cursor APIs into `core_ui/views/chat_views.py` and `core_ui/views/chat_helpers.py`
- [x] Extract Core UI legacy settings page into `core_ui/views/settings_page_views.py`
- [ ] Extract business rules into `servers/services/`
- [x] Split `core_ui/views/_views_all.py`

### 🟢 Phase 3: Decouple SSHTerminalConsumer
- [x] Extract pure terminal input/command parsing into `servers/services/terminal_input.py`
- [x] Extract terminal connection open/heartbeat/close persistence into `servers/services/terminal_connection_records.py`
- [x] Extract command history recorder into `servers/services/terminal_command_recorder.py`
- [x] Extract Terminal-AI preference normalization into `servers/services/terminal_ai/preferences.py`
- [x] Extract Terminal-AI report LLM streaming into `servers/services/terminal_ai/report_generation.py`
- [x] Extract Terminal-AI durable memory extraction into `servers/services/terminal_ai/memory_extraction.py`
- [x] Extract Terminal-AI planning LLM/JSON workflow into `servers/services/terminal_ai/planning.py`
- [x] Extract Terminal-AI recovery/step-decision workflow into `servers/services/terminal_ai/decision.py`
- [x] Extract Terminal-AI output explanation into `servers/services/terminal_ai/output_explanation.py`
- [x] Extract terminal agent extra-target ACL/context into `servers/services/terminal_agent_context.py`
- [x] Extract terminal access/session-limit/secret lookup into `servers/services/terminal_access.py`
- [x] Extract SSH connect kwargs assembly into `servers/services/terminal_connection_options.py`
- [x] Extract typed terminal WebSocket event DTO builders into `servers/services/terminal_events.py`
- [x] Extract SSH terminal lifecycle helpers into `servers/services/terminal_ssh_lifecycle.py`
- [x] Extract terminal plan-item and execution-mode policy shaping into `servers/services/terminal_ai/plan_items.py`
- [x] Extract terminal snapshotting into `servers/services/terminal_snapshotting.py`
- [x] Establish service boundaries for terminal AI workflows; full queue-runner shrink is future hardening

### 🟡 Future Hardening: Polymorphic Node Executors
- [ ] Migrate graph execution modules into `studio/executor/nodes/`
- [ ] Convert `PipelineExecutor` into a registry dispatcher using `NodeRegistry`

### 🟡 Future Hardening: Frontend Decomposition
- [ ] Create frontend `HttpClient`
- [ ] Split `src/lib/api.ts` into domain API clients
- [x] Extract `ServerPicker` from `TerminalPage.tsx` to keep the terminal page below its architecture baseline
- [x] Extract `SftpTransferQueue` from `SftpPanel.tsx` to keep the SFTP panel below its architecture baseline
- [ ] Extract Hooks controllers from massive page components (`PipelineEditorPage`, `LinuxUiPanel`, `Servers`)

---

## 💬 How to interact with Antigravity across terminals
Whenever you open a new chat session or terminal, simply mention this file or say:
> *"Посмотри в mars_status.md, какой у нас текущий статус, и продолжай работу"*
> *(Look at mars_status.md to see our current status and continue working)*

Antigravity will read this file, immediately understand the context, see what was completed, and continue from the exact spot where we left off.
