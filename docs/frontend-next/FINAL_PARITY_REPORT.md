# WebTerm Frontend Next — итоговая сверка

> Это отчёт первой технической приёмки. По последующему запросу пользователя выполняется дополнительная последовательная UX-переработка. Её незавершённые страницы и текущий статус указаны в [PAGE_BY_PAGE_UX_REWORK](PAGE_BY_PAGE_UX_REWORK.md); прежний GO не означает завершения этого этапа.

Дата: 2026-09-02. Область: полностью новый frontend к существующему Django backend. Сверка охватывает все 39 групп возможностей из FEATURE_INVENTORY.

## Что является результатом

Новый React/TypeScript frontend в `frontend/`, один App Shell, одна дизайн-система Light/Dark, доменные API, централизованный realtime transport, отдельные lazy bundles. Старые frontend-компоненты, скриншоты, стили и Git-история не использовались. Исходные пользовательские удаления и изменения сохранены.

Рабочая версия подключена к реальному backend на `http://127.0.0.1:8090`. Мутационные проверки выполняются на отдельной базе `webterm_frontend_qa_20260902` через 8091/9001. QA SSH/SFTP fixture слушает 22391 и не исполняет команды на компьютере.

Вердикт: **GO для локальной frontend-приёмки**. На 8090 раздаётся итоговая production-сборка. Внешняя production-приёмка ограничена перечисленными ниже непроверенными интеграциями и не объявляется завершённой.

## Матрица паритета

PASS в таблице означает реализованную frontend-возможность с проверенным контрактом и указанными проверками. Он не утверждает подключение каждого внешнего провайдера. Реальные внешние зависимости перечислены отдельно.

| ID | Статус frontend | Реализация / evidence |
|---|---|---|
| AUTH | PASS | Реальный UI login, CSRF, logout/expiry, сохранение session observer, безопасный return route; API unit + live E2E |
| PROJECTS | PASS | Выбор проекта, membership/role, сброс доменных caches и remount; реальные project API |
| OVERVIEW | PASS | Health/alerts/activity/actions, stale не выдаётся за здоровье; реальные данные 17 серверов, browser QA |
| SERVERS | PASS | Inventory/filter/search/sort/page, create/edit/delete, сохранность secrets; реальный CRUD E2E |
| SERVER_ACCESS | PASS | Capabilities, share/revoke/expiry/context, transfer, strict SHA256 trust; backend payloads, permission checks |
| SERVER_GROUP_OPS | PASS | Роли/участники/revoke, context rules/env/forbidden, server move, durable metadata bulk; backend ACL5 и E2E |
| TERMINAL | PASS | Реальный SSH WS, ввод/вывод, resize, вкладки, reconnect без replay, clipboard, focused mode, disconnect |
| TERMINAL_EDITOR | PASS | Сохранение настроек, nano/vim interception, remote editor/sudo; реальный SSH → editor E2E; AI shared-session events unit |
| SERVER_FILES | PASS | SFTP list/read/write/upload/download/rename/mkdir/chmod/chown/delete, сохранение черновика; реальный write/read-back E2E |
| SERVER_OPS | PASS | Services/processes/logs/docker/network/packages с capabilities и review мутаций; source contract map |
| MONITORING | PASS | Metrics/history/alerts, AI insights/certs/predictions, watcher draft/scan/ack/launch, refresh/thresholds; real list APIs |
| PLAYBOOKS | PASS | Catalog/create/import, YAML/file drafts, revisions/publish/rollback, compatibility, bindings/sharing/export/archive/restore; live authoring E2E |
| PLAYBOOK_RUNS | PASS | Preflight/launch/detail/log/cancel/per-host report; реальные contracts, target selection и capabilities |
| PIPELINES | PASS | Manifest-driven canvas/property editor, handles, save conflicts, structured issues → nodes, templates/clone/export; real edit/validate E2E |
| STUDIO_RUNS | PASS | History, readonly canvas сохранённого графа со статусами и выбором узла, traces, streamed events, cancel/resume/retry/approval; реальный QA logic run и immutable-snapshot API test |
| DRAFTS | PASS | Composition/review/compile/launch, phases/errors сохраняются; реальные Studio contracts |
| SCHEDULES | PASS | Schedule/webhook/monitoring triggers, execution profile, токены скрыты; реальные Studio contracts |
| SKILLS | PASS | CRUD/files/validation/workflow/sharing; grant round-trip сохраняет намерение backend |
| KUBERNETES | PASS | Provider → cluster → namespace → resource, logs/events/actions; contract E2E drilldown |
| K8S_ADMIN | PASS | Session request/other-user approval/breakglass, native discovery, dry-run proof invalidation, typed apply/patch/scale/delete, audit/recordings; E2E proofs/approval separation |
| K8S_REQUESTS | PASS | Action request queue, approvals, controlled execution, verification; typed backend contracts |
| K8S_DELIVERY | PASS | Helm ownership, Fleet/Devtron, diagnosis drafts; typed backend contracts |
| AGENTS | PASS | Agents/config/run/stop, plans/reports/artifacts/tools/approval; real catalog routes + state tests |
| AGENT_PROFILES | PASS | Studio AgentConfig CRUD, explicit sharing and capabilities |
| AGENT_OPERATIONS | PASS | Duty briefs, plan task edit/refine, six schedule modes, dispatch/stale cleanup |
| CHAT | PASS | Chat history/rename/context/playbook/servers, turn_snapshot, stream tools and confirmations; reducer/contract tests |
| MCP | PASS | Catalog/config/tools/status/permissions; explicit preservation of sharing semantics |
| MEMORY | PASS | Per-server overview/search/knowledge/snapshots, bulk lifecycle, admin access; real APIs and owner gate |
| MARS | PASS | Interview, editable approved plan, run stream/artifacts; refetch не перезаписывает draft |
| USERS | PASS | CRUD/profile/password/enable/disable, errors retain draft; real governance E2E |
| GROUPS | PASS | Access groups/membership/inherited permissions; real governance E2E |
| PERMISSIONS | PASS | Explicit allow/deny/inherit, effective value/provenance; real precedence tests |
| AUDIT | PASS | Actor/action/target/time/result/detail, filters и pagination; реальные API + a11y |
| USER_ACTIVITY | PASS | Activity/search/detail, active-last-5-min users, AI usage; real QA E2E |
| WORKSPACE_PREFS | PASS | Visibility/column/order/reset, preserves unrelated stored JSON, reload and navigation guard; real QA E2E |
| SETTINGS | PASS | General, LDAP/SSO, limits/readiness, routing, typed sensitive changes; реальные API + a11y |
| AI_CONNECTIONS | PASS | CLI/provider auth/grants/pools/purpose model, auth state/quotas/errors; текущий release flag учитывается |
| PLUGINS | PASS | Catalog/install/settings/lifecycle/private-package workflow с backend capability/feature gates |

## Техническая приёмка

| Gate | Результат |
|---|---|
| TypeScript strict / ESLint | PASS, без ошибок и lint warnings |
| Vitest | 34/34, 10 файлов; meaningful API, realtime, permissions, draft и graph проверки |
| Playwright | 26/26, общий прогон 3.1 min; 22 сценария с реальным Django/QA runtime и 4 Kubernetes contract fixtures |
| Backend regressions | 19/19; group membership ACL, immutable graph snapshot и sudo path quoting; Ruff lint/format PASS |
| Production build + budget | PASS; initial JS gzip 158 748 B, largest chunk 120 153 B, CSS 18 883 B |
| Storybook | PASS; статический каталог Light/Dark, состояния и интерактивные компоненты |
| npm audit | High 0, Critical 0; отдельный fail-closed audit parser test PASS |
| Preview Host allowlist | PASS; корпоративный host 200, посторонний 403, localhost 200 |
| Compose syntax | Оба файла PASS с `config --quiet --no-interpolate`; настоящий production env/deploy не запускался |

Unit coverage по всему новому source: statements 6.67%, lines 6.71%. Он не включает E2E и не является заявлением полного покрытия. Бюджет реакции интерфейса измерен отдельным Chromium сценарием против локального backend; точные значения в `frontend/artifacts/interaction-budget.json`, ограничения 1500 ms для поиска и 5000 ms для перехода.

Контрактные тесты Kubernetes используют локальные fixtures внутри Playwright. Реальные session/ACL/server CRUD/SFTP/SSH/governance/playbook/pipeline проверки используют Django + PostgreSQL. Unit coverage измеряется отдельно и не включает браузерные проверки; низкий процент общего line coverage не выдаётся за полное покрытие продукта.

Browser QA: Light/Dark, 1280×800 laptop, 390×844 navigation, real-data inventory/overview/canvas, dialogs, keyboard focus/search, long table content, file edits. Проверка WCAG2A/AA/2.1AA охватывает 12 рабочих разделов и форму с ошибкой; это автоматизированная проверка, не сертификат соответствия.

## Ограничения backend, сохранённые интерфейсом

- Monitoring thresholds меняются в процессе backend и сбрасываются при рестарте; UI не обещает долговременное сохранение.
- Snapshot restore сначала возвращает подготовленную команду. Фактическая запись выполняется отдельным подтверждённым execute; вывод подготовки не считается восстановлением.
- Staff не заменяет владельца/объектные capabilities. Например, share-видимость pipeline не даёт права запуска вопреки queryset.
- Approval token не берётся из обычного run detail; используется предусмотренный backend канал согласования.
- Active users API возвращает активность за 5 минут, а не управляемые session IDs. Кнопка отзыва таких «сессий» не выдумана.
- Старые значения theme_name не создают каталог тем: используется одна общая Light/Dark система и фиксированная рабочая палитра терминала.

## Границы релизной готовности

Локальная frontend-приёмка и проверка внешней инфраструктуры — разные gates. `/api/ready/` подтвердил PostgreSQL и Redis. Для данной задачи не выполнялись публикация/деплой, production нагрузка, корпоративный IdP login, платная AI/device authorization, реальные GitLab/Ansible и live Kubernetes mutations. Они требуют выделенного окружения и конфигурации конкретного заказчика.

Также не подтверждены end-to-end: AI agent/chat tool execution и Telegram delivery, MARS CLI workspace execution, исполняемые MCP tools, scheduler/memory worker infrastructure, live Kubernetes exec/tunnel/watch/metrics и политика хранения recordings. UI и API-адаптеры для этих сценариев реализованы; результат реального провайдера из fixtures не выводится.

Отсутствие этих внешних проверок не скрыто mock-данными. Production code обращается к backend, показывает feature-disabled/not-configured/permission-denied/error, не объявляет неполученные результаты успехом.

Изменения backend ограничены необходимым GET списка участников группы, сериализацией уже сохраняемого `edges_snapshot` запуска pipeline и исправлением shell quoting пути в существующем elevated file write. Для всех трёх добавлены regression tests. Обнаруженные save races файловых редакторов, сохранность SSH при отмене перехода и download JSON-file handling исправлены в frontend. Подробности: [ROOT_REVIEW_FIXES](research/ROOT_REVIEW_FIXES.md).

Deployment config передаёт разрешённые доменные имена frontend из `WEBTERM_FRONTEND_ALLOWED_HOSTS`, по умолчанию — из `ALLOWED_HOSTS`. Wildcard `*` не отключает Host validation. CI получает native LDAP build dependencies, production bundle/Host gates и сборку Storybook. Полный GitHub Actions run ещё не выполнялся.

## Артефакты и повторение

- `frontend/README.md` — запуск, изолированная QA среда, команды и build.
- `frontend/artifacts/bundle-budget.json`, `interaction-budget.json`, `coverage/` — технические evidence.
- `frontend/artifacts/final-validation.json` — сводка фактически выполненных проверок.
- `frontend/playwright-report/`, `test-results/` — итоговый browser run.
- `docs/frontend-next/research/*_CONTRACTS.md` — endpoint/payload/access детали.
- CI Playwright поднимает свою PostgreSQL/Redis/SSH/Django/Vite среду. Published smoke config существует отдельно и требует URL/credentials целевого deployment.

Откат frontend выполняется заменой build artifact. Пользовательские изменения до задачи не отменяются, migrations данных для frontend не добавлялись.
