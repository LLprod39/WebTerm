# Product Design UI/UX audit

Дата: 2026-06-10

## Проверено

- Воспроизведен login через frontend proxy `http://localhost:8080/api/auth/login/`.
- Проверены прямые backend-запросы к `http://127.0.0.1:9000/api/auth/csrf/`.
- Проверен UI login в браузере до перехода на `/dashboard`.
- Сняты desktop-экраны: login, dashboard, servers, agents, Studio overview/drafts/runs/skills/MCP/agents/notifications, settings AI/access/users/groups/permissions/SSO/memory/audit.
- Сняты mobile-экраны: dashboard, servers, Studio drafts, settings users.
- Повторно сняты контрольные screenshots после правок: dashboard mobile, Studio drafts mobile, settings users mobile, servers mobile, notifications desktop.
- Отдельно пройден flow настроек доступа: users list/create, users edit, groups, permissions desktop/mobile.
- Отдельно пройден flow Studio MCP/agent profiles: list/create на desktop и mobile, agent profile dialog.
- Отдельно пройден flow Pipeline Editor new pipeline на desktop/mobile и Settings AI/Audit desktop/mobile.
- Отдельно пройден flow Settings SSO, Settings Memory, Activity Journal filters и Terminal routes `/servers/hub`, `/servers/:id/terminal`.

## Причина 500 на login

Frontend шел на `/api/auth/login/` через Vite dev server на `localhost:8080`, но Vite proxy смотрел в устаревший WSL IP из `frontend/.env.local`.

Факты:

- `http://localhost:8080/api/auth/csrf/` возвращал `500 text/plain`.
- `http://127.0.0.1:9000/api/auth/csrf/` напрямую возвращал `200 JSON`.
- Прямой запрос к Django с `Host: localhost:8080` тоже возвращал `200`, значит причина была не в `ALLOWED_HOSTS`.

Исправление:

- `frontend/.env.local`: `VITE_DJANGO_URL=http://127.0.0.1:9000`
- Vite dev server перезапущен.
- `/api/auth/csrf/` и `/api/auth/login/` через `localhost:8080` после правки возвращают `200`.
- UI login в браузере проходит до `/dashboard`, console errors нет.
- Повторная проверка 2026-06-10 на текущем запуске: прямой POST без CSRF возвращает backend-level `403`, а browser flow с CSRF возвращает `csrf 200`, `login 200`, `session 200` и редиректит на `/dashboard/`. Это подтверждает, что текущий запрос до backend доходит; если снова виден `500` и Django console пустая, нужно перезапустить Vite dev-server, потому что proxy target читается при старте.

## Исправлено в UI

### Общий layout

- Mobile sidebar trigger больше не накладывается на заголовки страниц.
- Добавлен верхний mobile-safe offset в `AppLayout`.
- Подтверждено на `23-dashboard-mobile-after.png` и `27-servers-mobile-after-layout.png`.

### Studio overview

- Убран перегруженный промо-hero из первого экрана Studio.
- Основной экран теперь сначала показывает рабочий список pipeline/runbook, поиск и короткую сводку черновиков.
- `/studio/drafts` добавлен в Studio nav как нормальный раздел.

### Studio drafts

- Mobile-разметка разбита на рабочие панели: очередь, граф, запрос, проверка.
- Ключевые действия и статусы переведены на русский: черновики, активные, готовые, нужны правки, применены, новый.
- Canvas графа автоматически fit-to-view после загрузки.
- Review-панель теперь показывает реальные counts preview-графа, а не только patch stats.
- Подтверждено на `24-studio-drafts-mobile-after.png`.
- Повторный Product Design pass по `/studio/drafts` проверил desktop queue/empty graph и mobile queue/compose/graph panes.
- В RU-режиме оставались смешанные статические строки: `Отбросить draft`, `Graph появится после draft`, `Название draft pipeline`, `Операционный runbook`, presets `health-check`, `manual fallback`, `approval`, `agent`, `summary`, а также graph labels `Preview graph`, `Patch graph`, `Risk review`, `AI draft`.
- Static UI переведен на русские пользовательские формулировки: `Отбросить черновик ...`, `Граф появится после черновика`, `Название черновика пайплайна`, `Операционный сценарий`, `подтверждение`, `агент`, `сводка`, `ИИ-черновик`, `Проверка риска`.
- Discard icon action получил контекстный accessible label с названием черновика, а не generic `Отбросить draft`.
- Graph canvas panel/local status labels теперь локализуются через `lang`; технические `payload`, `Webhook`, `DAG`, `MCP`, API `draft_mode` остаются доменными/контрактными значениями.
- Подтверждено до правки: `208-studio-drafts-desktop-current.png`, `208-studio-drafts-desktop-current.md`, `210-studio-drafts-mobile-current.png`, `210-studio-drafts-mobile-current.md`, `212-studio-drafts-mobile-compose-current.png`, `212-studio-drafts-mobile-compose-current.md`, `214-studio-drafts-mobile-graph-current.md`.
- Подтверждено после правки: `224-studio-drafts-desktop-fixed-final.png`, `224-studio-drafts-desktop-fixed-final.md`, `218-studio-drafts-mobile-compose-fixed.png`, `218-studio-drafts-mobile-compose-fixed.md`, `222-studio-drafts-mobile-graph-fixed-final.png`, `222-studio-drafts-mobile-graph-fixed-final.md`; browser console errors = 0, mobile width stayed 390px.

### Notifications

- Экран оповещений очищен от смешанных смысловых фраз `defaults/workflow/approvals/alerts/audit trail`.
- Технические имена Telegram, Email, SMTP, Gmail оставлены как имена сервисов/протоколов.
- Подтверждено на `29-studio-notifications-desktop-ru-clean.png`.

### Settings users

- Mobile-карточки пользователей больше не раскрывают всю матрицу прав сразу.
- Добавлена компактная сводка: итоговый доступ, количество разрешенных/запрещенных прав, первые 6 chips и `+N`.
- Полный список остается на desktop и в режиме редактирования.
- `staff` в русской версии заменен на локализованный статус.
- Подтверждено на `26-settings-users-mobile-compact.png`.
- В edit-state карточки переопределения прав больше не накладывают строку `Итог/Источник` под select.
- Подтверждено: `35-settings-users-edit-desktop-current.png` до правки и `40-settings-users-edit-desktop-fixed.png` после.
- Повторный проход по create form нашел mobile friction: `Создать пользователя` стоял после 21 пользовательской карточки, поэтому основной create action был почти внизу длинной страницы.
- Create-панель пользователя теперь `order-first` на mobile и `xl:order-none` на desktop: mobile показывает форму сразу под summary, desktop сохраняет правую sticky-колонку.
- Подтверждено: `137-settings-users-mobile-create-current.png` до правки, `140-settings-users-mobile-create-fixed.png` и `142-settings-users-desktop-create-fixed.png` после.

### Settings permissions

- Desktop-формы `Правило для пользователя` и `Политика для группы` больше не сжимают три select и кнопку в одну узкую строку.
- На обычном desktop поля идут в две читаемые колонки, а 4-колоночный режим остается только для очень широкого viewport.
- Mobile-форма уже была читаемой и сохраняет вертикальную структуру.
- Подтверждено: `37-settings-permissions-desktop-current.png` до правки, `41-settings-permissions-desktop-fixed.png` после, `39-settings-permissions-mobile-current.png` как mobile baseline.
- Повторный accessibility pass по спискам правил нашел generic icon-only labels: все row actions читались как одинаковые `Переключить` и `Удалить`, без имени пользователя/группы и модуля.
- Toggle/delete labels теперь контекстные: например `Переключить правило German: Панель` и `Удалить правило группы admin: Серверы`.
- Подтверждено DOM-проверкой после правки: среди первых action buttons больше нет generic `Переключить`/`Удалить`; screenshot состояния `143-settings-permissions-mobile-actions-fixed.png`.

### Settings groups

- Desktop и mobile read/create surfaces визуально стабильны; критичных перекрытий на текущих screenshots не найдено.
- Подтверждено на `36-settings-groups-desktop-current.png` и `38-settings-groups-mobile-current.png`.
- Для согласованности с users create flow форма `Создать группу` тоже поднята над списком на mobile, при этом desktop right sidebar сохранен.
- Подтверждено: `138-settings-groups-mobile-create-current.png` до правки и `141-settings-groups-mobile-create-fixed.png` после.

### Server create/edit form

- На мобильном footer dialog перекрывал блок `Аутентификация`, и переключатели/пароль были частично скрыты под кнопками.
- Dialog переведен на flex-layout с ограничением `100dvh`; прокручивается только тело формы, footer не перекрывает поля.
- Подтверждено на `32-server-create-modal-mobile.png` до правки и `33-server-create-modal-mobile-fixed.png` после правки.

### Studio MCP

- Клик `Добавить MCP` открывал форму ниже длинного списка подключений, поэтому на первом экране desktop/mobile визуально ничего не менялось.
- Редактор MCP поднят сразу под hero, перед tabs/list, чтобы результат клика был виден без прокрутки.
- Подтверждено: `43-studio-mcp-create-desktop-current.png` и `50-studio-mcp-create-mobile-current.png` до правки, `51-studio-mcp-create-desktop-fixed.png` и `54-studio-mcp-create-mobile-fixed.png` после.

### Studio agent profiles

- `/studio/agents` был почти полностью на английском внутри русской Studio: `Agent Configs`, `New agent`, `No description`, `Mine`, form labels, tool descriptions.
- Страница, карточки, create/edit dialog, visibility block и tool labels локализованы через текущий `useI18n`/`localize`.
- В карточках разрешённые инструменты теперь показываются человекочитаемыми RU-названиями вместо внутренних id.
- Body agent dialog получил отдельный `DialogBody` с padding и scroll, чтобы первое поле не прижималось к левой границе модалки.
- Подтверждено: `44-studio-agent-profiles-desktop-current.png` и `45-studio-agent-profile-dialog-desktop-current.png` до правки, `52-studio-agent-profiles-desktop-fixed.png` и `55-studio-agent-profile-dialog-desktop-fixed-padding.png` после.
- Повторный accessibility pass нашел две icon-only кнопки удаления agent profile без текста, `aria-label` или `title`; edit action имел только generic title без имени агента.
- Edit/delete actions в карточках профилей теперь имеют контекстные accessible labels с именем агента, например `Изменить агента Check Logs` и `Удалить агента Check Logs`.
- Подтверждено: `146-studio-agents-desktop-accessibility-current.png` и `149-studio-agents-mobile-accessibility-current.png` до правки, `150-studio-agents-desktop-actions-fixed.png` и `151-studio-agents-mobile-actions-fixed.png` после. DOM-проверка: `badButtonsCount = 0`.

### Studio skills

- `/studio/skills` в RU-режиме показывал смешанную статическую copy: nav `Runbook`, hero `Studio library`, описание с `guardrails/runtime policy/workspace`, badges `Mine`, `Owner`, `Shared`, `Read only`, `enforced`, file kinds `reference/script/asset`, detail labels `runtime enforced`, `Guardrails`, `Runtime policy`, `Workspace Editor`.
- Mobile create dialog был layout-broken: footer с `Отмена/Создать` находился ниже viewport (`y≈1021`) внутри модалки высотой 760px, поэтому основное действие не было видно без неочевидной прокрутки.
- Static UI в каталоге, detail и wizard переведён на русские пользовательские формулировки: `Скиллы`, `Библиотека Studio`, `Ограничения`, `Политика выполнения`, `Редактор файлов`, `контроль`, `Мой`, `Общий`, `Только чтение`; filesystem names `SKILL.md`, `references/`, `scripts/`, `assets/`, provider/service names и slug оставлены доменными.
- Create skill dialog переведён на grid layout `auto/body/auto`: header и footer закреплены в viewport, body скроллится отдельно; мобильные отступы убраны с вложенных секций, чтобы поля использовали всю ширину.
- Общий `DialogContent` получил локализуемый `closeLabel`; в Studio Skills close action теперь читается как `Закрыть`, а не `Close`.
- Подтверждено до правки: `185-studio-skills-desktop-current.png`, `187-studio-skills-detail-desktop-current.png`, `189-studio-skills-mobile-current.png`, `191-studio-skills-create-mobile-current.png`.
- Подтверждено после правки: `193-studio-skills-mobile-fixed.png`, `195-studio-skills-create-mobile-fixed.png`, `196-studio-skills-create-mobile-close-fixed-snapshot.md`, `198-studio-skills-detail-desktop-fixed.png`; browser console errors = 0.
- Остаточный английский в карточках вроде `Environment skill for Keycloak...` и `Resolve the target server...` приходит из данных скиллов (`description`, `guardrail_summary`, `tags`) и должен решаться отдельным data/content localization pass, а не статической UI-заменой.

### Studio runs

- `/studio/runs` в RU-режиме показывал смешанную статическую copy: hero `Studio / Runs`, описание `pipeline run`, action aria-label `Обновить run`, detail toggle `Raw JSON (для отладки)`, header `Run #...`, toast `Run stopped`.
- Длительности в списке и detail оставались английскими (`39s`, `1m 41s`), хотя остальная навигация была русской.
- На mobile 390px список расширял страницу за viewport: контейнеры уходили до `417-418px` при ширине документа `385px`, из-за чего появлялся горизонтальный overflow.
- Mobile sidebar trigger в accessibility tree читался как `Toggle Sidebar`, несмотря на русский режим приложения.
- Static copy переведена на текущую локаль: `Studio / Запуски`, `запуски пайплайнов`, `Запуск #...`, `Обновить запуск`, `JSON для отладки`, `Запуск остановлен`.
- `formatRunDuration` и node duration теперь принимают `lang`; RU показывает `39 с`, `1 мин 41 с`, `мс/с`, EN сохраняет `39s`, `1m 41s`, `ms/s`.
- Runs layout получил `min-w-0`, `w-full` и `overflow-hidden` на корневых flex-контейнерах, чтобы list/detail не раздвигали mobile viewport.
- Общий mobile `SidebarTrigger` теперь использует переданный `aria-label/title`; `AppLayout` передает `Открыть навигацию` в RU.
- Подтверждено до правки: `200-studio-runs-desktop-current.png`, `200-studio-runs-desktop-current.md`, `202-studio-runs-mobile-current.png`, `202-studio-runs-mobile-current.md`.
- Подтверждено после правки: `204-studio-runs-mobile-fixed.png`, `204-studio-runs-mobile-fixed.md`, `206-studio-runs-desktop-fixed.png`, `206-studio-runs-desktop-fixed.md`; mobile containers теперь `385/384px`, browser console errors = 0.

### Pipeline Editor

- На mobile палитра нод была скрыта (`0x0` bounding box), поэтому с экрана `/studio/pipeline/new` нельзя было добавить шаг в pipeline.
- Добавлена mobile-кнопка `Ноды`, открывающая existing `NodePalette` в `Sheet`; после выбора ноды sheet закрывается и открывается настройка выбранного шага.
- Status warning в RU-режиме показывал английские `No active trigger` и `Add a manual...`; добавлен локальный display formatter для toolbar activity copy.
- Mobile status bar переведен в вертикальный layout, чтобы warning-detail не уезжал справа от badge.
- Подтверждено: `56-pipeline-editor-new-desktop-current.png` и `57-pipeline-editor-new-mobile-current.png` до правки, `65-pipeline-editor-mobile-node-sheet-fixed.png`, `66-pipeline-editor-mobile-node-added-fixed.png`, `69-pipeline-editor-new-mobile-fixed-status.png` после.
- Повторный Product Design pass по long-content/mobile node config показал, что `/studio/pipeline/new` на 390px открывает palette и MCP config panel без horizontal overflow, но palette descriptions для OPS-нод были наполовину на английском: `Read-only`, `List/install/update/remove`, `Inspect`, `latest archive`, `Terminate`.
- Breadcrumb/current-step chip после добавления MCP-ноды брал старый hard-coded English label `MCP Call`, хотя сама нода и config panel уже отображались как `MCP-вызов`.
- OPS palette descriptions переведены на русские пользовательские формулировки, технические имена вроде Linux, Docker, SFTP, MCP, systemctl, journal, tmp и backup сохранены как доменные термины.
- `getNodeDisplayLabel` теперь использует локализованный node metadata label, а не отдельную англоязычную lookup-таблицу; видимые chip/assistant/run labels получают текущий `lang`.
- Подтверждено до правки: `152-pipeline-new-mobile-current.png`, `154-pipeline-mobile-node-palette-current.png`, `156-pipeline-mobile-after-mcp-click-current.png`.
- Подтверждено после правки: `158-pipeline-mobile-node-palette-fixed.png`, `160-pipeline-mobile-mcp-config-fixed.png`, `161-pipeline-mobile-node-palette-fixed-smoke.png`, `162-pipeline-mobile-mcp-config-fixed-smoke.png`; smoke scan не нашел старые visible strings и подтвердил `MCP-вызов`.
- Повторный pass по Run dialog нашел смешанную RU/EN копию в ручном запуске: `Manual trigger`, `Task`, `Requester`, `Run context`, `requester metadata`, `JSON fields`, `Safe`, `Mutating`, `Approval gates`, `Verification`.
- Advanced context на 390px держал `Requester` и `Ticket/reference` в две узкие колонки, из-за чего label переносился грубо, а placeholder обрезался.
- Run dialog copy, risk summary, manual/webhook/schedule/monitoring helper text и validation errors переведены на русские пользовательские формулировки; технические термины `JSON`, `webhook`, `cron`, `pipeline` оставлены как доменные.
- Advanced fields теперь используют одну колонку на mobile и две начиная с `sm`.
- Подтверждено до правки: `165-pipeline-run-dialog-empty-mobile-current.png`, `167-pipeline-run-dialog-advanced-mobile-current.png`.
- Подтверждено после правки: `169-pipeline-run-dialog-empty-mobile-fixed.png`, `170-pipeline-run-dialog-advanced-mobile-fixed.png`; smoke scan не нашел старые visible strings, все required RU labels присутствуют.
- Повторный pass по `Помощник` нашел desktop layout bug: правая панель наследовала высоту длинной палитры нод, поэтому footer с textarea и кнопкой `Подготовить правку` уходил ниже viewport (`y≈1974..2131` при высоте экрана 1024).
- В этой же панели оставалась смешанная RU/EN copy: `approval`, `Docker service`, `patch`, `labels`.
- Helper copy переведена на русские пользовательские формулировки: `подтверждение`, `Docker-сервис`, `безопасную правку`, `понятные названия`; технические имена `pipeline`, `MCP`, `Docker`, `Telegram` оставлены как доменные.
- Дополнительно очищены соседние RU-строки Pipeline Editor с `approval`: risk badge, file write hint, MCP policy hint, approval-link labels и dangerous draft toast теперь говорят `подтверждение`/`ссылки подтверждения`.
- Immersive layout для `/studio/pipeline/...` теперь ограничен высотой viewport, а Pipeline Editor получил `min-h-0/overflow-hidden` на корневых flex-контейнерах. Внутри скроллятся палитра/панели, а не вся страница.
- Подтверждено до правки: `172-pipeline-assistant-mobile-current.png`, `174-pipeline-assistant-desktop-current.png`, `177-pipeline-assistant-desktop-fixed-snapshot.md` как evidence ещё не закрытого layout bug.
- Подтверждено после правки: `180-pipeline-assistant-desktop-layout-fixed.png`, `179-pipeline-assistant-desktop-layout-fixed-snapshot.md`, `182-pipeline-assistant-mobile-layout-fixed.png`, `181-pipeline-assistant-mobile-layout-fixed-snapshot.md`; desktop document height теперь 1024, кнопка `Подготовить правку` видима на `y=972..1012`, mobile overlay укладывается в viewport 390px.

### Settings AI

- Desktop и mobile read/config surfaces визуально стабильны на текущих screenshots; критичных перекрытий на текущем viewport не найдено.
- Подтверждено на `58-settings-ai-desktop-current.png` и `59-settings-ai-mobile-current.png`.
- Повторный Product Design проход по deep controls нашел смешанный язык в нижней части: `reasoning/thinking`, `Reasoning effort OpenAI`, варианты `(Auto)/(Low)/(Medium)/(High)`, `endpoint`, `proxy/header`, `Ollama Local Node`, `Ollama Cloud Hub`.
- Visible labels в блоке Ollama/reasoning переведены на русские пользовательские формулировки, технические API-значения (`reasoning_effort`, `<think>`, provider ids) сохранены без изменения payload.
- Role label `Оркестратор (Pipeline)` заменен на `Оркестратор пайплайнов`; OpenAI provider card больше не показывает `tool calling`.
- SSO summary внутри Settings AI теперь говорит `корпоративный прокси и HTTP-заголовок`, без `proxy/header`.
- Подтверждено до правки: `125-settings-ai-desktop-top-current.png`, `126-settings-ai-desktop-bottom-current.png`, `127-settings-ai-mobile-top-current.png`, `128-settings-ai-mobile-bottom-current.png`.
- Подтверждено после правки: `129-settings-ai-desktop-reasoning-fixed.png`, `130-settings-ai-desktop-bottom-fixed.png`, `131-settings-ai-mobile-bottom-fixed.png`; browser text scan не нашел старые visible strings, mobile `documentElement.scrollWidth === innerWidth`.

### Settings Audit

- Описания logging-карточек обрезались `truncate`, поэтому на desktop/mobile терялся смысл того, что именно будет логироваться.
- Описания переведены на двухстрочное отображение с нормальным line-height.
- Подтверждено: `60-settings-audit-desktop-current.png` и `61-settings-audit-mobile-current.png` до правки, `67-settings-audit-desktop-fixed.png` и `68-settings-audit-mobile-fixed.png` после.
- Вкладка `Журнал` на mobile была фактически desktop-таблицей: фильтры и строки уходили вправо, часть данных была недоступна без неочевидной горизонтальной прокрутки.
- Для mobile добавлен карточный список событий, а desktop-таблица сохранена.
- Фильтры журнала теперь укладываются без горизонтального overflow; mobile `document.body.scrollWidth === innerWidth`.
- Подтверждено: `74-settings-audit-activity-desktop-current.png` и `75-settings-audit-activity-mobile-current.png` до правки, `83-settings-audit-activity-desktop-fixed.png` и `84-settings-audit-activity-mobile-fixed.png` после.

### Settings SSO

- Mobile SSO экран имел риск визуального overflow на длинных описаниях и подсказках: help text и вводные сценарии обрезались у правого края.
- Добавлены `min-w-0`, `break-words`, line-height и mobile stacking для header/status.
- Подтверждено: `70-settings-sso-desktop-current.png` и `71-settings-sso-mobile-current.png` до правки, `82-settings-sso-mobile-fixed.png` после. Mobile `document.body.scrollWidth === innerWidth`.

### Settings Memory

- Desktop и mobile read/config surfaces визуально стабильны на текущих screenshots; критичных перекрытий на текущем viewport не найдено.
- Подтверждено на `72-settings-memory-desktop-current.png` и `73-settings-memory-mobile-current.png`.

### Terminal

- Проверены реальные маршруты терминала: `/servers/hub` и `/servers/:id/terminal`; `/terminal` корректно оказался несуществующим route.
- Desktop terminal surface визуально рабочий на текущем screenshot.
- Mobile SFTP и AI panel открывались как узкая боковая панель рядом с терминалом: слева просвечивали terminal rows, а сама панель не имела полноценной mobile ширины.
- На mobile все terminal side panels теперь открываются full-width и скрывают терминал, как уже делал Linux workspace.
- Xterm мог получать сохраненный `font_family: JetBrains Mono` без надежного fallback. Если шрифт не установлен в окружении, rows рендерились пропорциональным fallback и выглядели разреженно/рваными.
- Для xterm добавлен mono fallback stack: `JetBrains Mono`, `Cascadia Mono`, `Consolas`, `Courier New`, `monospace`; на mobile font size мягко ограничен до 14px с line-height не ниже 1.2.
- AI settings dialog на mobile перекрывал нижний контент footer-кнопками; диалог переведен на явные grid rows `header/body/footer`, body получил `min-h-0` и собственный scroll.
- Terminal settings panel не закрывался по `Escape`, из-за чего оставался поверх экрана и перехватывал следующий клик, например попытку перейти в SFTP.
- Добавлены Escape-close, `role="dialog"`, `aria-modal`, `aria-labelledby`, aria/title для close button; cursor options и `Reset` локализованы в RU/EN.
- Mobile Terminal settings panel теперь имеет `w-full max-w-sm sm:w-80`, поэтому на узком viewport не обрезается фиксированной шириной.
- Подтверждено до правки: `79-terminal-hub-desktop-current.png`, `80-terminal-server-desktop-current.png`, `81-terminal-server-mobile-current.png`, `91-terminal-sftp-mobile-current.png`, `92-terminal-linux-mobile-current.png`, `93-terminal-ai-mobile-current.png`, `94-terminal-settings-mobile-current.png`.
- Подтверждено после правки: `95-terminal-mobile-fixed.png`, `96-terminal-sftp-mobile-fixed.png`, `97-terminal-linux-mobile-fixed.png`, `98-terminal-ai-mobile-fixed.png`, `99-terminal-settings-mobile-fixed.png`.
- Повторный проход settings/SFTP: `118-terminal-settings-desktop-current.png` до Escape/localization правки, `119-terminal-settings-desktop-fixed.png` и `122-terminal-settings-mobile-fixed.png` после; `120-terminal-sftp-desktop-current.png`, `121-terminal-sftp-desktop-nested-current.png`, `124-terminal-sftp-mobile-current-content.png` подтверждают SFTP без console errors и без horizontal overflow.
- Повторный Product Design проход по Linux workspace settings нашел статический mixed-language в системном окне: `System Settings`, `Search settings...`, `Overview`, `Cron Jobs`, `Last Logins`, `Recent Failed Logins`, `Copy`, `Refresh`, а также соседние подписи `Система, пользователи, cron, security`, `Обновить workspace`.
- `SystemSettingsWindow` теперь использует `useI18n/localize` для секций, кнопок, поиска, пустых состояний, line count и copy toast; raw command output, PATH, usernames, ports и значения конфигов не переводятся.
- В родительском Linux workspace очищены видимые fallback/aria строки `workspace`, `security`, `Package manager`, `Shell execution`, `Root filesystem`, где они были статическим UI.
- Подтверждено после правки: `225-terminal-linux-settings-desktop-fixed.png`, `226-terminal-linux-settings-mobile-fixed.png`, `227-terminal-linux-settings-mobile-fixed-final.png`; browser console errors = 0, старые visible strings в проверенном snapshot не найдены.
- Повторный Product Design проход по Terminal SFTP/file operations нашел три связанные проблемы: Quick Run и Text Editor оставались частично англоязычными в RU shell, upload drop overlay в терминале был на английском, а SFTP список давал для файла только `Скачать`, из-за чего hidden text editor нельзя было открыть из нормального файлового workflow.
- Quick Run локализован: заголовок, summary cards, filter, empty state, result metadata, повтор/копирование, placeholder и aria-label запуска. Raw command, stdout/stderr и exit codes не переводятся.
- SFTP для файлов теперь показывает явную кнопку `Редактировать`, а двойной клик по файлу открывает редактор; `Скачать` оставлен отдельной явной кнопкой.
- Text Editor локализован и исправлен по доступности: кнопки `Открыть`, `Сохранить`, `Копировать путь`, `Перенос`, `Открыть / создать`, footer counts, loading/error/new-file states, aria-label для пути и close tab; nested `<button>` в tab header заменен на sibling controls, чтобы убрать React `validateDOMNesting` warning.
- Backend execute endpoint `/servers/api/<id>/execute/` падал для Quick Run с `You cannot call this from an async context - use a thread or sync_to_async`, потому что `ServerCommandHistory.objects.create` вызывался внутри async-функции напрямую. Запись истории завернута в `sync_to_async(..., thread_sensitive=True)`.
- Проверка login/proxy: `http://127.0.0.1:9000/api/auth/csrf/` = 200, `http://localhost:8080/api/auth/csrf/` = 200, POST login `lunix/1414` через Vite = 200. Кратковременные `500` во время autoreload воспроизводились как dev-server/reload состояние; постоянной ошибки login view на текущем запуске не найдено.
- Подтверждено после правок: `228-terminal-linux-files-desktop-fixed.png`, `229-terminal-quickrun-desktop-fixed.png`, `231-terminal-quickrun-clean-success.png`, `232-terminal-files-edit-button-fixed.md`, `233-terminal-text-editor-clean-fixed.png`; browser console errors = 0 после clean reload, Quick Run `whoami` вернул `exit 0` и stdout `lunix`.
- Повторный Product Design проход по SFTP destructive/permission operations нашел, что backend/API уже умел create folder, create file, rename, delete, chmod/chown, но UI прятал эти операции: в панели были только upload/refresh/download/edit.
- В SFTP добавлена верхняя action toolbar `Новый файл`, `Новая папка`, `Загрузить`, `Обновить`; для выбранного файла/папки добавлена scoped action panel с `Редактировать`, `Переименовать`, `Права`, `Владелец`, `Удалить`.
- Создание файла теперь сразу открывает существующий Linux Text Editor workflow, а standalone SFTP fallback получил встроенный редактор с `Открыть/Сохранить/Закрыть`, состоянием `Изменён`, ошибками и счетчиками строк/байт.
- `chmod` проверяет octal mode (`644`, `755`, `0644`) до запроса; `chown` оставлен как явное действие с prompt `владелец` или `владелец:группа`, потому что реальный успех зависит от прав SSH-пользователя.
- Подтверждено после правок: `234-terminal-sftp-actions-toolbar.png`, `234-terminal-sftp-actions-toolbar.md`, `235-terminal-sftp-after-temp-ops.md`, `236-terminal-sftp-created-editor.png`, `237-terminal-sftp-temp-cleaned.png`; UI smoke через временные `codex_sftp_audit_0610_1602*` и `codex_sftp_audit_0610_1620*` прошел create file, rename, chmod `600`, create folder/delete folder, delete file; фильтр после cleanup показывает `Поиск ничего не нашел`, browser console errors = 0.
- Повторный accessibility pass по общему `FileEditorModal` нашел legacy icon-only controls без accessible name и статические English `title`: `Minimize`, `Restore`, `Maximize`, `Close`; tab bar также был сверстан как nested `<button>` для tab close.
- `FileEditorModal` получил `role="dialog"`, `aria-modal`, localized `aria-label/title` для open/save/reload/copy/minimize/maximize/restore/close, localized tab count, отдельные sibling-кнопки для tab select/close и `aria-label` для file path input. Новые ключи добавлены в `ru/en` локали.
- Live route check через отдельный Vite `http://127.0.0.1:5173` и Django `127.0.0.1:9000`: login `lunix/1414` прошел, `/servers/hub` и SFTP открылись без browser console errors, `.bashrc` открылся в текущем Linux Text Editor workflow. Старый `FileEditorModal` не оказался основным SFTP workflow на этой странице, поэтому проверен сборкой и static scan; отдельный runtime trigger через terminal file-link interceptor остается для следующего pass.
- Подтверждено: `242-login-before-file-editor-smoke.md`, `243-terminal-hub-for-file-editor-smoke.md`, `244-sftp-before-file-editor-modal.md`, `245-sftp-before-file-editor-modal-deep.md`, `246-file-editor-modal-a11y-fixed.png`, `246-file-editor-modal-a11y-fixed.md`, `247-file-editor-modal-console-errors.txt`.
- Визуальный просмотр `246-file-editor-modal-a11y-fixed.png` дополнительно выявил, что SFTP selected action panel в узкой side panel обрезает правые actions (`Права/Владелец/Удалить`). Панель выбранного файла переведена на компактную 2-column grid с `justify-start`, чтобы действия не уходили за край.

### Dashboard

- Верхний hero частично локализован: обзор системы, центр управления, система защищена, CPU флота.
- Подтверждено на `23-dashboard-mobile-after.png`.
- Повторный Product Design проход по dashboard widgets нашел оставшиеся mixed-language и mobile readability проблемы: ISO timestamps на chart axis, `Openai`, `n/a`, `Server unreachable`, `CRITICAL`, `http_request`, а также микротаблицы в mobile widgets `Лидеры по активности` и `Анализ вызовов AI`.
- Добавлены display formatters для provider names, empty values, alert severity/type, activity category/action и короткого времени на графике.
- Mobile widgets `Лидеры по активности` и `Анализ вызовов AI` переведены с плотной таблицы на карточки; desktop tables сохранены.
- Подтверждено до правки: `100-dashboard-desktop-current.png`, `104-dashboard-mobile-current.png`.
- Подтверждено после правки: `108-dashboard-desktop-fixed.png`, `111-dashboard-mobile-fixed.png`, финальная проверка после alert-title fix: `114-dashboard-desktop-fixed.png`, `115-dashboard-mobile-fixed.png`.

### Servers

- В server inventory системная группа без группы отображалась как `Ungrouped`, а счетчик давал `1 серверов`.
- Добавлен display formatter для системных group labels и русское склонение `сервер / сервера / серверов`.
- Подтверждено до правки: `101-servers-desktop-current.png`, `105-servers-mobile-current.png`.
- Подтверждено после правки: `109-servers-desktop-fixed.png`, `112-servers-mobile-fixed.png`.

### Agents

- В filters и бейджах agent mode оставались английские `Mini`, `Full`, `Pipeline`.
- Добавлен единый formatter для agent mode labels: `Мини`, `Полный`, `Пайплайн`.
- Подтверждено до правки: `102-agents-desktop-current.png`, `106-agents-mobile-current.png`.
- Подтверждено после правки: `110-agents-desktop-fixed.png`, `113-agents-mobile-fixed.png`.

## Проверки

- `npm run build` в `frontend` прошел.
- `npx playwright test e2e/visual.spec.ts --project=chromium --grep "studio page snapshot" --update-snapshots` прошел.
- `npx vitest run src/pages/Servers.test.tsx` прошел после обновления устаревших ожиданий теста: `SSH` сейчас является link, а не button; английская локаль использует `Summary`, а не `Сводка`.
- Повторный `npm run build` после access settings правок прошел.
- Повторный `npm run build` после Studio MCP/agent profile правок прошел.
- Playwright smoke на `/studio/mcp` и `/studio/agents` после правок: login, create click, screenshots, browser console errors = 0.
- Повторный `npm run build` после Pipeline Editor/Settings Audit правок прошел.
- Playwright smoke на `/studio/pipeline/new`, `/settings/ai`, `/settings/audit`: login, screenshots, mobile node sheet, add node, browser console errors = 0.
- Повторный `npm run build` после Settings SSO/Activity Journal правок прошел.
- Playwright smoke на `/settings/sso`, `/settings/memory`, `/settings/audit` activity tab, `/servers/hub`, `/servers/:id/terminal`: login, screenshots, browser console errors = 0 кроме ожидаемого 404 при проверке ошибочного `/terminal` route.
- Повторный `npm run build` после terminal side panel/xterm/AI settings правок прошел.
- Playwright smoke на `/servers/hub`: login 200, screenshots terminal/SFTP/Linux/AI/settings, `documentElement.scrollWidth === innerWidth` на 390px, browser console errors = 0, HTTP >=400 responses = 0.
- Повторный `npm run build` после dashboard/server/agent display правок прошел.
- Playwright smoke на `/dashboard`, `/servers`, `/agents`: screenshots desktop/mobile, `documentElement.scrollWidth === innerWidth`, browser console errors = 0, HTTP >=400 responses = 0.
- Финальный Playwright smoke на `/dashboard` после alert-title fix: screenshots desktop/mobile, `documentElement.scrollWidth === innerWidth`, browser console errors = 0, HTTP >=400 responses = 0.
- Повторная проверка login proxy: browser flow через `http://localhost:8080/login` получил `csrf 200`, `login 200`, `session 200`, финальный URL `/dashboard/`.
- Повторный `npm run build` после Terminal settings Escape/localization правок прошел.
- `npx vitest run src/lib/terminal-file-links.test.ts` прошел: 7 tests.
- Playwright smoke на `/servers/hub`: Terminal settings desktop/mobile открывается и закрывается по `Escape`, SFTP desktop/mobile снимается без browser console errors и HTTP >=500, mobile `documentElement.scrollWidth === innerWidth`.
- Повторный `npm run build` после Settings AI deep controls copy правок прошел.
- Playwright smoke на `/settings/ai`: desktop/mobile screenshots, browser console errors = 0, HTTP >=500 responses = 0, mobile `documentElement.scrollWidth === innerWidth`, старые visible mixed-language strings не найдены.
- Повторный `npm run build` после mobile order правок в Settings Users/Groups прошел.
- Playwright smoke на `/settings/users` и `/settings/groups`: mobile create panels видны над списками, desktop users сохраняет правую колонку, browser console errors = 0, HTTP >=500 responses = 0, mobile `documentElement.scrollWidth === innerWidth`.
- Повторный `npm run build` после Settings Permissions action aria-label правок прошел.
- Playwright/DOM smoke на `/settings/permissions`: first 12 action buttons have contextual aria-labels, generic labels count = 0, browser console errors = 0, HTTP >=500 responses = 0, mobile `documentElement.scrollWidth === innerWidth`.
- Повторный `npm run build` после Studio agent action aria-label правок прошел.
- Playwright/DOM smoke на `/studio/agents`: icon-only buttons without accessible name = 0, contextual agent action labels present, browser console errors = 0, HTTP >=500 responses = 0, mobile `documentElement.scrollWidth === innerWidth`.
- Повторный `npm run build` после Studio Skills copy/dialog/accessibility правок прошел.
- Отдельных tests для `StudioSkillsPage` в `frontend/src` не найдено.
- Browser smoke на `/studio/skills`: desktop/mobile catalog, desktop detail, mobile create dialog screenshots; create dialog footer visible in viewport, close action label = `Закрыть`, browser console errors = 0.
- Повторный `npm run build` после Studio Runs copy/mobile/accessibility правок прошел.
- Отдельных tests для `PipelineRunsPage`/`PipelineRunDetail` в `frontend/src` не найдено.
- Browser smoke на `/studio/runs`: desktop split-pane и mobile list screenshots/snapshots, old mixed RU/EN strings cleaned in checked UI, mobile list no longer exceeds viewport (`385/384px`), browser console errors = 0.
- Повторный `npm run build` после Studio Drafts copy/accessibility правок прошел.
- `npx vitest run src/pages/StudioDraftsPage.test.tsx` прошел: 7 tests.
- Browser smoke на `/studio/drafts`: desktop queue/graph и mobile queue/compose/graph screenshots/snapshots, old static mixed strings absent, mobile width stayed 390px, browser console errors = 0.
- Повторный `npm run build` после Pipeline node palette/display-label правок прошел.
- `npx vitest run src/components/pipeline/nodes/nodes.test.tsx` прошел: 4 tests.
- Browser + Playwright smoke на `/studio/pipeline/new`: mobile palette opens, MCP node config opens, `MCP-вызов` visible, old mixed strings absent from scanned UI text, browser console errors = 0, HTTP >=500 responses = 0, mobile `documentElement.scrollWidth === innerWidth`.
- Повторный `npm run build` после Pipeline Run dialog copy/layout правок прошел.
- `npx vitest run src/pages/PipelineEditorPage.test.tsx` прошел: 8 tests.
- Playwright smoke на `/studio/pipeline/new`: Run dialog opens, advanced context opens, old mixed strings absent, required RU labels present, browser console errors = 0, HTTP >=500 responses = 0, mobile `documentElement.scrollWidth === innerWidth`.
- Повторный `npm run build` после Pipeline Assistant immersive layout/copy правок прошел.
- `npx vitest run src/pages/PipelineEditorPage.test.tsx` после Pipeline Assistant правок прошел: 8 tests.
- Browser smoke на `/studio/pipeline/new`: desktop и mobile `Помощник` открывается, footer виден в viewport, old helper strings не видны в проверенном состоянии, browser console errors = 0. Proxy CSRF через `http://localhost:8080/api/auth/csrf/` возвращает `200`, `.env.local` указывает `VITE_DJANGO_URL=http://127.0.0.1:9000`.
- Повторный `npm run build` после финальной чистки RU `approval` строк прошел.
- `npx vitest run src/pages/PipelineEditorPage.test.tsx` после финальной чистки прошел: 8 tests.
- Отдельных tests для `SettingsUsersPage`, `SettingsGroupsPage`, `SettingsPermissionsPage` в `frontend/src` не найдено.
- Отдельных tests для `SettingsSSOPage`, `SettingsMemoryPage`, `SettingsAuditPage` в `frontend/src` не найдено.
- Отдельных tests для `TerminalPage`/`AiPanel` в `frontend/src` не найдено; найден только `terminal-file-links.test.ts`.
- Browser console на проверенных страницах: 0 errors. Остались только стандартные dev warnings React Router/Vite.
- Повторная проверка login/proxy на текущем запуске перед Terminal Linux settings pass: `http://127.0.0.1:9000/api/auth/csrf/` = 200, `http://localhost:8080/api/auth/csrf/` = 200, POST `/api/auth/login/` с CSRF через `localhost:8080` = 200, UI login `lunix/1414` перешел на `/servers/hub`, browser console errors = 0. Если снова виден `500` при пустой Django console, это Vite proxy/dev-server слой, а не Django view.
- Повторный `npm run build` после Linux workspace/settings localization правок прошел.
- Browser smoke на `/servers/hub`: UI login, Linux workspace, settings app desktop/mobile screenshots, старые checked mixed strings absent, browser console errors = 0.
- Повторный `npm run build` после Terminal SFTP/Quick Run/Text Editor/backend execute правок прошел.
- Direct backend smoke: `POST http://localhost:8080/servers/api/24/execute/` с валидным CSRF вернул `200` и `{"stdout":"lunix\n","exit_code":0}`.
- Browser smoke на `/servers/hub`: clean reload, Linux workspace, Quick Run `whoami`, SFTP `.bashrc` -> `Редактировать`, Text Editor opened read-only without save, browser console errors = 0.
- Повторный `npm run build` после FileEditorModal accessibility/localization правок прошел.
- Повторный `npm run build` после SFTP selected action grid правки прошел.
- Static scan после FileEditorModal правок не нашел старые `title="Minimize|Maximize|Restore|Close"` и подтвердил наличие новых `editor.*` ключей в `ru/en`.
- Browser smoke на отдельном Vite `127.0.0.1:5173`: login, `/servers/hub`, SFTP, `.bashrc` -> `Редактировать`; browser console errors = 0 до момента закрытия Browser MCP transport. Live SFTP открыл текущий Linux Text Editor, не legacy `FileEditorModal`.
- Post-patch SFTP screenshot после grid правки не снят: Browser MCP transport закрылся. Не подменял проверку другим браузером; следующий pass должен переснять selected action panel.

## Осталось в следующем проходе

- Продолжить проверку оставшихся creation dialogs и data-vs-UI labels, где часть строк намеренно остается технической (provider brands, model ids).
- Проверить оставшиеся SFTP edge cases отдельно: chown под пользователем без root, длинные пути, массовые upload/download transfers и ошибки permission denied.
- Продолжить accessibility pass: keyboard focus, dialog focus trap, disabled states и оставшиеся aria labels за пределами Settings Permissions.
- Проверить runtime trigger для legacy `FileEditorModal` через terminal file-link interceptor; SFTP сейчас открывает Linux Text Editor, поэтому FileEditorModal пока подтвержден static/build checks.
- Повторить DOM-level SFTP accessibility pass, когда Browser MCP стабилен: snapshot группирует `Редактировать/Скачать` под row button, хотя текущий `SftpPanel.tsx` держит row button и action buttons sibling-элементами.
- Проверить long-content/mobile scroll для Pipeline node config panels после добавления сложных нод.
- Разобрать data-vs-UI localization: часть английских строк приходит из mock/API данных и должна переводиться отдельно от статического UI.

## Артефакты

Все screenshots и snapshots лежат рядом с этим файлом в `outputs/product-design-platform-audit/`.
