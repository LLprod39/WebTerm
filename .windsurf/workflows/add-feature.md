---
description: Add a new feature to WEU AI Platform (backend + frontend)
---

# Добавить новую фичу в WEU AI Platform

## Шаг 1. Определить контекст фичи

Прочитать `CONTRIBUTING.md` раздел "Определяем контекст".

Ответить на вопросы:
- К какому bounded context относится? (servers / studio / core_ui / app)
- Нужна ли новая модель?
- Нужен ли новый frontend?
- Пересекает ли фича несколько контекстов?

## Шаг 2. Backend — создать service

```bash
# Создать файл services/<feature_name>.py в нужном контексте
# Шаблон: CONTRIBUTING.md → "Новый service"
```

## Шаг 3. Backend — создать view + URL

```bash
# Создать файл views/<feature_name>.py
# Добавить URL в urls.py
# Шаблон: CONTRIBUTING.md → "Новый view"
```

## Шаг 4. Если нужна новая модель

```bash
python manage.py makemigrations --name=add_<feature_name>_model
python manage.py migrate --plan
python manage.py migrate
```

## Шаг 5. Frontend — API-функция

```bash
# Добавить в src/api/<domain>.ts (НЕ в lib/api.ts!)
# Шаблон: CONTRIBUTING.md → "Новый React компонент"
```

## Шаг 6. Frontend — страница/компонент

```bash
# Создать src/pages/<FeatureName>Page.tsx
# Добавить переводы в src/locales/en.json + ru.json
# Добавить route в App.tsx
```

## Шаг 7. Проверки

```bash
python manage.py check
ruff check .
cd ai-server-terminal-main && npm run type-check && npm run lint
pytest
```

## Шаг 8. Финал

- Убедиться что `manage.py check` — 0 issues
- Убедиться что нет новых cross-context imports
- Убедиться что переводы добавлены в оба файла (en + ru)
