# MARS Architecture Review and OOP Migration Plan

Проверено: 2026-05-27
Репозиторий: `C:\WebTrerm`
Базовый контекст проекта: `AGENTS.md`, `docs/local/ARCHITECTURE_CONTRACT.md`, `.importlinter`, `pyproject.toml`, текущая структура `app/`, `core_ui/`, `servers/`, `studio/`, `web_ui/`, `frontend/`, `desktop/`.

## 1. Итог ревью

Документ в прежнем виде был правильным по направлению: проект не надо переписывать с нуля и не надо дробить на микросервисы. Правильная цель - оставить модульный монолит, но довести его до нормальной объектной архитектуры по bounded context:

- Django views и Channels consumers должны быть тонкими адаптерами.
- Use-case/application services должны управлять сценариями.
- Domain services и policies должны держать бизнес-правила.
- Repositories/adapters должны изолировать Django ORM, SSH, RDP, LLM, MCP, email, Telegram и файловую систему.
- Registry/plugin-подход должен заменить большие `if/switch`-файлы там, где система расширяется типами: pipeline nodes, tools, providers, memory promotions.

Но прежний план уже устарел в нескольких важных местах:

1. `DjangoServerMemoryStore` уже физически вынесен из `app/agent_kernel/memory/store.py` в `servers/adapters/django_memory_store.py`.
2. `app/agent_kernel/memory/store.py` теперь маленький compatibility shim; shared-константы и pure-типы вынесены в `app/agent_kernel/memory/types.py`, а порт - в `app/agent_kernel/memory/ports.py`.
3. `studio/executor/` уже создан как целевая node-registry архитектура, но реально мигрированы только первые output nodes.
4. `frontend/src/api/` уже создан как целевая точка импорта, но почти все модули пока являются re-export shim поверх `src/lib/api.ts`.
5. `web_ui/settings.py` уже разложен в пакет `web_ui/settings/*`.
6. Есть реальные architecture fitness guards: `.importlinter`, `docs/local/ARCHITECTURE_CONTRACT.md`, `scripts/check_architecture_sizes.py`, baselines в `pyproject.toml`.
7. Architecture check снова проходит: рост `servers/adapters/django_memory_store.py` снят переносом pure memory types, а legacy exception `app.agent_kernel.memory.repair -> servers.models` удалён.
8. Legacy `servers/mcp_tool_runtime.py` shim удалён; серверные агенты получают MCP runtime через app-level `MCPRuntimeProvider`, а `studio` регистрирует concrete adapter.
9. Phase 2 почти закрыта по view monoliths: memory endpoints вынесены из `servers/views/_views_all.py` в `servers/views/server_memory.py`, knowledge endpoints вынесены в `servers/views/server_knowledge.py`, monitoring endpoints разделены между `servers/views/server_monitoring.py` и `servers/views/server_monitoring_actions.py`, SFTP/file endpoints вынесены в `servers/views/server_files.py`, agent endpoints разделены между `servers/views/server_agents.py` и `servers/views/server_agent_runs.py`, Linux UI endpoints разделены между `servers/views/server_linux_ui.py` и `servers/views/server_linux_ui_workloads.py`, group/share/context endpoints вынесены в `servers/views/server_groups.py`, `servers/views/server_shares.py`, `servers/views/server_context.py`, server CRUD/detail/reveal endpoints вынесены в `servers/views/server_crud.py`, test/execute/OS-detect endpoints вынесены в `servers/views/server_ops.py`, master-password session endpoints вынесены в `servers/views/server_auth_session.py`, SSR/bootstrap views вынесены в `servers/views/server_pages.py`, shared helpers вынесены в `servers/views/server_helpers.py`, а `servers/views/_views_all.py` теперь 26-line compatibility shim без legacy baseline. Studio split также продвинут: notification/template/server dropdown/MCP/share-users/trigger/run/agent/skill/pipeline/pipeline-assistant endpoints и shared helper groups вынесены из `studio/views/_views_all.py`. Core UI split тоже доведен до shim: auth/session/redirects, health endpoint, legacy page views, shared runtime helpers, access management endpoints, models/tools endpoints, settings config/activity endpoints, utility endpoints, IDE endpoints, RAG endpoints, admin dashboard/billing, chat/Cursor APIs и legacy settings page вынесены в focused modules, а `core_ui/views/_views_all.py` теперь 40-line compatibility shim.

Вывод: документ подходит как стратегическая основа, но его нужно читать в обновлённом виде: часть шагов уже начата, главная задача теперь не "начать ООП", а завершить миграцию без роста god-files и без новых нарушений границ.

## 2. Что считать "нормальной ООП архитектурой" для этого проекта

В этом проекте "нормальное ООП" не означает просто добавить классы. Плохой класс `Manager`, в который сложили тысячу строк процедурного кода, не решает проблему. Нужны классы с понятной ролью и одной причиной для изменения.

Правильные типы объектов:

- `UseCase` / application service: выполняет один пользовательский сценарий, например `CreateServerUseCase`, `RunPipelineUseCase`, `PromoteMemorySnapshotUseCase`.
- `Policy`: принимает бизнес-решение, например `ServerAccessPolicy`, `PipelineRunPolicy`, `MemoryRetentionPolicy`.
- `Domain service`: чистая доменная логика без Django request/response и без ORM side effects.
- `Repository`: скрывает ORM-запросы и возвращает domain objects или DTO.
- `Gateway`: внешний сервис или протокол, например `SshGateway`, `LlmGateway`, `McpGateway`, `NotificationGateway`.
- `Adapter`: Django view, Channels consumer, management command, ORM repository, Paramiko/RDP/MCP implementation.
- `Registry`: расширяемая карта типов, например pipeline node registry или tool registry.
- `Presenter` / serializer: формирует response DTO, чтобы view не собирал JSON руками.

Анти-цели:

- Не создавать новые top-level пакеты без необходимости.
- Не переносить все файлы ради красоты структуры.
- Не превращать Django models в толстые ActiveRecord-объекты.
- Не делать "универсальный сервис всего".
- Не смешивать frontend state, API transport и rendering в одном компоненте.
- Не обновлять baselines, чтобы спрятать рост god-files, если можно уменьшить файл.

## 3. Текущая архитектура проекта

Проект уже является модульным монолитом:

```text
web_ui/
  composition root: settings, urls, asgi/wsgi, routing

core_ui/
  identity, auth/session, access control, settings, admin dashboard, desktop API

servers/
  server inventory, SSH/RDP terminal, SFTP, monitoring, alerts, agents, layered memory

studio/
  pipelines, runs, MCP, skills, triggers, notifications, automation runtime

app/
  shared LLM runtime, agent kernel, memory algorithms, permissions, tools, safety

frontend/
  React/Vite SPA

desktop/
  WinUI desktop client
```

Главная проблема не в отсутствии модулей, а в том, что внутри модулей ещё остались файлы, которые совмещают слишком много ролей: controller, service, serializer, repository, external adapter и business rules одновременно.

## 4. Проверенные факты по текущему состоянию

### 4.1 Architecture fitness

Команда:

```bash
python scripts/check_architecture_sizes.py
```

Текущий результат после прохода 2026-05-26:

- import-linter: проходит.
- size guard: проходит.

Исправленная ошибка:

```text
Legacy file grew: 3824 > 3819
```

Это был важный сигнал: переход уже начался, но новый адаптер памяти стал следующим god-file. Теперь файл уменьшен до 647 строк и вошёл в целевой диапазон thin facade; следующий шаг - не наращивать его обратно и выносить оставшиеся focused blocks в adapters/services/repositories.

### 4.2 Самые крупные hotspots

Актуальные line counts из проекта:

| Файл | Строк | Проблема |
| --- | ---: | --- |
| `frontend/src/pages/PipelineEditorPage.tsx` | 4260 | route + graph editor + forms + assistant + run monitor |
| `frontend/src/lib/api.ts` | 4254 | все DTO, fetch, WebSocket, demo fallback и endpoints в одном файле |
| `frontend/src/components/terminal/LinuxUiPanel.tsx` | 4156 | desktop shell, apps, window state, API orchestration |
| `servers/consumers/ssh_terminal.py` | 3767 | WebSocket, SSH lifecycle, AI, memory, snapshots; terminal input parsing, connection record persistence, command-history recording, preferences, and report generation already extracted |
| `core_ui/views/_views_all.py` | 40 | Compatibility re-export shim; auth/session/redirects/health/page/runtime/access/models/settings/utility/IDE/RAG/admin/chat slices уже вынесены |
| `servers/adapters/django_memory_store.py` | 647 | Thin Django memory facade |
| `frontend/src/pages/Servers.tsx` | 3448 | server CRUD, groups, knowledge, memory UI |
| `studio/pipeline_executor.py` | 2737 | legacy executor with graph traversal and node-specific behavior |
| `studio/views/_views_all.py` | 60 | Compatibility re-export shim; notification/template/server dropdown/MCP/share-users/trigger/run/agent/skill/pipeline CRUD/pipeline assistant endpoints и shared helpers уже вынесены |
| `key_mcp.py` | 2089 | top-level large module outside clean bounded context |
| `frontend/src/pages/SettingsPage.tsx` | 2042 | settings container still too broad |

### 4.3 Что уже хорошо сделано

Есть реальные архитектурные зацепки, которые надо продолжать, а не ломать:

- `docs/local/ARCHITECTURE_CONTRACT.md` описывает file-size и import-boundary правила.
- `.importlinter` уже запрещает опасные зависимости между `app`, `core_ui`, `servers`, `studio`.
- `pyproject.toml` содержит legacy baselines, чтобы большие файлы не росли.
- `web_ui/settings/` уже выделен из одного settings-файла.
- `core_ui/views/` уже стал пакетом, есть отдельные view modules: `auth_views.py`, `access_views.py`, `access_group_views.py`, `admin_billing.py`, `admin_views.py`, `chat_helpers.py`, `chat_views.py`, `health_views.py`, `model_views.py`, `page_views.py`, `rag_views.py`, `runtime.py`, `settings_config_views.py`, `settings_activity_views.py`, `settings_page_views.py`, `utility_views.py`, `ide_views.py`, `dashboard_layout.py`, `terminal_preferences.py`.
- `servers/views/` уже стал пакетом, есть `command_history.py`, `snapshot_views.py`.
- `servers/services/` уже содержит полезные service modules, включая `server_query.py`, `ssh_connection.py`, `memory_service.py`, `pipeline_memory.py`, `pipeline_agents.py`, `terminal_ai/*`.
- `servers/consumers/` уже разделён на `ssh_terminal.py`, `rdp_terminal.py`, `agent_live.py`.
- `servers/adapters/memory_store.py` стал стабильной точкой импорта для `DjangoServerMemoryStore`.
- `app/agent_kernel/memory/ports.py` уже содержит `MemoryStore` protocol.
- `app/agent_kernel/memory/types.py` содержит pure memory constants/DTOs без Django imports.
- `app/agent_kernel/memory/repair.py` больше не импортирует Django или `servers.models`; ORM revalidation maintenance живёт в `servers/adapters/django_memory_repair.py`.
- `SkillPromotionGateway` добавлен как app-level port; promote-skill больше не создаёт прямой зависимости `servers.adapters.django_memory_store -> studio.*`.
- `servers.agent_engine -> studio.skill_registry` exception удалён; agent engine использует `SkillProvider` boundary без Studio type import.
- `MCPRuntimeProvider` добавлен как app-level port; `servers/agent_engine.py` и `servers/multi_agent_engine.py` больше не импортируют `servers.mcp_tool_runtime` или `studio.*` для MCP.
- `servers/mcp_tool_runtime.py` удалён; MCP runtime tests импортируют `studio.mcp_tool_runtime` напрямую как владельца реализации.
- `servers/adapters/django_memory_serializers.py` содержит memory overview/archive presenter helpers.
- `app/agent_kernel/memory/snapshot_utils.py` содержит pure helpers для snapshot line rendering, recent event point derivation, docker summary и memory-key guessing.
- `app/agent_kernel/memory/pattern_utils.py` содержит pure helpers для operational pattern scoring, metadata, candidate lines, automation/skill eligibility и human-habit/runbook derivation.
- `servers/views/server_memory.py` содержит user-facing и staff-only memory endpoints; `servers/urls.py` маршрутизирует memory API в этот module, а `servers/views/__init__.py` сохраняет re-export для совместимости.
- `servers/views/server_knowledge.py` содержит CRUD endpoints для server knowledge и manual-memory bridge sync/archive; `servers/urls.py` маршрутизирует knowledge API в этот module.
- `servers/views/server_monitoring.py` содержит monitoring dashboard/status/refresh/health endpoints; `servers/views/server_monitoring_actions.py` содержит alerts/watchers/config/AI analysis endpoints. Оба файла ниже нового-file limit.
- `servers/views/server_files.py` содержит SFTP/file endpoints; `servers/urls.py` маршрутизирует file API в этот module.
- `servers/views/server_agents.py` содержит agent config/schedule/template/launch endpoints; `servers/views/server_agent_runs.py` содержит run history/control/event/task endpoints. Оба файла ниже нового-file limit.
- `servers/views/server_linux_ui.py` содержит Linux UI read-only snapshot endpoints; `servers/views/server_linux_ui_workloads.py` содержит services/processes/docker endpoints и actions. Оба файла ниже нового-file limit.
- `servers/views/server_groups.py` содержит group CRUD/membership/subscription и bulk-update endpoints; `servers/views/server_shares.py` содержит share list/create/revoke endpoints; `servers/views/server_context.py` содержит global/group rules context endpoints.
- `servers/views/server_crud.py` содержит server create/update/delete/get/reveal endpoints; `servers/views/server_ops.py` содержит connection test, command execute и OS-detect endpoints; `servers/views/server_auth_session.py` содержит master-password session endpoints.
- `servers/views/server_pages.py` содержит SSR page и SPA bootstrap views; `servers/views/server_helpers.py` содержит shared access/share/password/OS helper functions. `servers/views/_views_all.py` уменьшен до 26 строк и оставлен только как compatibility shim; его legacy baseline в `pyproject.toml` удалён.
- `studio/views/notification_views.py` содержит notification settings, Telegram test, email test endpoints и notification config helpers; `studio/views/template_views.py` содержит pipeline template list/use endpoints; `studio/views/server_views.py` содержит server dropdown endpoint; `studio/views/mcp_views.py` содержит MCP pool CRUD/test/tools/templates endpoints и compatibility helpers; `studio/views/share_views.py` содержит shared user lookup endpoint; `studio/views/trigger_views.py` содержит trigger CRUD/webhook receive endpoints; `studio/views/run_views.py` содержит run list/detail/stop/approval endpoints и compatibility shims для package-level monkeypatch paths; `studio/views/agent_views.py` содержит agent config CRUD endpoints; `studio/views/skill_views.py` содержит skill catalog/detail/templates/scaffold/validate/workspace endpoints; `studio/views/pipeline_views.py` содержит pipeline CRUD/manual-run/clone/run-history endpoints; `studio/views/pipeline_assistant_views.py` содержит pipeline assistant endpoint; `studio/views/pipeline_assistant_preview.py` содержит assistant preview/risk helpers; `studio/views/common.py`, `pipeline_helpers.py`, `agent_helpers.py`, `skill_helpers.py` содержат shared view helpers. `studio/views/_views_all.py` уменьшен до 60 строк и оставлен только как compatibility re-export shim.
- `core_ui/views/auth_views.py` содержит frontend redirects, auth session/csrf/ws-token endpoints, login/logout API и `CustomLoginView`; `core_ui/views/access_views.py` содержит user access endpoints, access helpers и legacy access page redirects; `core_ui/views/access_group_views.py` содержит group/permission access endpoints; `core_ui/views/health_views.py` содержит lightweight health endpoint; `core_ui/views/model_views.py` содержит model/tool discovery endpoints; `core_ui/views/settings_config_views.py` содержит settings get/update/check endpoints; `core_ui/views/settings_activity_views.py` содержит activity log list/export endpoint; `core_ui/views/utility_views.py` содержит disk/legacy agent/upload endpoints; `core_ui/views/ide_views.py` содержит legacy IDE page/file endpoints and safer workspace path resolution; `core_ui/views/rag_views.py` содержит legacy RAG knowledge-base API endpoints; `core_ui/views/page_views.py` содержит legacy Django-rendered public/main page views; `core_ui/views/runtime.py` содержит shared orchestrator/RAG singleton lifecycle. `core_ui/urls.py` маршрутизирует auth/redirect/health/access/models/settings paths через focused modules, а `core_ui/views/__init__.py` сохраняет re-export для совместимости.
- `frontend/src/components/terminal/ServerPicker.tsx` вынесен из `TerminalPage.tsx`; `TerminalPage.tsx` уменьшен до 1309 строк и больше не нарушает legacy baseline.
- `frontend/src/components/terminal/SftpTransferQueue.tsx` вынесен из `SftpPanel.tsx`; `SftpPanel.tsx` уменьшен до 840 строк и больше не нарушает legacy baseline.
- `LinuxUiPanel.tsx` удержан ниже baseline: mobile window class mapping свернут в typed lookup, текущий размер 4156 строк.
- `servers/adapters/django_memory_overview.py` содержит ORM read-model для Settings -> AI Memory overview.
- `web_ui.settings.test` использует временный SQLite, поэтому targeted pytest больше не зависит от локального PostgreSQL из `.env`.
- `studio/executor/` уже содержит `PipelineEngine`, `NodeRegistry`, `BaseNode`, `OutputReportNode`, `OutputWebhookNode`.
- `frontend/src/api/` уже создан как целевая API-структура.
- `frontend/src/pages/settings/` уже содержит отдельные settings pages.

### 4.4 Что ещё не завершено

Ключевые незавершённые места:

- `servers/adapters/django_memory_store.py` сейчас thin facade, но его нельзя снова наращивать новой ORM/workflow логикой.
- `studio/pipeline_executor.py` всё ещё основной executor, а `studio/executor/` пока target architecture.
- Большинство frontend imports всё ещё идут из `@/lib/api`, а не из `@/api`.
- `src/api/auth.ts`, `src/api/servers.ts`, `src/api/studio.ts`, `src/api/settings.ts`, `src/api/agents.ts` в основном re-export или placeholder.
- `core_ui/views/_views_all.py`, `studio/views/_views_all.py` и `servers/views/_views_all.py` уже не содержат основной логики и работают как compatibility shims.
- `servers/consumers/ssh_terminal.py` больше не является владельцем большинства SSH/AI/memory workflows: pure terminal input parsing, connection record persistence, command-history recording, Terminal-AI preferences, report-generation streaming, durable memory extraction, command planning, recovery/step-decision workflow, output explanation, agent extra-target context, terminal access/secret lookup, SSH connect kwargs assembly, typed terminal events, SSH lifecycle helpers, plan-item shaping и terminal snapshotting вынесены в services. Файл всё ещё крупный из-за queue-runner и protocol glue, но это hardening target, не блокер для новых фич.
- `key_mcp.py` остаётся крупным top-level файлом, который надо либо обосновать как entrypoint, либо перенести в существующий bounded context.

## 5. Целевая архитектура

Цель - modular monolith с hexagonal boundaries:

```text
Clients
  React SPA, WinUI desktop, admin, WebSocket clients

Framework adapters
  Django views, Channels consumers, management commands, frontend API clients

Application layer
  Use cases, transaction orchestration, DTO mapping, authorization orchestration

Domain layer
  Entities, value objects, policies, pure domain services, domain events

Ports
  Repository protocols, LLM gateways, SSH gateways, MCP gateways, notification gateways

Infrastructure adapters
  Django ORM repositories, Paramiko/RDP adapters, email/Telegram/MCP implementations
```

Правило направления зависимостей:

```text
web_ui -> core_ui / servers / studio / app
core_ui -> app
servers -> app
studio -> app
app.agent_kernel -> pure Python only
```

Feature apps не должны напрямую импортировать друг друга:

- `servers` не должен напрямую импортировать `studio`.
- `studio` не должен напрямую импортировать `servers`, кроме временных whitelisted точек.
- `core_ui` не должен использовать `servers`/`studio` напрямую, кроме admin/desktop aggregation adapters.
- `app.agent_kernel` не должен импортировать Django, `servers`, `studio`, `core_ui`.

## 6. Целевая структура backend

### 6.1 `core_ui`

Назначение: identity/access/settings/admin/desktop integration.

Целевая структура:

```text
core_ui/
  domain/
    permissions.py
    audit.py
    sessions.py
  services/
    auth_session.py
    access_policy.py
    access_management.py
    managed_secrets.py
    audit_log.py
    dashboard_layout.py
    terminal_preferences.py
  repositories/
    django_access_repository.py
    django_audit_repository.py
  views/
    auth.py
    settings.py
    access_users.py
    access_groups.py
    admin_dashboard.py
    redirects.py
```

Правила:

- `core_ui/views/_views_all.py` больше не должен получать новую логику.
- Admin dashboard может агрегировать данные из других bounded contexts только через публичные query services.
- Desktop API остаётся integration adapter, но не должен становиться вторым god-controller.

### 6.2 `servers`

Назначение: server operations context.

Целевая структура:

```text
servers/
  domain/
    server.py
    access.py
    terminal.py
    monitoring.py
    memory.py
    agents.py
  services/
    server_inventory.py
    server_access.py
    server_query.py
    terminal_session.py
    sftp_service.py
    linux_inspection.py
    monitoring_service.py
    agent_run_service.py
    memory_application.py
  adapters/
    django_server_repository.py
    django_memory_event_repository.py
    django_memory_snapshot_repository.py
    django_memory_store.py
    paramiko_ssh_gateway.py
    rdp_gateway.py
  views/
    server_pages.py
    server_helpers.py
    server_crud.py
    server_ops.py
    server_auth_session.py
    server_groups.py
    server_shares.py
    server_context.py
    server_files.py
    server_linux_ui_workloads.py
    server_linux_ui.py
    server_knowledge.py
    server_memory.py
    server_monitoring_actions.py
    server_monitoring.py
    server_agents.py
    server_agent_runs.py
  consumers/
    ssh_terminal.py
    rdp_terminal.py
    agent_live.py
```

Правила:

- `servers/views/_views_all.py` остаётся только compatibility shim; новая логика идёт в тематические modules, а compatibility re-export живёт в `servers/views/__init__.py`.
- `servers/adapters/django_memory_store.py` надо разложить, потому что перенос из `app` был только первым шагом.
- Terminal AI code уже частично вынесен в `servers/services/terminal_ai/*`; нужно продолжать до тонкого `SSHTerminalConsumer`.
- `servers` не должен импортировать `studio` напрямую для skill promotion. Нужен порт или событие.

### 6.3 `studio`

Назначение: automation/pipeline context.

Целевая структура:

```text
studio/
  domain/
    pipeline_graph.py
    pipeline_run.py
    node_contracts.py
    triggers.py
    skills.py
  services/
    pipeline_service.py
    pipeline_run_service.py
    trigger_service.py
    skill_service.py
    mcp_service.py
    notification_service.py
  executor/
    engine.py
    registry.py
    nodes/
      agent_react.py
      agent_multi.py
      ssh_command.py
      llm_query.py
      mcp_call.py
      logic_condition.py
      logic_merge.py
      logic_wait.py
      human_approval.py
      output_report.py
      output_webhook.py
      output_email.py
      output_telegram.py
  adapters/
    django_pipeline_repository.py
    django_skill_repository.py
    email_gateway.py
    telegram_gateway.py
    mcp_gateway.py
```

Правила:

- `PipelineExecutor` должен стать facade/backward-compatible wrapper, а не местом для новой node logic.
- Новый node type добавляется через `BaseNode` + registry + test.
- `studio` должен ходить в `servers` только через публичные services/ports, а не через models.

### 6.4 `app`

Назначение: shared pure kernel and infrastructure-light services.

Целевая структура:

```text
app/
  agent_kernel/
    domain/
    memory/
      ports.py
      types.py
      compaction.py
      dreams.py
      repair.py
      redaction.py
      server_cards.py
    runtime/
    permissions/
    tools/
  core/
    llm_gateway.py
    model_config.py
  tools/
    safety.py
```

Правила:

- `app.agent_kernel` не импортирует Django.
- `app.agent_kernel` не импортирует `servers`, `studio`, `core_ui`.
- Memory algorithms могут жить в `app.agent_kernel.memory`, но persistence и Django transactions должны жить в `servers/adapters/*`.
- `app/core/llm.py` должен перестать напрямую зависеть от `core_ui` logging/budget models. Нужны callbacks/decorators или отдельный adapter.

## 7. Целевая структура frontend

React/Vite часть должна перейти от "page owns everything" к feature slices:

```text
frontend/src/
  api/
    httpClient.ts
    auth/
    servers/
    studio/
    settings/
    terminal/
    agents/
  features/
    servers/
      hooks/
      components/
      state/
      types.ts
    terminal/
    linux-ui/
    pipeline-editor/
    settings/
    agents/
  pages/
    thin route wrappers only
```

Целевые frontend roles:

- `HttpClient`: CSRF, credentials, JSON/blob, errors, demo fallback policy.
- `WebSocketFactory`: terminal/RDP/pipeline live socket URL creation.
- `PipelineGraphService`: normalize, validate, patch, serialize graph.
- `PipelineEditorController`: save/run/assistant/run-monitor orchestration.
- `TerminalSessionController`: tabs, connection lifecycle, AI state.
- `LinuxWorkspaceController`: window state, active app state, refresh policy.
- Presentational components: только props-in/events-out.

Правила:

- Новый frontend code не должен импортировать `@/lib/api` напрямую.
- Сначала переносить exports в `@/api`, затем физически выносить implementation из `lib/api.ts`.
- Page files должны постепенно стать route wrappers.
- Для сложных UI workflows использовать reducers/controllers, а не россыпь `useState` в page component.

## 8. Главные архитектурные риски

| Риск | Уровень | Почему опасно | Что делать |
| --- | --- | --- | --- |
| Рост `servers/adapters/django_memory_store.py` | Critical | Новый god-file вместо старого | Срочно разложить на ingestion/dreams/overview/promotion/repositories |
| Прямой импорт `studio` из `servers` | High | Ломает bounded context и создаёт циклическое давление | Skill promotion через port/domain event |
| `studio/pipeline_executor.py` остаётся центром node logic | High | Новый node требует править legacy executor | Мигрировать node types в `studio/executor/nodes/*` |
| `servers/consumers/ssh_terminal.py` слишком толстый | High | SSH/WebSocket/AI/memory невозможно тестировать изолированно | Выделить session, transport, AI coordinator, history recorder |
| `src/lib/api.ts` остаётся глобальным API-монолитом | High | Любая frontend feature тянет все типы и transport | Split by bounded context через `src/api/*` |
| View god-files получают новую логику | High | Рефакторинг откатывается назад | CI/team rule: no new logic in `_views_all.py` |
| Baseline updates вместо рефакторинга | Medium | Фитнес-метрики перестают защищать архитектуру | Baseline менять только осознанно после ревью |
| JSON fields без typed value objects | Medium | Схемы pipeline/memory/runtime ломаются тихо | Ввести validators/value objects |

## 9. Дорожная карта миграции

### Phase 0. Зафиксировать правила и убрать текущий красный guard

Цель: архитектурные проверки должны снова быть зелёными.

Статус 2026-05-26: выполнено. `python scripts/check_architecture_sizes.py` проходит, import-linter проходит, `servers/adapters/django_memory_store.py` уменьшен ниже baseline.

Шаги:

1. Уменьшить `servers/adapters/django_memory_store.py` ниже baseline `3819`, лучше не просто на 5 строк, а вынести первый cohesive блок.
2. Не обновлять baseline как быстрый обход, если нет отдельного решения команды.
3. Закрепить правило: новая логика не добавляется в:
   - `servers/views/_views_all.py`
   - `core_ui/views/_views_all.py`
   - `studio/views/_views_all.py`
   - `studio/pipeline_executor.py`
   - `servers/adapters/django_memory_store.py`
   - `frontend/src/lib/api.ts`
4. Добавить короткий migration note в каждый shim, где его ещё нет.

Success criteria:

- `python scripts/check_architecture_sizes.py` проходит.
- `lint-imports --no-cache` проходит.
- Новые PR не увеличивают legacy god-files.

### Phase 1. Завершить memory architecture migration

Статус сейчас: перенос из `app.agent_kernel.memory.store` в `servers.adapters.django_memory_store` сделан, но декомпозиция не завершена.

Обновление 2026-05-26:

- `_SnapshotCandidate`, `_OperationalPattern` и shared constants вынесены в `app/agent_kernel/memory/types.py`.
- `app.agent_kernel.memory.repair` очищен от Django/feature-app imports.
- ORM-specific auto revalidation maintenance вынесен в `servers/adapters/django_memory_repair.py`.
- Promote-skill переведён на `SkillPromotionGateway`: `servers` больше не импортирует `studio.*` из memory adapter.
- MCP runtime переведён на `MCPRuntimeProvider`: legacy `servers/mcp_tool_runtime.py` shim удалён без нарушения `servers-no-studio`.
- Snapshot/episode/revalidation serializers вынесены в `servers/adapters/django_memory_serializers.py`; pure snapshot utilities вынесены в `app/agent_kernel/memory/snapshot_utils.py`; pure pattern utilities вынесены в `app/agent_kernel/memory/pattern_utils.py`; overview read-model вынесен в `servers/adapters/django_memory_overview.py`.
- Runbook/recipes search вынесен в `servers/adapters/django_memory_runbooks.py`; archive/purge/promote snapshot actions вынесены в `servers/adapters/django_memory_snapshot_actions.py`.
- Django ingestion и nearline compaction вынесены в `servers/adapters/django_memory_ingestion.py`; shared line filters вынесены в pure `app/agent_kernel/memory/line_filters.py`.
- Dream snapshot candidate builder вынесен в pure `app/agent_kernel/memory/dream_candidates.py`.
- Snapshot upsert/revalidation repository вынесен в `servers/adapters/django_memory_snapshots.py`; operational pattern mining/promotion вынесен в `servers/adapters/django_memory_patterns.py`; LLM distillation/enhancement вынесен в `servers/adapters/django_memory_llm.py`; manual knowledge bridge вынесен в `servers/adapters/django_memory_manual.py`; dream-cycle orchestration, retention и schedule helpers вынесены в `servers/adapters/django_memory_dreams.py`; fact/change/incident recording workflows вынесены в `servers/adapters/django_memory_recording.py`; repair/maintenance workflow вынесен в `servers/adapters/django_memory_repair.py`; prompt card read-models вынесены в `servers/adapters/django_memory_cards.py`; `django_memory_store.py` уменьшен до 647 строк.
- Memory endpoints вынесены в `servers/views/server_memory.py`; knowledge endpoints вынесены в `servers/views/server_knowledge.py`; monitoring endpoints вынесены в `servers/views/server_monitoring.py` и `servers/views/server_monitoring_actions.py`; SFTP/file endpoints вынесены в `servers/views/server_files.py`; agent endpoints разделены между `servers/views/server_agents.py` и `servers/views/server_agent_runs.py`; Linux UI endpoints разделены между `servers/views/server_linux_ui.py` и `servers/views/server_linux_ui_workloads.py`; group/share/context endpoints вынесены в `servers/views/server_groups.py`, `servers/views/server_shares.py`, `servers/views/server_context.py`; server CRUD/detail/reveal endpoints вынесены в `servers/views/server_crud.py`; connection test/execute/OS-detect endpoints вынесены в `servers/views/server_ops.py`; master-password session endpoints вынесены в `servers/views/server_auth_session.py`; SSR/bootstrap views вынесены в `servers/views/server_pages.py`; shared helpers вынесены в `servers/views/server_helpers.py`; `servers/views/_views_all.py` уменьшен до 26 строк.
- `ServerPicker` вынесен в `src/components/terminal/ServerPicker.tsx`; `TerminalPage.tsx` уменьшен до 1309 строк.
- `SftpTransferQueue` вынесен в `src/components/terminal/SftpTransferQueue.tsx`; `SftpPanel.tsx` уменьшен до 840 строк.
- `LinuxUiPanel.tsx` удержан ниже legacy baseline за счет typed mapping для mobile window classes; текущий размер 4156 строк.
- LLM usage logging вынесен в `app/core/llm_usage.py`; async logging на SQLite больше не запускает detached DB writer, из-за которого memory tests ловили `database table is locked`.
- Frontend guard восстановлен без отката локализации: `MCPForm` вынесен в `src/components/studio/MCPForm.tsx`, report modal агентов вынесен в `src/components/studio/AgentReportModal.tsx`.
- `PipelineRunsPage.tsx` стал route-wrapper вокруг `PipelineRunDetail`, а copy для run dialog в `PipelineEditorPage.tsx` вынесен в `PipelineEditorCopy`; architecture guard снова зелёный без baseline bump.
- `StudioPage.tsx` вернулся ниже baseline: activity text helpers вынесены в `StudioActivityText`, trigger helpers вынесены в `StudioPipelineTriggers`.
- Тестовый settings изолирован на SQLite; targeted backend tests проходят без внешнего Postgres.

Целевая декомпозиция:

```text
app/agent_kernel/memory/
  ports.py
  types.py
  compaction.py
  dreams.py
  repair.py
  redaction.py
  server_cards.py

servers/adapters/
  django_memory_store.py          # facade only
  django_memory_repositories.py   # ORM queries

servers/services/
  memory_ingestion.py
  memory_compaction.py
  memory_dreams.py
  memory_repair.py
  memory_overview.py
  memory_promotion.py
```

Шаги:

1. [done] Перенести `_SnapshotCandidate`, `_OperationalPattern` и shared constants из `store.py` в `app/agent_kernel/memory/types.py`, если они реально pure.
2. [done] Убрать импорт `servers.models` из `app.agent_kernel.memory.repair`.
3. Разделить `DjangoServerMemoryStore` на facade + focused services:
   - ingestion,
   - compaction,
   - dream candidate builder,
   - overview reader,
   - snapshot promotion,
   - repair/revalidation,
   - repository layer.
4. [done] Убрать прямые imports `studio.*` из `servers.adapters.django_memory_store`.
5. Для promote-skill использовать один из подходов:
   - domain event `SkillDraftPromoted`,
   - [done] `SkillPromotionGateway` protocol,
   - публичный `studio.services.skill_service.SkillService`, подключаемый на composition layer.
6. Проверять после каждого шага:
   - `pytest tests/test_ops_agent_kernel.py`
   - `pytest tests/test_servers_api_smoke.py`
   - `python scripts/check_architecture_sizes.py`

Success criteria:

- `app.agent_kernel` не импортирует Django и feature apps.
- `servers/adapters/django_memory_store.py` меньше 800-1000 строк.
- Memory tests не требуют изменения публичных API.
- Skill promotion не создаёт прямой зависимости `servers -> studio`.

### Phase 2. Разложить backend view god-files

Порядок:

1. [done] `servers/views/_views_all.py`
2. [done] `studio/views/_views_all.py`
3. [done] `core_ui/views/_views_all.py`

Правильный pattern для каждого endpoint group:

```text
view -> request DTO/validation -> use case/service -> repository/gateway -> presenter -> JsonResponse
```

Пример для memory endpoints:

```text
servers/views/server_memory.py
  server_memory_overview()
  server_memory_run_dreams()
  server_memory_update_policy()
  server_memory_archive_snapshot()

servers/services/memory_application.py
  MemoryApplicationService

servers/adapters/django_memory_repositories.py
  DjangoMemorySnapshotRepository
  DjangoMemoryPolicyRepository
```

Success criteria:

- URL names and response shape stable.
- Existing tests pass.
- Moved endpoint groups covered by focused API tests.
- `_views_all.py` shrinks and eventually becomes empty compatibility shim.

Текущий статус:

- [done] Memory endpoint group moved to `servers/views/server_memory.py`.
- [done] `servers/urls.py` routes memory paths through `server_memory.*`.
- [done] Knowledge endpoint group moved to `servers/views/server_knowledge.py`.
- [done] `servers/urls.py` routes knowledge paths through `server_knowledge.*`.
- [done] Monitoring dashboard/status/refresh/health endpoint group moved to `servers/views/server_monitoring.py`.
- [done] Monitoring alerts/watchers/config/AI analysis endpoint group moved to `servers/views/server_monitoring_actions.py`.
- [done] `servers/urls.py` routes monitoring paths through the new monitoring modules.
- [done] SFTP/file endpoint group moved to `servers/views/server_files.py`.
- [done] `servers/urls.py` routes file paths through `server_files.*`.
- [done] Agent config/schedule/launch endpoint group moved to `servers/views/server_agents.py`.
- [done] Agent run/control/task endpoint group moved to `servers/views/server_agent_runs.py`.
- [done] `servers/urls.py` routes agent paths through `server_agents.*` and `server_agent_runs.*`.
- [done] Linux UI read-only endpoint group moved to `servers/views/server_linux_ui.py`.
- [done] Linux UI workload/action endpoint group moved to `servers/views/server_linux_ui_workloads.py`.
- [done] `servers/urls.py` routes Linux UI paths through `server_linux_ui.*` and `server_linux_ui_workloads.*`.
- [done] Group CRUD/membership/subscription and bulk-update endpoints moved to `servers/views/server_groups.py`.
- [done] Server share list/create/revoke endpoints moved to `servers/views/server_shares.py`.
- [done] Global/group context endpoints moved to `servers/views/server_context.py`.
- [done] `servers/urls.py` routes group/share/context paths through the new modules.
- [done] Server create/update/delete/get/reveal endpoints moved to `servers/views/server_crud.py`.
- [done] Connection test, command execute, and OS-detect endpoints moved to `servers/views/server_ops.py`.
- [done] Master-password session endpoints moved to `servers/views/server_auth_session.py`.
- [done] `servers/urls.py` routes CRUD/ops/session paths through the new modules.
- [done] SSR/bootstrap page views moved to `servers/views/server_pages.py`.
- [done] Shared access/share/password/OS helpers moved to `servers/views/server_helpers.py`.
- [done] `servers/views/_views_all.py` reduced to 26 lines and kept only as a compatibility shim.
- [done] Removed stale `servers.views._views_all -> app.runtime_limits` import-linter exception and removed the `_views_all.py` legacy size baseline.
- [done] Compatibility re-export kept in `servers/views/__init__.py`.
- [done] Studio notification settings/test endpoints and notification config helpers moved to `studio/views/notification_views.py`.
- [done] `studio/urls.py` routes notification paths through `notification_views.*`.
- [done] Studio pipeline template endpoints moved to `studio/views/template_views.py`.
- [done] Studio server dropdown endpoint moved to `studio/views/server_views.py`.
- [done] `studio/urls.py` routes template/server paths through the new modules.
- [done] Studio MCP pool CRUD/test/tools/templates endpoints moved to `studio/views/mcp_views.py`.
- [done] `studio/urls.py` routes MCP paths through `mcp_views.*`.
- [done] Studio share-users endpoint moved to `studio/views/share_views.py`.
- [done] Studio trigger CRUD/webhook receive endpoints moved to `studio/views/trigger_views.py`.
- [done] `studio/urls.py` routes share-users and trigger paths through the new modules.
- [done] Studio run list/detail/stop/approval endpoints moved to `studio/views/run_views.py`.
- [done] `studio/urls.py` routes run paths through `run_views.*`.
- [done] Compatibility paths kept for `studio.views.get_executor_for_run`, `studio.views.update_runtime_control`, and `studio.views.httpx`.
- [done] Studio agent config CRUD endpoints moved to `studio/views/agent_views.py`.
- [done] `studio/urls.py` routes agent paths through `agent_views.*`.
- [done] Studio skill catalog/detail/templates/scaffold/validate/workspace endpoints moved to `studio/views/skill_views.py`.
- [done] `studio/urls.py` routes skill paths through `skill_views.*`.
- [done] Studio pipeline CRUD/manual-run/clone/run-history endpoints moved to `studio/views/pipeline_views.py`.
- [done] `studio/urls.py` routes pipeline CRUD/run paths through `pipeline_views.*`.
- [done] Studio pipeline assistant endpoint moved to `studio/views/pipeline_assistant_views.py`.
- [done] Studio pipeline assistant preview/risk helpers moved to `studio/views/pipeline_assistant_preview.py`.
- [done] `studio/urls.py` routes pipeline assistant through `pipeline_assistant_views.*`.
- [done] Studio common/pipeline/agent/skill helper groups moved to `studio/views/common.py`, `studio/views/pipeline_helpers.py`, `studio/views/agent_helpers.py`, and `studio/views/skill_helpers.py`.
- [done] Removed stale `studio.views._views_all -> app.runtime_limits` import-linter exception; pipeline/run limit checks now reuse the existing `studio.trigger_dispatch -> app.runtime_limits` boundary.
- [done] `studio/views/_views_all.py` reduced to 60 lines and kept only as a compatibility re-export shim.
- [done] Core UI auth/session/csrf/ws-token/login/logout endpoints and frontend redirects moved to `core_ui/views/auth_views.py`.
- [done] `core_ui/urls.py` routes auth and frontend redirect paths through `auth_views.*`; package-level re-export kept in `core_ui/views/__init__.py`.
- [done] Core UI runtime singletons moved to `core_ui/views/runtime.py`.
- [done] Core UI health endpoint moved to `core_ui/views/health_views.py`; `core_ui/urls.py` routes `/api/health/` through `health_views.api_health`.
- [done] Core UI legacy Django-rendered public/main page views moved to `core_ui/views/page_views.py`; package-level re-export kept for compatibility.
- [done] Core UI access management users/groups/permissions endpoints moved to `core_ui/views/access_views.py` and `core_ui/views/access_group_views.py`; `core_ui/urls.py` routes `/api/access/*` through focused access modules.
- [done] Core UI model/tool discovery endpoints moved to `core_ui/views/model_views.py`; `core_ui/urls.py` routes `/api/models/*` through `model_views.*`.
- [done] Core UI settings config/check endpoints moved to `core_ui/views/settings_config_views.py`; activity log/export endpoint moved to `core_ui/views/settings_activity_views.py`; `core_ui/urls.py` routes `/api/settings/*` through focused settings modules.
- [done] Core UI disk/legacy agent/upload endpoints moved to `core_ui/views/utility_views.py`.
- [done] Core UI legacy IDE page/file endpoints moved to `core_ui/views/ide_views.py`; workspace path checks now use `Path.relative_to()` instead of string-prefix matching.
- [done] Core UI legacy RAG knowledge-base endpoints moved to `core_ui/views/rag_views.py`.
- [done] Core UI admin dashboard/billing endpoints moved to `core_ui/views/admin_views.py` and `core_ui/views/admin_billing.py`; `core_ui/urls.py` routes admin dashboard APIs through `admin_views.*`.
- [done] Core UI chat/Cursor APIs moved to `core_ui/views/chat_views.py` and `core_ui/views/chat_helpers.py`; package-level and `_views_all.py` compatibility re-exports kept.
- [done] Core UI legacy settings page moved to `core_ui/views/settings_page_views.py`.
- [done] `core_ui/views/_views_all.py` reduced to 40 lines and kept only as a compatibility re-export shim.
- [done] Focused backend suite passes: 150 tests, including `tests/test_studio_api_smoke.py` and `tests/test_core_ui_api_smoke.py`.

### Phase 3. Завершить Studio node-registry architecture

Статус сейчас:

- `studio/executor/engine.py` есть.
- `studio/executor/registry.py` есть.
- `BaseNode` есть.
- Мигрированы `output/report` и `output/webhook`.
- `studio/pipeline_executor.py` всё ещё главный legacy executor.

Порядок миграции node types:

1. Low-risk pure nodes:
   - `logic/merge`
   - `logic/condition`
   - `logic/wait`
2. Output nodes:
   - `output/email`
   - `output/telegram`
   - `output/report`
   - `output/webhook`
3. Integration nodes:
   - `mcp/call`
   - `ssh/command`
   - `llm/query`
4. Agent nodes:
   - `agent/react`
   - `agent/multi`

Для каждого node:

- Создать class в `studio/executor/nodes/*`.
- Зарегистрировать через `registry.register`.
- Написать unit test на `BaseNode.execute()`.
- Сверить output с legacy executor golden fixture.
- Удалить соответствующую ветку из `pipeline_executor.py`.

Success criteria:

- Новый node добавляется без правки `pipeline_executor.py`.
- `pipeline_executor.py` становится facade или удаляется.
- Node tests не требуют полного Django request cycle.

### Phase 4. Разобрать SSH terminal consumer

Статус сейчас: feature-ready baseline завершён. Terminal consumer разгружен по всем ключевым boundaries: input parsing, connection records, command recorder, AI preferences/report/planning/decision/memory/explain, agent target context, access/secret lookup, connect options, SSH lifecycle, event DTOs, plan-item shaping и snapshotting вынесены в focused services. `servers/consumers/ssh_terminal.py` всё ещё большой, но теперь основной риск локализован в queue-runner; новые features должны добавляться через services, а не расширять consumer.

Целевая структура:

```text
servers/consumers/ssh_terminal.py
  SSHTerminalConsumer as protocol adapter

servers/services/terminal_session.py
  TerminalSessionService

servers/services/terminal_connection.py
  TerminalConnectionService / SshTransport

servers/services/terminal_ssh_lifecycle.py
  open/resize/close interactive AsyncSSH PTY lifecycle

servers/services/terminal_connection_options.py
  known_hosts + SSH timeout/keepalive option assembly

servers/services/terminal_access.py
  user capability, terminal-open ACL, session limits, secret lookup

servers/services/terminal_connection_records.py
  register/touch/close persistence for live terminal sessions

servers/services/terminal_command_recorder.py
  manual/agent command-history recording and live recent-activity shaping

servers/services/terminal_input.py
  terminal input parsing, command marker policy, command classification

servers/services/terminal_events.py
  TerminalEventRouter / DTOs

servers/services/terminal_snapshotting.py
  pre-execution file snapshot capture

servers/services/terminal_agent_context.py
  extra-target ACL, ServerTarget shaping, layered memory prompt context

servers/services/terminal_ai/
  coordinator.py
  decision.py
  session.py
  preferences.py
  plan_items.py
  planning.py
  report_generation.py
  output_explanation.py
  memory_extraction.py
  memory.py
  reporter.py
  tools/

servers/services/command_history.py
  CommandHistoryRecorder

servers/services/snapshot_service.py
  SnapshotCoordinator
```

Шаги:

1. [done] Вынести pure terminal input parsing, marker policy, install/streaming classifiers.
2. [done] Вынести terminal connection open/heartbeat/close persistence.
3. [done] Вынести command history recording.
4. [done] Вынести Terminal-AI preference normalization.
5. [done] Вынести report LLM streaming из consumer.
6. [done] Вынести durable memory extraction bridge.
7. [done] Вынести command planning LLM/JSON workflow.
8. [done] Вынести recovery/step-decision LLM workflow.
9. [done] Вынести output explanation workflow.
10. [done] Вынести agent extra-target ACL/context helpers.
11. [done] Вынести terminal access/session-limit/secret lookup.
12. [done] Вынести SSH connect kwargs assembly.
13. [done] Выделить typed WebSocket event DTO builders.
14. [done] Вынести SSH open/resize/close lifecycle helpers.
15. [done] Вынести plan-item / execution-mode shaping.
16. [done] Вынести terminal snapshotting.
17. [done] Добавить focused tests с fake LLM / fake SSH / fake ORM boundaries.

Success criteria:

- Terminal AI workflow pieces можно тестировать без Channels test client.
- SSH lifecycle можно тестировать fake transport-ом.
- Architecture/import boundaries зелёные.
- Дальнейшее уменьшение `SSHTerminalConsumer` ниже 800 строк остаётся future hardening, а не обязательным условием для новых features.

### Phase 5. Разложить frontend API и feature controllers

Статус сейчас:

- `src/api/*` создан.
- `src/api/index.ts` re-export-ит `@/lib/api`.
- Большинство pages/components всё ещё импортируют `@/lib/api`.

Порядок:

1. Создать `src/api/httpClient.ts` и перенести туда `apiFetch`, CSRF, errors, demo fallback policy.
2. Перенести auth functions в `src/api/auth/index.ts`.
3. Перенести server functions в `src/api/servers/index.ts`.
4. Перенести studio functions в `src/api/studio/index.ts`.
5. Перенести settings/agents/terminal functions.
6. После каждого переноса оставлять compatibility export из `src/api/index.ts`, но убирать прямые imports из pages.
7. Запретить новые imports из `@/lib/api`.

Затем feature controllers:

```text
features/pipeline-editor/
  domain/pipelineGraphService.ts
  hooks/usePipelineEditorController.ts
  components/*

features/linux-ui/
  hooks/useLinuxWorkspaceController.ts
  state/linuxWorkspaceReducer.ts
  components/*

features/servers/
  hooks/useServerInventoryController.ts
  components/*

features/settings/
  hooks/useMemorySettingsController.ts
```

Success criteria:

- `src/lib/api.ts` меньше 800-1000 строк или удалён.
- `PipelineEditorPage.tsx`, `Servers.tsx`, `LinuxUiPanel.tsx`, `SettingsPage.tsx` превращаются в route/container shells.
- Сложная логика покрыта Vitest tests на services/hooks/reducers.

### Phase 6. Ввести value objects и typed JSON contracts

Где нужно:

- pipeline graph,
- node config,
- pipeline runtime control,
- route state,
- memory snapshot metadata,
- command execution result,
- server access grants,
- terminal AI settings.

Пример:

```python
@dataclass(frozen=True)
class PipelineGraph:
    nodes: tuple[PipelineNode, ...]
    edges: tuple[PipelineEdge, ...]

    def validate(self) -> list[ValidationError]:
        ...
```

Правила:

- Django JSONField остаётся persistence detail.
- Внутри services используется typed value object.
- Mapping ORM <-> domain object живёт в mapper/repository, а не во view.

Success criteria:

- Domain invariants тестируются без HTTP.
- Ошибки схемы ловятся до запуска pipeline.
- API response DTO формируется presenters/serializers, а не случайными dict-ами во views.

### Phase 7. Удалить compatibility shims

Каждый shim должен иметь:

- текущую роль,
- target module,
- критерий удаления,
- тесты, которые доказывают parity,
- issue/task id или migration note.

Кандидаты:

- `servers/views/__init__.py` re-export.
- `core_ui/views/__init__.py` re-export.
- `studio/views/__init__.py` re-export.
- `servers/adapters/memory_store.py` stable re-export.
- `frontend/src/api/index.ts` broad re-export.
- legacy imports from `@/lib/api`.

Shims нормальны во время миграции, но без срока удаления они становятся архитектурой.

## 10. Публичные интерфейсы между bounded contexts

### `core_ui`

```python
class AccessPolicyService:
    def can_use_feature(self, user, feature: str) -> bool: ...
    def effective_permissions(self, user) -> dict[str, bool]: ...

class ManagedSecretService:
    def get_secret(self, namespace: str, object_id: int, key: str) -> str | None: ...
    def set_secret(self, namespace: str, object_id: int, key: str, value: str) -> None: ...
```

### `servers`

```python
class ServerQueryService:
    def get_accessible_server(self, user, server_id: int): ...
    def list_accessible_servers(self, user): ...

class AgentRunService:
    def launch_run(self, agent_id: int, user, request: AgentRunRequest): ...
    def stop_run(self, run_id: int, user) -> None: ...
```

### `studio`

```python
class PipelineRunService:
    def create_run(self, pipeline_id: int, user, request: PipelineRunRequest): ...
    async def execute_run(self, run_id: int) -> PipelineRunResult: ...

class SkillPromotionGateway:
    def promote_memory_draft(self, user_id: int, payload: SkillDraftPayload) -> SkillPromotionResult: ...
```

### `app.agent_kernel`

```python
class MemoryStore(Protocol): ...
class LLMGateway(Protocol): ...
class ToolGateway(Protocol): ...
class SkillProvider(Protocol): ...
```

## 11. Domain events

Для снижения прямых imports между contexts использовать typed domain events. На первом этапе реализация может остаться на Django signals, но payload должен быть typed dataclass.

События:

- `CommandExecuted`
- `TerminalSessionClosed`
- `ServerAlertOpened`
- `AgentRunCompleted`
- `PipelineRunCompleted`
- `MemorySnapshotPromoted`
- `SkillDraftPromoted`
- `ServerKnowledgeUpdated`

Правило: handler живёт в принимающем context, а emitter не импортирует детали получателя.

## 12. Transaction and side-effect rules

Обязательные правила:

- Views не должны напрямую делать сложные `.save()` workflows.
- Application services владеют transactions.
- Domain services не импортируют Django models.
- Long-running operations не держат DB transaction во время SSH, LLM, MCP, email, Telegram, HTTP calls.
- Внешние calls должны идти через gateway interfaces.
- Retry/idempotency logic должна быть в application service или job layer, а не во view.

## 13. Testing strategy

Минимальный набор тестов для безопасной миграции:

```bash
python scripts/check_architecture_sizes.py
lint-imports --no-cache
pytest tests/test_ops_agent_kernel.py
pytest tests/test_servers_api_smoke.py
pytest app/test_studio_pipeline_features.py
```

Для отдельных фаз:

- Memory: unit tests на pure memory algorithms + integration tests на `DjangoServerMemoryStore` facade.
- Views: endpoint-level response contract tests.
- Pipeline nodes: golden tests на каждый `BaseNode.execute()`.
- Terminal: WebSocket transcript tests + fake SSH gateway + fake LLM gateway.
- Frontend API: Vitest tests на `HttpClient` и context API modules.
- Frontend controllers: tests на reducers/hooks без browser-heavy setup.

## 14. Architecture fitness functions

Автоматические проверки должны остаться обязательными:

- `app.agent_kernel` не импортирует Django, `servers`, `studio`, `core_ui`.
- `app.core` не импортирует feature apps.
- `app.tools` не импортирует feature apps, кроме временных documented shims.
- `core_ui` не импортирует `servers`/`studio`, кроме desktop/admin integration shims.
- `servers` не импортирует `studio`.
- `studio` не импортирует `servers`.
- Legacy god-files не растут.
- Новые Python/TS/TSX файлы свыше 500 строк требуют архитектурного обоснования.
- Новые файлы свыше 1000 строк должны блокироваться.

Текущее действие по fitness:

1. Продолжать запускать `python scripts/check_architecture_sizes.py` в CI и локально перед PR.
2. Не убирать import-linter exceptions молча. Каждое удаление exception должно сопровождаться тестом или проверкой.
3. Следующий fitness target: убрать следующий direct cross-context import из `.importlinter`, начиная с самого дешёвого exception.

## 15. Immediate next actions

Приоритетный порядок на ближайший refactoring sprint:

1. Вынести из `servers/adapters/django_memory_store.py` следующий безопасный блок:
   - оставшиеся facade wrappers, если появится естественный module boundary,
   - либо не наращивать facade обратно: текущий размер 647 строк.
2. Запретить новые imports из `@/lib/api`; новые frontend calls делать через `@/api`.
3. Мигрировать ещё 2-3 простых Studio nodes в `studio/executor/nodes/*`.
4. Новые backend features добавлять через уже выделенные services/adapters, не расширяя compatibility shims.
5. Для дальнейшего hardening уменьшать queue-runner в `SSHTerminalConsumer` инкрементально, с transcript tests.

## 16. Definition of Done для перехода

Переход на нормальную архитектуру можно считать выполненным не когда файлы переименованы, а когда выполняются эти условия:

- `python scripts/check_architecture_sizes.py` проходит стабильно.
- `lint-imports --no-cache` проходит без legacy exceptions для ключевых границ `app.agent_kernel`, `servers <-> studio`.
- `servers/views/_views_all.py`, `core_ui/views/_views_all.py`, `studio/views/_views_all.py` больше не содержат основной бизнес-логики.
- `servers/consumers/ssh_terminal.py` является Channels adapter + queue runner; SSH/AI/memory workflows вынесены в services и тестируются отдельно.
- `studio/pipeline_executor.py` больше не является местом добавления node types.
- `src/lib/api.ts` не является главным API-клиентом проекта.
- Page components не управляют всей domain/application логикой.
- Domain logic тестируется без Django request objects и без browser UI.
- Новые features добавляются через services/ports/registries, а не через рост god-files.

## 17. Финальная рекомендация

Проект уже движется в правильном направлении. Не нужен rewrite. Нужна строгая последовательная миграция:

1. Защитить границы и не давать god-files расти.
2. Завершить перенос Django-specific memory logic в `servers`, но разложить новый adapter на focused services/repositories.
3. Довести `app.agent_kernel` до чистого Python kernel.
4. Перевести Studio execution на node registry.
5. Разобрать backend views на thin adapters и application services.
6. Разобрать SSH terminal consumer на transport/session/AI/memory components.
7. Разделить frontend API и page-level logic по feature slices.
8. Удалять shims только после parity tests.

Такой подход даст расширяемость без большого взрыва: новые server features, pipeline nodes, memory promotions, tools и UI screens будут добавляться отдельными классами и модулями, а не правками в центральные файлы на 3000-4000 строк.
