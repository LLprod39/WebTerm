# Production Readiness Plan

Последнее обновление: 2026-03-13
Статус релиза: `NO-GO`

Этот файл используется как рабочий трекер подготовки к продакшену.

Правила ведения:
- Каждый пункт закрывается только после кода, проверки и краткой заметки в секции `Прогресс`.
- Если задача частично выполнена, статус меняется на `IN_PROGRESS`, но чекбокс не закрывается.
- Для блокеров релиза используем только статусы `TODO`, `IN_PROGRESS`, `DONE`, `BLOCKED`.
- Перед релизом должны быть закрыты все задачи из секции `P0`.

## Статусы

- `TODO` — задача еще не начата
- `IN_PROGRESS` — задача в работе
- `DONE` — задача завершена и проверена
- `BLOCKED` — задача заблокирована внешним фактором

## Критерий готовности к релизу

Проект считается готовым к выкладке только если одновременно выполнено все ниже:

- Все задачи `P0` имеют статус `DONE`
- Backend test suite зеленый
- Frontend build зеленый
- Frontend lint зеленый
- Основные browser smoke flows пройдены
- Проверен сценарий нескольких одновременных пользователей
- Проверены права доступа, логи и экспорт чувствительных данных
- Подготовлен rollback plan

## P0 Блокеры Продакшена

### 1. Runtime архитектура агентов

- [x] `DONE` Вынести запуск full agents из HTTP request path в background runtime / queue
- [x] `DONE` Вынести approve-plan path из HTTP request path в background runtime / queue
- [x] `DONE` Сделать единый control path для `run / stop / pause / resume / reply`
- [x] `DONE` Проверить работу при нескольких web workers

Критерий завершения:
- HTTP endpoint только ставит задачу и сразу возвращает ответ
- Долгий agent run не занимает web worker
- Stop/reply доходят до живого run независимо от воркера

### 2. Runtime архитектура pipelines

- [x] `DONE` Закрыть доступ к чужим pipeline live WebSocket run
- [x] `DONE` Сделать реальный stop для живого pipeline executor
- [x] `DONE` Прерывать `logic/wait` и `logic/human_approval` по stop
- [x] `DONE` Проверить межпроцессную работу pipeline control path
- [x] `DONE` Убедиться, что live updates работают при нескольких воркерах

Критерий завершения:
- Владелец run видит live events только своих запусков
- Stop реально останавливает выполнение, а не только меняет статус в БД
- Поведение не ломается при multi-worker deployment

### 3. Redis и межпроцессная шина

- [x] `DONE` Поднять Redis для Channels в production topology
- [x] `DONE` Убрать зависимость критичных live control сценариев от `InMemoryChannelLayer`
- [x] `DONE` Проверить работу live updates и control signals через Redis

Критерий завершения:
- Продакшен не зависит от in-memory состояния одного процесса
- Live updates и stop/control работают через общую шину

### 4. Security baseline Django

- [x] `DONE` Зафиксировать `DEBUG=False` для продакшена
- [x] `DONE` Установить реальный `SECRET_KEY`
- [x] `DONE` Включить `SECURE_SSL_REDIRECT`
- [x] `DONE` Включить `SESSION_COOKIE_SECURE`
- [x] `DONE` Включить `CSRF_COOKIE_SECURE`
- [x] `DONE` Настроить `SECURE_HSTS_SECONDS`
- [x] `DONE` Проверить `ALLOWED_HOSTS`
- [x] `DONE` Проверить `CSRF_TRUSTED_ORIGINS`

Критерий завершения:
- `python manage.py check --deploy` не показывает критичных security warnings

### 5. CSRF perimeter

- [x] `DONE` Проинвентаризировать все `@csrf_exempt`
- [x] `DONE` Убрать `@csrf_exempt` со всех обычных authenticated mutating API
- [x] `DONE` Оставить exemption только на webhook / token-only endpoints
- [x] `DONE` Перепроверить login, settings, access, servers, agents, studio API

Критерий завершения:
- Обычные браузерные POST/PUT/DELETE endpoint не живут без CSRF без веской причины

### 6. SSH безопасность

- [x] `DONE` Убрать `known_hosts=None` из terminal / monitor / ssh tools
- [x] `DONE` Добавить host key verification
- [x] `DONE` Определить стратегию первого доверия: TOFU или явное подтверждение ключа
- [x] `DONE` Добавить понятную обработку смены host key

Критерий завершения:
- SSH соединения не игнорируют host key verification

### 7. Frontend критичные runtime-дефекты

- [x] `DONE` Убрать постоянный resize WebSocket spam на скрытых терминальных вкладках
- [x] `DONE` Исправить потерю AI-запроса, если terminal socket еще не `OPEN`
- [x] `DONE` Добавить reconnect/backoff для terminal WebSocket
- [x] `DONE` Исправить stale state в Agent Run tasks
- [x] `DONE` Перевести pipeline live WebSocket на общий WS helper и prod env config

Критерий завершения:
- При нескольких открытых серверах нет лишнего фонового WS churn
- AI-запросы не теряются молча
- Временный разрыв соединения не убивает долгую сессию без восстановления

### 8. Права доступа и чувствительные данные

- [x] `DONE` Еще раз проверить admin-only доступ к логам и экспорту логов
- [x] `DONE` Перепроверить MCP, personal/shared context и reveal secret paths
- [x] `DONE` Убедиться, что non-admin не может читать audit data
- [x] `DONE` Проверить group/shared access на серверах и контекстах

Критерий завершения:
- Пользователь видит только свои данные и разрешенные shared-данные
- Логи и экспорт логов доступны только администратору

## P1 Стабилизация Перед Массовым Тестом

### 9. Frontend quality gate

- [x] `DONE` Убрать `@ts-nocheck` с критичных страниц
- [x] `DONE` Довести `npm run lint` до зеленого
- [ ] `TODO` Уменьшить количество `any` в e2e и runtime коде
- [x] `DONE` Закрыть warnings по hooks/deps там, где это реально влияет на поведение

Критерий завершения:
- `npm run lint` зеленый
- Ключевые страницы не скрывают ошибки через `@ts-nocheck`

### 10. Тестовое покрытие

- [x] `DONE` Добавить backend tests на runtime control и permissions
- [x] `DONE` Добавить browser smoke tests на login, terminal, agents, studio
- [x] `DONE` Добавить E2E на multi-tab terminal flow
- [x] `DONE` Добавить E2E на reconnect / lost connection сценарии
- [x] `DONE` Добавить E2E на pipeline live updates

Критерий завершения:
- Критичные сценарии покрыты не только unit-test, но и browser / integration тестами

### 11. Observability и audit

- [x] `DONE` Добавить request id / correlation id
- [x] `DONE` Подготовить file/syslog sink для серверных логов
- [x] `DONE` Проверить, что agent / pipeline / terminal ошибки не теряются
- [x] `DONE` Добавить health visibility по live runtime проблемам

Критерий завершения:
- По любой ошибке можно быстро восстановить цепочку событий

### 12. Ограничения и защита от перегрузки

- [x] `DONE` Ввести лимиты на число параллельных agent runs
- [x] `DONE` Ввести лимиты на pipeline concurrency
- [x] `DONE` Проверить лимиты на SSH sessions и timeouts
- [x] `DONE` Проверить MCP timeout / retry policy
- [x] `DONE` Проверить поведение при длинных LLM calls

Критерий завершения:
- Один пользователь или одна ошибка не валит систему под нагрузкой

### 13. Production deploy topology

- [x] `DONE` Зафиксировать production env template
- [x] `DONE` Зафиксировать production compose / service topology
- [x] `DONE` Подготовить one-command install / update script для чистого Linux-хоста
- [x] `DONE` Проверить Daphne / Nginx / static / media / healthcheck
- [x] `DONE` Проверить запуск с PostgreSQL и Redis
- [x] `DONE` Подготовить restart strategy и log rotation

Критерий завершения:
- Есть понятная воспроизводимая схема развертывания без dev-зависимостей

## P2 Финальная Приемка

### 14. Browser smoke и ручная приемка

- [x] `DONE` Login / logout
- [x] `DONE` Terminal SSH
- [x] `DONE` Несколько серверов одновременно
- [x] `DONE` AI assistant в терминале
- [x] `DONE` Agents create / run / stop / reply
- [x] `DONE` Studio pipeline create / run / stop / live
- [x] `DONE` MCP create / test / tools
- [x] `DONE` Notifications test intentionally skipped by user request for this release
- [x] `DONE` Admin-only log access

### 15. Multi-user и нагрузка

- [x] `DONE` Прогнать сценарий нескольких одновременных пользователей
- [x] `DONE` Прогнать несколько одновременных terminal sessions
- [x] `DONE` Прогнать несколько agent runs параллельно
- [x] `DONE` Прогнать несколько pipeline runs параллельно
- [x] `DONE` Проверить деградацию по CPU / RAM / DB / WS

### 16. Release management

- [x] `DONE` Подготовить release checklist
- [x] `DONE` Подготовить rollback plan
- [x] `DONE` Подготовить post-deploy smoke checklist
- [ ] `TODO` Зафиксировать итоговый `GO / NO-GO`

Release checklist:
- Проверить, что `DJANGO_DEBUG=false`, задан реальный `DJANGO_SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SITE_URL`, `FRONTEND_APP_URL`
- Проверить, что задан `CHANNEL_REDIS_URL` и `python manage.py check` проходит без production errors
- Проверить, что `docker compose --env-file .env.production -f docker-compose.production.yml config` проходит без ошибок
- Проверить, что `python manage.py migrate --noinput` и `python manage.py collectstatic --noinput` выполняются на целевом окружении
- Проверить доступность `/nginx-health`, `/api/health/`, `/`, `/static/admin/css/base.css`, `/media/...`
- Проверить login, terminal, agents, studio runs, admin activity logs на целевом публичном URL
- Проверить, что Redis/DB volumes и log rotation активны
- Снять backup БД непосредственно перед выкладкой

Rollback plan:
- Остановить приём трафика на время отката через балансировщик или временную maintenance страницу
- Откатить backend/frontend образы на предыдущий тег и поднять стек тем же `docker compose` файлом
- Если был schema change, откатывать только на заранее совместимую версию приложения; при несовместимости восстановить БД из pre-release backup
- Проверить `/api/health/`, login и один terminal flow сразу после отката
- Проверить, что background runs не застряли в `pending/running` после смены версии

Post-deploy smoke checklist:
- Открыть публичный `/login`, выполнить login/logout обычным пользователем
- Открыть SSH terminal и убедиться, что соединение устанавливается и не рвётся при переключении вкладок
- Проверить AI assistant panel в terminal
- Запустить один agent run и убедиться, что `stop/reply` работают
- Запустить один studio pipeline run, увидеть live updates и остановить его
- Проверить, что non-admin получает отказ на `/api/settings/activity/`, а admin получает `200`
- Проверить `X-Request-ID` в ответах `/api/health/` и наличие server log sink

## Прогресс

### 2026-03-13

- `DONE` Agent multi-worker regression hardened: explicit test proves `reply/stop` still work when no live engine is present in the local process; runtime control is persisted to DB and picked up later
- `DONE` Added `check_channel_layer` management command and shared transport verifier using independent channel layer instances to validate direct/group delivery
- `DONE` Production settings now fail fast if `DJANGO_DEBUG=false` and neither `CHANNEL_REDIS_URL` nor `CELERY_BROKER_URL` is configured
- `DONE` Deploy check for Channels layer escalated from warning to error when production is still on `InMemoryChannelLayer`
- `DONE` Redis-backed channel layer smoke passed against local Docker Redis: `python manage.py check_channel_layer --timeout 3`
- `DONE` Prod-style settings check passed with Redis configured: `python manage.py check`
- `DONE` Frontend lint green after typed cleanup and scoped legacy overrides for `e2e/ui`: `npm run lint`
- `DONE` Frontend app TypeScript compile green: `npx tsc -p tsconfig.app.json --noEmit`
- `DONE` Removed remaining frontend `@ts-nocheck` from the last critical pages: `AgentsPage`, `MCPHubPage`, `PipelineEditorPage`; repo grep no longer finds frontend `@ts-nocheck`
- `DONE` Frontend production build rechecked after typing/lint changes: `npm run build`
- `DONE` Frontend unit test smoke rechecked: `npm run test -- --run`
- `DONE` Backend regression coverage added for runtime control and permissions paths across agents, pipelines, audit/admin and desktop/studio access surfaces
- `DONE` Playwright functional smoke stabilized against current UI/API contracts for auth/navigation, servers, settings and studio pages
- `DONE` Added dedicated agents browser smoke covering mini-agent create/run flow and live full-agent stop flow from `/agents/run/:runId`
- `DONE` Targeted browser smoke pack rechecked green: `npm run test:e2e -- e2e/smoke.spec.ts e2e/navigation.spec.ts e2e/settings.spec.ts e2e/studio.spec.ts e2e/servers.spec.ts e2e/agents.spec.ts` → `13 passed`
- `DONE` Added dedicated terminal browser E2E with isolated WebSocket mock for multi-tab persistence and reconnect-after-loss behavior
- `DONE` Expanded targeted browser pack rechecked green with terminal coverage: `npm run test:e2e -- e2e/smoke.spec.ts e2e/navigation.spec.ts e2e/settings.spec.ts e2e/studio.spec.ts e2e/servers.spec.ts e2e/agents.spec.ts e2e/terminal.spec.ts` → `15 passed`
- `DONE` Added pipeline live browser E2E with isolated run WebSocket mock; verified `node_event` updates render in `/studio/runs`
- `DONE` Full targeted browser/E2E pack rechecked green: `npm run test:e2e -- e2e/smoke.spec.ts e2e/navigation.spec.ts e2e/settings.spec.ts e2e/studio.spec.ts e2e/servers.spec.ts e2e/agents.spec.ts e2e/terminal.spec.ts e2e/pipeline-live.spec.ts` → `16 passed`
- `DONE` Frontend typing hardening rechecked green after the last page cleanup: `npx tsc -p tsconfig.app.json --noEmit`, `npm run lint`, `npm run build`
- `DONE` Added backend concurrency guards for active agent/pipeline runs with env-configurable per-user and global limits; start endpoints now return `429` instead of overcommitting runtime
- `DONE` Scheduler and webhook pipeline launches now respect the same pipeline concurrency guard instead of bypassing manual-run limits
- `DONE` Regression checks for overload guards passed: `pytest --reuse-db tests/test_servers_api_smoke.py -k "full_agent_run_launches_in_background or full_agent_run_enforces_user_active_run_limit"` and `pytest tests/test_studio_api_smoke.py -k "studio_pipeline_trigger_template_and_servers_endpoints or pipeline_run_enforces_user_active_run_limit"`
- `DONE` SSH terminal runtime now uses shared timeout settings plus per-user/global session guards backed by `ServerConnection`; targeted checks passed for the new session-limit helper
- `DONE` MCP stdio/http clients now use shared timeout settings, safe HTTP retries only for initialize/list paths, and no automatic retry for tool calls; targeted unit tests passed for retryable and non-retryable HTTP paths
- `DONE` Targeted backend validation for the new overload protections passed: `python -m py_compile`, `python manage.py check`, `pytest --reuse-db tests/test_servers_api_smoke.py -k "terminal_session_limit_helper_enforces_user_limit or full_agent_run_enforces_user_active_run_limit"`, `pytest tests/test_tools_and_policy_units.py -k "mcp_client or mcp_http_client"`
- `DONE` Long LLM calls are now bounded by shared configurable timeouts across Gemini, Grok, Claude and OpenAI paths; timeout exits are explicit and tested instead of hanging indefinitely
- `DONE` LLM runtime protection checks passed: `python -m py_compile`, `python manage.py check`, `pytest tests/test_llm_runtime_unit.py tests/test_tools_and_policy_units.py -k "llm or mcp_http_client or mcp_client"`
- `DONE` Added production deployment artifacts: `.env.production.example` and `docker-compose.production.yml` with PostgreSQL, Redis, Daphne backend, frontend, nginx, named volumes, restart policy and json-file log rotation
- `DONE` Production compose syntax validated with `docker compose --env-file .env.production.example -f docker-compose.production.yml config`
- `DONE` Production env template rechecked with `python manage.py check --deploy`; only intentional preload warning remains when `SECURE_HSTS_PRELOAD=false`
- `DONE` Production topology hardened after live smoke found a real compose bug: internal service ports are now decoupled from published host ports via `*_HOST_PORT`, and production nginx serves `/static` and `/media` directly from shared volumes
- `DONE` Added isolated production smoke harness: `docker-compose.production.smoke.yml` plus `docker/smoke-production-stack.ps1`
- `DONE` Full production smoke passed on isolated ports with fresh PostgreSQL + Redis + backend + frontend + nginx; validated `nginx-health`, `/api/health/`, `/`, `/static/admin/css/base.css` and a real `/media/prod-smoke.txt` round-trip
- `DONE` Added isolated multi-user smoke tooling: `seed_multi_user_smoke` management command, internal `ssh-target` service in `docker-compose.production.smoke.yml`, and `docker/multi-user-load-smoke.ps1`
- `DONE` Live `1x1x1` isolated smoke exposed and then verified the pipeline SSH regression: `studio.pipeline_executor._execute_agent_ssh_cmd()` now awaits async `_build_connect_kwargs()` instead of treating it like a dict
- `DONE` Added regression coverage for the pipeline SSH connect-kwargs path: `pytest -q app/test_studio_pipeline_api_runtime.py -k execute_agent_ssh_cmd_awaits_async_connect_kwargs` → `1 passed` (WSL venv)
- `DONE` Full isolated `4x2x2` multi-user smoke passed on the running prod-like stack: `4 users / 8 terminal sessions / 8 pipeline runs`, total elapsed `4.618s`, terminal avg/max `3.07s / 3.283s`, pipeline avg/max `2.66s / 2.765s`
- `DONE` Resource snapshot captured after the `4x2x2` smoke in `docker/multi-user-load-smoke.stats.txt`; observed memory stayed low (`backend ~166.9 MiB`, `postgres ~79.7 MiB`, `nginx ~10 MiB`, `redis ~8 MiB`) with transient backend CPU burst during the active run
- `DONE` Multi-user smoke artifacts saved to `docker/multi-user-load-smoke.seed.json`, `docker/multi-user-load-smoke.results.json`, and `docker/multi-user-load-smoke.stats.txt`
- `DONE` Observability block closed: request-scoped `X-Request-ID` is now generated/forwarded, request/activity audit metadata is JSON-normalized so datetimes no longer drop events, `/api/health/` exposes basic runtime observability flags, and production log sinks are configurable through `APP_LOG_FILE` / syslog env
- `DONE` Observability regression checks passed: `python -m py_compile`, `python manage.py check`, `docker compose --env-file .env.production.example -f docker-compose.production.yml config`, `pytest -q tests/test_core_ui_api_smoke.py -k 'health_and_anonymous_auth_endpoints or log_user_activity_normalizes_datetime_metadata_and_uses_audit_context or request_audit_middleware_sets_request_id_header_and_logs_it'` → `3 passed` (WSL venv)
- `DONE` Seeded smoke users now include one deterministic mini-agent each; the shared multi-user harness supports `--agent-runs-per-user` without introducing a second load script
- `DONE` Isolated `1x1x1x1` smoke passed with agent coverage: `1 user / 1 terminal / 1 pipeline / 1 agent`, total elapsed `2.149s`, agent latency `1.348s`
- `DONE` Full isolated `4x2x2x2` smoke passed on the running prod-like stack: `4 users / 8 terminal sessions / 8 pipeline runs / 8 agent runs`, total elapsed `4.691s`, terminal avg/max `3.5s / 3.562s`, pipeline avg/max `3.306s / 3.43s`, agent avg/max `2.552s / 2.573s`
- `DONE` Resource snapshot after the `4x2x2x2` smoke stayed controlled in `docker/multi-user-load-smoke.stats.txt`: `backend ~138.9 MiB`, `postgres ~90 MiB`, `nginx ~10.12 MiB`, `redis ~8.18 MiB`, `ssh-target ~1.88 MiB`
- `DONE` Production nginx routing fixed for public `/login`: exact `/login` now stays on SPA instead of bouncing through `/login/` and the internal `:8080` host
- `DONE` Production frontend crash on `/login` fixed by removing the circular `react-vendor` split in Vite manual chunks; rebuilt smoke stack loads the login screen without the previous `createContext` runtime error
- `DONE` Public smoke browser acceptance on `http://127.0.0.1:18080`: login/logout works, non-admin `/api/settings/activity/` returns `403`, admin returns `200`, and admin settings page shows activity/logging UI
- `DONE` Public smoke browser acceptance for Studio runtime: UI-created pipeline `#3` opens correctly, slow acceptance pipeline run returned `202`, live pipeline WebSocket was observed, and the run finished as `stopped` after clicking `Стоп`
- `DONE` Local admin browser acceptance for MCP: create/detail/test/tools/delete passed against demo MCP over `http://127.0.0.1:8765/mcp`; tools inspection returned `7` tools and the server was visible in `/studio/mcp`
- `DONE` Notifications live acceptance intentionally waived by user for this release; backend transport-mocked coverage remains green, but no live external delivery sign-off was collected
- `DONE` Added one-command production installer `docker/install-production.sh`: it bootstraps `.env.production`, can generate secrets, validates compose/env, waits for healthchecks, runs Django checks, and can create an initial superuser
- `DONE` Installer dry-run validation passed against a temporary production env file: `bash docker/install-production.sh --env-file .env.production.install-test.tmp --validate-only`
- `NO-GO` P0, browser acceptance, observability, load and release checklists are green; remaining release gate is only final GO / NO-GO sign-off

### 2026-03-12

- `DONE` Backend suite: `69 passed`
- `DONE` `python manage.py check`
- `DONE` `npm run build`
- `DONE` Pipeline live authorization tightened
- `DONE` Pipeline stop wired to live executor
- `DONE` Pipeline wait/approval now react to stop
- `DONE` Full agent `run` moved out of HTTP request path into background launcher
- `DONE` Multi-agent `approve-plan` moved out of HTTP request path into background launcher
- `DONE` Background agent launcher now preserves immediate `run_id` and Channels live events
- `DONE` Agent runtime control moved to DB-backed mailbox in `AgentRun.runtime_control`; stop/pause/resume/reply no longer depend only on in-process registry
- `DONE` Agent engines now poll runtime control, ack replies from DB, and stop more safely during wait states
- `DONE` Backend suite after agent runtime control changes: `72 passed`
- `IN_PROGRESS` Production compose topology now includes Redis and backend gets default `CHANNEL_REDIS_URL=redis://redis:6379/1`
- `DONE` Added deploy-time check warning when `DEBUG=False` but Channels still use `InMemoryChannelLayer`
- `DONE` Security baseline hardened in settings: prod now requires explicit secret, derives hosts/origins safely, and passes `check --deploy` with valid prod env
- `DONE` CSRF perimeter tightened: removed blanket exemptions from browser/session APIs in `core_ui` and `servers`; remaining exemptions are token/webhook or desktop bearer endpoints
- `DONE` Backend suite after CSRF/security changes: `74 passed`
- `DONE` SSH host key verification enabled across terminal, monitor, agents and server SSH tools using TOFU + persisted trusted keys on `Server`
- `DONE` Added controlled host key refresh path for owner-only `server test` and auto-clear of trusted keys when server address changes
- `DONE` Backend suite after SSH hardening: `80 passed`
- `DONE` Frontend terminal runtime hardened: AI requests queue until socket is ready, terminal WS reconnects with backoff, and hidden tabs no longer spam resize events
- `DONE` Agent Run page now drops stale local plan state when fresh server plan diverges
- `DONE` Pipeline run live WebSocket moved onto shared WS origin helper and reconnect logic
- `DONE` Pipeline stop path moved to DB-backed mailbox in `PipelineRun.runtime_control`; HTTP/WS stop now persist stop intent even without live in-process executor
- `DONE` `PipelineExecutor` now polls both `status` and `runtime_control.stop_requested`, so cross-process stop does not depend only on the local registry
- `DONE` Targeted pipeline runtime checks after DB-backed stop control: `10 passed` (`app/test_studio_pipeline_api_runtime.py`, WSL venv)
- `DONE` Frontend verification after runtime fixes: `npm run build` green, `npm run test` green
- `DONE` Permission hardening: non-admin users are blocked from audit log stream/export and audit-setting mutations
- `DONE` Permission hardening: MCP management is now admin-only in both web Studio API and desktop API because it can execute backend-side commands
- `DONE` Permission hardening: skill workspace/scaffold/validate and global notifications are now admin-only
- `DONE` Shared server/group context tightened: shared users no longer see saved-secret indicators, and group members no longer receive group `environment_vars`
- `DONE` Reveal-password hardened: owner must provide session/payload master password; env fallback is no longer enough for password disclosure
- `NO-GO` До релиза остаются P0 блокеры по multi-worker/runtime architecture и Redis

## Текущий порядок выполнения

1. Final GO / NO-GO decision
