# Project Review Action Plan

Дата среза: 2026-05-19

Назначение: рабочий backlog проблем после обзорного аудита проекта. Файл сделан так, чтобы отдельные пункты можно было выдавать агентам как самостоятельные read-only или implementation задачи.

## Кратко о продукте

Проект сейчас является локальной ops-платформой, а не просто терминалом:

- Django/Channels backend: auth, access, settings, desktop API, WebSocket.
- Servers: CRUD серверов/групп, SSH terminal, RDP, SFTP/file manager, Linux UI, monitoring, alerts.
- Agents: server agents, live runs, terminal AI.
- Studio: pipeline editor/runtime, MCP servers, skills, triggers, notifications.
- AI memory: долговременная layered memory по серверам, которая попадает в prompt агентов.
- Frontend: React/Vite SPA в `ai-server-terminal-main/`.

## Проверки, которые были выполнены

- `manage.py check` прошел без ошибок.
- `npm run build` в `ai-server-terminal-main` прошел.
- `npm run lint -- --max-warnings=0` падает:
  - 12 errors в `ai-server-terminal-main/e2e/servers.spec.ts`;
  - 26 warnings по hooks/Fast Refresh.
- Frontend build дает warning по крупным чанкам, включая `vendor` около 1.1 MB minified.

## P0: Security / Safety

### 1. Shared server permissions слишком широкие

Проблема: shared server access выглядит как доступ ко всем операциям, а не только view/context. Общий queryset доступных серверов используется для command/file endpoints.

Смотреть:

- `servers/views/_views_all.py`
- `servers/models.py`
- `servers/sftp.py`
- `servers/consumers/ssh_terminal.py`
- `servers/consumers/rdp_terminal.py`
- frontend share UI в `ai-server-terminal-main/src/pages/Servers.tsx`

Задача для агента:

- проверить все endpoints, которые используют `_accessible_servers_queryset()`;
- разделить права на view/connect/execute/file_write/admin;
- предложить минимальную модель permissions для `ServerShare`;
- добавить тесты на shared user, которому нельзя execute/write/delete.

Ожидаемый результат:

- список endpoint-level permission gaps;
- миграция/модель или plan для explicit share permissions;
- тесты на запрет risky операций для shared access.

### 2. MCP / SSH / pipeline execution guardrails

Проблема: MCP в SAFE mode разрешается с предупреждением, pipeline напрямую вызывает MCP/SSH/webhook, outbound URL не выглядит ограниченным allowlist.

Смотреть:

- `app/agent_kernel/permissions/engine.py`
- `studio/pipeline_executor.py`
- `studio/mcp_client.py`
- `studio/views/_views_all.py`
- `app/tools/safety.py`
- `app/tools/ssh_tools.py`

Задача для агента:

- проверить, какие execution paths обходят PermissionEngine;
- предложить единый policy gate для SSH/MCP/webhook;
- добавить allowlist/blocklist для webhook и HTTP MCP destinations;
- закрыть localhost/private network SSRF там, где это не нужно.

Ожидаемый результат:

- runtime contract: что разрешено в PLAN/SAFE/AUTO_GUARDED;
- tests для blocked MCP/admin/write operations;
- tests для webhook/MCP URL validation.

### 3. Secrets redaction не везде применяется

Проблема: memory redaction есть, но логи/activity могут писать MCP args, pipeline output excerpts, SSH env.

Смотреть:

- `app/agent_kernel/memory/redaction.py`
- `studio/mcp_client.py`
- `studio/pipeline_executor.py`
- `app/tools/ssh_tools.py`
- `core_ui/middleware.py`
- `core_ui/managed_secrets.py`

Задача для агента:

- найти все logger/activity/event writes с args/output/env;
- провести их через общий redaction helper;
- добавить unit tests с token/password/bearer/private key примерами.

Ожидаемый результат:

- no raw secret values in logs/activity payloads;
- единый helper для redaction на egress.

### 4. Docker build context может включать локальные секреты

Проблема: `.dockerignore` не закрывает часть локальных production/config artifacts, а Dockerfile делает `COPY . .`.

Смотреть:

- `.dockerignore`
- `.gitignore`
- `docker/backend.Dockerfile`
- `production-upload-bundle-*`
- `.env.production`
- `.notification_config.json`
- `.model_config.json`

Задача для агента:

- обновить `.dockerignore`;
- проверить build context на секретные/тяжелые/генерируемые файлы;
- не печатать значения секретов.

Ожидаемый результат:

- `.dockerignore` закрывает `.env*` кроме examples, notification/model config, production bundles, reports, root node_modules, caches;
- краткий check-list проверки Docker context.

## P1: Product / UX

### 5. Битая кодировка в Pipeline Editor

Проблема: в ключевом Studio editor видны испорченные символы/русский текст.

Смотреть:

- `ai-server-terminal-main/src/pages/PipelineEditorPage.tsx`
- locales в `ai-server-terminal-main/src/locales/`

Задача для агента:

- найти все `Ð`, `â`, `�` и похожие mojibake-паттерны;
- восстановить нормальный текст или вынести строки в locales;
- убедиться, что UI не ломается.

Ожидаемый результат:

- исправленный visible text;
- frontend lint/build не ухудшены.

### 6. Silent demo fallback скрывает backend failures

Проблема: frontend может тихо показывать mock/demo данные при недоступном Django, что опасно для ops-продукта.

Смотреть:

- `ai-server-terminal-main/src/lib/demo.ts`
- `ai-server-terminal-main/src/lib/api.ts`
- `ai-server-terminal-main/src/App.tsx`

Задача для агента:

- сделать demo mode только через явный env flag, например `VITE_ENABLE_DEMO_MODE=true`;
- показывать явную backend unavailable ошибку вместо fake success;
- добавить тесты на fallback behavior.

Ожидаемый результат:

- localhost/dev не включает demo автоматически;
- пользователь ясно видит, что backend недоступен.

### 7. Settings / AI Memory раздвоены

Проблема: старый `SettingsPage.tsx` содержит полноценный AI Memory UI, а новый `/settings/*` layout использует отдельные страницы и alias-поля.

Смотреть:

- `ai-server-terminal-main/src/App.tsx`
- `ai-server-terminal-main/src/pages/SettingsPage.tsx`
- `ai-server-terminal-main/src/pages/settings/SettingsMemoryPage.tsx`
- `ai-server-terminal-main/src/lib/api.ts`
- `servers/views/_views_all.py`

Задача для агента:

- определить, какой Settings UI является canonical;
- удалить/заархивировать legacy UI или переиспользовать компоненты;
- привести поля policy к backend contract.

Ожидаемый результат:

- один источник UI для AI Memory settings;
- frontend policy payload совпадает с backend fields.

## P1: Architecture / Maintainability

### 8. Backend view monoliths

Проблема: `core_ui`, `servers`, `studio` имеют `_views_all.py` как transition state.

Смотреть:

- `core_ui/views/_views_all.py`
- `servers/views/_views_all.py`
- `studio/views/_views_all.py`
- `core_ui/views/__init__.py`
- `servers/views/__init__.py`
- `studio/views/__init__.py`

Задача для агента:

- предложить безопасный split plan без изменения URLs;
- начинать с одной зоны, например server files или auth/access;
- добавить smoke tests на перенесенные endpoints.

Ожидаемый результат:

- маленькие domain modules;
- `urls.py` остается стабильным;
- no behavior change.

### 9. Frontend monoliths

Проблема: несколько файлов слишком большие и stateful.

Смотреть:

- `ai-server-terminal-main/src/lib/api.ts`
- `ai-server-terminal-main/src/pages/Servers.tsx`
- `ai-server-terminal-main/src/pages/PipelineEditorPage.tsx`
- `ai-server-terminal-main/src/components/terminal/LinuxUiPanel.tsx`
- `ai-server-terminal-main/src/pages/SettingsPage.tsx`

Задача для агента:

- разделить без изменения поведения;
- начинать с API domain modules или hooks;
- не делать redesign в этом task.

Ожидаемый результат:

- уменьшение размеров ключевых файлов;
- импорты переведены на feature/domain API modules;
- tests/build проходят.

### 10. AI memory / agent runtime переусложнен

Проблема: много runtime paths и memory layers, часть поведения выглядит experimental для mini-prod.

Смотреть:

- `servers/agent_engine.py`
- `servers/multi_agent_engine.py`
- `servers/services/terminal_ai/`
- `servers/agent_tools.py`
- `studio/pipeline_executor.py`
- `app/agent_kernel/`
- `app/agent_kernel/memory/store.py`

Задача для агента:

- составить runtime contract: live, legacy, experimental;
- проверить, какие paths реально вызываются из UI/API;
- предложить disable/feature-flag для auto skill promotion;
- не удалять код без отдельного подтверждения.

Ожидаемый результат:

- карта runtime paths;
- список кандидатов на feature flag / archive / removal.

## P2: Repo Hygiene / Deploy

### 11. Generated artifacts tracked in Git

Проблема: в Git трекаются Playwright reports/output/test-results и другие generated artifacts.

Смотреть:

- `ai-server-terminal-main/playwright-report/`
- `ai-server-terminal-main/output/`
- `ai-server-terminal-main/test-results/`
- `docker/multi-user-load-smoke.*`
- `.gitignore`

Задача для агента:

- проверить, что реально tracked;
- предложить `git rm --cached` список;
- обновить `.gitignore`;
- не удалять локальные файлы без отдельного подтверждения.

Ожидаемый результат:

- generated artifacts больше не tracked;
- локально файлы могут остаться ignored.

### 12. Два frontend toolchain слоя

Проблема: есть root `package.json`/`vite.config.ts`/`src`, и отдельное полноценное приложение в `ai-server-terminal-main/`.

Смотреть:

- root `package.json`
- root `vite.config.ts`
- root `src/`
- `ai-server-terminal-main/package.json`
- `ai-server-terminal-main/vite.config.ts`
- `README.md`

Задача для агента:

- выяснить, нужен ли root thin entrypoint;
- если нет, предложить удаление/архивацию;
- если да, задокументировать назначение и убрать drift.

Ожидаемый результат:

- один canonical frontend workflow;
- README/scripts не конфликтуют.

### 13. Render / production compose incomplete

Проблема: Render blueprint не задает Redis/Channels env, production compose не поднимает отдельные worker/scheduler services.

Смотреть:

- `render.yaml`
- `docker-compose.production.yml`
- `web_ui/settings/production.py`
- `web_ui/settings/base.py`
- management commands в `servers/management/commands/` и `studio/management/commands/`

Задача для агента:

- определить production runtime requirements;
- добавить Redis env для Render или явно отметить unsupported;
- предложить worker/scheduler services для compose.

Ожидаемый результат:

- deploy docs/config соответствуют production settings;
- background jobs имеют понятный способ запуска.

### 14. Stale config references

Проблема: `pyproject.toml` и static manifest содержат ссылки на старые modules/routes.

Смотреть:

- `pyproject.toml`
- `core_ui/static/manifest.json`
- `requirements*.txt`
- `README.md`

Задача для агента:

- удалить stale `agent_hub`, `tasks`, неактивные app references;
- проверить testpaths/coverage/isort;
- исправить manifest routes/icons.

Ожидаемый результат:

- tooling config отражает текущую структуру: `core_ui`, `servers`, `studio`, `app`;
- no stale `/tasks/` references.

## Рекомендуемый порядок выдачи агентам

1. `.dockerignore` / generated artifacts cleanup.
2. Shared server permissions audit + tests.
3. Redaction for logs/activity.
4. MCP/webhook/SSH guardrails.
5. PipelineEditor encoding.
6. Demo fallback explicit flag.
7. Settings memory UI consolidation.
8. Frontend/backend monolith split plans.
9. Production deploy workers/Render config.
10. Runtime contract for AI memory/agents.

## Формат задачи для агента

```text
Read-only or implementation task.
Scope: <paths>
Goal: <one concrete objective>
Constraints:
- Do not commit or push.
- Do not touch unrelated files.
- Do not print secret values.
- List files inspected/changed.
Return:
- summary
- files changed
- tests/checks run
- risks/open questions
```
