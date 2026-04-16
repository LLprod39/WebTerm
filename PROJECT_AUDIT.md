# WEU AI Platform — Полный архитектурный аудит

> Дата: Апрель 2026  
> Репозиторий: `c:\WebTrerm`  
> Назначение: передача документа новой команде, рефакторинг, масштабирование

---

## 1. Общая структура проекта

### Дерево директорий верхнего уровня

```
c:\WebTrerm/
│
├── web_ui/                         # Django project: settings, URLs, ASGI, routing
├── core_ui/                        # Django app: auth, permissions, users, audit
├── servers/                        # Django app: серверы, SSH/RDP, agents, memory, monitor
├── studio/                         # Django app: pipelines, MCP, skills, triggers
├── app/                            # Общие Python-пакеты (LLM, agent_kernel, tools)
│   ├── core/                       # LLM-провайдеры, model config
│   ├── agent_kernel/               # Ядро агентов: domain, memory, permissions, runtime
│   └── tools/                      # SSH-tools, server-tools, safety
│
├── ai-server-terminal-main/        # React/Vite SPA (основной UI)
│   └── src/
│       ├── pages/                  # Страницы (маршруты)
│       ├── components/             # UI-компоненты
│       ├── lib/                    # api.ts, i18n, featureAccess, utils
│       └── hooks/                  # use-mobile, use-toast
│
├── desktop/                        # C# WinUI desktop-клиент (.NET)
│   └── src/MiniProd.Desktop/
│
├── docker/                         # Dockerfile-ы, nginx config, скрипты деплоя
│   ├── backend.Dockerfile
│   ├── frontend.Dockerfile
│   ├── nginx/
│   └── render-backend-start.sh
│
├── tests/                          # Интеграционные pytest-тесты
│
├── passwords/                      # ⚠️ Кодовый модуль, не подключён в INSTALLED_APPS
│
│── manage.py                       # Django CLI (дефолтный порт: 9000)
├── docker-compose.yml              # Локальная разработка (postgres, redis, backend, frontend, nginx, mcp-*)
├── docker-compose.production.yml   # Production-конфигурация
├── pyproject.toml                  # Ruff, pytest, project metadata
├── requirements-mini.txt           # Runtime Python-зависимости
│
│── [МУСОР В КОРНЕ]:
├── fix.py, fix_tree.py             # Одноразовые patch-скрипты
├── patch_layout.py                 # Одноразовый patch
├── patch_settings.py               # Одноразовый patch
├── patch_wizard.py                 # Одноразовый patch
├── patch_workspace.py              # Одноразовый patch
├── original_page.tsx               # ⚠️ 162 KB backup-файл TSX
├── diff.txt                        # ⚠️ 94 KB debug-артефакт
├── key_mcp.py                      # Standalone MCP-сервер (Keycloak) — 95 KB
├── key_mcp.py.new                  # Его замена — 80 KB, не применена
├── create_mega_pipeline.py         # Seeding-скрипт
├── create_pipeline.sql             # SQL seed
│
│── [КОНФИГИ ФРОНТЕНДА В КОРНЕ] (дублируют ai-server-terminal-main/):
├── vite.config.ts
├── tailwind.config.ts
├── tsconfig.json / tsconfig.app.json / tsconfig.node.json
├── package.json / package-lock.json / bun.lock
├── postcss.config.js / eslint.config.js
└── index.html
```

### Ключевые точки входа

| Точка входа | Назначение |
|---|---|
| `manage.py` | Django CLI, автоматически ставит порт `9000` |
| `web_ui/asgi.py` | ASGI-приложение (Daphne): HTTP + WebSocket |
| `web_ui/wsgi.py` | WSGI-fallback (не используется в prod с Daphne) |
| `web_ui/celery.py` | Celery (опционально, не в requirements-mini) |
| `ai-server-terminal-main/src/main.tsx` | React SPA entry |
| `ai-server-terminal-main/src/App.tsx` | Корневой роутинг SPA |
| `desktop/src/MiniProd.Desktop/` | WinUI desktop entry |
| `key_mcp.py` | Standalone Keycloak MCP-сервер |
| `studio/demo_mcp_server.py` | Demo MCP-сервер |

---

## 2. Описание модулей

### 2.1 `web_ui/` — Django Project Config

**Что делает:**
- `settings.py` (749 строк) — вся конфигурация: DEBUG, DB (PostgreSQL / SQLite auto-switch), Redis channels layer (InMemoryChannelLayer fallback), CORS, CSRF, ALLOWED_HOSTS, SSO/domain-auth, email/SMTP, уведомления, Render.com detection
- `urls.py` — корневой URL-роутинг: `/admin/`, `core_ui.urls`, `servers.urls`, `studio.urls`, `desktop_api.urls`
- `asgi.py` — `ProtocolTypeRouter` (HTTP + WebSocket через `AuthMiddlewareStack`)
- `routing.py` — агрегирует WS-маршруты из `servers` и `studio`
- `celery.py` — Celery app (в mini-prod не используется активно)

**Связи:** зависит от всех Django-приложений (импортирует их routing).

---

### 2.2 `core_ui/` — Auth, Permissions, Users, Audit

**Что делает:**
- Аутентификация и управление сессиями (`/api/auth/*`)
- Управление пользователями и группами (`/api/access/*`)
- Управление feature-доступом (`UserAppPermission`, `GroupAppPermission`)
- Аудит всех HTTP-запросов через middleware
- Редиректы Django URL → React SPA
- Desktop API (`/api/desktop/v1/`) — refresh-токены для WinUI
- Domain SSO (`DomainAutoLoginMiddleware`)

**Модели:**
- `ChatSession`, `ChatMessage` — история AI-чатов *(практически не используется в текущем UI)*
- `UserAppPermission`, `GroupAppPermission` — feature-флаги доступа
- `UserActivityLog` — единый лог действий
- `LLMUsageLog` — учёт LLM-вызовов
- `DesktopRefreshToken` — токены для desktop-клиента
- `ManagedSecret` — зашифрованные секреты (namespace/object_id/key)

**Ключевые файлы:**
- `views.py` — **171 394 байт** (⚠️ god file: вся бизнес-логика auth, settings, access, admin API, SSO в одном файле)
- `middleware.py` — `CsrfTrustNgrokMiddleware`, `AdminRussianMiddleware`, `MobileDetectionMiddleware`, `RequestAuditMiddleware`
- `domain_auth.py` — автологин по заголовкам `X-Forwarded-User` и т.п.
- `decorators.py` — `@login_required_json`, `@staff_required`, `@feature_required`
- `access.py`, `activity.py`, `audit.py` — вынесенные сервисные функции
- `desktop_api/views.py` — 24 KB API для WinUI

**Связи:** используется всеми модулями через `UserAppPermission`, `ManagedSecret`, `UserActivityLog`.

---

### 2.3 `servers/` — Серверы, Терминалы, Агенты, Мониторинг

Самый крупный и комплексный Django-модуль (~630 KB Python-кода).

**Что делает:**
- CRUD серверов (`Server`, `ServerGroup`, `ServerGroupMember`, `ServerShare`)
- SSH-терминал в браузере через WebSocket (`SSHTerminalConsumer` в `consumers.py`)
- RDP-терминал (`RDPTerminalConsumer`, `guacd_tunnel.py`)
- SFTP/файловый менеджер (`sftp.py`)
- Linux UI (обзор сервиса, процессов, дисков, логов, Docker) — `linux_ui.py` (48 KB)
- Мониторинг и алерты (`monitor.py`, `ServerHealthCheck`, `ServerAlert`)
- Agents — создание/запуск/остановка (`agents.py`, `agent_engine.py`, `multi_agent_engine.py`)
- Layered server memory — запись, compaction, dreams, snapshots (`ServerMemoryEvent`, `ServerMemoryEpisode`, `ServerMemorySnapshot`)
- Knowledge base серверов (`ServerKnowledge`, `knowledge_service.py`)
- Watcher-агенты (`watcher_service.py`, `watcher_actions.py`)
- Scheduled agents (`scheduled_agents.py`)
- SSH host-key verification / TOFU (`ssh_host_keys.py`)

**Ключевые файлы по размеру:**

| Файл | Размер | Проблема |
|---|---|---|
| `consumers.py` | 146 318 байт | ⚠️ God class: SSH-терминал + AI-чат + файловый менеджер + команды в одном Consumer |
| `views.py` | 159 135 байт | ⚠️ God file |
| `multi_agent_engine.py` | 83 426 байт | Очень большой |
| `agent_engine.py` | 43 440 байт | Большой |
| `linux_ui.py` | 48 693 байт | Много отдельных SSH-команд inline |
| `agents.py` | 25 673 байт | |
| `models.py` | 48 716 байт | |

**WebSocket-маршруты:**
```
ws/servers/<id>/terminal/   → SSHTerminalConsumer
ws/servers/<id>/rdp/        → RDPTerminalConsumer
ws/agents/<run_id>/live/    → AgentLiveConsumer
```

**Связи:** `app.agent_kernel`, `app.tools`, `app.core.llm`, `core_ui.models.ManagedSecret`, `studio.models.AgentConfig`

**Management commands:**
- `run_agent_execution_plane` — execution plane фоновых агентов
- `run_memory_dreams` — фоновые memory-dreams
- `run_monitor` — мониторинг серверов
- `run_ops_supervisor` — supervisor агентов
- `run_scheduled_agents` — планировщик
- `run_watchers` — watcher-сервис
- `repair_server_memory` — ремонт памяти

---

### 2.4 `studio/` — Pipelines, MCP, Skills, Triggers

**Что делает:**
- Visual pipeline editor (узлы + рёбра в JSON): `Pipeline`, `PipelineRun`
- Execution engine: `pipeline_executor.py` (114 285 байт — крупнейший исполнитель)
- MCP (Model Context Protocol) pool: `MCPServerPool`, `mcp_client.py`
- Agent configs: `AgentConfig`
- Webhook/cron/manual/monitoring triggers: `PipelineTrigger`, `trigger_dispatch.py`
- Skill authoring и registry: `skill_authoring.py`, `skill_registry.py`, `skill_policy.py`
- Pipeline templates: `templates_data.py` (42 KB), `PipelineTemplate`
- Уведомления: Telegram, Email
- Live updates pipeline run через WebSocket: `PipelineRunConsumer`

**Ключевые файлы по размеру:**

| Файл | Размер | Примечание |
|---|---|---|
| `pipeline_executor.py` | 114 285 байт | ⚠️ Один файл исполняет все типы узлов |
| `views.py` | 96 175 байт | ⚠️ God file |
| `keycloak_provisioning.py` | 60 252 байт | Standalone Keycloak automation |
| `docker_service_recovery.py` | 46 966 байт | Standalone Docker recovery |
| `templates_data.py` | 42 607 байт | Embedded template data (не в fixtures) |
| `models.py` | 25 128 байт | |

**WebSocket:**
```
ws/studio/pipeline-runs/<run_id>/live/ → PipelineRunConsumer
```

**Связи:** `app.core.llm`, `app.agent_kernel`, `servers.models.Server`, `core_ui.models.*`

---

### 2.5 `app/` — Общие Сервисы

Shared Python-пакет, не является Django-приложением.

#### `app/core/`
- `llm.py` (48 690 байт) — провайдеры LLM: Gemini, Claude, OpenAI, Grok, Ollama; логирование в `LLMUsageLog`
- `model_config.py` (32 430 байт) — конфигурация моделей, лимиты токенов
- `provider_registry.py` — реестр провайдеров
- `model_utils.py` — утилиты

#### `app/agent_kernel/` — Ядро Агентов

```
agent_kernel/
├── domain/
│   ├── specs.py     # Dataclasses: ToolSpec, MemoryRecord, ServerMemoryCard,
│   │                #   AgentState, SubagentSpec, PermissionDecision, RunEvent
│   └── roles.py     # Определения ролей агентов
├── memory/
│   ├── store.py     # ⚠️ 181 824 байт — главный memory store
│   ├── compaction.py # Выжимка run results
│   ├── redaction.py  # Redaction секретов
│   ├── repair.py     # Freshness/confidence decay
│   └── server_cards.py # Prompt-ready карточки памяти
├── permissions/
│   ├── engine.py    # Permission decision engine (PLAN/SAFE/ASSISTED/AUTONOMOUS)
│   └── modes.py     # PermissionMode enum
├── runtime/
│   ├── context.py   # Сборка ops prompt context
│   ├── parsing.py   # Разбор ответов LLM
│   └── subagents.py # Subagent dispatch
├── hooks/
│   └── manager.py   # Hook manager для lifecycle событий
├── sandbox/         # Sandbox-профили
└── tools/           # Tool registry внутри kernel
```

`memory/store.py` — **181 824 байт** — крупнейший файл в проекте. Содержит: ingestion, compaction, dreams, repair, overview, promote/archive.

#### `app/tools/`
- `ssh_tools.py` — connect/execute/disconnect через asyncssh
- `server_tools.py` — list/execute поверх Server-моделей
- `safety.py` — `is_dangerous_command()` blacklist
- `base.py` — базовый класс Tool

---

### 2.6 `ai-server-terminal-main/` — React SPA

**Стек:** React 18, Vite 5, TailwindCSS 3, Radix UI, shadcn/ui, react-router-dom v6, @tanstack/react-query v5, XTerm.js v6, @xyflow/react v12, recharts, framer-motion

**Страницы (`src/pages/`):**

| Страница | Маршрут | Feature Gate |
|---|---|---|
| `Login.tsx` | `/login` | — |
| `Servers.tsx` (156 KB!) | `/servers` | — |
| `TerminalPage.tsx` (45 KB) | `/servers/:id/terminal` | — |
| `RdpPage.tsx` | `/servers/:id/rdp` | — |
| `AgentsPage.tsx` (37 KB) | `/agents` | `agents` |
| `AgentRunPage.tsx` (62 KB) | `/agents/run/:runId` | `agents` |
| `StudioPage.tsx` (38 KB) | `/studio` | `studio` |
| `PipelineEditorPage.tsx` (157 KB!) | `/studio/pipeline/:id` | `studio_pipelines` |
| `PipelineRunsPage.tsx` (25 KB) | `/studio/runs` | `studio_runs` |
| `AgentConfigPage.tsx` (27 KB) | `/studio/agents` | `studio_agents` |
| `StudioSkillsPage.tsx` (74 KB) | `/studio/skills` | `studio_skills` |
| `MCPHubPage.tsx` (24 KB) | `/studio/mcp` | `studio_mcp` |
| `SettingsPage.tsx` (107 KB!) | `/settings/*` | `settings` |
| `AdminDashboard.tsx` (16 KB) | `/dashboard` | `dashboard` |
| `UserDashboard.tsx` (19 KB) | `/dashboard` | `dashboard` |

**Auth flow:** `AuthGate` → `fetchAuthSession()` → `/api/auth/session/` → cookies-based session

**Feature access:** `FeatureGate` использует `UserAppPermission` из `core_ui`, возвращаемые через `/api/auth/session/`

**Ключевые lib-файлы:**
- `lib/api.ts` — **133 257 байт** (⚠️ единый монолитный API-клиент для ВСЕХ endpoint-ов)
- `lib/i18n.tsx` — **52 965 байт** (встроенные переводы, не отдельные JSON-файлы)
- `lib/featureAccess.ts` — проверка feature-флагов на клиенте

---

### 2.7 `desktop/` — C# WinUI Desktop

- Проект `MiniProd.Desktop.sln` — .NET WinUI-приложение
- Использует `core_ui.desktop_api` (`/api/desktop/v1/`) для аутентификации через `DesktopRefreshToken`
- Минимально задокументирован; используется параллельно с web SPA

---

### 2.8 `passwords/` — Неподключённый модуль

- Файлы присутствуют, но **не в `INSTALLED_APPS`**
- Функциональность заменена `core_ui.models.ManagedSecret`
- **[Предположение]**: исторически был отдельным приложением для хранения паролей

---

### 2.9 Инфраструктура (`docker/`, `docker-compose.yml`)

**docker-compose.yml** определяет 6 сервисов:

| Сервис | Образ/Dockerfile | Порт | Зависимость |
|---|---|---|---|
| `postgres` | postgres:16-alpine | 5432 | — |
| `redis` | redis:7-alpine | 6379 | — |
| `backend` | docker/backend.Dockerfile | 9000 | postgres, redis |
| `frontend` | docker/frontend.Dockerfile | 8080 | backend |
| `nginx` | nginx:1.27-alpine | 8080 (pub) | backend, frontend |
| `mcp-demo` | python:3.12-slim | 8765 | — |
| `mcp-keycloak` | docker/keycloak-mcp.Dockerfile | 8766 | — |

---

## 3. Поток данных

### 3.1 HTTP-запрос (REST API)

```
Browser/Desktop
    │
    ▼
[nginx :8080]   (prod) / [Vite dev-server :8080 proxy]   (dev)
    │
    ▼
[Django/Daphne :9000]
    │
    ├── web_ui/urls.py
    │       ├── /admin/                    → Django Admin
    │       ├── /                          → core_ui.urls
    │       │       ├── /api/auth/*        → core_ui.views (auth/session)
    │       │       ├── /api/access/*      → core_ui.views (users/groups/perms)
    │       │       ├── /api/settings/*    → core_ui.views (LLM settings)
    │       │       └── /api/admin/*       → core_ui.views (dashboard)
    │       ├── /api/desktop/v1/           → core_ui.desktop_api.views
    │       ├── /servers/                  → servers.views
    │       │       ├── /api/agents/*      → agents CRUD + runs
    │       │       ├── /api/<id>/terminal → terminal page redirect
    │       │       ├── /api/<id>/files/*  → SFTP operations
    │       │       ├── /api/<id>/ui/*     → Linux UI (services/processes/docker)
    │       │       └── /api/monitoring/*  → health/alerts
    │       └── /api/studio/               → studio.views
    │               ├── /pipelines/*       → pipeline CRUD + run
    │               ├── /runs/*            → run detail/stop/approve
    │               ├── /agents/*          → agent configs
    │               ├── /skills/*          → skill authoring
    │               ├── /mcp/*             → MCP pool
    │               └── /triggers/*        → webhook/cron triggers
    │
    ▼
  views.py (core_ui / servers / studio)
    │
    ├── ORM (Django models → PostgreSQL / SQLite)
    ├── app.core.llm (LLM calls → external APIs: Gemini/Claude/OpenAI/Grok)
    ├── app.agent_kernel.* (memory / permissions / runtime)
    └── app.tools.ssh_tools (asyncssh → target servers)
```

### 3.2 WebSocket (терминал / агент / pipeline live)

```
Browser
    │  wss://<host>/ws/servers/<id>/terminal/
    ▼
[nginx] → [Daphne ASGI]
    │
    ▼
channels.auth.AuthMiddlewareStack
    │
    ▼
SSHTerminalConsumer (servers/consumers.py)
    │
    ├── asyncssh → Target SSH Server
    ├── Terminal AI: app.core.llm → LLM API
    └── Memory ingestion: app.agent_kernel.memory.store
```

### 3.3 Pipeline Execution

```
Trigger (webhook / cron / monitoring alert / manual)
    │
    ▼
studio.trigger_dispatch → PipelineRun.create()
    │
    ▼
studio.pipeline_executor.PipelineExecutor
    │
    ├── Node: "llm"          → app.core.llm
    ├── Node: "ssh"          → app.tools.ssh_tools
    ├── Node: "agent"        → servers.agent_engine / multi_agent_engine
    ├── Node: "mcp"          → studio.mcp_client
    ├── Node: "condition"    → eval условий
    ├── Node: "notify"       → email / telegram
    └── ...
    │
    ▼
WebSocket live update → PipelineRunConsumer → Browser
```

### 3.4 Agent Execution

```
User → POST /servers/api/agents/<id>/run/
    │
    ▼
servers.views.agent_run()
    │
    ▼
servers.agent_dispatch → AgentRun.create()
    │
    ▼
servers.agent_engine.AgentEngine
    │
    ├── app.agent_kernel.permissions.engine (PLAN/SAFE/ASSISTED/AUTONOMOUS)
    ├── app.agent_kernel.runtime.context (prompt building с memory)
    ├── app.core.llm (LLM inference)
    ├── app.tools.ssh_tools (команды на серверах)
    └── app.agent_kernel.memory.store (запись в память)
    │
    ▼
WebSocket → AgentLiveConsumer → Browser
```

### 3.5 Memory Pipeline

```
SSH команда выполнена / Health check / Alert / Agent run
    │
    ▼
servers.signals.py (Django signals)
    │
    ▼
ServerMemoryEvent.create() → DB
    │
    ▼
[фоновый: run_memory_dreams]
    │
    ▼
app.agent_kernel.memory.store
    ├── compaction.py  (events → episodes)
    ├── repair.py      (freshness/confidence decay)
    ├── redaction.py   (удаление секретов)
    └── server_cards.py (prompt-ready карточки)
    │
    ▼
ServerMemorySnapshot → DB → используется в agent prompt context
```

---

## 4. Архитектурные проблемы

### 4.1 God Files — критично

Файлы, которые содержат слишком много логики и не поддаются тестированию по частям:

| Файл | Размер | Проблема |
|---|---|---|
| `app/agent_kernel/memory/store.py` | **181 KB** | Ingestion + compaction + dreams + repair + overview — всё в одном |
| `core_ui/views.py` | **171 KB** | Auth + settings + access + admin + SSO + activity в одном файле |
| `servers/views.py` | **159 KB** | CRUD + files + linux UI + memory + agents в одном файле |
| `ai-server-terminal-main/src/lib/api.ts` | **133 KB** | Все API-вызовы платформы в одном файле |
| `servers/consumers.py` | **146 KB** | SSH-терминал + AI-чат + файловый менеджер + команды в одном Consumer |
| `studio/pipeline_executor.py` | **114 KB** | Все типы pipeline-узлов в одном файле |
| `studio/views.py` | **96 KB** | |
| `servers/multi_agent_engine.py` | **83 KB** | |
| `ai-server-terminal-main/src/pages/PipelineEditorPage.tsx` | **157 KB** | |
| `ai-server-terminal-main/src/pages/Servers.tsx` | **156 KB** | |
| `ai-server-terminal-main/src/pages/SettingsPage.tsx` | **107 KB** | |

### 4.2 Отсутствие сервисного слоя

В Django-приложениях вся бизнес-логика сидит прямо в `views.py`. Нет промежуточных service-классов. Views делают: DB-запросы → вызов LLM → SSH-команды → запись в memory — всё inline.

**Последствие:** сложно тестировать, сложно переиспользовать логику между API-эндпойнтами и management commands.

### 4.3 Смешение фронтенда и бэкенда в корне репозитория

В корне `/` присутствуют конфигурационные файлы **второго** Vite/React-проекта (`vite.config.ts`, `tailwind.config.ts`, `package.json`, `tsconfig.json`, `index.html`, `src/`), которые дублируют реальный SPA в `ai-server-terminal-main/`. Это создаёт путаницу: какой именно фронтенд собирать.

### 4.4 Мусорные файлы в корне

- `original_page.tsx` (162 KB) — бэкап-файл TSX, не нужен в репозитории
- `diff.txt` (94 KB) — debug-артефакт git diff
- `key_mcp.py` + `key_mcp.py.new` — два варианта одного файла, неясно что применять
- `fix.py`, `fix_tree.py`, `patch_*.py` — одноразовые скрипты, должны быть в отдельной папке или удалены
- `StudioSkillsPage.tsx.bak` — бэкап в `src/pages/`
- `LOVABLE_FRONTEND_PROMPT.txt` (28 KB) — промпт для Lovable в репозитории
- `.codex-logs/`, `.playwright-cli/`, `.playwright-mcp/`, `.tmp_notif_tests/`, `.tmp_skill_*` — артефакты инструментов

### 4.5 Две параллельные memory-системы

1. **Terminal AI session memory** (`_ai_history` в `SSHTerminalConsumer`) — краткоживущая, TTL по числу запросов, хранится in-memory Consumer
2. **Layered server memory** (`ServerMemoryEvent/Episode/Snapshot`) — долговременная, в БД

Связь неявная: терминальный Consumer иногда пишет в layered memory через signals. Это не задокументировано и приводит к путанице при отладке.

### 4.6 Разрозненное расположение тестов

Тесты находятся в 4 разных местах:
- `tests/` — основная папка интеграционных тестов
- `app/` — test-файлы рядом с production-кодом
- `core_ui/` — `test_access_permissions.py`
- `servers/`, `studio/` — некоторые smoke-тесты

`pyproject.toml` перечисляет `testpaths = ["tests", "app", "core_ui", ...]` — тесты собираются вручную, нет единой конвенции.

### 4.7 `passwords/` — зомби-модуль

Модуль существует, не подключён, но и не удалён. Создаёт ложное ощущение, что он делает что-то полезное. Функциональность покрыта `ManagedSecret`.

### 4.8 Tight Coupling между `servers` и `studio`

`studio` напрямую импортирует `servers.models.Server` для dropdowns в pipeline-узлах. `servers.agent_engine` использует `studio.models.AgentConfig`. Это создаёт циклическую зависимость на уровне приложений.

### 4.9 Отсутствие API-версионирования

Все эндпойнты `servers/` и `studio/` не версионированы (нет `/api/v1/`). Только `desktop_api` имеет `/api/desktop/v1/`. При изменении контракта нет возможности плавного перехода.

### 4.10 `lib/i18n.tsx` — переводы как код

52 KB переводов встроены в TSX-файл вместо отдельных JSON. Любое добавление строки требует изменения кода, нет возможности подключить внешний i18n-сервис без рефакторинга.

### 4.11 `lib/api.ts` — монолитный API-клиент

133 KB — все fetch-вызовы всей платформы в одном файле. При добавлении нового endpoint нужно редактировать этот файл, что приводит к конфликтам при командной разработке.

### 4.12 Inline конфигурация в `settings.py`

`settings.py` содержит 749 строк с условной логикой, env-переменными для 10+ разных подсистем. Нет разделения на `base.py`, `development.py`, `production.py`.

---

## 5. Рекомендации по улучшению

### 5.1 Ввести сервисный слой в Django

```python
# Вместо logic в views.py:
# servers/services/agent_service.py
class AgentRunService:
    def create_run(self, agent: ServerAgent, user: User) -> AgentRun: ...
    def stop_run(self, run: AgentRun) -> None: ...
```

Views становятся тонкими: только валидация входных данных, вызов service, формирование ответа.

### 5.2 Разбить god files

**`servers/views.py`** → разделить по доменам:
```
servers/views/
├── server_crud.py
├── server_files.py
├── server_linux_ui.py
├── server_monitoring.py
├── server_agents.py
└── server_memory.py
```

**`servers/consumers.py`** → разделить:
```
servers/consumers/
├── ssh_terminal.py
├── rdp_terminal.py
└── agent_live.py
```

**`app/agent_kernel/memory/store.py`** → разделить по операциям:
```
memory/
├── ingestion.py
├── compaction.py  (уже есть)
├── dreams.py
├── store.py  (только оркестрация)
```

**`lib/api.ts`** → разделить по доменам:
```
lib/api/
├── auth.ts
├── servers.ts
├── agents.ts
├── studio.ts
├── settings.ts
└── index.ts  (re-exports)
```

### 5.3 Ввести API-версионирование

```python
# web_ui/urls.py
path('api/v1/', include('servers.api_v1.urls')),
path('api/v1/', include('studio.api_v1.urls')),
```

### 5.4 Вынести переводы в JSON

```
ai-server-terminal-main/src/locales/
├── ru.json
├── en.json
```
Использовать `react-i18next` вместо self-made `i18n.tsx`.

### 5.5 Разделить settings.py

```python
web_ui/settings/
├── base.py        # Общие настройки
├── development.py # DEBUG=True, SQLite, InMemoryChannelLayer
├── production.py  # Postgres, Redis, Security headers
└── test.py        # Тестовые overrides
```

### 5.6 Очистить корень репозитория

Создать `scripts/` и перенести все `patch_*.py`, `fix*.py`, `create_*.py` туда.  
Удалить: `original_page.tsx`, `diff.txt`, `key_mcp.py.new`, `StudioSkillsPage.tsx.bak`.  
Корневой Vite/frontend конфиг либо удалить, либо преобразовать в monorepo-конфиг (`pnpm workspaces`).

### 5.7 Унифицировать расположение тестов

```
tests/
├── unit/          # pytest unit тесты (app/, core_ui/, servers/, studio/)
├── integration/   # текущие тесты из tests/
└── e2e/           # Playwright (сейчас в ai-server-terminal-main/e2e/)
```

### 5.8 Убрать циклическую зависимость servers ↔ studio

Ввести shared Django-app `shared/` или использовать Django signals / event bus вместо прямых импортов.

### 5.9 Задокументировать две memory-системы

Добавить явную архитектурную диаграмму в `docs/`. Добавить комментарий в `SSHTerminalConsumer` с объяснением разницы.

### 5.10 Удалить `passwords/`

Либо подключить (если нужно), либо удалить директорию полностью.

---

## 6. Предлагаемая новая структура

```
c:\WebTrerm/
│
├── backend/                        # Весь Python/Django код
│   ├── web_ui/                     # Django project config
│   │   ├── settings/
│   │   │   ├── base.py
│   │   │   ├── development.py
│   │   │   ├── production.py
│   │   │   └── test.py
│   │   ├── urls.py
│   │   ├── asgi.py
│   │   └── routing.py
│   │
│   ├── core_ui/                    # Auth, users, permissions, audit
│   │   ├── views/
│   │   │   ├── auth.py
│   │   │   ├── access.py
│   │   │   ├── settings.py
│   │   │   └── admin.py
│   │   ├── services/
│   │   │   ├── auth_service.py
│   │   │   └── access_service.py
│   │   ├── models.py
│   │   ├── middleware.py
│   │   └── ...
│   │
│   ├── servers/                    # Серверы, терминалы, агенты
│   │   ├── views/
│   │   │   ├── server_crud.py
│   │   │   ├── server_files.py
│   │   │   ├── server_linux_ui.py
│   │   │   ├── server_monitoring.py
│   │   │   ├── server_agents.py
│   │   │   └── server_memory.py
│   │   ├── consumers/
│   │   │   ├── ssh_terminal.py
│   │   │   ├── rdp_terminal.py
│   │   │   └── agent_live.py
│   │   ├── services/
│   │   │   ├── agent_service.py
│   │   │   ├── memory_service.py
│   │   │   └── monitor_service.py
│   │   ├── models.py
│   │   └── ...
│   │
│   ├── studio/                     # Pipelines, MCP, skills
│   │   ├── views/
│   │   │   ├── pipeline_views.py
│   │   │   ├── mcp_views.py
│   │   │   ├── skill_views.py
│   │   │   └── trigger_views.py
│   │   ├── executor/
│   │   │   ├── base.py
│   │   │   ├── llm_node.py
│   │   │   ├── ssh_node.py
│   │   │   ├── agent_node.py
│   │   │   └── ...
│   │   ├── models.py
│   │   └── ...
│   │
│   ├── app/                        # Shared services (без изменений в структуре)
│   │   ├── core/
│   │   ├── agent_kernel/
│   │   └── tools/
│   │
│   ├── manage.py
│   └── requirements-mini.txt
│
├── frontend/                       # React SPA (перемещён из ai-server-terminal-main/)
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   ├── features/               # Feature-based организация (новое)
│   │   │   ├── servers/
│   │   │   ├── agents/
│   │   │   ├── studio/
│   │   │   └── settings/
│   │   ├── api/                    # Разделённый API-клиент
│   │   │   ├── auth.ts
│   │   │   ├── servers.ts
│   │   │   ├── studio.ts
│   │   │   └── index.ts
│   │   ├── locales/                # i18n JSON файлы
│   │   │   ├── ru.json
│   │   │   └── en.json
│   │   └── lib/
│   ├── vite.config.ts
│   └── package.json
│
├── desktop/                        # C# WinUI (без изменений)
│
├── docker/                         # Docker infrastructure
│   ├── backend.Dockerfile
│   ├── frontend.Dockerfile
│   ├── nginx/
│   └── mcp/                        # MCP-серверы (перемещён key_mcp.py сюда)
│       ├── keycloak_mcp.py
│       └── demo_mcp.py
│
├── tests/                          # Единая папка тестов
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── scripts/                        # Утилиты (сейчас patch_*.py в корне)
│   ├── seed_servers.py
│   └── create_pipeline.py
│
├── docs/                           # Документация
│   ├── architecture.md
│   ├── memory_systems.md
│   └── api_reference.md
│
├── docker-compose.yml
├── pyproject.toml
└── AGENTS.md
```

**Почему лучше:**
- **Чёткое разделение** backend/frontend/desktop/docker — нет смешения в корне
- **Сервисный слой** исключает god-views
- **Feature-based** организация фронтенда масштабируется при добавлении новых разделов
- **Разделённый api-клиент** устраняет конфликты при командной разработке
- **Settings split** — разные конфиги для dev/prod/test
- **Единая папка тестов** — простая команда `pytest tests/`
- **`docs/`** — живая документация рядом с кодом

---

## 7. План миграции

> **Принцип:** не ломать работающее. Каждый шаг независим и может быть откатан.

### Шаг 1 — Очистка мусора (1-2 дня)

1. Удалить из репозитория:
   - `original_page.tsx`, `diff.txt`, `key_mcp.py.new`
   - `StudioSkillsPage.tsx.bak`
   - `.codex-logs/`, `.playwright-cli/`, `.playwright-mcp/`, `.tmp_*/`
2. Создать папку `scripts/` и перенести `patch_*.py`, `fix*.py`, `create_mega_pipeline.py`, `create_pipeline.sql`
3. Добавить перечисленные файлы в `.gitignore`

### Шаг 2 — Изоляция фронтенда (2-3 дня)

1. Проверить, используется ли корневой `vite.config.ts` / `package.json` где-либо в CI/CD и docker
2. Если нет — удалить дублирующий фронтенд из корня
3. Переименовать `ai-server-terminal-main/` → `frontend/` (обновить `docker-compose.yml`, `docker/frontend.Dockerfile`)

### Шаг 3 — Разделение `settings.py` (1 день)

1. Создать `web_ui/settings/base.py` — перенести всё общее
2. Создать `web_ui/settings/development.py` — dev-overrides
3. Создать `web_ui/settings/production.py` — prod-overrides
4. `manage.py` → `DJANGO_SETTINGS_MODULE = "web_ui.settings.development"` по умолчанию
5. Обновить `pyproject.toml` и `docker-compose.yml`

### Шаг 4 — Разбить `views.py` по доменам (3-5 дней на каждый модуль)

Начать с `servers/`:
1. Создать `servers/views/` как Python-пакет (`__init__.py` со всеми re-exports)
2. Перенести группы функций в отдельные файлы поодиночке
3. Убедиться, что `servers/urls.py` продолжает работать (импорты через `__init__.py`)
4. Запустить `pytest tests/test_servers_api_smoke.py` после каждого переноса

Повторить для `core_ui/`, `studio/`.

### Шаг 5 — Разбить `consumers.py` (2-3 дня)

1. Создать `servers/consumers/` — пакет
2. Перенести `SSHTerminalConsumer` → `ssh_terminal.py`
3. Перенести `RDPTerminalConsumer` → `rdp_terminal.py`
4. Перенести `AgentLiveConsumer` → `agent_live.py`
5. Обновить `servers/routing.py` импорты

### Шаг 6 — Ввести сервисный слой (1-2 недели)

Начать с нового кода: любая новая бизнес-логика идёт в `services/`, не в `views/`.
Постепенно выносить существующую логику при рефакторинге конкретных эндпойнтов.

### Шаг 7 — Разбить `api.ts` на фронтенде (2-3 дня)

1. Создать `frontend/src/api/` — папку
2. Выделить функции по доменам в отдельные файлы
3. Создать `index.ts` с re-exports для обратной совместимости
4. Запустить Playwright e2e-тесты

### Шаг 8 — Вынести i18n в JSON (1-2 дня)

1. Установить `react-i18next`
2. Экспортировать объекты переводов из `i18n.tsx` в `locales/ru.json`, `locales/en.json`
3. Заменить использование `useI18n()` на `useTranslation()` постепенно
4. Удалить `i18n.tsx`

### Шаг 9 — Разбить `memory/store.py` (3-5 дней)

1. Выделить `memory/ingestion.py` — только ingestion
2. Выделить `memory/dreams.py` — только dreams/overview
3. `store.py` остаётся как оркестратор, делегирующий в подмодули
4. Обновить все импорты; `app/agent_kernel/memory/__init__.py` должен сохранять публичный API

### Шаг 10 — Устранить циклическую зависимость servers ↔ studio (2-3 дня)

1. Создать shared app или использовать Django lazy imports / `apps.get_model()`
2. Убрать прямые `from servers.models import Server` из `studio/`; заменить на lazy lookup

### Шаг 11 — Удалить `passwords/` (1 час)

1. Убедиться, что нигде нет `from passwords import ...`
2. Удалить директорию
3. Убрать из `.gitignore` если упоминается

### Шаг 12 — Унифицировать тесты (1 день)

1. Создать `tests/unit/` и переместить тесты из `app/test_*.py` туда
2. Переместить `core_ui/test_access_permissions.py` → `tests/unit/test_access_permissions.py`
3. Обновить `pyproject.toml`: `testpaths = ["tests"]`

---

## Приложение: конфигурационные файлы

| Файл | Назначение |
|---|---|
| `.env` | Локальные секреты и переменные (не коммитить) |
| `.env.example` | Шаблон переменных для разработки |
| `.env.production.example` | Шаблон для production |
| `pyproject.toml` | Ruff lint/format, pytest config, project metadata |
| `requirements-mini.txt` | Python runtime-зависимости |
| `requirements-full.txt` | Полные зависимости (для full-platform) |
| `docker-compose.yml` | Локальная dev/test-среда |
| `docker-compose.production.yml` | Production-деплой |
| `render.yaml` | Деплой на Render.com |
| `.model_config.json` | Конфигурация LLM-моделей (runtime) |
| `.notification_config.json` | Настройки уведомлений Telegram/Email |
| `keycloak_profiles.json` | Профили Keycloak для MCP |

---

*Документ составлен на основе анализа структуры директорий, файлов и их размеров, содержимого ключевых конфигурационных и кодовых файлов. Предположения явно помечены как [Предположение].*
