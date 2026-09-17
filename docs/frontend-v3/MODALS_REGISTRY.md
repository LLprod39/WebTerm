# frontend-v3 — реестр диалогов / drawer / confirm

Источник: инвентарь старого `frontend/` + решения UI_SPEC.  
Типы: `Dialog` · `ConfirmDialog` · `PromptDialog` · `Drawer` · `Toast` · `UnsavedChangesDialog`.  
Typed-confirm = поле «введите имя» перед destructive submit.

---

## Shell / system

| ID | Раздел | Тип | Триггер | Title | Поля | Кнопки | API | Typed? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SYS-01 | Shell | Dialog | Ctrl+K | Команды | search | — (выбор пункта) | session, bootstrap | — |
| SYS-02 | Any | Toast | mutation ok/err | — | — | — | — | — |
| SYS-03 | Drawer* | UnsavedChangesDialog | close dirty | Несохранённые изменения | — | Остаться / Сбросить | — | — |
| SYS-04 | Auth | — (page) | session fail | — | — | Повторить | session | — |

---

## Servers

| ID | Раздел | Тип | Триггер | Title | Поля | Кнопки | API | Typed? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SRV-01 | Servers | Drawer | Добавить / Изменить | Новый SSH-хост / Изменить сервер | name*, host*, port, username*, auth_method, password, private_key+upload, sudo_auth_mode, sudo_password*, group, tags, notes | Отмена · Тест · Сохранить и проверить · Создать/Сохранить | createServer, updateServer, testServer | — |
| SRV-02 | Servers | ConfirmDialog | Удалить row | Удалить {name}? | — (typed если есть active sessions) | Отмена · Удалить | deleteServer | если sessions |
| SRV-03 | Servers | Drawer | Создать группу | Новая группа / Изменить группу | name*, description, color | Отмена · Создать/Сохранить · Правила | createServerGroup, updateServerGroup | — |
| SRV-04 | Servers | ConfirmDialog | Удалить группу | Удалить группу {name}? | — | Отмена · Удалить | deleteServerGroup | — |
| SRV-05 | Servers | Dialog lg | Дополнительно | {server.name} — дополнительно | tabs: access / knowledge / context / security / execute | Закрыть | shares, memory, context, master password, execute | — |
| SRV-05a | Servers | Dialog | Knowledge create/edit | Заметка / AI-знание | title, category, content, active | Отмена · Сохранить | server-memory | — |
| SRV-05b | Servers | ConfirmDialog | Knowledge delete | Удалить запись? | — | Отмена · Удалить | server-memory | — |
| SRV-06 | Servers | Dialog md | Host key unknown | Неизвестный SSH host key | fingerprint (mono), algorithm, confirm fingerprint input | Отмена · Подтвердить | testServer / enroll | fingerprint match |

---

## Terminal / Files

| ID | Раздел | Тип | Триггер | Title | Поля | Кнопки | API | Typed? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TERM-01 | Terminal | Dialog | New tab / hub | Выбрать сервер | list / search | Отмена · Открыть | bootstrap | — |
| TERM-02 | Terminal | ConfirmDialog | Close tab | Закрыть вкладку? | — | Отмена · Закрыть | — | — |
| TERM-03 | Files | PromptDialog | Папка | Новая папка | name* | Отмена · Создать | mkdir | — |
| TERM-04 | Files | PromptDialog | Rename | Переименовать | name* | Отмена · Сохранить | rename/write | — |
| TERM-05 | Files | ConfirmDialog | Delete entry | Удалить {name}? | — | Отмена · Удалить | delete | — |
| TERM-06 | Terminal | Dialog md | AI settings | Настройки AI-панели | auto-report, prefs switches | Сбросить · Очистить память · Сохранить | terminal-preferences / AI prefs | — |
| TERM-07 | Terminal | Dialog lg | File editor intercept | Редактор: {path} | textarea | Отмена · Сохранить | files write | — |
| TERM-08 | Terminal | Dialog md | Terminal prefs | Настройки терминала | theme, bg, font, size, line-height, cursor, blink, scrollback, intercept | Отмена · Сохранить | terminal-preferences | — |

---

## Agents

| ID | Раздел | Тип | Триггер | Title | Поля | Кнопки | API | Typed? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AGT-01 | Agents | Dialog lg (wizard) | Создать / Изменить | Новый агент | 5 steps: template, basics, servers, capabilities, review | Назад · Далее · Отмена · Сохранить · Сохранить и запустить | createAgent, updateAgent, runAgent | — |
| AGT-02 | Agents | ConfirmDialog | Удалить | Удалить агента {name}? | — | Отмена · Удалить | deleteAgent | — |
| AGT-03 | Agents | Dialog md | After run | Отчёт запуска | read-only summary | Закрыть · Открыть run | — | — |
| AGT-04 | Agent Run | ConfirmDialog | Approve / Stop / Cleanup | Подтвердить действие | — | Отмена · Подтвердить | approvePipelinePlan, stopAgent, cleanup | — |
| AGT-05 | Agent Run | — (inline form) | Pending question | — | reply text | Отправить | replyToAgent | — |

---

## Automation / Playbooks

| ID | Раздел | Тип | Триггер | Title | Поля | Кнопки | API | Typed? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| AUT-01 | Automation | Dialog lg | Import | Импорт playbook | mode tabs yaml/archive/gitlab; file; URL/token/branch; name/category/desc | Отмена · Preview · Commit | playbook-bundles | — |
| AUT-02 | Automation | Dialog | Bindings create/edit | Профиль привязки | name, servers, groups | Отмена · Сохранить | playbook workspace | — |
| AUT-03 | Automation | ConfirmDialog | Binding delete | Удалить профиль? | — | Отмена · Удалить | — | — |
| AUT-04 | Automation | Dialog | Sharing grant | Выдать доступ | user, role/capabilities | Отмена · Сохранить | — | — |
| AUT-05 | Automation | ConfirmDialog | Sharing revoke | Отозвать доступ? | — | Отмена · Отозвать | — | — |
| AUT-06 | Automation | Dialog lg | Revision detail | Ревизия {id} | diff read-only | Закрыть | — | — |
| AUT-07 | Automation | ConfirmDialog | Publish / rollback / delete rev | Подтвердить? | — | Отмена · Подтвердить | — | — |
| AUT-08 | Automation | Dialog | GitLab refresh | Обновить из GitLab | credentials/options | Отмена · Обновить | — | — |
| AUT-09 | Automation | ConfirmDialog / Unsaved | Leave dirty / delete playbook | Несохранённые / Удалить playbook? | — | … | — | delete playbook optional typed |
| AUT-10 | Automation | — (page wizard) | Run | Запуск | 2 steps essentials+targets / review | Назад · Далее · Запустить | validate + run | — |

---

## Studio

| ID | Раздел | Тип | Триггер | Title | Поля | Кнопки | API | Typed? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| STU-01 | Studio | Dialog sm | Create pipeline | Новый пайплайн | icon, name*, description | Отмена · Создать | studioPipelines.create | — |
| STU-02 | Studio | Dialog md | Manual trigger | Запуск | entry node Select | Отмена · Открыть редактор · Запустить | run | — |
| STU-03 | Studio | Dialog md | Trigger info | Триггеры | webhook URL, cron, filters (read-only+copy) | Закрыть · Открыть редактор | — | — |
| STU-04 | Studio | ConfirmDialog | Delete pipeline | Удалить пайплайн {name}? | — | Отмена · Удалить | delete | — |
| STU-05 | Editor | Dialog lg | Run pipeline | Запуск пайплайна | mode: manual/webhook/schedule/monitoring; task; advanced JSON | Отмена · Validate · Run · Save trigger | studio run | — |
| STU-06 | Drafts | ConfirmDialog | Discard / apply | Применить / Отклонить черновик? | — | Отмена · Подтвердить | drafts | — |
| STU-07 | Agents cfg | Drawer | Create/edit | Конфиг агента | form fields | Отмена · Сохранить | studioAgents | — |
| STU-08 | Agents cfg | ConfirmDialog | Delete | Удалить конфиг? | — | Отмена · Удалить | — | — |
| STU-09 | Skills | Dialog | Create skill | Новый skill | name, slug, description, template | Отмена · Создать | studioSkills | — |
| STU-10 | Skills | Dialog | Create file | Новый файл | path/name, kind | Отмена · Создать | — | — |
| STU-11 | Skills | Dialog | Validation | Отчёт валидации | read-only | Закрыть | — | — |
| STU-12 | Skills | Unsaved / Confirm | Leave / delete file | … | — | … | — | — |
| STU-13 | MCP | Drawer | Create/edit | MCP-сервер | name, transport, command/url, env, share | Отмена · Сохранить · Тест | studioMCP | — |
| STU-14 | MCP | ConfirmDialog | Delete | Удалить MCP-сервер? | — | Отмена · Удалить | — | — |

---

## Chat

| ID | Раздел | Тип | Триггер | Title | Поля | Кнопки | API | Typed? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CHT-01 | Chat | — (inline card) | confirm_required WS | Подтверждение действия | typed phrase (если требуется) | Отмена · Подтвердить | WS confirm | иногда |
| CHT-02 | Chat | Sheet/Dialog mobile | History | Чаты | list | Закрыть | assistant-chat | — |

---

## Mars

| ID | Раздел | Тип | Триггер | Title | Поля | Кнопки | API | Typed? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| MRS-01 | Mars | — (page wizard) | New session | Интервью | step fields | Назад · Далее · Запустить | marsApi | — |

---

## Kubernetes

| ID | Раздел | Тип | Триггер | Title | Поля | Кнопки | API | Typed? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| K8S-01 | K8s | Drawer | Ask Agent | Диагностика | prompt | Отмена · Отправить | diagnosis draft | — |
| K8S-02 | K8s | Dialog lg | Helm | Helm install | chart, values, ns | Отмена · Далее · Установить | helm | — |
| K8S-03 | K8s | ConfirmDialog | Action approve | Подтвердить действие? | — | Отмена · Подтвердить | action requests | — |

---

## Settings

| ID | Раздел | Тип | Триггер | Title | Поля | Кнопки | API | Typed? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| SET-01 | Users | Drawer | Create/edit | Пользователь | username*, email, password*, profile, groups, active | Отмена · Создать/Сохранить | access users | — |
| SET-02 | Users | Dialog sm | Reset password | Сброс пароля | password*, confirm* | Отмена · Сохранить | — | — |
| SET-03 | Users | ConfirmDialog | Delete user | Удалить пользователя {name}? | typed name | Отмена · Удалить | — | да |
| SET-04 | Groups | Drawer | Create/edit | Группа доступа | name, description, members | Отмена · Сохранить | access groups | — |
| SET-05 | Groups | ConfirmDialog | Delete | Удалить группу? | — | Отмена · Удалить | — | — |
| SET-06 | Permissions | Drawer | Exception | Исключение | subject, permission, scope | Отмена · Сохранить | permissions | — |
| SET-07 | Permissions | ConfirmDialog | Delete exception | Удалить исключение? | — | Отмена · Удалить | — | — |
| SET-08 | AI Connections | ConfirmDialog | Revoke / delete grant | Отозвать подключение? | — | Отмена · Отозвать | aiProviders | optional typed |
| SET-09 | Memory | ConfirmDialog | Purge | Очистить память сервера? | typed | Отмена · Очистить | server-memory | да |
| SET-10 | Appearance | — (inline) | Theme | — | theme toggle in sidebar | — | local | — |

---

## Plugins

| ID | Раздел | Тип | Триггер | Title | Поля | Кнопки | API | Typed? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PLG-01 | Plugins | ConfirmDialog | Disable / revoke perm | Отключить плагин / Отозвать право? | — | Отмена · Подтвердить | plugins API | — |
| PLG-02 | Plugins | Dialog | Install local | Установить пакет | file | Отмена · Установить | — | — |

---

## Убрано относительно старого фронта

| Старое | Решение |
| --- | --- |
| `window.confirm` / `window.prompt` | → ConfirmDialog / PromptDialog |
| NotificationCenter sheet (monitoring+runs mix) | упростить: только реальные алерты API или убрать до P2 |
| UI style dropdown (flow/enterprise/ashita) | убрать; только dark/light |
| AssistantDrawer из chrome | только раздел `/chat` |
| HotkeyCheatsheet overlay | опционально позже; не блокер |
| ConnectionBanner marketing | заменить на InlineError/LiveIndicator |

Итого учтённых ID: **~55**. Детали полей — в соответствующих `screens/*.md`.
