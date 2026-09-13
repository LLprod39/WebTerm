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
2. Меняет **только визуал и копирайт**: жёсткий ч/б минимализм в духе эталона до rewrite (`fa00a74`), удобный для Admin/DevOps.
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
| Тема | дефолт **тёмный** ч/б; светлый — переключателем |
| Эталон стиля | `fa00a74` (минимализм), **не** ashita/flow/pulse из DESIGN.md |
| Контракты | session / servers / terminal / ws / files и остальные API — **1:1**, без ломки |
| Тесты | пока ручные; тяжёлый Playwright — только по явной команде |
| Nightly Audit | снаружи команды, не в канале |
| Skills/MCP | Context7, Superdesign, frontend-design, Playwright, Semgrep; Wonder/Mobbin после логина; Github — пока broken |

---

## 3. Принципы UI (анти-нейрослоп)

1. Текст только операционный: что это, что делать, что сломалось.
2. Нет декоративных метрик/бейджей без реального поля API.
3. Нет «приветствий», motivational copy, пустых search/date на главной.
4. Навигация короткая: понятные названия (Servers, Terminal, Settings…), без маркетинга.
5. Плотность под DevOps: таблицы, статусы, действия; воздух минимальный.
6. Светлый режим — тот же layout, только токены цвета.

Если бэк отдаёт поля только под декор — Мост фиксирует список → Ядро чистит точечно (не блокер v3).

---

## 4. Порты и запуск

```text
frontend/     → http://127.0.0.1:8080  (текущий)
frontend-v3/  → http://127.0.0.1:8081  (новый)
backend       → http://127.0.0.1:9000
Postgres/Redis → Docker only
```

Proxy в `frontend-v3` (как сейчас):

- `/api/` → `9000`
- `/servers/api/` → `9000`
- `/ws/` → `9000` (websocket)

Env:

- `VITE_DJANGO_URL=http://127.0.0.1:9000`
- корневой `.env`: `FRONTEND_APP_URL` для v3-сессии при приёмке выставить на `http://127.0.0.1:8081`
- `.env*` **не** коммитить (Страж)

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
- [ ] Vite + React + TS в `frontend-v3/`
- [ ] порт `8081`, proxy → `9000`
- [ ] тёмные ч/б CSS-токены + shell-заглушка
- [ ] `.env.example`, `.gitignore`
- [ ] коммит скелета

### Фаза 1 — Матрица экранов ↔ API (Пиксель + Мост)

Таблица маршрутов текущего фронта → API-модули → приоритет переноса.

| Приоритет | Экран / path | API / канал | Owner UI |
| --- | --- | --- | --- |
| P0 | Login `/login` | `api/auth.ts`, session | Пиксель |
| P0 | Dashboard `/dashboard` | auth session + минимум без декор-метрик | Пиксель |
| P0 | Servers `/servers` | `api/servers.ts` | Пиксель |
| P0 | Terminal (server detail) | ws `/ws/…`, terminal prefs | Пиксель + Мост |
| P0 | Files | `api/server-files.ts` | Пиксель |
| P1 | Agents `/agents`, run/config | `api/agents.ts` | Пиксель |
| P1 | Automation `/automation` | playbooks / workspace API | Пиксель |
| P1 | Studio `/studio/*` | `api/studio.ts`, runs, mcp, skills | Пиксель |
| P1 | Chat `/chat` | `api/assistant-chat.ts` | Пиксель |
| P1 | Mars `/mars` | `api/mars.ts` | Пиксель |
| P1 | Kubernetes `/kubernetes/*` | `api/kubernetes*.ts` | Пиксель |
| P2 | Settings `/settings/*` | `api/settings.ts`, users/groups/permissions | Пиксель |
| P2 | Plugins `/settings/plugins` | `api/plugins.ts` | Пиксель |
| P2 | Monitoring insights | `api/monitoring*.ts` | Пиксель |
| P2 | Notifications settings | `api/studio-notifications.ts` | Пиксель |

Primary nav (источник: `frontend/src/lib/navigation.ts`):

- `/dashboard`, `/servers`, `/kubernetes`, `/agents`, `/automation`, `/chat`, `/studio`, `/mars`, `/settings/plugins`, `/monitoring/insights`, `/settings`

Дочерние studio: `/studio`, `/studio/drafts`, `/studio/skills`, `/studio/mcp`, `/studio/agents`, `/studio/runs`, `/studio/notifications`.

Мост дополняет точными endpoint/ws путями в этом же файле (секция ниже или отдельный `API_MATRIX.md`).

### Фаза 2 — Shell + auth (Пиксель)

- layout: sidebar / topbar минимальные
- theme tokens dark/light
- login + session gate
- feature-access как сейчас (без новых «capabilities» ради UI)
- ноль нейрослоп-копирайта на login/dashboard

### Фаза 3 — P0 функциональность (Пиксель, стыки Мост)

Servers → Terminal/ws → Files.  
Логика 1:1 с текущего клиента; визуал новый.

### Фаза 4 — P1/P2 (Пиксель)

Остальные разделы по матрице.  
Параллельно вычищать копирайт/навигацию.

### Фаза 5 — Приёмка

- ручной смок (Тест чеклист + пользователь): auth → servers → terminal/ws → files
- нет нейрослоп-бейджей (не «скрыты CSS», а удалены)
- Semgrep короткий по `frontend-v3` (Страж)
- CORS/CSRF: `FRONTEND_APP_URL=http://127.0.0.1:8081` (LU)
- решение: заменить `frontend/` или держать v3 основной

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

## 9. Открытые вопросы (на обсуждение)

1. После приёмки: `frontend-v3` становится основным (`frontend/`), или долгий dual-run?
2. i18n: сразу ru/en как сейчас, или сначала один язык (ru)?
3. Нужен ли перенос storybook/e2e в v3 на старте, или только после P0?
4. Github: ставим PAT-коннектор или ждём починки официального плагина?

Правки к плану — только через обсуждение в канале WebTerm.

---

## 10. Ближайшие шаги

1. LU дописывает скелет `8081` + коммит.
2. Команда ревьюит этот MD (вопросы/правки сюда).
3. Пиксель стартует Фазу 1–2 (матрица детализация + shell/auth).
4. Мост уточняет ws/API paths для P0.
5. Пользователь тыкает руками; сложные автотесты — по запросу.