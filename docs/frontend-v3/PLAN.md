# WebTerm frontend-v3 — план работ

Дата: 2026-09-13  
Ветка: `frontend-v3` (от `test`)  
Владелец UI: Пиксель  
Запуск/скелет: LU  
Контракты API/ws: Ядро + Мост  
Sec: Страж  
QA (ручной смок): Тест + пользователь

---

## 1. Цель

Собрать новый фронт в отдельной папке `frontend-v3`, который:

1. Переносит **всю рабочую функциональность** текущего `frontend/` (auth, servers, terminal/ws, files, automation, studio, agents, k8s, settings и т.д.).
2. Меняет **только визуал и копирайт**: корпоративный B2B-стиль (светлая тема, синий accent, карточки, RU-статусы) — понятный руководителю и удобный инженеру. См. [`UI_SPEC.md`](UI_SPEC.md).
3. Убирает нейрослоп: декоративные тексты, бейджи без источника, бесполезный поиск/даты на главной, «умные» индикаторы, AI-звучащую навигацию.

Не цель: придумать новый продукт или ломать бэкенд.

---

## 2. Зафиксированные решения

| Тема | Решение |
| --- | --- |
| Папка | `frontend-v3/` |
| Старый фронт | `frontend/` остаётся на порту **8080** до приёмки |
| Новый фронт | порт **8081** |
| Backend | оба proxy на `http://127.0.0.1:9000` |
| Тема | **v2 (2026-09-13): дефолт светлый, корпоративный B2B, accent синий `#2563eb`; тёмная — переключателем.** (v1 «тёмный ч/б» отменён) |
| Эталон стиля | [`UI_SPEC.md`](UI_SPEC.md) v2 — Atlassian / Datadog / Grafana Enterprise уровень; **не** ashita/flow/pulse и не ч/б `fa00a74` |
| Контракты | session / servers / terminal / ws / files и остальные API — **1:1**, без ломки |
| Тесты | пока ручные; тяжёлый Playwright — только по явной команде |
| Nightly Audit | снаружи команды, не в канале |
| Skills/MCP | Context7, Superdesign, frontend-design, Playwright, Semgrep; Wonder/Mobbin после логина; Github — пока broken |

---

## 3. Принципы UI (анти-нейрослоп)

1. Текст операционный: что это, что делать, что сломалось. Одна строка описания под заголовком — допустима.
2. Нет декоративных метрик/бейджей без реального поля API. KPI-карточки из API — да.
3. Нет «приветствий», motivational copy, пустых search/date на главной.
4. Навигация короткая: понятные русские названия, без маркетинга.
5. Плотность средняя: карточки → таблицы; статусы — русские подписи в Badge.
6. Тёмный режим — тот же layout, только токены цвета.

Если бэк отдаёт поля только под декор — Мост фиксирует список → Ядро чистит точечно (не блокер v3).

---

## 4. Порты и запуск

```text
frontend/     → http://127.0.0.1:8080  (текущий)
frontend-v3/  → http://127.0.0.1:8081  (новый)
backend       → http://127.0.0.1:9000
Postgres/Redis → Docker only
```

Proxy в `frontend-v3` (те же префиксы, что в `frontend/vite.config.ts`):

- `/api/` → `9000`
- `/servers/api/` → `9000`
- `/ws/` → `9000` (websocket)

**Расхождение со старым конфигом (закрыть в Фазе 0):** `frontend/vite.config.ts` явно
прокидывает `cookie` и domain-auth заголовки (`x-forwarded-user`, `x-remote-user`,
`remote-user`, `x-auth-request-user`, `x-forwarded-preferred-username`) в `proxyReq`
**и** в `proxyReqWs` — http-proxy не всегда передаёт Cookie на WS upgrade. В
`frontend-v3/vite.config.ts` этого нет → терминал по ws через dev-proxy может не
авторизоваться. Перенести `copyProxyHeaders` 1:1.

Env (`frontend-v3/.env`):

- `VITE_DJANGO_URL=http://127.0.0.1:9000` — target прокси
- опционально `VITE_DJANGO_WS_URL` / `VITE_WS_HOST` — старый клиент (`frontend/src/lib/api.ts`,
  `buildWsBase`) умеет ходить на ws мимо прокси; в v3 сохранить те же переменные
- `.env*` **не** коммитить (Страж) — `frontend-v3/.gitignore` уже исключает `.env`, `.env.local`, `.env.*.local`

Backend (корневой `.env`):

- CORS/CSRF: в `web_ui/settings/security.py` при `DEBUG=true` origin'ы
  `http://127.0.0.1:8081` и `http://localhost:8081` **уже** входят в дефолт
  (`_DEFAULT_FRONTEND_ORIGINS`). Для `DJANGO_DEBUG=false` — добавить в
  `CSRF_TRUSTED_ORIGINS` / `CORS_ALLOWED_ORIGINS` руками.
- `FRONTEND_APP_URL` используется бэком для **редиректов** (`core_ui/urls.py` index_redirect,
  `core_ui/views/auth_views.py` — SSO/domain-auth). Он один → в dual-run
  бэк-редиректы ведут на один фронт. По умолчанию оставляем `8080`; на приёмке
  переключаем на `http://127.0.0.1:8081`.

Запуск:

```powershell
cd C:\WebTrerm\frontend-v3
npm install
npm run dev
```

---

## 5. Фазы

### Фаза 0 — Скелет (LU, сейчас)

- [x] ветка `frontend-v3`
- [x] Vite + React + TS в `frontend-v3/`
- [x] порт `8081`, proxy → `9000`
- [x] тёмные ч/б CSS-токены + shell-заглушка
- [x] `.env.example`, `.gitignore`
- [x] коммит скелета (`dd731d8`)
- [x] proxy: перенести `copyProxyHeaders` (cookie + domain-auth headers, `proxyReq` и `proxyReqWs`) из `frontend/vite.config.ts`
- [x] `frontend-v3/README.md` — сейчас шаблон Vite; заменить на короткий запуск/порты/ссылку на этот план
- [x] закоммитить `frontend-v3/public/icons.svg` (висит untracked) или убрать

### Фаза 1 — Матрица экранов ↔ API (Пиксель + Мост)

Таблица маршрутов текущего фронта → API-модули → приоритет переноса.
Источник маршрутов: `frontend/src/App.tsx`; API-модули лежат в `frontend/src/api/*.ts`,
общий клиент (request/CSRF/demo-fallback/ws-URL builders) — `frontend/src/lib/api.ts`.

| Приоритет | Экран / path | API / канал | FeatureGate | Owner UI |
| --- | --- | --- | --- | --- |
| P0 | Login `/login` | `api/auth.ts`, session cookie + CSRF | — | Пиксель |
| P0 | Index `/` → редирект на первый доступный раздел; `/admin`, `/dashboard/admin` → `/dashboard`; `*` → NotFound | `lib/navigation.ts` `firstAllowedApplicationPath` | — | Пиксель |
| P0 | First-run gate (`FirstRunReadinessGate` оборачивает **все** приватные маршруты) → `/settings/readiness?firstRun=1` | `lib/first-run-readiness` | `settings` | Пиксель + Мост |
| P0 | Dashboard `/dashboard` | auth session + servers, без декор-метрик | `dashboard` | Пиксель |
| P0 | Servers `/servers` | `api/servers.ts`, `api/server-memory.ts` | `servers` | Пиксель |
| P0 | Terminal `/servers/:id/terminal`, hub `/servers/hub` | ws `/ws/servers/{id}/terminal/`, `api/terminal-preferences.ts`, `api/linux-ui.ts` | `servers` | Пиксель + Мост |
| P0 | Files (внутри terminal/server) | `api/server-files.ts` (`/servers/api/...`) | `servers` | Пиксель |
| P1 | Agents `/agents`, run `/agents/run/:runId` | `api/agents.ts`, `api/agent-*.ts` | `agents` | Пиксель |
| P1 | Automation `/automation/*` | `api/playbooks.ts`, `api/playbook-workspace.ts`, `api/playbook-bundles.ts`, `api/playbook-preflight.ts`, `api/playbook-run-report.ts` | `automation` | Пиксель |
| P1 | Studio `/studio`, `/studio/drafts`, `/studio/pipeline/:id`, `/studio/pipeline/new`, `/studio/runs`, `/studio/agents`, `/studio/skills`, `/studio/mcp`, `/studio/notifications` | `api/studio.ts`, `lib/studioPipelineDraftsApi.ts`, `api/studio-notifications.ts`; ws `/ws/studio/pipeline-runs/{id}/live/` | `studio`, `studio_pipelines`, `studio_runs`, `studio_agents`, `studio_skills`, `studio_mcp`, `studio_notifications` | Пиксель |
| P1 | Chat `/chat` | `api/assistant-chat.ts`; ws `/ws/operator/{chatId}/` | `chat` | Пиксель |
| P1 | Mars `/mars`, `/mars/runs/:runId` | `api/mars.ts`; ws `/ws/mars/runs/{id}/live/` | `mars` | Пиксель |
| P1 | Kubernetes `/kubernetes`, `/kubernetes/clusters/:clusterId`, `/kubernetes/fleet`, `/kubernetes/devtron`, `/kubernetes/admin` | `api/kubernetes.ts`, `api/kubernetes-actions.ts`, `api/kubernetes-ops-extra.ts`, `api/kubernetes-admin*.ts`; ws `/ws/kubernetes/admin/{logs,watch,exec,port-forward}/{session}/` | `kubernetes` (+ `ready_for_sidebar` с бэка) | Пиксель |
| P2 | Settings `/settings/{appearance,readiness,limits,ai,ai-connections,access,users,groups,permissions,sso,memory,audit,notifications,kubernetes,plugins}` | `api/settings.ts`, `api/aiProviders.ts`, `api/projects.ts` | `settings`, `ai_connections_personal`, `ai_connections_admin`; `kubernetes`/`plugins` staffOnly | Пиксель |
| P2 | Plugins `/settings/plugins`, `/plugins/:pluginId/:pageId`, `/marketplace` → redirect | `api/plugins.ts`, `frontend/src/plugins/*` (PluginPageHost) | `plugins` staffOnly | Пиксель |
| P2 | Monitoring insights `/monitoring/insights` | `api/monitoring.ts`, `api/monitoring-insights.ts`; ws `/ws/monitoring/live/` | `dashboard` staffOnly | Пиксель |

Гейты как сейчас: `FeatureGate feature=…`, `staffOnly`, `aiRoutingOnly`,
`requiresKubernetesReadiness`; логика — `frontend/src/lib/featureAccess.ts` +
`lib/navigation.ts`. Новых capability ради UI не добавляем.

Primary nav (источник: `frontend/src/lib/navigation.ts`):

- `/dashboard`, `/servers`, `/kubernetes`, `/agents`, `/automation`, `/chat`, `/studio`, `/mars`, `/settings/plugins`, `/monitoring/insights`, `/settings`

Отдельно решить (см. §9): `lib/api-demo*` — demo-fallback при недоступном бэке
(нужен для GitHub Pages `VITE_BASE`). Это не операционная функция → в v3 по умолчанию **не переносим**.

WS-каналы (все через `buildWsBase()` → `/ws/...`, cookie-auth):

- `/ws/servers/{id}/terminal/`
- `/ws/studio/pipeline-runs/{id}/live/`
- `/ws/mars/runs/{id}/live/`
- `/ws/monitoring/live/`
- `/ws/operator/{chatId}/`
- `/ws/kubernetes/admin/{logs|watch|exec|port-forward}/{sessionId}/?...`

Мост проверяет список по бэку (`routing.py`/consumers) и дополняет точными REST endpoint'ами
в отдельном `API_MATRIX.md`.

### Фаза 2 — Shell + auth (Пиксель)

- [x] layout: sidebar / topbar минимальные
- [x] theme tokens dark/light
- [x] login + session gate
- [x] feature-access как сейчас (без новых «capabilities» ради UI)
- [x] ноль нейрослоп-копирайта на login/dashboard
- [x] FirstRunReadinessGate → `/settings/readiness`

### Фаза 3 — P0 функциональность (Пиксель, стыки Мост)

- [x] Servers list + create/delete/test
- [x] Terminal/ws (`/servers/:id/terminal`, hub)
- [x] Files panel (list/read/write/mkdir/delete, textarea editor)
- [x] `docs/frontend-v3/API_MATRIX.md` (P0 endpoints)

Зависимости P0 установлены: `react-router-dom` 7, `@tanstack/react-query` 5, `@xterm/xterm` 6 + fit/search/web-links/unicode11.

Не тащить в P0: `@xyflow/react`, `@codemirror/*`, `recharts`, `framer-motion`, `embla`.

### Фаза D — UI design system (Пиксель)

См. [`DESIGN.md`](DESIGN.md) (кратко) и полную спецификацию:

| Документ | Назначение |
| --- | --- |
| [`UI_SPEC.md`](UI_SPEC.md) | Токены, примитивы, оверлеи, паттерны, копирайт, a11y |
| [`MODALS_REGISTRY.md`](MODALS_REGISTRY.md) | Реестр всех Dialog/Drawer/Confirm (~55 ID) |
| [`screens/`](screens/) | Поэкранные спеки 00–14 (кнопки, поля, статусы, anti-slop) |

- [x] DESIGN.md + CSS tokens + IBM Plex Sans / JetBrains Mono
- [x] примитивы: Button, Badge/StatusDot, PageHeader, DataTable, EmptyState/InlineError, PageShell
- [x] shell: секции nav, иконки, inset active bar, sticky topbar `webterm / section`
- [x] экраны P0: Login (split), Готовность (summary cards + filter + severity checklist), Панель/Серверы, Терминал + Files
- [x] статусы как Badge; mono на host/path/CLI; primary CTA
- [x] UI pass 2: denser surfaces, brand mark, checklist rail, login hero
- [x] **UI_SPEC + MODALS_REGISTRY + screens/00–14** (детальный план до кнопки/модалки)

### Фаза 4 — P1/P2 (Пиксель)

- [x] **Рестайл v2:** `index.css` под токены UI_SPEC §2 (light default, accent `#2563eb`, surface, soft-тона, shadow), `theme.tsx` default → `light`
- [x] Рестайл примитивов + Card, Tabs, KpiCard, Field, Avatar, ForbiddenState, IconButton, Skeleton
- [x] Оверлеи: Dialog, ConfirmDialog, PromptDialog, Drawer, Toast, DropdownMenu, Tooltip
- [x] Рестайл P0 (shell, login, dashboard, servers, terminal, readiness) под v2; FeatureGate → ForbiddenState
- [x] Полный SRV-01 (auth_method / key / sudo) + mobile sidebar Drawer
- [x] P1: Agents list/create + Agent Run page (`/agents/run/:runId`)
- [x] P1: Automation catalog (`/automation`) — list/create/delete
- [x] P1: Playbook editor (`/automation/playbooks/:id`) — YAML draft save + publish
- [x] P1: Playbook run wizard + results (`…/run`, `/automation/runs/:runId`)
- [x] P1: Studio hub (`/studio`) — pipelines list/create/delete
- [x] P1: Chat hub (`/chat`) — threads + HTTP compose (без full WS stream)
- [x] P1: Chat WS streaming + confirm/cancel actions
- [x] P1: MARS wizard + run monitor (`/mars`, `/mars/runs/:runId`)
- [x] P1: Kubernetes cockpit (`/kubernetes`) — overview + diagnose drawer
- [x] P1: Kubernetes cluster detail + fleet (`/kubernetes/clusters/:id`, `/fleet`)
- [x] P1: Settings account + AI connections
- [x] P1: Settings access users + audit journal
- [x] P1: Studio pipeline editor (list-based nodes, save/run) `/studio/pipelines/:id`
- [x] P1: Studio hubs — runs / agents / skills / mcp
- [x] P1: Settings groups + permissions + SSO
- [x] P1: Kubernetes admin sessions + Devtron
- [x] P1: Monitoring insights
- [x] P1: Settings AI / models routing
- [x] P1: Studio notifications + SVG graph canvas
- [x] P1: Settings limits/budgets
- [x] P1: Studio run detail `/studio/runs/:id`
- [x] P1: MARS workspace create/delete
- [ ] Плагины — отложено по запросу (PlaceholderPage)
- [ ] Держать UI_SPEC / screens в синхроне при переносе экранов


### Фаза 5 — Приёмка

- ручной смок (Тест чеклист + пользователь): auth → first-run gate → servers → terminal/ws → files
- смок через **оба** пути входа: форма `/login` и бэк-редирект (`FRONTEND_APP_URL` → 8081), т.к. SSO/domain-auth идёт через редирект бэка
- `npm run build` (`tsc -b` + vite) и `npm run lint` — зелёные
- нет нейрослоп-бейджей (не «скрыты CSS», а удалены)
- Semgrep короткий по `frontend-v3` (Страж)
- `FRONTEND_APP_URL=http://127.0.0.1:8081` в корневом `.env` (LU); CORS/CSRF для 8081 в debug уже дефолт
- решение: заменить `frontend/` или держать v3 основной; учесть `docker/frontend.Dockerfile` (`COPY frontend/ ./`) — при замене менять путь в Dockerfile, а не только папку

---

## 6. Что выкидываем с UI сразу (примеры)

- бесполезные блоки на главной (декор-статистика / «умные» сводки без действия)
- поиск и дата на главной, если не ведут к реальному фильтру/данным
- бейджи вроде «ПРОБЛЕМ: N» без реального источника
- маркетинговые/AI-тексты в кнопках и пустых состояниях

Замена: короткий заголовок раздела + список/таблица + первичные действия.

---

## 7. Skills / MCP — кто чем пользуется

| Кто | Инструмент | Зачем |
| --- | --- | --- |
| Пиксель | Superdesign, frontend-design, Context7 | UI/токены/компоненты |
| Пиксель | Wonder/Mobbin (после auth) | референсы минимализма |
| Мост / Ядро | Context7 | контракты/доки Django |
| Тест | Playwright MCP | только по команде пользователя |
| Страж | Semgrep | скелет + перед приёмкой |
| LU | Docker/compose, порты, env, ветка | запуск |
| Все | Github MCP | сейчас broken (`failed_to_load`); нужен PAT-вариант |

---

## 8. Критерии готовности скелета (Фаза 0)

- `npm run dev` поднимает `http://127.0.0.1:8081`
- proxy `/api/auth/session/` доходит до бэка `9000`
- тёмный фон по умолчанию, без Vite/React demo chrome
- в репо нет секретов `.env`

---

## 9. Решения по открытым вопросам (2026-09-13)

1. Dual-run до приёмки → потом `frontend-v3` становится основным.
2. i18n: сначала **ru**.
3. storybook/e2e — **после P0**.
4. Github PAT — отдельно, не блокер UI.
5. Dashboard: короткий заголовок + рабочие сущности (servers), без overview-карточек.
6. CSRF/CORS для `http://127.0.0.1:8081` и `localhost:8081` — в debug уже дефолт бэка (`web_ui/settings/security.py`), для prod — через env. Ничего в коде бэка менять не нужно.
7. Auth: session/cookie как сейчас — без localStorage для токенов/SSH-ключей (в `frontend/src/api/*` localStorage сейчас не используется — держим так).
8. `FirstRunReadinessGate` → `/settings/readiness` — часть P0, иначе после логина на чистом бэке некуда попасть.
9. Demo-fallback (`lib/api-demo*`, `VITE_BASE` для GitHub Pages) в v3 **не** переносим; если понадобится демо — отдельным решением.
10. `/servers/hub` и `/servers/:id/terminal` рендерят один `TerminalPage` — в v3 тоже один компонент, два маршрута.

---

## 10. Ближайшие шаги

1. ~~LU: добить Фазу 0~~ — сделано.
2. ~~Пиксель: Фаза 2–3 (shell/auth + servers/terminal/files)~~ — сделано.
3. ~~Пиксель: Фаза D (UI design system + P0 screens)~~ — сделано (`DESIGN.md`).
4. ~~Пиксель: детальная UI-спека (UI_SPEC + MODALS_REGISTRY + screens/00–14)~~ — сделано.
5. Пользователь: ручной смок UI на `:8081` (login → readiness → servers → terminal).
6. Пиксель: Фаза 4 — P1/P2 экраны **по `screens/*.md`** + оверлеи (Dialog/Drawer/Toast).
7. Мост: дополнить `API_MATRIX.md` REST для P1.
8. Автотесты — только по запросу.

---

## 11. UI-спецификация (2026-09-13)

Пакет документов для Фазы 4 (реализация по спеке, не «на глаз»):

- [`UI_SPEC.md`](UI_SPEC.md) — дизайн-система **v2 (corporate B2B, light, accent `#2563eb`)**
- [`MODALS_REGISTRY.md`](MODALS_REGISTRY.md) — ~55 диалогов
- [`screens/README.md`](screens/README.md) — индекс 00–14 + **таблица соответствия v1 → v2** для визуальных формулировок
- Текущий `frontend-v3/src/index.css` — ещё v1 (тёмный ч/б); переписывается в Фазе 4

Покрытие инвентаря старого `frontend/`: каждый экран из App.tsx имеет файл в `screens/`; каждый диалог из инвентаря — строку в `MODALS_REGISTRY` или пометку «убрано» в конце реестра / в § anti-slop экрана. Чеклист: [`COVERAGE.md`](COVERAGE.md).

---

## 12. Ревизия плана (2026-09-13, аудит по коду)

Что исправлено относительно первой версии:

- Proxy v3 **не** «как сейчас»: нет проброса cookie/domain-auth заголовков на HTTP и WS upgrade → добавлено в Фазу 0.
- Матрица экранов расширена по `frontend/src/App.tsx`: были пропущены `/servers/hub`, `/servers/:id/terminal`, `/agents/run/:runId`, `/studio/pipeline/*`, `/kubernetes/{admin,clusters,fleet,devtron}`, `/mars/runs/:runId`, `/plugins/:pluginId/:pageId`, `/marketplace`, 15 дочерних `/settings/*`, redirect'ы `/`, `/admin`, `/dashboard/admin`, `*`.
- Добавлен `FirstRunReadinessGate` как P0-зависимость.
- API-модули привязаны к реальному пути `frontend/src/api/*.ts` (в плане подразумевался `lib/api`, которого нет); добавлены пропущенные `terminal-preferences`, `linux-ui`, `server-memory`, `playbook-*`, `kubernetes-admin*`, `monitoring-insights`, `aiProviders`, `projects`.
- WS-каналы выписаны из `frontend/src/lib/api.ts` вместо «`/ws/…`».
- FeatureGate-фичи выписаны по маршрутам; зафиксировано «без новых capability».
- CORS/CSRF для 8081: уже в дефолте бэка для debug — пункт из «сделать» переведён в «проверить env для prod».
- `FRONTEND_APP_URL` — это редиректы бэка, а не CORS; отмечено ограничение dual-run.
- Зависимости P0 перечислены (в скелете только react).
- Приёмка: добавлены `build`/`lint`, вход через бэк-редирект, путь замены `docker/frontend.Dockerfile`.
- Открытые вопросы: demo-fallback, README-шаблон, untracked `icons.svg`.