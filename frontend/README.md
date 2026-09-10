# WebTerm Frontend Next

Новый интерфейс WebTerm: React + TypeScript + Vite, единая дизайн-система Light/Dark, Django session/CSRF, типизированные доменные API и общий WebSocket transport. Реализация создана по backend-контрактам, без использования предыдущего frontend.

## Локальная работа

Нужны Node 22.12+ или 24+, Python 3.12 с backend dependencies, PostgreSQL и Redis из существующего окружения проекта.

```powershell
cd C:\WebTrerm\frontend
npm ci
$env:WEBTERM_BACKEND_URL='http://127.0.0.1:9000'
npm run dev
```

Frontend открывается на `http://127.0.0.1:8090`. Vite проксирует `/api/`, `/servers/api/`, `/ws/` в Django. Также поддерживается существующий `VITE_DJANGO_URL` для Docker. Используйте одну origin для браузера и API; backend должен разрешать её в CSRF trusted origins. Frontend не содержит demo-login, фиктивных production данных или встроенных учётных данных.

Адрес backend можно сохранить в игнорируемом `frontend/.env.development.local`: `WEBTERM_BACKEND_URL=http://127.0.0.1:9001` для существующего QA backend. После этого достаточно `npm run dev`; переменные текущего PowerShell имеют приоритет над файлом. Без локальной настройки используется порт backend 9000. На машине текущей UX-проверки локальный файл настроен на QA backend 9001.

Для корпоративного DNS задайте `WEBTERM_FRONTEND_ALLOWED_HOSTS=webterm.example.com` (несколько имён через запятую). Docker Compose по умолчанию берёт список из `ALLOWED_HOSTS`. Проверка Host остаётся включённой, `*` не принимается. Native localhost/IP работают без дополнительной настройки.

Backend запускается из корня существующим `.venv`/`.env`. Для native Windows рядом с Docker PostgreSQL используется `POSTGRES_HOST=127.0.0.1`, `POSTGRES_PORT=5433`. Команда: `.venv\Scripts\daphne.exe -b 127.0.0.1 -p 9000 web_ui.asgi:application`. Redis должен быть доступен из выбранного backend settings profile. Готовность: `/api/ready/`.

На машине разработки этой задачи зависимости уже установлены: `frontend/node_modules` является junction на `D:\webterm-frontend-runtime\node_modules` из-за свободного места диска C. Для использования приложения переустановка не требуется. Это локальная оптимизация, а не требование репозитория; чистый clone использует обычный `npm ci`.

## Проверки

```powershell
npm run typecheck
npm run lint -- --max-warnings 0
npm run test:coverage
npm run build:budget
npm run build-storybook
```

`npm run storybook` открывает каталог primitives/состояний на 6006. Production output: `dist/`; сборка содержит lazy chunks для terminal, pipeline editor, AI, Kubernetes и governance. Бюджеты gzip контролируются `scripts/bundle-budget.mjs`, результат — `artifacts/bundle-budget.json`.

## Изолированные сквозные тесты

Тесты используют отдельную PostgreSQL базу `webterm_frontend_qa_20260902`, случайные учётные данные в игнорируемом `tests/.auth/`, отдельные cookies и локальный SSH/SFTP fixture. Fixture никогда не запускает shell-команды на компьютере: он реализует контролируемые ответы протокола и файловую систему в QA-каталоге. Production database не используется.

Из корня репозитория, в отдельных терминалах:

```powershell
$env:PYTHONPATH='C:\WebTrerm;C:\WebTrerm\frontend\tests\backend'
$env:POSTGRES_HOST='127.0.0.1'
$env:POSTGRES_PORT='5433'
.venv\Scripts\python.exe frontend/tests/backend/prepare.py
# После подготовки, отдельный процесс:
.venv\Scripts\python.exe frontend/tests/backend/ssh_fixture.py
# Ещё один процесс с теми же PYTHONPATH и PostgreSQL env:
$env:DJANGO_SETTINGS_MODULE='qa_settings'
.venv\Scripts\daphne.exe -b 127.0.0.1 -p 9001 web_ui.asgi:application
```

В `frontend/`:

```powershell
$env:WEBTERM_BACKEND_URL='http://127.0.0.1:9001'
npm run dev -- --port 8091
# В другом терминале:
npx playwright install chromium
npm run test:e2e
```

На этой машине Chromium уже в `D:\webterm-frontend-runtime\browsers`; перед запуском тестов задайте `PLAYWRIGHT_BROWSERS_PATH` этим путём. Тесты не должны работать против произвольного production URL. Не перезапускайте `prepare.py` при работающем SSH fixture: подготовка меняет случайные пароли; сначала завершите только свои QA-процессы, затем заново запустите их.

Playwright проверяет реальную аутентификацию/CRUD/ACL/SFTP/SSH/automation на Django. Kubernetes E2E используют явно локальные test-only contract fixtures для сценариев dry-run и раздельных approvals, поскольку live cluster для задачи не подключён. Эти fixtures не входят в приложение.

`tests/.auth`, test-results, reports, node_modules и artifacts исключены из Git; `.dockerignore` исключает QA credentials из build context. Не публикуйте трассы с реальными секретами. CI автоматически поднимает изолированные PostgreSQL/Redis/SSH/backend/frontend и запускает те же проверки.

## Структура

- `src/app`, `layouts`: auth, theme, routing, shell, command palette.
- `src/components/ui`, `styles`: общие компоненты, tokens, доступные dialogs/tables/forms.
- `src/api`: контракты Django, ошибки, CSRF, downloads; никакого прямого fetch в UI-функциях.
- `src/realtime`: ограниченный reconnect/backoff и cleanup без повтора пользовательских команд.
- `src/features`: infrastructure, automation, kubernetes, intelligence, governance.
- `stories`: каталог компонентов и состояний с переключением Light/Dark.
- `tests`: unit/contract, реальная QA среда, сквозные сценарии.

## Приёмка и развёртывание

Product/IA/permissions/API/realtime inventory и итоговая сверка находятся в `../docs/frontend-next/`. [FINAL_PARITY_REPORT](../docs/frontend-next/FINAL_PARITY_REPORT.md) отделяет проверенные локальные сценарии от внешних интеграций.

Существующий `docker/frontend.Dockerfile` и compose workflow поддерживаются; стандартный release pipeline должен раздавать `dist` с SPA fallback и передавать API/WS в backend через принятую инфраструктуру. Публичное развёртывание не выполнялось. HTTPS, корпоративный IdP, реальные Ansible/GitLab/AI/Kubernetes credentials и нагрузочные проверки требуют отдельного окружения приёмки заказчика.

В backend добавлены совместимый GET участников server group и поле `edges_snapshot` в сериализацию запуска pipeline; исправлено экранирование пути при записи файла через sudo. Отдельные regression tests проверяют ACL, неизменность снимка графа и безопасную обработку пути. Миграций данных для frontend нет; откат — предыдущий frontend deployment artifact. Пользовательские изменения и удаления, существовавшие до начала задачи, сохранены.
