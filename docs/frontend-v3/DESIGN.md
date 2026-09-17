# frontend-v3 — Design system (кратко, v2 corporate B2B)

Дата: 2026-09-13  
**Полная спецификация:** [`UI_SPEC.md`](UI_SPEC.md) · экраны: [`screens/`](screens/) · диалоги: [`MODALS_REGISTRY.md`](MODALS_REGISTRY.md).

Направление: корпоративный B2B-продукт для инфраструктурных команд. Светлая тема по умолчанию, один фирменный accent (корпоративный синий), карточки-контейнеры, русские подписи статусов.  
Референсы: Atlassian, Datadog, Grafana Enterprise, Fluent 2.  
Не брать: ashita / flow / pulse / glass / градиенты / ч/б «терминальный» chrome / marketing copy.

## Принципы

1. Понятно менеджеру, удобно инженеру: RU-подписи, mono только для технических значений.
2. Один accent `--accent #2563eb` — primary, ссылки, активная навигация, focus. Семантика — только у статусов.
3. Данные только из API (KPI, графики, бейджи).
4. Иерархия через Card → таблица/форма; тень одного уровня.
5. Один primary на экран; destructive — через ConfirmDialog.

## Typography

IBM Plex Sans (UI) · JetBrains Mono (host, path, id, код).

| Роль | Размер / вес |
| --- | --- |
| Body | 14px / 400 |
| Page title | 22px / 600 |
| Card title | 16px / 600 |
| Label / thead | 12px / 500–600, sentence-case |
| Mono | 13px |
| KPI value | 28px / 600 tabular |

## Tokens (light, default)

```
--bg #f5f7fa   --surface #ffffff   --surface-2 #f1f4f8
--fg #0f172a   --fg-2 #334155      --muted #64748b
--border #e2e8f0   --border-strong #cbd5e1   --row-hover #f1f5f9
--accent #2563eb   --accent-hover #1d4ed8   --accent-soft #eff6ff
--danger #dc2626   --warning #d97706   --success #16a34a   --info #0284c7
(+ *-soft фоны для Badge/Banner)
--terminal-bg #0b1220
--radius-sm 4 / --radius 6 / --radius-lg 8
--nav-width 248 / --topbar-h 56 / --drawer-w 480
```

Dark theme — `html[data-theme="dark"]`, те же роли токенов (см. UI_SPEC §2.2).

## Geometry

- Card: radius 8, border, `--shadow-sm`
- Button h 36 / 30; Input h 36; Table row 44
- Active nav: bg `--accent-soft`, text `--accent`, left bar 3px
- Badge: pill, soft-фон тона, RU-подпись
- Dialog/Drawer: shadow-md, без blur

## Components

Реализованы (v1, требуют рестайла): `Button`, `Badge`/`StatusDot`, `PageHeader`, `DataTable`, `EmptyState`/`InlineError`, `PageShell`.  
Создать: `Card`, `Tabs`, `FilterChips`, `KpiCard`, `Field`, `Dialog`, `ConfirmDialog`, `PromptDialog`, `Drawer`, `Toast`, `DropdownMenu`, `Tooltip`, `Skeleton`, `Avatar`, `ForbiddenState`.

## Anti-patterns

- KPI без поля API · motivational copy · эмодзи
- Второй accent, градиенты, glass
- lowercase-английские статусы в UI
- `window.confirm` / `prompt`
- Тёмный shell по умолчанию

## Эталонные экраны

1. Login — [`screens/01-login.md`](screens/01-login.md)
2. Панель — [`screens/02-dashboard.md`](screens/02-dashboard.md)
3. Серверы — [`screens/03-servers.md`](screens/03-servers.md)
4. Терминал — [`screens/04-terminal.md`](screens/04-terminal.md)
5. Настройки / Готовность — [`screens/11-settings.md`](screens/11-settings.md)
