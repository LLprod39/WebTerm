# Automation и Skills: инвентарь взаимодействий для UX-прохода

Дата: 2026-09-02. Основание — только текущий новый frontend и действующие backend-контракты. Страницы в рамках этого обзора не открывались, E2E не запускались. Все пункты ниже **ожидают последовательной браузерной проверки**; это не акт приёмки. Порядок прохода выбирает ведущий browser QA.

## Данные и безопасная QA-среда

| Код | Что подготовить до соответствующего workflow |
| --- | --- |
| Q0 | QA frontend `http://127.0.0.1:8091`, backend `9001`, БД `webterm_frontend_qa_20260902`; случайные credentials из игнорируемого `frontend/tests/.auth/credentials.json`. Не выводить credentials в отчёт. Уникальный префикс объектов `qa_ux_auto_*`, список созданных ID/slug для удаления только своих объектов. |
| Q1 | QA admin; отдельные QA-пользователи для reader/operator/editor/manager и пользователя без feature. Seed viewer по умолчанию имеет только `servers/dashboard`: он подходит для отказа маршрута, но для положительной проверки чтения automation нужны отдельный feature grant и object share в QA. Проверять тот же проект; staff-обход не заменяет проверку owner/shared ACL. |
| Q2 | Плейбук YAML с `ansible.builtin.debug`, runbook с текстовой командой `echo QA`, непубликованный черновик, две сохранённые версии, опубликованная версия; отдельный ZIP с `playbook.yml` и `roles/...` без секретов. Редактирование/версии/архивирование не требуют запуска на сервере. |
| Q3 | Локальный SSH/SFTP fixture `127.0.0.1:22391`, сервер `qa-ssh-local`; опубликованная версия и профиль целей. Preflight не считать реальным запуском. Для полного runbook/Ansible workflow отдельно проверить наличие соответствующего QA worker/controller; SSH fixture не исполняет host shell, но Ansible controller сам должен быть доступен. Не подменять цели реальными серверами, не включать become ради заполнения состояния UI. |
| Q4 | Чистый pipeline с inactive manual trigger, отдельный `manual → condition(always_true)`, branched graph и невалидный несохранённый вариант. Для реального безопасного завершения есть `frontend/tests/backend/run_safe_pipeline.py`: он допускает только точные ID `qa_manual/qa_condition`, prefix `qa_auto_pure_run_`, owner `frontend-qa-admin`, пустой context, указанную QA DB и отсутствие чужих live dispatch. Не менять guard для произвольного графа. |
| Q5 | Для failure/partial/awaiting_approval/dead-letter/старого отсутствующего edge snapshot нужен отдельный изолированный сценарий или явно обозначенный persisted QA fixture. Такой fixture проверяет отображение/управление, но не доказывает работу executor, внешнего согласования или доставки уведомлений. Нельзя запускать общий worker, который захватит посторонние задания. |
| Q6 | Draft create/revise и адаптация YAML могут обращаться к настроенному AI provider. Перед этими действиями определить отдельный QA provider/доступ и ожидаемую стоимость/поведение. Без него проверять честный unavailable/error и просмотр заранее созданного QA draft; не маркировать генерацию проверенной. GitLab import/refresh требует специально выбранного QA repository/ref/token; preview также выполняет сетевой запрос. |
| Q7 | Для расписаний: QA pipeline с нужным `trigger/schedule`, `trigger/webhook`, `trigger/monitoring`, `trigger/manual`; все изначально inactive. Безопасный CRUD — оставить inactive, сохранить/перезагрузить/удалить. Перед проверкой включения удостовериться, что никакой QA scheduler/monitoring ingress не сможет выполнить произвольный граф. Webhook token показывать только на QA-объекте, не включать в screenshots. |
| Q8 | **Skills пишутся в файловую систему.** `qa_settings.py` сейчас не переопределяет `STUDIO_SKILLS_DIRS`; default из `studio/skill_authoring.py:51` и `skill_registry.py:73` — общий `BASE_DIR/studio/skills`. До CRUD настроить QA-only root либо использовать строго новый уникальный QA slug с учётом удаления только своей папки. Не редактировать поставляемые навыки для проверки. Нужны `SKILL.md`, `references/qa.md`, script как неисполняемый текст, read-only shared skill. |

## Общие элементы — повторить на каждой странице

- [ ] Зафиксировать URL/роль/данные и исходный screenshot. Проверить каждый видимый tab, disclosure, menu, drawer и confirm; для скрытого по ACL элемента записать, какой ролью он должен открываться.
- [ ] Одна понятная основная задача; вторичные действия доступны, но не конкурируют с ней. Прочитать подписи кнопок как оператор без знания backend.
- [ ] Пустой каталог, пустой результат поиска, загрузка, отказ/ошибка с повтором, длинные названия/описания, отсутствующие необязательные значения; отсутствие mock-данных.
- [ ] Table: поиск, очистка поля, сортировка только отмеченных колонок, пагинация при достаточном объёме данных, переход по строковой ссылке. Проверить, не ищет ли UI лишь текущую серверную страницу.
- [ ] Drawer/confirm: клавиатура, Escape/закрытие, возврат фокуса, доступная подпись; pending/double-submit; что сохраняется после закрытия и повторного открытия.
- [ ] Для редактора: edit → сохранение → reload; edit → смена вкладки/файла/маршрута → отмена/продолжение; 409 должен оставить пользовательский текст. Проверить deep link, Back и reload вкладок — многие tab states сейчас локальные.
- [ ] Общие typed KeyValues: имя → «Добавить», значение/тип (текст, число, да/нет, список, группа, пустое), вложенные add/remove; secret mode не раскрывает сохранённые значения. TargetPicker: доступные серверы, checkbox выбора/снятия выбора, пустой список; поиска в этом компоненте сейчас нет. Все эти controls повторяются в формах ниже.
- [ ] После конкретного rework повторить тот же workflow в браузере, сохранить before/after и фактический результат. Source review или наличие теста не заменяет этот шаг.

## 1. `/automation` — входная точка

- [ ] Проверить redirect: `automation` → плейбуки; иначе `studio_pipelines` → процессы; иначе история запусков. Пользователь только с `studio_runs` должен попасть в допустимую историю; без features — увидеть отказ. Самостоятельных tabs/dialogs здесь нет. Данные: Q1.

## 2. `/automation/playbooks` — библиотека

- [ ] Шапка: **«Импорт»**, **«Шаблоны»**, **«Новый плейбук»**. Каталог: поиск имени/описания/тегов, тип `Все/Ansible/Runbook`, sort имени и доступных колонок, ссылка в workspace; пустая карточка «Создать плейбук». Q0–Q2.
- [ ] Drawer создания: название, описание, тип; Ansible YAML либо первая runbook-команда; «Создать плейбук». Проверить сохранение неправильного YAML, обязательные поля, последующий переход.
- [ ] Drawer импорта: tabs **YAML / Архив проекта / GitLab**; общий title; YAML text либо ZIP/TAR file; у archive/GitLab каталог и entrypoint; у GitLab URL/ref/token. «Проверить перед импортом» → выбранный файл, warnings, список файлов, раскрываемые результаты → «Импортировать проверенную версию». Изменение source после preview должно снять старое подтверждение. Q2; GitLab — Q6.
- [ ] Drawer шаблонов: **«Готовые шаблоны» / «Генератор»**; карточка → «Добавить в библиотеку»; рецепт → динамические checkbox/select/text/textarea → «Создать из рецепта». Это создание объекта, не выполнение инфраструктурных команд.
- [ ] После архивации: banner **«Восстановить» / «Закрыть»**; проверить возврат объекта и поведение Back/reload. Отдельного списка архива в этом UI нет.

## 3. `/automation/playbooks/:id` — workspace и вложенные workflows

- [ ] Шапка: «К библиотеке», **«Копия»** (`can_export`), **«Запустить»** (`can_run`). Права и опубликованная версия должны быть понятны до действий. Q1/Q2.
- [ ] **Содержимое**: YAML editor / runbook cards с описанием, командой, «Продолжить при ошибке», вверх/вниз/удалить, «Добавить шаг», «Сохранить черновик». Bundle: selector `Текущий черновик/Базовая/Опубликованная`, file tree, текст файла и сохранение. Read-only user получает опубликованное содержимое. Проверить текущее/base/published на одном изменённом файле.
- [ ] Боковые **«Сведения»**: версия/черновик/последний запуск/права/теги; disclosure **«Название и описание»** с name/description/tags → «Сохранить сведения»; ссылка «История запусков»; **«Архивировать плейбук»** → confirm с вводом имени.
- [ ] **Версии**: комментарий → «Создать версию из черновика»; строка → «Открыть»/«Закрыть» preview, «Опубликовать» confirm, «Восстановить» confirm, download. Редкие контрольные суммы раскрываются отдельно. Проверить, отличает ли оператор создание snapshot от публикации и от восстановления черновика.
- [ ] **Совместимость** (Ansible + `can_validate`): path, server targets, inventory mapping → **«Проверить совместимость»**; editor: instruction → **«Подготовить адаптацию»** → before/after, изменения, допущения/проверка поведения → **«Применить к черновику»** confirm или «Отклонить»; история адаптаций. Проверить stale proposal/409. AI часть требует Q6.
- [ ] **GitLab** (GitLab source + edit): entrypoint override/token → «Сравнить с GitLab» → file diff → «Импортировать новую версию» confirm; publication всё ещё на «Версии». Требует Q6.
- [ ] **Профили запуска** (edit OR run): таблица → «Новый профиль», «Изменить», delete icon → confirm. Форма: имя; Ansible group→targets add/remove; variables; новые/заменяемые secrets; checkbox удаления каждого сохранённого secret; «Использовать по умолчанию»; «Сохранить профиль». Проверить empty/masked/replace/remove без секретов в evidence. Q3.
- [ ] **Доступ** (`can_share`): user/group recipient, роль reader/operator/editor/manager, expiry, «Предоставить доступ»; current grants/expired state; «Отозвать» confirm. Положительную проверку читать/выполнять/редактировать провести другой QA-сессией. Q1.
- [ ] **Launch drawer**: revision + профиль/ручные цели; targets; disclosure «Привязка групп Ansible»; typed variables; concurrency; master-password; check-mode/become; disclosure «Фильтры задач» с tags/skip-tags/limit. **«Проверить готовность» → «Запустить» → confirm**. Каждое изменение значимых параметров должно инвалидировать preflight. Check mode не считать безусловно безопасным для любого Ansible module. Реальное выполнение только Q3.

## 4. `/automation/pipelines` — библиотека процессов

- [ ] Поиск, sort имя/число шагов/изменён; link workspace и last-run; длинное описание и пустое состояние. Шапка **«Шаблоны» / «Новый процесс»**, empty «Создать процесс». Q4.
- [ ] New drawer: имя/описание → «Создать процесс», inactive manual trigger. Templates drawer: карточка с назначением/категорией/числом шагов → «Использовать». Перед любым запуском отдельно проверить активные триггеры импортированного шаблона.

## 5. `/automation/pipelines/:id` — редактор

- [ ] Шапка: «К процессам», **«Сохранить»**, **«Проверить и запустить»**, dirty/saved. Toolbar: **«Добавить шаг»**, **«Свойства процесса»**, «Запуски» (`studio_runs`), icon download/clone/delete. Удаление всего процесса — typed-name confirm с влиянием на историю. Q4.
- [ ] Palette: поиск, category groups, node button/approval marker, close. Canvas: select/move nodes, connect handles, запрет self/cycle, select/delete edge/node, pan/zoom/fit/lock/minimap. Проверить клавиатурный альтернативный путь для удаления/редактирования связей; не предполагать его наличие.
- [ ] Inspector процесса: name/description. Inspector узла: label/delete, type/purpose/risk и manifest-driven required fields — bool/enum/number/text/multiline/server/array/object. Покрыть manual toggle, condition с требуемым значением, ветви, хотя бы один nested config. Save с missing required/unreachable → readable issues → «К узлу»; после исправления reload сохраняет topology/positions/config.
- [ ] Run drawer: manual entry, typed context, warnings и «К узлу», **«Проверить готовность»**, **«Запустить процесс»**, затем confirm. Проверить zero/multiple active manual entries, dirty disabled, validation error, dangerous gating; validate-only не должен выполнять граф. Реальное completed/run canvas — только точный Q4 helper scenario.

## 6. `/automation/runs` — история

- [ ] Tabs **«Плейбуки» / «Рабочие процессы» / «Требуют разбора»** по features. Проверить query links `?playbook=id` и `?pipeline=id`, отсутствие скрытого сохранённого фильтра после смены tab/Back. Q1/Q3–Q5.
- [ ] Плейбуки: search по имени/ID, status selector, run link, **«Более новые» / «Более ранние»** server cursor. Проверить поиск в истории с >25 запусками: сейчас фильтруется полученная страница.
- [ ] Процессы: search по имени/ID, table pagination, run link, trigger/status/timing; источник отдаёт последние 100. Проверить, понятны ли границы истории и текущий process filter.
- [ ] Требуют разбора: `Открытые/Разобранные/Все`, run link, ошибка/attempts, **«Зафиксировать решение»** → drawer «Результат разбора», текст решения → **«Закрыть запись»**. Это закрытие записи; повторного запуска здесь нет. Q5.

## 7. `/automation/runs/playbook/:id` — отчёт

- [ ] Шапка: link к плейбуку, **«Скачать отчёт»** при export capability, **«Повторить ошибки»**, **«Остановить»** → confirm. Проверить доступность на pending/running/completed/failed/partial/cancelled. Q3/Q5.
- [ ] Metrics/phase/estimated-or-unknown progress; failure message и suggested action. Таблица хостов: имя сервера и **«Открыть задачи»** ведут в один drawer; там задача/status/exit code/output. Покрыть пустой/длинный output.
- [ ] Журнал: incremental text, **«Обновить»**, ошибка и состояние усечения; tab скрыт/возвращён, reconnect/reload. Обновление не запускает операцию заново.
- [ ] Retry drawer: число failed hosts, исходная revision, required vars, typed variables/master password → **«Проверить и повторить неуспешные хосты»**. Эта кнопка непосредственно вызывает rerun API, отдельного preflight/confirm в этом drawer нет — проверить соответствие подписи и ожидаемых действий. Выполнение требует Q3, отображение ошибок — Q5.

## 8. `/automation/runs/pipeline/:id` — граф запуска

- [ ] Шапка: **«Открыть процесс»**, **«Возобновить»** при `can_resume`, **«Остановить»** у active → confirm; HTTP/WS freshness. Проверить роль только `studio_runs`, у которой нет доступа к редактору. Q1/Q4/Q5.
- [ ] **«Схема запуска»**: persisted nodes/edges/status, pan/zoom/fit/minimap; node click/keyboard selection → соседняя панель результата. Canvas readonly. **«Шаги процесса»** — альтернативный список выбора тех же узлов. Нет node state → «Нет результата»; нет edge snapshot → явное сообщение без подстановки current pipeline.
- [ ] Результат узла: label/type/status, ошибка/вывод и сохранённые времена, awaiting-approval explanation. Проверить completed/failed/awaiting/нет результата; изменение исходного pipeline не меняет snapshot.
- [ ] Resume: обычный request; при `resume_confirmation_required` → список неидемпотентных шагов → **«Возобновить с повтором»**. Входящие approval tokens отсутствуют в run API; кнопки «Одобрить всё» здесь нет. Q5; реальный повтор — только заранее ограниченный QA сценарий.

## 9. `/automation/drafts` — AI-черновики

- [ ] Search title/goal, status/update, ссылки на draft/source/applied pipeline. **«Новый черновик»** и empty **«Описать задачу»** → drawer title/goal → **«Подготовить черновик»**, pending и provider error. Q6.

## 10. `/automation/drafts/:id` — согласование предложения

- [ ] Шапка: «К черновикам», **«Проверить»**, **«Применить черновик»** либо «Открыть процесс» после apply. Покрыть drafting/questions/ready/applied/discarded и dangerous/invalid gating. Apply создаёт/обновляет pipeline, не запускает его. Q6.
- [ ] Readonly preview graph: zoom/fit/select; **«Предложение ассистента»**: reply, patch summary, warnings/validation. Выбор узла сейчас не открывает inspector — проверить, хватает ли информации перед apply.
- [ ] **«Уточнить задачу»**: вопросы, answer/requirements → **«Обновить предложение»**. **«Контекст черновика»**: original goal/risk/requirements, template selector → **«Подготовить из шаблона»**, **«Отбросить черновик»** confirm. Проверить, не теряется ли введённый ответ при переключении/закрытии.

## 11. `/automation/schedules` — расписания и события

- [ ] Type filter **Расписания / Webhooks / Мониторинг / Ручные / Все**, process link; строка **«Настроить» / «Включить–Выключить» / delete**. Шапка **«Настроить триггер»** открывает создание. Q7.
- [ ] Drawer: процесс (при edit disabled), тип, существующий узел соответствующего типа, имя; отсутствие eligible node → ссылка в editor. Schedule: cron + пояснение server timezone. Webhook: mapping, новый signing secret, URL, masked token + показать/скрыть/копировать. Monitoring: typed filters. Active checkbox, **«Сохранить триггер»**.
- [ ] Delete confirm объясняет, что графовый node может восстановить trigger при следующем save. Проверить на QA: настройка/выключение в table и node в editor остаются согласованными; отличить временное выключение от окончательного удаления узла.

## 12. `/intelligence/skills` — каталог

- [ ] Поиск name/description/service/tags; skill link, category/service, safety, owner, read/edit. **«Проверить каталог»** → summary/errors/warnings, **«Новый навык»** и empty create. Q8.
- [ ] Create drawer: template или с нуля; name/slug/description/service/category/safety/tags; guardrails/recommended tools по строкам; typed runtime policy; create scripts/references checkboxes; **«Создать навык»**. Проверить slug/defaults/required error и отсутствие исполнения созданного script.

## 13. `/intelligence/skills/:slug` — инструкции и файлы

- [ ] Шапка: «К навыкам», **«Проверить»**, **«Настройки»** (`can_edit`) → форма metadata как create, immutable slug. Tabs **«Инструкции» / «Рабочие файлы» / «Доступ»** (`can_share`). Q1/Q8.
- [ ] Инструкции: rendered Markdown и ссылки; правила применения/safety/guardrails/tools, явный read-only. Проверить длинный документ, code blocks, пустой instruction text.
- [ ] Рабочие файлы: tree → editor/status; **«Новый файл»** → path `references/`, `scripts/`, `assets/`; **«Сохранить файл»**, **«Удалить файл»** confirm кроме `SKILL.md`; validation и unsaved file/tab switching. Проверить binary/read-only файл: editor может быть readOnly, а нижние действия зависят от `skill.can_edit` — проверить ясность/доступность.
- [ ] Доступ: **«Общий доступ»** (`Не менять/Включить/Отключить`), individual user checkboxes, **«Сохранить разрешения»**. Проверить, понимает ли оператор текущее effective состояние, особенно mixed individual/shared; изменение подтверждается отдельной QA-сессией. В этой странице нет удаления самого навыка — cleanup QA папки должен быть заранее определён.

## Кандидаты для осмысленного rework — проверить в браузере

| Приоритет просмотра | Наблюдение из source | Что решить после browser-прохода |
| --- | --- | --- |
| Высокий | Создание черновика → snapshot revision → publish; launch выбирает любую доступную revision, а описание drawer говорит «опубликованную». | Явно показать, какую версию запускают и зачем отдельные стадии. Не объединять разные backend mutations вслепую. |
| Высокий | Retry button говорит «Проверить и повторить», handler сразу делает `rerun-failed`. | Уточнить действие/этап подтверждения по реальному flow, не обещать несуществующий preflight. |
| Высокий | Trigger конфиг в canvas и отдельной schedules page; удаление trigger может быть отменено последующим graph save. | Определить основной источник настройки и ясную навигацию между ними. |
| Высокий | Pipeline primary «Проверить и запустить» → drawer «Проверить готовность» → «Запустить процесс» → confirm. | Проверить реальную стоимость кликов и структуру summary; сохранить осознанную границу execution. |
| Высокий | Skill runtime policy и inventory mapping — универсальные typed KV; safety/type/status/role часто показывают backend English. | Показать понятные термины/предустановки и раскрывать сложную конфигурацию по необходимости. |
| Средний | Node palette выводит часть backend type (`condition`), ID в inspector/result; enum values без перевода. | Более понятное название + назначение; технический ID оставить вторичным. |
| Средний | Run detail «Открыть процесс» не имеет локального feature guard, хотя route editor отдельно gated. | Для run-only role исключить бессмысленный переход в отказ; существующее отсутствие manifest-запроса сохранить. |
| Средний | На playbook host row имя и «Открыть задачи» делают одно действие; run canvas и steps table дублируют выбор. | Первый дубль упростить, второй оценить как полезную доступную альтернативу canvas. |
| Средний | Кнопки создания одновременно в header/empty state; playbook import/template/create — три равных входа. | Проверить визуальную конкуренцию, выбрать один primary; empty CTA — контекстный дубль, не автоматический дефект. |
| Средний | Tabs локальные; history search только по текущему cursor batch; filter `?pipeline`/`?playbook` не имеет отдельного явно видимого сброса. | Проверить сохранение контекста/Back/reload и границы поиска, добавить ясный scoped state при rework. |
| Средний | Skill sharing selector стартует «Не менять», effective sharing в форме не раскрыт; users — плоский checkbox list. | Показать текущий доступ и путь изменения; проверить список при десятках пользователей. |
| Средний | TargetPicker — плоский список серверов без поиска; он повторяется в запуске и совместимости. | Проверить выбор на десятках серверов и необходимость поиска/группировки. |
| Низкий/редкий | GitLab token/ref/entrypoint, inventory groups, become/limit/tags, hashes, whole-catalog validation, download/clone/delete graph. | Проверить необходимую discoverability и progressive disclosure; не выносить редкое управление в основной путь без причины. |
| Низкий/редкий | Архив restore доступен из переходного banner; нет archive browser. | Проверить recovery после dismiss/reload и объяснение ограничения без обещания отсутствующего backend списка. |

## Источники и форма evidence

Маршруты/feature gates: `frontend/src/features/automation/routes.tsx`. Контролы: `PlaybookLibrary.tsx`, `PlaybookWorkspace.tsx`, `PlaybookOperations.tsx`, `PlaybookCompatibility.tsx`, `Pipelines.tsx`, `Runs.tsx`, `RunCanvas.tsx`, `DraftsSchedules.tsx`, `Skills.tsx`, `shared.tsx`. QA prerequisites: `frontend/tests/backend/prepare.py`, `qa_settings.py`, `ssh_fixture.py`, `run_safe_pipeline.py`; filesystem skill roots: `studio/skill_authoring.py`, `studio/skill_registry.py`. Все пути относятся к текущему workspace `C:/WebTrerm`.

На каждый проверенный control group заполнять: **URL → роль → QA ID → действие → observed result → UX решение → изменённые файлы → повторный browser result → screenshot/trace**. Для внешнего провайдера/worker, которого нет, указывать конкретный недостающий prerequisite, а не «проверено». Предыдущие smoke-тесты полезны как сценарии подготовки, но не закрывают этот новый page-by-page UX-проход.
