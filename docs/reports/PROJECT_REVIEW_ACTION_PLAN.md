# Project Review Action Plan

Last reviewed: 2026-06-21

This is the current implementation backlog after refreshing the docs against the codebase. It replaces the older 2026-05-19 action list.

## Checks Performed During This Refresh

- Reviewed current docs under `docs/`.
- Reviewed current project files with `rg --files`.
- Checked pipeline node contract against `studio/pipeline_validation.py`, `studio/models.py`, `studio/pipeline_executor.py`, `studio/trigger_dispatch.py`, `studio/executor/`, and frontend node metadata.
- Ran `python scripts\check_architecture_sizes.py --strict-new`.
  - Import boundaries: passed.
  - File-size guard: passed.

Full test suites were not run during the documentation refresh.

## 2026-06-20 Implementation Progress

- Restored import-boundary health: `python scripts\check_architecture_sizes.py --strict-new` now reports `SUCCESS: Import boundaries respected`.
- Closed the current legacy-growth backlog: `python scripts\check_architecture_sizes.py --strict-new` now reports `SUCCESS: All architecture contracts satisfied`.
- Added app-level provider/event seams for managed LLM secrets, LLM budget checks, LLM usage logging, runtime run/session limits, monitoring alert events and snapshots, tool activity/audit logging, server auth/sudo secrets, server-tool ORM/knowledge operations, SSH host-key verification, chat server context, admin dashboard server metrics, smoke-test seeding, agent-tool catalog reads, Studio owned-server access, Studio pipeline memory/SSH/agent execution/command-history access, Studio skill access, and notification config so `app.core`, `app.tools`, `core_ui`, `servers`, and `studio` no longer need the direct cross-app imports that were breaking the contracts.
- Moved sudo policy primitives to `app.sudo_policy`; `app.agent_kernel.sudo_policy` remains a compatibility re-export.
- Split mini-agent LLM analysis into `servers/agent_analysis.py`, bringing `servers/agents.py` back below the standard 500-line limit.
- Split LLM runtime policy/key-loading/model catalog helpers into `app/core/llm_runtime.py`, `app/core/llm_provider_keys.py`, `app/core/model_catalog.py`, and `app/core/ollama_config.py`, making `app/core/llm.py` and `app/core/model_config.py` small enough to remove from legacy baselines.
- Split provider registry status/default policy and LLM auto-routing into `app/core/provider_adapters.py` and `app/core/llm_provider_resolution.py`; `ProviderRegistry` now composes provider adapters, and `LLMProvider.stream_chat` delegates auto provider/model selection before the concrete streaming branches.
- Moved provider model-selection metadata into `app/core/model_catalog.py`; `ModelManager` now delegates chat/agent model selection, default model lists, available-model cache lookup, and config enabled checks to the provider model catalog.
- Moved provider model-list refresh into `app/core/model_refresh.py`; `ModelManager.fetch_available_*` methods remain compatibility delegates while Gemini, Grok, Claude, OpenAI, FAIR.Hyperion, and Ollama local/cloud refresh logic lives outside `model_config.py`.
- Fixed purpose-specific LLM default inheritance: `chat_llm_*`, `agent_llm_*`, and `orchestrator_llm_*` now default to empty strings, matching the documented "inherit from internal provider" behavior and the settings UI fallback contract.
- Moved OpenAI-compatible streaming into `app/core/llm_openai_compatible.py`: OpenAI, FAIR, and Grok now share request construction, Responses/Completions/Chat Completions SSE parsing, retry/backoff, HTTP/timeout error handling, optional `trust_env`, and usage logging.
- Moved Claude streaming into `app/core/llm_anthropic.py`: Anthropic request construction, prompt-cache `cache_control`, streaming retry/timeout behavior, timeout/error messages, and usage logging are now outside `LLMProvider.stream_chat`.
- Moved Gemini streaming into `app/core/llm_gemini.py`: Gemini request construction, `system_instruction`, JSON-mode `response_mime_type`, stream consumption, retry/timeout behavior, timeout/error messages, and usage logging are now outside `LLMProvider.stream_chat`.
- Moved Ollama streaming into `app/core/llm_ollama.py`: local/cloud target construction, payload building, JSON-line stream parsing, local base-URL fallback, retry/timeout behavior, local base-URL persistence callback, and usage logging are now outside `LLMProvider.stream_chat`.
- Split Studio integration readiness requirements into `studio/readiness_requirements.py`, keeping `studio/readiness.py` focused on report assembly.
- Split Studio pipeline validation schema helpers into `studio/pipeline_validation_schema.py` and node-manifest schema builders into `studio/node_manifest_schema.py`.
- Split environment/settings helpers into `web_ui/settings/env_helpers.py`.
- Moved model-local helpers into `studio/model_helpers.py` and `servers/model_helpers.py`, bringing `studio/models.py` and `servers/models.py` back under their legacy baselines.
- Moved AI settings route/provider DTOs into `frontend/src/pages/settings-page/aiSettingsTypes.ts`, keeping `useAiSettingsForm.ts` below the standard size limit.
- Moved Studio notification API calls/types into `frontend/src/api/studio-notifications.ts`, continuing the `frontend/src/lib/api.ts` facade shrink.
- Moved auth/session, settings/access, and server inventory/share/group API calls and types into `frontend/src/api/auth.ts`, `frontend/src/api/settings.ts`, and `frontend/src/api/servers.ts`, starting the current compatibility-facade shrink.
- Moved Studio pipeline/run/agent/skill/MCP/trigger/template API calls into `frontend/src/api/studio.ts` and Studio DTO contracts into `frontend/src/api/studio-types.ts`; `frontend/src/lib/api.ts` remains a compatibility facade.
- Added explicit `tool_spec` policy metadata to built-in agent tools and changed `ToolRegistry` to prefer declared metadata over legacy name-based inference, with server engines injecting the built-in tool catalog at the runtime boundary.
- Added explicit lifecycle hooks for the LLM provider registry, live agent-engine registry, and Studio node registry, including cleanup for stale agent-to-run mappings when a live engine unregisters and in-place snapshot/restore for temporary node-registry overrides.
- Changed the target `PipelineEngine` to fail unregistered node types instead of silently skipping them, matching the current production executor contract.
- Moved terminal-AI confirm/cancel/stop transitions, forbidden-pattern request state, and new-request/cancel request-state reset into `servers/services/terminal_ai/session.py`, reducing `servers/consumers/ssh_terminal.py` without changing the WebSocket event contract.
- Moved the transitional legacy consumer `_ai_*` sync/apply bridge into `servers/services/terminal_ai/legacy_state.py`, keeping `TerminalAiSession` focused on request state and queue state-machine behavior.
- Moved terminal-AI queue cursor transitions into `servers/services/terminal_ai/session.py`: initial plan installation, next-command preparation, blocked-command skip, wait-for-confirm setup, current-command completion, and goal-achieved skip-remaining are now service-level state-machine operations.
- Moved terminal-AI asyncio run lifecycle into `servers/services/terminal_ai/run_controller.py`: the service now owns the AI lock, active task, user-reply futures, and shared ask-user send/wait/cleanup flow, while `SSHTerminalConsumer` delegates task start/cancel/cleanup, `ai_reply` resolution, and repeated `ai_question` waiting.
- Moved terminal-AI active PTY command state into `servers/services/terminal_ai/active_command.py`: the helper owns active command registration, exit-future lookup/resolution/cancel cleanup, bounded active-output capture, tail projection, and guarded clear behavior; `terminal_manual_command_state.append_ai_output()` now delegates to it.
- Moved terminal-AI PTY command completion/runtime monitoring into `servers/services/terminal_ai/pty_command.py`: the service now owns marker-future waiting, streaming timeout fallback, install-progress events, install-error interrupt callbacks, helper-task cleanup, and active-output tail return.
- Moved terminal-AI recovery decision helpers into `servers/services/terminal_ai/recovery.py`: the service now owns recovery-attempt gating, recovery-action normalization, retry-command validation, recovery text defaults, and retry-item insertion/event emission through consumer-compatible owner hooks.
- Moved terminal-AI fast-mode recovery orchestration into `servers/services/terminal_ai/recovery.py`: the service now owns analyze-error status emission, remaining-command projection, LLM recovery calls, ask-user retry follow-up, abort/error events, timeout fallback, and recovery exception handling for fast-mode command failures.
- Moved terminal-AI step-mode post-command orchestration into `servers/services/terminal_ai/recovery.py`: the service now owns step-decision calls, ask-user follow-up, retry insertion, adaptive next-step insertion, goal-complete skip handling, abort events, and step-mode exception handling after each command.
- Moved terminal-AI post-queue completion orchestration into `servers/services/terminal_ai/queue_completion.py`: the service now owns final done-item snapshotting, auto-report generation, report/history side effects, memory candidate projection, and memory-extraction task spawning.
- Fixed retry-item recovery suppression: `_build_reserved_plan_item(..., no_recovery=True)` now writes `_no_recovery=True`, with regression coverage in `tests/test_terminal_ai_recovery.py`.
- Moved terminal-AI retry/adaptive plan-item reservations into `servers/services/terminal_ai/plan_insertions.py`, including retry-count registration and adaptive-step limit accounting.
- Moved terminal-AI parallel-batch payload construction into `servers/services/terminal_events.py`, and moved parallel-batch selection, cursor advancement, and explicit plan completion into `TerminalAiSession`, including a guard against negative plan indices.
- Replaced the standard Terminal AI status/error/response/direct-output dictionaries in `SSHTerminalConsumer` with `servers.services.terminal_events` builders; only custom payloads without a matching builder remain inline.
- Moved non-PTY direct command execution into `servers/services/terminal_direct_execution.py`: SSH channel execution, timeout mapping, stdout/stderr merging, truncation, null-exit fallback, and `ai_direct_output` event emission now live outside `SSHTerminalConsumer`.
- Moved parallel direct-command batch execution into `servers/services/terminal_parallel_batch.py`: batch start/done events, per-item running/done events, dry-run previews, snapshots, direct execution, command-history writes, unavailable-command recording, and explicit plan-index completion now live outside `SSHTerminalConsumer`.
- Moved manual terminal input orchestration into `servers/services/terminal_manual_input.py`: capture-buffer updates, editor intercept cancellation/event payloads, marker injection for single safe commands, no-marker immediate persistence, manual command activity logging, and pending manual-command queue bookkeeping now live outside `SSHTerminalConsumer`.
- Moved terminal-agent test fakes into `tests/agent_tool_fakes.py`, bringing `tests/test_agent_tools.py` below the standard size limit.
- Moved shared multi-agent task lifecycle helpers into `servers/multi_agent_run_state.py`: skipped/running/done/failed/stopped task mutation, task event payloads, context-summary result/user-answer chunks, replanned task id assignment, and session-timeout retry-deadline calculation now live outside the duplicated `run` and `execute_existing_plan` loops.
- Moved multi-agent task/subagent preparation into `servers/multi_agent_subagents.py`: plan-task shaping, task subagent construction, tool-slice filtering, fallback no-registry subagents, and subagent prompt context now live outside `MultiAgentEngine` while compatibility methods delegate to the service.
- Moved multi-agent task runtime setup into `servers/multi_agent_task_setup.py`: role/permission/tool metadata application, subagent metadata merging, task-specific operational recipe query construction, server/group recipe scope selection, and memory-store recipe prompt loading now live outside `MultiAgentEngine`.
- Moved multi-agent task-iteration state helpers into `servers/multi_agent_task_iterations.py`: iteration entry/event construction, observation/final/verification-blocked task updates, observation-history appends, verification-continuation wording, observation truncation limits, and live `plan_tasks` merge behavior now live outside `MultiAgentEngine`.
- Moved multi-agent task-agent prompt assembly into `servers/multi_agent_task_prompts.py`: connected-server text, tool/MCP descriptions filtered by task tool slice, skill catalog text, operator-provided materials, MCP/skill error blocks, sudo-policy text, prior-task context, and initial chat history now live outside `MultiAgentEngine`.
- Moved multi-agent per-tool execution into `servers/multi_agent_tool_execution.py`: subagent tool-slice checks, tool-registry lookup, permission decisions, sudo argument preparation, sandbox validation, MCP skill-policy application, MCP success recording, built-in tool dispatch, and post-tool hooks now live outside `MultiAgentEngine` while `_execute_tool` remains a compatibility delegate.
- Moved shared multi-agent plan execution into `servers/multi_agent_plan_executor.py`: normal run and approved existing-plan execution now share completed/skipped task filtering, pause/stop/timeout checks, task events, persistence callbacks, replan restart, ask-user waiting state, and retry handling. Both paths skip already done/skipped tasks, so a replan does not rerun completed work.
- Split server API access smoke coverage into `tests/test_servers_access_smoke.py`, agent-engine prompt text into `servers/agent_engine_prompts.py`, and model helpers into `servers/model_helpers.py` / `studio/model_helpers.py`.
- Split server trusted-host-key API smoke coverage into `tests/test_servers_host_key_api.py`, agent-control API coverage into `tests/test_servers_agent_control_api.py`, and knowledge/master-password API coverage into `tests/test_servers_knowledge_api.py`, lowering `tests/test_servers_api_smoke.py` to its current size.
- Fixed the server execute endpoint's missing `sudo_password` resolution and stabilized the mocked SSH execute smoke test against background OS-detect side effects.
- Split SSH terminal manual-input consumer compatibility coverage into `tests/test_ssh_terminal_manual_input_compat.py`, lowering `tests/test_ops_agent_kernel.py` to its current size while keeping marker injection, output persistence, and multiline no-marker fallback covered.
- Split Studio agent-node executor coverage into `tests/test_studio_agent_node_executors.py`, notification output-node coverage into `tests/test_studio_notification_node_executors.py`, report/webhook output-node coverage into `tests/test_studio_output_node_executors.py`, and ops-node coverage into `tests/test_studio_ops_node_executors.py`, lowering `tests/test_studio_node_executors.py` to its current size while keeping `agent/react`, `agent/multi`, output nodes, and ops nodes covered.
- Split frontend legacy-growth pages into focused modules: agent config cards/options, agents wizard utilities/materials/progress, server groups tab, server list state controller, server/group CRUD controllers, server advanced workflow controllers, Studio skill catalog/detail/workspace/settings/dialog modules, and shared settings AI constants.
- Split the frontend API compatibility facade further: access feature metadata lives in `frontend/src/lib/access-features.ts`, and demo/offline fallback routing/data is split across focused `frontend/src/lib/api-demo-*.ts` modules; `frontend/src/lib/api.ts` is below the standard size limit and removed from legacy baselines.
- Split the nested `AgentFrontedTest/log-seer-main` shadcn sidebar into `sidebar-context.tsx`, `sidebar-layout.tsx`, `sidebar-menu.tsx`, and a compatibility `sidebar.tsx` barrel so the untracked nested frontend no longer trips the strict architecture size guard.
- Lowered stale legacy baselines to current file lengths so the size guard has no hidden slack on already-shrunk files.
- Verification for this slice: `npm run build` passed in `frontend/`; `npm run test -- src/pages/Servers.test.tsx` passed in `frontend/`; `python -m ruff check --select I,UP,F servers\services\terminal_ai\session.py servers\consumers\ssh_terminal.py tests\test_terminal_ai_session.py tests\test_server_ai_read_only.py` passed; WSL pytest passed for `app/test_runtime_limits.py`, `app/test_studio_skill_authoring.py`, `tests/test_agent_tool_registry.py`, `tests/test_agent_tools.py`, `tests/test_agent_and_pipeline_policy_enforcement.py`, `tests/test_chat_server_provider.py`, `tests/test_smoke_seed_provider.py`, `tests/test_provider_adapters.py`, `tests/test_llm_provider_resolution.py`, `tests/test_llm_runtime_unit.py`, `tests/test_json_mode.py`, `tests/test_runtime_singletons.py`, `tests/test_pipeline_engine.py`, `tests/test_studio_unknown_node_runtime.py`, `tests/test_studio_node_manifest_consistency.py`, `tests/test_servers_host_key_api.py`, `tests/test_servers_api_smoke.py::test_server_create_accepts_uploaded_ssh_private_key`, `tests/test_terminal_ai_session.py`, `tests/test_server_ai_read_only.py`, `tests/test_studio_monitoring_trigger.py`, `tests/test_servers_monitor.py`, `tests/test_studio_node_executors.py`, `tests/test_studio_pipeline_v2.py`, `tests/test_studio_readiness.py`, `tests/test_studio_run_creation_preflight.py`, `tests/test_studio_runtime_context_validation.py`, `tests/test_studio_api_smoke.py::test_studio_notification_endpoints_with_mocked_transports`, and `tests/test_studio_all_nodes_smoke.py`.
- Additional Terminal AI verification: `python -m ruff check --select I,UP,F` passed for the changed Terminal AI/session/event/manual-input/direct-execution/parallel-batch modules and focused tests; WSL `.venv` pytest passed 155 focused Terminal AI/server AI/ops-kernel tests, 59 focused manual-input/input-service/command-recorder/editor-intercept/ops-kernel tests, 14 focused direct-execution compatibility tests, 2 focused dry-run/direct-output event tests, and 56 focused parallel-batch/session/direct/dry-run event tests; `python scripts\check_architecture_sizes.py --strict-new` passed.
- Additional test-layout verification: `python -m ruff check --select I,UP,F` passed for the split ops-agent/manual-terminal, Studio agent-node, Studio notification-node, Studio output-node, Studio ops-node, server API smoke, server agent-control API, server knowledge API, and server execute endpoint modules; WSL `.venv` pytest passed 13 focused SSH terminal manual-input compatibility/service/input and ops-kernel tests, 50 focused Studio agent/output/ops/node executor tests, and focused server API smoke/agent-control checks; `python scripts\check_architecture_sizes.py --strict-new` passed.
- Additional LLM provider verification: `python -m ruff check --select I,UP,F` passed for the changed LLM provider/model/runtime modules and focused tests; WSL `.venv` pytest passed 28 focused Grok/OpenAI-compatible/runtime tests, 43 focused provider/model/runtime/OpenAI-compatible streaming tests, 58 focused Anthropic/provider/model/runtime tests, 62 focused Gemini/Anthropic/provider/model/runtime tests, 55 focused Ollama/Gemini/Anthropic/provider/model/runtime tests, and 42 focused model-refresh/provider/model/runtime tests in the broader LLM slice; `python scripts\check_architecture_sizes.py --strict-new` passed.
- Additional multi-agent verification: `python -m ruff check --select I,UP,F` passed for `servers/multi_agent_engine.py`, `servers/multi_agent_plan_executor.py`, `servers/multi_agent_run_state.py`, `servers/multi_agent_subagents.py`, `servers/multi_agent_task_setup.py`, `servers/multi_agent_task_iterations.py`, `servers/multi_agent_task_prompts.py`, `servers/multi_agent_tool_execution.py`, and focused tests; WSL `.venv` pytest passed 6 focused multi-agent subagent/policy tests, 10 focused multi-agent tool-execution/subagent/policy tests, 12 focused multi-agent prompt/tool/subagent/policy tests, 18 focused multi-agent iteration/prompt/tool/subagent/policy tests, 23 focused multi-agent setup/iteration/prompt/tool/subagent/policy tests, 28 focused multi-agent run-state/setup/iteration/prompt/tool/subagent/policy tests, and 32 focused multi-agent plan-executor/run-state/setup/iteration/prompt/tool/subagent/policy tests; higher-level WSL `.venv` smoke tests passed for API run launch, approve-plan background launch, and Studio multi-agent node execution; `python scripts\check_architecture_sizes.py --strict-new` passed.
- Additional Studio skills frontend verification: `npx eslint` passed for `src/pages/StudioSkillsPage.tsx` and the focused `src/pages/studio-skills/` modules; `npm run build` passed in `frontend/`; `python scripts\check_architecture_sizes.py --strict-new` passed after reducing `StudioSkillsPage.tsx` below the standard size limit and removing its legacy baseline.
- Additional frontend API facade verification: `npx eslint` passed for `src/lib/api.ts`, `src/lib/access-features.ts`, and the split `src/lib/api-demo-*.ts` modules; `npm run build` passed in `frontend/`; `python scripts\check_architecture_sizes.py --strict-new` passed after reducing `frontend/src/lib/api.ts` below the standard size limit and removing its legacy baseline.
- Additional Agent run frontend verification: `npx eslint` passed for `src/pages/AgentRunPage.tsx` and the focused `src/pages/agent-run/` modules; `npm run build` passed in `frontend/`; `python scripts\check_architecture_sizes.py --strict-new` passed after reducing `AgentRunPage.tsx` below the standard size limit and removing its legacy baseline.
- Additional Terminal page frontend verification: `npx eslint` passed for `src/pages/TerminalPage.tsx` and the focused `src/pages/terminal-page/` modules; `npm run build` passed in `frontend/`; `python scripts\check_architecture_sizes.py --strict-new` passed after reducing `TerminalPage.tsx` below the standard size limit and removing its legacy baseline.
- Additional XTerminal frontend verification: `npx eslint` passed for `src/components/terminal/XTerminal.tsx`, `XTerminalDropZone.tsx`, and `xterminalConfig.ts`; `npm run build` passed in `frontend/` after moving default xterm theme/font normalization into `xterminalConfig.ts` and file-drop overlay handling into `XTerminalDropZone.tsx`, reducing `XTerminal.tsx` to 480 lines and removing its legacy baseline.
- Additional Pipeline editor frontend verification: `npx eslint` passed for `src/pages/PipelineEditorPage.tsx`, `src/pages/PipelineEditorPage.test.tsx`, and the focused `src/pages/pipeline-editor/` modules touched in this slice; `npm run test -- src/pages/PipelineEditorPage.test.tsx` passed in `frontend/`; `npm run build` passed in `frontend/`; `python scripts\check_architecture_sizes.py --strict-new` passed after moving live run graph overlay handling into `usePipelineRunGraphOverlay.ts`, graph display-state derivation into `usePipelineGraphDisplayState.ts`, graph editing callbacks into `usePipelineEditorGraphActions.ts`, assistant draft orchestration into `usePipelineAssistantDraft.ts`, trigger/run-mode derivation into `usePipelineEditorTriggers.ts`, save/run/dry-run mutations into `usePipelineEditorMutations.ts`, and run-dialog wiring into `PipelineRunDialogHost.tsx`, reducing `PipelineEditorPage.tsx` to 488 lines and removing its legacy baseline.
- Additional SSH terminal agent-target verification: `python -m ruff check --select I,UP,F` passed for `servers/services/terminal_agent_context.py`, `servers/consumers/ssh_terminal.py`, and `tests/test_terminal_agent_context.py`; WSL `.venv` pytest passed `tests/test_terminal_agent_context.py`; `python scripts\check_architecture_sizes.py --strict-new` passed after moving authorised agent extra-target connection setup into `terminal_agent_context.py`, reducing `ssh_terminal.py` to 2426 lines, and lowering its legacy baseline.
- Additional Terminal AI panel verification: `npx eslint` passed for `src/components/terminal/AiPanel.tsx`, `src/components/terminal/ai-panel/AiPanelMessages.tsx`, `src/components/terminal/ai-panel/AiPanelSettingsDialog.tsx`, `src/components/terminal/ai-panel/AgentTimelineMessages.tsx`, and `src/components/terminal/ai-panel/AgentToolMsg.tsx`; `npm run build` passed in `frontend/`; `python scripts\check_architecture_sizes.py --strict-new` passed after moving AI message rendering, Nova/agent timeline rendering, and settings-dialog rendering into focused `ai-panel/` modules, reducing `AiPanel.tsx` to 380 lines and removing its legacy baseline.
- Additional AI settings route verification: `npx eslint` passed for `src/pages/settings/SettingsAIPage.tsx`, `src/pages/settings-page/AiSettingsPanel.tsx`, `src/pages/settings-page/useAiSettingsForm.ts`, and `src/pages/settings-page/PurposeModelSelector.tsx`; `npm run build` passed in `frontend/`; `python scripts\check_architecture_sizes.py --strict-new` passed after replacing the standalone AI settings monolith with a thin route wrapper around shared `AiSettingsPanel` and `useAiSettingsForm`, reducing `SettingsAIPage.tsx` to 76 lines and removing its legacy baseline.
- Additional Studio page frontend verification: `npx eslint` passed for `src/pages/StudioPage.tsx`, `src/pages/StudioPage.test.tsx`, and the focused `src/pages/studio-page/` modules; `npm run test -- src/pages/StudioPage.test.tsx` passed in `frontend/` after moving pipeline cards plus create/run/trigger/delete dialogs into page-local components, reducing `StudioPage.tsx` to 410 lines and removing its legacy baseline.
- Additional Agents page frontend verification: `npx eslint` passed for `src/pages/AgentsPage.tsx`, `src/pages/agents-page/CreateAgentDialog.tsx`, `src/pages/agents-page/AgentWizardStepContent.tsx`, and `src/pages/agents-page/AgentWizardProgress.tsx` after moving the create/edit wizard dialog into `CreateAgentDialog.tsx`, reducing `AgentsPage.tsx` to 291 lines and removing its legacy baseline.
- Additional Agent config frontend verification: `npx eslint` passed for `src/pages/AgentConfigPage.tsx`, `src/pages/agent-config/AgentFormAccessSections.tsx`, `src/pages/agent-config/AgentConfigCard.tsx`, and `src/pages/agent-config/agentConfigOptions.ts` after moving core settings, tool access, MCP, skills, server scope, and visibility sections into `AgentFormAccessSections.tsx`, reducing `AgentConfigPage.tsx` to 455 lines and removing its legacy baseline.
- Additional Settings users frontend verification: `npx eslint` passed for `src/pages/SettingsUsersPage.tsx` and the focused `src/pages/settings-users/` modules after moving permission helpers, typed create/edit drafts, shared permission controls, the user directory, and create-user sidebar out of the route component, reducing `SettingsUsersPage.tsx` to 160 lines and removing its legacy baseline.
- Additional Settings audit frontend verification: `npx eslint` passed for `src/pages/settings/SettingsAuditPage.tsx` and the focused `src/pages/settings-audit/` modules after moving audit logging constants, logging settings UI, and activity-log filters/table rendering out of the route component, reducing `SettingsAuditPage.tsx` to 177 lines and removing its legacy baseline.
- Additional Settings memory frontend verification: `npx eslint` passed for `src/pages/settings/SettingsMemoryPage.tsx` and the focused `src/pages/settings-memory/` modules after moving memory panel layout, overview sections, snapshot cards/actions, and worker-state cards out of the route component, reducing `SettingsMemoryPage.tsx` to 162 lines and removing its legacy baseline.
- Additional admin dashboard frontend verification: `npx eslint` passed for `src/pages/AdminDashboard.tsx` and the focused `src/pages/admin-dashboard/` modules after moving admin widget definitions out of the route component, reducing `AdminDashboard.tsx` to 78 lines and removing its legacy baseline.
- Additional customizable dashboard verification: `npx eslint` passed for `src/components/dashboard/CustomizableDashboard.tsx`, the focused dashboard builder modules, `src/pages/AdminDashboard.tsx`, `src/pages/UserDashboard.tsx`, and admin dashboard widget modules; `npm run build` passed in `frontend/`; `python scripts\check_architecture_sizes.py --strict-new` passed after moving dashboard widget definitions/types, curated layout presets, visible-widget derivation, widget library rendering, edit help, controls, grid rendering, settings panel, and resize/drag frame rendering into focused `src/components/dashboard/` modules, reducing `CustomizableDashboard.tsx` to 215 lines and removing its legacy baseline.
- Additional SFTP panel verification: `npx eslint` passed for `src/components/terminal/SftpPanel.tsx`, `SftpTransferQueue.tsx`, `LinuxUiPanel.tsx`, and the focused `src/components/terminal/sftp-panel/` modules; `npm run build` passed in `frontend/`; `python scripts\check_architecture_sizes.py --strict-new` passed after moving SFTP path/permission/entry helpers, text-editor rendering, text-editor state/load/save behavior, transfer queue orchestration, and SFTP formatting helpers into focused modules, reducing `SftpPanel.tsx` to 421 lines and removing its legacy baseline. The same slice fixed a stale `useMemo` dependency warning in `LinuxUiPanel.tsx`.
- Additional Linux UI settings verification: `npx eslint` passed for `src/components/terminal/LinuxUiSystemSettings.tsx` and the focused `src/components/terminal/linux-ui-settings/` modules; `npm run build` passed in `frontend/`; `python scripts\check_architecture_sizes.py --strict-new` passed after moving settings parsing/search/copy helpers, shared output primitives, search-result rendering, and section rendering into focused modules, reducing `LinuxUiSystemSettings.tsx` to 220 lines and removing its legacy baseline.
- Additional Linux UI text editor verification: `npx eslint` passed for `src/components/terminal/LinuxUiTextEditor.tsx` and the focused `src/components/terminal/linux-ui-text-editor/` modules; `npm run build` passed in `frontend/`; `python scripts\check_architecture_sizes.py --strict-new` passed after moving tab/recent-file/language-hint helpers, open/save/reload controller state, and editor layout rendering into focused modules, reducing `LinuxUiTextEditor.tsx` to 79 lines and removing its legacy baseline.
- Additional sidebar UI verification: `npx eslint` passed for `src/components/ui/sidebar.tsx`, the focused `src/components/ui/sidebar/` modules, `AppLayout.tsx`, `AppSidebar.tsx`, and `AppSidebar.mars.test.tsx`; `npm run test -- src/components/AppSidebar.mars.test.tsx` passed; `npm run build` passed in `frontend/`; `python scripts\check_architecture_sizes.py --strict-new` passed after keeping `sidebar.tsx` as a 29-line compatibility barrel and moving provider/context, layout primitives, group primitives, and menu primitives into focused modules.
- Additional Servers page test baseline cleanup: `npx eslint` passed for `src/pages/Servers.test.tsx` and `src/pages/servers/serversPageTestHarness.tsx`; `npm run test -- src/pages/Servers.test.tsx` passed after moving shared render helpers, fixtures, and API mock setup into `serversPageTestHarness.tsx`, reducing `Servers.test.tsx` to 201 lines and removing its legacy baseline.
- Additional Pipeline editor test baseline cleanup: `npx eslint` passed for `src/pages/PipelineEditorPage.test.tsx` and `src/pages/pipeline-editor/pipelineEditorPageTestHarness.tsx`; `npm run test -- src/pages/PipelineEditorPage.test.tsx` passed after moving pipeline editor fixtures, render helpers, and default API mock setup into `pipelineEditorPageTestHarness.tsx`, reducing `PipelineEditorPage.test.tsx` to 312 lines and removing its legacy baseline.
- Additional Studio pipeline assistant API test split: `python -m ruff check --select I,UP,F` passed for `app/test_studio_pipeline_assistant_api.py` and `app/test_studio_pipeline_assistant_api_templates.py`; WSL `.venv` pytest passed both files with 9 tests after moving template/interview/discard assistant draft scenarios into `test_studio_pipeline_assistant_api_templates.py`, reducing `test_studio_pipeline_assistant_api.py` to 369 lines and removing its legacy baseline.
- Additional pipeline draft view extraction: `python -m ruff check --select I,UP,F` passed for `studio/views/pipeline_draft_views.py`, `studio/views/pipeline_draft_helpers.py`, and focused assistant API tests; WSL `.venv` pytest passed both pipeline assistant API files with 9 tests after moving draft queryset/revision/validation/template helpers into `pipeline_draft_helpers.py`, reducing `pipeline_draft_views.py` to 250 lines and removing its legacy baseline.
- Additional pipeline validation reference extraction: `python -m ruff check --select I,UP,F` passed for `studio/pipeline_validation.py` and `studio/pipeline_validation_references.py`; WSL `.venv` pytest passed 15 focused pipeline validation/policy tests plus the all-nodes smoke validation after moving server, MCP, agent config, skill, cron, and node option reference checks into `pipeline_validation_references.py`, reducing `pipeline_validation.py` to 245 lines and removing its legacy baseline.
- Additional node manifest catalog extraction: `python -m ruff check --select I,UP,F` passed for `studio/node_manifest.py`, `studio/node_manifest_common.py`, `studio/node_manifest_ops.py`, and the consistency command; WSL `.venv` pytest passed node-manifest consistency plus all-nodes smoke validation, and `manage.py check_node_manifest_consistency --settings=web_ui.settings.test` passed after moving shared manifest builders into `node_manifest_common.py`, Ops node definitions into `node_manifest_ops.py`, and updating the checker to read `frontend/src/components/pipeline/nodes/nodeGuidanceMeta.ts`. `node_manifest.py` is now 347 lines and removed from its legacy baseline.
- Additional demo MCP server extraction: `python -m ruff check --select I,UP,F` and `python -m py_compile` passed for `studio/demo_mcp_server.py` and `studio/demo_mcp_tools.py`; stdio `tools/list`, stdio `workspace_snapshot`, and HTTP `/health` plus `/mcp` `tools/list` checks passed after moving tool schemas, handlers, and workspace filesystem helpers into `demo_mcp_tools.py`, reducing `demo_mcp_server.py` to 175 lines and removing its legacy baseline. `docker/demo-mcp.Dockerfile` now copies both modules.
- Additional Agent loop test split: `python -m ruff check --select I,UP,F` passed for `tests/test_agent_loop.py` and `tests/test_agent_system_prompt.py`; WSL `.venv` pytest passed both files with 13 tests after moving Terminal Agent system-prompt contract coverage into `test_agent_system_prompt.py`, reducing `test_agent_loop.py` to 465 lines and removing its legacy baseline.
- Additional pipeline node metadata verification: `npx eslint` passed for `src/components/pipeline/nodes/nodeMeta.tsx`, `nodeGuidanceMeta.ts`, `nodeMetaTypes.ts`, and `nodes.test.tsx`; `npm run test -- src/components/pipeline/nodes/nodes.test.tsx` passed after moving node guidance metadata and shared node metadata types out of the public facade, reducing `nodeMeta.tsx` to 191 lines and removing its legacy baseline.
- Additional Studio drafts frontend verification: `npx eslint` passed for `src/pages/StudioDraftsPage.tsx`, `src/pages/StudioDraftsPage.test.tsx`, and the focused `src/pages/studio-drafts/` modules; `npm run test -- src/pages/StudioDraftsPage.test.tsx` passed; `npm run build` passed in `frontend/`; `python scripts\check_architecture_sizes.py --strict-new` passed after moving draft payload helpers, queue rendering, graph wrapper, composer, review actions, and mobile tabs into page-local modules, reducing `StudioDraftsPage.tsx` to 374 lines and removing its legacy baseline.
- Additional nested frontend verification: `npm --prefix AgentFrontedTest\log-seer-main run build` passed after installing dependencies without rewriting the out-of-sync lockfile; `python scripts\check_architecture_sizes.py --strict-new` passed with the split sidebar files.

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
- The legacy size baseline for `servers/consumers/ssh_terminal.py` has been lowered from 4097 to 2426 lines across the stream-state, Terminal AI service-extraction, manual-input, direct-execution, parallel-batch, and agent-target context service slices.

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

Continue shrinking legacy-large frontend, terminal, and API files opportunistically when touching them. Keep behavior stable and add focused tests.

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
- `frontend/src/pages/PipelineEditorPage.tsx` is reduced to 488 lines and removed from legacy baselines; extracted palette, assistant, run-monitor, run dialog host, flow summary bar, toolbar/activity bar, canvas, main-area layout, side-panel rendering, run-dialog state/preparation, trigger/run-mode derivation, save/run/dry-run mutations, live run graph overlay, graph display-state derivation, graph editing actions, assistant draft orchestration, presentation, graph, cron, JSON schema, trigger config, `NodeConfigPanel`, and node-config modules live under `frontend/src/pages/pipeline-editor/`.
- `frontend/src/pages/Servers.tsx` is reduced to 390 lines and removed from legacy baselines; extracted page-local types, playbook helpers/panel, server list tab, server CRUD controller, server-group CRUD controller, server form dialog, share workflow controller, advanced dialog shell, access/context/security/execute advanced tabs, knowledge workflow controller, knowledge tab, knowledge dialogs, rules tab, rules/context workflow controller, security workflow controller, execute-command controller, memory snapshot helpers, server form helpers, rules/env helpers, group dialog, server groups tab, and formatters live under `frontend/src/pages/servers/`.
- `frontend/src/pages/AgentConfigPage.tsx` is reduced to 455 lines and removed from legacy baselines; core form settings, tool access, MCP, skills, server scope, and visibility sections plus agent option/card rendering live under `frontend/src/pages/agent-config/`.
- `frontend/src/pages/AgentsPage.tsx` is reduced to 291 lines and removed from legacy baselines; create/edit wizard orchestration lives in `frontend/src/pages/agents-page/CreateAgentDialog.tsx`, while wizard helpers, progress, step content, materials editor, and quick summary live under `frontend/src/pages/agents-page/`.
- `frontend/src/pages/AgentRunPage.tsx` is reduced to 430 lines and removed from legacy baselines; pipeline view, flow-node primitives, task-edit modal, timeline, report, status badge, formatters, and page-local types live under `frontend/src/pages/agent-run/`.
- `frontend/src/pages/StudioPage.tsx` is reduced to 410 lines and removed from legacy baselines; pipeline card rendering, create-pipeline dialog, manual-trigger dialog, trigger-info dialog, and delete confirmation dialog live under `frontend/src/pages/studio-page/`.
- `frontend/src/pages/TerminalPage.tsx` is reduced to 482 lines and removed from legacy baselines; tab/session model helpers, terminal WebSocket event projection, AI action handlers, query state, header, and terminal workspace rendering live under `frontend/src/pages/terminal-page/`.
- `frontend/src/components/terminal/AiPanel.tsx` is reduced to 380 lines and removed from legacy baselines; AI message rendering, Nova/agent timeline message rendering, sticky todo rendering, and settings-dialog rendering live under `frontend/src/components/terminal/ai-panel/`.
- `frontend/src/components/terminal/LinuxUiSystemSettings.tsx` is reduced to 220 lines and removed from legacy baselines; settings parsing/search/copy helpers, shared output primitives, search-result rendering, and section rendering live under `frontend/src/components/terminal/linux-ui-settings/`.
- `frontend/src/components/terminal/LinuxUiTextEditor.tsx` is reduced to 79 lines and removed from legacy baselines; tab/recent-file/language-hint helpers, open/save/reload controller state, and layout rendering live under `frontend/src/components/terminal/linux-ui-text-editor/`.
- `frontend/src/components/ui/sidebar.tsx` is reduced to a 29-line compatibility barrel and removed from legacy baselines; provider/context, layout primitives, group primitives, and menu primitives live under `frontend/src/components/ui/sidebar/`.
- `frontend/src/pages/Servers.test.tsx` is reduced to 201 lines and removed from legacy baselines; shared render helpers, fixtures, and API mock setup live in `frontend/src/pages/servers/serversPageTestHarness.tsx`.
- `frontend/src/pages/PipelineEditorPage.test.tsx` is reduced to 312 lines and removed from legacy baselines; pipeline editor fixtures, render helpers, and default API mock setup live in `frontend/src/pages/pipeline-editor/pipelineEditorPageTestHarness.tsx`.
- `frontend/src/pages/StudioSkillsPage.tsx` is reduced to 497 lines and removed from legacy baselines; skill scaffold/payload helpers, reusable skill cards/markdown/validation summary, catalog/detail views, workspace/settings tabs, and create-file/create-skill/validation dialogs live under `frontend/src/pages/studio-skills/`.
- `frontend/src/pages/settings/SettingsAIPage.tsx` is reduced to 76 lines and removed from legacy baselines; the standalone AI settings route now reuses shared `AiSettingsPanel` and `useAiSettingsForm`, keeping provider/model/key behavior in one frontend extension point.
- `frontend/src/pages/SettingsPage.tsx` is reduced to 425 lines and removed from legacy baselines; extracted settings constants, provider selector, section card, AI settings form/panels, memory settings panel, memory card leaf components, access navigation, logging controls, activity log table, and memory overview panels live under `frontend/src/pages/settings-page/`.
- `frontend/src/components/terminal/LinuxUiPanel.tsx` is reduced to 431 lines and removed from legacy baselines; overview, processes, workspace chrome/apps, services, logs, disk, network, Docker, package-manager UI, and shared summary cards live under `frontend/src/components/terminal/linux-ui/`, and the inactive desktop/window-shell model has been removed from the active panel.
- `servers/services/terminal_ai/prompts.py` is reduced to 469 lines and removed from legacy baselines; prompt sanitisation is isolated in `servers/services/terminal_ai/prompt_safety.py`, and report/output-explain/memory-extraction prompt builders live in `servers/services/terminal_ai/prompt_reporting.py`.
- `studio/all_nodes_smoke.py` is reduced to 97 lines and removed from legacy baselines; smoke entry/collector graph composition lives in `studio/all_nodes_smoke_flow.py`, while branch/probe node definitions live in `studio/all_nodes_smoke_branches.py`.
- `web_ui/settings/base.py` is reduced to 206 lines and removed from legacy baselines; security/origins, channel/database, auth/LDAP, runtime/LLM/MARS/CLI, Celery, and env parsing now live in focused `web_ui/settings/` modules.
- `scripts/check_architecture_sizes.py` is reduced to a 78-line CLI facade and removed from legacy baselines; architecture guard config/models, size validation, project scanning, import-boundary checks, baseline writing, and report formatting live in focused `scripts/architecture_guard_*.py` modules.
- `studio/demo_showcase.py` is reduced to a 131-line facade and removed from legacy baselines; incident/content/detective showcase graph definitions live in focused `studio/demo_showcase_*.py` modules, and focused tests now cover demo graph validation plus seed creation. The incident demo graph also now routes rejected/timeout approval branches through an explicit merge node.
- `studio/models.py` is reduced to 496 lines and removed from legacy baselines; ORM classes remain in `studio.models`, while model serialization, pipeline trigger synchronization, pipeline-template instantiation, and monitoring-filter normalization live in focused helper/service modules.
- `studio/docker_service_recovery.py` is reduced to an 89-line facade and removed from legacy baselines; command builders, graph assembly, pre-approval nodes, and recovery-loop nodes live in focused `studio/docker_service_recovery_*.py` modules, with the existing monitoring-trigger test suite covering graph validation and runtime trigger launch behavior.
- The current strict architecture size guard is green; large compatibility entry points should continue to shrink when adjacent work touches them.

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

Current state:

- `SettingsMemoryPage.tsx` is now a thin route/controller and delegates the memory panel layout, overview sections, snapshot cards/actions, and worker-state rendering to focused `frontend/src/pages/settings-memory/` modules.

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
| Pipeline node registry dispatch | Done for current executable node types. `_execute_node` dispatches registered handlers from `studio/executor/nodes/`; both target and production paths fail unregistered node types instead of skipping them. |
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
| Frontend API extraction | Done for this slice. Auth/session API lives in `frontend/src/api/auth.ts`; settings/access/model/activity API lives in `frontend/src/api/settings.ts`; server inventory/share/group/bootstrap API lives in `frontend/src/api/servers.ts`; Studio pipeline/run/agent/skill/MCP/trigger/template API lives in `frontend/src/api/studio.ts`; Studio DTO contracts live in `frontend/src/api/studio-types.ts`; Linux UI API calls/types live in `frontend/src/api/linux-ui.ts` and `frontend/src/api/linux-ui-types.ts`; SFTP/server-file API calls/types live in `frontend/src/api/server-files.ts`; MARS API calls/types live in `frontend/src/api/mars.ts`; server-memory API calls/types live in `frontend/src/api/server-memory.ts`; monitoring/admin dashboard API lives in `frontend/src/api/monitoring.ts`; agents/runs/schedules API lives in `frontend/src/api/agents.ts`; access feature metadata lives in `frontend/src/lib/access-features.ts`; demo/offline fallback routing and data live in split `frontend/src/lib/api-demo-*.ts` modules; `frontend/src/lib/api.ts` is below the standard size limit and no longer pinned. |
| Agent run page split | Done for this slice. `frontend/src/pages/AgentRunPage.tsx` is below the standard size limit and no longer pinned; run orchestration stays in the page container while pipeline, flow-node primitives, task editing, timeline, report, status badge, formatters, and local types live under `frontend/src/pages/agent-run/`. |
| Terminal page split | Done for this slice. `frontend/src/pages/TerminalPage.tsx` is below the standard size limit and no longer pinned; tab/session helpers live in `terminal-page/model.ts`, terminal WebSocket/AI event projection lives in `terminal-page/ws-events.ts`, AI send/confirm/reply/report/default actions live in `terminal-page/useTerminalAiActions.ts`, and the query/header/workspace rendering lives in focused `terminal-page/` components. |
| Servers page workflow extraction | Done for this slice. `frontend/src/pages/Servers.tsx` is below the standard size limit and no longer pinned; `frontend/src/pages/servers/useServerCrudController.ts` owns server create/edit/delete/test dialog state and mutations; `frontend/src/pages/servers/useServerGroupController.ts` owns server-group dialog state and mutations; `frontend/src/pages/servers/ServerFormDialog.tsx` owns the server create/edit dialog rendering; `frontend/src/pages/servers/useServersListController.ts` owns search, grouping, collapsed groups, selection, and online count; `frontend/src/pages/servers/useServerSharesController.ts` owns advanced-dialog share state and create/revoke/refresh operations; `frontend/src/pages/servers/ServerAdvancedDialog.tsx` owns the advanced-dialog shell and tab composition; `frontend/src/pages/servers/ServerAccessTab.tsx` owns access-tab rendering; `frontend/src/pages/servers/useServerKnowledgeController.ts` owns manual/AI knowledge state, filters, dialogs, CRUD, bulk delete, and purge operations; `frontend/src/pages/servers/ServerKnowledgeTab.tsx` owns knowledge-tab rendering; `frontend/src/pages/servers/ServerKnowledgeDialogs.tsx` owns manual/AI knowledge edit dialogs; `frontend/src/pages/servers/useServerRulesController.ts` owns global/group/server rules state, effective previews, context loading, server override saves, and group-member operations; `frontend/src/pages/servers/ServerRulesTab.tsx` owns main rules-tab rendering; `frontend/src/pages/servers/ServerContextTab.tsx` owns context-tab rendering; `frontend/src/pages/servers/useServerSecurityController.ts` owns master-password status/save/clear/reveal; `frontend/src/pages/servers/ServerSecurityTab.tsx` owns security-tab rendering; `frontend/src/pages/servers/useServerCommandController.ts` owns advanced execute-tab command state/result; `frontend/src/pages/servers/ServerExecuteTab.tsx` owns execute-tab rendering. |
| Terminal AI run lifecycle split | Done for this slice. `servers/services/terminal_ai/run_controller.py` owns the terminal-AI asyncio lock, active task, reply futures, and shared ask-user send/wait/cleanup flow; `SSHTerminalConsumer` keeps WebSocket/SSH behavior but delegates task start/cancel/current-task cleanup, active-task checks, reply creation, reply resolution, reply-future cleanup, and repeated `ai_question` waiting. |
| Terminal AI active-command state split | Done for this slice. `servers/services/terminal_ai/active_command.py` owns active PTY command id/output/future state and cleanup; `SSHTerminalConsumer` keeps PTY command execution orchestration but delegates registration, interrupt lookup, future resolution, output-tail reads, and cancel/clear handling. |
| Terminal AI PTY command runtime split | Done for this slice. `servers/services/terminal_ai/pty_command.py` owns marker-future waiting, streaming timeout fallback, install-progress event construction/emission, install-error interrupt callbacks, helper-task cleanup, and output-tail return; `SSHTerminalConsumer` keeps command normalization and PTY write/marker injection. |
| Terminal AI recovery helper split | Done for this slice. `servers/services/terminal_ai/recovery.py` owns recovery-attempt gating, action normalization, retry-candidate projection, recovery text defaults, retry-item insertion/event emission, fast-mode recovery orchestration, and step-mode post-command orchestration; `SSHTerminalConsumer` keeps command execution and queue loop transport. |
| Terminal AI queue-completion split | Done for this slice. `servers/services/terminal_ai/queue_completion.py` owns final done-item snapshotting, auto-report generation, report/history side effects, memory candidate projection, and memory-extraction task spawning; `SSHTerminalConsumer` delegates the post-queue completion flow after the queue becomes idle. |
| Terminal AI queue state split | Done for this slice. `servers/services/terminal_ai/session.py` owns initial plan installation, per-run id allocation, retry/adaptive insertion positions, parallel-batch snapshot/cursor advancement, next-command preparation, blocked-command skip, waiting-confirm setup, current-command completion, explicit parallel-batch plan-index completion, goal-achieved skip-remaining transitions, remaining-command projections, and done-item report/memory projections; `servers/services/terminal_ai/plan_insertions.py` owns retry/adaptive item reservation; `SSHTerminalConsumer` keeps WebSocket transport and SSH command execution. |
| Terminal AI legacy bridge split | Done for this slice. `servers/services/terminal_ai/legacy_state.py` owns sync/apply between historical consumer `_ai_*` attributes and `TerminalAiSession`; legacy bridge tests live in `tests/test_terminal_ai_legacy_state.py`. |
| Terminal AI report formatting split | Done for this slice. `servers/services/terminal_ai/reporter.py` owns dry-run report labeling and compact execution-summary formatting; `SSHTerminalConsumer` keeps report generation orchestration and event emission. |
| Terminal AI command outcome split | Done for this slice. `servers/services/terminal_ai/command_outcome.py` owns exit-127 unavailable-command extraction; `SSHTerminalConsumer` keeps command execution and event emission. |
| Terminal AI event payload split | Done for this slice. `servers/services/terminal_events.py` owns common `ai_*` payload shapes used by the consumer, including status, error, response, command status, direct output, report, recovery, question, and parallel-batch events. |
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
