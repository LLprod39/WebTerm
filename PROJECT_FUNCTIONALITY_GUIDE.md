# WebTerm / mini_prod — полный функциональный обзор проекта

Этот документ нужен как быстрый, но достаточно полный onboarding по текущему живому коду в `C:\WebTrerm`.

Он покрывает:

- что это за продукт;
- какие пользовательские сценарии он уже поддерживает;
- какие backend/frontend/desktop-модули реально активны;
- какие сущности, API, WebSocket, фоновые воркеры и management-команды есть в проекте;
- какие ограничения и legacy-следы нужно понимать до начала доработок.

## 1. Что это за проект

`WebTerm` — это операционная платформа для работы с серверами и инфраструктурой в одном месте.

По факту здесь объединены:

- инвентарь серверов и групп;
- SSH и RDP доступ;
- общий инфраструктурный контекст и заметки;
- AI-агенты по серверам;
- layered AI memory по серверам;
- monitoring, alerts и watcher-drafts;
- Studio для pipelines, skills, MCP и notifications;
- Windows desktop-клиент;
- служебные MCP/Keycloak/automation-скрипты.

Технический стек:

- backend: Django 5 + Channels + Daphne;
- realtime: WebSocket через Channels;
- frontend: React 18 + TypeScript + Vite + TanStack Query + xterm.js + Tailwind + Radix UI;
- desktop: WinUI 3 + WebView2;
- БД: SQLite по умолчанию, PostgreSQL при наличии `POSTGRES_*`;
- realtime layer: `InMemoryChannelLayer` в dev, Redis в production/multi-worker;
- LLM/runtime: собственные provider/runtime/memory/agent-модули в `app/`.

Важно:

- основной SPA-фронтенд находится в `ai-server-terminal-main/`;
- корневой `src/main.tsx` просто реэкспортирует этот SPA;
- Django в основном отдает API, WebSocket и redirect entrypoints в SPA;
- в проекте все еще есть legacy SSR templates и часть legacy view-функций, но основная эксплуатация идет через SPA.

## 2. Карта активных модулей

| Путь | Назначение |
| --- | --- |
| `manage.py` | Django entrypoint, по умолчанию подставляет порт `9000` для `runserver`. |
| `web_ui/` | settings, ASGI/WSGI, root URLs, сборка WebSocket routing. |
| `core_ui/` | auth/session API, admin/access/settings API, middleware, domain auth, desktop API. |
| `servers/` | серверы, группы, SSH/RDP, file manager, Linux UI, monitoring, AI memory, server agents. |
| `studio/` | pipelines, pipeline runs, MCP pool, skills, triggers, templates, notifications. |
| `app/` | общие LLM/runtime/memory/permissions/safety/tools сервисы. |
| `ai-server-terminal-main/` | основной React/Vite SPA. |
| `desktop/` | WinUI 3 desktop-клиент. |
| `docker/` | Dockerfile, nginx/startup runtime-артефакты. |
| `tests/` | backend/integration/unit smoke coverage. |
| `key_mcp.py` | отдельный Keycloak MCP server/tool bridge. |
| `create_mega_pipeline.py` | one-shot генератор большой demo/ops pipeline. |
| `passwords/` | папка есть, но Django app сейчас не подключен. |

## 3. Пользовательский функционал по продуктовым зонам

### 3.1. Авторизация, доступы и административный слой

Проект умеет:

- логин/логаут через web API;
- выдачу auth session payload для SPA;
- выдачу отдельного WebSocket token для terminal/ws;
- desktop login/refresh/logout/me flow с refresh token моделью;
- middleware-based domain auto login через заголовок вроде `REMOTE_USER`;
- автосоздание пользователей из доменного principal при включенной доменной схеме;
- per-user и per-group feature permissions;
- staff-only зоны для dashboard/settings/memory admin;
- журналирование действий пользователя;
- аудит входов, изменений, terminal/file/MCP/pipeline событий;
- хранение managed secrets на сервере.

Живые feature-флаги доступа:

- `servers`
- `dashboard`
- `agents`
- `studio`
- `studio_pipelines`
- `studio_runs`
- `studio_agents`
- `studio_skills`
- `studio_mcp`
- `studio_notifications`
- `settings`
- `orchestrator`
- `knowledge_base`

Публичные пользовательские эффекты:

- скрытие/разрешение разделов SPA;
- ограничение desktop API по bearer token и feature;
- админские таблицы пользователей, групп, прав и activity;
- staff dashboard с активностью, API usage, состоянием флита и alerts.

### 3.2. Инвентарь серверов и группы

Система серверов поддерживает:

- CRUD серверов;
- типы сервера `ssh` и `rdp`;
- auth modes: `password`, `key`, `key_password`;
- хранение зашифрованного секрета аутентификации;
- trusted SSH host keys;
- network/corporate context на сервере;
- теги, заметки, статус активности;
- bulk update серверов;
- CRUD групп серверов;
- group roles: `owner`, `admin`, `member`, `viewer`;
- memberships;
- subscriptions: `follow`, `favorite`;
- group-level rules, forbidden commands и environment vars;
- explicit group permission overrides;
- server sharing между пользователями с опцией передачи контекста;
- reveal password через master password flow;
- bootstrap payload для SPA со списком серверов, групп, owned/shared-статистикой и recent activity.

Отдельные контекстные слои вокруг серверов:

- `GlobalServerRules` — глобальные правила пользователя;
- `ServerGroupKnowledge` — знания/политики на группу;
- `ServerKnowledge` — знания по конкретному серверу;
- `server.notes` и `server.corporate_context`;
- network config с proxy/VPN/bastion/firewall/env metadata.

### 3.3. Терминал, SSH и RDP

Поддерживаются:

- web SSH terminal через WebSocket;
- RDP terminal/session consumer;
- terminal hub с несколькими вкладками;
- minimal terminal view;
- desktop terminal ticket API;
- учет active connections через `ServerConnection`;
- история выполненных команд через `ServerCommandHistory`;
- xterm.js frontend с resize, reconnect, drag-and-drop файлов;
- статусы `connecting`, `connected`, `disconnected`, `error`.

В `TerminalPage` и terminal UI реализованы:

- несколько одновременных SSH tabs на один и тот же сервер;
- быстрый server picker;
- AI panel рядом с терминалом;
- хранение AI preferences в `localStorage`;
- chat mode: `ask` и `agent`;
- execution mode: `auto`, `step`, `fast`;
- авто-отчеты `auto/on/off`;
- подтверждение опасных команд;
- whitelist/blacklist паттернов команд;
- показ suggested/executed commands;
- ручной `ai_clear_memory`.

### 3.4. AI assistant в терминале

Эфемерный terminal AI умеет:

- принимать свободный запрос оператора;
- генерировать команды;
- выполнять команды автоматически или пошагово;
- задавать уточняющие вопросы;
- подтверждать/отменять опасные команды;
- присылать report/progress/recovery messages;
- очищать session memory;
- извлекать durable факты о сервере после работы и сохранять их в долговременную memory/knowledge цепочку.

Это отдельная, краткоживущая память:

- живет в `SSHTerminalConsumer`;
- хранится как `_ai_history`;
- TTL считается по количеству запросов, а не по wall-clock времени;
- не равна layered server memory.

### 3.5. Linux UI workspace

Кроме raw-терминала, проект дает “псевдо-десктоп” для Linux-сервера.

Поддерживаемые подсекции:

- capability detection;
- overview по машине;
- settings snapshot;
- service list;
- service logs;
- service actions `start/stop/restart/reload`;
- process list;
- process actions `terminate/kill_force`;
- log viewer по нескольким источникам;
- disk mounts и size breakdown;
- network interfaces/routes/listening sockets;
- package inventory;
- docker containers/stats/logs/actions.

Linux UI умеет распознавать наличие:

- `systemctl`
- `journalctl`
- `docker`
- `ss`
- `ip`
- `apt/apt-get`
- `dnf`
- `yum`
- `python3`
- `bash/sh`

На frontend это собрано как оконный workspace с launcher/taskbar-поверхностью внутри `LinuxUiPanel.tsx`.

### 3.6. Файловый менеджер / SFTP-подобные операции

Серверный file layer поддерживает:

- list directory;
- read text file;
- write text file;
- upload file;
- download file;
- rename;
- delete;
- mkdir;
- chmod;
- chown.

Frontend `SftpPanel` дает:

- навигацию по директориям;
- просмотр файлов/папок;
- transfer progress;
- скачивание на локальную машину;
- загрузку через file input / drag-and-drop;
- встроенный текстовый редактор для простых правок.

### 3.7. Контекст, knowledge и правила

Проект поддерживает несколько независимых knowledge/context слоев:

- глобальные правила пользователя для всех серверов;
- знания на группу серверов;
- знания на конкретный сервер;
- ручные заметки;
- AI-generated заметки;
- bridge из terminal AI в `ServerKnowledge`;
- bridge из `ServerKnowledge` в layered memory snapshots.

Пользователь может:

- читать и редактировать global context;
- читать и редактировать group context;
- создавать/обновлять/удалять server knowledge;
- управлять server memory snapshots;
- архивировать snapshot;
- продвигать snapshot в note;
- продвигать snapshot в Studio skill.

### 3.8. Monitoring, health checks и alerts

Мониторинг по серверу умеет:

- регулярный health-check;
- quick и deep режим;
- сбор CPU/load/memory/disk/uptime/process_count;
- network bytes;
- разбор failed systemd units;
- разбор log errors и kernel errors;
- docker container state scan;
- автогенерацию `ServerAlert`;
- dashboard со сводкой по флоту;
- историю health checks;
- ручной trigger health check;
- monitoring thresholds config;
- resolve alert.

Поддерживаемые типы alert:

- CPU
- memory
- disk
- service
- log error
- unreachable

Поддерживаемые severity:

- `info`
- `warning`
- `critical`

### 3.9. Watchers и draft-инциденты

Watcher layer анализирует health/alerts/recent agent runs/memory и создает operator-facing draft suggestions.

Он умеет:

- сканировать парк серверов;
- присваивать severity и recommended role;
- формулировать objective;
- прикладывать reasons и memory excerpts;
- сохранять persistent `ServerWatcherDraft`;
- переводить старые draft в resolved;
- отдавать draft list в UI;
- подтверждать draft;
- запускать draft как agent scenario.

Watcher нужен для полуавтоматического triage: не сразу исполнять действия, а сначала показать оператору, что система считает подозрительным.

### 3.10. Layered AI memory по серверам

Это отдельная долговременная система памяти поверх событий эксплуатации сервера.

Основные уровни:

- `ServerMemoryEvent` — L0 raw inbox событий;
- `ServerMemoryEpisode` — L1 compaction по сессиям/окнам;
- `ServerMemorySnapshot` — L2 canonical/archive snapshots;
- `ServerMemoryRevalidation` — очередь устаревших/конфликтных фактов;
- `ServerMemoryPolicy` — user-level policy;
- `BackgroundWorkerState` — состояние фоновых memory workers.

Ingress в память идет из:

- SSH session open/close;
- terminal command history;
- RDP consumer;
- agent live events;
- final agent run summary;
- monitoring health checks;
- alerts;
- watcher drafts;
- manual knowledge;
- terminal AI durable extraction.

Dream/repair pipeline умеет:

- nearline compaction;
- сбор canonical sections `profile`, `access`, `risks`, `runbook`, `recent_changes`, `human_habits`;
- pattern mining из команд;
- создание `pattern_candidate:*`;
- создание `automation_candidate:*`;
- создание `skill_draft:*`;
- confidence decay;
- freshness/revalidation;
- archive старых events/episodes;
- detect fact conflicts.

Settings UI для memory дает:

- overview по snapshots/episodes/revalidation;
- запуск `run-dreams`;
- редактирование policy;
- archive/promote действий по snapshot;
- просмотр состояния workers.

Ограничения текущей реализации:

- policy сейчас user-level, хотя API выглядит server-level;
- `is_enabled=false` не очищает старые active snapshots автоматически;
- `rdp_semantic_capture_enabled` уже хранится, но не является полным hard-gate для RDP ingestion;
- candidate snapshots не входят напрямую в main memory block, но могут попадать в operational recipes.

### 3.11. AI-анализ сервера

Есть отдельный endpoint `ai_analyze_server`, который умеет:

- брать состояние сервера;
- прогонять аналитический LLM-проход;
- выдавать вывод по состоянию/рискам/следующим шагам.

Это отдельный сценарий от terminal AI и от full agent execution.

### 3.12. Server agents

Подсистема `servers/` включает не только Studio agents, но и server-bound agents.

Поддерживаются режимы:

- `mini`
- `full`
- `multi`

Типы агентов:

- `security_audit`
- `log_analyzer`
- `performance`
- `disk_report`
- `docker_status`
- `service_health`
- `custom`
- `security_patrol`
- `deploy_watcher`
- `log_investigator`
- `infra_scout`
- `multi_health`

Server agents умеют:

- CRUD конфигураций агента;
- привязку к нескольким серверам;
- mini mode со списком команд;
- full mode с `goal`, `system_prompt`, `max_iterations`, tools config, stop conditions;
- multi mode для multi-server orchestration;
- schedule minutes;
- per-agent memory policy override;
- manual run;
- scheduled dispatch;
- stop;
- run detail/log/events;
- user reply flow;
- approve plan flow;
- update task;
- AI refine task;
- live streaming через WebSocket;
- dashboard по активным и recent runs.

Модели и runtime данных для run:

- `AgentRun`
- `AgentRunDispatch`
- `AgentRunEvent`
- `iterations_log`
- `tool_calls`
- `plan_tasks`
- `orchestrator_log`
- `runtime_control`
- `pending_question`
- `final_report`

### 3.13. Studio: visual pipelines

`studio/` — это отдельная automation-зона, не равная server agents.

Studio pipelines поддерживают:

- CRUD pipelines;
- clone pipeline;
- manual run;
- просмотр runs;
- stop run;
- approve human-approval node;
- live node/run updates через WebSocket;
- pipeline assistant для генерации/патча graph-а;
- graph versioning;
- шаблоны pipelines;
- server dropdown integration;
- ownership/shared access.

Триггеры pipeline:

- `manual`
- `webhook`
- `schedule`
- `monitoring`

Поддерживаемые node types:

- `trigger/manual`
- `trigger/webhook`
- `trigger/schedule`
- `trigger/monitoring`
- `agent/react`
- `agent/multi`
- `agent/ssh_cmd`
- `agent/llm_query`
- `agent/mcp_call`
- `logic/condition`
- `logic/parallel`
- `logic/merge`
- `logic/wait`
- `logic/human_approval`
- `logic/telegram_input`
- `output/report`
- `output/webhook`
- `output/email`
- `output/telegram`

Pipeline runtime умеет:

- topo/routing processing;
- node-by-node state tracking;
- context propagation;
- approval waits;
- Telegram callback/reply flows;
- webhook payload mapping;
- monitoring-trigger filtering;
- MCP tool execution;
- LLM node execution;
- SSH command node execution;
- output delivery по webhook/email/telegram.

### 3.14. Studio: agent configs

Это отдельный слой reusable агентных конфигов для pipelines.

Поддерживаются:

- name/description/icon;
- system prompt и instructions;
- model и max iterations;
- allowed tools;
- подключение MCP servers;
- подключение skill slugs;
- server scope;
- shared access;
- owner/shared/admin access modes.

Allowed tools в Studio agent config:

- `ssh_execute`
- `read_console`
- `send_ctrl_c`
- `open_connection`
- `close_connection`
- `wait_for_output`
- `report`
- `ask_user`
- `analyze_output`

### 3.15. Studio: skills

Skills в `studio/` — это filesystem-backed knowledge/instruction bundles.

Поддерживаются:

- list skills;
- read detail;
- share access metadata;
- skill templates;
- scaffold skill;
- validate skills;
- workspace browser;
- workspace file read/write;
- ручное создание файлов в skill workspace;
- редактирование `SKILL.md`, scripts, references, assets;
- runtime policy JSON;
- service/category/safety metadata;
- рекомендации инструментов и guardrails.

Есть и системные management-команды:

- `scaffold_skill`
- `validate_skills`

А также folder-level registry/policy/runtime обработчики:

- `skill_registry.py`
- `skill_policy.py`
- `skill_authoring.py`
- `skill_templates.py`

### 3.16. Studio: MCP registry

MCP в проекте поддерживается на двух уровнях:

- Studio MCP server registry;
- отдельные standalone MCP scripts вроде `key_mcp.py`.

Studio MCP registry умеет:

- CRUD MCP server definitions;
- transport `stdio` и `sse`;
- command/args/env конфигурацию;
- URL-конфигурацию для SSE;
- test connection;
- inspect tools;
- templates;
- shared visibility.

### 3.17. Studio: notifications

Notification subsystem поддерживает:

- сохранение notification settings;
- Telegram delivery test;
- Email delivery test;
- конфиг-файл уведомлений;
- использование email и Telegram из pipeline output и approval flows.

### 3.18. Dashboard и аналитика

В продукте есть минимум два dashboard-слоя:

- `AdminDashboard` для staff;
- `UserDashboard` для обычного пользователя.

Admin dashboard показывает:

- online users;
- AI requests today;
- terminals active;
- agent runs stats;
- API usage и cost по провайдерам;
- providers config;
- servers count;
- tasks summary, если tasks app доступен;
- hourly activity;
- top users;
- recent activity;
- fleet health;
- active alerts;
- app version.

User dashboard показывает:

- servers;
- online servers;
- configured agents;
- active runs;
- latest AI analysis;
- active agent runs;
- recent reports/runs.

### 3.19. Desktop-клиент

`desktop/` — это отдельный WinUI 3 клиент для Windows.

Текущий scaffold/функционал:

- shell с `NavigationView`;
- страницы `Login`, `Servers`, `Terminal`, `Mcp`, `Settings`;
- desktop auth через backend `/api/desktop/v1/`;
- refresh-token flow;
- server list/create/update/delete через desktop API;
- local encrypted settings store;
- local encrypted server store;
- native SSH terminal service через `Renci.SshNet`;
- WebView2 terminal bridge assets;
- AI assistant service;
- workspace state/navigation services.

Текущий статус desktop terminal:

- есть native SSH service;
- есть WebView2 bridge;
- визуальная terminal page пока partly scaffolded/hardened;
- desktop usable как отдельная оболочка, но web SPA по-прежнему основной клиент.

## 4. Реальная backend-структура

### 4.1. `web_ui/`

Отвечает за:

- Django settings;
- выбор SQLite/PostgreSQL;
- выбор Redis/InMemory channel layer;
- ASGI composition;
- static/media wiring;
- агрегацию WebSocket маршрутов `servers` + `studio`.

Root routing:

- `/admin/`
- `'' -> core_ui.urls`
- `/api/desktop/v1/ -> core_ui.desktop_api.urls`
- `/servers/ -> servers.urls`
- `/api/studio/ -> studio.urls`

### 4.2. `core_ui/`

Основные живые зоны:

- auth/session API;
- settings API;
- admin dashboard API;
- access/users/groups/permissions API;
- desktop API;
- middleware;
- managed secrets;
- domain auth;
- activity/audit logging;
- provider/model settings.

Есть и legacy/full-platform функции, которые остаются в `core_ui/views.py`, но не все из них проброшены в активные URL mini-сборки.

### 4.3. `servers/`

Основные живые зоны:

- servers/groups/shares CRUD;
- SSH/RDP realtime access;
- Linux UI;
- file manager;
- knowledge/context;
- layered server memory;
- monitoring/alerts/watchers;
- server agents execution plane;
- live agent events;
- master password flow;
- frontend bootstrap JSON.

### 4.4. `studio/`

Основные живые зоны:

- pipelines;
- runs;
- agent configs;
- skills;
- MCP pool;
- triggers;
- templates;
- notification settings;
- live run streaming.

### 4.5. `app/`

Это общая платформенная библиотека для backend-модулей.

В ней лежат:

- LLM providers и usage logging;
- agent kernel domain types;
- prompt context builder;
- memory store/compaction/redaction/repair;
- permissions engine;
- sandbox profiles;
- tool registry;
- SSH и server tools;
- dangerous command detection.

## 5. Основные модели данных

### 5.1. `core_ui.models`

| Модель | Назначение |
| --- | --- |
| `ChatSession` | Сессии legacy/internal chat. |
| `ChatMessage` | Сообщения в chat session. |
| `UserAppPermission` | Явные per-user permissions по разделам. |
| `GroupAppPermission` | Явные per-group permissions. |
| `UserActivityLog` | Unified activity/audit log. |
| `LLMUsageLog` | Логи использования LLM и затрат. |
| `DesktopRefreshToken` | Refresh tokens для desktop-клиента. |
| `ManagedSecret` | Серверное хранилище encrypted secret envelopes. |

### 5.2. `servers.models`

| Модель | Назначение |
| --- | --- |
| `ServerGroup` | Группа серверов с rules/env/forbidden commands. |
| `ServerGroupTag` | Теги групп. |
| `ServerGroupMember` | Membership + role. |
| `ServerGroupSubscription` | Follow/favorite подписки. |
| `ServerGroupPermission` | Granular group override rights. |
| `Server` | Основная сущность сервера. |
| `ServerShare` | Явный шаринг сервера другому пользователю. |
| `ServerConnection` | Активные terminal connections. |
| `ServerCommandHistory` | История команд. |
| `GlobalServerRules` | Глобальные правила пользователя на все серверы. |
| `ServerKnowledge` | Заметки/знания по серверу. |
| `ServerHealthCheck` | Результаты health monitoring. |
| `ServerAlert` | Alert-объекты мониторинга. |
| `ServerWatcherDraft` | Draft-предложения watcher subsystem. |
| `ServerMemoryPolicy` | User-level policy для layered memory. |
| `BackgroundWorkerState` | Heartbeat/lease фоновых воркеров. |
| `ServerMemoryEvent` | L0 memory event. |
| `ServerMemoryEpisode` | L1 compacted episode. |
| `ServerMemorySnapshot` | L2 canonical/archive snapshot. |
| `ServerMemoryRevalidation` | Очередь revalidation. |
| `ServerGroupKnowledge` | Group-level knowledge. |
| `ServerAgent` | Конфигурация server-bound агента. |
| `AgentRun` | Запуск server agent. |
| `AgentRunDispatch` | Queue/dispatch запись execution plane. |
| `AgentRunEvent` | Persistent event log по run. |

### 5.3. `studio.models`

| Модель | Назначение |
| --- | --- |
| `MCPServerPool` | Reusable MCP definitions. |
| `AgentConfig` | Reusable agent config для Studio pipelines. |
| `Pipeline` | Graph pipeline definition. |
| `PipelineTrigger` | Manual/webhook/schedule/monitoring trigger. |
| `PipelineRun` | Конкретный запуск pipeline. |
| `PipelineTemplate` | Готовые шаблоны pipelines. |
| `StudioSkillAccess` | Ownership/sharing metadata для filesystem skills. |

## 6. HTTP API: карта живых эндпоинтов

### 6.1. `core_ui` root API

Auth/session:

- `/api/auth/csrf/`
- `/api/auth/session/`
- `/api/auth/ws-token/`
- `/api/auth/login/`
- `/api/auth/logout/`

Admin:

- `/api/admin/dashboard/`
- `/api/admin/users/activity/`
- `/api/admin/users/sessions/`

Settings:

- `/api/settings/`
- `/api/settings/check/`
- `/api/settings/activity/`
- `/api/models/`
- `/api/models/refresh/`

Access management:

- `/api/access/users/`
- `/api/access/users/<user_id>/`
- `/api/access/users/<user_id>/password/`
- `/api/access/users/<user_id>/profile/`
- `/api/access/groups/`
- `/api/access/groups/<group_id>/`
- `/api/access/groups/<group_id>/members/`
- `/api/access/permissions/`
- `/api/access/permissions/<perm_id>/`
- `/api/access/group-permissions/`
- `/api/access/group-permissions/<perm_id>/`

Redirect/entry pages:

- `/login/`
- `/logout/`
- `/`
- `/dashboard/`
- `/settings/`
- `/settings/access/`
- `/settings/users/`
- `/settings/groups/`
- `/settings/permissions/`
- `/api/health/`

### 6.2. Desktop API

Desktop auth/session:

- `/api/desktop/v1/auth/login/`
- `/api/desktop/v1/auth/refresh/`
- `/api/desktop/v1/auth/logout/`
- `/api/desktop/v1/auth/me/`

Desktop bootstrap and terminal:

- `/api/desktop/v1/bootstrap/`
- `/api/desktop/v1/terminal/ws-ticket/`

Desktop server operations:

- `/api/desktop/v1/servers/`
- `/api/desktop/v1/servers/groups/`
- `/api/desktop/v1/servers/context/global/`
- `/api/desktop/v1/servers/context/groups/<group_id>/`
- `/api/desktop/v1/servers/<server_id>/`
- `/api/desktop/v1/servers/<server_id>/knowledge/`
- `/api/desktop/v1/servers/<server_id>/knowledge/<knowledge_id>/`

Desktop MCP:

- `/api/desktop/v1/mcp/`
- `/api/desktop/v1/mcp/<mcp_id>/`
- `/api/desktop/v1/mcp/<mcp_id>/test/`
- `/api/desktop/v1/mcp/<mcp_id>/tools/`

### 6.3. `servers/` API

Servers and groups:

- `/servers/api/frontend/bootstrap/`
- `/servers/api/create/`
- `/servers/api/<server_id>/update/`
- `/servers/api/<server_id>/delete/`
- `/servers/api/<server_id>/get/`
- `/servers/api/<server_id>/test/`
- `/servers/api/<server_id>/execute/`
- `/servers/api/bulk-update/`
- `/servers/api/groups/create/`
- `/servers/api/groups/<group_id>/update/`
- `/servers/api/groups/<group_id>/delete/`
- `/servers/api/groups/<group_id>/add-member/`
- `/servers/api/groups/<group_id>/remove-member/`
- `/servers/api/groups/<group_id>/subscribe/`

Secrets and shares:

- `/servers/api/master-password/set/`
- `/servers/api/master-password/check/`
- `/servers/api/master-password/clear/`
- `/servers/api/<server_id>/reveal-password/`
- `/servers/api/<server_id>/shares/`
- `/servers/api/<server_id>/share/`
- `/servers/api/<server_id>/shares/<share_id>/revoke/`

Context and knowledge:

- `/servers/api/global-context/`
- `/servers/api/global-context/save/`
- `/servers/api/groups/<group_id>/context/`
- `/servers/api/groups/<group_id>/context/save/`
- `/servers/api/<server_id>/knowledge/`
- `/servers/api/<server_id>/knowledge/create/`
- `/servers/api/<server_id>/knowledge/<knowledge_id>/update/`
- `/servers/api/<server_id>/knowledge/<knowledge_id>/delete/`

Layered memory:

- `/servers/api/<server_id>/memory/snapshots/`
- `/servers/api/<server_id>/memory/snapshots/bulk-delete/`
- `/servers/api/<server_id>/memory/snapshots/<snapshot_id>/update/`
- `/servers/api/<server_id>/memory/snapshots/<snapshot_id>/delete/`
- `/servers/api/<server_id>/memory/purge/`
- `/servers/api/<server_id>/memory/overview/`
- `/servers/api/<server_id>/memory/run-dreams/`
- `/servers/api/<server_id>/memory/policy/`
- `/servers/api/<server_id>/memory/snapshots/<snapshot_id>/archive/`
- `/servers/api/<server_id>/memory/snapshots/<snapshot_id>/promote-note/`
- `/servers/api/<server_id>/memory/snapshots/<snapshot_id>/promote-skill/`

Linux UI:

- `/servers/api/<server_id>/ui/capabilities/`
- `/servers/api/<server_id>/ui/settings/`
- `/servers/api/<server_id>/ui/overview/`
- `/servers/api/<server_id>/ui/services/`
- `/servers/api/<server_id>/ui/services/logs/`
- `/servers/api/<server_id>/ui/services/action/`
- `/servers/api/<server_id>/ui/processes/`
- `/servers/api/<server_id>/ui/processes/action/`
- `/servers/api/<server_id>/ui/logs/`
- `/servers/api/<server_id>/ui/disk/`
- `/servers/api/<server_id>/ui/network/`
- `/servers/api/<server_id>/ui/packages/`
- `/servers/api/<server_id>/ui/docker/`
- `/servers/api/<server_id>/ui/docker/logs/`
- `/servers/api/<server_id>/ui/docker/action/`

Files:

- `/servers/api/<server_id>/files/`
- `/servers/api/<server_id>/files/read/`
- `/servers/api/<server_id>/files/write/`
- `/servers/api/<server_id>/files/chmod/`
- `/servers/api/<server_id>/files/chown/`
- `/servers/api/<server_id>/files/upload/`
- `/servers/api/<server_id>/files/download/`
- `/servers/api/<server_id>/files/rename/`
- `/servers/api/<server_id>/files/delete/`
- `/servers/api/<server_id>/files/mkdir/`

Monitoring and watchers:

- `/servers/api/monitoring/dashboard/`
- `/servers/api/<server_id>/health/`
- `/servers/api/<server_id>/health/check/`
- `/servers/api/alerts/`
- `/servers/api/alerts/<alert_id>/resolve/`
- `/servers/api/monitoring/config/`
- `/servers/api/watchers/scan/`
- `/servers/api/watchers/drafts/`
- `/servers/api/watchers/drafts/<draft_id>/ack/`
- `/servers/api/watchers/drafts/<draft_id>/launch/`
- `/servers/api/<server_id>/ai-analyze/`

Server agents:

- `/servers/api/agents/`
- `/servers/api/agents/schedules/`
- `/servers/api/agents/schedules/dispatch/`
- `/servers/api/agents/templates/`
- `/servers/api/agents/create/`
- `/servers/api/agents/<agent_id>/update/`
- `/servers/api/agents/<agent_id>/delete/`
- `/servers/api/agents/<agent_id>/run/`
- `/servers/api/agents/<agent_id>/stop/`
- `/servers/api/agents/<agent_id>/runs/`
- `/servers/api/agents/runs/<run_id>/`
- `/servers/api/agents/runs/<run_id>/log/`
- `/servers/api/agents/runs/<run_id>/events/`
- `/servers/api/agents/runs/<run_id>/reply/`
- `/servers/api/agents/dashboard/`
- `/servers/api/agents/runs/<run_id>/approve-plan/`
- `/servers/api/agents/runs/<run_id>/tasks/<task_id>/update/`
- `/servers/api/agents/runs/<run_id>/tasks/<task_id>/ai-refine/`

Legacy/SSR pages still available:

- `/servers/`
- `/servers/hub/`
- `/servers/<server_id>/terminal/`
- `/servers/<server_id>/terminal/minimal/`

### 6.4. `studio/` API

Pipelines:

- `/api/studio/pipelines/`
- `/api/studio/pipelines/assistant/`
- `/api/studio/pipelines/<pipeline_id>/`
- `/api/studio/pipelines/<pipeline_id>/run/`
- `/api/studio/pipelines/<pipeline_id>/clone/`
- `/api/studio/pipelines/<pipeline_id>/runs/`

Runs:

- `/api/studio/runs/`
- `/api/studio/runs/<run_id>/`
- `/api/studio/runs/<run_id>/stop/`
- `/api/studio/runs/<run_id>/approve/<node_id>/`

Studio agent configs:

- `/api/studio/agents/`
- `/api/studio/agents/<agent_id>/`

Skills:

- `/api/studio/skills/`
- `/api/studio/skills/templates/`
- `/api/studio/skills/scaffold/`
- `/api/studio/skills/validate/`
- `/api/studio/skills/<slug>/workspace/`
- `/api/studio/skills/<slug>/workspace/file/`
- `/api/studio/skills/<slug>/`

MCP:

- `/api/studio/mcp/`
- `/api/studio/mcp/templates/`
- `/api/studio/mcp/<mcp_id>/`
- `/api/studio/mcp/<mcp_id>/test/`
- `/api/studio/mcp/<mcp_id>/tools/`

Triggers/templates/notifications:

- `/api/studio/triggers/`
- `/api/studio/triggers/<trigger_id>/`
- `/api/studio/triggers/<token>/receive/`
- `/api/studio/templates/`
- `/api/studio/templates/<slug>/use/`
- `/api/studio/servers/`
- `/api/studio/share-users/`
- `/api/studio/notifications/`
- `/api/studio/notifications/test-telegram/`
- `/api/studio/notifications/test-email/`

## 7. WebSocket endpoints

| URL | Consumer | Назначение |
| --- | --- | --- |
| `/ws/servers/<server_id>/terminal/` | `SSHTerminalConsumer` | SSH terminal, AI-команды, resize, status, output. |
| `/ws/servers/<server_id>/rdp/` | `RDPTerminalConsumer` | RDP/live terminal channel. |
| `/ws/agents/<run_id>/live/` | `AgentLiveConsumer` | Live stream server-agent run. |
| `/ws/studio/pipeline-runs/<run_id>/live/` | `PipelineRunConsumer` | Live stream pipeline node/run state. |

## 8. SPA routes и пользовательские страницы

Основные SPA routes:

- `/login`
- `/`
- `/dashboard`
- `/servers`
- `/servers/hub`
- `/servers/:id/terminal`
- `/servers/:id/rdp`
- `/agents`
- `/agents/run/:runId`
- `/studio`
- `/studio/pipeline/:id`
- `/studio/pipeline/new`
- `/studio/runs`
- `/studio/agents`
- `/studio/skills`
- `/studio/mcp`
- `/studio/notifications`
- `/settings`
- `/settings/users`
- `/settings/groups`
- `/settings/permissions`

Главные страницы SPA и что они дают:

| Файл | Назначение |
| --- | --- |
| `Servers.tsx` | Серверы, группы, контекст, knowledge, shares, playbooks, bulk/server actions. |
| `TerminalPage.tsx` | Multi-tab terminal hub, AI panel, Linux UI, SFTP panel. |
| `RdpPage.tsx` | RDP frontend shell. |
| `AgentsPage.tsx` | CRUD server agents и быстрый запуск. |
| `AgentRunPage.tsx` | Live run detail, timeline, plan approval, task editing, report. |
| `StudioPage.tsx` | Список pipelines, run/clone/open, trigger info. |
| `PipelineEditorPage.tsx` | Полноценный visual pipeline editor. |
| `PipelineRunsPage.tsx` | Runs monitor и detail. |
| `AgentConfigPage.tsx` | CRUD Studio agent configs. |
| `StudioSkillsPage.tsx` | Skill catalog, scaffold, validate, workspace editing. |
| `MCPHubPage.tsx` | MCP registry, templates, connection tests, tools list. |
| `NotificationsSettingsPage.tsx` | Telegram/email notification settings и тесты. |
| `SettingsPage.tsx` | LLM settings, models, logging, AI memory, activity. |
| `SettingsUsersPage.tsx` | Управление пользователями. |
| `SettingsGroupsPage.tsx` | Управление группами доступа. |
| `SettingsPermissionsPage.tsx` | Управление feature permissions. |
| `AdminDashboard.tsx` | Staff dashboard по системе. |
| `UserDashboard.tsx` | User dashboard по серверам и агентам. |

Отдельные frontend-фичи, которые легко пропустить:

- playbook builder/importer в `Servers.tsx`;
- импорт Ansible YAML/JSON playbooks;
- AI memory tab в Settings;
- встроенный visual editor для skill workspace;
- pipeline assistant с graph patch;
- Live pipeline monitor через WebSocket;
- Linux UI как windowed workspace, а не просто список метрик.

## 9. Desktop-карта

Desktop solution:

- `desktop/MiniProd.Desktop.sln`
- `desktop/src/MiniProd.Desktop/`

Главные страницы:

- `LoginPage`
- `ServersPage`
- `TerminalPage`
- `McpPage`
- `SettingsPage`

Главные сервисы:

- `DesktopApiClient` — работа с `/api/desktop/v1/`;
- `SessionService` — текущая desktop session;
- `SettingsService` — локальные настройки с защитой секрета;
- `ProtectedSecretService` — protect/unprotect;
- `LocalServerStoreService` — локальное хранилище серверов;
- `SshTerminalService` — native SSH terminal;
- `TerminalBridgeService` — WebView2 bridge;
- `AiAssistantService` — AI assistant HTTP-интеграция;
- `NavigationService`
- `WorkspaceStateService`

## 10. Management-команды и фоновые процессы

### 10.1. `core_ui`

- `check_channel_layer`
- `seed_multi_user_smoke`

### 10.2. `servers`

- `repair_server_memory`
- `run_agent_execution_plane`
- `run_memory_dreams`
- `run_monitor`
- `run_ops_supervisor`
- `run_scheduled_agents`
- `run_watchers`
- `seed_servers_for_frontend`

### 10.3. `studio`

- `load_pipeline_templates`
- `run_scheduled_pipelines`
- `scaffold_skill`
- `setup_all_nodes_smoke_pipeline`
- `setup_docker_service_recovery_pipeline`
- `setup_keycloak_ops_pipelines`
- `setup_keycloak_provisioning_pipeline`
- `setup_mcp_showcase_pipeline`
- `setup_server_update_pipeline`
- `setup_webhook_smoke_pipeline`
- `validate_skills`

Что это значит practically:

- monitoring, watchers, memory dreams и scheduled agents/pipelines предполагают отдельные фоновые запускатели;
- execution plane для agents вынесен отдельно;
- проект уже рассчитан не только на request/response, но и на long-running background orchestration.

## 11. Внутренние платформенные подсистемы

### 11.1. LLM/provider слой

`app/core/llm.py` дает:

- provider selection;
- timeout/retry policy;
- usage logging;
- retryable/non-retryable error handling.

### 11.2. Agent kernel

`app/agent_kernel/` включает:

- domain specs (`ToolSpec`, `MemoryRecord`, `ServerMemoryCard`, `PermissionDecision`, `RunEvent`, `AgentState`, `SubagentSpec`);
- prompt context builder `build_ops_prompt_context()`;
- memory store `DjangoServerMemoryStore`;
- compaction helpers;
- prompt redaction/sanitization;
- repair/freshness/conflict detection;
- permission engine;
- sandbox profiles/manager;
- tool registry.

### 11.3. Dangerous action safety

`app/tools/safety.py` содержит `is_dangerous_command()`.

Эта проверка критична для:

- terminal AI;
- Linux UI actions;
- server tools;
- agent execution;
- всех будущих risky backend operations.

### 11.4. SSH/server tools

Подготовлены tool-обертки:

- `SSHConnectionManager`
- `SSHConnectTool`
- `SSHExecuteTool`
- `SSHDisconnectTool`
- `ServersListTool`
- `ServerExecuteTool`

Это внутренняя база для агентного runtime и tool registry.

## 12. Вспомогательные скрипты, интеграции и деплой

В корне проекта есть важные служебные файлы:

- `bootstrap-config.ps1` — заготовка локальных конфигов на Windows;
- `bootstrap-linux.sh` — bootstrap для Linux/macOS;
- `docker-compose.yml` и production/postgres-mcp варианты;
- `render.yaml` — blueprint под Render;
- `key_mcp.py` — standalone Keycloak MCP tool server;
- `keycloak_profiles.json` — профили подключения к Keycloak;
- `create_mega_pipeline.py` — script, создающий большой demo/ops pipeline;
- `create_pipeline.sql` — SQL-артефакт;
- `docker/` — production startup/nginx/runtime scripts.

`key_mcp.py` по коду умеет:

- работать как MCP bridge/tool server;
- обращаться к Keycloak admin API;
- использовать профили и env;
- валидировать URL/SSL/auth;
- возвращать JSON-RPC/MCP-style ответы.

## 13. Тесты и качество

Backend test-покрытие включает отдельные зоны:

- `test_core_ui_api_smoke.py`
- `test_servers_api_smoke.py`
- `test_studio_api_smoke.py`
- `test_desktop_api.py`
- `test_servers_monitor.py`
- `test_memory_redaction.py`
- `test_memory_repair.py`
- `test_ops_agent_kernel.py`
- `test_agent_and_pipeline_policy_enforcement.py`
- `test_studio_all_nodes_smoke.py`
- `test_studio_node_executors.py`
- `test_studio_pipeline_v2.py`
- `test_studio_monitoring_trigger.py`
- `test_tools_and_policy_units.py`
- `test_scheduled_agents.py`
- `test_channel_layer_health.py`
- `test_llm_runtime_unit.py`
- `test_ssh_host_keys.py`

Frontend:

- Vitest unit/integration tests;
- Playwright e2e/a11y/visual scripts в `ai-server-terminal-main/package.json`.

Ожидаемые quality-команды:

- `pytest`
- `ruff check .`
- `ruff format .`
- `npm run test`
- `npm run test:e2e`

## 14. Что важно понимать до изменения кода

1. Это уже не `servers-only` сборка. Активны `core_ui`, `servers`, `studio`, `app`, `desktop`, `ai-server-terminal-main`.

2. Основной пользовательский интерфейс — SPA в `ai-server-terminal-main/`, а не Django templates.

3. В проекте есть две memory-системы:

- ephemeral terminal AI memory;
- layered server memory.

Их нельзя смешивать ни в логике, ни в UI.

4. В `core_ui/views.py` остался legacy/full-platform код, который не весь маршрутизирован в текущую mini-сборку.

5. `passwords/` в дереве есть, но сейчас не включен в `INSTALLED_APPS`.

6. Часть desktop-функционала уже рабочая, но desktop по состоянию кода все еще secondary client относительно web SPA.

7. Root `src/main.tsx` — это не отдельный frontend, а thin entrypoint, который импортирует `ai-server-terminal-main/src/main.tsx`.

8. Candidate memory snapshots (`pattern_candidate`, `automation_candidate`, `skill_draft`) — это operational support layer, а не часть основного prompt memory блока.

## 15. Куда смотреть по основным темам

Если нужно менять конкретную зону, стартовые файлы такие:

| Тема | Куда смотреть |
| --- | --- |
| Auth / settings / access | `core_ui/urls.py`, `core_ui/views.py`, `core_ui/models.py`, `core_ui/access.py` |
| Desktop API | `core_ui/desktop_api/urls.py`, `core_ui/desktop_api/views.py` |
| Servers CRUD / shares / knowledge | `servers/views.py`, `servers/models.py` |
| Terminal / AI terminal | `servers/consumers.py`, `ai-server-terminal-main/src/pages/TerminalPage.tsx`, `components/terminal/XTerminal.tsx`, `AiPanel.tsx` |
| RDP | `servers/rdp_consumer.py`, `RdpPage.tsx` |
| Linux UI | `servers/linux_ui.py`, `components/terminal/LinuxUiPanel.tsx` |
| File manager | `servers/views.py` file endpoints, `components/terminal/SftpPanel.tsx` |
| Monitoring / alerts | `servers/monitor.py`, `servers/views.py`, `servers/models.py` |
| Watchers | `servers/watcher_service.py`, `servers/views.py` |
| Layered memory | `app/agent_kernel/memory/*`, `servers/signals.py`, `servers/views.py`, `SettingsPage.tsx` |
| Server agents | `servers/agent_engine.py`, `servers/multi_agent_engine.py`, `servers/agent_consumer.py`, `servers/views.py`, `AgentsPage.tsx`, `AgentRunPage.tsx` |
| Studio pipelines | `studio/models.py`, `studio/views.py`, `studio/pipeline_executor.py`, `PipelineEditorPage.tsx` |
| Studio skills | `studio/skill_registry.py`, `studio/skill_authoring.py`, `studio/views.py`, `StudioSkillsPage.tsx` |
| Studio MCP | `studio/mcp_client.py`, `studio/views.py`, `MCPHubPage.tsx` |
| Notifications | `studio/views.py`, `NotificationsSettingsPage.tsx` |
| Desktop app | `desktop/src/MiniProd.Desktop/*` |

## 16. Итог в одной фразе

Сейчас это не “мини-терминал”, а уже полноценная ops-платформа: инвентарь серверов, realtime terminal access, file/system tooling, monitoring, долговременная AI memory, server agents, visual automation pipelines, MCP registry, skills, notifications и отдельный Windows desktop-клиент поверх того же backend-а.
