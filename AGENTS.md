# mini_prod Unified Working Context

Репозиторий: `C:\Users\German.Keller\Desktop\db\mini\WEU-AI\mini_prod`
WSL-путь: `/mnt/c/Users/German.Keller/Desktop/db/mini/WEU-AI/mini_prod`

Этот файл - единый Markdown-источник правды для проекта. Он заменяет удаленные `README_MINI.md`, `CLAUDE.md`, `docs/FRONTEND_SPEC_LAVAB.md` и `ai-server-terminal-main/README.md`.

## Что это за проект

- Это локально-обрезанная сборка WEU AI Platform внутри папки `mini_prod`.
- По факту проект уже не "servers only": сейчас активны `core_ui`, `servers`, `studio`, плюс общие модули в `app/`.
- Основной UI - внешний React/Vite SPA в `ai-server-terminal-main/`, а Django в основном отдает API, WebSocket и редиректы в SPA.
- Старые описания про `views_mini.py` и "только servers" устарели.

## Правила работы с репозиторием

- Новую логику класть в ближайшее существующее Django-приложение; не создавать новые top-level пакеты без явной необходимости.
- Python: 3.10+, 4 пробела, двойные кавычки.

Именование:
- `snake_case` для модулей, файлов, функций.
- `PascalCase` для классов.
- `UPPER_SNAKE_CASE` для констант и env-переменных.

Инструменты качества:
- `ruff check .`
- `ruff format .`
- Тесты: `pytest`, `pytest-django`, `pytest-asyncio`.
- Тестовые файлы: `test_*.py` или `*_test.py`.
- Не коммитить секреты из `.env`.
- Для опасных серверных действий сохранять и расширять проверки в `app/tools/safety.py`.

## Быстрый запуск

Backend:

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements-mini.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Frontend:

```bash
cd ai-server-terminal-main
npm install
npm run dev
```

Проверки:

```bash
pytest
ruff check .
ruff format .
```

## Важная оговорка по портам

- `manage.py` автоматически подставляет порт `9000`, если запустить `python manage.py runserver` без явного порта.
- `FRONTEND_APP_URL` по умолчанию: `http://127.0.0.1:8080`.
- Vite proxy в `ai-server-terminal-main/vite.config.ts` тоже по умолчанию смотрит на `http://127.0.0.1:9000`.
- Старые упоминания `8000` в удаленных markdown-файлах были частично устаревшими.

## Актуальная карта верхнего уровня

- `manage.py` - основной вход в Django CLI; подставляет порт `9000`.
- `web_ui/` - Django settings, root URLs, ASGI/WSGI, сборка WebSocket routing.
- `core_ui/` - auth/session API, redirects в SPA, settings/access/admin endpoints, middleware.
- `servers/` - серверы, группы, SSH/RDP терминал, мониторинг, знания по серверам, server agents.
- `studio/` - pipelines, runs, MCP, triggers, notifications, live updates по pipeline runs.
- `app/` - общие LLM, safety, SSH/server tools.
- `ai-server-terminal-main/` - React/Vite SPA.
- `passwords/` - остался как кодовый модуль, но не подключен в `INSTALLED_APPS`.
- `docker/` - Dockerfile и сопутствующие runtime-артефакты.
- `agent_projects/` - runtime-папка для агентных проектов.
- `media/` - загрузки и медиа.
- `docs/` - после чистки пустая папка; отдельного Markdown там больше нет.
- `venv/` - локальное окружение, не использовать как источник контекста.

Шум и генерируемые артефакты, которые обычно не стоит трогать:

- `venv/`
- `ai-server-terminal-main/node_modules/`
- `db.sqlite3`, `db.sqlite3-shm`, `db.sqlite3-wal`
- `media/`
- `agent_projects/`

## Backend: реальная архитектура

### `web_ui/`

`web_ui/settings.py`:

- активные Django apps: `daphne`, `channels`, `core_ui`, `servers`, `studio`.
- база выбирается автоматически: PostgreSQL при наличии `POSTGRES_HOST` или `POSTGRES_DB`, иначе SQLite.
- channels layer: Redis при наличии `CHANNEL_REDIS_URL`, иначе `InMemoryChannelLayer`.
- `FRONTEND_APP_URL` по умолчанию `http://127.0.0.1:8080`.
- включает Domain SSO и email/notification config.

`web_ui/urls.py`:

- `/admin/`
- `'' -> core_ui.urls`
- `'api/desktop/v1/' -> core_ui.desktop_api.urls`
- `'servers/' -> servers.urls`
- `'api/studio/' -> studio.urls`
- `web_ui/asgi.py` поднимает HTTP + WebSocket через `ProtocolTypeRouter`.
- `web_ui/routing.py` агрегирует WS-маршруты `servers` и `studio`.

### `core_ui/`

Назначение:

- логин/логаут и auth session API;
- редиректы из Django URL в React SPA;
- settings, access, admin dashboard API;
- middleware и доменная авторизация.

Ключевые файлы:

- `core_ui/urls.py` - основные frontend redirects и API auth/settings/access.
- `core_ui/views.py` - фактическая реализация всех этих endpoints.
- `core_ui/middleware.py` - `CsrfTrustNgrokMiddleware`, `AdminRussianMiddleware`, `MobileDetectionMiddleware`.
- `core_ui/domain_auth.py` - `DomainAutoLoginMiddleware`.
- `core_ui/templates/` - остались базовые Django templates и admin override.

Важно:

- В `core_ui/views.py` все еще много legacy/full-platform кода и API, часть которого не подключена в `core_ui/urls.py`.
- Документы, ссылавшиеся на `core_ui/views_mini.py`, были устаревшими; файла сейчас нет.

### `servers/`

Назначение:

- CRUD серверов и групп;
- SSH/RDP terminal;
- group subscriptions и shares;
- server knowledge/context;
- мониторинг и alerts;
- server agents и live runs.

Ключевые файлы:

- `servers/models.py`
- `ServerGroup`
- `ServerGroupTag`
- `ServerGroupMember`
- `ServerGroupSubscription`
- `ServerGroupPermission`
- `Server`
- `ServerShare`
- `ServerConnection`
- `ServerCommandHistory`
- `GlobalServerRules`
- `ServerKnowledge`
- `ServerHealthCheck`
- `ServerAlert`
- `ServerGroupKnowledge`
- `ServerAgent`
- `AgentRun`
- `servers/views.py` - HTTP API и редиректы/страницы.
- `servers/consumers.py` - `SSHTerminalConsumer`.
- `servers/rdp_consumer.py` - `RDPTerminalConsumer`.
- `servers/agent_consumer.py` - `AgentLiveConsumer`.
- `servers/routing.py` - WebSocket routes.
- `servers/templates/servers/` - legacy/SSR templates для terminal/list/RDP.

### `studio/`

Назначение:

- pipeline editor/runtime;
- agent configs;
- MCP pool и tool discovery;
- cron/webhook triggers;
- notification settings;
- live updates по pipeline run.

Ключевые файлы:

- `studio/models.py`
- `MCPServerPool`
- `AgentConfig`
- `Pipeline`
- `PipelineTrigger`
- `PipelineRun`
- `PipelineTemplate`
- `studio/views.py` - REST API для pipelines, runs, MCP, triggers, templates, notifications.
- `studio/pipeline_executor.py` - `PipelineExecutor`.
- `studio/mcp_client.py` - stdio/http MCP клиенты.
- `studio/routing.py` - WebSocket live updates по pipeline runs.
- `studio/management/commands/`
- `load_pipeline_templates.py`
- `run_scheduled_pipelines.py`
- `setup_keycloak_ops_pipelines.py`
- `setup_keycloak_provisioning_pipeline.py`
- `setup_mcp_showcase_pipeline.py`
- `setup_server_update_pipeline.py`

### `app/`

Общие сервисы, которые используют backend-модули:

- `app/core/llm.py` - провайдеры LLM и логирование использования.
- `app/tools/safety.py` - `is_dangerous_command`.
- `app/tools/ssh_tools.py` - SSH connection/execute/disconnect tools.
- `app/tools/server_tools.py` - list/execute tools поверх серверов.

### `passwords/`

- Папка есть в проекте.
- В `INSTALLED_APPS` не подключена.
- В старых текстах упоминалось, что она оставлена как кодовая зависимость; это соответствует текущей структуре.

## Frontend: `ai-server-terminal-main/`

Стек:

- React 18
- TypeScript
- Vite
- React Router
- TanStack Query
- xterm.js
- Radix UI
- Tailwind
- Vitest

Ключевые пути:

- `ai-server-terminal-main/src/App.tsx` - основной роутер SPA.
- `ai-server-terminal-main/src/lib/api.ts` - frontend API и WebSocket helper-слой.
- `ai-server-terminal-main/src/pages/` - страницы.
- `ai-server-terminal-main/src/components/terminal/` - терминальные компоненты.
- `ai-server-terminal-main/src/components/pipeline/` - pipeline UI.
- `ai-server-terminal-main/vite.config.ts` - proxy на Django и WS.

Актуальные frontend routes:

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

## HTTP маршруты backend

### Root / `core_ui.urls`

- `/login/` - редирект на frontend login flow.
- `/logout/`
- `/`
- `/dashboard/`
- `/settings/`
- `/settings/access/`
- `/settings/users/`
- `/settings/groups/`
- `/settings/permissions/`
- `/api/health/`
- `/api/admin/dashboard/`
- `/api/admin/users/activity/`
- `/api/admin/users/sessions/`
- `/api/auth/session/`
- `/api/auth/ws-token/`
- `/api/auth/login/`
- `/api/auth/logout/`
- `/api/settings/`
- `/api/settings/check/`
- `/api/models/`
- `/api/models/refresh/`
- `/api/settings/activity/`
- `/api/access/users/`
- `/api/access/users/<user_id>/`
- `/api/access/users/<user_id>/password/`
- `/api/access/users/<user_id>/profile/`
- `/api/access/groups/`
- `/api/access/groups/<group_id>/`
- `/api/access/groups/<group_id>/members/`
- `/api/access/permissions/`
- `/api/access/permissions/<perm_id>/`

### `servers.urls`

UI/pages:

- `/servers/`
- `/servers/api/frontend/bootstrap/`
- `/servers/hub/`
- `/servers/<server_id>/terminal/`
- `/servers/<server_id>/terminal/minimal/`

Server CRUD / shares / knowledge / context:

- `/servers/api/create/`
- `/servers/api/<server_id>/update/`
- `/servers/api/<server_id>/test/`
- `/servers/api/<server_id>/execute/`
- `/servers/api/<server_id>/delete/`
- `/servers/api/<server_id>/get/`
- `/servers/api/<server_id>/reveal-password/`
- `/servers/api/<server_id>/shares/`
- `/servers/api/<server_id>/share/`
- `/servers/api/<server_id>/shares/<share_id>/revoke/`
- `/servers/api/<server_id>/knowledge/`
- `/servers/api/<server_id>/knowledge/create/`
- `/servers/api/<server_id>/knowledge/<knowledge_id>/update/`
- `/servers/api/<server_id>/knowledge/<knowledge_id>/delete/`
- `/servers/api/global-context/`
- `/servers/api/global-context/save/`
- `/servers/api/groups/<group_id>/context/`
- `/servers/api/groups/<group_id>/context/save/`

Groups:

- `/servers/api/groups/create/`
- `/servers/api/groups/<group_id>/update/`
- `/servers/api/groups/<group_id>/delete/`
- `/servers/api/groups/<group_id>/add-member/`
- `/servers/api/groups/<group_id>/remove-member/`
- `/servers/api/groups/<group_id>/subscribe/`
- `/servers/api/bulk-update/`

Master password:

- `/servers/api/master-password/set/`
- `/servers/api/master-password/check/`
- `/servers/api/master-password/clear/`

Monitoring:

- `/servers/api/monitoring/dashboard/`
- `/servers/api/<server_id>/health/`
- `/servers/api/<server_id>/health/check/`
- `/servers/api/alerts/`
- `/servers/api/alerts/<alert_id>/resolve/`
- `/servers/api/monitoring/config/`
- `/servers/api/<server_id>/ai-analyze/`

Server agents:

- `/servers/api/agents/`
- `/servers/api/agents/templates/`
- `/servers/api/agents/create/`
- `/servers/api/agents/<agent_id>/update/`
- `/servers/api/agents/<agent_id>/delete/`
- `/servers/api/agents/<agent_id>/run/`
- `/servers/api/agents/<agent_id>/stop/`
- `/servers/api/agents/<agent_id>/runs/`
- `/servers/api/agents/runs/<run_id>/`
- `/servers/api/agents/runs/<run_id>/log/`
- `/servers/api/agents/runs/<run_id>/reply/`
- `/servers/api/agents/dashboard/`
- `/servers/api/agents/runs/<run_id>/approve-plan/`
- `/servers/api/agents/runs/<run_id>/tasks/<task_id>/update/`
- `/servers/api/agents/runs/<run_id>/tasks/<task_id>/ai-refine/`

### `studio.urls` под префиксом `/api/studio/`

- `/api/studio/pipelines/`
- `/api/studio/pipelines/assistant/`
- `/api/studio/pipelines/<pipeline_id>/`
- `/api/studio/pipelines/<pipeline_id>/run/`
- `/api/studio/pipelines/<pipeline_id>/clone/`
- `/api/studio/pipelines/<pipeline_id>/runs/`
- `/api/studio/runs/`
- `/api/studio/runs/<run_id>/`
- `/api/studio/runs/<run_id>/stop/`
- `/api/studio/runs/<run_id>/approve/<node_id>/`
- `/api/studio/agents/`
- `/api/studio/agents/<agent_id>/`
- `/api/studio/skills/`
- `/api/studio/skills/templates/`
- `/api/studio/skills/scaffold/`
- `/api/studio/skills/validate/`
- `/api/studio/skills/<slug>/workspace/`
- `/api/studio/skills/<slug>/workspace/file/`
- `/api/studio/skills/<slug>/`
- `/api/studio/mcp/`
- `/api/studio/mcp/templates/`
- `/api/studio/mcp/<mcp_id>/`
- `/api/studio/mcp/<mcp_id>/test/`
- `/api/studio/mcp/<mcp_id>/tools/`
- `/api/studio/triggers/`
- `/api/studio/triggers/<trigger_id>/`
- `/api/studio/triggers/<token>/receive/`
- `/api/studio/templates/`
- `/api/studio/templates/<slug>/use/`
- `/api/studio/servers/`
- `/api/studio/notifications/`
- `/api/studio/notifications/test-telegram/`
- `/api/studio/notifications/test-email/`

## WebSocket маршруты

- `/ws/servers/<server_id>/terminal/` -> `servers.consumers.SSHTerminalConsumer`
- `/ws/servers/<server_id>/rdp/` -> `servers.rdp_consumer.RDPTerminalConsumer`
- `/ws/agents/<run_id>/live/` -> `servers.agent_consumer.AgentLiveConsumer`
- `/ws/studio/pipeline-runs/<run_id>/live/` -> `studio.consumers.PipelineRunConsumer`

## Переменные окружения и конфиг

Минимально важные:

- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `GEMINI_API_KEY`
- `CHANNEL_REDIS_URL`
- `FRONTEND_APP_URL`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `SITE_URL`
- `EMAIL_HOST`
- `EMAIL_PORT`
- `EMAIL_USE_TLS`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `DEFAULT_FROM_EMAIL`
- `PIPELINE_NOTIFY_EMAIL`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `DOMAIN_AUTH_ENABLED`
- `DOMAIN_AUTH_HEADER`
- `DOMAIN_AUTH_AUTO_CREATE`
- `DOMAIN_AUTH_LOWERCASE_USERNAMES`
- `DOMAIN_AUTH_DEFAULT_PROFILE`
- `DJANGO_PORT`
- `CLI_RUNTIME_TIMEOUT_SECONDS`
- `CLI_FIRST_OUTPUT_TIMEOUT_SECONDS`
- `ANALYZE_TASK_BEFORE_RUN`
- `CURSOR_CLI_HTTP_1`
- `CURSOR_CLI_EXTRA_ENV`
- `KEYCLOAK_*`

Файлы конфигурации:

- `.env` - локальные реальные значения, не переносить секреты в git.
- `.env.example` - безопасный шаблон.
- `requirements-mini.txt` - минимальные runtime dependencies.
- `requirements.txt`, `requirements-full.txt` - более широкие наборы зависимостей.
- `pyproject.toml` - Ruff, pytest, coverage.

## Docker и служебные утилиты

`docker-compose.yml`:

- PostgreSQL
- `mcp-demo` на `8765`
- `mcp-keycloak` на `8766`
- `docker-compose.postgres-mcp.yml` - альтернативный локальный стек Studio: PostgreSQL + MCP сервисы.
- `docker/keycloak-mcp.Dockerfile` - сборка Keycloak MCP-контейнера.
- `key_mcp.py` - standalone MCP server для Keycloak.
- `keycloak_profiles.json` - профили окружений Keycloak.
- `create_mega_pipeline.py` - одноразовый Python-скрипт создания большого DevOps autopilot pipeline.
- `create_pipeline.sql` - SQL-вставка похожего pipeline напрямую в БД.

Management commands:

- `servers/management/commands/run_monitor.py`
- `servers/management/commands/seed_servers_for_frontend.py`
- `studio/management/commands/load_pipeline_templates.py`
- `studio/management/commands/run_scheduled_pipelines.py`
- `studio/management/commands/setup_keycloak_ops_pipelines.py`
- `studio/management/commands/setup_keycloak_provisioning_pipeline.py`
- `studio/management/commands/setup_mcp_showcase_pipeline.py`
- `studio/management/commands/setup_server_update_pipeline.py`

## Тесты и качество

- `pytest` использует `DJANGO_SETTINGS_MODULE = web_ui.settings`.
- В `pyproject.toml` до сих пор есть ссылки на `agent_hub` и `tasks` в `testpaths` и coverage source.
- Эти директории в текущем `mini_prod` отсутствуют, поэтому часть конфигурации историческая.
- В `pyproject.toml` `known-first-party` Ruff тоже содержит исторические пакеты.

## Состояние UI и ожидания по фронтенду

Из старого frontend spec оставлено только то, что реально полезно для работы:

- продукт строится вокруг серверов, SSH/RDP терминала, AI-панели, мониторинга, pipelines и studio/MCP tooling;
- backend API и WebSocket URLs менять осторожно, frontend на них уже завязан;
- терминальная часть использует `xterm.js`;
- нужен рабочий mobile layout, sidebar, notifications, auth flow и SPA routing;
- RDP, SSH terminal, settings, agents и studio - активные пользовательские сценарии.

## Что помнить перед изменениями

- Главный источник правды по поведению - текущий код, а не старые README.
- Если есть конфликт между этим файлом и кодом, верить коду и обновлять этот файл.
При работе почти всегда проверять:
- `web_ui/settings.py`
- `web_ui/urls.py`
- `core_ui/urls.py`
- `servers/urls.py`
- `studio/urls.py`
- `ai-server-terminal-main/src/App.tsx`
- `ai-server-terminal-main/src/lib/api.ts`

## Итог после чистки Markdown

После консолидации в папке `mini_prod` должен оставаться один рабочий Markdown-файл: этот `AGENTS.md`.
