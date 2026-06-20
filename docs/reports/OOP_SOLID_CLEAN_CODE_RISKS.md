# OOP / SOLID / Clean Code Risk Report

Last reviewed: 2026-06-21

This report captures architecture and maintainability risks found in the current worktree. It is not a bug list. The current architecture guard passes, but several areas can still create problems as the project grows, especially when adding plugins, providers, pipeline nodes, terminal AI behavior, or new frontend workflows.

## Evidence Checked

- `python scripts\check_architecture_sizes.py --strict-new` passes: import boundaries and size guard are green.
- `.importlinter` has no `ignore_imports` entries; all declared import-boundary contracts are exception-free.
- `[tool.architecture.legacy_baselines]` still pins 13 large files in `pyproject.toml`.
- The guard prevents legacy files from growing above their pins; below-limit files should be removed from this table only after `python scripts\check_architecture_sizes.py --strict-new` proves they pass without the pin.
- Largest current files include:
  - `servers/consumers/ssh_terminal.py` - 2426 lines.
  - `servers/multi_agent_engine.py` - 1322 lines.
  - `key_mcp.py` - 1304 lines.
  - `servers/models.py` - 1301 lines.
  - `tests/test_ops_agent_kernel.py` - 1293 lines.
  - `tests/test_servers_api_smoke.py` - 1188 lines.
  - `mars/services.py` - 1169 lines.
  - `studio/keycloak_provisioning.py` - 1167 lines.
  - `studio/services/pipeline_assistant.py` - 1070 lines.
  - `tests/test_studio_node_executors.py` - 962 lines.
  - `servers/agent_engine.py` - 961 lines.
  - `tests/test_studio_api_smoke.py` - 891 lines.
  - `tests/test_studio_pipeline_v2.py` - 879 lines.
  - `studio/docker_service_recovery.py` - 858 lines.
  - `studio/demo_showcase.py` - 840 lines.
- `frontend/src/pages/AgentRunPage.tsx` is now 430 lines and removed from legacy baselines; pipeline, flow-node, report, timeline, status badge, task-edit modal, formatter, and page-local type modules live under `frontend/src/pages/agent-run/`.
- `frontend/src/pages/AgentsPage.tsx` is now 291 lines and removed from legacy baselines; the create/edit wizard dialog lives in `frontend/src/pages/agents-page/CreateAgentDialog.tsx`.
- `frontend/src/pages/AgentConfigPage.tsx` is now 455 lines and removed from legacy baselines; core settings plus access/integration/visibility form sections live in `frontend/src/pages/agent-config/AgentFormAccessSections.tsx`.
- `frontend/src/pages/SettingsUsersPage.tsx` is now 160 lines and removed from legacy baselines; access-user form types, permission payload helpers, shared permission controls, the user directory, and the create-user sidebar live under `frontend/src/pages/settings-users/`.
- `frontend/src/pages/settings/SettingsAuditPage.tsx` is now 177 lines and removed from legacy baselines; audit logging constants, logging settings rendering, and activity-log filtering/table rendering live under `frontend/src/pages/settings-audit/`.
- `frontend/src/pages/settings/SettingsMemoryPage.tsx` is now 162 lines and removed from legacy baselines; memory panel layout, overview sections, snapshot cards/actions, and worker-state cards live under `frontend/src/pages/settings-memory/`.
- `frontend/src/pages/AdminDashboard.tsx` is now 78 lines and removed from legacy baselines; admin dashboard widget definitions live under `frontend/src/pages/admin-dashboard/`.
- `frontend/src/components/dashboard/CustomizableDashboard.tsx` is now 215 lines and removed from legacy baselines; dashboard widget definitions/types, curated layout presets, visible-widget derivation, widget library rendering, edit help, controls, grid rendering, settings panel, and resize/drag frame rendering live under focused `frontend/src/components/dashboard/` modules.
- `frontend/src/components/terminal/SftpPanel.tsx` is now 421 lines and removed from legacy baselines; SFTP path/permission/entry helpers, text-editor rendering, text-editor state/load/save behavior, transfer queue orchestration, and formatting helpers live under focused `frontend/src/components/terminal/sftp-panel/` modules.
- `frontend/src/components/terminal/LinuxUiSystemSettings.tsx` is now 220 lines and removed from legacy baselines; Linux UI settings parsing/search/copy helpers, shared output primitives, search-result rendering, and section rendering live under focused `frontend/src/components/terminal/linux-ui-settings/` modules.
- `frontend/src/components/terminal/LinuxUiTextEditor.tsx` is now 79 lines and removed from legacy baselines; text-editor tab/recent-file/language-hint model helpers, open/save/reload controller state, and layout rendering live under focused `frontend/src/components/terminal/linux-ui-text-editor/` modules.
- `frontend/src/components/ui/sidebar.tsx` is now a 29-line compatibility barrel and removed from legacy baselines; provider/context, layout primitives, group primitives, and menu primitives live under focused `frontend/src/components/ui/sidebar/` modules.
- `frontend/src/pages/Servers.test.tsx` is now 201 lines and removed from legacy baselines; shared render helpers, fixtures, and API mock setup live in `frontend/src/pages/servers/serversPageTestHarness.tsx`.
- `frontend/src/pages/PipelineEditorPage.test.tsx` is now 312 lines and removed from legacy baselines; pipeline editor test fixtures, render helpers, and default API mock setup live in `frontend/src/pages/pipeline-editor/pipelineEditorPageTestHarness.tsx`.
- `app/test_studio_pipeline_assistant_api.py` is now 369 lines and removed from legacy baselines; template/interview/discard assistant draft scenarios live in `app/test_studio_pipeline_assistant_api_templates.py`.
- `studio/views/pipeline_draft_views.py` is now 250 lines and removed from legacy baselines; draft queryset/revision/validation/template helpers live in `studio/views/pipeline_draft_helpers.py`.
- `studio/demo_mcp_server.py` is now 175 lines and removed from legacy baselines; demo MCP tool catalog, handlers, and workspace filesystem helpers live in `studio/demo_mcp_tools.py`.
- `studio/pipeline_validation.py` is now 245 lines and removed from legacy baselines; ORM-backed node reference validation for server, MCP, agent config, skill, cron, and node option checks lives in `studio/pipeline_validation_references.py`.
- `studio/node_manifest.py` is now 347 lines and removed from legacy baselines; shared manifest types/builders live in `studio/node_manifest_common.py`, and Ops node manifest definitions live in `studio/node_manifest_ops.py`.
- `studio/all_nodes_smoke.py` is now 97 lines and removed from legacy baselines; smoke entry/collector nodes and edges live in `studio/all_nodes_smoke_flow.py`, while branch/probe nodes and branch target ids live in `studio/all_nodes_smoke_branches.py`.
- `web_ui/settings/base.py` is now 206 lines and removed from legacy baselines; security/origin settings, channel/database settings, auth/LDAP settings, runtime/LLM/MARS/CLI settings, Celery settings, and env parsing helpers live in focused `web_ui/settings/` modules.
- `scripts/check_architecture_sizes.py` is now a 78-line CLI facade and removed from legacy baselines; architecture guard config/models, size validation, project scanning, import-boundary checks, baseline writing, and report formatting live in focused `scripts/architecture_guard_*.py` modules.
- `studio/demo_showcase.py` is now a 131-line facade and removed from legacy baselines; incident/content/detective showcase graph definitions live in focused `studio/demo_showcase_*.py` modules, and the incident demo graph now uses an explicit merge for rejected/timeout approval branches.
- `studio/models.py` is now 496 lines and removed from legacy baselines; Django model classes stay in the original module for ORM/migration stability, while model serialization, pipeline trigger sync, template instantiation, and monitoring-filter normalization live in focused helper/service modules.
- `studio/docker_service_recovery.py` is now an 89-line facade and removed from legacy baselines; shell command builders, recovery graph assembly, pre-approval nodes, and recovery-loop nodes live in focused `studio/docker_service_recovery_*.py` modules.
- `frontend/src/components/pipeline/nodes/nodeMeta.tsx` is now 191 lines and removed from legacy baselines; node guidance metadata and shared metadata types live in focused `nodeGuidanceMeta.ts` and `nodeMetaTypes.ts` modules.
- `servers/services/terminal_ai/prompts.py` is now 469 lines and removed from legacy baselines; prompt sanitisation lives in `servers/services/terminal_ai/prompt_safety.py`, while report, output-explanation, and memory-extraction prompt builders live in `servers/services/terminal_ai/prompt_reporting.py`.
- `frontend/src/pages/StudioDraftsPage.tsx` is now 374 lines and removed from legacy baselines; draft payload helpers, queue rendering, graph wrapper, composer, review actions, and mobile tabs live under `frontend/src/pages/studio-drafts/`.
- `frontend/src/pages/StudioPage.tsx` is now 410 lines and removed from legacy baselines; pipeline cards, create dialog, manual-trigger dialog, trigger-info dialog, and delete dialog live under `frontend/src/pages/studio-page/`.
- `frontend/src/pages/TerminalPage.tsx` is now 482 lines and removed from legacy baselines; tab/session model helpers, WebSocket/AI event projection, AI action handlers, query state, header, and terminal workspace rendering live under `frontend/src/pages/terminal-page/`.
- `frontend/src/components/terminal/XTerminal.tsx` is now 480 lines and removed from legacy baselines; default xterm theme/font helpers live in `frontend/src/components/terminal/xterminalConfig.ts`, and file-drop overlay handling lives in `frontend/src/components/terminal/XTerminalDropZone.tsx`.
- `tests/test_agent_loop.py` is now 465 lines and removed from legacy baselines; Terminal Agent system-prompt contract coverage lives in `tests/test_agent_system_prompt.py`.
- `frontend/src/pages/PipelineEditorPage.tsx` is now 488 lines and removed from legacy baselines; run-dialog state/preparation, toolbar/activity bar, canvas, main-area layout, side-panel rendering, trigger/run-mode derivation, save/run/dry-run mutations, run-dialog host wiring, live run graph overlay, graph display-state derivation, graph editing actions, and assistant draft orchestration now live under `frontend/src/pages/pipeline-editor/`.
- `frontend/src/pages/settings/SettingsAIPage.tsx` is now 76 lines and removed from legacy baselines; the standalone AI settings route reuses `AiSettingsPanel` and `useAiSettingsForm`, so AI provider/model/key behavior has one frontend extension point.
- `frontend/src/components/terminal/AiPanel.tsx` is now 380 lines and removed from legacy baselines; AI message rendering, Nova/agent timeline rendering, and settings-dialog rendering live under `frontend/src/components/terminal/ai-panel/`.

## Findings

### 1. Partially Mitigated: Legacy Baselines Can Hide Future SRP Regressions

Evidence:

- `pyproject.toml:89` starts the legacy baseline list.
- Many files are still allowed to exceed the standard size limit, including terminal, API, frontend pages, tests, model config, and agent engines.
- Baselines were lowered or removed during this review, so the guard will catch growth in the remaining pinned files and no longer accepts already-small files as legacy exceptions.
- `docs/architecture/README.md` says large legacy files are pinned and should not grow.

SOLID / Clean Code impact:

- Single Responsibility Principle risk: large files often mix orchestration, state, rendering, persistence, and integration logic.
- Open/Closed Principle risk: new behavior is likely to be added to existing large files instead of new extension points.
- Clean Code risk: reviewers may treat a green guard as "done" even when the design still has large compatibility centers.

Future problem:

- The project can pass guard while still being hard to extend. New plugin or provider work may land in already-large files because those files remain accepted compatibility surfaces.

Recommended direction:

- Keep lowering baselines after every split.
- Add a short owner comment for each remaining baseline: why it exists, what owns the next extraction, and what condition removes it.

### 2. Partially Mitigated: SSH Terminal Consumer Is Still a Large Stateful Object

Evidence:

- `servers/consumers/ssh_terminal.py:81` defines `SSHTerminalConsumer`.
- `servers/consumers/ssh_terminal.py:98-119` declares many `_ai_*` state fields.
- `servers/services/terminal_ai/session.py:96` now stores per-request forbidden command patterns alongside the plan queue and run context.
- `servers/services/terminal_ai/session.py:179` now owns initial plan installation, including cursor reset, next-id tracking, and forbidden-pattern request state.
- `servers/services/terminal_ai/session.py:255-433` now owns parallel-batch snapshot/cursor advancement, next-command preparation, current-command completion, explicit plan-index completion, remaining-command skip, and stop transitions for queued commands.
- `servers/services/terminal_ai/legacy_state.py:10-47` owns transitional sync helpers between legacy consumer `_ai_*` request-state fields and `TerminalAiSession`.
- `servers/services/terminal_ai/plan_insertions.py:11-43` now owns retry/adaptive plan-item reservation helpers, including retry-count registration and adaptive-step limit accounting.
- `servers/services/terminal_ai/run_controller.py:9-72` now owns the asyncio lock, active AI task, user-reply futures, and shared ask-user send/wait/cleanup flow.
- `servers/services/terminal_ai/active_command.py:12-68` now owns active PTY command id, exit-future lookup/resolution/cancel cleanup, bounded active-output capture, tail projection, and active-command clear behavior.
- `servers/services/terminal_ai/pty_command.py:29-143` now owns PTY marker-future waiting, streaming timeout fallback, install-progress monitoring, install-error interrupt callbacks, task cleanup, and active-output tail return for interactive Terminal AI commands.
- `servers/services/terminal_ai/recovery.py:10-433` now owns recovery retry limits, recovery-action normalization, retry-candidate projection, recovery question/abort text defaults, retry-candidate insertion, fast-mode error-recovery orchestration, and step-mode post-command orchestration through consumer-compatible owner hooks.
- `servers/services/terminal_ai/queue_completion.py:22-94` now owns final done-item snapshotting, auto-report generation, report status emission, dry-run report labeling, execution-history summary writes, memory candidate projection, and memory-extraction task spawning.
- `servers/services/terminal_events.py:44-145` now owns common Terminal AI WebSocket event builders for status, error, response, command status, parallel-batch status, install progress, direct output, reports, recovery, and questions.
- `servers/services/terminal_direct_execution.py:16-57` now owns non-PTY direct command execution: SSH channel run, timeout-to-124 mapping, stdout/stderr merging, output truncation, null-exit fallback, and direct-output event emission.
- `servers/services/terminal_parallel_batch.py:20-96` now owns parallel direct-command batch execution: batch start/done events, per-item running/done events, dry-run direct-output previews, pre-execution snapshots, concurrent direct execution, command-history writes, unavailable-command recording, and explicit plan-index completion callbacks.
- `servers/services/terminal_manual_input.py:15-177` now owns manual terminal input capture orchestration: capture-buffer updates, editor intercept cancellation/event payloads, single-command marker injection, immediate persistence for commands that cannot be marker-wrapped, manual command activity logging, and pending-command queue bookkeeping.
- `servers/services/terminal_agent_context.py:158-207` now owns authorised terminal-agent extra-target connection setup: ACL lookup, master-password fallback, secret resolution, connect-kwargs construction, `asyncssh.connect`, and best-effort failure handling.
- `servers/services/terminal_manual_command_state.py:14-15` now routes Terminal AI output capture through the active-command helper instead of mutating `_ai_active_*` fields directly.
- `servers/consumers/ssh_terminal.py:592-602` now delegates manual terminal input handling to `servers.services.terminal_manual_input`.
- `servers/consumers/ssh_terminal.py:701-719` now delegates `ai_stop` pending-skip selection to `TerminalAiSession`.
- `servers/consumers/ssh_terminal.py:721-734` now uses `TerminalAiSession.clear()` for cancel-path queue/request-state reset.
- `servers/consumers/ssh_terminal.py:761-799` now uses `TerminalAiSession.reset_for_new_request()` when starting a new AI turn.
- `servers/consumers/ssh_terminal.py` now delegates AI task start/cancel, active-task checks, current-task cleanup, `ai_reply` future resolution, and repeated `ai_question` wait/cleanup handling to `TerminalAiRunController`.
- `servers/consumers/ssh_terminal.py` now delegates active PTY command registration, exit-future lifecycle, interrupt lookup, active-output tail reads, and clear/cancel cleanup to `servers.services.terminal_ai.active_command`.
- `servers/consumers/ssh_terminal.py` now delegates PTY command completion waiting, install-progress event emission, install-error interrupts, streaming timeout fallback, and cleanup of command helper tasks to `servers.services.terminal_ai.pty_command`.
- `servers/consumers/ssh_terminal.py` now delegates recovery-attempt gating, recovery-action normalization, retry-command validation, recovery text defaults, retry-item insertion/event emission, user-question retry follow-up, abort event emission, fast-mode recovery exception handling, adaptive step insertion, step-mode goal completion, and step-mode post-command exception handling to `servers.services.terminal_ai.recovery`.
- `servers/consumers/ssh_terminal.py` now delegates queue cursor mutation for blocked/confirm/running/done/goal-achieved transitions to `TerminalAiSession`.
- `servers/consumers/ssh_terminal.py` now delegates per-run id allocation and retry/adaptive queue insertion positions to `TerminalAiSession`.
- `servers/consumers/ssh_terminal.py` now delegates retry/adaptive plan-item reservations to `servers.services.terminal_ai.plan_insertions`.
- `servers/consumers/ssh_terminal.py` now delegates recovery remaining-command projections and report/memory done-item projections to `TerminalAiSession`.
- `servers/consumers/ssh_terminal.py` now delegates initial plan installation to `TerminalAiSession.load_plan()`.
- `servers/consumers/ssh_terminal.py` now delegates dry-run report labeling and command execution summary formatting to `servers.services.terminal_ai.reporter`.
- `servers/consumers/ssh_terminal.py` now delegates post-queue report/history/memory side effects to `servers.services.terminal_ai.queue_completion`.
- `servers/consumers/ssh_terminal.py` now delegates exit-127 unavailable-command extraction to `servers.services.terminal_ai.command_outcome`.
- `servers/consumers/ssh_terminal.py` now delegates parallel-batch selection and cursor advancement to `TerminalAiSession`.
- `servers/consumers/ssh_terminal.py` now delegates parallel-batch plan item completion to `TerminalAiSession.mark_plan_index_done()`, which rejects negative indices instead of relying on Python list indexing.
- `servers/consumers/ssh_terminal.py:1613-1645` now keeps a compatibility `_execute_parallel_batch` method that delegates batch execution behavior to `servers.services.terminal_parallel_batch`.
- `servers/consumers/ssh_terminal.py` now constructs standard Terminal AI status, error, response, and direct-output events through `servers.services.terminal_events` instead of ad-hoc dictionaries.
- `servers/consumers/ssh_terminal.py:1039-1093` now delegates `ai_confirm` and `ai_cancel` queue mutations to `TerminalAiSession`.
- `servers/consumers/ssh_terminal.py:1973-1986` now keeps only a compatibility `_open_agent_target_conn` delegate for agent extra-target SSH connection setup.
- `servers/consumers/ssh_terminal.py:327-379` routes many WebSocket message types.
- `servers/consumers/ssh_terminal.py:761`, `1317`, `1571`, and `1763` show AI request handling, queue execution, direct command compatibility delegation, and agent mode in the same class.
- `tests/test_terminal_ai_session_queue.py` covers per-run id allocation, retry/adaptive insertion positions, next-command preparation, completion, skip-remaining transitions, remaining-command projections, and done-item projections.
- `tests/test_terminal_ai_session.py` covers confirm/cancel/stop current-command state transitions, request reset, cancel clear, and the session lifecycle.
- `tests/test_terminal_ai_legacy_state.py` covers legacy consumer attribute sync/apply behavior separately from the session state-machine tests.
- `tests/test_terminal_ai_reporter_memory.py` covers report status, fallback reports, dry-run report labeling, execution summary formatting, and memory helper behavior.
- `tests/test_terminal_ai_command_outcome.py` covers unavailable-command extraction for command-not-found outcomes.
- `tests/test_terminal_ai_run_controller.py` covers task start/cancel/current-task cleanup, reply-future lifecycle, and ask-user timeout cleanup.
- `tests/test_terminal_ai_active_command.py` covers active-command initialization, registration, future resolution/pop/cancel cleanup, bounded output capture, tail projection, and guarded clear behavior.
- `tests/test_terminal_ai_pty_command.py` covers PTY marker-future completion cleanup, active-output tail return, install-progress last-line events, and install-error interrupt callbacks.
- `tests/test_terminal_ai_recovery.py` covers recovery gating, action normalization, retry candidate projection, retry-item insertion/event emission, recovery text defaults, fast-mode retry/ask/abort/no-op orchestration, step-mode retry/next/done/abort orchestration, and the `_no_recovery=True` retry-item regression.
- `tests/test_terminal_ai_queue_completion.py` covers auto-report event emission, history writes, memory-extraction task spawning, no-op behavior without a user message, and disabled report/memory settings.
- `tests/test_terminal_ai_plan_insertions.py` covers retry/adaptive item reservation, retry-count registration, and adaptive-step limit handling.
- `tests/test_terminal_events.py` covers the shared Terminal AI event builders, including parallel-batch payloads.
- `tests/test_terminal_manual_input.py:71-121` covers manual input marker injection, immediate no-marker persistence for unfinished shell syntax, and editor command intercept behavior.
- `tests/test_ssh_terminal_manual_input_compat.py:60-89` keeps the consumer compatibility path covered for manual terminal marker injection, output persistence, and multiline no-marker fallback.
- `tests/test_terminal_direct_execution.py:30-94` covers service-level direct execution event emission, timeout mapping, and empty-command short-circuit behavior.
- `tests/test_terminal_parallel_batch.py:41-121` covers service-level parallel batch execution, dry-run remote-execution bypass, per-item plan-index completion, and unavailable-command recording.
- `tests/test_exec_direct.py:72-177` keeps the consumer compatibility delegate covered for stdout/stderr handling, non-zero exits, timeouts, no-connection errors, truncation, null exit status, and PTY isolation.

SOLID / Clean Code impact:

- SRP risk remains: one class still coordinates WebSocket protocol, SSH lifecycle, terminal input/output, AI planning, command execution, recovery, reporting, memory, audit, and redaction.
- Queue cursor mutation, initial plan installation, parallel-batch selection/cursor advancement/item completion, parallel direct-command batch execution, retry/adaptive insertion positioning and reservation, retry gating/candidate projection/insertion, fast-mode recovery orchestration, step-mode post-command orchestration, per-run id allocation, remaining-command/done-item projections, post-queue report/history/memory side effects, report formatting, command-outcome classification, common event payload construction, non-PTY direct command execution, manual input capture/marker/persistence behavior, confirm/cancel/stop queue-state mutation, per-request forbidden patterns, new-request/cancel request-state reset, active AI task lifecycle, user reply futures, ask-user send/wait/cleanup flow, active PTY command future/output-tail state, PTY marker waiting, and install-progress monitoring are now isolated and unit-testable without a WebSocket consumer harness.
- Interface Segregation risk: small features depend on a huge consumer surface instead of narrow ports.
- Testability risk: async state transitions are hard to test without building a full consumer/SSH context.

Future problem:

- Adding new terminal AI modes, approvals, or plugin-controlled terminal tools can create subtle regressions in lock handling, event order, cancellation, and memory/report side effects.

Recommended direction:

- Continue expanding Terminal AI services so command execution and retry orchestration move out of `SSHTerminalConsumer` behind narrow callbacks.
- Keep `SSHTerminalConsumer` focused on WebSocket transport and SSH stream plumbing.
- Add state-machine tests around cancel/stop/confirm/retry/ask-user flows before deeper extraction.

### 3. Mitigated: Servers Page Is Below The Size Limit, But Still Coordinates Workflows

Evidence:

- `frontend/src/pages/Servers.tsx:48` defines the page component.
- `frontend/src/pages/Servers.tsx:49-217` still contains page-level tab state, advanced-dialog state, route data, controller construction, and open/close orchestration.
- `frontend/src/pages/servers/useServerCrudController.ts:25-145` now owns server create/edit/delete/test dialog state, form state, private-key file reading, save/delete/test mutations, and sudo-password requirement derivation.
- `frontend/src/pages/servers/useServerGroupController.ts:17-97` now owns server-group dialog state, group form state, save/delete mutations, and reset behavior.
- `frontend/src/pages/servers/ServerFormDialog.tsx:35-270` now owns the server create/edit dialog rendering.
- `frontend/src/pages/servers/useServersListController.ts:1-53` now owns server search, filtered/grouped list state, collapsed groups, selected server tracking, and online count.
- `frontend/src/pages/servers/useServerSharesController.ts:12-62` now owns advanced-dialog share list/form state, share loading, create, refresh, and revoke operations.
- `frontend/src/pages/servers/ServerAccessTab.tsx:32-202` now owns advanced access-tab rendering.
- `frontend/src/pages/servers/useServerKnowledgeController.ts:27-406` now owns manual/AI knowledge list state, filters, dialog state, category fallback, load/refresh, manual CRUD, AI snapshot edit/delete, bulk delete, and purge operations.
- `frontend/src/pages/servers/ServerKnowledgeTab.tsx:46-321` now owns advanced knowledge-tab rendering.
- `frontend/src/pages/servers/ServerKnowledgeDialogs.tsx:22-194` now owns manual/AI knowledge edit dialogs and receives the knowledge controller as one dependency.
- `frontend/src/pages/servers/useServerRulesController.ts:43-427` now owns global/group/server rules state, JSON parsing, effective previews, advanced-dialog context loading, server override saves, and group-member add/remove operations.
- `frontend/src/pages/servers/ServerRulesTab.tsx:23-286` now owns main rules-tab rendering for global/group rules and previews and receives the rules controller as one dependency.
- `frontend/src/pages/servers/ServerAdvancedDialog.tsx:46-284` now owns the advanced-dialog shell, sidebar navigation, and advanced tab composition; it receives share/knowledge/rules/security/command controllers instead of dozens of individual props.
- `frontend/src/pages/servers/ServerContextTab.tsx:26-128` now owns advanced context-tab rendering.
- `frontend/src/pages/servers/useServerSecurityController.ts:13-65` now owns master-password status, save, clear, reveal, and advanced-open reset behavior.
- `frontend/src/pages/servers/useServerCommandController.ts:10-39` now owns advanced execute-tab command state and command execution result formatting.
- `frontend/src/pages/servers/ServerSecurityTab.tsx:16-72` and `frontend/src/pages/servers/ServerExecuteTab.tsx:14-46` now own those advanced-tab render sections.
- `frontend/src/pages/Servers.tsx:183-199` still coordinates advanced-dialog multi-resource loading, but delegates share, knowledge, rules, security, and command state to their controllers.
- `frontend/src/pages/Servers.tsx:250-390` contains the route render composition tree and dialog wiring.

SOLID / Clean Code impact:

- SRP risk is substantially reduced: the page is now below the standard size limit and mostly composes route data, controllers, and child views.
- The server/group CRUD workflows, server form dialog, basic server-list controller state, advanced dialog shell, advanced share/access workflow, manual/AI knowledge workflow state/rendering/dialogs, main rules-tab rendering, rules/context workflow, group-member workflow, security workflow, and execute workflow are now isolated behind focused controllers/components.
- Clean Code risk: new UI tabs are likely to add more state and handlers directly to the page.
- Dependency inversion risk is reduced for page workflows that now call concrete API functions behind focused controllers; remaining route wiring passes controller objects instead of long prop lists.

Future problem:

- Adding server plugins, new advanced tabs, or new route-level workflows can still make the page harder to reason about unless new workflows continue to land behind controllers/components first.

Recommended direction:

- Keep `Servers.tsx` below the standard size limit and remove it from legacy baselines.
- Keep future workflow additions behind focused hooks or child components first.
- Keep the route component as composition only: load route data, choose tabs, pass controller objects to child components.

### 4. Partially Mitigated: LLM Provider Layer Still Has Provider-Specific Branching

Evidence:

- `app/core/provider_adapters.py:14-234` now owns provider metadata, API-key aliases, CLI binary policy, provider-specific status details for FAIR/Ollama, and the explicit default fallback order.
- `app/core/provider_registry.py:16-178` now composes provider adapters for enabled/configured checks, provider payloads, detailed status, and default fallback instead of owning those provider conditionals directly.
- `app/core/llm_provider_resolution.py:7-85` now owns auto provider resolution for `LLMProvider.stream_chat`, including key-vs-enabled behavior and runtime fallback order.
- `app/core/model_catalog.py:57-151` now owns provider model-selection metadata: chat model field, agent-model fallback chain, available-model cache attribute, default model list, and config enabled field.
- `app/core/llm.py:207-216` delegates auto provider/model selection to `resolve_stream_provider`.
- `app/core/model_config.py:38-119` stores provider-specific config fields in one model.
- `app/core/model_refresh.py:18-291` now owns provider model-list refresh for Gemini, Grok, Claude, OpenAI, FAIR.Hyperion, and Ollama local/cloud catalogs.
- `app/core/model_config.py:244-260` keeps the public `ModelManager.fetch_available_*` API as thin delegating methods.
- `app/core/model_config.py:262-441` now delegates default model lists, chat/agent model selection, available-model cache lookup, and enabled checks to the provider model catalog instead of keeping local provider branches.
- `app/core/model_config.py` is now below the standard architecture size limit and no longer needs a legacy baseline.
- `ModelConfig` purpose-specific provider/model defaults are empty strings again, matching the documented inheritance contract: empty purpose overrides inherit `internal_llm_provider` and that provider's chat/agent model.
- `app/core/llm_openai_compatible.py:30-282` now owns OpenAI-compatible request construction, SSE parsing for Responses/Completions/Chat Completions, retry/backoff, HTTP error handling, timeout/error messages, `trust_env` session policy, and usage logging for OpenAI-compatible providers.
- `app/core/llm.py:261-299`, `328-367`, and `369-407` now keep Grok/FAIR/OpenAI provider guards, key checks, model selection, and request wiring but delegate the shared streaming loop to `stream_openai_compatible_response`.
- `app/core/llm_anthropic.py:17-101` now owns Claude request construction, Anthropic prompt-cache `cache_control`, stream timeout/retry behavior, timeout/error messages, and usage logging.
- `app/core/llm.py:301-326` now keeps only Claude provider guards, key lookup, model selection, and delegation to `stream_claude_response`.
- `app/core/llm_gemini.py:17-119` now owns Gemini request construction, `system_instruction`, JSON-mode `response_mime_type`, stream consumption, timeout/retry behavior, timeout/error messages, and usage logging.
- `app/core/llm.py:233-259` now keeps only Gemini provider guards, key lookup, model selection, and delegation to `stream_gemini_response`.
- `app/core/llm_ollama.py:21-284` now owns Ollama target construction, local/cloud request payload construction, stream JSON-line parsing, WSL/local base-URL fallback, retry/timeout/error behavior, local base-URL persistence callback, and usage logging.
- `app/core/llm.py:409-445` now keeps only Ollama provider guards, model selection, runtime-target validation, and delegation to `stream_ollama_response`.
- `app/core/llm.py` is now below the standard architecture size limit and no longer needs a legacy baseline.
- `tests/test_provider_adapters.py:1-49` covers adapter key aliases, status details, CLI binary policy, and fallback order.
- `tests/test_llm_provider_resolution.py:1-89` covers preferred-key behavior, fallback behavior, and explicit provider pass-through.
- `tests/test_model_purpose_routing.py` covers terminal-purpose inheritance, explicit purpose overrides, provider model selection, Claude agent-model inheritance, Ollama configured/available fallback chain, available-model cache lookup, and unknown CLI provider enabled compatibility.
- `tests/test_llm_openai_compatible.py` covers OpenAI Responses request construction, JSON-mode hinting, retry behavior, `trust_env` propagation, SSE parsing, and usage logging for the shared OpenAI-compatible stream helper.
- `tests/test_llm_anthropic.py:83-190` covers Claude payload construction, system prompt cache-control wiring, successful stream usage logging, retry behavior, and timeout status logging.
- `tests/test_llm_gemini.py:73-171` covers Gemini payload construction, system instruction, JSON-mode config, successful stream usage logging, retry behavior, and timeout status logging.
- `tests/test_llm_ollama.py:110-280` covers Ollama cloud target construction, JSON/think payload construction, HTTP retry behavior, successful usage logging, and fallback to the next local base URL.
- `tests/test_model_refresh.py:20-96` covers Gemini model-list pagination/filtering and OpenAI text-model filtering in the extracted refresh module.

SOLID / Clean Code impact:

- OCP risk is reduced for provider status, runtime auto-routing, model selection, model-list refresh, OpenAI-compatible streaming, Claude streaming, Gemini streaming, and Ollama streaming: provider metadata, availability policy, default/available model lookup, chat/agent model field selection, provider catalog refresh, shared SSE/retry/session-policy behavior, Anthropic stream behavior, Gemini stream behavior, and Ollama local/cloud stream behavior now have focused seams.
- OCP risk remains because `LLMProvider.stream_chat` still owns provider guard/key/model-selection wiring instead of being fully table/adapter-driven.
- DIP risk: high-level runtime code depends on concrete provider behavior and global `model_manager`.
- Clean Code risk is lower in registry/status/model-selection/model-refresh/provider-streaming code, but provider-specific edge cases can still accumulate inside central provider wiring.

Future problem:

- Adding plugins for custom providers or enterprise providers is less risky for status/default routing, model selection, catalog refresh, OpenAI-compatible execution, Anthropic-style streaming, Gemini-style streaming, and Ollama-style local/cloud streaming, but still expensive until providers have first-class registration.

Recommended direction:

- Extend the provider adapter/catalog split toward methods like `list_models` and provider-specific `stream_chat`.
- Move provider-specific behavior into `app/core/providers/<provider>.py`.
- Continue moving the remaining provider guard/key/model-selection wiring into provider adapters. `ProviderRegistry` is now composition over adapters and should stay that way.

### 5. Fixed: Frontend API Facade No Longer Owns Studio API Groups

Evidence:

- `frontend/src/lib/api.ts:6-17` re-exports domain API modules and feature metadata.
- `frontend/src/lib/api.ts:153` owns shared `apiFetch`.
- `frontend/src/lib/api.ts` is below the standard size limit and no longer appears in `[tool.architecture.legacy_baselines]`.
- Studio API runtime functions now live in `frontend/src/api/studio.ts`.
- Studio API DTOs and public TypeScript contracts now live in `frontend/src/api/studio-types.ts`.
- Demo/offline fallback routing and payloads now live in focused `frontend/src/lib/api-demo-*.ts` modules.
- `frontend/src/lib/api.ts` keeps compatibility exports but no longer defines the concrete `studioPipelines`, `studioRuns`, `studioAgents`, `studioSkills`, `studioMCP`, capabilities, node manifests, share users, triggers, templates, or Studio server dropdown API groups.

SOLID / Clean Code impact:

- This closes the concrete SRP/OCP issue for Studio frontend API groups.
- Residual risk remains for any future feature that adds new concrete API groups back into `frontend/src/lib/api.ts` instead of the matching domain module.

Future problem:

- If the compatibility facade starts growing concrete domain APIs again, plugin/pipeline features can regress into the old central-file pattern.

Recommended direction:

- Keep `frontend/src/lib/api.ts` as transport plus compatibility re-export only.
- Keep new demo/offline payloads in the matching `api-demo-*.ts` module instead of growing `api.ts`.
- Move call sites from `@/lib/api` to `@/api` or direct domain imports when touching those files.

### 6. Fixed: Import Boundaries Are Exception-Free

Evidence:

- `.importlinter:25-35` now keeps Contract 2 (`app.core` must not import `servers`, `studio`, or `core_ui`) without legacy exceptions.
- `.importlinter:38-62` now keeps Contract 3 and Contract 4 (`app.tools` must not import feature apps or `app.agent_kernel`) without legacy exceptions.
- `.importlinter:64-74` now keeps Contract 5 (`core_ui` must not import `servers` or `studio`) without legacy exceptions.
- `.importlinter:77-86` now keeps Contract 6 (`servers` must not import `studio`) without legacy exceptions.
- `.importlinter:89-96` now keeps Contract 7 (`studio` must not import `servers`) without legacy exceptions.
- `app/command_history_provider.py:6-42` owns generic command-history recording for pipeline SSH command history.
- `app/core/llm_budget.py:12-50` owns generic LLM budget status, error, and provider registration.
- `app/core/llm_usage_sink.py:9-47` owns generic LLM usage event and recorder registration.
- `app/agent_tool_catalog.py:6-20` owns generic agent-tool catalog provider registration for Studio skill validation.
- `app/monitoring_events.py:6` owns the shared server-alert-opened signal used between server monitoring and Studio triggers.
- `app/pipeline_agent_provider.py:8-40` owns generic pipeline agent-runner provider registration and the cross-domain `AgentRunSnapshot` DTO.
- `app/pipeline_memory_provider.py:6-49` owns generic pipeline memory provider registration.
- `app/pipeline_ssh_provider.py:6-34` owns generic pipeline SSH connection/sudo provider registration.
- `app/runtime_limits.py:24-246` owns generic runtime-limit provider protocols, settings lookup, error shape, and compatibility facade functions.
- `app/server_alert_provider.py:8-44` owns generic server-alert snapshot lookup for Studio monitoring triggers.
- `app/studio_server_access.py:6-132` owns generic Studio server-access provider registration and compatibility facade functions.
- `app/tools/activity_provider.py:13-31` owns generic tool audit/activity provider registration.
- `app/tools/server_secret_provider.py:12-44` owns generic server auth/sudo secret provider registration.
- `app/tools/server_tool_gateway.py:29-62` owns generic server-tool gateway registration for list/get/share/history/knowledge operations.
- `app/tools/ssh_host_key_provider.py:15-64` owns generic SSH host-key provider registration for `ssh_tools`.
- `app/chat_server_provider.py:17-38` owns generic chat server-context provider registration.
- `app/admin_metrics_provider.py:6-58` owns generic admin-dashboard server metrics registration.
- `app/smoke_seed_provider.py:8-60` owns generic smoke-seed server/pipeline registration.
- `servers/chat_server_provider.py:14-128` implements chat server context and safe server command routing in the server domain.
- `servers/admin_metrics_provider.py:8-73` implements admin dashboard server metrics in the server domain.
- `servers/agent_tool_catalog_provider.py:6-8` exposes server agent tool names through the app-level catalog provider.
- `servers/command_history_provider.py:6-22` persists command history through the app-level command-history provider.
- `servers/pipeline_agent_provider.py:8-14` exposes server agent engines through the app-level pipeline agent provider.
- `servers/pipeline_memory_provider.py:8-25` exposes server memory cards and recipes through the app-level pipeline memory provider.
- `servers/pipeline_ssh_provider.py:8-13` exposes SSH connect kwargs and sudo secret lookup through the app-level pipeline SSH provider.
- `servers/runtime_limit_provider.py:8-50` implements agent-run and terminal-session runtime limits in the server domain.
- `servers/server_alert_provider.py:7-12` exposes server alert snapshots through the app-level alert provider.
- `servers/smoke_seed_provider.py:8-56` implements smoke server and server-agent seeding in the server domain.
- `servers/studio_server_access_provider.py:8-100` implements Studio server-access queries in the server domain.
- `studio/runtime_limit_provider.py:9-56` implements pipeline-run runtime limits in the Studio domain.
- `studio/smoke_seed_provider.py:7-49` implements smoke pipeline seeding in the Studio domain.
- `servers/tool_gateway.py:13-86` implements those operations with Django ORM and `ServerKnowledgeService`.
- `core_ui/apps.py:23-31` injects the Django budget, usage, and tool activity providers at the app boundary; `servers/apps.py:16-35` and `studio/apps.py:12-22` inject server/studio providers.
- `.importlinter` no longer has `ignore_imports` entries.

SOLID / Clean Code impact:

- The `app.core` shared-service boundary is now cleaner: LLM budget and usage logging depend on registered ports instead of `core_ui` implementations.
- Tool activity/audit logging now depends on a registered port instead of direct `core_ui` imports.
- Tool server secrets now depend on a registered port instead of direct `servers.secret_utils` imports.
- `ServerExecuteTool` no longer imports server ORM or knowledge services directly; those concerns sit behind a registered server-tool gateway.
- `SSHConnectionManager` no longer imports server-owned host-key helpers directly; those concerns sit behind a registered host-key provider.
- `core_ui.views.chat_helpers` no longer imports `servers` or `app.tools.server_tools` directly; chat-specific server behavior sits behind a registered provider.
- `core_ui.views.admin_views` no longer imports server ORM directly; admin dashboard aggregation sits behind a registered metrics provider.
- `core_ui.management.commands.seed_multi_user_smoke` no longer imports `servers` or `studio` directly; smoke-domain object creation sits behind registered seed providers.
- `app.runtime_limits` no longer imports both feature domains directly; agent, terminal, and pipeline limit behavior sits behind registered providers.
- `studio.apps` no longer imports `servers.signals`; server monitoring publishes an app-level signal that Studio subscribes to.
- `studio.skill_authoring` no longer imports server tool catalog directly; recommended-tool validation reads a registered app-level catalog.
- `studio.trigger_dispatch` no longer imports server alert query helpers directly; monitoring trigger launch uses registered alert snapshot lookups.
- `studio.services.server_access` no longer imports server query helpers directly; resource binding and validation use a registered server-access provider.
- `studio.pipeline_agent_llm` and `studio.pipeline_agent_runtime` no longer import server memory, command-history, SSH connection, or server-agent engine helpers directly.
- DIP risk remains as a maintenance risk if future feature-app bridges are added without a provider/gateway.
- Interface boundary risk: future developers may copy an exception pattern instead of adding a provider/gateway.

Future problem:

- New exceptions would weaken the architecture contract; the current contract is clean and should stay exception-free.

Recommended direction:

- Keep `.importlinter` exception-free; treat any proposed ignored import as an architecture review item with an owner and removal condition.
- Add new cross-feature behavior through app-level providers, gateways, events, or DTOs.
- Keep new shared `app.core` functionality behind provider registration instead of reintroducing feature-app imports.

### 7. Fixed For Built-Ins: Agent Tools Use Explicit Metadata

Evidence:

- `servers/agent_tools.py:218-348` declares `tool_spec` metadata next to every built-in agent tool implementation.
- `app/agent_kernel/tools/registry.py:61-79` builds `ToolSpec` from declared metadata before considering compatibility inference.
- `app/agent_kernel/tools/registry.py:86-99` receives the built-in agent tool source as an explicit dependency instead of importing `servers.agent_tools`.
- `servers/agent_engine.py:327-331` and `servers/multi_agent_engine.py:300-304`, `567-571` inject `AGENT_TOOLS` at the server-runtime boundary.
- `app/agent_kernel/tools/registry.py:105-113` keeps name-based inference only as a logged compatibility fallback for undeclared built-in tools and generic MCP bindings.
- `tests/test_agent_tool_registry.py:5-37` asserts built-in metadata is mandatory and declared metadata wins over legacy name inference.

SOLID / Clean Code impact:

- The concrete OCP/Clean Code risk for built-in server tools is reduced: adding a built-in tool now means adding explicit policy metadata beside the tool registration instead of editing registry heuristics.
- The direct DIP issue in `ToolRegistry` is closed for built-ins because the source catalog is injected by the server runtime.
- Extension risk remains for MCP/plugin tools until their bindings can provide explicit `ToolSpec` metadata too.

Future problem:

- Plugin or MCP tools can still be too generic if their bindings cannot declare category, risk, mutation, and verification requirements.
- New built-in tools will fail the metadata test if they omit `tool_spec`, but the runtime still has a compatibility fallback instead of hard-failing.

Recommended direction:

- Remove built-in compatibility inference once all runtime call paths tolerate strict metadata requirements.
- Extend MCP/plugin bindings so external tools can carry explicit `ToolSpec` metadata instead of only generic MCP risk.
- Add a contract test for MCP/plugin tool metadata once plugin registration exists.

### 8. Partially Mitigated: Pipeline Has a Target Engine and a Production Compatibility Path

Evidence:

- `studio/executor/registry.py:1-13` describes the target node registry architecture.
- `studio/executor/engine.py:1-17` says the engine is the target architecture while `studio/pipeline_executor.py` still handles execution.
- `studio/executor/engine.py:114-121` now fails fast when the target engine sees an unregistered node type instead of silently skipping it.
- `studio/pipeline_executor.py:196-239` executes registry-owned nodes from the current production executor.
- `studio/pipeline_executor.py:316-327` dispatches registered node types through the registry and fails unknown node types.
- `tests/test_pipeline_engine.py:10-32` covers target-engine unknown-node failure.
- `tests/test_studio_unknown_node_runtime.py:8-34` covers production-executor unknown-node failure.
- `tests/test_studio_node_manifest_consistency.py:16-17` asserts the executor registry covers every non-trigger known node type.

SOLID / Clean Code impact:

- SRP risk remains because pipeline execution knowledge is still split between target engine, production executor, node adapters, and compatibility helpers.
- OCP risk is lower for unknown-node behavior and registry coverage, because both target and production paths now fail unregistered nodes and tests enforce current registry coverage.

Future problem:

- New pipeline nodes or plugin nodes can still behave differently in validation, dry-run, production run, and target-engine paths unless parity is explicitly tested beyond node registration and unknown-node behavior.

Recommended direction:

- Keep production node additions going through the registry adapter only.
- Add a parity checklist for each new node: manifest, validation, dry-run, production execution, redaction, policy, tests.
- Retire compatibility aliases only after call-site search proves they are unused.

### 9. Partially Mitigated: Multi-Agent Engine Still Owns Run Finalization and Mini ReAct Logic

Evidence:

- `servers/multi_agent_engine.py:223-435` still owns top-level run setup, planning, final synthesis, report delivery, and cleanup.
- `servers/multi_agent_engine.py:437-580` still owns existing-plan connection setup, final synthesis, report delivery, and cleanup.
- `servers/multi_agent_engine.py:712-870` still owns the mini ReAct task loop.
- `servers/multi_agent_plan_executor.py:24-132` now owns the shared plan-task execution control flow used by both normal `run()` and approved `execute_existing_plan()` paths: completed/skipped task filtering, pause/stop/timeout checks, task start/done/failure events, persistence callbacks, replan restart, ask-user waiting state, and retry handling.
- `servers/multi_agent_run_state.py:18-75` now owns shared task lifecycle helpers used by both run loops: skipped/running/done/failed/stopped task mutation, task start/done/failure event payloads, context-summary result/user-answer chunks, replanned task id assignment, and session-timeout retry-deadline calculation.
- `servers/multi_agent_subagents.py:13-122` now owns plan-task preparation, task subagent construction, fallback no-registry subagents, tool-slice selection, and subagent prompt context construction.
- `servers/multi_agent_engine.py:648-674` keeps compatibility methods for plan-task preparation and subagent prompt context, but delegates their behavior to `servers.multi_agent_subagents`.
- `servers/multi_agent_task_setup.py:12-87` now owns task runtime setup: role/permission/tool metadata application, subagent metadata merging, task-specific operational recipe query construction, server/group recipe scope selection, and memory-store recipe prompt loading.
- `servers/multi_agent_task_iterations.py:15-132` now owns task-iteration entry/event helpers, observation/final/verification-blocked state updates, observation-history message appends, verification-blocked continuation wording, observation truncation limits, and live `plan_tasks` merge helpers for persistence.
- `servers/multi_agent_task_prompts.py:15-113` now owns task-agent prompt assembly: connected-server text, tool/MCP description filtering by task tool slice, skill catalog text, operator-provided materials, MCP/skill error blocks, sudo-policy instruction text, prior-task context, and initial chat history.
- `servers/multi_agent_tool_execution.py:17-149` now owns the per-tool execution boundary: subagent tool-slice checks, tool-registry lookup, permission decisions, sudo argument preparation, sandbox validation, MCP skill-policy application, MCP success recording, built-in tool dispatch, and post-tool hooks.
- `servers/multi_agent_engine.py:1144-1173` keeps the compatibility `_execute_tool` method, but delegates behavior to `execute_multi_agent_tool`.
- `tests/test_multi_agent_run_state.py:20-87` covers shared task lifecycle status/event mutations, legacy stopped/timeout reason strings, context-summary formats, replanned task id assignment, and timeout-only retry deadline extension.
- `tests/test_multi_agent_subagents.py:36-94` covers legacy task shape without a registry, subagent metadata/tool filtering with a registry, and task-specific recipe prompt precedence.
- `tests/test_multi_agent_task_setup.py:26-139` covers task runtime metadata merging, deterministic recipe query/scope construction, recipe prompt loading/skipping, and the combined runtime preparation path.
- `tests/test_multi_agent_task_iterations.py:26-145` covers iteration entry/event shape, observation/event truncation, final-answer state updates, verification-blocked state updates, observation history append behavior, required verification-continuation wording, and immutable `plan_tasks` merging.
- `tests/test_multi_agent_task_prompts.py:17-84` covers prompt history shape, task context/materials, connected-server text, MCP tool-slice filtering, skill catalog text, MCP/skill error blocks, max-iteration text, and empty-state fallbacks.
- `tests/test_multi_agent_tool_execution.py:55-125` covers subagent slice denial, missing local registry specs, the built-in tool permission/sandbox/hook path, and disabled built-in tool compatibility messages.
- `tests/test_multi_agent_plan_executor.py:73-168` covers shared plan execution success/context carry-over, done/skipped filtering, replan behavior that does not rerun completed work, and ask-user waiting-state/context behavior.

SOLID / Clean Code impact:

- SRP risk is lower for shared task lifecycle/context/replan state, common plan execution control flow, role/tool slicing, task runtime setup/recipe loading, task-iteration state/history/persistence helpers, task-agent prompt construction, subagent prompt context construction, and per-tool execution because those behaviors are now isolated and unit-testable without a running `MultiAgentEngine`.
- SRP risk remains in the top-level run methods and mini ReAct loop, which still mix connection setup, LLM calls, run finalization, report delivery, and runtime control.
- OCP risk remains for adding new orchestration modes or subagent lifecycle behaviors because most execution policy still routes through one large class.

Future problem:

- Adding new multi-agent modes or plugin-driven subagents can still regress verification gating, event ordering, final synthesis, or run status persistence unless the remaining engine-owned phases are split behind narrower services.

Recommended direction:

- Continue extracting multi-agent execution phases around task mini-ReAct execution, failure/replan decisions, final synthesis, and report delivery.
- Keep `MultiAgentEngine` as the compatibility coordinator and push new subagent behavior into focused modules first.

### 10. Partially Mitigated: Test Files Are Also Becoming God Files

Evidence:

- `tests/test_servers_api_smoke.py` is 1188 lines after moving host-key, agent-control, and knowledge/master-password API coverage out.
- `tests/test_servers_host_key_api.py:1-121` now owns trusted-host-key update/test/refresh-sharing coverage.
- `tests/test_servers_agent_control_api.py:1-430` now owns agent CRUD/run/control, runtime reply sync, live-engine-free reply/stop, targeted stop, and queued-dispatch cancellation coverage.
- `tests/test_servers_knowledge_api.py:1-293` now owns server sharing, master-password, knowledge, memory snapshot CRUD/bulk delete, memory policy, dream-run, and reveal-password endpoint coverage.
- `tests/test_studio_node_executors.py` is 962 lines after moving agent-node, output-node, and ops-node coverage out.
- `tests/test_studio_agent_node_executors.py:1-121` now owns `agent/react` and `agent/multi` rendered-goal/runtime dispatch coverage.
- `tests/test_studio_notification_node_executors.py:1-305` now owns `output/email` and `output/telegram` rendering, redaction, transport, and failure coverage.
- `tests/test_studio_output_node_executors.py:1-244` now owns `output/report` and `output/webhook` summary, redaction, payload, and failure coverage.
- `tests/test_studio_ops_node_executors.py:1-496` now owns `ops/server_snapshot`, `ops/log_query`, `ops/file_action`, `ops/package_action`, `ops/disk_cleanup`, `ops/backup_restore_check`, `ops/http_check`, and `ops/alert_update` runtime coverage.
- `tests/test_ops_agent_kernel.py` is 1293 lines after moving SSH terminal manual-input compatibility coverage out.
- `tests/test_ssh_terminal_manual_input_compat.py:1-89` now owns consumer-level manual terminal marker/persistence compatibility tests.
- These are pinned in `pyproject.toml` legacy baselines.

SOLID / Clean Code impact:

- Clean Code risk remains: oversized smoke tests reduce locality. A small behavior change may require understanding a large fixture/setup surface.
- Test feedback risk: broad files encourage broad setup and broad assertions instead of focused unit/contract tests.

Future problem:

- Refactors will become slower because developers avoid touching large, brittle test modules.

Recommended direction:

- Split by behavior contract, not just by endpoint:
  - access/capability denial
  - mutation policy
  - redaction
  - node adapter parity
  - happy-path API smoke
- Keep one smoke file only for cross-feature integration coverage.
- Continue moving cohesive endpoint slices, like the host-key API block, into focused files with local helpers.

### 11. Partially Mitigated: Global Singletons Make Dependency Boundaries Harder to See

Evidence:

- `app/core/llm.py:28-44` caches a module-level `LLMProvider`.
- `app/core/provider_registry.py:190-205` keeps a module-level provider registry but now exposes explicit `set_provider_registry` and `reset_provider_registry` lifecycle hooks.
- `studio/executor/registry.py:65-90` exposes in-place snapshot/replace/clear methods for the global node registry.
- `studio/executor/registry.py:100-116` exposes module-level lifecycle helpers that keep the singleton object stable for modules that already imported it.
- `servers/agent_runtime.py:100-140` maintains an in-process live engine registry, now with `clear_registered_engines`.
- `servers/agent_runtime.py:108-122` now clears all `agent_id -> run_id` mappings for an unregistered run, even when the live engine object does not expose `engine.agent.id`.
- `tests/test_runtime_singletons.py:18-88` covers provider registry install/reset, live-engine unregister cleanup, full live-engine registry clearing, and Studio node-registry snapshot/clear/restore.

SOLID / Clean Code impact:

- DIP risk: callers often depend on ambient global state instead of explicit collaborators.
- Testability risk is lower for provider registry, live agent engines, and the Studio node registry because reset/clear hooks are now explicit and covered.
- Plugin risk: runtime plugin registration can leak between users, tests, or process lifecycles if not carefully scoped.

Future problem:

- Multi-tenant plugin/provider behavior may become hard to isolate while `LLMProvider`, MCP/skill runtime registries, and other app-level registries still rely on process-global state.

Recommended direction:

- Keep global registries for compatibility, but expose explicit context-bound registries for new plugin/runtime work.
- Continue adding register/reset tests around remaining global registries, especially MCP/skill/runtime registries.

## Recommended Priority Order

1. Continue shrinking `SSHTerminalConsumer` by moving command execution and retry orchestration behind focused Terminal AI services.
2. Finish the LLM provider adapter migration by moving model-list/default-model selection and concrete streaming execution behind provider adapters.
3. Extend MCP/plugin tool bindings with explicit `ToolSpec` metadata and remove the remaining compatibility inference.
4. Add lifecycle/reset tests around the remaining global registries.
5. Split the largest test modules by behavior contract.

## Practical Rule For Future Work

When adding a feature, do not put new behavior into a compatibility file merely because it already exports a related symbol. Add a focused module, keep the compatibility export thin, and lower the legacy baseline if the old file shrinks.
