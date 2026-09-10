# Intelligence и Kubernetes: карта взаимодействий для последовательной UX-проверки

## Область и статус

Это инвентаризация **текущего нового frontend и Django backend**. Старый frontend, Git history, браузер и E2E в этом этапе не использовались. Product source не менялся. Ни одна строка ниже не означает, что страница визуально проверена или операция выполнена. Таблицы описывают доступные в исходниках ветви интерфейса, условия их появления и данные, которые необходимо подготовить перед очередью страниц.

Маршруты: `frontend/src/features/intelligence/index.tsx`, `frontend/src/features/kubernetes/routes.tsx`. API: `frontend/src/api/{intelligence,agent-profiles,kubernetes,kubernetes-workflows,kubernetes-describe}.ts`. Подробные HTTP/WS контракты: [INTELLIGENCE_CONTRACTS.md](INTELLIGENCE_CONTRACTS.md), [KUBERNETES_CONTRACTS.md](KUBERNETES_CONTRACTS.md).

## 1. Все маршруты

| ID | Маршрут | Страница / вход | Route guard |
|---|---|---|---|
| I01 | `/intelligence/profiles` | Профили агентов для AI-узлов pipelines | `studio_agents` |
| I02 | `/intelligence/agents` | Агенты инфраструктуры | `agents` |
| I03 | `/intelligence/agents/:id` | Конфигурация агента и история запусков | `agents`, принадлежащий пользователю агент |
| I04 | `/intelligence/runs/:id` | Выполнение, план и доказательства | `agents`, принадлежащий пользователю запуск |
| I05 | `/intelligence/chat` | Новый диалог оператора; создаётся при отправке | `chat` |
| I06 | `/intelligence/chat/:id` | История, текущий ответ, действия и материалы | `chat`, собственный диалог |
| I07 | `/intelligence/mcp` | Подключения MCP | `studio_mcp` |
| I08 | `/intelligence/memory` | Память выбранного сервера | `servers`; backend дополнительно требует владельца сервера |
| I09 | `/intelligence/mars` | Проектные задачи MARS | `mars` |
| I10 | `/intelligence/mars/sessions/:id` | Условия, план и запуск MARS | `mars`, собственная session |
| I11 | `/intelligence/mars/runs/:id` | Результат и проверка MARS | `mars`, собственный run |
| K01 | `/infrastructure/kubernetes` | Кластеры | `kubernetes` |
| K02 | `/infrastructure/kubernetes/clusters/:id` | Инвентарь кластера | `kubernetes` |
| K03 | `/infrastructure/kubernetes/clusters/:clusterId/namespaces/:id` | Namespace и связанные ресурсы | `kubernetes` |
| K04 | `/infrastructure/kubernetes/resources/:kind/:id` | Snapshot нагрузки / Pod / сети | `kubernetes` |
| K05 | `/infrastructure/kubernetes/readiness` | Готовность и возможности | `kubernetes` |
| K06 | `/infrastructure/kubernetes/providers` | Провайдеры Rancher / Devtron | `kubernetes` + `staff` |
| K07 | `/infrastructure/kubernetes/sessions` | Выдача и согласование доступа | `kubernetes`; режимы дополнительно по capabilities |
| K08 | `/infrastructure/kubernetes/explorer/:sessionId` | Live-ресурсы в сессии | `kubernetes`, собственная active session, provider/RBAC |
| K09 | `/infrastructure/kubernetes/activity` | Admin-действия, записи и аудит | `kubernetes`; `all` и review дополнительно ограничены |
| K10 | `/infrastructure/kubernetes/requests` | Отдельные заявки на изменение | `kubernetes` |
| K11 | `/infrastructure/kubernetes/requests/:id` | Согласование, исполнение и проверка заявки | `kubernetes`, доступ к request; переходы дополнительно staff/policy |
| K12 | `/infrastructure/kubernetes/delivery` | Helm, Fleet, Devtron | `kubernetes` |
| K13 | `/infrastructure/kubernetes/delivery/:kind/:id` | Detail Fleet или Devtron | `kubernetes`; штатные kind: `fleet`, `devtron` |

K03 и K04 используют один `InventoryDetailPage`. В K04 ожидаются backend kind `workloads`, `pods`, `network`; нормализованный `app_…` не превращается в ссылку на несуществующий workload. K07 принимает `?cluster=…` для предвыбора кластера; K09 — `?session=…` для связанного журнала. Эти query-переходы входят в проверку контекста.

## 2. Общие элементы, которые повторяются на страницах

- `DataTable`: локальная пагинация по 15 строк, счётчик диапазона, «Предыдущая страница» / «Следующая страница». Поиск и его очистка существуют **только** при `searchValue`. Сортировка существует **только** для колонок с `sortValue`; отсутствие сортировки других колонок не считать проверенным дефектом без обсуждения сценария.
- Поиск: I01 название/назначение; I02 название/цель/сервер; I07 название/описание; I08 заголовок/содержимое; I09 brief. K01 имя/окружение/provider; snapshot ItemTable — имя/namespace/kind; K06 имя/platform; K07 cluster/namespace/operator; K09 action/recording context; K10 action/cluster/reason; K12 delivery names/context. `KubeEvents` имеет поиск по reason/message/object. Live explorer использует свою форму server-side фильтрации, а не поиск DataTable.
- Сортировка явно задана: I02 имя агента; I07 имя MCP; I08 уверенность и актуальность; I09 дата обновления. Пагинация server-side выборки live explorer и cursor «Загрузить более ранние» I04 — отдельные уровни от DataTable.
- `Tabs` используют общий Radix-компонент. У большинства страниц выбранная вкладка хранится локально и не входит в URL. Кнопка Back, reload, смена route и возврат из drawer требуют отдельного наблюдения в браузере; сохранение вкладки не подтверждено этой инвентаризацией.
- `Drawer`: заголовок, описание, крестик «Закрыть», overlay; footer задан некоторыми страницами. `ConfirmDialog`: «Отмена», «Подтвердить», необязательная точная строка. Общий confirm имеет danger-цвет даже для некоторых согласований и запусков; это UX-кандидат, а не признак разрушительности всех операций.
- `JsonDetails` и обычные `details/summary` раскрывают технические данные. Их присутствие ниже отмечено как часть интерфейса; это не отдельный API или выполненная операция.
- Kubernetes имеет повторяющийся `KubeNav`: «Кластеры», «Поставки», «Заявки», «Сессии доступа», «Действия и записи», «Готовность», staff-only «Провайдеры».
- Loading/error/empty, запрещённая роль, disabled capability, pending submit, server validation, отсутствие данных и истёкшая session — разные состояния. Пустая таблица не подтверждает правильность заполненной страницы. Отрисованный fixture не подтверждает provider execution.

## 3. Данные для безопасной QA: подготовить до очереди страниц

Имена ниже — **предлагаемые метки подготовки**, а не существующие записи. Числовые ID и UUID нужно брать из ответов backend. Секреты в документ/скриншоты/фикстуры не помещать. Использовать подтверждённый изолированный QA backend/frontend и отдельный проект `ux-intel-k8s-<run>`; ранее использованные адреса 8091/9001 не считать автоматически доступными сейчас. Пользовательский frontend8090 и его данные не использовать для пробных изменений.

| Набор | Точные необходимые данные / условия | Что позволяет рассмотреть безопасно |
|---|---|---|
| Q0 — аккаунты | Отдельные owner-A, staff-reviewer-B с другим username, viewer-C. Проект A, при необходимости второй project-B. Явные features по таблице маршрутов; для недоступного состояния отдельная роль без feature. Никакого обхода разрешений. | Route guards, ownership, readonly sharing, переключение проекта, собственное/чужое согласование. |
| QI1 — агенты | Собственный ServerAgent в каждом `mini/full/multi`; при создании `schedule_config.mode=manual`, без внешней доставки; `mini.commands` заполнен заранее одобренной диагностической командой. Отдельные записи: без run, с `active_run_id`, с завершённым/failed run; 16+ строк для пагинации. Server scope только выделенные QA-серверы одного проекта, capability выполнения подтверждён backend. | Editor/detail/history; отсутствие автоматического запуска при сохранении manual-конфигурации. Для реального запуска нужен отдельный согласованный шаг QA, не просто открытие страницы. |
| QI2 — состояния run | Собственные `AgentRun`: `running`, `paused`, `waiting` + `pending_question`, `plan_review` + plan_tasks, `completed`, `failed`, `stopped`; задачи `pending/failed/skipped` и неизменяемые состояния. Report v2 с документом available/unavailable, findings/phases, delivery.can_retry, артефактами, cursor>50. | Все видимые actiongroups I04. Prepared backend-shaped records годятся для layout/state review, но не доказывают живой lifecycle. Stop/resume/reply/refine требуют существующего управляемого runtime, если нажимается финальное действие. |
| QI3 — расписания | Отдельные disabled QA-агенты с `manual/interval/daily/weekly/monthly/once`, timezone, next_due, due_now true/false, enabled и active_run combinations; feature `automation`. Worker readiness available/unavailable. | Все поля и блокировки; не включать периодический запуск ради просмотра формы. Due dispatch и cleanup — реальные mutations; только отдельные расходуемые записи и известное состояние worker. |
| QI4 — профили/MCP | AgentConfig owner-A, shared readonly viewer-C, admin-editable; действительные owned server IDs, MCP IDs, skill slugs. Для MCP — owned stdio и SSE записи, last_test_ok null/true/false, персональный grant при глобальном sharing false, `can_edit/can_share` combinations; 16+ записей для таблиц. | CRUD/review grants без глобального расширения. «Проверить» и «Инструменты» могут запустить процесс/сетевой запрос: нужен заранее согласованный локальный MCP с безопасным набором read-only tools или выделенный тестовый SSE endpoint. |
| QI5 — чат | Собственный manual chat с human/assistant history, Markdown/table/long code, active_turn busy true/false, action statuses `requires_confirmation/proposed/pending/completed/failed/canceled`, dangerous/mutating/read risks, typed_confirm_required/token, dry_run_preview/result/error; 2+ версионных artifacts. | I05/I06 layout и action review. Любое реальное message, confirm, stop или briefing требует настроенного AI runtime и выделенного контекста. Новая отправка создаёт чат и вызывает модель; это не локальный UI-only submit. |
| QI6 — память | Два **owned** QA-сервера; can_edit в bootstrap само по себе не заменяет backend ownership. На первом >=16 snapshots разных kind/confidence/freshness/version, на втором пусто. Отдельный disposable snapshot для delete и два для bulk/last-active сценария; staff-owner для overview/archive/promote/policy/purge; `studio_skills` для skill promotion. Retrieval enabled/disabled и daemon states. | Scope reset, фильтрация, editor, карточка, политика. У snapshot UI нет самостоятельной кнопки создания: данные готовятся утверждённым backend seed или контролируемой работой агента. Purge/last-active delete не выполнять на общей памяти. |
| QI7 — MARS | Собственная enabled personal workspace в выделенной QA-папке; sessions interview/plan_ready/approved + разные question kinds/options/required; runs queued/running/completed/failed/stopped с report/review/test_output/events. Для реального создания session нужен доступный Codex interviewer; для run — настроенные CLI/worker и разрешённые read/write roots, отдельный clean Git workspace. | Interview/plan/review flow. Не использовать рабочий пользовательский checkout. allow_dirty оставлять false; включение рассматривается только для специально подготовленного disposable dirty workspace. |
| QK1 — snapshot inventory | Rancher/Devtron provider, нормализованный cluster→namespace→Deployment→Pod→Service/Ingress, связи owner/sibling, events, last_sync свежий/устаревший/error; Helm ownership conflict и nonconflict, Fleet bundle, Devtron app/history/values metadata. 16+ элементов и отсутствие данных. | K01–K04/K12/K13 без объявления свежести/здоровья по фикстурам. Provider rows без доступного provider не доказывают live-доступ. |
| QK2 — read session | `kubernetes` + `kubernetes_admin_read`, `KUBERNETES_ADMIN_MODE_ENABLED`; active own read session со scope выделенного namespace, kind `*`; для Node/CRD нужна разрешённая cluster scope. Реальный Rancher и discovery/get/list/events RBAC; подходящие ресурсы и selector. | K08 live/read-only. Изолированные backend records возможны для presentation review, но реальные describe/logs/watch/metrics требуют provider. |
| QK3 — write session | `kubernetes_admin_write`, own request `pending_approval`, отдельный staff-B с активным write capability; approval_ref `UX-<run>-WRITE`; после реального согласования active own write session. Разрешённые write kinds **Deployment, StatefulSet, DaemonSet, Job, CronJob, Service, Ingress**. Namespace `webterm-ux-<run>` вне protected scopes. | Согласование и формы mutations. Для apply нужен свежий own dry-run proof с тем же точным манифестом/target; исправление YAML инвалидирует proof. Для реальных изменений нужен выделенный расходуемый Deployment и разрешённая операция. |
| QK4 — break-glass | Feature `kubernetes_break_glass`, active mode, peer-approved own session с причиной и коротким TTL. Разрешённые kinds **Pod, Node**; для Node scope `*` должен быть разрешён policy. Отдельный disposable Pod/тестовый узел, допустимые команды/порты, provider streaming, recording policy. | Терминал, node debug, pod exec, Pod port tunnel, node maintenance. Не выполнять drain на узле с пользовательскими workloads. Service port-forward не становится доступным только от включения transport: текущий mode kinds не включает Service. |
| QK5 — заявки | Request, принадлежащий A; отдельный чужой для B; статусы pending_approval/approved_external/executed_native/verified_external/verified_native/verification_failed/execution_blocked. preview/blast-radius/rollback/expected-verification/report/timeline. Для apply reference — настоящий собственный dry-run action; для Fleet/Devtron — существующий normalized ID. | K10/K11 action transitions и disabled policy. Verify сохраняет утверждение о внешнем результате: не вводить вымышленное доказательство в реальную заявку. |
| QK6 — аудит/записи | Own и all-staff actions, completed/blocked/failed, post_review_required и pending/completed/not_ready; recordings transcript_stored true/false, redacted/truncated, expired-retention и bounded events. Closed/expired break-glass session для review. | K09 и разбор сессии без подмены отсутствующей записи пустым успешным результатом. Экспорт содержит только фактически возвращённые данные. |
| QK7 — external/runtime | Выделенные Fleet/Devtron/GitOps объекты без пользовательских поставок; `studio_pipelines` и доступный owned read-only Kubernetes MCP для diagnose; staff для audit/deeplink. Metrics API `metrics.k8s.io` для CPU/memory. | Внешние ссылки, diagnosis draft, реальные provider operations после отдельного включения в очередь QA. Создание draft не подтверждает выполнение диагностики. |

### Runtime gates Kubernetes, которые нельзя заменять тестовыми «available»

Источник: `kubernetes_ops/permissions.py`, `services/capabilities.py`, `services/admin_sessions.py`. Помимо active/own session, namespace/kind/verb и provider RBAC:

| Операция | Feature / необходимые runtime flags |
|---|---|
| Live read / dry-run | admin mode + соответственно `kubernetes_admin_read` / `kubernetes_admin_write` |
| Secret reveal | read capability + `kubernetes_secret_read` + `KUBERNETES_ADMIN_SECRET_READ_ENABLED` |
| Apply / patch / scale / restart / delete | write capability + соответствующий `KUBERNETES_ADMIN_NATIVE_{APPLY,PATCH,SCALE,RESTART,DELETE}_ENABLED` |
| Pod exec | break-glass + `KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED`, `KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED`, applicable recording policy |
| Port tunnel | break-glass + `KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED`, `KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED`, applicable recording policy |
| Cordon/uncordon | break-glass + `KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED` |
| Drain | node-maintenance capability + `KUBERNETES_ADMIN_NODE_DRAIN_EXECUTION_ENABLED` |
| Cluster terminal / node debug | break-glass + `KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED` / `KUBERNETES_ADMIN_NODE_DEBUG_ENABLED` и соответствующие `…_RECORDING_ENABLED` transport gates |
| Execute approved request | staff UI, request approved_external, k8s action, write session + returned `access_policy.can_execute_approved_action`; backend включает `KUBERNETES_ACTION_REQUEST_NATIVE_EXECUTION_ENABLED` и конкретное право mutation |

Read/write/break-glass TTL defaults 60/30/15 минут; maxima 240/60/30. `available=true` без `transport_enabled` не доказывает интерактивное соединение. В записи режима нет разрешения расширять write/break-glass kinds сверх backend allowlist.

## 4. Intelligence — страницы и все actiongroups

### I01 — «Профили агентов»

Источник: `Profiles.tsx`, `SharedUsers.tsx`, `api/agent-profiles.ts`, `studio/views/agent_views.py` и `agent_helpers.py`. Данные: Q0/QI4.

- Страница: «Создать профиль», поиск, таблица name/description/owner/server scope/skills/updated. Ссылка в редактор pipeline. `can_edit`: «Настроить», «Удалить»; иначе «Только чтение».
- Drawer нового/существующего профиля: название (required, 200), назначение, системные инструкции, рабочие инструкции, максимум шагов 1–100, sudo `disabled/ask/approved`, разрешённые tools по строке, skill slugs через запятую при `studio_skills`, server checkboxes при `servers`, MCP checkboxes при `studio_mcp`.
- Existing `can_share`: общий доступ «Оставить без изменений / Включить / Отключить», персональные назначения пользователей. «Отмена / Сохранить профиль». Save — POST/PUT AgentConfig, не запуск AI.
- Delete — ConfirmDialog с точным названием профиля. Backend delete может потребовать перенастройки связанных AI-узлов.
- Кандидаты: два длинных поля «инструкции» без примера различия; raw skill/tool IDs; server/MCP checkbox lists без собственного поиска; shared settings только после создания. Сопоставить название раздела с I02 перед изменением навигации.

### I02 — «Агенты» и общий AgentEditor

Источник: `Agents.tsx`, `AgentMaterials.tsx`, `Operations.tsx`; backend `servers/views/server_agents.py`. Данные: QI1/QI3/QI4.

- Toolbar: «Расписания и процессы», «Обновить», «Создать агента»; empty-state create. Метрики: всего / в работе / по расписанию. Поиск «Найти агента или сервер», сортировка имени. Ссылки: имя и отдельная arrow-ссылка к одному detail; active/last run badges к I04.
- AgentEditor footer: «Отмена / Сохранить агента». Поля: название; **только создание** — способ `Автономный агент/full`, `Команды и анализ/mini`, `Командная работа/multi`, template selector. Выбор template заменяет goal/commands и заполняет пустое name. Ожидаемый результат; mini-команды по строке; server selection.
- Лимиты: шаги 1–100, время 30–3600 секунд; «Агент включён»; sudo запрещено / спросить / разрешено; simultaneous connections 1–10; multi-server checkbox. Save проверяет JSON tools/число соединений/поля schedule и отправляет конфигурацию, не вызывает run endpoint.
- Feature `automation`: schedule manual/interval/daily/weekly/monthly/once. Интервал 1–10080 минут; календарные timezone/time; weekly дни Пн–Вс; monthly день 1–31; once datetime. Изменение расписания на активное — изменение будущего поведения, даже если run button не нажат.
- Disclosure «Материалы и чеклисты»: add/remove до 10 materials, имя, kind document/task_list/script, content/code до 12000, run hint до 500; checklist пункты до 80, редактирование названия и remove/add. Это ввод материалов, не исполнение скрипта.
- Disclosure «Доставка отчёта»: Telegram enabled, Chat ID (пустое = notification default), include full-report link. Disclosure «Дополнительные условия»: system prompt, stop conditions по строке, skill slugs, tools JSON.
- Runtime drawer: scheduled table со ссылкой на agent, next_due/status; «Запустить наступивший» только due_now && enabled && !active_run; подтверждение запуска; worker/readiness JSON disclosures. «Проверить зависшие запуски» → confirm «Обработать…» → cleanup до 100 own runs, который может закрыть записи ошибкой и отменить queue tasks. При отсутствии automation расписания скрыты, cleanup остаётся.
- Кандидаты: very long editor, редкие delivery/runtime/tool controls, дубли arrow/name и create/empty-state create; «Командная работа» может означать team collaboration вместо multi-agent; «Запустить наступивший» непонятно без контекста; «Проверить зависшие» звучит read-only, но следующий шаг мутирует состояние.

### I03 — Detail агента

Данные: QI1/QI2. Back к I02. Toolbar «Настроить», «Запустить» (disabled при active_run_id). Run confirm показывает цель и server scope; подтверждение POST run ведёт к I04. Метрики режима/области/лимита; ссылка к текущему run; таблица истории запусков; раскрытие runtime readiness; удаление конфигурации отдельным ConfirmDialog с названием. Удаление вынесено ниже основной работы.

Кандидаты: необходимость переключаться между detail и run для наблюдения текущей задачи; доступность run по UI определяется active_run, тогда как реальные readiness/permissions дополнительно проверит backend — требуется понятное объяснение отказа. Не заменять неизвестный readiness зелёной кнопкой-свидетельством готовности.

### I04 — Выполнение агента

Источник: `Agents.tsx:AgentRunPage`, `Operations.tsx:PlanTaskEditor`; backend `server_agent_runs.py` и agent WS. Данные: QI2.

- Back к agent; status/start/server; active run: «Остановить» → confirm, «Приостановить / Продолжить» напрямую по WS. WS-connected guard; reconnect и refresh. REST evidence остаётся отдельным путём при недоступном live.
- Waiting/pending question: текст вопроса, поле ответа, «Отправить ответ» (непустой ответ). Plan section: «Одобрить план» только plan_review → confirm; задачи pending/failed/skipped имеют «Изменить» и «Исключить». «Исключить» сразу отправляет task delete, без отдельного preview.
- PlanTaskEditor: название, описание; «Сохранить задачу». Disclosure «Уточнить с помощью AI»: инструкция, «Уточнить и сохранить в плане»; это сразу сохраняет AI-результат на backend, не локальный draft. Несохранённые поля основной формы не передаются как AI instruction.
- Tabs: **Результат / Действия / События / Материалы**. Результат: outcome/evidence/report metrics, итоговый Markdown/findings, phases, document available gate, «Скачать отчёт», «Экспорт журнала аудита», «Повторить доставку» только delivery.can_retry → external-delivery confirm.
- Действия/события: отдельные карточки, cursor «Загрузить более ранние». Материалы: index и returned download URLs. Смена tab сбрасывает cursor/history локально.
- Кандидаты: approval/reply/план перед всеми tabs может отодвигать итог; overlap действий/событий; общая danger confirm для approval; немедленное исключение задачи; технические поля evidence при кратком пользовательском вопросе о результате.

### I05/I06 — «Оператор»

Источник: `Chat.tsx`, `Operations.tsx:DutyDrawer/RenameChatDrawer`, assistant API и operator WS. Данные: QI5 + exact QA server bootstrap.

- Header «Дежурный / Новый диалог», боковая история с title/time links. Для выбранного chat: rename, reconnect icon, materials icon, delete icon (disabled busy). Новый диалог — переход на I05, а POST create происходит при первой отправке.
- Composer: выбор точного сервера «Контекст @» при servers feature добавляет `@server.name` в текст; textarea до 12000; **Ctrl+Enter / Cmd+Enter отправляет**, обычный Enter добавляет строку; «Отправить» и busy «Остановить» (WS `turn.stop`, только connected). Runtime phase/errors, закрытие сообщения ошибки. Initial send создаёт chat и использует REST message; существующий использует WS или REST fallback.
- Message stream и persisted history; disclosure «Действия оператора · N» для tool events. ActionCard: input/blast-radius/result disclosures, status/error; pending requires_confirmation/proposed/pending — «Рассмотреть действие», «Отклонить» (сразу POST cancel).
- Action review drawer: описание/risk/input, optional dry-run preview, typed token если backend требует; «Назад / Подтвердить действие». Это самостоятельный реальный action, не просто согласование сообщения.
- Materials drawer → выбранный artifact drawer: просмотр, «Редактировать / Просмотр», content<=256000, «Сохранить» с bump_version. Delete chat confirm удаляет переписку и материалы. Rename drawer: title<=200, save PATCH.
- Duty drawer: состояние, «Открыть диалог», «Включить/Отключить дежурство», «Подготовить сводку сейчас». Каждое изменение/brief имеет confirm. **GET duty создаёт дежурный chat, если отсутствует**: само открытие drawer не является гарантированно лишённым persisted effect. Brief запускает AI и открывает дежурный chat; enable меняет автоматическое поведение.
- Кандидаты: «Дежурный» как редкая header-action; три icon-only controls; вложенные drawers материалов и duty confirm; выбор сервера дописывает mention, а не заменяет прежний; разные stop/reconnect состояния initial REST и существующего WS; tool evidence не должно заслонять основной ответ.

### I07 — MCP

Источник: `McpMemory.tsx:McpPage/McpEditor`, `SharedUsers.tsx`; backend `studio/views/mcp_views.py`. Данные: QI4.

- «Каталог шаблонов / Подключить MCP», поиск, сортировка имени, last-test/status/owner. can_edit: «Проверить», «Настроить», delete. **«Инструменты» доступны также read-only viewers**; живое чтение возможностей не равно праву редактировать конфигурацию.
- Catalog drawer: templates → «Использовать шаблон» закрывает catalog, открывает prefilled editor. Шаблон не проверяет доступность.
- Editor: name/description; stdio command,args-per-line,env JSON; SSE URL,headers JSON; managed secret key names без прежних значений; can_share existing — tri-state global sharing и personal users. «Отмена / Сохранить».
- «Проверить» POST сохраняет результат test. «Инструменты» GET живого MCP открывает drawer со списком/полным contract; это может запускать внешний процесс/соединение. Delete confirm с названием, внешний сервис не удаляется.
- Кандидаты: рядом «Проверить» и «Инструменты» без очевидного различия side effects; env/auth headers raw JSON; длинные списки grants; test state null следует читать как «не проверено», не как отказ и не как соединение.

### I08 — память

Источник: `McpMemory.tsx:MemoryPage/MemoryEditor/MemoryPolicy`, `Operations.tsx:MemoryBulkDrawer`; backend server_memory/search. Данные: QI6.

- Selector owned server; смена сервера закрывает snapshot/editor/policy/bulk/confirm и сбрасывает searchResult. Header «Удалить несколько сведений» disabled empty. Нет кнопки создать сведение.
- Tabs: **Сведения / Поиск по памяти / Обработка и политика** (последняя staff). Сведения: title open, kind, confidence/freshness sortable %, updated, «Изменить» в строке. Snapshot drawer: версия/источник/дата/content/provenance, «Изменить», «Удалить» → confirm; staff «В архив», «В заметку», staff+studio_skills «Создать навык» — непосредственные mutations.
- Editor: title<=200, content<=8000; «Отмена / Сохранить». Bulk drawer: checkboxes snapshots → «Рассмотреть удаление · N» → confirm списка и exact server name; удаление последнего активного snapshot очищает derived memory.
- Search: query<=1000, «Найти» POST search; результаты с source/content/score. Не выдавать отсутствие результатов из disabled retrieval за пустую рабочую память.
- Management: mode/daemon/enabled, «Настроить политику», «Обработать сейчас» → confirm run-dreams hybrid, «Очистить память» → confirm; кандидаты patterns/automation/skills, worker JSON.
- Policy drawer: heuristic/nightly_llm/hybrid; events threshold2–50; sleep start/end0–23; raw retention7–365; episodes14–365; enabled и human-habits checkbox; save. Область policy — **все свои серверы**, несмотря на endpoint выбранного server.
- Кандидаты: destructive bulk как единственная header-action; термин «сведение» и «В заметку» нуждаются в различении; snapshot delete copy с упоминанием удаления server profile не поясняет именно текущую операцию; policy wider-than-selected scope; процессы/кандидаты/политика на одной длинной вкладке.

### I09/I10/I11 — MARS

Источник: `Mars.tsx`, `mars/views.py/services.py/models.py`. Данные: QI7.

- I09: «Новая задача», поиск brief, sortable updated, session link, latest run link, «Продолжить»; workspace context. Create drawer brief → «Отмена / Начать постановку» POST session с реальным interviewer.
- I10 tabs: **Условия задачи / План выполнения**. Интервью генерирует текстовые/длинные/choice поля по backend question contract; required fields контролируют «Подготовить план». Plan textarea + disclosure Markdown preview; «Согласовать план» → confirm сохраняет редакцию и **открывает** launch drawer; фактический запуск отдельной кнопкой. Approved session также имеет «Запустить», disabled если plan edited. Пустой plan → «Перейти к вопросам».
- Launch drawer: workspace/условия, test command override, allow_dirty checkbox, «Отмена / Запустить выполнение». Backend проверяет approved plan, workspace policy и dirty checkout. Отдельная карточка workspace показывает root и enabled, не разрешает редактировать workspace.
- I11: back к session, status/time/live, «Обновить», active «Остановить» → confirm; stop_requested блокирует повторный stop. Tabs **Результат / Проверка / Журнал**: final/codex summary, gemini review/test output, события. Event stream имеет REST recovery; источник отчёта не равен подтверждению результата тестов.
- Кандидаты: название MARS не раскрывает исполнителя; большие plan/edit + preview дубли; автоматическое открытие launch drawer после approve может смешивать этапы; raw test command/allow_dirty редки и имеют серьёзный эффект; после failed run нужен понятный путь назад к постановке.

## 5. Kubernetes — страницы и все actiongroups

### K01–K04 — snapshot inventory

Источник: `Inventory.tsx`; backend inventory views/serializers. Данные: QK1.

- K01: refresh, cluster health/ready/namespaces/workloads/sync evidence; table links имени и отдельной стрелки. Staff empty-state «Подключить провайдер» → K06.
- K02: title/environment/sync, «Сессии доступа» → K07?cluster; namespace filter «Все пространства», refresh; tabs **Пространства имён / Нагрузки / Pods / Сеть / События**. ItemTable с local search, имя→detail, namespace, health, ready and timestamp. Snapshot filter — не cluster mutation.
- K03/K04: «Кластер» back; tabs **Обзор / События / Логи** (только Pod) **/ Метаданные**. Overview fields identity/owner/node/IP/restarts/version; связанные workloads/owner_workloads/pods/siblings/network через таблицы. Events с поиском. Metadata labels и inventory summary disclosure.
- Pod logs: выбор 100/200/500 строк, refresh, available/error/log text; snapshots не являются live-follow. Нет произвольной shell/exec на snapshot page.
- Кандидаты: английские Pods рядом с «Нагрузки»; одинаковые названия snapshot/live «События/Обзор» без явного времени источника; дубли name/arrow; длинные связанные таблицы; путь к live-resource проходит через session и должен быть понятен.

### K05 — готовность

Источник: `Inventory.tsx:ReadinessPage`, backend readiness/capabilities. Данные: QK1 + отключённые/разрешённые capabilities.

Refresh обеих частей; таблица system checks status/detail/required; список workflow availability с blocked_reason/transport-off reason. Mutations нет. Названия checks сейчас заменяют underscore пробелами, но часто остаются backend identifiers/English. Кандидат: сгруппировать «что доступно мне» и «что должен настроить администратор»; не прятать missing capabilities как успешные пустые секции.

### K06 — провайдеры

Источник: `Providers.tsx`, provider API. Данные: QK1/QK7, staff.

- Connect / empty connect, search; row «Настроить / Проверить / Синхронизировать / Удалить». Sync disabled if provider.enabled=false. Probe/sync запускают реальные provider calls, показывают result drawer.
- Editor: name, platform Rancher/Devtron, API URL, auth secret_ref/OIDC/none; secret source managed token/reference; blank replacement preserves current credential; enabled checkbox; disclosure labels JSON; «Отмена / Сохранить».
- Delete: typed provider-name confirm; configuration и managed secret удаляются. Result drawer: message/status/details. Произвольный URL/token нельзя пробовать на реальном окружении ради layout.
- Кандидаты: probe/sync в каждой строке, различие результатов и времени; auth/source controls как два связанных selector; OIDC/none должны объяснять реальную применимость; labels редки; наличие credential не должно выглядеть как успешно проверенное подключение.

### K07 — сессии доступа

Источник: `Sessions.tsx`, backend admin_sessions. Данные: Q0/QK2/QK3/QK4/QK6.

- «Запросить доступ», staff-only all-users checkbox, search cluster/namespace/operator. Название строки и «Подробнее» открывают одинаковый drawer.
- Create: cluster (optional initial from query), mode Просмотр/Изменения/Аварийный доступ с disabled unavailable options; namespace CSV, kinds CSV, TTL; цель доступа (required mutating). «Открыть сессию» для read / «Запросить согласование» для write/break-glass.
- Detail: scope/verbs/kinds/approval/requester/time. Own active → «Открыть ресурсы» и «Завершить». Own/staff active или pending → «Отозвать». Other staff с capability и pending → «Согласовать». Own pending получает текст, что сам согласовать не может.
- Внутренняя transition form: approve reference required; revoke/close reason; closed/expired break-glass post-review → outcome accepted/needs_followup/incident_created, summary, evidence. «Подтвердить» сохраняет выбранный переход. Session review staff gate отличается от creation.
- Кандидаты: CSV kind/ns вместо конкретного выбора; одновременно «Отозвать / Завершить» для own active; два входа в один drawer; TTL/scope допускаются UI текстом, но kinds ограничены backend; после согласования reviewer не должен видеть ложную возможность открыть чужую live session.

### K08 — live explorer и resource detail

Источник: `Explorer.tsx`, `ResourceDescription.tsx`, `ResourceTools.tsx`, `Mutations.tsx`, `Emergency.tsx`; QK2–QK4.

- Header «История действий» → K09?session; session cluster/mode/scope/expires; «CPU и память». Неактивная session → явное сообщение и ссылка к сессиям. Break-glass добавляет emergency actiongroup ниже.
- Discovery-backed kind selector; namespace (disabled cluster-scoped), labels, имя, **«Применить» фильтр**, icon refresh. Write-only **«Применить YAML…»**. Resource table name/detail кнопки, phase/replicas/creation; «Предыдущая/Следующая выборка» для API continue token дополнительно к таблице.
- Resource drawer tabs: **Обзор / Описание и связи / События / Наблюдение / Манифест / Логи** (logs Pod-only). Overview summary/conditions/replicas/containers/ownership. Non-read shows applicable «Реплики / Перезапуск / Изменить поля / Удалить» capability-gated. Pod/Service transport buttons описаны далее.
- «Описание и связи»: lazy live GET describe; identity/status/metadata/ownerRefs/ports/related Pods/ReplicaSets/events, refresh description; separate unavailable/error/skipped/empty/truncated/redacted. Это **не** возвращаемый для apply исходник.
- Events: provider availability и таблица. Watch: «Начать / Остановить наблюдение», state, event rows с раскрытием resource; максимум20 batches/300 events. No auto-restart после лимита.
- Manifest: JSON API resource, download; Secret explicit reveal checkbox только с permission/flag. Уход со вкладки сбрасывает reveal. Полный секрет не нужен для обычного QA; использовать отдельный dummy Secret при отдельном допуске.
- Pod logs: container input, «Снимок», «Следить/Остановить поток», state/error, последние1500 lines; limit25 batches; container/snapshot disabled во время follow.
- Metrics drawer: scope nodes/pods; для pods namespace, refresh; CPUm/memoryMiB/timestamp/container details и truncated. Наличие этой кнопки не доказывает metrics API.
- Кандидаты: шесть tabs в drawer; overlap overview/describe/events/manifest; два «Применить» с разной семантикой; вложенные transport drawers; два уровня pagination; отсутствие подбора container из списка; refresh snapshot и follow рядом; отсутствие конкретной причины у некоторых disabled mutations.

### K08 — mutation drawer

Источник: `Mutations.tsx`. Данные QK3 и **disposable разрешённый Deployment**, не ConfigMap/ReplicaSet вне write allowlist.

- Общий заголовок операции/cluster/session expiry; target; reason required. Parameters → отдельный review → «Подтвердить выполнение». На review поля заблокированы; «Вернуться к параметрам», «Отмена», success «Открыть журнал действий / Закрыть».
- Apply: namespace, YAML, «Проверить схему», «Проверить на сервере» dry-run; validation/diff/ownership/proof. Любая правка YAML/namespace обнуляет proof. Apply disabled без свежего доказательства, active/capability и reason. Diff — submitted vs server dry-run response, не полный live-baseline diff.
- Patch: merge/json/strategic type, JSON body. Scale: integer replicas>=0. Restart: target/reason. Delete: exact `delete Kind namespace/name`, для cluster target `delete Kind name`, foreground policy из кода.
- Кандидаты: сохранение review при server error/expiry, понятность schema vs dry-run, управление scroll/focus после длинного diff, точная подпись final action вместо универсального confirm. Не добавлять повторные auto-submit при timeout.

### K08 — интерактивные и аварийные инструменты

Источники: `Emergency.tsx`, `ResourceTools.tsx`; данные QK4. Все интерактивные starts — реальные операции; review нельзя тестировать нажатием финальной кнопки на пользовательском runtime.

- Emergency group: «Терминал кластера», «Диагностика узла», «Запретить размещение», «Разрешить размещение», «Освободить узел», «Просмотреть ограниченный контекст доступа». Последний POST возвращает RBAC/context, ничего сам не применяет; result JSON disclosure.
- Cluster terminal/node debug drawer: exact node для debug, reason; «Проверить и продолжить / Открыть соединение»; xterm input/output, connection/error status, «Закрыть соединение», ссылка в журнал/запись. No auto reconnect/re-execution.
- Node maintenance drawer: exact node/reason; drain exact `drain Node name`; parameters→review→execute. Cordon/uncordon/drain не отменяются закрытием UI после server acceptance; показывается результат и журнал.
- ResourceTransport: Pod «Терминал контейнера» и Pod/Service «Подключение к порту» показываются по type, но enabled требуют active break-glass + workflow + transport. Exec fields container/command/reason; port fields1–65535/duration1–900/reason; review→connect, изменение параметров до start.
- Tunnel connected: received bytes/status, close; HTTP Host/path, «Отправить GET-запрос»; disclosure «Отправить свои данные» → UTF8/Base64, payload, send; response view≤200000 chars, download visible text, summary. **Локальный OS TCP listener не создаётся.** Даже GET может иметь side effect у конкретного target; использовать заранее согласованный тестовый HTTP endpoint.
- Кандидаты: шесть emergency controls в одном ряду, terminology для cordon/drain, редкий restricted context, defaults shell/port; исчезновение transport после expiry; бинарный канал отображается UTF8, что требует ясного назначения; Service forwarding currently unreachable через стандартные break-glass kinds.

### K09 — действия и записи

Источник: `Activity.tsx`. Данные QK6.

- Tabs **Действия / Записи сессий / Аудит**, staff all-users checkbox, action post-review filter Все/Ожидает/Завершён/Выполняется. Query session фильтрует связанные записи; searches таблиц.
- Action row → drawer: identity/target/status/requester/review, payload/diff/result disclosures, timeline; download report. Post-review-required + staff corresponding active mode → «Зафиксировать итог проверки»; inline form outcome verified/accepted/needs_followup/incident_created, summary required, evidence/follow-up refs; «Сохранить разбор».
- Recording row → drawer: status/context/event_count/transcript-stored/retention/redaction, bounded stored events, «Скачать доступную запись». Fetch `event_limit=500`; отсутствие transcript должно оставаться объяснённым.
- Audit tab — returned audit summary/evidence disclosures. Никаких provider operations.
- Кандидаты: actions/request queue naming overlap; raw verb labels; разные значения «Принято / Результат проверен»; visible session filter; footer pagination легко спутать с backend limit100/recording event-limit500.

### K10/K11 — отдельная очередь заявок

Источник: `Requests.tsx`, `api/kubernetes-workflows.ts`, backend action request services. Данные QK5.

- K10: create, state select (пока **raw codes**), staff all-users, search action/cluster/reason, row detail link; states pending_approval/approved_external/executed_native/verified_external/verified_native/verification_failed/execution_blocked.
- Create drawer: operation и reason<=1000; target по таблице ниже; «Рассмотреть заявку» → target review → «Создать заявку». Это создаёт request/preflight, не исполняет mutation. Back-to-parameters / cancel.

| Operation | Target controls |
|---|---|
| `k8s.rollout.restart` — Перезапуск нагрузки | cluster, namespace, kind, exact name, API version |
| `k8s.workload.scale` — Число реплик | тот же target + integer replicas>=0 |
| `k8s.resource.apply` — Применение манифеста | successful own dry-run selector, ссылка к сессиям для получения proof |
| `k8s.resource.patch` — Изменение полей | resource target + merge/strategic/json, JSON body |
| `k8s.resource.delete` — Удаление ресурса | resource target + exact delete text + Foreground/Background/Orphan propagation |
| `fleet.rollout.pause/resume` — Приостановка/Продолжение Fleet | известный Fleet bundle selector |
| `gitops.create_merge_request` — Изменение через GitOps | optional cluster, repository URL, file path, source/target branch, title, diff summary |
| `devtron.open_rollback` — Откат Devtron | известный Devtron app selector |

- K11 status/requester/date, tabs **Область и план / Результат / Журнал**. Scope/preview/rollback/expected verification/report/timeline; export report.
- Pending other-user request + staff → «Согласовать»: approval_ref required, comment → review→confirm. Own request сообщает о необходимости другого сотрудника.
- Approved_external k8s request + staff → «Выполнить в WebTerm», disabled unless returned policy. Execute drawer active own write session selector (UI фильтрует status/mode/cluster), apply additionally exact JSON manifest; review→confirm. Backend дополнительно проверяет TTL/scope/permissions/proof.
- Approved_external/executed_native staff → «Зафиксировать проверку»: succeeded/failed, evidence reference, summary required, performed checks per line; review→confirm. Это сохранение доказательств, не автоматический повторный health check.
- Кандидаты: отличие «заявка на действие» и «сессия доступа» неочевидно; native/external labels в tooltip/report; “apply YAML” в explorer против “exact JSON” в execute; повторное ручное заполнение target; resource-request форма требует непустой namespace и строит namespaced delete phrase, поэтому cluster-scoped target через неё не предлагается — сопоставить с intended action contract; active-session selector не проверяет TTL локально в этой форме.

### K12/K13 — поставки

Источник: `Delivery.tsx`, normalized delivery APIs. Данные QK1/QK7.

- K12 tabs **Helm-релизы / Fleet / Devtron**, cluster selector, table search. Helm release name открывает drawer ownership/conflict/evidence/related workloads/apps/Fleet. Fleet/Devtron names ведут к K13.
- K13 header actions идут из `requestable_actions` и открывают CreateRequest с known target; Devtron+studio_pipelines — «Подготовить диагностику» → drawer → «Создать черновик» POST diagnose → automation draft.
- Tabs **Обзор / Нагрузки / События**; Devtron дополнительно **Pods / История и values**. Overview ownership/source/target/version/readiness/team/sync, Fleet partitions disclosure и related Devtron apps. Workload/Pod links к snapshot resource. History: chart/release/latest deployment evidence, values digest/redacted preview; нет editor полных values.
- Staff external fallback: кнопка с returned link key → POST audit/deeplink → появляется ссылка «Открыть … во внешней системе» в новом окне. Только returned HTTP(S), действие не автонавигация.
- Кандидаты: «Поставки и владельцы» vs deployment vocabulary; «История и values» смешанный язык; слово «редактированный» для redacted preview может означать editable; raw link key buttons; два клика внешнего перехода должны объяснять цель; requestable actions/diagnose — редкие controls, не основная метрика состояния.

## 6. Список кандидатов для очереди UX-рефакторинга

Это **гипотезы по исходникам**, а не результаты браузерной приёмки. Сначала открыть страницу на соответствующих Q-наборах, затем решать изменение.

| Приоритет просмотра | Кандидат / источник | Что выяснить на странице |
|---|---|---|
| Высокий | I01/I02: два вида агентов | Различает ли оператор конфигурацию роли для pipeline и исполняемую инфраструктурную задачу без чтения API терминов? |
| Высокий | K07/K10/K11: две модели согласования | Понятно ли, что session даёт временную область доступа, а request фиксирует конкретное изменение? Есть ли ясный следующий шаг после approve? |
| Высокий | K08: «Применить» фильтр рядом с YAML mutation | Можно ли ошибиться в назначении действия; нужен ли label «Показать ресурсы» или отдельная mutation group? |
| Высокий | K08: overview/describe/events/manifest в drawer | Какой tab отвечает на “что не работает и почему”; какие сведения повторяются без новой ценности? |
| Высокий | Backend allowed kinds vs UI hints/actions | Write ConfigMap/ReplicaSet и break-glass Service не разрешаются mode allowlist; убрать/объяснить недостижимые affordances после проверки intended contract. Не расширять права ради совпадения UI. |
| Высокий | K11 execute session filter и K10 target scope | Истёкший timestamp при status active требует ясного отказа до финального действия; K10 требует namespace даже для типов, потенциально имеющих cluster scope. Согласовать доступные targets с backend, не расширять права автоматически. |
| Средний | I02 editor / profile tools/grants | Какие поля нужны для первого сценария, а что переносится в disclosures; skill IDs/JSON/CSV нуждаются в реальном выборе из доступных сущностей? |
| Средний | I04 plan edits и I08 archive/promote | Какие действия сохраняют сразу; достаточно ли текста, busy и результата, нужен ли undo/review для конкретного риска? |
| Средний | I06 duty/artifacts nested drawers | Возврат фокуса, закрытие, непрерывность context и потеря несохранённых artifact edits; duty GET создаёт запись уже при открытии. |
| Средний | I08 bulk/purge/policy | Почему bulk deletion в header, когда основная задача — найти знание; ясно ли, что policy шире выбранного сервера? |
| Средний | I10 approve→launch drawer | Различимы ли “сохранить согласование” и “запустить реальную работу”; не выглядят ли они одним действием? |
| Средний | K08 emergency actiongroup | Нужны ли отдельные группы “доступ” и “обслуживание узла”; как виден blast radius и причина unavailable? |
| Средний | Raw names в K05/K09/K10/K13 | Составить пользовательские подписи checks/verbs/statuses/values/deeplink keys, сохраняя диагностический code в деталях. |
| Низкий | Дубли name/arrow, name/Подробнее, create empty-state/header | Удалять только если не теряется понятная точка входа; проверить на keyboard и narrow viewport. |
| Низкий | DataTable15 + API selection100 + watch/event limits | Пользователь понимает текущую страницу, текущую серверную выборку и неполный transcript? |
| Общий | Universal danger confirm / technical JsonDetails | Красный означает риск или любую финальную кнопку? JSON полезен для доказательств, но не должен быть единственным объяснением результата. |

## 7. Карточка, которую заполнять при фактической проверке каждой страницы

Для каждого I/K ID зафиксировать: подтверждённый QA origin и роль; реальные ID подготовленных сущностей; какие Q-наборы использованы; viewport; открытые tabs/drawers; проверенные navigation/search/filter/submit/cancel states; фактические API/WS ответы; что изменилось на backend; скриншот до/после; конкретный UX дефект; исправление; повторная проверка именно исправленного сценария. Указывать отдельно «presentation на подготовленных данных», «реальный backend CRUD» и «реальный внешний runtime». До этого момента статус сценариев данного документа — **не проверено в браузере в текущем этапе**.
