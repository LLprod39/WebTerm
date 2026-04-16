# DEVELOPMENT RULES
# WEU AI Platform — правила разработки для людей и AI-агентов

> Этот файл — **обязательное чтение** перед любым изменением проекта.
> AI-агентам (Cascade, Codex, Claude и т.д.) — следовать этим правилам **буквально**, без интерпретации.

---

## 1. ТЕКУЩИЙ СТАТУС АРХИТЕКТУРЫ

### ✅ Что в порядке (не трогать без причины)

| Область | Статус |
|---|---|
| Разделение settings на base / development / production / test | ✅ |
| Cross-context граница servers → studio (через Django Signal) | ✅ |
| SkillProvider Protocol (DI вместо прямого импорта) | ✅ |
| importlinter контракты в `.importlinter` | ✅ |
| ruff + isort в `pyproject.toml` | ✅ |
| i18n → `src/locales/*.json` | ✅ |
| `servers/adapters/`, `servers/services/`, `servers/consumers/` | ✅ |
| `studio/executor/` с NodeRegistry | ✅ |
| `src/api/` пакет (домены) | ✅ |

### ⚠️ Известные нарушения контрактов (зафиксированы, не расширять)

| Файл | Нарушение | Приоритет |
|---|---|---|
| `servers/multi_agent_engine.py:54-55` | Прямой `from studio.skill_*` | Высокий — применить SkillProvider DI как в `agent_engine.py` |
| `core_ui/views.py:39-49` | Прямые импорты `from servers.*`, `from studio.*` | Средний — desktop API-специфика, нужен отдельный adapter |
| `servers/agent_engine.py:54-55` | Прямой `from studio.skill_*` fallback | Низкий — legacy path, обёрнут в try/except |

> Эти нарушения **зафиксированы**. Новый код **не должен** их повторять. Исправлять в порядке приоритета отдельными PR.

### ⚠️ Известные технические долги (работать осторожно)

| Файл | Размер | Статус |
|---|---|---|
| `servers/views/_views_all.py` | 4207 строк | God-file, НЕ добавлять сюда новый код |
| `studio/views/_views_all.py` | 2510 строк | God-file, НЕ добавлять сюда новый код |
| `studio/pipeline_executor.py` | 2722 строк | God-file, мигрировать в `studio/executor/nodes/` |
| `app/agent_kernel/memory/store.py` | 3850 строк | God-file, частичная миграция |
| `servers/multi_agent_engine.py` | 1720 строк | God-file |
| `servers/agent_engine.py` | 997 строк | Приближается к лимиту |
| `ai-server-terminal-main/src/lib/api.ts` | 4133 строк | God-file, мигрировать в `src/api/` |
| `ai-server-terminal-main/src/pages/Servers.tsx` | 3330 строк | Разбить на подкомпоненты |
| `ai-server-terminal-main/src/pages/PipelineEditorPage.tsx` | 3523 строк | Разбить на подкомпоненты |

### 🔴 Инфраструктурные ограничения (блокируют 100+ пользователей)

Текущий `development` режим использует заглушки. **Для production 100+ пользователей ОБЯЗАТЕЛЬНО:**

```
SQLite           → PostgreSQL 15+     (POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD)
InMemoryChannel  → Redis Channels     (CHANNEL_REDIS_URL=redis://...:6379/1)
LocMemCache      → Redis Cache        (настроить CACHES в production.py)
Session in DB    → Redis Sessions     (SESSION_ENGINE = django.contrib.sessions.backends.cache)
Celery eager     → Celery + Redis     (убрать CELERY_TASK_ALWAYS_EAGER в production)
```

---

## 2. ЖЁСТКИЕ ПРАВИЛА (НАРУШЕНИЕ ЗАПРЕЩЕНО)

### R-001: Запрет прямых cross-context импортов

```
# ЗАПРЕЩЕНО в servers/*.py:
from studio.pipeline_executor import run_pipeline
import studio.skill_policy

# РАЗРЕШЕНО:
from app.agent_kernel.domain.specs import SkillProvider   # Protocol
from servers.signals import server_alert_opened            # Django Signal
```

```
# ЗАПРЕЩЕНО в studio/*.py:
from servers.models import Server

# РАЗРЕШЕНО:
Server = apps.get_model("servers", "Server")   # lazy reference
```

```
# ЗАПРЕЩЕНО в core_ui/*.py:
from servers.models import ServerGroup
from studio.views import pipeline_list
```

Контракты проверяются автоматически: `lint-imports` в `.importlinter`.

---

### R-002: Views — только тонкие обёртки

View-функция/класс **не должна** содержать бизнес-логику.
Разрешённый код в view:

```python
# ✅ OK
def my_view(request):
    data = my_service.get_data(request.user, request.GET)
    return JsonResponse({"items": data})

# ❌ ЗАПРЕЩЕНО — логика прямо в view
def my_view(request):
    items = MyModel.objects.filter(...).annotate(...).order_by(...)
    for item in items:
        item.status = compute_status(item)
    return JsonResponse(...)
```

---

### R-003: Лимит размера файла

| Тип файла | Лимит | Действие при превышении |
|---|---|---|
| Backend `.py` | **600 строк** | Обязательно разбить на модули |
| Frontend `.tsx` / `.ts` | **500 строк** | Обязательно разбить на компоненты/хуки |
| Backend view-файл | **300 строк** | Создать отдельный service-файл |

Новый код **не должен** добавляться в файлы, уже превышающие лимит.
Исключение: hotfix с явной пометкой `# TODO: extract to service`.

---

### R-004: Новые модели требуют индексов

Каждая новая Django-модель **обязана** иметь `Meta.indexes` для всех полей:
- используемых в `.filter()`, `.order_by()`, `.select_related()`
- внешних ключей (ForeignKey)
- полей типа `status`, `created_at`, `server`, `user`

```python
# ✅ ПРАВИЛЬНО
class AgentRun(models.Model):
    server = models.ForeignKey(Server, on_delete=models.CASCADE)
    status = models.CharField(max_length=32)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["server", "status"]),
            models.Index(fields=["created_at"]),
        ]
```

---

### R-005: Никаких новых файлов в корне Django-приложений

```
# ЗАПРЕЩЕНО (flat монолиты):
servers/my_new_feature.py          # всё в один файл
servers/views.py                   # view-монолит (уже мигрирован в views/)

# ПРАВИЛЬНО:
servers/services/my_new_feature.py # сервисный слой
servers/views/my_new_feature.py    # view отдельно
```

Исключения только для: `models.py`, `admin.py`, `apps.py`, `urls.py`,
`routing.py`, `signals.py`, `tasks.py`.

---

### R-006: Frontend — новые API в src/api/, не в src/lib/api.ts

```typescript
// ❌ ЗАПРЕЩЕНО — добавлять функции в lib/api.ts
// lib/api.ts уже 4133 строки, это god-file

// ✅ ПРАВИЛЬНО — создавать в домен-файле
// src/api/servers.ts
export async function getServerAlerts(serverId: number) { ... }

// src/api/index.ts уже реэкспортирует всё
```

---

### R-007: Frontend — переводы только через JSON

```typescript
// ❌ ЗАПРЕЩЕНО — хардкод строк в компонентах
<Button>Delete Server</Button>

// ✅ ПРАВИЛЬНО
const { t } = useI18n();
<Button>{t("server.delete")}</Button>

// И добавить ключ в:
// src/locales/en.json: { "server.delete": "Delete Server" }
// src/locales/ru.json: { "server.delete": "Удалить сервер" }
```

---

## 3. КАК ДОБАВИТЬ НОВУЮ ФИЧУ

### Чеклист для backend-фичи (строго по порядку)

```
[ ] 1. Определить контекст: к какому Django-приложению относится?
        servers/ → серверы, SSH, агенты, мониторинг
        studio/  → пайплайны, MCP, расписание, автоматизация
        core_ui/ → авторизация, настройки платформы, пользователи
        app/     → разделяемые сервисы без Django-зависимостей

[ ] 2. Создать/расширить модель (если нужна) в models.py
        → обязательно добавить Meta.indexes

[ ] 3. Создать migration:
        python manage.py makemigrations

[ ] 4. Написать сервисную функцию в services/:
        servers/services/my_feature.py
        def get_my_data(user, filters) -> list[dict]: ...

[ ] 5. Написать view-обёртку в views/:
        servers/views/my_feature.py
        def my_endpoint(request): return JsonResponse(service.get_my_data(...))

[ ] 6. Добавить URL в urls.py приложения

[ ] 7. Запустить проверки:
        ruff check .
        lint-imports
        python manage.py check
        pytest tests/

[ ] 8. Если фича пересекает контексты (servers ↔ studio):
        → использовать Django Signal или Protocol (SkillProvider-паттерн)
        → НЕ добавлять прямой импорт
```

### Чеклист для frontend-фичи

```
[ ] 1. Новая страница → src/pages/MyFeaturePage.tsx (макс. 500 строк)
        Если сложнее — сразу разбить:
        src/pages/my-feature/MyFeaturePage.tsx
        src/pages/my-feature/MyFeatureList.tsx
        src/pages/my-feature/MyFeatureForm.tsx

[ ] 2. Новые API-вызовы → src/api/<domain>.ts (НЕ в lib/api.ts)

[ ] 3. Shared компоненты → src/components/<category>/MyComponent.tsx

[ ] 4. Переиспользуемая логика → src/hooks/useMyFeature.ts

[ ] 5. Все строки → src/locales/en.json + ru.json

[ ] 6. Добавить route в src/App.tsx (или router-файл)

[ ] 7. Запустить:
        npm run type-check
        npm run lint
        npm test
```

---

## 4. КАК ИЗМЕНИТЬ СУЩЕСТВУЮЩУЮ ФИЧУ

### Правило минимального вмешательства

1. Изменять **только** то, что явно задано в задаче.
2. Не рефакторить "попутно" (это отдельный PR).
3. Если файл превышает лимит — добавить `# TODO: extract` и создать задачу.

### При изменении модели

```
[ ] Изменить поле/модель в models.py
[ ] python manage.py makemigrations --name=описание_изменения
[ ] Обновить API-сериализацию в views/ (если нужно)
[ ] Обновить тесты
[ ] Проверить: python manage.py migrate --plan (нет destructive migration)
```

### При изменении API-endpoint

```
[ ] Изменить сервис в services/
[ ] Убедиться, что view-слой не сломан
[ ] Проверить, не используется ли endpoint в frontend: grep по src/lib/api.ts и src/api/
[ ] Обновить frontend при необходимости
```

---

## 5. ЧТО АБСОЛЮТНО ЗАПРЕЩЕНО (AI-агентам особо)

```
❌ НЕ создавать новые top-level Django приложения без явного обсуждения
❌ НЕ добавлять бизнес-логику в views.py / views/_views_all.py
❌ НЕ добавлять прямые импорты между servers ↔ studio в Python-коде
❌ НЕ добавлять переводы хардкодом в TSX-компонентах
❌ НЕ добавлять новые функции в src/lib/api.ts
❌ НЕ создавать migration без проверки makemigrations + migrate --plan
❌ НЕ коммитить .env, секреты, ключи, пароли
❌ НЕ использовать bare except без логирования
❌ НЕ обходить importlinter (# noqa) без комментария с обоснованием
❌ НЕ добавлять синхронные блокирующие операции в async-consumers
❌ НЕ делать database queries в циклах (N+1 проблема) — использовать select_related/prefetch_related
```

---

## 6. АВТОМАТИЧЕСКИЕ ПРОВЕРКИ

Запускать перед каждым коммитом:

```bash
# Backend
ruff check .
ruff format --check .
lint-imports
python manage.py check --deploy
pytest

# Frontend
cd ai-server-terminal-main
npm run type-check
npm run lint
npm test
```

---

## 7. МАСШТАБИРОВАНИЕ ДО 100+ ПОЛЬЗОВАТЕЛЕЙ

### Что нужно переключить (только env-переменные, код не менять)

```env
# .env.production
POSTGRES_HOST=db.prod
POSTGRES_DB=weu_prod
POSTGRES_USER=weu
POSTGRES_PASSWORD=...

CHANNEL_REDIS_URL=redis://redis.prod:6379/1
REDIS_URL=redis://redis.prod:6379/0
CELERY_BROKER_URL=redis://redis.prod:6379/2

# В web_ui/settings/production.py уже есть:
SESSION_ENGINE = django.contrib.sessions.backends.cache
CACHES → RedisCache (добавить при деплое)
```

### Минимальная production-топология

```
                    ┌─────────────┐
Browser ──────────▶ │   Nginx      │
                    └──────┬──────┘
                    ┌──────▼──────┐   ┌──────────────┐
                    │  Daphne x N  │──▶│  Redis (WS)  │
                    │  (ASGI)      │   └──────────────┘
                    └──────┬──────┘
                    ┌──────▼──────┐   ┌──────────────┐
                    │  Django x N  │──▶│  PostgreSQL  │
                    └──────┬──────┘   └──────────────┘
                    ┌──────▼──────┐
                    │  Celery x N  │
                    └─────────────┘
```

### Что НЕ требует изменений в коде

Код уже написан с учётом горизонтального масштабирования:
- Settings через env-переменные (не хардкод)
- Celery tasks для тяжёлых операций
- Django Channels для WebSocket (не threading)
- Сигналы вместо прямых вызовов между контекстами

---

## 8. БЫСТРАЯ СПРАВКА ДЛЯ AI-АГЕНТОВ

```
ВОПРОС: Куда положить новую бизнес-логику для серверов?
ОТВЕТ:  servers/services/<feature_name>.py

ВОПРОС: Куда положить новый API endpoint для серверов?
ОТВЕТ:  servers/views/<feature_name>.py + URL в servers/urls.py

ВОПРОС: Как обратиться из servers к studio?
ОТВЕТ:  Django Signal или Protocol-инъекция, НЕ прямой импорт

ВОПРОС: Куда добавить новый перевод?
ОТВЕТ:  src/locales/en.json + src/locales/ru.json

ВОПРОС: Куда добавить новый API-вызов на frontend?
ОТВЕТ:  src/api/<domain>.ts (agents.ts, servers.ts, studio.ts, settings.ts, auth.ts)

ВОПРОС: Как добавить новый тип pipeline node?
ОТВЕТ:  studio/executor/nodes/<node_name>.py наследуя BaseNode + registry.register()

ВОПРОС: Как проверить что импорты не нарушают контракт?
ОТВЕТ:  lint-imports (из корня проекта)

ВОПРОС: Как добавить новую модель?
ОТВЕТ:  models.py → Meta.indexes → makemigrations → migrate
```

---

*Версия: 2.0 | Дата: апрель 2026 | Основан на: ARCHITECTURE_CONTRACT.md*
