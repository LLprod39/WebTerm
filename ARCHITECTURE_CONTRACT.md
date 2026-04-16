# WEU AI Platform — Архитектурный Контракт

> Версия: 1.0 · Апрель 2026  
> Статус: **ДЕЙСТВУЮЩИЙ** — обязателен для всей команды  
> Основан на: полном аудите кодовой базы `c:\WebTrerm`

Этот документ **не описывает** систему — он **задаёт**, какой она должна быть.  
Любое архитектурное решение, противоречащее этому документу, требует явного обсуждения и обновления контракта.

---

## 1. Архитектурный стиль

### 1.1 Текущее состояние

**Стиль: Distributed Monolith (патологическая форма монолита)**

Django-приложения физически разделены, но архитектурно слиты в одно целое:
- `servers/agent_engine.py` напрямую импортирует `studio.skill_policy`, `studio.skill_registry`
- `studio/pipeline_executor.py` импортирует `servers.mcp_tool_runtime`
- `servers/signals.py` внутри transaction callback делает `from studio.trigger_dispatch import ...`
- `app/agent_kernel/memory/store.py` напрямую импортирует `django.db.transaction` — ядро агента зависит от ORM
- Вся бизнес-логика в `views.py` — нет слоя сервисов

Итог: нельзя изменить `studio` без риска поломки `servers` и наоборот. Нельзя тестировать `agent_kernel` без Django.

### 1.2 Целевое состояние

**Стиль: Modular Monolith с чёткими bounded contexts**

Характеристики целевого стиля:
- Одно Django-приложение (один процесс, одна БД) — **без микросервисов**
- Каждый bounded context — **независимый модуль** со своим публичным API
- Взаимодействие между контекстами — **только через определённые интерфейсы** (сервисы, Django signals, явные вызовы API-модуля)
- `app/agent_kernel` — **чистый Python**, без зависимости от Django ORM
- Новая функциональность добавляется как новый узел/провайдер/плагин, **не расширяя существующие god files**

### 1.3 Почему не микросервисы

- Текущая команда не имеет инфраструктуры для распределённых транзакций
- Основная нагрузка — WebSocket + LLM latency, не CPU/memory scaling
- SSH-терминал и agent execution требуют shared state (session, memory) — разделение усложняет без выгоды
- Monolith можно извлечь в сервис позже, когда границы контекстов чётко зафиксированы

**Правило:** Не переходить к микросервисам, пока bounded contexts не стабилизированы в рамках монолита минимум 6 месяцев.

---

## 2. Bounded Contexts

### Карта контекстов

```
┌─────────────────────────────────────────────────────────────────┐
│                        Frontend SPA                              │
│          (ai-server-terminal-main/src)                           │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP REST + WebSocket
┌──────────────────────────▼──────────────────────────────────────┐
│                     [Identity & Access]                          │
│                        core_ui/                                  │
│   Auth · Permissions · Users · Audit · Desktop API              │
└─────┬──────────────────────────────────────────────┬────────────┘
      │                                               │
      │ (всё зависит от Identity)                     │
      ▼                                               ▼
┌─────────────────────┐               ┌──────────────────────────┐
│  [Server Domain]    │               │  [Pipeline & Automation]  │
│    servers/         │◄──signals─────│       studio/             │
│  SSH·RDP·Monitor    │               │  Pipelines·MCP·Skills     │
│  Agents·Memory      │               │  Triggers·Notifications   │
└────────┬────────────┘               └──────────────┬───────────┘
         │                                            │
         │ uses                                       │ uses
         ▼                                            ▼
┌──────────────────────────────────────────────────────────────┐
│                    [Agent Platform]                           │
│                    app/agent_kernel/                          │
│       Runtime · Memory · Permissions · Tools · Hooks         │
│       ← Pure Python, НЕТ зависимостей от Django ORM →       │
└──────────────────────────────┬───────────────────────────────┘
                               │ uses
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                   [Shared Services]                           │
│                     app/core/ + app/tools/                   │
│            LLM Providers · SSH Tools · Safety                │
└──────────────────────────────────────────────────────────────┘
```

---

### 2.1 Identity & Access Context (`core_ui/`)

**Зона ответственности:**
- Аутентификация и сессии пользователей (cookie-based, desktop refresh tokens)
- Feature-based permissions (`UserAppPermission`, `GroupAppPermission`)
- Управление пользователями и группами Django
- Audit logging всех HTTP-действий
- Domain SSO (заголовки `X-Forwarded-User`)
- Desktop API (`DesktopRefreshToken`)
- Шифрование секретов (`ManagedSecret`)

**Чего НЕ входит:**
- Серверная логика, агенты, pipelines — ничего domain-специфичного
- `ChatSession`/`ChatMessage` — устаревшие модели, подлежат удалению

**Данные (владелец):**
- `User`, `Group` (Django built-in)
- `UserAppPermission`, `GroupAppPermission`
- `UserActivityLog`, `LLMUsageLog`
- `DesktopRefreshToken`
- `ManagedSecret`

**Публичный API (что предоставляет другим контекстам):**
```python
# core_ui/services/auth.py — публичный контракт
def get_user_feature_permissions(user: User) -> dict[str, bool]: ...
def log_activity(user, action, status, **kwargs) -> None: ...
def get_managed_secret(namespace: str, object_id: int, key: str) -> str | None: ...
def set_managed_secret(namespace: str, object_id: int, key: str, value: str) -> None: ...
```

**Зависит от:** Django, ничего из servers/studio/app

**Кому МОЖНО зависеть от Identity:**
- servers ✅, studio ✅, app/agent_kernel ❌ (только через инъекцию зависимости)

**ЗАПРЕЩЕНО:**
- `core_ui` не импортирует `servers`, `studio`, `app.agent_kernel`
- `app.agent_kernel` не импортирует `core_ui` напрямую

---

### 2.2 Server Domain Context (`servers/`)

**Зона ответственности:**
- CRUD серверов и групп
- SSH/RDP подключения и терминал (WebSocket)
- SFTP/файловый менеджер
- Linux UI (сервисы, процессы, диски, Docker, логи)
- Server health monitoring и alerts
- Server knowledge base
- Layered server memory (модели + ingestion pipeline)
- Server agents (запуск, управление, AgentRun)
- Watcher-сервис

**Чего НЕ входит:**
- Pipeline execution логика — это `studio`
- LLM-провайдеры — это `app/core`
- Agent runtime (ReAct loop, permissions) — это `app/agent_kernel`
- Skill definitions — это `studio`

**Данные (владелец):**
```
Server, ServerGroup, ServerGroupMember, ServerGroupSubscription
ServerShare, ServerConnection, ServerCommandHistory
GlobalServerRules, ServerKnowledge, ServerMemoryPolicy
BackgroundWorkerState, ServerHealthCheck, ServerAlert
ServerAgent, AgentRun, AgentRunEvent, AgentTask
ServerMemoryEvent, ServerMemoryEpisode, ServerMemorySnapshot, ServerMemoryRevalidation
ServerWatcherDraft
```

**Публичный API (что предоставляет другим контекстам):**
```python
# servers/services/server_query.py
def get_servers_for_user(user: User) -> QuerySet[Server]: ...
def get_server(server_id: int, user: User) -> Server: ...

# servers/services/agent_service.py — публичный контракт
def create_agent_run(agent: ServerAgent, user: User, **kwargs) -> AgentRun: ...
def get_run_events(run_id: int) -> list[AgentRunEvent]: ...
```

**Зависит от:** Identity (для `ManagedSecret`, `log_activity`), Agent Platform (для execution), Shared Services

**Кому МОЖНО зависеть от Server Domain:**
- `studio` — только через публичный API (`get_servers_for_user`), НЕ прямые модели
- Frontend — через REST API

**ЗАПРЕЩЕНО:**
- `servers` не импортирует `studio.models` напрямую
- `servers/signals.py` не делает `from studio.trigger_dispatch import ...` внутри handler — использовать Django signal или обратный вызов через интерфейс
- `servers/views.py` не содержит бизнес-логику агентов inline

---

### 2.3 Agent Platform Context (`app/agent_kernel/`)

**Зона ответственности:**
- Домен агентов: типы (`ToolSpec`, `AgentState`, `PermissionDecision`, `ServerMemoryCard`)
- Permission engine: PLAN / SAFE / ASSISTED / AUTONOMOUS / AUTO_GUARDED
- Memory system: ingestion, compaction, dreams, repair, prompt-cards
- Runtime: context building, LLM response parsing, subagent dispatch
- Hooks: lifecycle callbacks для observability
- Tool registry (внутренний)
- Sandbox profiles

**Чего НЕ входит:**
- Django models — `agent_kernel` не знает о `ServerMemoryEvent` и других ORM-моделях напрямую
- HTTP views, WebSocket consumers
- Конкретные SSH-соединения — это `app/tools/ssh_tools.py`

**Критическое ограничение: agent_kernel — Pure Python**

Текущее нарушение: `app/agent_kernel/memory/store.py` строки 12-14:
```python
from asgiref.sync import async_to_sync, sync_to_async
from django.db import transaction   # ← НАРУШЕНИЕ
from django.utils import timezone
```

`DjangoServerMemoryStore` — конкретная Django-реализация — должна быть вынесена из `agent_kernel` в `servers/` как адаптер.

**Целевая архитектура:**
```python
# app/agent_kernel/memory/store.py — только протокол (уже есть)
class MemoryStore(Protocol):
    async def get_server_card(self, server_id: int) -> ServerMemoryCard: ...
    async def append_run_summary(self, run_id: int, summary: dict) -> str: ...
    # ...

# servers/adapters/memory_store.py — Django-реализация
class DjangoServerMemoryStore:
    """Adapter: реализует MemoryStore поверх Django ORM."""
    # Все import django.db здесь
```

**Публичный API (что предоставляет другим контекстам):**
```python
# app/agent_kernel/__init__.py
from app.agent_kernel.permissions.engine import PermissionEngine
from app.agent_kernel.domain.specs import AgentState, PermissionMode, ToolSpec
from app.agent_kernel.hooks.manager import HookManager

# Конкретные хранилища предоставляет потребитель через DI:
# engine = AgentEngine(memory_store=DjangoServerMemoryStore(), ...)
```

**Зависит от:** `app/core/llm` (через DI), `app/tools` (через DI), loguru — **ничего Django**

**Кому МОЖНО зависеть от Agent Platform:**
- `servers` ✅ (создаёт `AgentEngine`, передаёт Django memory store)
- `studio` ✅ (создаёт pipeline nodes с AgentEngine)

**ЗАПРЕЩЕНО:**
- `agent_kernel` не импортирует `servers.models`, `studio.models`, `core_ui.models`
- `agent_kernel` не импортирует `django.*` (кроме `django.utils.timezone` — допустимо как utility)

---

### 2.4 Pipeline & Automation Context (`studio/`)

**Зона ответственности:**
- Pipeline editor (модели: узлы + рёбра как JSON)
- Pipeline execution engine
- MCP server pool (конфигурация и клиент)
- Agent configs (`AgentConfig`)
- Webhook/cron/monitoring triggers
- Skill authoring, registry, policy
- Notifications (Telegram, Email)
- Live updates pipeline runs через WebSocket

**Чего НЕ входит:**
- SSH-соединения напрямую — делегировать через `app/tools/ssh_tools`
- Server memory — это `servers/`
- User management — это `core_ui/`

**Данные (владелец):**
```
MCPServerPool, AgentConfig
Pipeline, PipelineTrigger, PipelineRun
PipelineTemplate
```

**Зависит от:** Identity (auth), Agent Platform (execution), Shared Services

**Кому МОЖНО зависеть от Pipeline:**
- Frontend — через REST API
- `servers/signals.py` — вызывает `studio` для запуска monitoring-triggered pipelines  
  ⚠️ **Сейчас это прямой import — нужно переделать через Django signal**

**ЗАПРЕЩЕНО:**
- `studio` не импортирует `servers.models` напрямую (только через публичный API)
- `studio/pipeline_executor.py` не импортирует `servers.mcp_tool_runtime` — `MCPBoundTool` должен быть в `studio` или `app/`

---

### 2.5 Shared Services (`app/core/`, `app/tools/`)

**Зона ответственности:**
- LLM провайдеры: Gemini, Claude, OpenAI, Grok, Ollama (`app/core/llm.py`)
- Model config и registry (`app/core/model_config.py`, `provider_registry.py`)
- SSH execute/connect/disconnect (`app/tools/ssh_tools.py`)
- Server tools (`app/tools/server_tools.py`)
- Safety checker (`app/tools/safety.py`)

**Это нижний уровень — от него зависят все, он не зависит ни от кого.**

**ЗАПРЕЩЕНО:**
- `app/tools` не импортирует `servers.*`, `studio.*`, `core_ui.*`
- `app/core` не импортирует `servers.*`, `studio.*`, `core_ui.*`
- `app/core/llm.py` не пишет `LLMUsageLog` напрямую — логирование через callback/hook

---

### 2.6 Frontend Context (`ai-server-terminal-main/`)

**Зона ответственности:**
- SPA: все страницы, компоненты, роутинг
- Feature access checks (клиентская сторона)
- WebSocket клиенты (XTerm, AgentRun live, PipelineRun live)
- i18n

**Граница:** Frontend общается с backend **только** через:
- `GET/POST /api/*` — JSON REST
- `GET/POST /servers/api/*` — JSON REST  
- `wss://.../ws/*` — WebSocket

**ЗАПРЕЩЕНО:**
- Никаких серверных шаблонов Django в основном UI (только редиректы из `core_ui/urls.py`)
- Никаких прямых DB-запросов из frontend

---

## 3. Architecture Constraints

Эти правила **обязательны**. Нарушение = отказ в code review.

### 3.1 Слой ответственности

```
CONSTRAINT-01: Views не содержат бизнес-логику.
  View = [валидация входных данных] + [вызов service] + [формирование HTTP-ответа]
  Максимум 30 строк кода в теле view-функции.

CONSTRAINT-02: Вся бизнес-логика живёт в services/.
  servers/services/, studio/services/, core_ui/services/
  Service — обычный Python-класс или функция, не знающая о HTTP.

CONSTRAINT-03: Django Consumer (WebSocket) не содержит бизнес-логику.
  Consumer = управление соединением + делегирование в service/engine.
```

### 3.2 Зависимости между контекстами

```
CONSTRAINT-04: agent_kernel не импортирует django.db.
  Исключение: django.utils.timezone — допустимо.
  DjangoServerMemoryStore переносится в servers/adapters/.

CONSTRAINT-05: studio не импортирует servers.models напрямую.
  Для получения серверов: servers.services.server_query.get_servers_for_user()
  servers.mcp_tool_runtime переносится в studio/ или app/.

CONSTRAINT-06: servers/signals.py не делает прямой import из studio внутри signal handler.
  Паттерн: Django signal "alert_opened" → studio подписывается через Signal.connect()
  Или: servers вызывает интерфейс, зарегистрированный studio при startup.

CONSTRAINT-07: Запрещены циклические зависимости между Django-приложениями.
  Проверяется инструментом: import-linter или ручной аудит при каждом PR.

CONSTRAINT-08: Общая логика между контекстами идёт в app/, не дублируется.
```

### 3.3 Файлы и размер

```
CONSTRAINT-09: Ни один Python-файл не превышает 500 строк.
  Исключения требуют явного обоснования в PR.

CONSTRAINT-10: Ни один TypeScript-файл не превышает 400 строк.
  Компоненты > 200 строк разбиваются на sub-components.

CONSTRAINT-11: views.py всегда является пакетом (папкой), не одним файлом,
  если в модуле > 5 view-функций.
```

### 3.4 Тестируемость

```
CONSTRAINT-12: Service-функции тестируются без HTTP-запросов (pytest, не APIClient).

CONSTRAINT-13: agent_kernel/* тестируется без запущенного Django (pytest --no-django).

CONSTRAINT-14: Каждый новый pipeline node type имеет unit-тест в tests/unit/studio/.

CONSTRAINT-15: Каждый новый agent tool имеет unit-тест с mock SSH.
```

### 3.5 Pipeline и Agent расширяемость

```
CONSTRAINT-16: Новый тип pipeline node — это новый файл studio/nodes/<type>.py,
  не модификация pipeline_executor.py.

CONSTRAINT-17: Новый тип агента — это новая роль в app/agent_kernel/domain/roles.py,
  не новый класс Engine.

CONSTRAINT-18: Новый LLM-провайдер — это новый класс в app/core/llm.py + запись
  в provider_registry.py. Не трогает ни один другой файл.
```

---

## 4. Ключевые системы

### 4.1 Agent Platform — Целевая архитектура

#### Разделение ответственности

```
app/agent_kernel/
│
├── domain/               УРОВЕНЬ 0 — Типы (нет зависимостей)
│   ├── specs.py          # ToolSpec, AgentState, PermissionDecision, MemoryRecord...
│   └── roles.py          # Декларативные роли агентов
│
├── permissions/          УРОВЕНЬ 1 — Решение о допуске (зависит только от domain)
│   ├── engine.py         # PermissionEngine: входит ToolSpec + command, выходит PermissionDecision
│   └── modes.py          # PermissionMode constants
│
├── memory/               УРОВЕНЬ 1 — Абстракция памяти (зависит только от domain)
│   ├── store.py          # MemoryStore Protocol — ТОЛЬКО интерфейс
│   ├── compaction.py     # Pure функции: compact_text, extract_signal_lines
│   ├── redaction.py      # Pure функции: redact_for_storage, sanitize_*
│   ├── repair.py         # Pure функции: decay_confidence, compute_freshness
│   └── server_cards.py   # Pure функции: build_server_memory_card → ServerMemoryCard
│
├── runtime/              УРОВЕНЬ 2 — Оркестрация (зависит от domain + memory Protocol)
│   ├── context.py        # build_ops_prompt_context(memory_store: MemoryStore, ...)
│   ├── parsing.py        # parse_response(text) → Action
│   └── subagents.py      # SubagentDispatcher
│
├── hooks/                УРОВЕНЬ 2 — Observability
│   └── manager.py        # HookManager — lifecycle callbacks
│
├── sandbox/              УРОВЕНЬ 1 — Профили sandbox
│   └── manager.py
│
└── tools/                УРОВЕНЬ 1 — Tool registry (внутренний)
    └── registry.py

servers/adapters/         ← НОВАЯ ПАПКА
└── memory_store.py       # DjangoServerMemoryStore(MemoryStore): вся Django ORM логика здесь

servers/engines/          ← НОВАЯ ПАПКА (выделить из agent_engine.py)
├── react_engine.py       # AgentEngine (ReAct loop)
└── multi_engine.py       # MultiAgentEngine
```

#### Как они взаимодействуют

```
AgentEngine (servers/engines/react_engine.py)
    │
    ├── получает memory_store: MemoryStore (инъекция из servers/)
    ├── получает permission_engine: PermissionEngine (создаёт сам)
    ├── получает hook_manager: HookManager (инъекция)
    ├── вызывает app/core/llm.py → LLM API
    ├── вызывает app/tools/ssh_tools.py → SSH target server
    └── пишет результаты через memory_store.append_run_summary()

DjangoServerMemoryStore (servers/adapters/memory_store.py)
    │
    ├── читает/пишет ServerMemoryEvent, ServerMemoryEpisode, ServerMemorySnapshot
    ├── вызывает app/agent_kernel/memory/compaction.py (pure functions)
    ├── вызывает app/agent_kernel/memory/repair.py (pure functions)
    └── вызывает app/core/llm.py для dream/compaction LLM calls
```

#### Что НЕ должно знать друг о друге

| A | B | Направление | Статус |
|---|---|---|---|
| `PermissionEngine` | `MemoryStore` | не знает | ✅ |
| `MemoryStore Protocol` | `Django ORM` | не знает | ⚠️ нарушено (исправить) |
| `compaction.py` | `repair.py` | не знает | ✅ |
| `domain/specs.py` | любой сервис | не знает | ✅ |
| `HookManager` | `AgentEngine` | не знает | ✅ |

---

### 4.2 Pipeline Engine — Целевая архитектура

#### Проблема

`studio/pipeline_executor.py` (114 KB) содержит:
- Топологическую сортировку графа
- Диспатч по типам узлов (15+ типов)
- Логику каждого типа узла (SSH, LLM, MCP, condition, parallel, approval, email, telegram...)
- Telegram polling loop
- Template rendering
- Approval token management

Это нарушает CONSTRAINT-09 и делает добавление нового узла опасным.

#### Целевая архитектура Node Registry

```
studio/
├── executor/
│   ├── __init__.py
│   ├── engine.py           # PipelineExecutor: топологический обход + диспатч
│   ├── registry.py         # NodeRegistry: регистрация типов узлов
│   ├── context.py          # ExecutionContext: shared state между узлами
│   └── nodes/              # Один файл = один тип узла
│       ├── base.py         # BaseNode(ABC): execute(ctx) → NodeResult
│       ├── agent_react.py  # AgentReactNode
│       ├── agent_multi.py  # AgentMultiNode
│       ├── agent_ssh.py    # DirectSSHNode
│       ├── agent_llm.py    # LLMQueryNode
│       ├── agent_mcp.py    # MCPCallNode
│       ├── logic_condition.py
│       ├── logic_parallel.py
│       ├── logic_wait.py
│       ├── logic_approval.py  # HumanApprovalNode (+ Telegram polling)
│       ├── output_report.py
│       ├── output_webhook.py
│       ├── output_email.py
│       └── output_telegram.py
```

#### Как добавить новый тип узла (целевой процесс)

```python
# 1. Создать файл studio/executor/nodes/output_slack.py
from studio.executor.nodes.base import BaseNode, NodeResult

class SlackOutputNode(BaseNode):
    node_type = "output/slack"
    
    async def execute(self, ctx: ExecutionContext) -> NodeResult:
        webhook_url = self.node_data.get("webhook_url")
        message = ctx.resolve_template(self.node_data.get("message", ""))
        # ... отправить в Slack
        return NodeResult(output={"sent": True})

# 2. Зарегистрировать в studio/executor/registry.py
registry.register(SlackOutputNode)

# 3. Написать тест в tests/unit/studio/nodes/test_slack_output.py
# Всё. Не трогать pipeline_executor.py.
```

#### ExecutionContext — shared state между узлами

```python
@dataclass
class ExecutionContext:
    run_id: int
    user: User
    pipeline: Pipeline
    node_outputs: dict[str, Any]          # results предыдущих узлов
    stop_event: threading.Event
    memory_store: MemoryStore             # инъекция
    hook_manager: HookManager             # инъекция
    
    def resolve_template(self, template: str) -> str: ...
    def get_upstream_output(self, node_id: str) -> Any: ...
    def emit_event(self, event_type: str, data: dict) -> None: ...
```

---

### 4.3 Server Domain — Целевая архитектура

#### Разделение

```
servers/
├── models.py                  # Только Django ORM models (без бизнес-логики)
│
├── views/                     # Тонкие views (CONSTRAINT-01)
│   ├── server_crud.py         # Создание/чтение/обновление/удаление серверов
│   ├── server_files.py        # SFTP/файловый менеджер
│   ├── server_linux_ui.py     # Linux UI (сервисы, процессы, диски, Docker)
│   ├── server_monitoring.py   # Health, alerts, watchers
│   ├── server_agents.py       # Agent CRUD + runs (тонко: делегирует в services/)
│   └── server_memory.py       # Memory API (snapshots, overview, dreams)
│
├── services/                  # Бизнес-логика (CONSTRAINT-02)
│   ├── server_query.py        # get_servers_for_user(), get_server() — публичный API
│   ├── agent_service.py       # create_run(), stop_run(), get_run_status()
│   ├── memory_service.py      # purge_memory(), run_dreams(), get_overview()
│   ├── monitor_service.py     # check_health(), resolve_alert()
│   └── sftp_service.py        # file_read(), file_write(), file_list()
│
├── adapters/                  # Django-реализации внешних интерфейсов
│   └── memory_store.py        # DjangoServerMemoryStore(MemoryStore)
│
├── engines/                   # Agent execution (выделить из agent_engine.py)
│   ├── react_engine.py        # AgentEngine (ReAct loop)
│   └── multi_engine.py        # MultiAgentEngine
│
├── consumers/                 # WebSocket consumers (тонкие)
│   ├── ssh_terminal.py        # SSHTerminalConsumer → sftp_service, terminal_ai
│   ├── rdp_terminal.py        # RDPTerminalConsumer
│   └── agent_live.py          # AgentLiveConsumer
│
├── signals.py                 # Django signals → ingest_memory_event_task
├── tasks.py                   # Celery tasks (memory ingestion, dream cycle)
└── management/commands/       # Management commands (без изменений)
```

#### Что должно быть вынесено в services

| Текущее место | Вынести в |
|---|---|
| `views.py`: логика агентов (300+ строк) | `services/agent_service.py` |
| `views.py`: SFTP operations | `services/sftp_service.py` |
| `views.py`: health check, alerts | `services/monitor_service.py` |
| `consumers.py`: Terminal AI chat | `services/terminal_ai_service.py` |
| `linux_ui.py`: SSH-команды inline | `services/linux_ui_service.py` |

---

## 5. Взаимодействие между контекстами

### Карта взаимодействий

| Инициатор | Потребитель | Механизм | Sync/Async | Статус |
|---|---|---|---|---|
| `servers/signals.py` | `studio.trigger_dispatch` | прямой import | sync | ⚠️ НАРУШЕНИЕ — переделать |
| `servers/agent_engine.py` | `studio.skill_policy` | прямой import | sync | ⚠️ НАРУШЕНИЕ — переделать |
| `studio/pipeline_executor.py` | `servers.mcp_tool_runtime` | прямой import | sync | ⚠️ НАРУШЕНИЕ — переделать |
| `servers/signals.py` | `servers/tasks.py` | Celery task | async | ✅ правильно |
| `servers/views.py` | `core_ui.activity` | прямой вызов | sync | ✅ допустимо |
| `studio/pipeline_executor.py` | `app/agent_kernel.*` | прямой import | sync | ✅ допустимо |
| `servers/agent_engine.py` | `app/agent_kernel.*` | прямой import | sync | ✅ допустимо |

### 5.1 Правильный паттерн: servers → studio (мониторинг)

**Текущий (НАРУШЕНИЕ):**
```python
# servers/signals.py
def _launch_monitoring_pipelines(alert_id: int):
    from studio.trigger_dispatch import launch_monitoring_triggers_for_alert  # ← ПЛОХО
    launch_monitoring_triggers_for_alert(alert)
```

**Целевой (Django Signal):**
```python
# servers/signals.py
from django.dispatch import Signal
alert_opened = Signal()  # аргументы: alert_id, server_id, severity

@receiver(post_save, sender=ServerAlert)
def on_alert_saved(sender, instance, created, **kwargs):
    if created and not instance.is_resolved:
        transaction.on_commit(lambda: alert_opened.send(
            sender=ServerAlert, alert_id=instance.pk,
            server_id=instance.server_id, severity=instance.severity
        ))

# studio/apps.py
class StudioConfig(AppConfig):
    def ready(self):
        from servers.signals import alert_opened
        from studio.trigger_dispatch import launch_monitoring_triggers_for_alert
        alert_opened.connect(lambda **kw: launch_monitoring_triggers_for_alert(kw["alert_id"]))
```

### 5.2 Правильный паттерн: servers → studio (skills)

**Текущий (НАРУШЕНИЕ):**
```python
# servers/agent_engine.py
from studio.skill_policy import apply_skill_policies  # ← servers знает о studio
from studio.skill_registry import SkillDefinition
```

**Целевой (Protocol + DI):**
```python
# app/agent_kernel/domain/specs.py
class SkillProvider(Protocol):
    def resolve_skills(self, slugs: list[str]) -> list[Any]: ...
    def compile_policies(self, skills: list[Any]) -> Any: ...

# servers/engines/react_engine.py
class AgentEngine:
    def __init__(self, ..., skill_provider: SkillProvider | None = None): ...
    # skill_provider передаётся при создании из servers/views/server_agents.py

# studio/ предоставляет реализацию при старте:
engine = AgentEngine(..., skill_provider=StudioSkillProvider())
```

### 5.3 Memory ingestion flow (правильный паттерн — уже частично реализован)

```
Event (команда / healthcheck / alert)
    │
    ▼ Django Signal post_save
servers/signals.py
    │
    ▼ transaction.on_commit → Celery task
servers/tasks.ingest_memory_event_task
    │
    ▼ DjangoServerMemoryStore (servers/adapters/memory_store.py)
app/agent_kernel/memory/* (pure functions)
    │
    ▼ Django ORM write
ServerMemoryEvent → ServerMemoryEpisode → ServerMemorySnapshot
```

**Проблема:** `servers/tasks.py` использует `celery.shared_task`, но Celery нет в `requirements-mini.txt`. В текущей mini-конфигурации tasks выполняются синхронно. Нужно явно задокументировать fallback.

---

## 6. Масштабирование

### 6.1 Добавить новый тип агента

**Что нужно сделать:**
1. Добавить запись в `app/agent_kernel/domain/roles.py`:
```python
ROLE_SPECS["database_admin"] = RoleSpec(
    name="database_admin",
    title="Database Administrator Agent",
    permission_mode=PermissionMode.ASSISTED,
    allowed_tools=("ssh_execute", "file_read"),
    system_prompt_template="...",
)
```
2. Тест: `tests/unit/agent_kernel/test_roles.py`
3. Frontend: добавить в dropdown агентов через `/servers/api/agents/templates/`

**Что НЕ нужно трогать:** `AgentEngine`, `MultiAgentEngine`, `pipeline_executor.py`, любые views.

---

### 6.2 Добавить новый pipeline node

**Что нужно сделать:**
1. Создать `studio/executor/nodes/output_slack.py` (BaseNode subclass)
2. Зарегистрировать в `studio/executor/registry.py`
3. Написать тест `tests/unit/studio/nodes/test_output_slack.py`
4. Добавить компонент в frontend: `ai-server-terminal-main/src/components/pipeline/nodes/`

**Что НЕ нужно трогать:** `pipeline_executor.py` (после рефакторинга — ликвидируется как monolith).

---

### 6.3 Масштабировать execution plane агентов

Текущая архитектура: агент запускается в asyncio-задаче внутри Django-процесса.

**Горизонтальное масштабирование — 2 уровня:**

**Уровень 1 (краткосрочный): Celery worker pool**
```yaml
# docker-compose.production.yml — добавить:
agent-worker:
  command: celery -A web_ui worker -Q agent_runs -c 4
  # Агенты запускаются как Celery tasks, не в основном процессе
```
Требует: перенести `AgentEngine.run()` в `servers/tasks.run_agent_task`.

**Уровень 2 (долгосрочный): Agent execution plane**
Уже заложен management command `run_agent_execution_plane`.  
Паттерн: `servers/worker_state.py` (lease/heartbeat) — используется для распределённой координации воркеров.

---

### 6.4 Избежать новых god files

Правила процесса (не только архитектуры):

1. **PR rule:** файл > 300 строк — обязательный комментарий "почему нельзя разбить"
2. **Feature flag:** новая фича начинается с нового `services/` файла, не с расширения существующего
3. **Ownership:** каждый bounded context имеет owner-разработчика, ответственного за его размер
4. **Lint rule:** добавить в `pyproject.toml`:
```toml
[tool.ruff.lint]
select = [..., "C901"]  # complexity check
```

---

## 7. Technical Debt — Приоритеты

### P0 — Критично (блокирует безопасное развитие)

**P0-01: Циклическая зависимость servers ↔ studio**
- Файлы: `servers/agent_engine.py:45-46`, `servers/signals.py:142-144`, `studio/pipeline_executor.py:55`
- Почему плохо: невозможно тестировать `servers` без `studio`; любое изменение в `studio.skill_policy` может сломать agent execution
- Если не исправить: при рефакторинге любого из модулей будут неожиданные регрессии

**P0-02: DjangoServerMemoryStore в app/agent_kernel**
- Файл: `app/agent_kernel/memory/store.py:12-14` — Django imports в "чистом" ядре
- Почему плохо: нельзя запустить/тестировать agent_kernel без Django; нарушает принцип изолированного ядра
- Если не исправить: тесты agent_kernel всегда будут требовать полного Django setup

**P0-03: God file consumers.py**
- Файл: `servers/consumers.py` (146 KB) — SSH terminal + AI chat + SFTP + commands
- Почему плохо: любое изменение в терминале рискует сломать AI-чат; невозможно понять scope изменения
- Если не исправить: каждый баг в терминале будет занимать в 3x больше времени на диагностику

**P0-04: Celery в requirements-mini.txt отсутствует, но используется**
- Файл: `servers/tasks.py` — `@shared_task`; `requirements-mini.txt` — нет celery
- Почему плохо: `ingest_memory_event_task.delay()` упадёт silently или будет выполняться синхронно без явного документирования поведения
- Если не исправить: memory ingestion непредсказуемо — то работает, то нет

---

### P1 — Важно (замедляет разработку)

**P1-01: God files views.py**
- Файлы: `core_ui/views.py` (171 KB), `servers/views.py` (159 KB), `studio/views.py` (96 KB)
- Почему плохо: merge conflicts при командной работе, невозможно grep-нуть конкретную функцию быстро
- Если не исправить: скорость разработки будет падать с ростом команды

**P1-02: api.ts — монолитный API-клиент**
- Файл: `ai-server-terminal-main/src/lib/api.ts` (133 KB)
- Почему плохо: любой разработчик фронтенда правит один файл → постоянные конфликты
- Если не исправить: frontend-разработка станет узким местом

**P1-03: i18n как код**
- Файл: `ai-server-terminal-main/src/lib/i18n.tsx` (52 KB)
- Почему плохо: нельзя добавить язык без деплоя; нельзя отдать переводы переводчику
- Если не исправить: локализация останется недоступной для внешних контрибьюторов

**P1-04: memory/store.py — 181 KB**
- Файл: `app/agent_kernel/memory/store.py`
- Почему плохо: ingestion + dreams + repair + compaction в одном месте — изменение любой части рискует сломать всё
- Если не исправить: memory system станет самым хрупким местом платформы

**P1-05: Отсутствие API-версионирования**
- Файлы: `servers/urls.py`, `studio/urls.py` — нет `/v1/` prefix
- Почему плохо: при изменении контракта нет пути обратной совместимости
- Если не исправить: каждое изменение API = синхронный деплой frontend + backend

**P1-06: settings.py монолит**
- Файл: `web_ui/settings.py` (749 строк)
- Почему плохо: нельзя использовать разные конфиги для test/dev/prod без env-переменных; сложно найти конкретную настройку
- Если не исправить: конфигурационные ошибки будут регулярными

---

### P2 — Можно позже (tech debt без острой боли)

**P2-01: passwords/ — зомби-модуль**
- Файл: `passwords/` — не подключён, не удалён
- Почему плохо: вводит в заблуждение новых разработчиков

**P2-02: Мусор в корне репозитория**
- Файлы: `original_page.tsx`, `diff.txt`, `key_mcp.py.new`, `patch_*.py`, `fix*.py`, `StudioSkillsPage.tsx.bak`
- Почему плохо: профессиональный вид, confusion при навигации

**P2-03: Двойной frontend в корне**
- Файлы: корневые `vite.config.ts`, `package.json`, `tailwind.config.ts` — не используются или дублируют `ai-server-terminal-main/`

**P2-04: templates_data.py — 42 KB embedded data**
- Файл: `studio/templates_data.py` — шаблоны как Python-код, не Django fixtures
- Почему плохо: обновление шаблона = деплой кода

**P2-05: ChatSession/ChatMessage — устаревшие модели**
- Файл: `core_ui/models.py` — модели не используются текущим UI
- Почему плохо: миграции, DB storage без пользы

---

## 8. Основа для миграции

### Принципы

1. **Strangler Fig:** новый код пишется по контракту, старый заменяется постепенно
2. **Never Break Green:** тесты должны проходить после каждого шага
3. **Atomic Steps:** каждый шаг — это один PR, который можно ревертировать независимо

### Фазы и порядок зависимостей

```
ФАЗА 0 (независимо, параллельно)
├── Очистка мусора в корне (P2-02, P2-03)
├── Удаление passwords/ (P2-01)
├── Разбить settings.py на base/development/production (P1-06)
└── Добавить celery в requirements-mini.txt или задокументировать sync-fallback (P0-04)

ФАЗА 1 (требует ФАЗА 0)
├── Перенести DjangoServerMemoryStore → servers/adapters/memory_store.py (P0-02)
│   Шаги:
│   1. Создать servers/adapters/memory_store.py с копией класса
│   2. Изменить импорты в servers/agent_engine.py, studio/pipeline_executor.py
│   3. Оставить re-export в app/agent_kernel/memory/store.py на 1 релиз
│   4. Убрать re-export
│   Тесты: pytest tests/test_ops_agent_kernel.py после каждого шага
│
├── Убрать циклическую зависимость servers ↔ studio (P0-01)
│   Шаги:
│   1. Создать Django Signal alert_opened в servers/signals.py
│   2. Подписать studio в studio/apps.py.ready()
│   3. Удалить прямой import из servers/signals.py
│   4. Создать SkillProvider Protocol в app/agent_kernel/domain/specs.py
│   5. Передавать skill_provider через DI в AgentEngine
│   6. Удалить from studio.* в servers/agent_engine.py
│   Тесты: pytest tests/test_servers_api_smoke.py, test_studio_api_smoke.py
│
└── Разбить api.ts (P1-02)
    Шаги:
    1. Создать ai-server-terminal-main/src/api/ папку
    2. Перенести функции по доменам (не удалять из api.ts пока)
    3. Заменить import в pages/ по одному
    4. Удалить api.ts
    Тесты: npm run test + playwright e2e smoke

ФАЗА 2 (требует ФАЗА 1)
├── Разбить consumers.py (P0-03)
│   servers/consumers/ пакет: ssh_terminal.py, rdp_terminal.py, agent_live.py
│   Тесты: playwright terminal e2e
│
├── Разбить views.py (P1-01)
│   servers/views/, core_ui/views/, studio/views/ — пакеты с re-exports
│   Тесты: pytest tests/test_servers_api_smoke.py, test_core_ui_api_smoke.py
│
└── Разбить memory/store.py (P1-04)
    memory/ingestion.py, memory/dreams.py — выделить операции
    store.py становится оркестратором
    Тесты: pytest tests/test_ops_agent_kernel.py, test_memory_repair.py

ФАЗА 3 (требует ФАЗА 2)
├── Pipeline node registry (studio/executor/nodes/)
│   Ввести BaseNode, реестр, перенести узлы поодиночке
│   pipeline_executor.py → engine.py (только граф + диспатч)
│   Тесты: pytest tests/test_studio_node_executors.py (добавить per-node тесты)
│
├── Сервисный слой (servers/services/, studio/services/)
│   Любая новая функциональность → только через services/
│   Постепенный перенос существующей логики
│
└── i18n JSON (P1-03)
    Установить react-i18next, перенести i18n.tsx → locales/*.json
```

### Высокий риск поломки

| Изменение | Риск | Mitigation |
|---|---|---|
| Перенос `DjangoServerMemoryStore` | High: используется в 5+ местах | Re-export на переходный период |
| Разбить `consumers.py` | High: WebSocket state management | Тестировать в staging с реальным SSH |
| Убрать прямой import servers→studio | Medium: скрытые зависимости | grep всего codebase перед PR |
| Разбить `pipeline_executor.py` | High: 15+ типов узлов, edge cases | Перенос по одному узлу за PR |
| i18n миграция | Medium: 1000+ строк переводов | Двойная система на переходный период |

### Нельзя делать независимо (строгий порядок)

```
1. DjangoServerMemoryStore → adapters/ ДОЛЖЕН быть ДО разбивки agent_kernel/memory/store.py
2. Django Signal для alert→pipeline ДОЛЖЕН быть ДО разбивки consumers.py
3. SkillProvider Protocol ДОЛЖЕН быть ДО разбивки views.py (servers)
4. settings split ДОЛЖЕН быть ДО любых изменений в prod конфигурации
```

---

## Приложение: Dependency Matrix

Разрешённые зависимости между модулями (`✅` = допустимо, `❌` = запрещено, `⚠️` = только через интерфейс):

| From ↓ \ To → | `web_ui` | `core_ui` | `servers` | `studio` | `agent_kernel` | `app/core` | `app/tools` |
|---|---|---|---|---|---|---|---|
| `web_ui` | — | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ |
| `core_ui` | ❌ | — | ❌ | ❌ | ❌ | ❌ | ❌ |
| `servers` | ❌ | ✅ | — | ⚠️ signal | ✅ | ✅ | ✅ |
| `studio` | ❌ | ✅ | ⚠️ API only | — | ✅ | ✅ | ✅ |
| `agent_kernel` | ❌ | ❌ | ❌ | ❌ | — | ✅ | ✅ |
| `app/core` | ❌ | ❌ | ❌ | ❌ | ❌ | — | ❌ |
| `app/tools` | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | — |

---

*Документ обязателен. Отступление от него требует явного RFC (Request for Change) с обоснованием и обновлением этого документа.*
