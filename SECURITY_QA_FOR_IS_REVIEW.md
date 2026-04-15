# WebTerm / WEU AI Platform — Вопросы и ответы для ИБ

> **Цель документа**: подготовка к встрече с Информационной Безопасностью (ИБ).  
> Документ содержит примерные вопросы, которые может задать ИБ, и развёрнутые ответы с отсылками к конкретным модулям кода.  
> Составлен на основе полного аудита кодовой базы **15 апреля 2026 г.**

---

## Содержание

1. [Общая архитектура и поверхность атак](#1-общая-архитектура-и-поверхность-атак)
2. [Аутентификация и авторизация](#2-аутентификация-и-авторизация)
3. [Хранение учётных данных и шифрование](#3-хранение-учётных-данных-и-шифрование)
4. [AI/LLM — потоки данных и промпты](#4-aillm--потоки-данных-и-промпты)
5. [SSH/RDP: терминал и доступ к серверам](#5-sshrdp-терминал-и-доступ-к-серверам)
6. [AI-агенты: исполнение, права и ограничения](#6-ai-агенты-исполнение-права-и-ограничения)
7. [AI Memory: что хранится, куда попадает](#7-ai-memory-что-хранится-куда-попадает)
8. [Файловые операции и SFTP](#8-файловые-операции-и-sftp)
9. [MCP-интеграции](#9-mcp-интеграции)
10. [Сетевая безопасность и транспорт](#10-сетевая-безопасность-и-транспорт)
11. [Аудит и журналирование](#11-аудит-и-журналирование)
12. [Desktop-клиент](#12-desktop-клиент)
13. [Продакшен-защита](#13-продакшен-защита)
14. [Известные ограничения и риски](#14-известные-ограничения-и-риски)
15. [Рекомендации по усилению](#15-рекомендации-по-усилению)

---

## 1. Общая архитектура и поверхность атак

### В: Что это за система и для чего она используется?

**О:** WebTerm (WEU AI Platform) — операционная платформа для работы с серверной инфраструктурой. Она объединяет:

- **Инвентарь серверов** (CRUD, группы, теги, shares)
- **Web-терминал** (SSH/RDP через WebSocket)
- **AI-ассистент** в терминале (генерация/выполнение команд)
- **AI-агенты** (автономные задачи по серверам)
- **Studio** (визуальные pipelines, MCP, skills)
- **Мониторинг** (health checks, alerts, watchers)
- **Долговременная AI-память** по серверам
- **Desktop-клиент** (WinUI 3)

### В: Какой технический стек?

| Компонент | Технология |
|---|---|
| Backend | Django 5 + Channels + Daphne (ASGI) |
| Realtime | WebSocket через Django Channels |
| Frontend | React 18 + TypeScript + Vite (SPA) |
| Desktop | WinUI 3 + WebView2 |
| БД | SQLite (dev) / PostgreSQL (prod) |
| Очереди | Celery + Redis |
| WebSocket layer | InMemoryChannelLayer (dev) / Redis (prod) |
| LLM | Gemini, OpenAI, Anthropic (Claude), Grok, Ollama |

### В: Какие внешние сетевые подключения делает платформа?

**О:** Платформа инициирует следующие исходящие соединения:

| Направление | Протокол | Назначение |
|---|---|---|
| SSH-серверы пользователя | TCP/SSH (порт 22+) | Терминал, агенты, мониторинг |
| RDP-серверы пользователя | TCP/RDP (порт 3389+) | RDP-сессии |
| LLM провайдеры (API) | HTTPS | Запросы к AI (Gemini/OpenAI/Claude/Grok) |
| SMTP-сервер | TLS/SMTP | Email-уведомления |
| Telegram API | HTTPS | Telegram-уведомления |
| MCP-серверы (опционально) | stdio / HTTPS (SSE) | Интеграция с внешними инструментами |
| Redis | TCP (6379) | Message broker (prod) |

> [!IMPORTANT]
> Платформа **не имеет** входящих интеграций за пределами HTTP(S)/WebSocket и webhook-эндпоинтов Studio.

---

## 2. Аутентификация и авторизация

### В: Как пользователи проходят аутентификацию?

**О:** Поддерживаются три механизма:

1. **Django session auth** (логин/пароль через `/api/auth/login/`) — основной механизм.
2. **Domain SSO / LDAP** — через middleware `DomainAutoLoginMiddleware` (`core_ui/domain_auth.py`):
   - Доверенный заголовок (по умолчанию `REMOTE_USER`, настраивается через `DOMAIN_AUTH_HEADER`)
   - Требует включения через `DOMAIN_AUTH_ENABLED=true`
   - Может автоматически создавать пользователей (`DOMAIN_AUTH_AUTO_CREATE`)
   - Поддерживает LDAP/AD через `django-auth-ldap` (bind DN + search filter)
3. **Desktop refresh tokens** — модель `DesktopRefreshToken` с TTL и hash-ем (`core_ui/models.py`).

### В: Как устроена авторизация (RBAC/permissions)?

**О:** Многоуровневая система:

| Уровень | Механизм | Модуль |
|---|---|---|
| **Feature permissions** | `UserAppPermission` / `GroupAppPermission` — per-user/per-group флаги на каждый раздел (servers, agents, studio, settings и т.д.) | `core_ui/models.py` |
| **Staff-only зоны** | Admin dashboard доступен только для `is_staff=True` | `core_ui/views.py` |
| **Server ownership** | Каждый сервер привязан к `user` (FK) | `servers/models.py` |
| **Server sharing** | Явный шаринг через `ServerShare` с возможностью отзыва и TTL | `servers/models.py` |
| **Group roles** | `owner`, `admin`, `member`, `viewer` через `ServerGroupMember` | `servers/models.py` |
| **Granular group perms** | `ServerGroupPermission`: `can_view`, `can_execute`, `can_edit`, `can_manage_members` | `servers/models.py` |
| **Domain profiles** | Автосоздаваемые пользователи получают профиль `server_only` (только серверы) | `core_ui/domain_auth.py` |

### В: Какие feature-флаги существуют?

**О:** 13 feature-флагов контролируют доступ к разделам SPA:

```
servers, dashboard, agents, studio, studio_pipelines, studio_runs,
studio_agents, studio_skills, studio_mcp, studio_notifications,
settings, orchestrator, knowledge_base
```

По умолчанию обычные пользователи имеют доступ к: `servers`, `agents`, `knowledge_base`.
`dashboard` — staff-only.

### В: Как защищены WebSocket-соединения?

**О:** Два механизма:

1. **Session cookie** — стандартная Django session auth через Channels middleware.
2. **WS token** — короткоживущий signed token (TTL = 5 минут) для случаев, когда proxy не пробрасывает cookie:
   - Генерируется через `/api/auth/ws-token/`
   - Подписывается `TimestampSigner` с salt `ws-token`
   - Передаётся как `?ws_token=...` в query string
   - Код: `SSHTerminalConsumer._resolve_ws_token_user()` в `servers/consumers.py`

### В: Есть ли защита от bruteforce?

**О:** Django встроенно ограничивает через `AUTH_PASSWORD_VALIDATORS` (минимальная длина, словарь, числовой пароль, сходство с username). Отдельного rate-limiting на login endpoint **на текущий момент нет** — рекомендуется добавить через middleware или WAF.

---

## 3. Хранение учётных данных и шифрование

### В: Как хранятся пароли серверов (SSH/RDP)?

**О:** Двухслойная система шифрования:

#### Слой 1: Managed Secrets (основной, рекомендуемый)
- Модель `ManagedSecret` в `core_ui/models.py`
- Шифрование через **Fernet** (AES-128-CBC + HMAC-SHA256)
- Ключ шифрования: `SHA256(MANAGED_SECRET_KEY || ":managed-secret:v1")`
- Fallback ключа: `APP_SECRET_ENCRYPTION_KEY` → `SECRET_KEY`
- Секрет хранится как encrypted JSON blob в поле `ciphertext`
- Код: `core_ui/managed_secrets.py`

#### Слой 2: Legacy encrypted_password (PBKDF2 + Fernet)
- Мастер-пароль пользователя → PBKDF2-HMAC-SHA256 (100 000 итераций, random 16-byte salt) → Fernet key
- Зашифрованный пароль в `Server.encrypted_password`, salt в `Server.salt`
- Код: `passwords/encryption.py`

```
Цепочка расшифровки:
1. Ищем ManagedSecret (по server_id) → decrypt через server key
2. Если нет → decrypt encrypted_password через master_password + salt
3. Если master_password не задан → fallback на plain_password из WS-сообщения (только для connect)
```

### В: Видят ли AI-агенты пароли серверов?

**О:** **Нет.** AI-агенты **никогда** не получают пароли в промптах. Расшифровка происходит:
- В `SSHTerminalConsumer._resolve_server_secret()` — на уровне WebSocket consumer
- В `ssh_host_keys.build_server_connect_kwargs()` — при построении SSH connection kwargs

Пароль передаётся напрямую в `asyncssh.connect(password=...)` и **никогда** не попадает ни в prompt, ни в логи, ни в AI memory.

### В: Как хранится мастер-пароль?

**О:** Мастер-пароль **не хранится** на сервере. Он передаётся:
- Через WebSocket при connect (`master_password` в payload)
- Через переменную окружения `MASTER_PASSWORD` (fallback)
- Через session (после set через `/servers/api/master-password/set/`)

Master password хранится в Django session (server-side) и НЕ пишется в БД.

### В: Какие ещё секреты хранятся?

| Секрет | Хранение | Шифрование |
|---|---|---|
| Пароли серверов | `ManagedSecret` + legacy `encrypted_password` | Fernet AES + PBKDF2 |
| MCP env-переменные | `ManagedSecret` (namespace=`mcp_secret_env`) | Fernet AES |
| LLM API ключи | `.env` файл (не в БД) | Нет (файл вне git) |
| Django SECRET_KEY | `.env` файл | Нет |
| LDAP bind password | `.env` файл | Нет |
| SMTP password | `.env` файл | Нет |
| Telegram bot token | `.env` файл | Нет |
| Desktop refresh tokens | `DesktopRefreshToken.token_hash` | SHA256 hash (не plain) |

### В: Могут ли пользователи раскрыть (reveal) пароль?

**О:** Да, через API `/servers/api/<id>/reveal-password/` — **но только** при предъявлении корректного master_password. Без master_password расшифровка невозможна.

---

## 4. AI/LLM — потоки данных и промпты

### В: Какие данные отправляются в LLM-провайдеры?

**О:** Данные, попадающие во внешние LLM:

```mermaid
flowchart LR
    A["Запрос пользователя"] --> B["System prompt\n(role, rules, context)"]
    C["Контекст сервера\n(notes, knowledge,\ncorporate_context)"] --> B
    D["Последние команды\nиз terminal tail"] --> B
    E["AI Memory\n(canonical snapshots)"] --> B
    F["Global rules +\nGroup rules +\nForbidden commands"] --> B
    B --> G["LLM Provider API\n(Gemini/OpenAI/Claude/Grok)"]
    G --> H["Ответ: команды/текст"]
```

#### Что **отправляется** в LLM:
1. **Текст запроса** пользователя (ai_request message)
2. **System prompt** с ролью и инструкциями
3. **Terminal tail** — последние ~100 строк вывода терминала (для контекста)
4. **Server metadata**: имя, host, port, ОС-информация, notes, corporate_context
5. **Global/group rules**: правила и forbidden commands
6. **Server knowledge**: заметки (ручные + AI-генерированные)
7. **AI Memory snapshots**: canonical sections (profile, access, risks, runbook, recent_changes) — **уже прошедшие redaction**
8. **Operational recipes** (если есть релевантные)
9. **Agent task goal** (для server agents)

#### Что **НЕ отправляется** в LLM:
- ❌ Пароли серверов
- ❌ SSH ключи
- ❌ API ключи LLM
- ❌ Мастер-пароль
- ❌ MCP env-переменные (секретные)
- ❌ Content других пользователей (каждый пользователь видит только свои серверы)
- ❌ Raw output команд в полном объёме (обрезается)

### В: Есть ли защита от утечки секретов через промпты?

**О:** Да, многоуровневая система redaction в `app/agent_kernel/memory/redaction.py`:

#### Паттерны автоматического удаления из текста:
| Паттерн | Пример | Замена |
|---|---|---|
| PEM-блоки | `-----BEGIN PRIVATE KEY-----...` | `[REDACTED:pem_block]` |
| Bearer tokens | `Bearer eyJ...` | `[REDACTED:bearer_token]` |
| Auth headers | `Authorization: Basic ...` | `[REDACTED:auth_header]` |
| Connection strings | `postgres://user:pass@host` | `[REDACTED:connection_string]` |
| Secret assignments | `password=abc123` | `[REDACTED:secret_assignment]` |
| SSH inline keys | `ssh-rsa AAAA...` | `[REDACTED:private_key_inline]` |
| AWS access keys | `AKIA1234567890ABCDEF` | `[REDACTED:aws_access_key]` |
| GitHub PAT | `ghp_xxxxx...` | `[REDACTED:github_pat]` |
| OpenAI API key | `sk-proj-xxxxx...` | `[REDACTED:openai_api_key]` |
| GitLab PAT | `glpat-xxxxx...` | `[REDACTED:gitlab_pat]` |
| Slack tokens | `xoxb-xxxxx...` | `[REDACTED:slack_token]` |
| Azure SAS tokens | `sv=...&sig=...` | `[REDACTED:azure_sas_token]` |

#### Анти-prompt-injection:
| Паттерн | Пример |
|---|---|
| Instructional content | `ignore all previous instructions`, `you are ChatGPT`, `system prompt`, `follow these instructions` |
| Observation control | `system:`, `[developer]`, `<system>`, `Thought:`, `Action:`, `tool call` |
| Prompt context control | `role: system`, `respond with` |

Обнаруженные строки заменяются на `[FILTERED:instructional_content]` или `[FILTERED:prompt_injection_content]`.

Каждый обнаруженный секрет хешируется (SHA256[:16]) и записывается в `redaction_report` + `redaction_hashes` для аудита.

### В: Проходит ли prompt context через sanitization перед отправкой в LLM?

**О:** Да. В `app/agent_kernel/runtime/context.py` функция `build_ops_prompt_context()` пропускает все блоки через `sanitize_prompt_context_text()`, которая применяет:
1. `redact_text()` — удаление секретов
2. `sanitize_observation_text()` — фильтрация prompt injection
3. Дополнительная фильтрация control-line patterns

### В: Логируются ли LLM-запросы?

**О:** Да. Каждый запрос к LLM фиксируется в:
- `LLMUsageLog` — провайдер, модель, user, input/output tokens, duration, status
- `UserActivityLog` — через `log_llm_activity()` с деталями prompt/response

Администратор видит использование на дашборде: стоимость, requests/day, top users.

---

## 5. SSH/RDP: терминал и доступ к серверам

### В: Как устроено SSH-подключение?

**О:** 
1. Пользователь открывает WebSocket к `/ws/servers/<server_id>/terminal/`
2. `SSHTerminalConsumer` проверяет auth (session или WS token)
3. Проверяет, что пользователь владеет сервером или имеет share
4. Проверяет feature permission `servers`
5. Проверяет лимит сессий (`SSH_TERMINAL_SESSIONS_PER_USER_LIMIT=12`, global=120)
6. Расшифровывает пароль/ключ через `secret_utils.get_server_auth_secret()`
7. Выполняет SSH host key verification (TOFU)
8. Подключается через `asyncssh.connect()`
9. Все I/O идёт через WebSocket ↔ SSH shell

### В: Есть ли SSH host key verification?

**О:** Да. Реализован TOFU (Trust On First Use):
- При первом подключении host key сохраняется в `Server.trusted_host_keys` (JSON)
- При последующих подключениях ключ проверяется через `asyncssh.SSHKnownHosts`
- Поддерживаются алгоритмы: RSA, ED25519, ECDSA
- Fingerprint SHA256 сохраняется для аудита
- Код: `servers/ssh_host_keys.py`

### В: Какие защиты от опасных команд?

**О:** Несколько уровней:

1. **Dangerous command detection** (`app/tools/safety.py`):
   ```
   rm -rf, rm -r, mkfs.*, dd if=, shutdown, reboot,
   systemctl stop/disable/mask/poweroff/halt,
   service ... stop, truncate -s 0
   ```
   AI-ассистент помечает такие команды как `requires_confirm: true`.

2. **User confirmation** — по умолчанию включено (`confirm_dangerous_commands: true`). Пользователь должен явно подтвердить опасную команду.

3. **Forbidden commands** — три уровня запретов:
   - Global: `GlobalServerRules.forbidden_commands`
   - Group: `ServerGroup.forbidden_commands`
   - Server: через notes/context

4. **Allowlist/blocklist patterns** — per-session настройки `allowlist_patterns` и `blocklist_patterns`.

5. **Memory heuristics** — фильтрация trivial команд (`clear`, `pwd`, `cd`, `ls`, `echo`) через `servers/memory_heuristics.py`.

### В: Может ли один пользователь видеть терминал другого?

**О:** **Нет.** Каждая WebSocket-сессия привязана к конкретному `user_id`. Consumer проверяет:
- `Server.user == request.user` (владелец)
- Или наличие `ServerShare` (активный, не отозванный, не expired)
- Feature permission `servers` включен

Нет механизма «shared terminal» — каждый пользователь получает свой SSH-shell.

---

## 6. AI-агенты: исполнение, права и ограничения

### В: Что могут делать AI-агенты на серверах?

**О:** AI-агенты выполняются через `servers/agent_engine.py` и `servers/multi_agent_engine.py`. Их capabilities:

| Tool | Возможность |
|---|---|
| `ssh_execute` | Выполнение SSH-команды на сервере |
| `read_console` | Чтение последнего вывода терминала |
| `send_ctrl_c` | Отправка Ctrl+C |
| `open_connection` | Открытие SSH-соединения |
| `close_connection` | Закрытие SSH-соединения |
| `wait_for_output` | Ожидание вывода |
| `report` | Отправка отчёта оператору |
| `ask_user` | Вопрос оператору (Human-in-the-Loop) |
| `analyze_output` | Анализ вывода |

### В: Какие ограничения есть у агентов?

**О:**

| Ограничение | Значение | Настройка |
|---|---|---|
| Max active runs per user | 5 | `AGENT_ACTIVE_RUNS_PER_USER_LIMIT` |
| Max active runs global | 25 | `AGENT_ACTIVE_RUNS_GLOBAL_LIMIT` |
| Max iterations per run | Настраивается per-agent | `ServerAgent.max_iterations` |
| Session timeout | Настраивается | `ServerAgent.timeout` |
| Dangerous command check | Да | `is_dangerous_command()` |
| Forbidden commands check | Да | Global + Group rules |
| Human approval flow | Да | `ask_user`, `approve_plan` |
| Run stop by user | Да | `/servers/api/agents/<id>/stop/` |
| Tool registry restriction | Да | `allowed_tools` per agent config |

### В: Может ли агент выполнить действие без ведома оператора?

**О:** Зависит от конфигурации:
- **mini mode** — агент выполняет предопределённый список команд
- **full mode** — агент сам выбирает команды, но:
  - Все опасные команды проходят через `is_dangerous_command()` check
  - Оператор может настроить `execution_mode: step` для пошагового подтверждения
  - Агент может задать вопрос через `ask_user` (Human-in-the-Loop)
  - Агент может запросить одобрение плана через `approve_plan`
- **multi mode** — оркестрация нескольких серверов, те же ограничения

### В: Знают ли агенты пароли серверов?

**О:** **Нет.** Агенты используют SSH-инструменты (`SSHConnectTool`, `SSHExecuteTool`), которые:
1. Получают server_id
2. Внутри runtime расшифровывают пароль через `get_server_auth_secret()`
3. Передают его напрямую в `asyncssh.connect()`
4. Пароль **не входит** ни в prompt, ни в tool call kwargs, ни в agent memory

---

## 7. AI Memory: что хранится, куда попадает

### В: Что хранит AI Memory?

**О:** Многоуровневая система:

| Уровень | Модель | Содержимое |
|---|---|---|
| **L0 — Events** | `ServerMemoryEvent` | Сырые события: open/close сессии, выполненные команды, agent results, мониторинг. Текст проходит `redact_for_storage()`. |
| **L1 — Episodes** | `ServerMemoryEpisode` | Компактированные группы событий (terminal session, agent run, incident). |
| **L2 — Snapshots** | `ServerMemorySnapshot` | Canonical memory: `profile`, `access`, `risks`, `runbook`, `recent_changes`, `human_habits`. |
| **Revalidation** | `ServerMemoryRevalidation` | Очередь устаревших/конфликтных фактов. |

### В: Какие данные попадают в AI Memory?

**О:** Источники:

1. **Terminal sessions**: open/close events, команды (после фильтрации heuristics)
2. **Agent runs**: summary, events, results
3. **Monitoring**: health checks, alerts
4. **Watchers**: draft-предложения
5. **Manual knowledge**: заметки пользователя
6. **Terminal AI extraction**: durable facts (профиль сервера, риски)

> [!IMPORTANT]
> **Все** данные перед записью в memory проходят через `redact_for_storage()`:
> - Удаление секретов (passwords, tokens, keys, connection strings)
> - Нейтрализация prompt injection
> - Генерация redaction report + SHA256 hashes для аудита

### В: Кто может видеть AI Memory?

**О:** 
- **Владелец сервера** — через Settings → AI Memory в UI
- **Администратор** (`is_staff`) — через admin dashboard
- **AI-агенты этого пользователя** — через prompt (canonical snapshots → ServerMemoryCard)
- **Другие пользователи** — **НЕТ** (memory привязана к серверу → к пользователю)

### В: Есть ли retention policy?

**О:** Да, настраивается через `ServerMemoryPolicy`:
- `raw_event_retention_days` = 30 (по умолчанию)
- `episode_retention_days` = 90
- Архивация старых events/episodes через `_repair_server_memory_sync()`
- Confidence decay и freshness scoring
- `is_enabled` flag для включения/отключения pipeline

### В: Может ли пользователь удалить свою memory?

**О:** Да:
- Bulk delete snapshots: `/servers/api/<id>/memory/snapshots/bulk-delete/`
- Single snapshot delete: `/servers/api/<id>/memory/snapshots/<id>/delete/`
- Full purge: `/servers/api/<id>/memory/purge/`
- Archive snapshot: `/servers/api/<id>/memory/snapshots/<id>/archive/`

---

## 8. Файловые операции и SFTP

### В: Какие файловые операции доступны?

**О:** Через API `/servers/api/<id>/files/`:
- `list` — листинг директории
- `read` — чтение текстового файла
- `write` — запись текстового файла
- `upload` — загрузка файла (через SFTP)
- `download` — скачивание файла
- `rename`, `delete`, `mkdir`, `chmod`, `chown`

### В: Какие ограничения?

**О:**
- Лимит загрузки: **50 MB** (`FILE_UPLOAD_MAX_MEMORY_SIZE`)
- Файловые операции требуют **активного SSH-подключения** к серверу
- Все операции **логируются** в audit log (если `log_file_operations=true`)
- Пользователь может оперировать **только** своими серверами (или shared)

---

## 9. MCP-интеграции

### В: Что такое MCP в контексте платформы?

**О:** Model Context Protocol — стандарт для tool-серверов. Платформа поддерживает:
- **Studio MCP Registry** (`studio/models.py: MCPServerPool`) — CRUD MCP server definitions
- Транспорты: `stdio` (локальный процесс), `sse` (HTTP SSE endpoint)
- **Standalone MCP** (`key_mcp.py`) — Keycloak MCP bridge

### В: Какие секреты используются MCP?

**О:** MCP env-переменные хранятся в `ManagedSecret` (namespace=`mcp_secret_env`):
- Шифруются при записи через Fernet
- Расшифровываются только при запуске MCP-процесса
- Ключи env-переменных видны в UI (`get_mcp_secret_env_keys`), значения — нет
- Код: `core_ui/managed_secrets.py`

---

## 10. Сетевая безопасность и транспорт

### В: Какие security headers настроены?

**О:** Из `web_ui/settings.py`:

| Header / Setting | Значение (prod) |
|---|---|
| `SECURE_SSL_REDIRECT` | `true` (если HTTPS в SITE_URL) |
| `SECURE_HSTS_SECONDS` | 31536000 (1 год) |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `true` |
| `SECURE_HSTS_PRELOAD` | `true` |
| `SECURE_CONTENT_TYPE_NOSNIFF` | `true` |
| `SECURE_REFERRER_POLICY` | `strict-origin-when-cross-origin` |
| `SECURE_CROSS_ORIGIN_OPENER_POLICY` | `same-origin` |
| `X_FRAME_OPTIONS` | Django default (`DENY`) |
| `SESSION_COOKIE_SECURE` | `true` (prod) |
| `CSRF_COOKIE_SECURE` | `true` (prod) |
| `SESSION_COOKIE_SAMESITE` | `Lax` (или `None` при CROSS_SITE_AUTH) |
| `CSRF_COOKIE_SAMESITE` | `Lax` (или `None` при CROSS_SITE_AUTH) |

### В: Как настроен CORS?

**О:** 
- `CORS_ALLOWED_ORIGINS` — явный список (default: `FRONTEND_APP_URL`)
- `CORS_ALLOW_CREDENTIALS` = `true` (если есть allowed origins)
- В dev добавляются `localhost:8080`, `localhost:8081`
- Код: `web_ui/settings.py`, `corsheaders` middleware

### В: Как защищён CSRF?

**О:**
- Django `CsrfViewMiddleware` включён
- `CSRF_TRUSTED_ORIGINS` — автоматически из `FRONTEND_APP_URL` + `SITE_URL`
- Ngrok: `CsrfTrustNgrokMiddleware` динамически добавляет ngrok-origin
- Фронтенд получает CSRF token через `/api/auth/csrf/`

### В: Есть ли защита Django SECRET_KEY?

**О:** Да:
- В production `DJANGO_DEBUG=false` **требует** задать `DJANGO_SECRET_KEY`
- Проверки: не должен начинаться с `django-insecure-`, длина ≥ 50, уникальных символов ≥ 5
- При нарушении — `ImproperlyConfigured` при старте

---

## 11. Аудит и журналирование

### В: Что журналируется?

**О:** Система `UserActivityLog` + `RequestAuditMiddleware`:

| Категория | Примеры | Флаг |
|---|---|---|
| **Auth** | login, logout, login_failed | `log_auth_events` |
| **Terminal** | terminal_connect, terminal_command, ai_request | `log_terminal_commands` |
| **AI** | chat_request, llm_request, agent_ai_refine | `log_ai_assistant` |
| **Agent** | agent_start, agent_stop, agent_complete | `log_agent_runs` |
| **Pipeline** | pipeline_run, pipeline_stop, node_complete | `log_pipeline_runs` |
| **Server** | server_create, server_update, server_delete | `log_server_changes` |
| **Settings** | settings_update, access_change | `log_settings_changes` |
| **File** | file_upload, file_download, file_delete | `log_file_operations` |
| **MCP** | mcp_test, mcp_tool_call | `log_mcp_calls` |
| **HTTP** | все HTTP-запросы (метод, path, status, duration) | `log_http_requests` |

### В: Какие данные содержатся в логе?

**О:** `UserActivityLog` хранит:
- `user` + `username_snapshot`
- `ip_address`
- `user_agent`
- `category`, `action`, `status`
- `entity_type`, `entity_id`, `entity_name`
- `metadata` (JSON) — детали запроса (sanitized)
- `created_at`

### В: Как sanitize-ятся payload-ы в логах?

**О:** `RequestAuditMiddleware` (`core_ui/middleware.py`):
- Поля `password`, `master_password`, `token`, `secret`, `api_key`, `authorization`, `smtp_password`, `encrypted_password` заменяются на `***`
- Body > 128KB усекается
- Текстовые значения обрезаются до 2000 символов
- Файлы логируются только как metadata (name, size), без содержимого

### В: Есть ли retention для логов?

**О:** Да:
- `retention_days` = 90 (настраивается, 1–3650)
- Автоматическая очистка `UserActivityLog` и `LLMUsageLog` через `maybe_apply_log_retention()`
- Интервал проверки: 1 раз в час
- Код: `core_ui/audit.py`

### В: Можно ли экспортировать логи?

**О:** Поддерживаемые форматы: `json`, `csv`, `syslog`. Настраивается через `export_format` в конфигурации логирования.

---

## 12. Desktop-клиент

### В: Как аутентифицируется desktop-клиент?

**О:** 
- Login через `/api/desktop/v1/auth/login/` → получает `access_token` + `refresh_token`
- Refresh через `/api/desktop/v1/auth/refresh/`
- Refresh token хранится как `SHA256(token)` в `DesktopRefreshToken` (серверная модель)
- TTL, revocation, replaced_by chain — защита от replay attacks
- Код: `core_ui/desktop_api/`

### В: Как хранятся секреты в desktop-клиенте?

**О:** WinUI 3 desktop использует:
- `ProtectedSecretService` — для шифрования локальных секретов
- `SettingsService` — encrypted local settings store
- `LocalServerStoreService` — encrypted server store
- Native `Renci.SshNet` для SSH (без browser WebSocket)

---

## 13. Продакшен-защита

### В: Что нужно настроить для production?

**О:** Обязательные проверки при `DJANGO_DEBUG=false`:

| Проверка | Описание |
|---|---|
| `DJANGO_SECRET_KEY` | Должен быть задан, ≥ 50 символов, не `insecure-` |
| `ALLOWED_HOSTS` | Должен быть задан явно или из SITE_URL |
| `CHANNEL_REDIS_URL` | Обязателен Redis для WebSocket layer |
| `SECURE_SSL_REDIRECT` | auto-true при HTTPS в SITE_URL |
| Cookie security | `SESSION_COOKIE_SECURE=true`, `CSRF_COOKIE_SECURE=true` |
| HSTS | 1 year + include_subdomains + preload |

### В: Какие rate limits настроены?

**О:**

| Ресурс | Лимит per user | Лимит global |
|---|---|---|
| Agent active runs | 5 | 25 |
| Pipeline active runs | 8 | 40 |
| SSH terminal sessions | 12 | 120 |

### В: Какие таймауты настроены?

| SSH | LLM | MCP |
|---|---|---|
| Connect: 10s | Gemini: 90s | stdio init: 20s |
| Login: 20s | Grok: 60s | stdio request: 30s |
| Keepalive: 20s (interval) | Claude: 120s | stdio tool: 120s |
| Keepalive max: 3 (count) | OpenAI: 90s | HTTP connect: 10s |
| Stale session: 180s | OpenAI Responses: 300s | HTTP request: 30s |
| Heartbeat: 30s | Retry attempts: 3 | HTTP tool: 120s |

---

## 14. Известные ограничения и риски

> [!WARNING]
> Следующие пункты — не уязвимости, а области, требующие внимания при развёртывании.

| # | Ограничение | Уровень риска | Комментарий |
|---|---|---|---|
| 1 | Нет login rate-limiting на уровне приложения | Средний | Рекомендуется WAF или django-axes |
| 2 | SQLite в dev не подходит для multi-worker | Низкий (dev only) | В prod используется PostgreSQL |
| 3 | InMemoryChannelLayer в dev не персистирует | Низкий (dev only) | В prod используется Redis |
| 4 | `MASTER_PASSWORD` может быть в env var | Средний | Лучше передавать через session |
| 5 | Ngrok trust middleware автоматически доверяет ngrok origins | Средний (dev only) | В prod ngrok не нужен |
| 6 | `passwords/` app не подключён в INSTALLED_APPS, но код используется | Низкий | Legacy, только encryption модуль |
| 7 | LLM ключи в .env (plaintext) | Средний | Стандартная практика, но можно vault |
| 8 | Memory policy user-level, а не server-level | Низкий | По дизайну, не уязвимость |
| 9 | Desktop client: local encrypted store — зависит от OS-level protection | Средний | Windows DPAPI через ProtectedSecretService |
| 10 | SSH TOFU (Trust On First Use) не защищает от MITM при первом подключении | Низкий | Стандартная практика как у OpenSSH |

---

## 15. Рекомендации по усилению

> [!TIP]
> Рекомендации для обсуждения с ИБ — не блокеры, а potential improvements.

1. **Rate limiting** — добавить `django-axes` или `django-ratelimit` на login/auth endpoints
2. **Secret management** — рассмотреть HashiCorp Vault / AWS Secrets Manager для LLM ключей
3. **Сетевая изоляция** — SSH-подключения к серверам через выделенный bastion/proxy
4. **Content Security Policy** — добавить CSP header для SPA
5. **2FA/MFA** — добавить поддержку TOTP/WebAuthn для критичных пользователей
6. **Audit log export** — настроить syslog для SIEM-интеграции
7. **SSH key rotation** — автоматическая ротация trusted host keys
8. **LLM data residency** — рассмотреть self-hosted Ollama для чувствительных данных вместо cloud LLM
9. **Session timeout** — настроить SESSION_COOKIE_AGE для автоматического логаута
10. **Penetration testing** — провести pen-test на exposed API surface

---

## Резюме для ИБ

| Аспект | Статус |
|---|---|
| Хранение паролей серверов | ✅ Fernet AES + PBKDF2, двухслойное шифрование |
| Пароли не в промптах LLM | ✅ Подтверждено аудитом кода |
| Redaction секретов в AI memory | ✅ 12+ паттернов, SHA256 hash audit trail |
| Anti-prompt-injection | ✅ Фильтрация instructional/control content |
| HTTPS / HSTS / Secure cookies | ✅ Автоматически в prod |
| CORS / CSRF protection | ✅ Явные origin lists + CSRF middleware |
| Audit logging | ✅ Все категории, sanitized payloads, retention |
| Session/resource limits | ✅ Per-user + global limits на SSH, agents, pipelines |
| WebSocket auth | ✅ Session + signed short-lived tokens |
| Server access isolation | ✅ Per-user ownership + explicit sharing |
| Dangerous command detection | ✅ Pattern matching + user confirmation |
| Production hardening | ✅ Mandatory checks при DEBUG=false |
