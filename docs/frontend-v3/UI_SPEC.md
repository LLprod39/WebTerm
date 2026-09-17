# frontend-v3 — UI Specification (v2, corporate B2B)

Дата: 2026-09-13 (ревизия направления)  
Источник истины для токенов, примитивов, оверлеев, паттернов страниц и копирайта.  
Экраны: [`screens/`](screens/). Реестр диалогов: [`MODALS_REGISTRY.md`](MODALS_REGISTRY.md).  
Краткая версия: [`DESIGN.md`](DESIGN.md). Контракты API: [`API_MATRIX.md`](API_MATRIX.md).

**Направление:** корпоративный B2B-продукт для инфраструктурных команд и их руководителей.  
Светлая тема по умолчанию, один фирменный accent (корпоративный синий), спокойная плотность, понятные русские подписи, карточки-контейнеры.  
Референсы уровня: Atlassian Design System, Datadog, Grafana Enterprise, Microsoft Fluent 2.  
Не брать: ashita / flow / pulse / glass / фиолетовые градиенты / «хакерский» ч/б терминал-стиль в chrome / marketing copy.

> Ревизия v2 заменяет ч/б-минимализм v1. Где экраны в `screens/*.md` говорят «primary = белая кнопка», «lowercase badge», «без KPI», «ч/б» — читать по таблице соответствия в [`screens/README.md`](screens/README.md).

---

## 1. Принципы

1. Понятно менеджеру, удобно инженеру: русские человекочитаемые статусы и подписи, технические значения — mono.
2. Один accent-цвет (`--accent`) для primary-действий, ссылок, активной навигации, фокуса. Семантические цвета — только у статусов.
3. Данные только из API: сводные карточки, графики и бейджи рисуются, если поле есть в ответе. Нет заглушек «N проблем» без источника.
4. Иерархия через контейнеры: страница → карточки/секции с заголовком → таблицы/формы. Тени лёгкие, один уровень.
5. Один primary на экран или футер диалога. Destructive — всегда через подтверждение.
6. Светлая тема — основная; тёмная — полноценная опция с теми же токенами. Терминал всегда тёмный.
7. Копирайт операционный, sentence-case, без восклицаний и маркетинга. Допустима одна строка описания под заголовком раздела.

### Anti-patterns

- Заглушки KPI без поля API, «умные» индикаторы, motivational copy
- Больше одного accent-цвета; градиенты; glassmorphism
- Pill-кнопки `rounded-full` (кроме Badge)
- lowercase-английские статусы в интерфейсе (API-токен — только в tooltip/`title`)
- `window.confirm` / `window.prompt` / `window.alert`
- Пульсирующие точки, glow, многослойные тени
- Тёмный shell по умолчанию

---

## 2. Токены

Источник значений: `frontend-v3/src/index.css` (обновить под v2). Тема: `document.documentElement.dataset.theme`, default `"light"`, storage key `webterm.v3.theme`.

### 2.1 Цвета — light (`:root`, по умолчанию)

| Token | Hex / value | Применение |
| --- | --- | --- |
| `--bg` | `#f5f7fa` | Фон страницы |
| `--surface` | `#ffffff` | Карточки, таблицы, sidebar, drawer, dialog |
| `--surface-2` | `#f1f4f8` | Sticky thead, toolbar внутри карточки, hover input |
| `--fg` | `#0f172a` | Основной текст |
| `--fg-2` | `#334155` | Вторичный текст, значения в KeyValue |
| `--muted` | `#64748b` | Подписи, hint, kicker, неактивная навигация |
| `--border` | `#e2e8f0` | Разделители, границы карточек и таблиц |
| `--border-strong` | `#cbd5e1` | Границы input/button |
| `--row-hover` | `#f1f5f9` | Hover строк таблиц и меню |
| `--accent` | `#2563eb` | Primary button, ссылки, активная навигация, focus, checked |
| `--accent-hover` | `#1d4ed8` | Hover primary |
| `--accent-soft` | `#eff6ff` | Фон активного nav-пункта, выделенных строк, info-баннера |
| `--accent-fg` | `#ffffff` | Текст на accent |
| `--focus` | `#2563eb` | Focus ring (2px) |
| `--danger` | `#dc2626` | Ошибка, offline, destructive |
| `--danger-soft` | `#fef2f2` | Фон danger-badge/баннера |
| `--warning` | `#d97706` | Предупреждение, stale, paused |
| `--warning-soft` | `#fffbeb` | Фон warning-badge |
| `--success` | `#16a34a` | Ready, online, completed |
| `--success-soft` | `#f0fdf4` | Фон success-badge |
| `--info` | `#0284c7` | Running, queued, connecting |
| `--info-soft` | `#f0f9ff` | Фон info-badge |
| `--neutral-soft` | `#f1f5f9` | Фон unknown/disabled-badge |
| `--overlay` | `rgb(15 23 42 / 0.45)` | Затемнение под Dialog/Drawer, без blur |
| `--terminal-bg` | `#0b1220` | Фон xterm / `.terminal-wrap` (в обеих темах) |
| `--shadow-sm` | `0 1px 2px rgb(15 23 42 / 0.06)` | Карточки |
| `--shadow-md` | `0 8px 24px rgb(15 23 42 / 0.12)` | Dialog, Drawer, Dropdown |

### 2.2 Цвета — dark (`html[data-theme="dark"]`)

| Token | Hex |
| --- | --- |
| `--bg` | `#0f172a` |
| `--surface` | `#141d33` |
| `--surface-2` | `#1a2540` |
| `--fg` | `#e2e8f0` |
| `--fg-2` | `#cbd5e1` |
| `--muted` | `#94a3b8` |
| `--border` | `#1e293b` |
| `--border-strong` | `#334155` |
| `--row-hover` | `#1a2540` |
| `--accent` | `#3b82f6` |
| `--accent-hover` | `#60a5fa` |
| `--accent-soft` | `rgb(59 130 246 / 0.14)` |
| `--accent-fg` | `#ffffff` |
| `--focus` | `#60a5fa` |
| `--danger` / `--danger-soft` | `#f87171` / `rgb(248 113 113 / 0.14)` |
| `--warning` / `--warning-soft` | `#fbbf24` / `rgb(251 191 36 / 0.14)` |
| `--success` / `--success-soft` | `#4ade80` / `rgb(74 222 128 / 0.14)` |
| `--info` / `--info-soft` | `#38bdf8` / `rgb(56 189 248 / 0.14)` |
| `--neutral-soft` | `rgb(148 163 184 / 0.14)` |
| `--overlay` | `rgb(0 0 0 / 0.6)` |
| `--terminal-bg` | `#0b1220` |
| `--shadow-sm` / `--shadow-md` | `none` / `0 8px 24px rgb(0 0 0 / 0.45)` |

**xterm theme (обе темы):** `background #0b1220` · `foreground #e2e8f0` · `cursor #e2e8f0` · `selectionBackground #334155` · fontSize 14 · JetBrains Mono.

### 2.3 Типографика

Шрифты те же: **IBM Plex Sans** (UI) и **JetBrains Mono** (технические значения). Файлы: `frontend-v3/public/fonts/`.

| Роль | Размер / вес / прочее |
| --- | --- |
| Body | `--text-base` 0.875rem (14px) / 400 / lh 1.5 |
| Small | `--text-sm` 0.8125rem (13px) — hint, meta, table dense |
| Caption | `--text-xs` 0.75rem (12px) — labels, thead, badge |
| Page title (h2) | `--text-xl` 1.375rem (22px) / 600 / −0.01em |
| Section / card title (h3) | `--text-lg` 1rem (16px) / 600 |
| Kicker | 12px / 500 / `--muted` / **sentence-case** (не uppercase); допускается uppercase только для секций sidebar |
| Table thead | 12px / 600 / `--muted` / sentence-case |
| Button | 14px / 500 (sm: 13px) |
| Mono | JetBrains Mono 13px (`--text-sm`), в коде/pre 12px |
| KPI value | 1.75rem / 600 / tabular-nums (Sans, не Mono) |

### 2.4 Spacing, radius, размеры

| Token | Value |
| --- | --- |
| `--space-1 … --space-8` | 4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 px |
| `--radius-sm` | `4px` — badge, kbd, chips |
| `--radius` | `6px` — button, input, dropdown |
| `--radius-lg` | `8px` — карточки, dialog, drawer |
| `--nav-width` | `248px` |
| `--topbar-h` | `56px` |
| `--drawer-w` | `480px` |
| `--dialog-w-sm` / `-md` / `-lg` | `440px` / `560px` / `760px` |
| Button md / sm | h `36px` / `30px`; padding `0 14px` / `0 10px` |
| IconButton | 36×36 / 30×30 |
| Input / Select | h `36px`; padding `0 12px` |
| Table row | `44px` (dense-режим таблиц серверов/логов — `40px`) |
| Badge | h `22px`; padding `0 8px`; radius `999px` (единственное место с pill) |
| Card padding | `--space-5` (20px); header `16px 20px` |
| Page max-width | `1280px` (`.page`); wide/terminal — none |
| Main padding | `--space-6` (24px); ≥1440px — `--space-8` |

### 2.5 Z-index

| Token | Value |
| --- | --- |
| `--z-topbar` | `10` |
| `--z-drawer` | `20` |
| `--z-dialog` | `30` |
| `--z-toast` | `40` |
| `--z-tooltip` | `50` |

### 2.6 Карта статусов → тон → подпись

Badge показывает **русскую подпись**, API-токен — в `title`. Тон задаёт цвет текста/точки и soft-фон.

| API values | Tone | RU подпись |
| --- | --- | --- |
| `online` | success | В сети |
| `offline` | danger | Не в сети |
| `unknown` | neutral | Неизвестно |
| `ready`, `healthy`, `success`, `ok` | success | Готово / Исправен / Успешно |
| `completed`, `applied`, `approved`, `published`, `validated` | success | Завершено / Применено / Одобрено / Опубликовано / Проверено |
| `connected` | success | Подключено |
| `warning`, `warn`, `stale` | warning | Внимание / Устарело |
| `paused`, `pending` | warning | На паузе / Ожидает |
| `degraded` | warning | Деградация |
| `error`, `failed` | danger | Ошибка / Сбой |
| `critical`, `unreachable` | danger | Критично / Недоступен |
| `stopped`, `cancelled`, `rejected` | danger | Остановлено / Отменено / Отклонено |
| `running`, `rolling`, `progressing` | info | Выполняется / Раскатка |
| `queued`, `scheduled` | info | В очереди / По расписанию |
| `connecting` | info | Подключение |
| `disconnected`, `disabled`, `discarded`, `draft` | neutral | Отключено / Выключено / Отклонён / Черновик |

StatusDot: 8px круг цвета тона; **без пульса**.

---

## 3. Layout

### 3.1 App shell

```
┌────────────┬────────────────────────────────────────────┐
│ Sidebar    │ Topbar 56px: раздел · breadcrumbs · [🔍 Ctrl+K] · user │
│ 248px      ├────────────────────────────────────────────┤
│ surface    │ Main  bg --bg  padding 24px                 │
│ logo       │   .page max-width 1280                      │
│ nav        │   PageHeader                                │
│ footer     │   Card / Table / Form                       │
└────────────┴────────────────────────────────────────────┘
```

- `.sidebar`: bg `--surface`; border-right `--border`; логотип + название продукта сверху (20px/600); секции с kicker uppercase 11px `--muted`.
- Nav item: h 36px; radius 6; icon 18px; text 14px `--fg-2`. Hover `--row-hover`. **Active:** bg `--accent-soft`, text/icon `--accent`, 500, left bar 3px `--accent`.
- Sidebar footer: карточка пользователя (аватар-инициалы 28px на `--accent-soft`, имя, роль muted), меню `⋯` → Тема / Выйти.
- `.topbar`: h 56px; bg `--surface`; border-bottom; без blur. Слева — название раздела (16/600) + breadcrumbs muted; справа — кнопка поиска `Ctrl+K` (secondary sm с `Kbd`), переключатель темы (IconButton), пользователь.
- `.main`: bg `--bg`.

### 3.2 Responsive

| Ширина | Поведение |
| --- | --- |
| ≥1440px | main padding 32px |
| 960–1279px | sidebar 220px, KPI-strip 2 колонки |
| <960px | sidebar скрыт → IconButton `☰` в topbar открывает Drawer слева; таблицы — горизонтальный скролл; PageHeader actions переносятся вниз; Drawer/Dialog — 100vw |

### 3.3 Focus

`:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; border-radius: inherit; }`  
Inputs on focus: `border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft)`.

---

## 4. Примитивы

### 4.1 Button

| Variant | Look |
| --- | --- |
| `primary` | bg `--accent`, text `--accent-fg`; hover `--accent-hover`; один на экран/футер |
| `secondary` | bg `--surface`, border `--border-strong`, text `--fg`; hover `--row-hover` |
| `danger` | bg `--danger`, text white — **только** confirm-кнопка destructive; в строках таблиц — `ghost` с текстом `--danger` |
| `ghost` | без границы/фона; text `--fg-2`; hover `--row-hover` |
| `link` | text `--accent`, underline on hover — для навигационных действий в тексте |

Sizes `md` (36) / `sm` (30). Disabled: opacity 0.5. Loading: spinner 14px слева + текст с `…`. Иконка 16px слева от текста, gap 8px.

### 4.2 IconButton

36/30 квадрат, radius 6, ghost или secondary. Обязателен `aria-label` + Tooltip.

### 4.3 Badge / StatusDot

Badge: h 22, radius 999, padding 0 8, 12px/500; bg `--{tone}-soft`, text `--{tone}`; опциональная точка 6px слева. Подпись — из карты §2.6.  
StatusDot отдельно — в ячейках таблиц перед именем (8px).

### 4.4 Field / Input / Textarea / Select / Checkbox / Switch

```
.field
  label   14px/500 --fg   (+ «*» accent для обязательных)
  control h 36, radius 6, border --border-strong, bg --surface
  .hint   13px --muted
  .error  13px --danger + иконка
```

Textarea: min-height 120px (код/YAML — mono 13px, 240px). Select — нативный с chevron 16px или кастом с тем же боксом.  
Checkbox 16×16 radius 4, checked bg `--accent`. Switch 36×20, checked bg `--accent`. Radio-карточки (выбор режима): border, radius 8, checked — border `--accent` + bg `--accent-soft`.

### 4.5 Card / FormSection

Card: bg `--surface`, border `--border`, radius 8, shadow-sm. Header: title 16/600 + optional description muted 13px + actions справа; border-bottom. Body padding 20px.  
FormSection = Card с формой внутри; поля в grid 2 колонки на ≥960px (широкие поля — span 2).

### 4.6 DataTable

Внутри Card без внутренних отступов. Thead sticky bg `--surface-2`, 12px/600 muted sentence-case. Row h 44 (dense 40). Ячейки 14px; mono 13px для host/id/path. Hover `--row-hover`. Выделенная строка `--accent-soft`.  
Row actions: `ghost sm` кнопки с текстом + `⋯` меню; появляются всегда (не только на hover).  
Сортировка: кликабельный th с иконкой стрелки. Пагинация/«Показать ещё» — если API отдаёт постранично.  
Пустая таблица → EmptyState внутри Card.

### 4.7 KeyValueList

Две колонки: label 13px muted (min-width 160) / value 14px `--fg` (mono где технически). Row h 32, разделитель `--border`.

### 4.8 Tabs

Горизонтальные, h 40; текст 14px `--muted`; активный — `--fg`/500 + underline 2px `--accent`. Счётчик в Badge neutral.

### 4.9 FilterChips / SegmentedControl

Chip: h 30, radius 6, border `--border-strong`, text 13px; active — bg `--accent-soft`, border/text `--accent`. Для 2–4 взаимоисключающих значений — SegmentedControl (одна рамка, активный сегмент `--surface` + shadow-sm).

### 4.10 KpiCard / SummaryStrip

Card компактная: label 13px muted → value 28px/600 tabular → optional delta/подпись 13px (например «из 24»). Тон применяется к точке/иконке слева, не к всей карточке. Grid 4 (≥1280) / 2 / 1. **Только при наличии поля API.**

### 4.11 PageHeader / PageShell

```
kicker (breadcrumb-like, 12px muted)         
h2 22/600                 [secondary] [primary]
description 14px muted, ≤ 1 строка
```

Без нижней границы; отступ до контента 24px.

### 4.12 EmptyState / InlineError / Banner

EmptyState внутри Card: иконка 32px `--muted`, title 16/600, description 14 muted, CTA primary/secondary. Без dashed-рамки.  
InlineError: Banner tone danger (bg `--danger-soft`, left bar 3px, иконка, текст, `Повторить` secondary sm).  
Banner также для info (`--accent-soft`) и warning — например «Есть несохранённые изменения».

### 4.13 Skeleton

Прямоугольники `--surface-2`, radius 4, лёгкий shimmer допустим (1.2s). Показывать при loading ≥ 300 мс.

### 4.14 CodeBlock / `<pre>`

Mono 12–13px; bg `--surface-2` (light) / `--bg` (dark); border; radius 6; padding 12px; кнопка «Копировать» IconButton в правом верхнем углу.

### 4.15 Kbd

Inline; border `--border-strong`; radius 4; padding 1px 6px; mono 12px; bg `--surface-2`.

### 4.16 Dialog

Центр; overlay `--overlay`; z 30; ширина sm/md/lg; bg `--surface`; radius 8; shadow-md.  
Header: title 18/600 + description muted + × IconButton. Body padding 24. Footer: border-top, кнопки справа `[ghost Отмена] [secondary …] [primary|danger]`.  
ESC/overlay закрывают, кроме `busy`. Focus trap.

### 4.17 ConfirmDialog

sm. Иконка тона (warning/danger) слева от title. Title — вопрос с объектом («Удалить сервер prod-01?»). Body — последствие. Кнопки `Отмена` ghost / `Удалить` danger (или `Подтвердить` primary).  
**Typed confirm** для опасных действий: label «Введите название {name} для подтверждения».

### 4.18 PromptDialog

sm; одно поле; `Отмена` / `Создать`|`Сохранить` primary.

### 4.19 Drawer

Справа; width 480; overlay; z 20; bg `--surface`; shadow-md. Header sticky (title 18/600, description, ×). Body — FormSections без внешней карточки. Footer sticky: `Отмена` ghost · `Сохранить` primary. Dirty close → UnsavedChangesDialog.

### 4.20 Toast

Низ-право; width 360; z 40; bg `--surface`; border; shadow-md; иконка тона; title 14/500 + optional description 13 muted; auto-dismiss 5с (error — до закрытия). `role="status"`.

### 4.21 DropdownMenu

Триггер `⋯` IconButton или кнопка с chevron. Меню bg `--surface`, radius 6, shadow-md, min-width 180; item h 36, иконка 16, hover `--row-hover`; destructive item text `--danger`; разделители `--border`.

### 4.22 Tooltip

Для IconButton и обрезанного текста. bg `--fg`, text `--surface`, 12px, radius 4, delay 300мс.

### 4.23 LiveIndicator

StatusDot + подпись из §2.6 (Подключение / Подключено / Отключено / Ошибка). Без анимации.

### 4.24 Avatar

Инициалы на `--accent-soft`, текст `--accent`, 28/32px, radius 999.

---

## 5. Паттерны страниц

### 5.1 CRUD-список

```
PageHeader (title + description + primary «Добавить»)
[KpiStrip — если API]
Card
  toolbar: search · FilterChips/Select · [⋯]
  DataTable | EmptyState
→ Drawer form → ConfirmDialog → Toast
```

### 5.2 Detail

```
PageHeader (breadcrumb kicker · title · Badge · actions)
Tabs
Card(s): KeyValueList / DataTable / CodeBlock
```

### 5.3 Live / Run

```
Card sticky header: Badge статуса · длительность · actions (Подтвердить / Остановить)
Tabs: Результат | Выполнение | Улики
Card body: лог (CodeBlock) или таблица шагов
```

### 5.4 Wizard

Dialog lg или страница. Steps rail слева (номер в круге 24px: active `--accent`, done `--success` ✓, future `--border-strong`). Footer `Назад` ghost · `Далее` primary; последний — `Сохранить` / `Сохранить и запустить`.

### 5.5 Settings-форма

FormSections (Card) по смыслу; sticky footer-bar внизу main при dirty: Banner «Есть несохранённые изменения» + `Отменить` ghost + `Сохранить` primary. Save → Toast «Изменения сохранены».

### 5.6 Split-панель терминала

Тёмный `.terminal-wrap` (`--terminal-bg`, radius 8) внутри светлого shell; боковая панель Files/AI/Linux UI — Card 340–400px.

---

## 6. Состояния данных

| State | UI |
| --- | --- |
| Loading < 300 мс | ничего не менять |
| Loading ≥ 300 мс | Skeleton (карточки/строки) |
| Empty | EmptyState в Card: title + description + CTA |
| Error | Banner danger + `Повторить` |
| Forbidden | `ForbiddenState`: EmptyState «Нет доступа к разделу» + путь mono + CTA «На главную». `FeatureGate` рендерит его внутри shell (не silent `Navigate`) |
| Backend down | Полноэкранный EmptyState «Сервер недоступен» + описание «Бэкенд не ответил. Проверьте, что Django запущен на :9000.» + `Повторить` |
| First-run | redirect `/settings/readiness?firstRun=1`; текст «Проверяем готовность…» |

---

## 7. Копирайт

### 7.1 Глоссарий кнопок

Создать · Сохранить · Отмена · Удалить · Повторить · Обновить · Открыть · Назад · Далее · Запустить · Остановить · Проверить подключение · Войти · Выйти · Продолжить · Изменить · Закрыть · Добавить · Подтвердить · Отозвать · Экспорт · Импорт

Pending: глагол + `…` («Сохранение…», «Проверка…»).

### 7.2 Заголовки и описания

Заголовок раздела — существительное («Серверы», «Готовность платформы»). Под заголовком — одна операционная строка («SSH-хосты, доступные вашей учётной записи»). Без приветствий и лозунгов.

### 7.3 Форматы

Дата/время `13.09.2026, 19:46` · относительное «5 мин назад» в таблицах с `title` полной датой · длительность `1 мин 12 с` · `{user}@{host}:{port}` mono · числа с тонкими пробелами для тысяч.

### 7.4 Статусы

Только русские подписи из §2.6, sentence-case. API-токен — в `title`.

### 7.5 Запрещено

«Добро пожаловать», «умный», «AI-powered», «магия», «проблем: N» без источника, англ. lowercase-статусы в UI, эмодзи в тостах и кнопках.

### 7.6 `frontend/src/locales/ru.json`

Операционные ключи переносим; маркетинговые переписываем по глоссарию; декоративные не переносим. RU хардкод в v3 до отдельного решения по i18n.

---

## 8. A11y и клавиатура

- Контраст текста ≥ 4.5:1 (`--fg`/`--muted` на `--surface` проверены; `--muted #64748b` на white = 4.7:1).
- Focus ring 2px `--focus`; trap в Dialog/Drawer; `Esc` закрывает; `Enter` — submit.
- IconButton — `aria-label`; Toast — `role="status"`; таблицы — `<th scope="col">`.
- Nav `aria-label="Основная навигация"`, `aria-current="page"`.
- `Ctrl+K` — палитра: навигация + серверы.

---

## 9. Связь с кодом

| Спека | Код v3 | Статус |
| --- | --- | --- |
| Токены v2 | `frontend-v3/src/index.css` | **переписать** (`:root` = light, `[data-theme="dark"]`) |
| Button / Badge / DataTable / EmptyState / PageHeader / PageShell | `components/ui/*` | обновить стили и подписи статусов |
| Card, Tabs, FilterChips, KpiCard, Field, Dialog, ConfirmDialog, PromptDialog, Drawer, Toast, DropdownMenu, Tooltip, Skeleton, Avatar, ForbiddenState | — | **создать** |
| Nav / theme | `lib/navigation.ts`, `lib/theme.tsx` (default → `light`) | обновить |
| Badge labels | `components/ui/Badge.tsx` | карта §2.6 |
