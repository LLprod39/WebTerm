# Дополнение к очереди UX: текущие маршруты и вложенные экраны

Актуальная сверка исходников: **2026-09-06**, checkout `C:\WebTrerm`. Объём: **37 маршрутов с содержимым, 17 фиксированных redirect-patterns с учётом `/`, 3 входа с выбором по правам**, отдельно wildcard 404 и `RouteError`. Это карта обязательного браузерного прохода, **не UX-приёмка**: в рамках этой сверки браузер и тесты не запускались, product source и основная очередь не изменялись. Историческая сверка 2026-09-02 сохранена ниже и не определяет текущий объём.

Источники: `frontend/src/app/router.tsx`, `frontend/src/features/automation/routes.tsx`, `frontend/src/features/intelligence/index.tsx`, `frontend/src/features/governance/routes.tsx`; выбор доступного входа — `frontend/src/layouts/navigation.ts` и `NavigationLanding.tsx`. `features/intelligence/routes.tsx` только реэкспортирует определения; `features/kubernetes/routes.tsx` не подключён к app router.

## 37 маршрутов с содержимым

Количество обозначает route-patterns, а не число записей или вкладок. Например, оба адреса чата считаются отдельно; каждый доступный вариант содержимого по ID, query и правам проверяется внутри соответствующего прохода.

| Область | Количество | Полный список |
| --- | ---: | --- |
| Вход | 1 | `/login` |
| Серверы | 3 | `/infrastructure/servers`; `/infrastructure/servers/:id`; `/infrastructure/terminal/:id` |
| Автоматизация | 10 | `/automation/playbooks`; `/automation/playbooks/:id`; `/automation/pipelines`; `/automation/pipelines/:id`; `/automation/runs`; `/automation/runs/playbook/:id`; `/automation/runs/pipeline/:id`; `/automation/drafts`; `/automation/drafts/:id`; `/automation/schedules` |
| Навыки | 2 | `/intelligence/skills`; `/intelligence/skills/:slug` |
| AI | 11 | `/intelligence/profiles`; `/intelligence/agents`; `/intelligence/agents/:id`; `/intelligence/runs/:id`; `/intelligence/chat`; `/intelligence/chat/:id`; `/intelligence/mcp`; `/intelligence/memory`; `/intelligence/mars`; `/intelligence/mars/sessions/:id`; `/intelligence/mars/runs/:id` |
| Управление | 5 | `/governance/users`; `/governance/groups`; `/governance/permissions`; `/governance/audit`; `/governance/plugins` |
| Настройки | 5 | `/settings/general`; `/settings/ai`; `/settings/identity`; `/settings/readiness`; `/settings/limits` |

## 17 фиксированных переходов и 3 входа по правам

Все перечисленные переходы используют `replace`. Проверить каждый исходный адрес; для `/*` — корень и вложенный адрес. Назначение перехода не предоставляет дополнительных прав на целевую страницу.

| Количество | Исходные адреса | Назначение |
| --- | --- | --- |
| 10 | `/`; `/dashboard/*`; `/overview/*`; `/servers`; `/monitoring/*`; `/infrastructure/monitoring/*`; `/kubernetes/*`; `/infrastructure/kubernetes/*`; `/governance/activity/*`; `/settings/workspace/*` | `/infrastructure/servers` |
| 1 | `/agents` | `/intelligence/agents` |
| 1 | `/chat` | `/intelligence/chat` |
| 1 | `/studio` | `/automation/pipelines` |
| 2 | `/settings/users`; `/settings/access` | `/governance/users` |
| 1 | `/settings/groups` | `/governance/groups` |
| 1 | `/settings/permissions` | `/governance/permissions` |

| Вход | Проверяемые ветви `NavigationLanding` |
| --- | --- |
| `/automation` | Первый доступный основной инструмент: playbooks, pipelines, runs; если основные недоступны — доступный дополнительный пункт, например профили AI-узлов. Только `studio_runs`, только `studio_agents` и отсутствие всех доступных пунктов — разные случаи. |
| `/settings` | Первый доступный пункт настроек с учётом feature, staff и `can_manage_ai_routing`; при отсутствии доступных пунктов — «Недостаточно прав». Это больше не фиксированный переход в general. |
| `/settings/integrations` | Первый доступный дочерний пункт: MCP, иначе плагины; без обоих — «Недостаточно прав». |

- [ ] Отдельно открыть 404 внутри shell и воспроизвести `RouteError`, заменяющий shell. Оба предлагают «Открыть серверы». Неверный URL не проверяет аварийную ветвь.
- [ ] Проверить защищённый URL → login → исходные pathname **и query**; `/login` с действующей сессией → серверы через текущий домашний переход.
- [ ] Проверить прямые маршруты и вложенную навигацию под реальными доступными/ограниченными ролями; скрытая кнопка сама по себе не доказывает отказ доступа.

## Исключения и функции, которые остаются в объёме

По [MINIMAL_NAVIGATION_PLAN.md](../MINIMAL_NAVIGATION_PLAN.md) самостоятельные обзор, рабочий стол, мониторинг, весь Kubernetes и активность команды исключены из интерфейса. Их файлы/API могут оставаться, но текущий router направляет старые адреса на серверы. Проверяются эти переходы и отсутствие входов в исключённые экраны. Подэкраны K8s и `AdminActivityPage` из архивной таблицы ниже не являются активными страницами.

**Система конкретного сервера, журналы, память AI и аудит остаются активными функциями.** Скрытый глобальный пункт памяти не исключает `/intelligence/memory`: вход есть из карточки сервера. `/settings/access` объединяет вход к пользователям и группам и сам является переходом, а не отдельной страницей. Мобильная версия и глобальный поиск исключены ранее; поиск внутри рабочих списков остаётся обязательным.

## Обязательные вложенные ветви

Это дополнительные границы покрытия, а не сокращение проверки controls. В каждом родителе также проверить каждую create/edit/confirm форму, меню, поле, поиск, сортировку, пагинацию и empty/loading/error/disabled/permission states. Условно скрытые ветви открывать подходящей ролью/QA-данными; отсутствующий внешний prerequisite фиксировать как непроверенный workflow. После изменений повторить браузерный сценарий и только затем переходить к следующей странице.

Пути исходников в таблице относительно `frontend/src/features/`.

| Родитель | Обязательные ветви | Источник |
| --- | --- | --- |
| Серверы и группы | `tab=servers/groups`, создание `create=1`; группа `group`, `group_view=servers/members/context/bulk`; настройки, доступ, AI-правила и массовые изменения. Результат `bulk_operation` открыть также прямым URL и после reload. | `infrastructure/ServersPage.tsx`, `ServerGroups.tsx`, `GroupBulkOperations.tsx` |
| Карточка сервера | `tab=overview/files/knowledge/access`; «Ещё»: `command/operations/snapshots`, память AI и удаление. Набор зависит от capabilities. Файлы: меню строки и редактор; знания: детали/редактор; доступ: выдача/отзыв; снимки: просмотр и подтверждение восстановления. | `infrastructure/ServerDetailPage.tsx`, `ServerFiles.tsx`, `ServerKnowledge.tsx`, `ServerAccess.tsx`, `ServerSnapshots.tsx` |
| Система сервера | `tab=operations&system=overview/processes/services/docker/logs`; «Ещё»: `disk/network/packages/settings`. Всего 9 возможных вкладок, условных по capabilities. Меню процессов, журналы службы/контейнера в drawers, действия и опасные подтверждения. | `infrastructure/ServerOperations.tsx` |
| Терминал | Несколько одновременных SSH-сеансов, новый сеанс, переключение/закрытие/уход; `focus=1`; шрифт, preferences drawer, clipboard, reconnect/disconnect; file editor; AI-панель и её настройки, команды/инструменты, ответ на вопрос и согласование действия. | `infrastructure/TerminalPage.tsx`, `TerminalPreferences.tsx`, `TerminalFileEditor.tsx`, `TerminalAssistant.tsx` |
| Библиотека playbooks | Создание; импорт `yaml/archive/gitlab`; шаблоны `templates/guided`, включая генератор. | `automation/PlaybookLibrary.tsx` |
| Playbook | `content/revisions/compatibility/source/bindings/shares` по типу и правам; содержимое, версии/публикация, совместимость, GitLab, профили запуска и доступ; drawers запуска и редактирования. | `automation/PlaybookWorkspace.tsx`, `PlaybookOperations.tsx`, `PlaybookCompatibility.tsx` |
| Pipeline | Создание/редактирование/запуск; вкладки node picker, inspector, context menu узла и canvas, toolbar «Ещё», validation/launch drawer, подтверждения. Один просмотр canvas не покрывает редактор. | `automation/Pipelines.tsx`, `editor/PipelineEditor.tsx`, `editor/ContextMenu.tsx`, `editor/EditorTopBar.tsx` |
| История и детали запусков | `playbook/pipeline/dead`; DeadLetters — отдельные открытые/разобранные записи с решением. Детали host/tasks и pipeline steps/graph, ожидание согласования, повтор/остановка и результаты. | `automation/Runs.tsx`, `RunCanvas.tsx` |
| Черновики и расписания | Создание/пересмотр/публикация черновика; типы trigger: schedule/webhook/monitoring/manual, настройки/включение/удаление. Сверить отдельную настройку trigger с узлом pipeline. | `automation/DraftsSchedules.tsx` |
| Навыки | Создание/metadata; `instructions/files/access`, дерево и редактор, новый/удаляемый файл, sharing. | `automation/Skills.tsx` |
| Агенты и запуск агента | Editor/launch; drawer «Расписания и рабочие процессы», workers/recovery; запуск `report/activity/events/artifacts`, ответ на вопрос, редактор задачи плана, согласование/остановка/повтор доставки. | `intelligence/Agents.tsx`, `Operations.tsx` |
| AI-чат | Новый/существующий диалог, rename/delete, дополнительные инструменты composer, action detail, материалы и artifact detail. «Дежурный оператор» — отдельный drawer с включением, постоянным диалогом и сводкой. | `intelligence/Chat.tsx`, `Operations.tsx` |
| Память | Выбор сервера; `knowledge/search/management`; staff-ветвь обработки/политики, policy editor, workers/candidates/processing, bulk deletion. | `intelligence/McpMemory.tsx`, `Operations.tsx` |
| MARS | Сессия `questions/plan`, редактирование задач; запуск `result/review/events`, детали review. | `intelligence/Mars.tsx`, `Operations.tsx` |
| Плагины | URL `tab=installed/catalog/sources/review/maintenance`; installed detail `overview/settings/access/lifecycle`; установка `upload/remote/validate`; источники, доверие и обслуживание. | `governance/PluginsPage.tsx` |
| AI-настройки | URL `tab=platform/connections/preferences/pools`; runtime-disabled и role-dependent ветви; ConnectionDrawer → DeviceFlow/ConnectionGrants, PoolDrawer; провайдеры/ключи/назначения моделей и удаления. | `governance/AiPage.tsx`, `SettingsPages.tsx` |
| Доступ, интеграции и остальные настройки | Вложенные маршруты пользователей/групп и дополнительная матрица разрешений; MCP/плагины; «Дополнительно»: audit/general/identity/limits/readiness. Формы пользователя/группы, права, детали аудита, корпоративный вход и его подтверждение, поля общих настроек/лимитов и диагностика. | `governance/AccessPages.tsx`, `AuditPage.tsx`, `SettingsPages.tsx`; `intelligence/McpMemory.tsx`; `../layouts/SectionNavigation.tsx` |

Для automation подробности controls уже описаны в [UX_AUTOMATION_INTERACTIONS.md](UX_AUTOMATION_INTERACTIONS.md). Его старые порты, fixtures и настройки QA — сведения о прежней среде; перед операциями перепроверять текущую изоляцию и доступные зависимости.

## Согласование с основной очередью

- [ ] В строке 56 учитывать текущие 17/3 переходов и обе аварийные ветви; строку `/settings/access` трактовать как redirect.
- [ ] Согласовать статус карточки сервера с подразделами 05а–г: исторический частичный проход не закрывает оставшиеся вкладки системы или весь терминал.
- [ ] После shell/project продолжать принятый приоритет: серверы/группы → все ветви карточки и терминал → AI-чат с дежурным → остальные активные маршруты по очереди. Контекстную память открывать из карточки. Исключённые страницы не возвращать ради старого счётчика.
- [ ] Для каждой закрываемой ветви записывать URL/роль/QA-объект → действие → наблюдаемый результат → UX-решение → повторную браузерную проверку. Эта карта не выставляет PASS ни одной странице.

## Архив: сверка 2026-09-02 до сокращения маршрутов

Ниже сохранён прежний source inventory. **Числа 55/11, прежние назначения redirects, `AutomationLanding`, пункты K8s/активности и ссылки на старые строки не описывают текущий router.** Невыполненные checkbox из архива не добавляют исключённые страницы обратно в объём. Историческая сверка также не была браузерной приёмкой.

Сверка исходников на 2026-09-02 с `docs/frontend-next/PAGE_BY_PAGE_UX_REWORK.md`, строки 01–56. Браузер и тесты не запускались, product source и очередь не изменялись. Это дополнение к плану проверки, не результат UX-приёмки.

### Исторические пробелы в явном учёте маршрутов

Все **55 маршрутов с содержимым** уже названы в очереди, включая оба адреса чата в строке 25. Дополнительную страницу с содержимым добавлять не требуется. Сверены `frontend/src/app/router.tsx:41`, `frontend/src/features/automation/routes.tsx:79`, `frontend/src/features/governance/routes.tsx:66`, `frontend/src/features/kubernetes/routes.tsx:57` и `frontend/src/features/intelligence/index.tsx:39` — последний файл содержит определения, а `frontend/src/features/intelligence/routes.tsx:1` только реэкспортирует их.

- [ ] **Добавить к 56 явный `/automation`.** Это единственный адрес из feature-маршрутов, не названный в очереди: `AutomationLanding` выбирает `/automation/playbooks` при `automation`, иначе `/automation/pipelines` при `studio_pipelines`, иначе `/automation/runs`. Нужны отдельные случаи только `studio_runs` и отсутствие всех трёх прав; последний приводит к экрану ограничения доступа. Источник: `frontend/src/features/automation/routes.tsx:63`.
- [ ] **Расшифровать «совместимые redirects» в 56**, чтобы не проверить один произвольный alias вместо всех 11. `/dashboard → /`; `/servers → /infrastructure/servers`; `/monitoring → /infrastructure/monitoring`; `/agents → /intelligence/agents`; `/chat → /intelligence/chat`; `/studio → /automation/pipelines`; `/kubernetes → /infrastructure/kubernetes`; `/settings → /settings/general`; `/settings/users → /governance/users`; `/settings/groups → /governance/groups`; `/settings/permissions → /governance/permissions`. Все используют `replace`. Источник: `frontend/src/app/router.tsx:92`.
- [ ] **Добавить в 56 аварийный `RouteError` отдельно от 404.** `errorElement` заменяет shell при ошибке маршрута и даёт «Открыть обзор»; wildcard показывает обычный `EmptyState` внутри shell. Проверка неверного URL не покрывает эту ветвь. Источники: `frontend/src/app/router.tsx:30`, `:53`, `:106`.

Повторный вход уже учтён в 56. Для конкретизации достаточно двух переходов: защищённый URL → login → исходный pathname **и query**, а `/login` с действующей сессией → `/`. Источники: `frontend/src/layouts/AppShell.tsx:105`, `frontend/src/features/auth/LoginPage.tsx:29` и `:36`.

### Исторические самостоятельные подэкраны без отдельной строки

Родительские страницы уже стоят в очереди, а общий порядок требует проверки всех controls. Ниже только крупные ветви с собственными данными или самостоятельным workflow: их стоит явно отметить внутри соответствующей строки. Обычные create/edit/confirm формы и полный перечень вкладок здесь не дублируются.

| Строка | Что явно добавить к проходу | Точный источник |
| --- | --- | --- |
| 05 | Деталь **результата массовой операции группы** по `?tab=groups&group=<id>&group_view=bulk&bulk_operation=<id>`, включая повторное открытие URL. Эта запись результата существует отдельно от формы массового изменения и не имеет своего pathname. | `frontend/src/features/infrastructure/GroupBulkOperations.tsx:57`, `:78`; `frontend/src/features/infrastructure/ServerGroups.tsx:33` |
| 13 | **«Требуют разбора» / DeadLetters** — отдельный журнал исчерпанных попыток с фиксацией решения, а не фильтр failed-запусков. Нужны открытая и разобранная записи. | `frontend/src/features/automation/Runs.tsx:94`, `:950` |
| 21 | Drawer **«Расписания и процессы»**: расписания агентов, состояние workers, обработка зависших AgentRun. Это отдельная область от pipeline schedules в 18. | `frontend/src/features/intelligence/Agents.tsx:433`; `frontend/src/features/intelligence/Operations.tsx:512` |
| 25 | **«Дежурный оператор»** с постоянным диалогом, включением дежурства и отдельной сводкой. Обычный новый/существующий чат эту ветвь не открывает. | `frontend/src/features/intelligence/Chat.tsx:448`; `frontend/src/features/intelligence/Operations.tsx:27` |
| 27 | **«Обработка и политика»** и её редактор политики: staff-ветвь со сведениями о daemon/workers, кандидатами и операциями обработки. Переключатель сервера меняет контекст; обычный owner проходит другую ветвь. | `frontend/src/features/intelligence/McpMemory.tsx:764`, `:890` |
| 34 | Развернуть параметр `:kind` в **workloads / pods / network**; pod добавляет логи, остальные возвращают разные связи и поля. Namespace отдельно уже учтён в 33. Один произвольный ресурс не покрывает все варианты. | `frontend/src/features/kubernetes/Inventory.tsx:341`, `:365`, `:395` |
| 38 | **ResourceDetail внутри live Explorer**, включая describe/связи, watch, manifest и условные logs. Это самостоятельный Drawer выбранного live-ресурса, который не покрывается страницей сохранённого инвентаря в 34. | `frontend/src/features/kubernetes/Explorer.tsx:186`, `:228`, `:236` |
| 39 | Две отдельные детали без маршрутов: **ActionReport** с последующим разбором и **RecordingDetail** с доступной записью/сроком хранения. Кроме списка действий существуют списки записей и аудита; `?session=<id>` задаёт отдельный вход из сессии. | `frontend/src/features/kubernetes/Activity.tsx:34`, `:183`, `:255` |
| 42–43 | В 42 отдельно **Helm release Drawer** с владельцами и конфликтом владельцев. В 43 нужны оба реальных `:kind`: **fleet** и **devtron**; Pods, «История и values» и подготовка диагностики есть только у Devtron. Helm-detail pathname не объявлен. | `frontend/src/features/kubernetes/Delivery.tsx:136`, `:286`, `:333`, `:383` |
| 48 | Три самостоятельных URL-представления: `?view=users`, `?view=events`, `?view=usage`. Переход из пользователя в события добавляет `user_id`; это не тот же экран, что audit в 47. | `frontend/src/features/governance/AdminActivityPage.tsx:718` |
| 49 | Пять URL-представлений `?tab=installed/catalog/sources/review/maintenance`; отдельно **InstalledPlugin detail** с параметрами, доступом и lifecycle, а также **установка пакета** из файла/URL/серверного пути. Одного просмотра установленного списка недостаточно. | `frontend/src/features/governance/PluginsPage.tsx:1639`, `:700`, `:99` |
| 51 | Четыре URL-представления `?tab=platform/connections/preferences/pools`; дополнительно **ConnectionDrawer → DeviceFlow / ConnectionGrants** и **PoolDrawer**. Проверить доступную и отключённую CLI-ветвь; открытие общего AI config не покрывает подключения и назначения моделей. | `frontend/src/features/governance/AiPage.tsx:1257`, `:53`, `:148`, `:396`, `:700` |

Эти пункты не требуют новых product routes и не меняют последовательность страниц. Достаточно назначить им явные подпункты у существующих строк и отдельно фиксировать ограничения внешних действий. Подробный automation checklist уже есть в `docs/frontend-next/research/UX_AUTOMATION_INTERACTIONS.md`; здесь он не повторяется.
