# API contract map

Проверено по текущему backend, 2026-09-02. Карта описывает новый frontend; предыдущие frontend-файлы, интерфейс и история не использовались.

## Общий транспорт

- Django session cookie, `credentials: include`; CSRF берётся из `GET /api/auth/csrf/` и передаётся в `X-CSRFToken` для изменений. После login/logout CSRF обновляется.
- `APIContractMiddleware` сохраняет поля объектных ответов на верхнем уровне. Чистая обёртка `{success:true,code:"ok",data:[...]}` распаковывается API-клиентом. Объекты, содержащие собственное поле `data`, не распаковываются произвольно.
- HTTP 200 с `success:false` считается ошибкой. Подробности ошибки сохраняются для host-key challenge, validation issues и conflict handling. HTML/login redirect, 401, 403, 409, 429, сеть и timeout различаются.
- GET ограничен 45 секундами, изменение — 180 секундами; после timeout изменения интерфейс просит сначала проверить результат, поскольку сервер мог завершить операцию. Изменения автоматически не повторяются.
- При выходе/смене пользователя отменяются запросы и удаляются данные предыдущей сессии. При смене проекта очищаются доменные query caches и перемонтируется рабочая область.
- Файлы скачиваются как Blob; upload использует FormData. Секреты не сохраняются в localStorage и не заполняются из скрытых backend credentials.

## Session и инфраструктура

| API | Методы и данные | UI / важная семантика |
|---|---|---|
| `/api/auth/session/` | GET `{authenticated,user}` | SessionUser содержит features, permission_sources, staff, active_project |
| `/api/auth/login/`, `logout/` | POST username/password/auth_mode; POST logout | Реальная локальная/корпоративная аутентификация; return route |
| `/servers/api/frontend/bootstrap/` | GET servers/groups/stats/recent_activity | Inventory, exact server search, group filters; list и detail имеют разные типы |
| `/servers/api/create/` | POST SSH identity, auth secret, group, context, network | `{server_id}`; пароль/ключ передаётся только при заданной замене |
| `/servers/api/{id}/get/` | GET ServerDetail | `is_shared_server`, `can_edit`, capabilities; не подменяются полями списка |
| `/servers/api/{id}/update/`, `delete/` | POST partial fields; POST delete | `sudo_auth_mode`: none/nopasswd/stored_password; удаление с вводом имени |
| `/servers/api/{id}/test/` | POST; при enrollment expected_host_key_fingerprint/enroll_host_key/replace_host_key | Первый ключ и ротация требуют сверки SHA256 и явного подтверждения; автоматического trust нет |
| `/servers/api/{id}/shares/`, `share/`, `shares/{share}/revoke/`, `transfer-owner/` | GET, POST | Терминал/команды/чтение/запись, expiry, shared context; передача владельца подтверждается отдельно |
| `/servers/api/groups/*` | Create/update/delete, members, context, servers, bulk | Участники и роли, context rules, группировка серверов, durable metadata operations; см. TERMINAL_GROUPS_IMPLEMENTATION |
| `/servers/api/{id}/files/` | GET path → path/parent_path/entries | SFTP browser; capabilities.read_files/write_files |
| `/servers/api/{id}/files/read/`, `write/` | POST path, content для write; elevate/sudo_password при необходимости | `{file:{path,content,size,encoding}}`; пароль sudo только в body, несохранённый текст защищён при закрытии |
| `/servers/api/{id}/files/upload/`, `download/` | FormData files/path; POST path → Blob | Фактическая запись/скачивание, ошибки не выдаются за файлы |
| `/servers/api/{id}/files/{mkdir,rename,chmod,chown,delete}/` | POST path и параметры операции | Опасные удаления подтверждаются, каталог/файл различаются |
| `/servers/api/{id}/execute/` | POST command → `{output:{stdout,stderr,exit_code}}` | Просмотр команды до отправки, вывод и exit code |
| `/api/terminal/preferences/` | GET/PATCH font_size/font_family/line_height/cursor_style/cursor_blink/scrollback/intercept_editors | Пользовательские настройки терминала; одна палитра терминала, без каталога тем |
| `/ws/servers/{id}/terminal/` | ready/status/output/error/exit; connect/input/resize/disconnect/ping | Разделение SSH и transport state, вкладки, reconnect, no input replay |
| тот же terminal WS | editor_intercept + set_editor_intercept; ai_* и agent_* | nano/vim → remote editor; помощник использует существующий SSH-сеанс, approvals/replies/stop/report |
| `/servers/api/monitoring/dashboard/` | GET servers/alerts/summary/recent_activity/meta | Stale и unknown не считаются подтверждённым здоровьем |
| `/servers/api/monitoring/*`, `health/*`, `alerts/*` | History/check/refresh/resolve + live updates | Метрики, watcher findings, acknowledgements, remediation drafts, thresholds; детали в SERVER_OPERATIONS_CONTRACTS |

## Доменные контракты

Эти документы содержат endpoint-by-endpoint таблицы, payload, ownership и особенности backend:

| Область | Контракт | Реализация API |
|---|---|---|
| Playbooks, revisions, compatibility, import/export, bindings, preflight, runs | [AUTOMATION_CONTRACTS](research/AUTOMATION_CONTRACTS.md) | `src/api/automation.ts` |
| Studio pipelines, manifest schemas, drafts, triggers, skills, approvals | [AUTOMATION_CONTRACTS](research/AUTOMATION_CONTRACTS.md) | `src/api/automation.ts` |
| Agents, operator chat, plans, scheduling, memory, MCP, MARS, profiles | [INTELLIGENCE_CONTRACTS](research/INTELLIGENCE_CONTRACTS.md) | `intelligence.ts`, `agent-profiles.ts` |
| Kubernetes providers, inventory, sessions, requests, delivery, mutation proofs | [KUBERNETES_CONTRACTS](research/KUBERNETES_CONTRACTS.md) | `kubernetes.ts` |
| Users/groups/permissions, projects, audit, settings, AI providers, plugins | [GOVERNANCE_CONTRACTS](research/GOVERNANCE_CONTRACTS.md) | `governance.ts` |
| Linux operations, knowledge, snapshots, monitoring/watchers | [SERVER_OPERATIONS_CONTRACTS](research/SERVER_OPERATIONS_CONTRACTS.md) | `server-operations.ts`, `monitoring-extras.ts` |
| Terminal AI and server group membership/bulk | [TERMINAL_GROUPS_IMPLEMENTATION](research/TERMINAL_GROUPS_IMPLEMENTATION.md) | `terminal-ai.ts`, `server-groups.ts` |

## Совместимость и границы

Необходимые совместимые расширения backend: GET участников server group с owner/admin ACL и поле `edges_snapshot` в сериализации pipeline run. Список участников нужен для отображения действующих grants и их отзыва; сохранённые связи нужны для точного отображения графа конкретного запуска после изменения pipeline. Оба контракта покрыты regression tests. Дополнительно исправлено экранирование пути при существующей записи файла через sudo: путь передаётся как shell-аргумент, а не исполняемый синтаксис. Тесты проверяют пробелы и метасимволы без удалённого выполнения. Существующие контракты совместимы, данные не мигрировались.

Backend constraints сохраняются: snapshot restore сначала готовит команду, а не восстанавливает файл; monitoring thresholds временные для процесса; разрешение staff не заменяет object ownership; approval tokens отсутствуют в обычной сериализации run; shared visibility некоторых объектов шире edit/run ACL. Интерфейс учитывает это явно. Реальная готовность внешнего Kubernetes/AI/LDAP/GitLab/Ansible runtime проверяется отдельно от соответствия frontend контракту.
