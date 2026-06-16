# Studio Pipeline Nodes: полный справочник

Last reviewed: 2026-05-28

Этот файл описывает реальные node types Studio Pipeline в текущем `C:\WebTrerm`: что делает каждая нода, какие поля читает UI/runtime, как она роутит граф, какие ошибки даёт и какие есть фишки/ограничения.

## Источники правды

- Backend graph contract: `studio/pipeline_validation.py`
- Production runtime: `studio/pipeline_executor.py`
- Pipeline/trigger/run storage: `studio/models.py`
- Trigger launchers: `studio/views/pipeline_views.py`, `studio/views/trigger_views.py`, `studio/trigger_dispatch.py`, `studio/management/commands/run_scheduled_pipelines.py`
- Run controls and approval endpoint: `studio/views/run_views.py`
- Frontend palette and editor forms: `frontend/src/pages/PipelineEditorPage.tsx`
- Frontend node metadata and labels: `frontend/src/components/pipeline/nodes/nodeMeta.tsx`, `frontend/src/components/pipeline/nodes/index.ts`
- Node manifest metadata + input/output schemas: `studio/node_manifest.py`
- Node manifest API: `GET /api/studio/node-manifests/`
- Capability/task-family registry: `studio/capability_registry.py`, `studio/views/capability_views.py`
- Pilot capability pack/tool schemas: `studio/pilot_capability_packs.py`
- AI drafter catalog/aliases: `studio/services/pipeline_assistant.py`, `studio/services/pipeline_assistant_prompt.py`
- AI drafter pilot template selector: `studio/services/pipeline_template_recommendations.py`
- Target node-registry architecture: `studio/executor/`
- Smoke/tests: `tests/test_studio_node_executors.py`, `tests/test_studio_all_nodes_smoke.py`, `tests/test_studio_pipeline_v2.py`
- Manifest + registry/schema consistency verifier: `python manage.py check_node_manifest_consistency`

## Инвентарь нод

В текущем контракте 30 встроенных типов.

| Type | Категория | UI component | Production runtime | Выходные handles |
| --- | --- | --- | --- | --- |
| `trigger/manual` | Trigger | `TriggerNode` | entry-only, запускается API/UI | `out` |
| `trigger/webhook` | Trigger | `TriggerNode` | public webhook endpoint | `out` |
| `trigger/schedule` | Trigger | `TriggerNode` | scheduler command | `out` |
| `trigger/monitoring` | Trigger | `TriggerNode` | monitoring alert dispatcher | `out` |
| `agent/react` | Agent | `AgentNode` | registry adapter -> `AgentReactNode` over ReAct runtime | `success`, `error`, `out` |
| `agent/multi` | Agent | `AgentNode` | registry adapter -> `AgentMultiNode` over multi-agent runtime | `success`, `error`, `out` |
| `agent/ssh_cmd` | Agent | `SSHCommandNode` | registry adapter -> `AgentSSHCommandNode` over SSH runtime | `success`, `error`, `out` |
| `agent/llm_query` | Agent | `LLMQueryNode` | registry adapter -> `AgentLLMQueryNode` over LLM runtime | `success`, `error`, `out` |
| `agent/mcp_call` | Agent | `MCPCallNode` | registry adapter -> `AgentMCPCallNode` over MCP runtime | `success`, `error`, `out` |
| `ops/server_snapshot` | Ops | `OutputNode` | registry adapter -> `OpsServerSnapshotNode` | `success`, `error`, `out` |
| `ops/log_query` | Ops | `OutputNode` | registry adapter -> `OpsLogQueryNode` | `success`, `error`, `out` |
| `ops/file_action` | Ops | `OutputNode` | registry adapter -> `OpsFileActionNode` | `success`, `error`, `out` |
| `ops/package_action` | Ops | `OutputNode` | registry adapter -> `OpsPackageActionNode` | `success`, `error`, `out` |
| `ops/disk_cleanup` | Ops | `OutputNode` | registry adapter -> `OpsDiskCleanupNode` | `success`, `error`, `out` |
| `ops/backup_restore_check` | Ops | `OutputNode` | registry adapter -> `OpsBackupRestoreCheckNode` | `success`, `error`, `out` |
| `ops/service_action` | Ops | `OutputNode` | registry adapter -> `OpsServiceActionNode` | `success`, `error`, `out` |
| `ops/docker_action` | Ops | `OutputNode` | registry adapter -> `OpsDockerActionNode` | `success`, `error`, `out` |
| `ops/process_action` | Ops | `OutputNode` | registry adapter -> `OpsProcessActionNode` | `success`, `error`, `out` |
| `ops/http_check` | Ops | `OutputNode` | registry adapter -> `OpsHttpCheckNode` | `success`, `error`, `out` |
| `ops/alert_update` | Ops | `OutputNode` | registry adapter -> `OpsAlertUpdateNode` | `success`, `error`, `out` |
| `logic/condition` | Logic | `ConditionNode` | registry adapter -> `LogicConditionNode` | `true`, `false` |
| `logic/parallel` | Logic | `ParallelNode` | registry adapter -> `LogicParallelNode` plus executor batch routing | `out` |
| `logic/merge` | Logic | `MergeNode` | registry adapter -> `LogicMergeNode` plus router merge state | `out` |
| `logic/wait` | Logic | `WaitNode` | registry adapter -> `LogicWaitNode` | `done`, `out` |
| `logic/human_approval` | Logic | `HumanApprovalNode` | registry adapter -> `LogicHumanApprovalNode` over approval runtime | `approved`, `rejected`, `timeout` |
| `logic/telegram_input` | Logic | `TelegramInputNode` | registry adapter -> `LogicTelegramInputNode` over polling runtime | `received`, `timeout` |
| `output/report` | Output | `OutputNode` | registry adapter -> `OutputReportNode` | `success`, `error`, `out` |
| `output/webhook` | Output | `OutputNode` | registry adapter -> `OutputWebhookNode` | `success`, `error`, `out` |
| `output/email` | Output | `EmailNode` | registry adapter -> `OutputEmailNode` | `success`, `error`, `out` |
| `output/telegram` | Output | `TelegramNode` | registry adapter -> `OutputTelegramNode` | `success`, `error`, `out` |

## Общий graph contract

- Текущая версия графа: `2` (`CURRENT_PIPELINE_GRAPH_VERSION`).
- `Pipeline.nodes` и `Pipeline.edges` хранят React Flow compatible JSON.
- Сохранение/обновление pipeline всегда гоняет `validate_pipeline_definition(...)`.
- При сохранении `Pipeline.sync_triggers_from_nodes()` синхронизирует trigger-ноды в таблицу `PipelineTrigger`.
- В графе должен быть минимум один `trigger/*`.
- Trigger-ноды являются entry point и не могут иметь входящие edges.
- Любая нода кроме `logic/merge` может иметь максимум один входящий edge.
- `logic/merge` нужен для явного join веток и должен иметь минимум один входящий edge.
- Циклы запрещены.
- Ноды, недостижимые от любого trigger, запрещены.
- `sourceHandle` edge должен соответствовать типу source-ноды.
- Manual run дополнительно требует хотя бы один активный `trigger/manual`.
- Если в pipeline несколько активных manual triggers, run API/UI должен передать `entry_node_id`.
- Runtime запускает только ветку выбранного entry trigger. Другие trigger-ветки этого run не стартуют.

## Run lifecycle и routing

`PipelineRun` хранит snapshot графа на момент запуска:

- `nodes_snapshot`
- `edges_snapshot`
- `entry_node_id`
- `context`
- `trigger_data`
- `node_states`
- `routing_state`
- `summary`
- `error`

Run statuses:

- `pending`
- `running`
- `completed`
- `failed`
- `stopped`
- `hibernating`

Node state обычно содержит:

- `status`
- `output`
- `error`
- `started_at`
- `finished_at`
- `routing_ports`
- дополнительные поля конкретной ноды, например `agent_run_id`, `approval_token`, `decision`, `exit_code`

Routing rules:

- `logic/condition`: `passed=true` -> `true`, иначе `false`.
- `logic/human_approval`: `decision` -> `approved`, `rejected` или `timeout`.
- `logic/telegram_input`: `decision` -> `received` или `timeout`.
- `logic/wait`: при `completed` открывает `done` и `out`.
- `logic/parallel` и `logic/merge`: при завершении открывают `out`.
- `agent/*`, `ops/*` и `output/*`: при `completed` открывают `success` и `out`, при `failed` открывают `error`.
- `stopped` не открывает downstream handles.
- `skipped` сейчас не открывает downstream handles для `agent/*`/`output/*`.

`on_failure`:

- Проверяется только для `agent/*` и `output/*`.
- Если нода вернула `failed` и `on_failure="abort"`, весь run падает.
- Если `on_failure="continue"` или поле пустое, runtime идёт через `error` handle.
- Logic-ноды не abort-ят pipeline через `on_failure`; например rejected approval может идти в ветку `rejected`.
- UI по умолчанию ставит `on_failure="abort"` для `agent/react`, `agent/multi`, `agent/llm_query`, `agent/mcp_call`. Для `ops/*` и остальных типов backend default фактически `continue`, если поле не задано.

## Context и шаблоны

Перед выполнением каждой ноды runtime обогащает context:

| Variable | Значение |
| --- | --- |
| `{pipeline_name}` | имя pipeline |
| `{run_id}` | id текущего `PipelineRun` |
| `{entry_node_id}` | выбранный trigger node id |
| `{trigger_type}` | тип trigger из `PipelineTrigger` |
| `{trigger_name}` | имя trigger |
| `{node_id}` | output предыдущей ноды с таким id |
| `{node_id_output}` | output предыдущей ноды |
| `{node_id_error}` | error предыдущей ноды |
| `{node_id_status}` | status предыдущей ноды |
| `{all_outputs}` | агрегат предыдущих output, если нода его поддерживает |

Важно:

- Основной renderer `_render_template_value` заменяет только простые `{name}`. Неизвестные переменные становятся пустой строкой.
- Часть старых email/telegram мест использует `format_map`; там неизвестный placeholder может оставить шаблон как есть.
- JSON/prompt поля можно шаблонизировать, если executor конкретной ноды прогоняет их через renderer.
- Webhook trigger может превратить входящий JSON payload в context через `webhook_payload_map`.
- Monitoring trigger создаёт context из `ServerAlertSnapshot`.

## Общие validation errors

Структура:

- `Pipeline nodes must be a list.`
- `Pipeline edges must be a list.`
- `Pipeline graph_version must be an integer.`
- `Pipeline graph_version=<n> is not supported. Resave or recreate the pipeline as V2.`
- `Node #<n> must be an object.`
- `Node #<n> is missing an id.`
- `Duplicate node id '<id>'.`
- `Node '<id>' uses an unknown type '<type>'.`
- `Node '<id>' position must be an object.`
- `Node '<id>' data must be an object.`
- `Edge #<n> must be an object.`
- `Duplicate edge id '<id>'.`
- `Edge #<n> must define both source and target.`
- `Edge #<n> references missing source node '<id>'.`
- `Edge #<n> references missing target node '<id>'.`
- `Pipeline graph contains a cycle or unreachable loop involving: ...`
- `Pipeline must include at least one trigger node.`
- `Manual runs require at least one active manual trigger node.`
- `Trigger node '<id>' must be a graph entry point and cannot have incoming edges.`
- `Merge node '<id>' requires at least one incoming edge.`
- `Node '<id>' has <n> incoming edges. Use an explicit merge node for branch joins.`
- `Edge '<id>' uses sourceHandle '<handle>' which is invalid for node '<id>' (<type>). Allowed: ...`
- `Nodes are unreachable from every trigger: ...`

Data/reference validation:

- `webhook_payload_map_text` and `arguments_text` must be valid JSON object text.
- `webhook_payload_map` must be a JSON object.
- `cron_expression` must be valid 5-field cron. If `croniter` is installed, it is used; otherwise Studio uses its local 5-field parser for validation and scheduler runtime.
- `server_ids`, `severities`, `alert_types`, `container_names` must have the expected type.
- Agent server ids must belong to the pipeline owner.
- `agent_config_id` must be an accessible `AgentConfig`.
- MCP is admin/staff-only in validation.
- `mcp_server_ids` and `mcp_server_id` must belong to the owner.
- `skill_slugs` are normalized and resolved; skill errors are appended to validation errors.

## Trigger nodes

### `trigger/manual`

Назначение: запуск pipeline вручную из Studio UI или через API.

Runtime:

- Создаёт `PipelineTrigger` с `trigger_type="manual"` при сохранении pipeline.
- Запускается через `POST /api/studio/pipelines/<pipeline_id>/run/`.
- Run получает `trigger_data.source="manual"` и `entry_node_id` выбранного manual trigger.
- Если активный manual trigger один, он выбирается автоматически.
- Если активных manual triggers несколько, нужен `entry_node_id`.

Поля:

- `label`: UI-имя.
- `is_active`: включает/выключает ручной запуск, default `true`.

Ошибки:

- `Pipeline has no active manual trigger nodes.`
- `Manual trigger '<id>' was not found. Available manual triggers: ...`
- `Pipeline has multiple manual triggers. Provide entry_node_id. Available manual triggers: ...`
- Общие graph errors: входящие edges запрещены, handle только `out`.

Фишки:

- Можно держать несколько manual entry points в одном графе и запускать разные ветки одного pipeline.
- Context можно передать в body manual run: `{ "context": { ... } }`.
- Перед фактическим запуском можно вызвать тот же endpoint с `{"validate_only": true}` или `{"dry_run": true}`. Backend проверяет graph contract, manual trigger routing, references и policy/risk review, возвращает `validation`, `risk`, `dry_run.executed=false`, `would_create_run=false` и не создаёт `PipelineRun` / не вызывает launcher.

### `trigger/webhook`

Назначение: публичный HTTP POST entry point для внешних систем.

Runtime:

- Создаёт `PipelineTrigger` с `trigger_type="webhook"` и `webhook_token`.
- Endpoint: `POST /api/studio/triggers/<webhook_token>/receive/`.
- Endpoint публичный и аутентифицируется токеном в URL.
- Body должен быть JSON object. Пустой body превращается в `{}`.
- Перед запуском pipeline снова валидируется.
- Context строится через `webhook_payload_map`.
- `last_triggered_at` обновляется после создания run.

Поля:

- `label`
- `is_active`
- `webhook_payload_map`: object вида `{ "context_key": "payload.path" }`.
- `webhook_payload_map_text`: editor-only JSON text, валидируется и синхронизируется в object.

Пример mapping:

```json
{
  "branch": "ref",
  "commit": "head_commit.id"
}
```

Ошибки:

- `Invalid token` при неактивном/неверном webhook token.
- `Webhook payload must be valid JSON`.
- `Webhook payload must be a JSON object`.
- `Pipeline is not runnable: ...` при validation errors.
- Run limit возвращает HTTP 429.
- `webhook_payload_map_text` invalid JSON ломает сохранение pipeline.

Фишки:

- Если mapping пустой, весь payload становится context.
- Dot-path поддерживает вложенные dict-поля.
- Webhook trigger запускает только свою ветку, даже если в графе есть другие triggers.

### `trigger/schedule`

Назначение: автоматический запуск по cron.

Runtime:

- Создаёт `PipelineTrigger` с `trigger_type="schedule"`.
- Запускается management command:

```powershell
python manage.py run_scheduled_pipelines --daemon
python manage.py run_scheduled_pipelines --once
```

- Scheduler использует `croniter`, если он установлен. Без `croniter` включается local fallback parser для стандартного 5-field cron: `*`, `*/n`, числа, ranges и comma lists.
- Если `last_triggered_at` пустой, trigger срабатывает, если last due попал в polling window.
- `trigger_data` содержит `source="schedule"` и `cron`.
- Context по умолчанию пустой.

Поля:

- `label`
- `is_active`
- `cron_expression`: 5-field cron, default UI `*/5 * * * *`.

Ошибки:

- Invalid cron на сохранении pipeline.
- Если cron expression invalid, scheduler пишет ошибку оценки конкретного trigger и не запускает его.
- Empty `cron_expression` просто пропускается scheduler-ом.

Фишки:

- UI даёт presets, minute interval и daily time, но сохраняет всё как 5-field cron.
- `last_triggered_at` защищает от повторного запуска одного и того же due time.

### `trigger/monitoring`

Назначение: запуск pipeline при новом open alert из server monitoring.

Runtime:

- Создаёт `PipelineTrigger` с `trigger_type="monitoring"`.
- Запускается через `launch_monitoring_triggers_for_alert(...)`.
- Matching работает только по alerts серверов владельца pipeline.
- Resolved alerts не запускают pipeline.
- Перед запуском pipeline валидируется.
- Run получает monitoring context.

Поля:

- `label`
- `is_active`
- `monitoring_filters`
- `server_ids`
- `severities`
- `alert_types`
- `container_names`
- `match_text`

Context:

- `alert_id`
- `alert_type`
- `alert_severity`
- `alert_title`
- `alert_message`
- `alert_metadata`
- `server_id`
- `server_name`
- `server_host`
- `server_username`
- `container_name`
- `container_names`
- `container_names_csv`
- `trigger_source="monitoring"`

Ошибки:

- Inaccessible `server_ids` ломают validation.
- `severities`, `alert_types`, `container_names` должны быть списками непустых строк.
- Если pipeline validation падает или run limit превышен, dispatcher silently skips trigger.

Фишки:

- Empty filters означают "любой open alert владельца".
- `match_text` ищет подстроку в title, message и JSON metadata.
- Docker container match проверяет `metadata.containers[].name` и `metadata.container_name`.

## Agent nodes

### `agent/react`

Назначение: ReAct-агент, который рассуждает и выбирает инструменты во время выполнения.

Runtime:

- Выполняется через registry adapter `studio/executor/nodes/agent_react.py`, подключенный из production `PipelineExecutor`.
- Adapter сохраняет существующую ReAct runtime semantics: AgentConfig/server/MCP/skill resolution, event callback, provider/model resolution и final report mapping остаются в production ReAct runtime.
- Вызывает `run_pipeline_react_agent(...)`.
- Может использовать серверы, MCP servers, Studio skills и сохранённый `AgentConfig`.
- `goal`, `system_prompt`, `instructions` шаблонизируются context-переменными.
- События агента отправляются в websocket group `pipeline_run_<run_id>`.
- Возвращает `agent_run_id`, `output=final_report`, `error=ai_analysis` если agent run не completed.

Поля:

- `label`
- `goal`
- `agent_config_id`
- `server_ids`
- `mcp_server_ids`
- `skill_slugs`
- `provider`
- `model`
- `max_iterations`
- `system_prompt`
- `instructions`
- `allowed_tools`
- `on_failure`

AgentConfig behavior:

- Если `agent_config_id` задан, prompt/model/tools/MCP/server scope берутся из `AgentConfig`.
- Node-level `skill_slugs` объединяются со skills из AgentConfig.
- Если у AgentConfig есть `server_scope`, node не может выбрать сервер вне scope.

Ошибки:

- `Invalid agent config id: ...`
- `Agent config not found: ...`
- `Node references servers outside agent scope: [...]`
- `Servers not found: [...]`
- `Configure at least one server, one MCP server, or one skill for this agent node`
- Validation errors по server/MCP/skill access.

Фишки:

- Можно запустить агента без сервера, если есть MCP server или skill.
- MCP доступ admin/staff-only.
- UI default `max_iterations=6`, backend fallback без поля: `10`.

### `agent/multi`

Назначение: multi-agent/multi-server orchestration.

Runtime:

- Выполняется через registry adapter `studio/executor/nodes/agent_multi.py`, подключенный из production `PipelineExecutor`.
- Adapter сохраняет существующую multi-agent runtime semantics: AgentConfig/server/MCP/skill resolution, event callback, provider/model resolution и final report mapping остаются в production multi-agent runtime.
- Вызывает `run_pipeline_multi_agent(...)`.
- Логика выбора AgentConfig, servers, MCP и skills почти такая же, как у `agent/react`.
- Возвращает `agent_run_id`, `output=final_report`, `error=ai_analysis` если run не completed.

Поля:

- `label`
- `goal`
- `agent_config_id`
- `server_ids`
- `mcp_server_ids`
- `skill_slugs`
- `provider`
- `model`
- `max_iterations`
- `system_prompt`
- `allowed_tools`
- `on_failure`

Ошибки:

- `Invalid agent config id: ...`
- `Agent config not found: ...`
- `Node references servers outside agent scope: [...]`
- `Servers not found: [...]`
- `Configure at least one server, one MCP server, or one skill for this multi agent node`
- Validation errors по server/MCP/skill access.

Фишки:

- Подходит для сравнения нескольких серверов/целей.
- UI default `max_iterations=6`, backend fallback без поля: `20`.

### `agent/ssh_cmd`

Назначение: прямое выполнение одной SSH-команды без LLM-планирования.

Runtime:

- Выполняется через registry adapter `studio/executor/nodes/agent_ssh_cmd.py`, подключенный из production `PipelineExecutor`.
- Adapter сохраняет существующую SSH runtime semantics: direct command path, permission/sandbox/hook checks, preflight/verification, command history и fallback в ReAct при пустой команде с agent config/goal остаются в production SSH runtime.
- Использует `asyncssh.connect(...)`.
- Берёт SSH параметры через `get_server_connect_kwargs(server, connect_timeout=30)`.
- Прогоняет command через `PermissionEngine`, `SandboxManager`, `HookManager`.
- Пишет command history и user activity.
- `command` форматируется через Python `.format(**context)`.
- `preflight_commands` и `verification_commands` прогоняются через `_render_template_value`.

Поля:

- `label`
- `server_id`
- `command`
- `preflight_commands`: список команд; UI показывает advanced textarea "Preflight команды", одна команда на строку.
- `verification_commands`: список команд; UI показывает advanced textarea "Verification команды", одна команда на строку.
- `permission_mode`: `PLAN`, `SAFE`, `ASSISTED`, `AUTONOMOUS`, `AUTO_GUARDED`; default `SAFE`.
- `on_failure`

Ошибки:

- Если `server_id` пустой, node возвращает `failed` с текстом "No server configured...".
- Если `command` пустой, но есть `agent_config_id` или `goal`, runtime пытается делегировать в `agent/react`.
- Если `command` пустой без agent fallback: `Команда не задана...`
- `Server not found: <id>`.
- Permission denial возвращает reason из `PermissionEngine`.
- Preflight non-zero: `Preflight command failed: <cmd>`.
- Verification non-zero: `Verification command failed: <cmd>`.
- SSH exception возвращается с server detail: `<exc> (server: <name> [<user>@<host>])`.

Фишки:

- Preflight может разрешить сначала выполнить read-only проверки, а затем заново проверить основную команду.
- Output собирается секциями `## preflight`, `## command`, `## verification`, `## verification_summary`.
- `skipped` сейчас не открывает downstream `success/out`, поэтому отсутствие server может оборвать ветку без error routing.

### `agent/llm_query`

Назначение: прямой запрос к LLM без автономных инструментов и SSH.

Runtime:

- Выполняется через registry adapter `studio/executor/nodes/agent_llm_query.py`, подключенный из production `PipelineExecutor`.
- Adapter сохраняет существующую LLM runtime semantics: prompt rendering, previous outputs context, server memory, operational recipes, provider/model resolution, streaming и error handling остаются в production LLM runtime.
- Требует `prompt`.
- Собирает compact context предыдущих node outputs.
- Подмешивает server memory и operational recipes, если есть выбранные servers/context.
- Стримит ответ через `LLMProvider.stream_chat(...)`.
- Ответ compact-ится до 6000 символов.
- Если ответ начинается с `Error:`, node считается failed.

Поля:

- `label`
- `prompt`
- `system_prompt`, default `You are a helpful DevOps assistant.`
- `provider`, default `gemini`
- `model`
- `include_all_outputs`, default `true`
- `purpose`, default `opssummary`
- `permission_mode`, default `SAFE`
- `role`
- `watcher`
- `server_ids`
- `server_id`
- `max_context_nodes`, clamp `1..12`, default `6`
- `max_output_chars`, clamp `200..4000`, default `1200`
- `on_failure`

Ошибки:

- `No prompt configured for llm_query node`.
- Provider/model exceptions возвращаются как `failed`.
- LLM text starting with `Error:` превращается в failed state.

Фишки:

- `{all_outputs}` можно вставить вручную. Если prompt не содержит `{all_outputs}`, но `include_all_outputs=true`, runtime всё равно добавит предыдущие outputs отдельным блоком.
- Поддерживает ops context: role, permission mode, server memory, operational recipes.

### `agent/mcp_call`

Назначение: прямой вызов конкретного MCP tool с JSON arguments.

Runtime:

- Выполняется через registry adapter `studio/executor/nodes/agent_mcp_call.py`, подключенный из production `PipelineExecutor`.
- Adapter сохраняет существующую MCP runtime semantics: server/tool lookup, argument rendering, skill policies, permission/sandbox/hook managers, activity log, result normalization и executed-tool tracking остаются в production MCP runtime.
- MCP server выбирается по `mcp_server_id` владельца pipeline.
- Tool выбирается строго по `tool_name`.
- Arguments берутся из `arguments_text` или `arguments`.
- Arguments шаблонизируются context-переменными.
- Skill policies могут модифицировать/запретить call.
- Permission/Sandbox/Hook managers применяются перед/после MCP call.
- Result превращается в text: `content[].text`, JSON content, `structuredContent` или raw JSON.
- Activity пишется в audit/activity log.

Поля:

- `label`
- `mcp_server_id`
- `mcp_server_name`
- `tool_name`
- `arguments_text`
- `arguments`
- `skill_slugs`
- `permission_mode`
- `on_failure`

Ошибки:

- `Select an MCP server for this node`.
- `Select an MCP tool for this node`.
- `Invalid MCP arguments JSON: ...`
- `MCP arguments must be a JSON object`.
- `MCP server not found: <id>`.
- `Invalid MCP server id: <id>`.
- `Skill policy validation failed: ...`
- Permission/sandbox policy reason.
- MCP result with `isError` returns failed with tool output as error.
- Exceptions become `failed`.

Фишки:

- UI может inspect-ить MCP tools через `/api/studio/mcp/<id>/tools/`.
- При выборе tool UI может seed-ить JSON template из input schema.
- Editor показывает schema-driven typed arguments поверх JSON, permission mode, risk preview и skill/policy selection для `agent/mcp_call`.
- Skills can enforce tool policies and execution order; executed MCP tools are tracked in current executor.

## OPS nodes

Ноды `ops/*` — первый production-пакет структурированных DevOps/admin операций. Они исполняются через target registry (`studio/executor/nodes/ops.py`) из текущего production executor adapter, поэтому новые типы не раздувают legacy `PipelineExecutor._execute_node` отдельными ветками.

Общие правила:

- Handles: `success`, `error`, `out`.
- Target server: явный `server_id` или context key из `server_id_context_key`, default `server_id`.
- Для mutating действий (`file_action.write`, `package_action.install/update/remove`, `disk_cleanup.journal_vacuum/tmp_cleanup`, `service_action`, `docker_action`, `process_action`, `alert_update`) шаблоны должны ставить `logic/human_approval` перед нодой.
- Runtime использует существующие WebTerm Linux UI collectors/actions и owner access check; недоступный сервер даёт `failed`.

### `ops/server_snapshot`

Назначение: read-only снимок Linux-сервера для диагностики и дальнейшего анализа.

Поля:

- `server_id`
- `server_id_context_key`, default `server_id`
- `sections`: `overview`, `services`, `processes`, `docker`, `logs`, `disk`, `network`, `packages`
- `log_source`, `service`, `lines`, `limit`
- `on_failure`

Runtime:

- Загружает owner-accessible server.
- Собирает выбранные sections через `servers.linux_ui`.
- Возвращает human-readable `output` и structured `snapshot`.

### `ops/log_query`

Назначение: read-only сбор Linux/service/Docker логов как отдельный универсальный diagnostic primitive, чтобы AI drafter не уходил в raw SSH для типовых incident задач.

Поля:

- `server_id` или `server_id_context_key`
- `source`: `journal`, `service`, `docker`, `syslog`, `messages`, `auth`, `nginx_error`, `nginx_access`, `apache_error`, `apache_access`
- `service`: systemd unit для `source=service`
- `container`: Docker container для `source=docker`, поддерживает `{container_name}`
- `lines`, default `120`
- `filter_text`: необязательный case-insensitive filter по строкам
- `on_failure`

Runtime:

- Загружает owner-accessible server.
- Для `source=docker` использует `get_linux_ui_docker_logs(...)`.
- Для остальных источников использует `get_linux_ui_logs(...)`.
- Возвращает human-readable `output` и structured `logs`; при `filter_text` добавляет `match_count` и `matched_lines`.

### `ops/file_action`

Назначение: generic SFTP primitive для чтения/записи UTF-8 config/text files без raw SSH.

Поля:

- `server_id` или `server_id_context_key`
- `action`: `read` или `write`
- `path`
- `content`, `allow_empty_content` для write
- `max_bytes`, clamp `1024..1048576`
- `on_failure`

Runtime:

- `read` возвращает `output` и structured `file.content`.
- `write` пишет через SFTP, возвращает metadata и `content_sha256`, но не возвращает raw content.
- `write` классифицируется policy guard как mutating и требует approved `logic/human_approval`.

### `ops/package_action`

Назначение: generic OS package primitive для read-only update listing и явных install/update/remove действий.

Поля:

- `server_id` или `server_id_context_key`
- `action`: `list_updates`, `install`, `update`, `remove`
- `packages`: явный список пакетов для mutating действий
- `verify`, default `true`
- `on_failure`

Runtime:

- `list_updates` вызывает package collector и возвращает structured `packages`.
- Mutating actions определяют package manager (`apt`, `dnf`, `yum`), выполняют только явный список пакетов и возвращают `package_action`.
- Full system upgrade не поддержан; это осознанное ограничение MVP.

### `ops/disk_cleanup`

Назначение: generic disk maintenance primitive для inspect, journal vacuum и ограниченной очистки старых tmp-файлов без произвольного `rm`.

Поля:

- `server_id` или `server_id_context_key`
- `action`: `inspect`, `journal_vacuum`, `tmp_cleanup`
- `dry_run`, default `false`
- `verify`, default `true`
- `min_age_days`, `max_entries` для `tmp_cleanup`
- `vacuum_time_days`, `vacuum_size_mb` для `journal_vacuum`
- `on_failure`

Runtime:

- `inspect` read-only вызывает `get_linux_ui_disk(...)` и возвращает structured `disk`.
- `journal_vacuum` запускает bounded `journalctl --vacuum-time/--vacuum-size`.
- `tmp_cleanup` работает только с `/tmp` и `/var/tmp`, только для entries старше `min_age_days`, ограниченно `max_entries`.
- Mutating actions возвращают `disk_cleanup`, делают optional post-check и требуют approved `logic/human_approval`.

### `ops/backup_restore_check`

Назначение: read-only primitive для проверки свежести backup directory и integrity latest archive без выполнения restore.

Поля:

- `server_id` или `server_id_context_key`
- `action`: `inspect`, `verify_latest`
- `path`: remote backup directory
- `max_depth`, clamp `1..5`
- `max_files`, clamp `1..100`
- `max_age_hours`, clamp `1..8760`
- `on_failure`

Runtime:

- Находит последние backup-файлы через bounded `find` в указанном каталоге.
- `inspect` возвращает summary: latest path, age, size, freshness относительно `max_age_hours`.
- `verify_latest` дополнительно проверяет latest archive для поддержанных форматов (`tar`, `tar.gz`, `tgz`, `gz`, `zip`).
- Restore не выполняется; для настоящего restore нужен отдельный approved workflow/MCP/tool.

### `ops/service_action`

Назначение: структурированное действие с systemd unit без raw SSH command.

Поля:

- `server_id` или `server_id_context_key`
- `service`
- `action`: `start`, `stop`, `restart`, `reload`
- `verify`, default `true`
- `on_failure`

Runtime:

- Собирает service log/status preflight.
- Выполняет `run_linux_ui_service_action(...)`.
- При `verify=true` снова читает service logs/status.
- `success=false` превращается в `failed` и открывает `error`.

### `ops/docker_action`

Назначение: structured Docker container action.

Поля:

- `server_id` или `server_id_context_key`
- `container`, поддерживает `{container_name}`
- `action`: `start`, `stop`, `restart`
- `include_logs`, default `true`
- `verify`, default `true`
- `lines`
- `on_failure`

Runtime:

- Берёт Docker snapshot до действия.
- Выполняет `run_linux_ui_docker_action(...)`.
- При `verify=true` берёт Docker snapshot после действия.
- При `include_logs=true` добавляет excerpt `docker logs`.

### `ops/process_action`

Назначение: завершение процесса по PID как явный OPS-шаг.

Поля:

- `server_id` или `server_id_context_key`
- `pid` или `pid_context_key`
- `action`: `terminate`, `kill_force`
- `on_failure`

Runtime:

- Выполняет `run_linux_ui_process_action(...)`.
- Возвращает `still_running`, `process_excerpt`, `dangerous`.
- `kill_force` должен использоваться только после approval в шаблонах.

### `ops/http_check`

Назначение: проверить HTTP endpoint после изменения или как standalone health gate.

Поля:

- `url`, поддерживает templates
- `method`: `GET` или `HEAD`
- `expected_status`: list of status codes, default `200..399`
- `body_contains`
- `timeout_seconds`, clamp `1..120`
- `retries`, clamp `1..5`
- `on_failure`

Runtime:

- Делает HTTP request через `httpx.AsyncClient`.
- Успех требует ожидаемый status и, если задано, наличие `body_contains`.
- Возвращает structured `http_check`.

### `ops/alert_update`

Назначение: обновить WebTerm monitoring alert после успешной диагностики/верификации.

Поля:

- `alert_id` или `alert_id_context_key`, default `alert_id`
- `action`: сейчас только `resolve`
- `note`
- `on_failure`

Runtime:

- Проверяет, что alert принадлежит серверу владельца pipeline.
- Для `resolve` выставляет `is_resolved`, `resolved_at`, `resolved_by`.
- Возвращает structured `alert`.

## Logic nodes

### `logic/condition`

Назначение: if/else routing по output/status предыдущей ноды.

Runtime:

- Выполняется через registry adapter `studio/executor/nodes/logic_condition.py`, подключенный из production `PipelineExecutor`.
- Берёт `source_node_id`.
- Сравнивает `node_outputs[source_node_id].output` или `status`.
- Возвращает `passed` и `output` как строку `True`/`False`.

Поля:

- `label`
- `source_node_id`
- `check_type`
- `check_value`

`check_type`:

- `contains`
- `not_contains`
- `status_ok`
- `status_failed`
- `always_true`

Ошибки/подводные места:

- Если `source_node_id` пустой или не найден, output/status считаются пустыми.
- Unknown `check_type` не падает, а даёт `false`.
- `contains` / `not_contains` с пустым `check_value` блокируются server validation; editor также показывает inline error и не отправляет save/run до backend.

Фишки:

- UI при соединении source -> condition автозаполняет `source_node_id`.
- Для status checks `check_value` не нужен.

### `logic/parallel`

Назначение: fan-out marker для параллельных downstream веток.

Runtime:

- Выполняется через registry adapter `studio/executor/nodes/logic_parallel.py`, подключенный из production `PipelineExecutor`.
- Сама нода возвращает `completed` и output `параллельное разветвление`.
- Реальная параллельность появляется потому, что downstream targets попадают в один batch и выполняются через `asyncio.gather(...)`.

Поля:

- `label`

Ошибки:

- Специфических runtime errors нет.
- Общие graph errors по handles/reachability.

Фишки:

- Используйте с `logic/merge`, иначе ветки могут завершиться независимо.

### `logic/merge`

Назначение: явное объединение нескольких веток.

Runtime:

- Router хранит `pending_merges`.
- `mode="all"` ждёт все возможные активные source-ветки.
- `mode="any"` выпускает downstream после первой пришедшей ветки.
- Возможные source-ветки считаются с учётом entry trigger, достижимости и реальных routing ports source-ноды.
- Выполняется через registry adapter `studio/executor/nodes/logic_merge.py`, подключенный из production `PipelineExecutor`.
- Registry execution возвращает `completed` и human-readable output.

Поля:

- `label`
- `mode`: `all` или `any`, default `all`

Ошибки/подводные места:

- Merge без входящих edges не проходит validation.
- Invalid mode на runtime silently coerced to `all`.
- Не используйте несколько входящих edges напрямую в action/output-ноду, validation потребует explicit merge.

Фишки:

- `all` ждёт только возможные активные ветки, а не все нарисованные edges без учёта условий.
- `any` удобен для "любой trigger / любая успешная ветка продолжает".

### `logic/wait`

Назначение: пауза выполнения на заданное время.

Runtime:

- Выполняется через registry adapter `studio/executor/nodes/logic_wait.py`, подключенный из production `PipelineExecutor`.
- `wait_minutes` парсится в float.
- Clamp: минимум `0.1`, максимум `1440` минут.
- Sleep идёт кусками по 1 секунде.
- На каждом шаге проверяется stop event из `ExecutionContext` и DB status `stopped`.
- При stop возвращает `stopped`.

Поля:

- `label`
- `wait_minutes`, UI default `20`, backend fallback `1`

Ошибки:

- Невалидное значение заменяется на `1.0`.
- Stop во время wait возвращает `Wait cancelled by stop request`.

Фишки:

- При successful wait открываются оба handles: `done` и `out`.
- Можно использовать короткие `0.1` минут для smoke tests.

### `logic/human_approval`

Назначение: остановить поток и дождаться approve/reject от оператора.

Runtime:

- Выполняется через registry adapter `studio/executor/nodes/logic_human_approval.py`; implementation живет в `studio/pipeline_interactions.py`, а production `PipelineExecutor` оставляет только compatibility alias.
- Adapter сохраняет существующую approval runtime semantics: state arming, email/Telegram delivery, polling, timeout и stop handling остаются в production approval runtime.
- Генерирует one-time `approval_token`.
- Сохраняет в `node_states[node_id]`: `status="awaiting_approval"`, token, approve/reject URL, `started_at`.
- URL:
  - `GET /api/studio/runs/<run_id>/approve/<node_id>/?token=...&decision=approved`
  - `GET /api/studio/runs/<run_id>/approve/<node_id>/?token=...&decision=rejected`
- Endpoint также принимает POST с `token`, `decision`, `response_text`.
- Может отправить email и/или Telegram inline buttons.
- Poll interval: 2 секунды.
- Telegram callback сохраняется в node_state и подтверждается сообщением.
- Approved возвращает `completed`, `decision="approved"`.
- Rejected возвращает `failed`, `decision="rejected"`.
- Timeout возвращает `failed`, `decision="timeout"`.
- Stop возвращает `stopped`.

Поля:

- `label`
- `message`
- `manual_link_only`, default `false`; если `true`, email/Telegram delivery не требуется, runtime сохраняет approval links и ждёт ручное решение.
- `timeout_minutes`, default `120`
- `base_url`
- `to_email`
- `email_subject`
- `email_body`
- `smtp_host`
- `smtp_port`
- `smtp_user`
- `smtp_password`
- `from_email`
- `tg_bot_token`
- `tg_chat_id`
- `tg_parse_mode`
- `telegram_message`

Ошибки/подводные места:

- Если email/Telegram delivery не настроены и `manual_link_only=true` не задан явно, runtime fail-fast вместо скрытого ожидания до timeout.
- Если `manual_link_only=true`, оператор должен получить approve/reject links из run state/API или другого контролируемого канала; email/Telegram не отправляются.
- Ошибка отправки email/Telegram логируется, но не всегда fail-ит сам approval node.
- `timeout_minutes` кастится через `float(...)` без try/except; нечисловое значение может уронить execution.
- Rejected/timeout имеют `status="failed"`, но logic routing всё равно идёт по `rejected`/`timeout`, и pipeline не abort-ится автоматически.
- Public approve endpoint защищён только token из URL/node_state.

Фишки:

- Telegram approval работает кнопками inline keyboard, без открытия браузера.
- `response`/`response_text` сохраняется как комментарий оператора.
- `base_url` берётся из node config или global notification config/site URL.

### `logic/telegram_input`

Назначение: задать вопрос оператору в Telegram и дождаться обычного text reply.

Runtime по текущему коду:

- Выполняется через registry adapter `studio/executor/nodes/logic_telegram_input.py`; implementation живет в `studio/pipeline_interactions.py`, а production `PipelineExecutor` оставляет только compatibility alias.
- Adapter сохраняет существующую polling runtime semantics: Telegram ForceReply delivery, DB state polling, Telegram reply polling, timeout и stop handling остаются в production telegram-input runtime.
- Это logic node, не trigger. Она не запускает pipeline сама.
- Требует bot token и chat id, с fallback на global notification settings.
- Если chat id не задан в node/global config, может взять `tg_chat_id` или `chat_id` из context.
- Отправляет Telegram message с `force_reply`.
- Требует `last_message_id` от Telegram API.
- Сохраняет `node_state.status="awaiting_operator_reply"`, `telegram_prompt_message_id`, `telegram_chat_id`, `bot_token`, `started_at`.
- Poll loop проверяет `operator_response` в DB state и Telegram `getUpdates` через `_poll_telegram_reply_message(...)`:
  - есть response -> `completed`, `decision="received"`
  - timeout -> `failed`, `decision="timeout"`
  - stop -> `stopped`
  - иначе ждёт следующий poll interval
- `run_telegram_bot.py` больше не пропускает reply messages молча: reply к prompt message записывается в matching node_state через `store_telegram_operator_reply(...)`.

Поля:

- `label`
- `message`
- `timeout_minutes`, default `120`
- `tg_bot_token`
- `tg_chat_id`
- `bot_token`
- `chat_id`
- `telegram_bot_token`
- `telegram_chat_id`
- `parse_mode`, default `Markdown`

Ошибки:

- `tg_bot_token not configured for telegram_input node.`
- `tg_chat_id not configured for telegram_input node.`
- Telegram send error from `_send_telegram_message`.
- `Telegram не вернул message_id для ожидания ответа оператора.`
- Timeout: `Таймаут ожидания ответа оператора - нет ответа в течение <n> мин.`

Фишки:

- Отличается от `output/telegram`: output только отправляет сообщение, input должен ждать ответ.
- AI drafter специально нормализует ошибочные `trigger/telegram_input`, `telegram_trigger`, `input/telegram` в `logic/telegram_input`.

## Output nodes

### `output/report`

Назначение: собрать Markdown summary и сохранить в `PipelineRun.summary`.

Runtime:

- Выполняется через registry adapter `studio/executor/nodes/output_report.py`, подключенный из production `PipelineExecutor`.
- Если `template` задан, рендерит его через `_render_template_value`.
- Если `template` пустой, собирает auto report по всем `node_outputs`.
- Output каждой ноды режется до 2000 символов в auto report.
- Обновляет `PipelineRun.summary`.
- Перед сохранением и возвратом редактирует context/node outputs через pipeline output boundary.
- Возвращает итоговый markdown в `output`.

Поля:

- `label`
- `template`
- `on_failure`

Ошибки:

- Специфических runtime errors почти нет, кроме неожиданных DB/template exceptions.

Фишки:

- UI при соединении source -> report автозаполняет template.
- `output/report` теперь один из первых non-OPS production nodes, переведенных на registry adapter.

### `output/webhook`

Назначение: отправить результаты pipeline во внешний HTTP endpoint.

Production runtime:

- Требует `url`.
- Выполняется через registry adapter `studio/executor/nodes/output_webhook.py`, подключенный из production `PipelineExecutor`.
- Payload:
  - `context`
  - `outputs`, где каждый output обрезан до 1000 символов
  - `extra_payload`, если object
- Перед отправкой payload редактируется через pipeline output boundary, чтобы raw secrets из context/node outputs не уходили во внешний endpoint.
- Делает `httpx.AsyncClient(timeout=<timeout_seconds>).post(url, json=payload, headers=<headers>)`.
- По умолчанию любой HTTP status считается `completed`; status code пишется в `http_status`.
- Если `fail_on_non_2xx=true`, HTTP 4xx/5xx возвращает `failed` и открывает `error` route.

Поля:

- `label`
- `url`
- `extra_payload`
- `headers`
- `timeout_seconds`, clamp `1..120`, default `30`
- `fail_on_non_2xx`
- `on_failure`

Ошибки:

- `No URL configured`.
- Validation rejects `timeout_seconds` outside `1..120`.
- Validation rejects non-object `headers` / `extra_payload`.
- Network/HTTP client exception -> `failed`.

Фишки/расхождения:

- `output/webhook` теперь один из первых non-OPS production nodes, переведенных на registry adapter.
- HTTP 4xx/5xx не fail-ит ноду сам по себе, если `fail_on_non_2xx` не включен явно.

### `output/email`

Назначение: отправить report/result по SMTP.

Runtime:

- Выполняется через registry adapter `studio/executor/nodes/output_email.py`, подключенный из production `PipelineExecutor`.
- Node config overrides global notification config/Django settings.
- Recipient нормализуется: если указан login без `@`, для Yandex/Gmail может добавиться домен.
- From тоже нормализуется, чтобы не слать `noreply@...` через SMTP, который такое отвергнет.
- Body отправляется как plain text; если установлен `markdown`, добавляется HTML alternative.
- SMTP 465 использует SSL, 587 использует STARTTLS.
- Subject/body редактируются через pipeline output boundary; approval links можно сохранить через internal preserve-list.

Поля:

- `label`
- `to_email`
- `subject`
- `body`
- `smtp_host`
- `smtp_port`
- `smtp_user`
- `smtp_password`
- `from_email`
- `on_failure`

Ошибки:

- `No recipient email. Set PIPELINE_NOTIFY_EMAIL in .env or fill in the node.`
- SMTP exceptions -> `SMTP error: ...`

Фишки:

- Если `body` пустой, auto body собирается по node outputs.
- UI при соединении source -> email автозаполняет subject/body.
- Глобальные настройки берутся из `.notification_config.json`, env/Django settings.
- `output/email` теперь один из non-OPS production nodes, переведенных на registry adapter.

### `output/telegram`

Назначение: отправить сообщение в Telegram Bot API.

Runtime:

- Выполняется через registry adapter `studio/executor/nodes/output_telegram.py`, подключенный из production `PipelineExecutor`.
- Credentials берутся из node config или global notification settings.
- `chat_id` может fallback-нуться из context.
- Если `message` пустой, runtime собирает auto message по outputs.
- Message разбивается на chunks по 4000 символов.
- `reply_markup` применяется только к последнему chunk.
- `parse_mode` default `Markdown`.
- Перед отправкой message редактируется через pipeline output boundary.

Поля:

- `label`
- `message`
- `bot_token`
- `chat_id`
- `tg_bot_token`
- `tg_chat_id`
- `telegram_bot_token`
- `telegram_chat_id`
- `parse_mode`
- `reply_markup`
- `disable_web_page_preview`
- `on_failure`

Ошибки:

- `bot_token not configured. Set TELEGRAM_BOT_TOKEN in .env or fill in the node.`
- `chat_id not configured. Set TELEGRAM_CHAT_ID in .env or fill in the node.`
- Telegram API non-200 -> `Telegram API error <status>: <body>`.
- Exceptions -> `Telegram send error: ...`

Фишки:

- Поддерживает Markdown.
- UI при соединении source -> telegram автозаполняет message.
- Может использоваться внутри `logic/human_approval` для inline approval buttons.
- `output/telegram` теперь один из non-OPS production nodes, переведенных на registry adapter.

## UI и AI drafter фишки

- Node palette берётся из `NODE_PALETTE` и содержит те же 30 типов.
- `NODE_TYPE_META` и `NODE_TYPE_GUIDANCE_META` дают RU/EN labels, descriptions и checklist в palette/node panel.
- Draft canvas (`DraftGraphCanvas`) использует те же visual components, что и редактор pipeline.
- При соединении нод UI автозаполняет:
  - `logic/condition.source_node_id`
  - `agent/llm_query.prompt`
  - `output/report.template`
  - `output/email.subject/body`
  - `output/telegram.message`
  - `logic/human_approval.message/email_body`
  - `logic/telegram_input.message`
- AI pipeline assistant catalog (`NODE_TYPE_CATALOG`) знает все 30 типов и source handles.
- AI assistant aliases:
  - `manual` -> `trigger/manual`
  - `webhook` -> `trigger/webhook`
  - `schedule` -> `trigger/schedule`
  - `monitoring` -> `trigger/monitoring`
  - `ssh_cmd`, `ssh_command` -> `agent/ssh_cmd`
  - `llm_query` -> `agent/llm_query`
  - `mcp_call` -> `agent/mcp_call`
  - `server_snapshot`, `linux_snapshot` -> `ops/server_snapshot`
  - `log_query`, `logs`, `journal`, `service_logs`, `docker_logs` -> `ops/log_query`
  - `service_action`, `service_restart`, `systemctl` -> `ops/service_action`
  - `docker_action`, `docker_restart` -> `ops/docker_action`
  - `process_action` -> `ops/process_action`
  - `http_check`, `health_check` -> `ops/http_check`
  - `resolve_alert`, `alert_update` -> `ops/alert_update`
  - `condition`, `parallel`, `merge`, `wait`, `human_approval` -> corresponding `logic/*`
  - `telegram_input`, `trigger/telegram_input`, `telegram_trigger` -> `logic/telegram_input`
  - `report` -> `output/report`
  - `email` -> `output/email`
  - `telegram`, `send_telegram` -> `output/telegram`
- Assistant prompt explicitly says: `Telegram Input` is strictly `logic/telegram_input`; it is not a trigger.
- Editor manual Run dialog показывает `Risk before run`: mutating MCP/OPS/SSH steps, approval gates, verification nodes и mutating steps без approved approval ancestor. Логика находится в `frontend/src/components/pipeline/pipelineRiskSummary.ts`.
- Backend draft risk, pipeline validation и runtime policy summary используют общий policy contract `studio/execution_policy.py` (`ExecutionPolicyDecision`). Он смотрит на MCP metadata: `mutates_state`, `requires_approval`, `permission_mode`, `operation_kind`, `risk_level`, поэтому MCP tools с нестандартными именами тоже попадают в risk/approval review.
- Backend pipeline validation теперь содержит policy guard: mutating `agent/mcp_call`, mutating `agent/ssh_cmd`, `ops/service_action`, `ops/docker_action`, `ops/process_action` и `ops/alert_update` требуют upstream `logic/human_approval` через handle `approved`. Если после `logic/merge` есть путь к mutating node, который обходит approval, graph считается невалидным. Runtime inherits this because `PipelineExecutor.execute(...)` runs `validate_pipeline_definition(...)` before executing nodes.
- External side effects тоже классифицируются policy contract: `output/webhook` с URL, `output/email` с recipients и `output/telegram` с chat/bot target дают review-level `external` decision. По умолчанию они не блокируют запуск, но попадают в AI Draft risk и в runtime `trigger_data.execution_policy`. Webhook URL query/fragment values редактируются в policy summary.
- Runtime output boundary редактирует node outputs/context перед внешними каналами: `output/report` и `PipelineRun.summary`, `output/webhook` JSON payload, `output/email` body/subject, `output/telegram` message, а также approval/Telegram-input previews. Approval URLs сохраняются через internal preserve-list, чтобы одноразовые ссылки/inline buttons не ломались.
- Saved pipeline manual Run API поддерживает validate-only/dry-run: `POST /api/studio/pipelines/<id>/run/` с `validate_only=true` или `dry_run=true` возвращает `validation`, `risk`, `dry_run.executed=false`, `would_create_run=false` и не создаёт `PipelineRun`.
- Editor manual Run dialog имеет отдельную кнопку `Проверить`, которая сохраняет текущую версию графа и запускает этот validate-only path без выполнения MCP tools, SSH commands, OPS actions или notifications.
- AI Drafts validate/dry-run endpoint: `POST /api/studio/assistant/drafts/<id>/validate/`.
  Он берет latest revision preview graph, заново запускает `validate_pipeline_definition(...)` и `pipeline_assistant_risk(...)`, сохраняет свежие `validation`, `risk`, `dry_run` в revision response и возвращает обновленный draft.
  `dry_run.executed=false`: endpoint не запускает pipeline, MCP tools, SSH commands, OPS actions или notifications.
- AI Drafts provider-free compiler: если create/revise payload содержит `compiler_mode="deterministic"` (UI кнопка `Quick skeleton`), backend использует локальный deterministic pilot compiler и не вызывает LLM provider. Ответ помечает `selected_template.source="pilot_template_compiler"` для matched pilot templates.
- AI Drafts interview mode: если skeleton/resource binding видит blocking gaps (`Argument: realm`, `service_name`, `target server`, MCP server и т.д.), response получает `questions`, draft переходит в `needs_input`, а Composer переключается в режим ответа на вопросы. `POST /api/studio/assistant/drafts/<id>/revise/` передает AI исходную задачу + открытые вопросы + ответ оператора, поэтому короткий ответ вроде `realm prod, user ivan, role admin` считается уточнением текущей автоматизации, а не новой задачей.
- `/api/studio/capabilities/` остается backend registry для AI Drafts, templates и будущих экранов: readiness по task families, подключенные MCP/skills и missing capability не выводятся отдельным тяжелым блоком на `/studio`.
- AI drafter получает `template_recommendations` в assistant context. Selector матчится по user message / pipeline name и передает compact skeleton: slug, tags, node types, nodes/edges and key data hints. Prompt требует использовать лучший pilot template как DAG skeleton перед raw generation.
- Если LLM provider вернул ошибку и запрос матчится на pilot template, local fallback собирает `graph_patch` из этого template skeleton. Keycloak fallback остается resource-aware и имеет приоритет для IAM задач.
- AI Drafts UI показывает `Pilot skeleton` в review panel, если response содержит `template_recommendations`. Оператор может выбрать другой recommendation и вызвать `POST /api/studio/assistant/drafts/<id>/use-template/` с `template_slug`; backend создает новую revision из выбранного skeleton, валидирует graph/risk и не запускает runtime actions.
- Pilot template resource binding находится в `studio/services/pipeline_template_recommendations.py`:
  - `agent/mcp_call.data.mcp_server_id` подставляется по `mcp_server_name` и доступным MCP серверам.
  - OPS node `server_id` подставляется только если prompt/draft title явно матчится на server name/host или у пользователя ровно один доступный сервер.
  - `skill_slugs` сохраняются/дополняются только доступными skills по slug/service/category.
  - Typed prompt arguments подставляются до apply, если они явно извлечены из текста: Keycloak `realm`/`username`/`role`/`group`/`operation`, Kubernetes `cluster`/`namespace`/`kind`/`workload_name`, GitLab `project_id`/`pipeline_id`/`branch`/`commit_sha`, DB `database`/`schema`, Observability/Incident `alert_id`/`alert_source`/`alert_severity`/`service_name`, service `service_name`/`healthcheck_url`.
  - MCP pilot tool metadata берется из `studio/pilot_capability_packs.py`: `input_schema`, `tool_description`, `capability_pack`, `task_family`, `service`, `risk_level`, `operation_kind`, `mutates_state`, `requires_approval`, `policy_tags`.
  - Рекомендованные skill slugs из capability pack попадают в node data только если доступны пользователю; иначе они идут в `resource_plan.missing`, чтобы draft оставался валидным.
  - Нераспознанные input placeholders остаются в graph как `{placeholder}` и попадают в `resource_plan.missing`; runtime placeholders из webhook, monitoring trigger или предыдущих нод попадают в notes.
  - Неоднозначные ресурсы попадают в `resource_plan.missing`; случайный ресурс не выбирается.

## Built-in pilot templates

`studio/templates_data.py` содержит отдельный starter pack категории `Pilot OPS`. Он нужен для первого production pilot: пользователи могут брать готовый workflow skeleton и подставлять свои MCP server/tool, skill и context fields без добавления узких сервисных нод.

Текущие pilot templates:

| Slug | Сценарий | Ключевые ноды |
| --- | --- | --- |
| `pilot-keycloak-access-change` | Keycloak role/group/user access change | `agent/mcp_call`, `logic/human_approval`, verification `agent/mcp_call`, `output/report` |
| `pilot-kubernetes-rollout` | Kubernetes diagnose and rollout restart | read-only `agent/mcp_call`, `agent/llm_query`, approval, mutating `agent/mcp_call`, verification |
| `pilot-gitlab-failed-pipeline-mr` | GitLab failed pipeline -> MR | webhook trigger, read-only CI evidence, approval, MR MCP action, pipeline verification |
| `pilot-database-diagnostics-maintenance` | DB diagnostics and guarded maintenance | read-only DB checks, approval, guarded maintenance MCP action, health verification |
| `pilot-observability-incident-response` | Observability incident response | monitoring trigger, read-only alert/metrics/log MCP calls, AI incident summary, approval, ticket/update MCP action, acknowledgement verification |
| `pilot-linux-package-maintenance` | Linux package maintenance | `ops/server_snapshot`, AI risk review, approval, `ops/package_action`, package-state verification |
| `pilot-linux-disk-cleanup` | Linux disk cleanup | `ops/disk_cleanup` inspect, AI risk review, approval, bounded cleanup, disk-state verification |
| `pilot-backup-restore-check` | Backup restore check | `ops/backup_restore_check` inspect, latest archive verification, AI readiness review, report |
| `pilot-service-config-validate-restart` | Service config validate and restart | `ops/server_snapshot`, `agent/llm_query`, approval, `ops/service_action`, `ops/http_check` |

Инварианты:

- Service-specific work проходит через `agent/mcp_call` или generic `ops/*`, а не через `keycloak/*`, `kubernetes/*`, `gitlab/*`, `database/*` ноды.
- `agent/mcp_call` nodes для pilot MCP tools получают embedded schema/policy metadata из capability packs, поэтому editor может показать typed arguments даже до живого MCP tool inspection.
- `agent/mcp_call` теперь валидирует embedded `input_schema` на backend и в frontend pre-save checks: обязательные MCP arguments, enum и базовые типы ловятся до запуска. Template placeholders вида `{namespace}` считаются допустимыми до resource binding/runtime context.
- Mutating шаги идут только из `logic/human_approval` через handle `approved`.
- Approval templates включают `manual_link_only=true`, чтобы starter можно было запускать в тесте без настроенной почты/Telegram.
- Каждый mutating сценарий имеет verification/report path.
- AI Drafts selector использует эти starter templates как skeleton для Keycloak, Kubernetes, GitLab CI/MR, DB maintenance, Observability/Incident, Linux package/disk maintenance, backup restore checks и service restart intents.
- `tests/test_studio_pipeline_templates.py` проверяет регистрацию, graph validation, safety shape и selector/graph patch conversion этих starter templates.
- `app/test_studio_pipeline_assistant_api.py` проверяет, что draft можно переключить на выбранный pilot template без создания pipeline/run.
- `tests/fixtures/studio_ops_prompt_evals.json` + `tests/test_studio_prompt_evals.py` проверяют 35 representative OPS prompts: Keycloak/IAM, Kubernetes, GitLab CI/MR, DB maintenance, Observability/Incident, Linux package maintenance, disk cleanup, backup restore checks и runtime service incidents. Для каждого prompt тестируется selected skeleton, graph validation, отсутствие service-specific node types, approval перед mutation, verification path и output path; отдельные assertions проверяют typed argument binding, missing placeholders/questions, backend MCP metadata risk и end-to-end draft API creation через `compiler_mode="deterministic"` без LLM provider calls.
- API tests также проверяют resource binding: GitLab pilot fallback подставляет доступный GitLab MCP и explicit prompt args в `agent/mcp_call`, Kubernetes deterministic compiler работает без LLM provider и встраивает MCP schema/policy metadata, а service skeleton подставляет `server_id`, `service` и `http_check.url`, когда prompt явно содержит имя сервера/сервиса/health URL.

## Известные ошибки и gaps на 2026-05-28

1. `logic/telegram_input` теперь подключена к production polling path, но это ещё не detached worker.
   Нода сохраняет `awaiting_operator_reply`, отправляет ForceReply-сообщение, опрашивает Telegram/DB и `run_telegram_bot.py` маршрутизирует reply обратно в `PipelineRun.node_states`. Оставшийся gap: executor всё ещё держит активное ожидание до timeout; полноценная hibernation/resume модель должна переводить run в отдельный sleeping state и будить его внешним событием.

2. All-nodes smoke graph обновлён для `trigger/monitoring`, `logic/telegram_input` и OPS nodes.
   Оставшийся gap: smoke pipeline безопасно валидирует форму и граф, но не выполняет реальные mutating OPS действия без внешнего контекста/серверов.

3. Target node-registry architecture частичная.
   `studio/executor/registry.py` и `studio/executor/engine.py` являются целевой архитектурой, но production run lifecycle всё ещё в `studio/pipeline_executor.py`. OPS nodes, все `output/*`, все `logic/*` и все `agent/*` nodes уже выполняются через registry adapter. `PipelineExecutor._execute_node` dispatch теперь использует `node_type in registry`, поэтому новые registry-ноды не требуют отдельной ветки в executor. Простые logic helper-реализации для `logic/condition`, `logic/wait` и `logic/merge` живут в `studio/pipeline_logic.py`; interactive helper-реализации для `logic/human_approval` и `logic/telegram_input` живут в `studio/pipeline_interactions.py`; `pipeline_executor.py` сохраняет legacy alias-имена.
   `python manage.py check_node_manifest_consistency` теперь также проверяет, что executor registry содержит ровно все non-trigger node types из manifest, без пропусков и лишних runtime types, а каждая нода имеет object `input_schema` и `output_schema`.

3a. `NodeManifest` теперь отдает единый контракт для UI и AI.
   `studio/node_manifest.py` публикует `input_schema`, `output_schema`, risk metadata, handles, dry-run/approval flags и tags. `GET /api/studio/node-manifests/` возвращает этот contract отдельно от capability readiness, а `/api/studio/capabilities/` встраивает те же node schemas в `nodes`. AI assistant catalog тоже строится из этого manifest, чтобы drafter, API и future form generation не расходились. Frontend editor уже подтягивает endpoint и использует schemas для client-side проверки настроенных enum/range значений перед save/run.

4. Все output-ноды (`output/report`, `output/webhook`, `output/email`, `output/telegram`) переведены на production registry adapter. `output/report` держит parity по `PipelineRun.summary`, template rendering, auto-report и redaction; `output/webhook` держит parity по `context`/`outputs` payload, redaction, `headers`, `timeout_seconds` и `fail_on_non_2xx`; `output/email` держит parity по SMTP/global settings, normalized recipients/from, STARTTLS/SSL, subject/body templates и redaction preserve-list; `output/telegram` держит parity по global/node credentials, context fallback, chunks, Telegram API errors и redaction.
   Оставшийся registry gap теперь не в output-нóдах, а в agent/logic production nodes.

4a. `logic/condition` переведен на production registry adapter и держит parity по `source_node_id`, `contains`/`not_contains`, status checks, `always_true`, `passed` и строковому `output`. `logic/parallel` переведен на registry adapter с parity по gateway output; executor batch routing всё ещё отвечает за фактический fan-out. `logic/merge` тоже переведен на registry adapter с parity по `mode=all|any`, fallback invalid mode -> `all` и human-readable `output`; router-level pending merge state остается в `PipelineExecutor`. `logic/wait` переведен на registry adapter с parity по `wait_minutes` parsing/clamp, chunked sleep, stop-event handling, DB stopped status и completed/stopped output. Общая implementation для `condition`, `merge` и `wait` живет в `studio/pipeline_logic.py`.

4b. `logic/human_approval` переведен на production registry adapter без смены approval semantics: state arming, `approval_token`, manual links, email/Telegram delivery, Telegram callback polling, DB decision polling, timeout и stop handling остаются совместимыми с прежним runtime path. Общая implementation живет в `studio/pipeline_interactions.py`.

4c. `logic/telegram_input` переведен на production registry adapter без смены polling semantics: ForceReply delivery, `awaiting_operator_reply` state, DB/operator reply polling, Telegram reply polling, timeout и stop handling остаются совместимыми с прежним runtime path. Общая implementation живет в `studio/pipeline_interactions.py`.

4d. `agent/llm_query` и `agent/mcp_call` переведены на production registry adapter без смены runtime semantics. Для `agent/mcp_call` adapter передает текущий executor `executed_mcp_tools` set, чтобы skill-policy order tracking оставался совместимым с прежним path.

4e. `agent/react`, `agent/multi` и `agent/ssh_cmd` переведены на production registry adapter без смены runtime semantics. ReAct/multi adapters сохраняют AgentConfig/server/MCP/skill resolution и event callbacks; SSH adapter сохраняет direct command, preflight/verification, permission/sandbox/hook checks, command history и fallback в ReAct.

5. Schedule validation и scheduler runtime используют общий cron helper: при наличии `croniter` используется он, без него работает local 5-field fallback parser. Это закрывает прежнее расхождение, где validation принимал cron, а scheduler без `croniter` не запускал triggers.

6. `logic/human_approval` теперь fail-fast без delivery channel, если `manual_link_only=true` не задан явно. UI форма показывает этот режим отдельным switch в Delivery section, чтобы это был осознанный выбор оператора.

7. `logic/condition` с `contains` / `not_contains` и пустым `check_value` теперь ловится и backend validation, и frontend pre-save/pre-run validation.

8. `agent/ssh_cmd` имеет runtime support и UI форму для `preflight_commands` и `verification_commands`: advanced textareas принимают одну команду на строку и сохраняют списки в node data.

9. `agent/ssh_cmd` без server теперь возвращает `failed` и может уйти в `error` route.
   Оставшийся gap: существующие шаблоны, которые полагались на silent skip, нужно мигрировать на явный context-gate или condition.

10. OPS catalog покрывает первые high-value админские операции, но не весь Runbook surface.
    `ops/log_query` добавлен как read-only diagnostic primitive для incident/log workflows.
    `ops/file_action` добавлен как generic SFTP primitive для read/write UTF-8 config/text files; write path классифицируется policy guard как mutating и должен идти после approved `logic/human_approval`.
    `ops/package_action` добавлен как generic package primitive: read-only `list_updates` и mutating `install`/`update`/`remove` только по явному списку пакетов, с approval guard.
    `ops/disk_cleanup` добавлен как generic disk maintenance primitive: read-only `inspect` и bounded `journal_vacuum` / `tmp_cleanup` за approval guard.
    `ops/backup_restore_check` добавлен как read-only backup freshness/latest archive verification primitive; настоящий restore остается отдельным approved workflow/MCP/tool.
    Kubernetes rollout и IAM/user access пока остаются через `agent/mcp_call` + MCP tool schema + skills/templates; отдельные `ops/k8s_rollout` / `ops/user_access_action` не добавляются в MVP, пока этот универсальный путь покрывает сценарии без raw shell.

## Как добавлять новую ноду

Минимальный checklist:

1. Добавить type в `KNOWN_NODE_TYPES` и handles в `studio/pipeline_validation.py`.
2. Добавить frontend component/metadata в `frontend/src/components/pipeline/nodes/` и `NODE_PALETTE`.
3. Добавить форму настройки в `PipelineEditorPage.tsx` или общий node panel.
4. Добавить registry handler в `studio/executor/nodes/` и вынести shared runtime helper в focused `studio/pipeline_*` module, если логика не помещается в тонкий adapter.
5. Добавить assistant catalog/aliases в `studio/services/pipeline_assistant.py`, если ноду должен уметь генерировать AI drafter.
6. Добавить тесты:
   - validation
   - runtime node executor
   - frontend node/palette
   - all-nodes smoke graph
7. Обновить этот файл.

## Проверочные команды

Быстро проверить соответствие документа source-of-truth:

```powershell
@'
import os
from pathlib import Path

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web_ui.settings.development")
import django
django.setup()
from studio.pipeline_validation import KNOWN_NODE_TYPES

doc = Path('docs/PIPELINE_NODES_SPEC.md').read_text(encoding='utf-8')
missing = sorted(t for t in KNOWN_NODE_TYPES if f'`{t}`' not in doc)
print('known:', len(KNOWN_NODE_TYPES))
print('missing in doc:', missing)
'@ | python -
```

Точечные тесты по node runtime:

```powershell
python -m pytest tests/test_studio_node_executors.py
python -m pytest tests/test_studio_pipeline_v2.py
python -m pytest tests/test_studio_all_nodes_smoke.py
```

Manifest/source-of-truth consistency:

```powershell
python manage.py check_node_manifest_consistency
python -m pytest tests/test_studio_node_manifest_consistency.py
```
