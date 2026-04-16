# CONTRIBUTING — Как работать с проектом WEU AI Platform

> **Это главный документ для всех, кто работает с проектом**: разработчики, QA, DevOps и AI-агенты (Cascade, Codex, Claude и др.).
>
> Дополнительные документы:
> - [`DEVELOPMENT_RULES.md`](./DEVELOPMENT_RULES.md) — жёсткие правила архитектуры (нарушать нельзя)
> - [`ARCHITECTURE_CONTRACT.md`](./ARCHITECTURE_CONTRACT.md) — архитектурный контракт
> - [`AGENTS.md`](./AGENTS.md) — описание модулей и контекст для AI-агентов

---

## СОДЕРЖАНИЕ

1. [Быстрый старт](#1-быстрый-старт)
2. [Структура проекта за 2 минуты](#2-структура-проекта-за-2-минуты)
3. [Ежедневный рабочий цикл](#3-ежедневный-рабочий-цикл)
4. [Добавить новую backend-фичу](#4-добавить-новую-backend-фичу)
5. [Добавить новую frontend-фичу](#5-добавить-новую-frontend-фичу)
6. [Изменить существующую фичу](#6-изменить-существующую-фичу)
7. [Добавить новый тип pipeline-ноды](#7-добавить-новый-тип-pipeline-ноды)
8. [Работа с базой данных](#8-работа-с-базой-данных)
9. [Тестирование](#9-тестирование)
10. [Деплой и production](#10-деплой-и-production)
11. [Если что-то сломалось](#11-если-что-то-сломалось)
12. [AI-агентам: обязательный раздел](#12-ai-агентам-обязательный-раздел)

---

## 1. БЫСТРЫЙ СТАРТ

### Backend

```bash
# Из корня проекта (c:\WebTrerm)
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements-mini.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver     # порт 9000 по умолчанию
```

### Frontend

```bash
cd ai-server-terminal-main
npm install
npm run dev                    # порт 8080, proxy → 9000
```

### Проверка что всё работает

```bash
python manage.py check         # должно быть 0 issues
ruff check .
pytest
```

---

## 2. СТРУКТУРА ПРОЕКТА ЗА 2 МИНУТЫ

```
WebTrerm/
│
├── web_ui/                   # Django: settings, urls, asgi, wsgi
│   └── settings/             # base.py + development.py + production.py + test.py
│
├── core_ui/                  # Identity & Access: auth, пользователи, настройки
│   ├── views/                # HTTP endpoints
│   ├── desktop_api/          # Electron Desktop API (интеграционный слой)
│   └── models.py             # ChatSession, UserPermission, LLMUsageLog...
│
├── servers/                  # Server Domain: серверы, SSH, агенты, память
│   ├── services/             # ← СЮДА бизнес-логику
│   ├── views/                # HTTP endpoints (тонкие обёртки над services/)
│   ├── consumers/            # WebSocket: SSH, RDP, Agent Live
│   ├── adapters/             # DjangoServerMemoryStore и др.
│   └── models.py             # Server, ServerAgent, AgentRun, Memory*...
│
├── studio/                   # Pipeline & Automation: пайплайны, MCP, скилы
│   ├── executor/             # PipelineEngine + NodeRegistry
│   │   └── nodes/            # ← СЮДА новые типы нод
│   ├── views/                # HTTP endpoints
│   └── models.py             # Pipeline, PipelineRun, MCPServerPool...
│
├── app/                      # Shared Services: LLM, agent_kernel, tools
│   ├── agent_kernel/         # memory, permissions, runtime, DI registry
│   ├── core/                 # LLM providers
│   └── tools/                # SSH tools, server tools
│
└── ai-server-terminal-main/  # Frontend: React 18 + Vite 5 + TailwindCSS
    └── src/
        ├── api/              # ← СЮДА API-вызовы (НЕ в lib/api.ts)
        ├── pages/            # Страницы
        ├── components/       # Компоненты
        ├── hooks/            # Хуки
        └── locales/          # en.json + ru.json (переводы)
```

### Граница между контекстами

```
core_ui  ←→  (не общаются напрямую)  ←→  servers
                                          ↑
                                    Django Signals /
                                    SkillProvider DI
                                          ↑
studio   ←→  (не общаются напрямую)  ←→  servers

app/  →  (shared, без Django ORM вне agent_kernel)
```

---

## 3. ЕЖЕДНЕВНЫЙ РАБОЧИЙ ЦИКЛ

### Перед началом работы

```bash
git pull
python manage.py migrate       # применить новые миграции
cd ai-server-terminal-main && npm install   # если изменился package.json
```

### После любых изменений — обязательные проверки

```bash
# Backend
python manage.py check         # 0 issues
ruff check .                   # 0 ошибок
ruff format .                  # форматирование

# Frontend
cd ai-server-terminal-main
npm run type-check             # TypeScript: 0 ошибок
npm run lint                   # ESLint: 0 ошибок
```

### Перед коммитом

```bash
pytest                         # все тесты проходят
python manage.py migrate --check  # нет непримененных миграций
```

---

## 4. ДОБАВИТЬ НОВУЮ BACKEND-ФИЧУ

### Определяем контекст

| Фича касается | Куда добавлять |
|---|---|
| Серверов, SSH, агентов, мониторинга | `servers/` |
| Пайплайнов, MCP, скилов, триггеров | `studio/` |
| Авторизации, пользователей, настроек | `core_ui/` |
| Разделяемой логики без Django ORM | `app/` |

### Пошаговый чеклист

```
[ ] 1. Создать сервисный слой
       servers/services/my_feature.py   # или studio/, core_ui/
       
       def get_my_data(user, filters) -> list[dict]:
           return MyModel.objects.filter(user=user, **filters).values(...)

[ ] 2. Создать view-endpoint
       servers/views/my_feature.py
       
       @require_http_methods(["GET"])
       def my_endpoint(request):
           data = my_feature_service.get_my_data(request.user, request.GET)
           return JsonResponse({"items": data})

[ ] 3. Подключить URL
       servers/urls.py:
       path("api/servers/my-feature/", views.my_endpoint, name="my_feature"),

[ ] 4. Если нужна новая модель — см. раздел 8 (База данных)

[ ] 5. Запустить проверки:
       python manage.py check && ruff check .
```

### Если фича пересекает два контекста

```python
# ❌ НЕ ДЕЛАЙ — прямой импорт через границу
# servers/my_file.py
from studio.pipeline_executor import run_pipeline  # ЗАПРЕЩЕНО

# ✅ ДЕЛАЙ — через Django Signal
# servers/signals.py
my_event = Signal()

# studio/apps.py в ready():
from servers.signals import my_event
my_event.connect(studio_handler)

# ✅ ИЛИ — через Protocol/DI (как SkillProvider)
# app/agent_kernel/my_protocol.py
class MyProtocol(Protocol):
    def do_thing(self, data: Any) -> Any: ...
```

---

## 5. ДОБАВИТЬ НОВУЮ FRONTEND-ФИЧУ

### Структура новой страницы

```
Простая страница (< 500 строк):
  src/pages/MyFeaturePage.tsx

Сложная страница (> 500 строк) — сразу разбить:
  src/pages/my-feature/
  ├── MyFeaturePage.tsx       # роутер + layout
  ├── MyFeatureList.tsx       # список
  ├── MyFeatureForm.tsx       # форма
  └── MyFeatureDetail.tsx     # детали
```

### Пошаговый чеклист

```
[ ] 1. Создать API-функции в src/api/<domain>.ts (НЕ в lib/api.ts):
       // src/api/servers.ts
       export async function getMyFeatureData(params) {
           const res = await fetch(`/servers/api/my-feature/`, {credentials: "include"});
           return res.json();
       }

[ ] 2. Создать хук в src/hooks/useMyFeature.ts (если логика сложная):
       export function useMyFeature(params) {
           return useQuery({queryKey: ["my-feature", params], queryFn: () => getMyFeatureData(params)});
       }

[ ] 3. Создать компонент страницы в src/pages/MyFeaturePage.tsx

[ ] 4. Добавить переводы в src/locales/en.json и src/locales/ru.json:
       "my.feature.title": "My Feature"
       "my.feature.title": "Моя функция"

[ ] 5. Подключить route в src/App.tsx (или router-файл):
       <Route path="/my-feature" element={<MyFeaturePage />} />

[ ] 6. Запустить:
       npm run type-check && npm run lint
```

### Использование переводов в компонентах

```typescript
// В компоненте
const { t } = useI18n();

// В JSX
<h1>{t("my.feature.title")}</h1>
<Button>{t("common.save")}</Button>

// НЕ хардкодить строки:
<h1>My Feature</h1>   // ❌
```

---

## 6. ИЗМЕНИТЬ СУЩЕСТВУЮЩУЮ ФИЧУ

### Принцип минимального вмешательства

1. Менять **только** то, что явно задано в задаче
2. Не рефакторить "попутно" → отдельный PR/коммит
3. Если файл > 600 строк (backend) или > 500 (frontend) — добавить `# TODO: extract` и создать задачу

### При изменении API endpoint

```
[ ] Найти endpoint в urls.py: grep -r "my-endpoint" servers/urls.py
[ ] Изменить сервис в services/
[ ] Убедиться что view не сломан
[ ] Найти все вызовы в frontend: grep -r "my-endpoint" ai-server-terminal-main/src/
[ ] Обновить frontend если изменился контракт (метод, поля, статусы)
[ ] Запустить: python manage.py check && npm run type-check
```

### При изменении модели

```
[ ] Изменить поле в models.py
[ ] python manage.py makemigrations --name=описание_что_изменилось
[ ] python manage.py migrate --plan   # убедиться нет destructive операций
[ ] python manage.py migrate
[ ] Обновить сериализацию в views/ или services/ если нужно
```

---

## 7. ДОБАВИТЬ НОВЫЙ ТИП PIPELINE-НОДЫ

Архитектура: `studio/executor/nodes/<node_name>.py`, наследуется от `BaseNode`.

```python
# studio/executor/nodes/my_node.py
from studio.executor.nodes.base import BaseNode, NodeResult
from studio.executor.registry import registry


class MyNode(BaseNode):
    node_type = "my/node_type"   # должен совпадать с type в React Flow

    async def execute(self, node, context):
        # node.data — данные из React Flow конфигурации
        # context.pipeline_run — PipelineRun ORM объект
        # context.emit(event_type, data) — отправить WS событие
        result = do_my_thing(node.data)
        return NodeResult(status="completed", output=result)


registry.register(MyNode)
```

**Импортировать** в `studio/executor/nodes/__init__.py`:

```python
from studio.executor.nodes.my_node import MyNode  # noqa: F401
```

**Проверка**:
```python
from studio.executor.registry import registry
import studio.executor.nodes.my_node
registry.list_types()  # должен содержать "my/node_type"
```

---

## 8. РАБОТА С БАЗОЙ ДАННЫХ

### Правила для новых моделей

```python
class MyNewModel(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)
    status = models.CharField(max_length=20, default="active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            # ОБЯЗАТЕЛЬНО — для каждого ForeignKey и поля в filter/order
            models.Index(fields=["user", "-updated_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]
```

### Правила для миграций

```bash
# После любого изменения модели:
python manage.py makemigrations --name=краткое_описание_изменения

# Перед применением проверить план:
python manage.py migrate --plan

# Применить:
python manage.py migrate

# ЗАПРЕЩЕНО:
# - squash migrations без согласования
# - ручное редактирование сгенерированных файлов миграции (кроме зависимостей)
# - удалять поля без дата-миграции для обнуления/переноса данных
```

### Оптимизация запросов

```python
# ❌ N+1 запросов
for server in Server.objects.filter(user=user):
    print(server.group.name)  # запрос на каждой итерации

# ✅ Один запрос
for server in Server.objects.filter(user=user).select_related("group"):
    print(server.group.name)

# ❌ Запрос в цикле
for run in AgentRun.objects.all():
    print(run.agent.name)

# ✅ Prefetch
for run in AgentRun.objects.all().prefetch_related("agent"):
    print(run.agent.name)
```

---

## 9. ТЕСТИРОВАНИЕ

### Структура тестов

```
tests/                    # интеграционные тесты
servers/test_*.py         # юнит-тесты для servers
studio/test_*.py          # юнит-тесты для studio
core_ui/test_*.py         # юнит-тесты для core_ui
ai-server-terminal-main/src/  # frontend тесты рядом с компонентами
```

### Запуск тестов

```bash
# Backend
pytest                            # все тесты
pytest servers/                   # только servers
pytest -k "test_my_feature"       # конкретный тест
pytest --tb=short                 # короткий traceback

# Frontend
cd ai-server-terminal-main
npm test                          # vitest
npm run test:ui                   # UI режим
npx playwright test               # e2e
```

### Что тестировать обязательно

```
[ ] Новые service-функции: юнит-тест с моками
[ ] Новые endpoints: интеграционный тест через Django test client
[ ] Edge cases: пустой список, None, ошибка сети
[ ] Права доступа: убедиться что endpoint проверяет @login_required
```

### Шаблон теста для endpoint

```python
# servers/test_my_feature.py
import pytest
from django.test import Client

@pytest.mark.django_db
class TestMyFeatureEndpoint:
    def test_requires_auth(self, client: Client):
        resp = client.get("/servers/api/my-feature/")
        assert resp.status_code == 302  # redirect to login

    def test_returns_data(self, client: Client, django_user_model):
        user = django_user_model.objects.create_user("test", password="test")
        client.force_login(user)
        resp = client.get("/servers/api/my-feature/")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
```

---

## 10. ДЕПЛОЙ И PRODUCTION

### Переключение на production инфраструктуру

Только через переменные окружения — **код не меняется**:

```env
# .env.production
DJANGO_SETTINGS_MODULE=web_ui.settings.production

# База данных (вместо SQLite)
POSTGRES_HOST=db.prod.internal
POSTGRES_DB=weu_prod
POSTGRES_USER=weu_app
POSTGRES_PASSWORD=<secret>

# Redis (WebSocket + Celery + Cache)
CHANNEL_REDIS_URL=redis://redis.prod.internal:6379/1
REDIS_URL=redis://redis.prod.internal:6379/0
CELERY_BROKER_URL=redis://redis.prod.internal:6379/2

# Безопасность
SECRET_KEY=<долгий случайный ключ>
ALLOWED_HOSTS=weu.company.internal,weu.company.com
DEBUG=false
```

### Чеклист перед деплоем

```
[ ] python manage.py check --deploy    # 0 issues с production-настройками
[ ] python manage.py migrate --plan    # нет destructive migrations
[ ] cd ai-server-terminal-main && npm run build  # frontend собирается
[ ] Все тесты проходят: pytest && npm test
[ ] Нет секретов в коде: git grep -i "password\|secret\|token" --and --not ".env"
```

---

## 11. ЕСЛИ ЧТО-ТО СЛОМАЛОСЬ

### Диагностика

```bash
# Что сломалось при запуске Django?
python manage.py check
python -c "import web_ui.settings.development"

# Что сломалось в импортах?
python -c "
import os; os.environ['DJANGO_SETTINGS_MODULE']='web_ui.settings.development'
import django; django.setup()
from servers.agent_engine import AgentEngine   # проверить конкретный импорт
"

# Что сломалось в БД?
python manage.py showmigrations
python manage.py migrate --plan

# Что сломалось во frontend?
cd ai-server-terminal-main && npm run type-check
```

### Логи

```bash
# Django в dev режиме выводит в stdout
# Runtime логи агентов:
Get-Content c:\WebTrerm\runtime_logs\*.log -Tail 100

# В production:
docker logs <container> --tail=200
```

### Откат миграции

```bash
python manage.py migrate <app_name> <migration_number>
# Например: python manage.py migrate servers 0022
```

---

## 12. AI-АГЕНТАМ: ОБЯЗАТЕЛЬНЫЙ РАЗДЕЛ

> Это раздел для Cascade, Codex, Claude, GPT и любых других AI-агентов, работающих с проектом.

### Перед любым изменением — прочитать

1. `DEVELOPMENT_RULES.md` — архитектурные правила (нарушать нельзя)
2. `AGENTS.md` — актуальная карта модулей

### Алгоритм выполнения задачи

```
1. ПОНЯТЬ задачу
   - Что изменить? Где? Что НЕ трогать?
   - К какому bounded context относится?

2. ПРОЧИТАТЬ существующий код
   - Использовать Read/Grep перед любым изменением
   - Найти похожие паттерны в кодовой базе

3. СПЛАНИРОВАТЬ изменения
   - Минимальные изменения, не рефакторить попутно
   - Один файл за раз если возможно

4. РЕАЛИЗОВАТЬ
   - Следовать паттернам из DEVELOPMENT_RULES.md
   - Не создавать новые top-level пакеты
   - Не добавлять cross-context импорты

5. ПРОВЕРИТЬ
   - python manage.py check  (должно быть 0 issues)
   - ruff check .
   - npm run type-check (если менял frontend)

6. ДОЛОЖИТЬ результат
   - Какие файлы изменены
   - Какие проверки прошли
```

### Чего никогда не делать (AI-агентам)

```
❌ Добавлять from studio.* в servers/*.py (и наоборот)
❌ Добавлять бизнес-логику прямо в view-функцию
❌ Создавать новые Django приложения (top-level папки)
❌ Добавлять функции в src/lib/api.ts (god-file, уже 4133 строки)
❌ Хардкодить строки в TSX без добавления в locales/*.json
❌ Делать git commit/push без команды от пользователя
❌ Удалять или изменять тесты без явного указания
❌ Создавать squash-миграции или удалять файлы миграций
❌ Делать Database queries в циклах (N+1)
```

### Быстрые ответы на частые вопросы

| Вопрос | Ответ |
|---|---|
| Куда положить бизнес-логику для серверов? | `servers/services/<feature>.py` |
| Куда положить API endpoint для серверов? | `servers/views/<feature>.py` + `servers/urls.py` |
| Как из servers обратиться к studio? | Django Signal или Protocol DI |
| Куда добавить перевод? | `src/locales/en.json` + `src/locales/ru.json` |
| Куда добавить API-вызов на frontend? | `src/api/<domain>.ts` |
| Как добавить новую pipeline ноду? | `studio/executor/nodes/<name>.py` + `registry.register()` |
| Как проверить что импорты корректны? | `python manage.py check` |
| Нужна новая модель? | `models.py` → `Meta.indexes` → `makemigrations` → `migrate` |

### Шаблоны кода для AI-агентов

**Новый service:**
```python
# servers/services/my_service.py
from servers.models import MyModel

def get_items(user, *, status=None) -> list[dict]:
    qs = MyModel.objects.filter(user=user)
    if status:
        qs = qs.filter(status=status)
    return list(qs.values("id", "name", "status", "created_at"))
```

**Новый view:**
```python
# servers/views/my_view.py
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from servers.services import my_service

@login_required
@require_http_methods(["GET"])
def my_endpoint(request):
    items = my_service.get_items(request.user, status=request.GET.get("status"))
    return JsonResponse({"items": items})
```

**Новый React компонент:**
```typescript
// src/pages/MyPage.tsx
import { useI18n } from "../lib/i18n";
import { useMyFeature } from "../hooks/useMyFeature";

export default function MyPage() {
    const { t } = useI18n();
    const { data, isLoading } = useMyFeature();

    if (isLoading) return <div>{t("loading")}</div>;

    return (
        <div className="p-6">
            <h1 className="text-2xl font-bold">{t("my.page.title")}</h1>
        </div>
    );
}
```

---

## ССЫЛКИ

| Документ | Назначение |
|---|---|
| `DEVELOPMENT_RULES.md` | Жёсткие правила архитектуры — нарушать нельзя |
| `ARCHITECTURE_CONTRACT.md` | Архитектурный контракт и bounded contexts |
| `AGENTS.md` | Карта модулей и контекст для AI-агентов |
| `.importlinter` | Автоматическая проверка cross-context импортов |
| `pyproject.toml` | ruff, pytest, isort конфигурация |
| `web_ui/settings/` | Django settings: base / development / production / test |

---

*Версия: 1.0 | Апрель 2026 | Поддерживать актуальным при изменении архитектуры*
