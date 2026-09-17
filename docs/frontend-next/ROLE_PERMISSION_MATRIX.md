# Roles and permission matrix

Источник: `core_ui/models/access.py` (`FEATURE_CHOICES`), `core_ui/access.py`, `frontend/src/lib/accessUiText.ts` (`ACCESS_FEATURE_META`), FeatureGate в SPA.

Коды прав (**не переименовывать**) — это feature keys API. Подписи в UI локализуются на фронте.

| Key | RU UI | Что открывает |
|---|---|---|
| `servers` | Серверы | `/servers`, терминал; servers CRUD/ops |
| `dashboard` | Панель | `/dashboard` |
| `agents` | Агенты | `/agents`, отчёты запусков |
| `chat` | Чат (ассистент) | `/chat` |
| `automation` | Автоматизация (плейбуки) | `/automation/*` |
| `ai_connections_personal` | AI-подключения (личные) | Settings → AI (личные) |
| `ai_connections_admin` | AI-подключения (админ workspace) | Workspace AI providers (opt-in) |
| `studio` | Студия | `/studio` hub |
| `studio_pipelines` | Студия: Пайплайны | pipeline editor API |
| `studio_runs` | Студия: Запуски | runs API |
| `studio_agents` | Студия: Агент-конфиги | `/api/studio/agents/` |
| `studio_skills` | Студия: Скиллы | skills API |
| `studio_mcp` | Студия: MCP | MCP registry |
| `studio_notifications` | Студия: Уведомления | Studio alerts |
| `kubernetes` | Кубернетес | `/kubernetes*` inventory + approvals |
| `kubernetes_admin_read` | Kubernetes: углублённый просмотр | live YAML/logs/watch (opt-in) |
| `kubernetes_admin_write` | Kubernetes: изменение кластера | apply/patch/scale/delete (opt-in) |
| `kubernetes_break_glass` | Kubernetes: аварийный доступ (exec) | exec/port-forward (opt-in) |
| `kubernetes_secret_read` | Kubernetes: чтение секретов | secret values (opt-in + env) |
| `mars` | MARS (диагностика) | `/mars*` (opt-in) |
| `settings` | Настройки | `/settings/*` (кроме AI-connections) |
| `orchestrator` | Оркестратор (legacy) | legacy tools API (не основной Chat) |
| `knowledge_base` | База знаний | RAG / KB API |
| `web_research` | Веб-исследование (инструмент чата) | chat web tool (opt-in) |

**Opt-in даже для staff** (`EXPLICIT_OPT_IN_FEATURES`): k8s admin/break/secret, mars, web_research, `ai_connections_admin`.

**Профиль «Кастомный»** = `access_profile: "custom"`, не «тип права». Роль «Администратор» = `is_staff`.

**Plugins** в матрице выдачи Users нет (staff + release flag отдельно).

Общие правила: скрытие кнопок ≠ защита backend. 403 виден пользователю, 401 сбрасывает сессию. Tri-state override: inherit / allow / deny.
