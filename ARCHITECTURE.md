# WEU AI Platform - Карта Архитектуры Проекта

Этот документ содержит полную, актуальную техническую карту репозитория `weu-ai-platform`, предназначенную для разработчиков и ИИ-агентов. Описание собрано на основе реального состояния кода, файлов настроек и зависимостей.

---

## 1. Общий обзор системы (Общая архитектура)
Проект представляет собой платформу для автоматизации DevOps/IT задач с использованием ИИ.
Состоит из трех основных частей:
1. **Backend**: Python 3.10+, Django 5.2.10, Django Channels, Celery.
2. **Frontend**: React 18, Vite, TypeScript, Tailwind CSS, shadcn/ui.
3. **Desktop**: WinUI 3 (.NET 8) desktop-клиент.

Хранилище данных и кэш: PostgreSQL, Redis. Управление через Docker Compose.

---

## 2. Структура Backend (Django)

Проект разбит на несколько изолированных Bounded Contexts (приложений Django), связи между которыми строго контролируются контрактами (`.importlinter`).

### 2.1. Основные приложения (Apps)
- **`web_ui/`**: Корневой проект Django. Содержит `settings/` (base, development, production, test), `urls.py` (корневой роутинг), `routing.py` (корневой WebSocket роутинг) и настройки Celery.
- **`app/`**: Ядро бизнес-логики агента (`agent_kernel`), хуки, песочницы для запуска, регистраторы навыков, провайдеры LLM (`core/llm.py`) и инструменты безопасного исполнения команд (`tools/safety.py`). **Правило:** `agent_kernel` не должен импортировать Django ORM.
- **`core_ui/`**: API для аутентификации, доступа, настроек, UI, логирования (UserActivityLog, LLMUsageLog) и desktop-клиента (`desktop_api`). Не импортирует `servers` или `studio`.
- **`servers/`**: Управление серверами, SSH/RDP терминалы, файловый менеджер, мониторинг (ServerHealthCheck, ServerAlert), фоновые агенты (ServerAgent, AgentRun), слоистая память (ServerMemorySnapshot) и история команд (CommandSnapshot). Допустим импорт из `app.tools`.
- **`studio/`**: Платформа для визуальных пайплайнов (React Flow), триггеров (PipelineTrigger), интеграции с MCP серверами (MCPServerPool) и настройки навыков (StudioSkillAccess).

### 2.2. Основные Модели Данных
*   **`core_ui`**:
    *   `UserAppPermission`, `GroupAppPermission`: Контроль доступа к функциям.
    *   `UserActivityLog`, `LLMUsageLog`: Аудит.
    *   `TerminalPreference`: Настройки внешнего вида терминала.
    *   `DesktopRefreshToken`: Авторизация WinUI клиента.
*   **`servers`**:
    *   `Server`: Основная модель (SSH/RDP).
    *   `ServerConnection`: Активные соединения.
    *   `ServerCommandHistory`, `CommandSnapshot`, `TerminalAiChatMessage`: История взаимодействия и ИИ-чата.
    *   `ServerMemoryEvent` (L0), `ServerMemoryEpisode` (L1), `ServerMemorySnapshot` (L2): Многоуровневая память об инцидентах и состоянии серверов.
    *   `ServerAgent`, `AgentRun`, `AgentRunEvent`: Запуск и логи ИИ-агентов.
*   **`studio`**:
    *   `Pipeline`, `PipelineRun`, `PipelineTemplate`: Визуальные процессы (Nodes/Edges хранятся как JSON).
    *   `MCPServerPool`: Настройки Model Context Protocol.
    *   `AgentConfig`: Настройки агентов-нод.

### 2.3. Маршруты (API & Routing)
- Основной API префикс: `/api/`
- Настройки и аутентификация: `/api/auth/`, `/api/settings/`, `/api/access/` (`core_ui.urls`)
- Серверы и метрики: `/servers/api/`, `/api/<int:server_id>/ui/` (`servers.urls`)
- Студия пайплайнов и MCP: `/api/studio/pipelines/`, `/api/studio/mcp/` (`studio.urls`)
- **WebSockets** (ASGI, `routing.py` -> `CHANNEL_LAYERS` Redis):
    - `ws/servers/...` (в `servers.routing`, SSH/RDP терминалы)
    - `ws/studio/...` (в `studio.routing`, обновления UI пайплайнов)

### 2.4. Фоновые процессы и Celery
Система использует **Celery** (через Redis `redis://localhost:6379/0`) для отложенных задач (`CELERY_TASK_TIME_LIMIT = 30 * 60`).
Также есть долгоживущие процессы (management commands), запрашивающие лезы (lease) в `BackgroundWorkerState`:
- `run_monitor`: Мониторинг серверов (CPU/RAM).
- `run_watchers`: Запуск watcher-ов.
- `run_scheduled_agents` / `run_agent_execution_plane`: Диспетчеризация и запуск агентов.
- `run_memory_dreams` / `repair_server_memory`: L0 -> L1 -> L2 консолидация памяти.
- `run_scheduled_pipelines` / `run_ops_supervisor`: Планировщик Studio.

---

## 3. Структура Frontend (Vite/React)

Расположен в `ai-server-terminal-main/`. Настроен в `package.json` и `vite.config.ts`.

### 3.1. Технологический стек
- Фреймворк: React 18, сборщик Vite.
- Маршрутизация: `react-router-dom` (роуты защищены `AuthGate` и `FeatureGate`).
- Состояние: `@tanstack/react-query` (кеширование запросов).
- UI/Стили: Tailwind CSS, `radix-ui`, `framer-motion`, `lucide-react`, Shadcn UI (`src/components/ui/`).
- Терминал: `@xterm/xterm` и аддоны (fit, search, web-links).
- Редакторы кода: `@codemirror/*` (для логов и кода), `@xyflow/react` (Node-панели для Studio).

### 3.2. Архитектура папок (`src/`)
- `api/`: Функции `fetch`/Axios, маппинг на Backend API.
- `components/`:
    - `editor/`: Редактор файлов.
    - `pipeline/`: Панели графов и нод (`AgentNode`, `SSHCommandNode` и т.д.).
    - `settings/`: Страницы настроек (AI, SSO, Audit).
    - `studio/`: Компоненты раздела Studio.
    - `terminal/`: Компоненты XTerm терминала и панели AI (`AiPanel.tsx`).
    - `ui/`: Базовые UI-компоненты Shadcn.
- `pages/`: Экраны SPA (Login, Index, Servers, TerminalPage, StudioPage, Settings).

---

## 4. Ограничения и Правила Разработки (Важно!)

1. **Изоляция Контекстов (`.importlinter`)**:
   - `agent_kernel` **строго запрещено** импортировать модели `django.db.models`. Обоснование: ядро агента не должно зависеть от ORM.
   - Общие сервисы `app.core` и `app.tools` не могут импортировать `servers`, `studio`, или `core_ui`. (Исключение: `server_tools.py` и `ssh_tools.py` пока имеют доступ к моделям серверов).
   - `core_ui` не импортирует `servers` или `studio`.
   - `servers` не импортирует `studio`.
2. **Безопасность выполнения (Safety Guardrails)**:
   - Анализ команд происходит в `app/tools/safety.py`. Перед изменением файлов ИИ-агентом (`> / tee / sed -i`), создается `CommandSnapshot` с сохранением предыдущего состояния для возможности быстрого отката (rollback).
3. **Лимиты Runtime**:
   - Настраиваются в `app/runtime_limits.py` (и через переменные окружения). Например: одновременные соединения, таймауты LLM и MCP, лимиты агентов.
4. **Утечки и N+1**:
   - (Из `PROJECT_AUDIT.md`): При запросах списков (например, Users/Servers) важно использовать `prefetch_related` и избегать запросов внутри циклов.

---

## 5. Настройки, Запуск и Развертывание

### 5.1. `.env` и Базы Данных
Приложение переключается на PostgreSQL, если задана переменная `POSTGRES_HOST` или `POSTGRES_DB` (см. `web_ui/settings/base.py`). Если нет — использует SQLite (только для dev).

### 5.2. Docker Compose
- `docker-compose.yml`: Запускает `postgres` (16-alpine), `redis` (7-alpine), `backend` (Daphne), `frontend` (Vite preview), `nginx`, `mcp-demo` и `mcp-keycloak`.
- Фоновые воркеры запускаются внутри `backend` через `docker/render-backend-start.sh` (в котором также вызывается `migrate` и `collectstatic`).

### 5.3. Тесты и Качество Кода
- **Backend**: `pytest` (настроен в `pyproject.toml`), `ruff check .` для статического анализа, `lint-imports` для проверки архитектурных границ.
- **Frontend**: `vitest` для юнит тестов, `playwright test` для E2E и smoke тестов. `eslint` и `tsc` для проверки типов.

### 5.4. Десктоп и Артефакты
- Клиент для Windows компилируется из `desktop/MiniProd.Desktop.sln` (.NET 8 / WinUI 3). Взаимодействует с Backend через `/api/desktop/v1/`.

---
*Документ создан в рамках автономного анализа проекта.*
