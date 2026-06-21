# WebTerm: полный аудит frontend, UI/UX и дизайн-направление

**Ветка:** `test`  
**Зафиксированное состояние:** commit `6002ef73c0c3d2b73adcba469887d7e414bf71db`  
**Область аудита:** React/Vite frontend в `frontend/`, активные маршруты, общие UI-примитивы, формы, модальные окна, уведомления, статусы, responsive-поведение и визуальные тесты.  
**Не входит в область:** Django-шаблоны, desktop-клиент, backend-архитектура и фактическая корректность API.

## 1. Итог в одном абзаце

WebTerm уже не является просто веб-терминалом. Сейчас это операционная платформа, которая объединяет серверы, SSH/SFTP, мониторинг, агентов, pipeline-автоматизации, skills, MCP, MARS, RBAC, SSO, память AI и аудит. Функционально frontend сильный и во многих местах хорошо разложен на компоненты. Главная проблема находится не в количестве возможностей и не в React как таковом, а в отсутствии единой визуальной грамматики: одновременно существуют несколько поколений интерфейса, разные шаблоны страниц, две системы уведомлений, несколько видов карточек и статусов, конкурирующие навигации, слишком мелкая типографика, чрезмерная вложенность рамок и смешение продуктовых понятий. Полностью переписывать приложение не нужно. Следует сохранить API-слой, React Query, routing, терминальный движок, pipeline-логику и большую часть бизнес-состояний, но последовательно заменить presentation layer и целиком переписать пять критических пользовательских потоков: создание сервера, создание агента, запуск/отчёт агента, верхнюю панель терминала и оболочку настроек.

## 2. Что это за проект сейчас

По активным маршрутам приложение состоит из следующих продуктовых зон:

1. **Аутентификация:** локальный вход и SSO.
2. **Панель:** пользовательский и административный dashboard.
3. **Серверы:** реестр серверов, группы, правила, SSH/SFTP, терминал и файловые операции.
4. **Агенты:** создание автоматизаций, расписания, запуск, согласование, отчёты и артефакты.
5. **Studio:** pipelines, AI-черновики, графовый редактор, история запусков, профили агентов, skills, MCP и настройки уведомлений.
6. **Kubernetes:** пока placeholder.
7. **MARS:** отдельный мастер AI-разработки и страница выполнения.
8. **Настройки:** AI-провайдеры и модели, пользователи, группы, разрешения, SSO, память и аудит.

Технологическая база хорошая: React 18, TypeScript, Vite, React Query, React Router, Radix/shadcn, React Hook Form, Zod, xterm, xyflow, CodeMirror, Playwright и axe уже присутствуют. Это означает, что главные инструменты для исправления UX уже установлены; проблема не требует смены стека.

## 3. Метод аудита и ограничение уверенности

Аудит выполнен по коду ветки `test`, активной таблице маршрутов, общим компонентам и предоставленным скриншотам. Я не проводил полноценную интерактивную сессию против живого backend со всеми ролями и состояниями данных, поэтому выводы о визуальной композиции, архитектуре интерфейса и поведении компонентов имеют высокую уверенность, а отдельные выводы о реальном пользовательском пути требуют проверки в работающем стенде.

Просмотрены:

- `frontend/src/App.tsx` и активные route guards;
- `AppLayout`, `AppSidebar`, `StudioNav`, `SettingsLayout`;
- `index.css`, `tailwind.config.ts`, `DESIGN.md`;
- общие `PageShell`, `PageHero`, `SectionCard`, `StatusBadge`, `Button`, `Dialog`, toast-компоненты;
- все активные верхнеуровневые страницы;
- основные формы и мастера;
- терминальная оболочка, pipeline editor, AI draft workspace;
- визуальные Playwright-тесты.

## 4. Главный диагноз

### 4.1. Интерфейс создавался по функциям, а не по пользовательским задачам

Почти каждая новая зона получила собственный hero, собственный набор карточек, собственный способ показывать статусы и собственную вторичную навигацию. Из-за этого пользователь каждый раз заново учится читать экран.

Примеры:

- общая панель использует `PageHero`;
- Studio использует `StudioHero` и отдельный `StudioNav`;
- MARS имеет собственный фон, палитру и мастер;
- Settings имеет вторую боковую панель внутри основной;
- immersive-страницы используют третий заголовок;
- agent report строит ещё один визуальный язык внутри модалки.

### 4.2. Слишком много поверхностей и рамок

Основной паттерн сейчас: фон -> hero-карточка -> section-карточка -> вложенная карточка -> строка с собственной рамкой -> badge. Это создаёт ощущение тяжёлого «конструктора админок» и убивает приоритеты. Пользователь видит много одинаково важных прямоугольников.

Нужно перейти к схеме:

- один canvas страницы;
- один основной surface для сложного рабочего пространства;
- section divider вместо отдельной карточки для каждой группы;
- карточки только для самостоятельных объектов или KPI;
- тень только у overlay, popover и dialog.

### 4.3. Типографика слишком мелкая

Текущий `DESIGN.md` прямо задаёт `text-xs`, 13 px, 11 px, 10 px и 9 px как базовые размеры. Это основная причина ощущения «всё мелкое, серое и одинаковое». В приложении много `text-[9px]`, `text-[10px]` и `text-[11px]` для статусов, метаданных, действий и пояснений.

Новый минимум:

- основной текст: 14 px / 20 px;
- вторичный текст: 13 px / 18 px;
- подпись и metadata: 12 px / 16 px;
- field label: 13 px / 18 px;
- 10-11 px оставить только для keyboard shortcut, ID и очень редких micro-label;
- page title: 24 px desktop, 20 px mobile;
- section title: 16 px.

### 4.4. Teal выполняет слишком много ролей

Сейчас `primary` используется одновременно как бренд, active state, online, healthy, info и иногда success. Это делает семантику неясной. Online-сервер и выбранная вкладка не должны выглядеть как одно и то же состояние.

Разделение:

- teal - бренд, primary action, selected state;
- green - успешно, healthy, online;
- blue - информация и running;
- amber - warning и waiting;
- red - failed, critical, destructive;
- violet - AI/category, но не общий статус.

### 4.5. Смешение русского и английского языка

В коде одновременно встречаются `Fleet Health`, `Control Center`, `Pipeline`, `Timeline`, `Run`, `Changed files`, `Verification`, `Final report`, `staff`, `override`, `Operations console` и русские подписи. Это противоречит собственному `DESIGN.md`.

Решение: все product copy хранить в typed i18n dictionaries; запретить user-facing string literals ESLint-правилом или CI-проверкой для route-компонентов.

### 4.6. Две системы уведомлений

В корневом `App.tsx` одновременно подключены Radix Toast и Sonner. Части приложения вызывают `useToast`, другие напрямую `toast` из Sonner. В результате различаются расположение, внешний вид, время жизни, действия и обработка ошибок.

Решение: оставить только Sonner через единый adapter `notify`, чтобы доменный код не зависел от библиотеки.

### 4.7. Нативные browser dialogs остаются в production-потоках

Используются `window.confirm`, `confirm`, `prompt` и `alert` для удаления файлов, агентов, пользователей, групп, разрешений и сброса пароля. Это ломает визуальную систему, неудобно на mobile, не показывает контекст и особенно плохо для безопасности.

Решение: единый `ConfirmDialog`, `DeleteDialog`, `ResetPasswordDialog` и `UnsavedChangesDialog`.

### 4.8. Формы не имеют единой модели валидации

React Hook Form и Zod установлены, но многие большие формы и мастера управляются десятками `useState`. Disabled-кнопка часто не объясняет причину. Некоторые формы проверяют только имя, хотя сохраняют гораздо более опасную конфигурацию.

Решение: RHF + Zod, field-level errors, form summary, `isDirty`, `isValid`, server error mapping, typed schema на каждую форму.

### 4.9. Информационная архитектура дублирует понятия

Есть главные «Агенты» и отдельные `Studio / Agents`, которые фактически являются профилями. Есть общая навигация и дополнительный `StudioNav`. Есть основная sidebar и ещё одна большая sidebar в Settings. Пользователь не понимает, где объект, где шаблон, где запуск, где профиль.

### 4.10. Тесты защищают только небольшую часть визуального продукта

Visual regression покрывает только login, servers, studio и settings на одном основном viewport. Нет snapshots для agents, create-agent, terminal, run report, pipeline editor, MARS, dialogs и mobile.

## 5. Что не нужно переписывать

Сохранять и развивать:

- React, TypeScript, Vite;
- React Query и существующие query keys;
- API clients и server types;
- feature gates и route guards, изменив только UX недоступности;
- xterm integration;
- xyflow graph logic;
- CodeMirror editors;
- доменные hooks pipeline editor;
- websocket/polling run logic;
- текущую декомпозицию сложных страниц на feature-компоненты там, где она уже выполнена.

Не следует начинать с нового framework, CSS-in-JS или тотального rewrite. Это увеличит риск и отложит исправление UX.

## 6. Что необходимо переписать полностью

1. `CreateAgentDialog.tsx`, `AgentWizardProgress.tsx`, основную композицию `AgentWizardStepContent.tsx`.
2. `ServerFormDialog.tsx` как новый безопасный connection flow.
3. `TerminalHeader.tsx` и раскладку terminal utilities.
4. Presentation layer `AgentRunPage` и `AgentReportModal`.
5. `SettingsLayout.tsx` и базовый шаблон страниц настроек.
6. Notification/confirmation layer приложения.
7. Shared status system.
8. Shared page header/surface primitives.

## 7. Целевое направление: WebTermAI Ops Console 2.0

### 7.1. Принципы

1. **Сначала операционный ответ.** На экране сразу видно: что происходит, где, насколько критично, что делать.
2. **Одна основная задача на экран.** Вторичные действия скрываются в меню или context panel.
3. **Один primary CTA.** Исключение - редакторы, где допустимы Validate и Run, но их роли должны быть разными.
4. **Progressive disclosure.** Технические детали доступны, но не конкурируют с итогом.
5. **Состояние не выражается только цветом.** Иконка, текст и форма обязательны.
6. **Опасные действия всегда объясняют последствия.**
7. **Плотность зависит от контекста.** Terminal и log viewer плотные; формы и мастера - спокойные.
8. **Один язык и одни термины.**
9. **Все страницы используют один shell.** Исключения только для terminal и graph editor.

### 7.2. Предлагаемая палитра

| Token | HEX | Использование |
|---|---:|---|
| Canvas | `#071019` | основной фон приложения |
| Canvas secondary | `#09141E` | фон рабочих зон и editor canvas |
| Surface 1 | `#0D1822` | базовая панель |
| Surface 2 | `#111F2C` | приподнятая или selected панель |
| Hover | `#162635` | hover строк и нейтральных кнопок |
| Border | `#223444` | стандартный divider |
| Border strong | `#30475A` | focus, selected, важная граница |
| Text primary | `#E8F0F6` | заголовки и основной текст |
| Text secondary | `#A6B6C6` | пояснения |
| Text muted | `#7890A4` | metadata не меньше 12 px |
| Primary | `#22C7AE` | CTA, выбранный item, focus |
| Primary hover | `#2AD6BC` | hover primary |
| Success | `#35C981` | healthy, completed, online |
| Warning | `#F2B84B` | warning, waiting, risk |
| Danger | `#F06464` | failed, critical, delete |
| Info | `#5DA9F6` | running, informational |
| AI accent | `#9B87F5` | AI feature/category only |
| Disabled text | `#607386` | disabled state |

Все предложенные основные текстовые и семантические цвета имеют достаточный запас контраста на `Canvas` и `Surface 1`; не нужно дополнительно уменьшать их opacity для обычного текста.

### 7.3. Поверхности

- Canvas страницы не имеет рамки и тени.
- `PageHeader` не является карточкой.
- `ContentPanel` имеет один solid background и одну border.
- `Section` внутри панели разделяется `border-top`, а не новой карточкой.
- `ObjectCard` используется только для самостоятельного объекта: сервер, pipeline, agent template.
- Overlay, dropdown, dialog получают тень.
- Убрать глобальные radial gradients из большинства внутренних экранов. Допустить слабый gradient только на login или marketing-empty state.

### 7.4. Типографика

| Роль | Размер / line-height | Вес |
|---|---|---|
| Page title | 24/32 desktop, 20/28 mobile | 650/700 |
| Section title | 16/24 | 600 |
| Card title | 14/20 | 600 |
| Body | 14/20 | 400/500 |
| Secondary | 13/18 | 400 |
| Label | 13/18 | 500/600 |
| Metadata | 12/16 | 400/500 |
| Mono log | 12-13/18 | 400 |
| KPI | 24-28/32 | 650/700 |

Не использовать uppercase для длинных русских labels. Uppercase допустим для короткого статуса, severity или kicker длиной до 12 символов.

### 7.5. Размеры и spacing

- base unit: 4 px;
- control default: 40 px;
- compact control: 36 px только в data table и editor toolbar;
- icon button: минимум 40 x 40 px;
- card radius: 10 px;
- input/button radius: 8 px;
- dialog radius: 12 px;
- page horizontal padding: 24 px desktop, 16 px mobile;
- section gap: 24 px;
- field gap: 8 px;
- content max width: 1440 px;
- длинные формы: 760-960 px или side sheet, не растягивать на весь экран.

## 8. Спецификация общих компонентов

### 8.1. Кнопки

**Primary**

- solid `#22C7AE`, текст `#041A17`;
- один primary action на обычном экране;
- без glow;
- hover `#2AD6BC`;
- loading сохраняет label и добавляет spinner;
- disabled показывает tooltip/inline reason, когда причина не очевидна.

**Secondary**

- `Surface 2`, border `Border`, текст primary;
- для «Проверить», «Поделиться», «Скачать», «Назад».

**Ghost**

- только для row actions и chrome;
- hover `Hover`;
- icon-only обязательно имеет tooltip и aria-label.

**Destructive**

- красная кнопка только внутри confirmation dialog или danger zone;
- в списке delete находится в `...` меню;
- не окрашивать весь интерфейс красным до момента подтверждения.

### 8.2. StatusBadge

Новый API:

```ts
type StatusTone = "neutral" | "info" | "success" | "warning" | "danger";

type StatusBadgeProps = {
  icon: LucideIcon;
  label: string;
  tone: StatusTone;
  size?: "sm" | "md";
  description?: string;
};
```

Правила:

- label минимум 12 px;
- pulse только для действительно live/running состояния;
- uppercase только для `FATAL`, `HIGH`, `P0`;
- status mapping централизован, а не создаётся на странице;
- online = green, running = blue, selected = teal.

### 8.3. Уведомления

Оставить один `notify` adapter поверх Sonner:

```ts
notify.success({ title, description, action });
notify.error({ title, description, details, retry });
notify.progress({ id, title, progress });
```

Поведение:

- success: 4 секунды;
- info: 6 секунд;
- error: 10 секунд или до закрытия;
- long-running operation: один persistent toast, который обновляется;
- reversible action: «Отменить»;
- field validation никогда не показывать toast-ом;
- backend stack/details скрыть под «Подробнее» и дать «Скопировать ID ошибки».

### 8.4. Dialog, Sheet и Wizard

- подтверждение: 420-480 px;
- обычная форма: right sheet 560-640 px;
- сложный мастер: full-screen dialog с max-width 1400 px;
- header/footer fixed, scroll только body;
- dirty form закрывается через Unsaved Changes dialog;
- close label локализован;
- destructive dialog показывает имя объекта и последствия;
- Enter не должен случайно подтверждать опасное действие.

### 8.5. Формы

- React Hook Form + Zod;
- label над полем;
- required отмечается текстом или `*`, но ошибка всегда словами;
- helper text 12-13 px;
- validation on blur, critical checks on submit;
- server error привязывается к полю, если возможно;
- secret field имеет show/hide, copy и статус сохранения;
- native `<select>` постепенно заменить на единый Radix Select/Combobox;
- searchable entity selection использовать Command/Popover.

### 8.6. Таблицы и списки

- таблица для серверов, пользователей, runs и audit;
- карточки для templates и onboarding;
- row height 52-60 px;
- sticky header при длинном списке;
- filters находятся в одной toolbar;
- row click открывает detail;
- actions справа в `...` menu;
- destructive action не видна постоянно;
- mobile превращается в structured list, а не горизонтально прокручиваемую desktop-table без адаптации.

### 8.7. Loading, empty и error states

**Loading:** skeleton сохраняет будущую геометрию, spinner только для локальной операции.  
**Empty:** объясняет причину и предлагает один следующий шаг.  
**Error:** человеческий текст, retry, technical details, correlation ID.  
**Permission denied:** отдельный экран/inline state, а не молчаливый redirect на Servers.

## 9. Навигация и терминология

### 9.1. Предлагаемая структура главной навигации

1. **Обзор**
2. **Инфраструктура**
   - Серверы
   - Kubernetes (показывать только при готовом модуле)
3. **Автоматизации**
   - Агенты
   - Запуски агентов
4. **Studio**
   - Pipelines
   - Запуски
   - Черновики AI
   - Skills
   - Интеграции MCP
   - Профили выполнения
5. **MARS beta**
6. **Настройки**

### 9.2. Ключевые переименования

| Сейчас | Предлагается | Причина |
|---|---|---|
| Агенты | Автоматизации / Агенты | отделить объект от профиля |
| Studio / Agents | Профили выполнения | это reusable config, не runnable agent |
| Fleet Health | Состояние серверов | русский и понятный термин |
| Pipeline | Pipeline или Сценарий - выбрать один термин | не смешивать внутри одного экрана |
| Run | Запуск | локализация |
| Control Center | Панель управления | соответствует продукту |
| Memory dreams | Консолидация памяти | объясняет действие |
| MARS | MARS beta: AI-разработка | аббревиатура без контекста непонятна |

## 10. Аудит по страницам

## 10.1. Login

**Файл:** `frontend/src/pages/Login.tsx`

**Что хорошо:** desktop split-layout, понятная форма, большие inputs и submit, отдельный выбор языка.

**Проблемы:**

- английские `Operations console`, `Secure operations` в русском интерфейсе;
- «Локально» и «SSO / auto» выглядят как два режима одной формы, хотя это разные authentication journeys;
- нет show password и Caps Lock warning;
- backend error выводится почти напрямую;
- SSO не объясняет, какой provider будет использован;
- левая половина на широком экране содержит много пустоты.

**Новый вариант:**

- desktop: 42% informational panel, 58% auth area;
- заголовок «Вход в WebTermAI»;
- две явные вкладки: «Локальная учётная запись» и «Корпоративный SSO»;
- SSO-вкладка показывает provider/domain и одну кнопку «Продолжить через SSO»;
- local-вкладка: username, password, show/hide, Caps Lock, submit;
- ошибка под формой: «Не удалось войти. Проверьте логин и пароль», technical details только по раскрытию;
- ссылка «Проблемы со входом?» ведёт к администратору/документации;
- язык остаётся в правом верхнем углу.

**Цвета:** primary только submit; error `Danger`; informational bullets нейтральные, без трёх teal-иконок одинаковой важности.

**Приоритет:** P1.

## 10.2. Пользовательский Dashboard

**Файл:** `frontend/src/pages/UserDashboard.tsx`, dashboard components.

**Проблемы:**

- много виджетов одинакового веса;
- KPI, server health, recent servers, alerts, activity и quick tools конкурируют;
- встречается `Fleet Health` и другие английские подписи;
- metadata часто 9-11 px;
- customization показана слишком рано и усложняет default experience;
- quick action «Создать агента» ведёт в Studio Skills, что концептуально неверно;
- colored metric cards и nested SectionCards создают шум.

**Новый default layout:**

1. Plain page header «Обзор» + last refresh.
2. Critical strip: offline servers, failed runs, pending approvals.
3. 4 KPI максимум: доступные серверы, активные инциденты, запуски сегодня, ожидают подтверждения.
4. Левая колонка 8/12: «Требует внимания» и recent activity.
5. Правая колонка 4/12: quick actions и состояние сервисов.
6. «Настроить панель» открывает drawer; режим редактирования не должен быть постоянной частью экрана.

**Кнопки:** `Открыть инциденты` primary только при наличии проблем; остальные secondary/ghost.

**Приоритет:** P1.

## 10.3. Административный Dashboard

**Файлы:** `AdminDashboard.tsx`, `adminDashboardWidgets.tsx`.

**Проблемы:**

- отдельная визуальная стилистика `Admin Control Center`, `System Secure`;
- слишком много микрометрик и цветных индикаторов;
- графики и списки не образуют hierarchy «сначала риски»;
- маленькие подписи усложняют сканирование.

**Новый вариант:**

- тот же shell, что у пользовательского dashboard;
- верхняя risk summary: critical alerts, unavailable servers, auth failures, pending updates;
- секции: Infrastructure health, Automation health, Security activity;
- графики только там, где есть trend/decision;
- «Система защищена» не показывать как вечный зелёный badge: выводить конкретные проверки и timestamp.

**Приоритет:** P1.

## 10.4. Серверы

**Файлы:** `Servers.tsx`, `ServersListTab.tsx`.

**Что хорошо:** feature decomposition, группы, правила, быстрый SSH, расширенные возможности.

**Проблемы:**

- search находится в hero, дополнительные фильтры разнесены;
- вкладки «Серверы / группы / правила / playbook» смешивают объектный список и настройки;
- карточки/группы перегружены host, OS, status, tags и icon actions;
- Sparkles action не объясняет результат;
- edit/delete видны на каждой строке;
- row не имеет одного очевидного primary action;
- mobile-композиция легко становится тесной.

**Новый вариант:**

- plain header «Серверы», count и CTA «Добавить сервер»;
- sticky toolbar: Search, Status, Environment, Group, Tags, View;
- table default: Status, Name, Endpoint, Group/Environment, Last seen, Health, Actions;
- click row -> server drawer/detail;
- button «Открыть терминал» внутри detail или явная primary row action;
- `...` menu: SFTP, Linux UI, Edit, Duplicate, Delete;
- группы становятся filter/group-by, а управление группами - отдельным contextual drawer;
- правила и playbook вынести в secondary sub-navigation страницы Infrastructure.

**Цвета:** online green; degraded amber; unreachable red; selected row teal border/neutral fill.

**Приоритет:** P0/P1.

## 10.5. Создание и редактирование сервера

**Файл:** `ServerFormDialog.tsx`.

**Проблемы:**

- длинная форма одним полотном;
- mixed native select и shadcn controls;
- нет обязательного test connection;
- auth, sudo, tags и notes имеют одинаковый визуальный вес;
- root/sudo risk не объяснён;
- disabled Save не сообщает, чего не хватает;
- secrets и key upload не образуют понятный security flow.

**Переписать как right sheet 640 px:**

1. **Подключение:** name, host, port, username, environment.
2. **Аутентификация:** password/key/agent, secret status, key validation.
3. **Политика доступа:** sudo policy, root warning, group/tags, notes.
4. **Проверка:** кнопка «Проверить подключение», latency, SSH fingerprint, permissions, result log.

Footer:

- `Отмена` ghost;
- `Проверить` secondary;
- `Сохранить сервер` primary доступна после валидной формы; test может быть optional для edit, но warning видим.

Для prod + root/sudo показывать confirmation с точным scope.

**Приоритет:** P0.

## 10.6. Terminal workspace

**Файлы:** `TerminalPage.tsx`, `TerminalHeader.tsx`, terminal components.

**Что хорошо:** мощный рабочий экран, multiple sessions, xterm, SFTP, editor, AI panel, resize.

**Проблемы:**

- один header одновременно содержит back, server identity, tabs, add, SFTP, Linux UI, AI и settings;
- server identity дублируется;
- utility modes конкурируют с terminal tabs;
- icon-only controls недостаточно объяснены;
- маленькие endpoint/status labels;
- подтверждения закрытия/удаления местами через browser confirm;
- AI и files выглядят как ещё одна группа равноправных вкладок, хотя это инструменты текущей сессии.

**Новая структура:**

**Row 1:** Back, server switcher, connection state, latency, reconnect, session menu.  
**Row 2:** terminal tabs + `+`; справа utility toggles «Файлы», «AI», «Настройки».

- utility открывается в resizable right panel;
- SFTP и AI scoped к активному серверу/terminal tab;
- connection lost показывается persistent inline banner;
- keyboard shortcuts доступны через command palette;
- mobile: server header, horizontal session tabs, utility bottom sheet;
- unsaved file/active command closing uses custom confirmation.

**Цвета:** terminal canvas остаётся почти чёрным; chrome использует общие surfaces; зелёный не используется как декоративный terminal cliché, только status/output semantics.

**Приоритет:** P0.

## 10.7. Список агентов

**Файл:** `AgentsPage.tsx`.

**Проблемы:**

- в строках много равнозначных действий run/edit/delete/report/watch;
- type/mode заметнее, чем назначение агента;
- sudo badge есть, но не раскрывает реальный scope/risk;
- фильтр только по типу;
- browser confirm на удаление;
- report banner и modal добавляют ещё один уровень UI.

**Новый список:**

- Name + purpose;
- Scope: N servers / group;
- Trigger: Manual / schedule;
- Last result + duration;
- Next run;
- owner;
- primary action `Запустить` или `Открыть запуск`;
- `...` menu: Edit, Duplicate, Export, Delete.

Filters: search, status, trigger, owner, environment, risk.  
Type отображается вторичным neutral badge.

**Приоритет:** P1.

## 10.8. Мастер создания агента

**Файлы:** `CreateAgentDialog.tsx`, `AgentWizardProgress.tsx`, `AgentWizardStepContent.tsx`.

**Это главный кандидат на полный UI rewrite.**

**Текущие проблемы:**

- более 25 локальных state variables;
- огромный prop contract step content;
- пять больших step-карточек занимают много высоты;
- шаги кликабельны без завершения обязательных полей;
- canSave проверяет недостаточную часть конфигурации;
- Save и Create имеют пересекающуюся семантику;
- right summary повторяет данные, но не показывает readiness/risk;
- commands - простой textarea без syntax/validation;
- server selection без поиска, environment и health;
- schedule - шесть одинаковых карточек;
- review не содержит test run и security checks.

**Новая модель данных:**

```ts
type AgentDraft = {
  scenario: { type; templateId };
  behavior: { name; description; commands; instructions; sudoPolicy };
  environment: { serverIds; schedule };
  resources: { skillSlugs; materials; notifications };
};
```

Использовать `useForm<AgentDraft>` + Zod или reducer/state machine, а не отдельный state для каждого поля.

**Новый мастер:**

1. **Сценарий** - тип, template search, результат, duration, risk.
2. **Поведение** - name, goal, command editor, instructions, sudo policy.
3. **Окружение** - searchable server table, selected chips, schedule builder.
4. **Ресурсы** - skills, materials, notifications.
5. **Проверка** - readiness, security checks, diff, test run.

**Right rail:** live preview, readiness %, risks, estimate; не повторяет все поля.

**Footer:** Back / autosave state / Next. На последнем шаге `Сохранить как черновик` secondary и `Создать агента` primary.

**Обязательные проверки:**

- имя;
- минимум одна валидная команда или template action;
- минимум один server для runnable agent;
- sudo risk acknowledged;
- schedule valid;
- Telegram config valid, если включён;
- test run для prod-рискованных сценариев.

**Приоритет:** P0.

## 10.9. Запуск агента и отчёт

**Файлы:** `AgentRunPage.tsx`, `AgentReportModal.tsx`.

**Проблемы:**

- mixed `Pipeline`, `Timeline`, `Report`, raw statuses;
- очень маленькие 9-10 px labels и exit badges;
- текущий step/status часто выражен dot/цветом;
- header перегружен tabs, actions, status и counters;
- report modal пытается быть полноценной страницей внутри 90vh dialog;
- technical console конкурирует с выводом и решением;
- большие кастомные цветные блоки создают отдельный дизайн.

**Новая route-page:**

- header: agent name, server scope, status, started, duration, owner;
- при running: current step, progress, Stop/Approve;
- при completed/failed: outcome summary;
- tabs: `Обзор`, `События`, `Логи`, `Артефакты`;
- Overview: what happened, impact, result, recommendations;
- Events: filterable timeline;
- Logs: command output, search, copy, wrap toggle;
- Artifacts: files/downloads;
- report modal оставить только как quick preview из списка, с CTA «Открыть полный отчёт».

Approval и Stop используют explicit confirmation.  
Exit code не показывать 9 px badge: строка получает icon + «Завершено / Код 1».

**Приоритет:** P0.

## 10.10. Studio landing

**Файл:** `StudioPage.tsx`, `StudioNav.tsx`.

**Проблемы:**

- отдельная custom hero grammar;
- до шести stat chips в header;
- search находится в отдельной карточке;
- second navigation добавляется поверх global navigation;
- список pipelines и linked modules конкурируют;
- смешение «runbook», pipeline, profile, skills, MCP.

**Новый layout:**

- compact contextual tabs под plain page header;
- primary CTA «Создать pipeline»;
- secondary «Создать через AI»;
- health strip только для failed/running/needs review;
- search + status + owner + tags в одной toolbar;
- pipelines в list/table по умолчанию, cards как optional view;
- отдельная секция «Инструменты Studio» только в empty/onboarding state, не постоянно.

**Приоритет:** P1.

## 10.11. AI-черновики Studio

**Файл:** `StudioDraftsPage.tsx` и `studio-drafts/*`.

**Что хорошо:** URL state, отдельные queue/graph/composer/review components, mobile panes.

**Проблемы:**

- на desktop три плотные колонки 300 / graph / 390;
- composer и review находятся в одном right aside и могут восприниматься как две конкурирующие фазы;
- пользователь не видит простой последовательности «описать -> проверить -> применить»;
- validation/risk спрятаны в сложном workspace;
- queue постоянно отнимает ширину.

**Новый вариант:**

- queue 280 px collapsible;
- center graph - основное workspace;
- inspector 360 px с tabs `Запрос`, `Проверка`, `Изменения`;
- top progress: Draft -> Validated -> Ready -> Applied;
- AI questions показываются как blocking checklist;
- dangerous risk блокирует Apply и объясняет, что исправить;
- mobile использует отдельные routes/panes с явным Back.

**Приоритет:** P1.

## 10.12. Pipeline editor

**Файлы:** `PipelineEditorPage.tsx`, `pipeline-editor/*`.

**Что хорошо:** бизнес-логика уже хорошо вынесена в hooks, graph actions и dialog state; эту архитектуру нельзя выбрасывать.

**Проблемы presentation layer:**

- toolbar содержит Save, Nodes, Run, AI и raw last run в одном весе;
- relation Save/Validate/Run неочевидна;
- hardcoded background в activity bar;
- несколько status bars подряд уменьшают canvas;
- AI side panel и node inspector могут конкурировать;
- маленькие h-9 controls и status text.

**Новый toolbar:**

- Back;
- editable name + `Сохранено / Есть изменения`;
- `Проверить` secondary;
- `Запустить` primary;
- AI toggle secondary/icon+label;
- More: history, duplicate, export, delete.

Activity bar показывать только во время live run или когда есть blocking warning. Flow summary сделать collapsible. Node palette слева, inspector справа, AI заменяет inspector tab, а не создаёт ещё один параллельный panel.

**Не делать silent autosave опубликованного graph.** Допустим local draft autosave, но Publish/Save должен быть явным.

**Приоритет:** P1.

## 10.13. История pipeline-запусков

**Файл:** `PipelineRunsPage.tsx`.

**Что хорошо:** split-pane - правильный паттерн для run inspection.

**Проблемы:**

- только status chips, нет search/date/pipeline filters;
- metadata 11 px;
- повторный click закрывает выбранный run, что неожиданно;
- mobile detail navigation не выражена как отдельный экран;
- raw status и ID доминируют.

**Новый вариант:**

- filter toolbar: search, pipeline, status, date range, owner;
- list rows 60 px: pipeline, status, started, duration, trigger;
- выбранная строка остаётся selected;
- detail pane сохраняется;
- mobile click ведёт на `/studio/runs/:id` или full-screen detail sheet;
- failed run показывает concise error and retry action.

**Приоритет:** P1.

## 10.14. Профили агентов Studio

**Файл:** `AgentConfigPage.tsx`.

**Главная проблема:** название дублирует основную сущность «Агент».

**Переименовать:** `Профили выполнения` или `Профили агента для pipeline`.

**Проблемы UI:**

- длинная 4xl modal form;
- model, tools, MCP, skills, scope и sharing находятся одним полотном;
- Save валидирует в основном name;
- no readiness/risk summary;
- cards grid плохо сравнивается при большом количестве profiles.

**Новый вариант:**

- table/list с name, model, tools, scope, owner, updated;
- edit в right sheet 640-720 px;
- sections/tabs: Основное, Инструменты, Scope, Доступ;
- sticky save bar с dirty state;
- risk summary для tools/sudo/production scope;
- read-only profile явно помечается в header.

**Приоритет:** P1.

## 10.15. Skills

**Файл:** `StudioSkillsPage.tsx`, `studio-skills/*`.

**Что хорошо:** есть catalog, workspace, validation, templates, file editor и access settings.

**Проблемы:**

- catalog и IDE-like authoring находятся в одной route state;
- очень много состояний в page orchestrator;
- browser confirm для удаления файла;
- unsaved editor state не защищён при выборе другого файла/skill;
- validation, settings и file editing конкурируют;
- badges и metadata слишком мелкие.

**Новая структура:**

- `/studio/skills` - catalog;
- `/studio/skills/:slug` - detail/editor;
- detail: file tree, CodeMirror, validation/metadata inspector;
- tabs inspector: Validation, Settings, Access;
- dirty file guard;
- create skill wizard на 2 шага: Template/metadata -> Starter files/runtime;
- delete file через custom dialog, SKILL.md защищён с объяснением.

**Приоритет:** P1/P2.

## 10.16. MCP

**Файл:** `MCPHubPage.tsx`, `MCPForm.tsx`.

**Проблемы:**

- connection health не является главным визуальным сигналом;
- card содержит transport, owner, shared, readonly и actions в большом количестве badges;
- test/edit/delete icon actions слабо различимы;
- templates не имеют clear categories/use cases;
- env secrets требуют более явной security semantics.

**Новый вариант:**

- tabs `Подключения` / `Каталог`;
- connection row: status, name, transport/endpoint, tools count, last test, owner;
- primary action `Проверить` только если status unknown/failed; обычно в menu;
- details drawer показывает command/url, env variable names без secret values, capabilities и test history;
- create/edit sheet с live connection preview и `Проверить перед сохранением`;
- templates: search, category, required secrets, supported capabilities.

**Приоритет:** P1.

## 10.17. Настройки уведомлений Studio

**Файл:** `NotificationsSettingsPage.tsx`.

**Что хорошо:** test actions, secret reveal, readiness calculations.

**Проблемы:**

- длинная страница из stacked SectionCards;
- три readiness cards дублируют содержание секций;
- global Save сверху, но dirty state не виден;
- show secret button исключён из tab order;
- test result локальный, а save/error feedback глобальный;
- Telegram и Email выглядят всегда активными, хотя могут быть не настроены.

**Новый вариант:**

- channel cards: Telegram, Email, Public URL;
- каждая card имеет Enable toggle, Status, summary и `Настроить`;
- edit открывает sheet/expand section;
- sticky dirty bar: `Есть несохранённые изменения` + Save/Discard;
- test result остаётся в секции и содержит timestamp;
- show/hide secret доступен с keyboard;
- public URL вынести в General settings, не считать каналом доставки.

**Приоритет:** P1.

## 10.18. Kubernetes placeholder

**Файл:** `KubernetesPage.tsx`.

**Проблема:** navigation ведёт на большую пустую страницу с PageHero, SectionCard и ещё одним EmptyState. Это выглядит как сломанный продукт.

**Решение:**

- скрыть пункт feature flag-ом до минимальной готовности; или
- показывать компактный beta onboarding: «Подключить кластер», поддерживаемые способы, roadmap, docs;
- убрать 520 px искусственной пустоты.

**Приоритет:** P2, но скрытие незавершённой страницы - P0 для публичного релиза.

## 10.19. MARS - мастер проекта

**Файл:** `MarsPage.tsx`, `mars/*`.

**Что хорошо:** flow Idea -> questions -> plan -> run, project history и progress.

**Проблемы:**

- выглядит как отдельное приложение из-за своего radial gradient, slate/emerald palette и `Project Command Center`;
- смешивает русский и английский: scripts, automation, guided brief;
- одновременно три зоны: history, wizard, orchestrator rail;
- пять шагов включают final state как отдельный шаг, что удлиняет flow;
- аббревиатура MARS не объяснена.

**Новый вариант:**

- тот же app canvas/tokens;
- header «MARS beta - AI-разработка»;
- project history collapsible drawer;
- 4 шага: Задача, Уточнения, План, Выполнение;
- результат является state шага Выполнение, а не отдельной навигацией;
- status rail появляется только после запуска;
- technical model names не показывать обычному пользователю;
- primary action всегда соответствует следующему шагу.

**Приоритет:** P2.

## 10.20. MARS run

**Файл:** `MarsRunPage.tsx`.

**Проблемы:**

- длинный экран с Progress, events, execution log, result, quality, changed files, tests, final report одновременно;
- mixed `Verification`, `Changed files`, `Tests`, `Final report`;
- внутренние Codex/Gemini concepts просачиваются в user-facing UI;
- много вложенных SectionCards;
- важный итог появляется ниже raw logs.

**Новый вариант:**

- header: project, status, duration, Stop;
- Overview первым: итог, changed files count, tests, next action;
- tabs: `Ход работы`, `Логи`, `Изменения`, `Отчёт`;
- progress timeline с этапами и timestamps;
- logs search/copy/download;
- quality review переводится в «Проверка качества» без model names;
- final report имеет отдельный readable layout.

**Приоритет:** P2.

## 10.21. Settings shell

**Файл:** `components/settings/SettingsLayout.tsx`.

**Проблемы:**

- внутри global sidebar появляется ещё одна sidebar шириной 304 px;
- navigation item высотой 60 px с icon box и description - слишком тяжёлый;
- footer hint постоянно занимает место;
- content max 6xl плюс две sidebars оставляют мало ширины;
- заголовки страниц затем используют ещё один собственный pattern.

**Переписать:**

- contextual nav 220-240 px, компактные items 40-44 px; или horizontal category tabs для среднего количества разделов;
- sidebar description показывать tooltip/section intro, не на каждом item;
- убрать footer hint;
- content header единый;
- mobile sheet сохранить;
- dirty settings показывать sticky bottom bar.

**Приоритет:** P0/P1.

## 10.22. AI settings

**Файлы:** `SettingsAIPage.tsx`, `AiSettingsPanel`.

**Проблемы:**

- header 16 px и description 11 px слишком малы;
- «N активных API» и «Есть черновик» не объясняют health;
- provider secrets, model roles и runtime могут восприниматься одной сложной формой;
- нет единого test provider pattern.

**Новый layout:**

1. Providers: card/rows с Connected/Not configured/Error и `Проверить`.
2. Role assignment matrix: role -> provider/model -> fallback.
3. Local/Ollama runtime.
4. Safety/fallback.
5. Sticky Save bar только при dirty.

**Приоритет:** P1.

## 10.23. Access overview

**Файл:** `SettingsAccessPage.tsx`.

**Проблемы:**

- страница в основном повторяет links, уже видимые в settings sidebar;
- цветные cards Users/Groups/Permissions не дают operational insight;
- quick actions дублируют те же переходы;
- длинный explanatory block занимает место.

**Новый overview:**

- metrics: active users, admins, groups, explicit overrides;
- risk list: disabled accounts with access, direct overrides, users without group, last admin change;
- primary `Добавить пользователя`;
- links к Users/Groups/Permissions как compact tabs/rows;
- «Как работает» перенести в docs drawer.

**Приоритет:** P1.

## 10.24. Users

**Файлы:** `SettingsUsersPage.tsx`, `settings-users/*`.

**Критические проблемы:**

- delete через `confirm`;
- reset password через `prompt`;
- success через `alert`;
- create form всегда занимает right sidebar 380 px;
- list + inline editing + create sidebar перегружают экран;
- password flow не показывает policy и copy behavior.

**Новый вариант:**

- user table: status, username, email, profile, groups, last login, actions;
- search/status/profile/group filters;
- `Добавить пользователя` открывает right sheet;
- click row открывает detail/edit drawer;
- reset password dialog: generate/manual, policy checklist, show/copy, force reset on next login;
- delete/deactivate distinction; по умолчанию `Деактивировать`, permanent delete только danger zone;
- audit info в detail.

**Приоритет:** P0.

## 10.25. Groups

**Файл:** `SettingsGroupsPage.tsx`.

**Проблемы:**

- group cards с inline full editing;
- create form постоянно справа;
- member picker - длинный набор chips без search;
- permission modes используют native selects;
- browser confirm;
- colored avatars/stats добавляют декоративный шум.

**Новый вариант:**

- group list/table;
- detail drawer: Members, Inherited permissions, Overrides, Audit;
- searchable member combobox;
- permissions показывать как matrix/summary, редактировать в отдельном mode;
- create drawer;
- remove group dialog показывает, что произойдёт с участниками и inherited access.

**Приоритет:** P1.

## 10.26. Permissions

**Файл:** `SettingsPermissionsPage.tsx`.

**Проблемы:**

- две параллельные формы user override и group override;
- пользователь не видит effective permission, только отдельные rules;
- duplicate/conflicting overrides возможны визуально;
- toggle/delete icon actions плохо объясняют последствия;
- browser confirm;
- native selects.

**Новый вариант:**

- сначала effective access matrix: субъект x feature;
- filter by user/group/feature;
- selected cell объясняет source: profile -> group -> explicit override;
- CTA `Добавить исключение` открывает drawer;
- conflict warning до сохранения;
- revoke dialog показывает effective result после удаления rule;
- audit trail для каждой override.

**Приоритет:** P0/P1.

## 10.27. SSO

**Файл:** `SettingsSSOPage.tsx`.

**Что хорошо:** dirty/reset state, clear sections, examples.

**Проблемы:**

- text 11 px для важных helper descriptions;
- native select;
- enable toggle не проверяет рабочую конфигурацию;
- нет test header / test login;
- proxy examples постоянно занимают место;
- mixed hardcoded Russian and i18n.

**Новый вариант:**

- status banner `SSO выключен / Готов / Ошибка конфигурации`;
- core form: enabled, header, auto-create, username normalization, default profile;
- button `Проверить заголовок` с mock/request inspector;
- перед Enable: validation checklist и confirmation о fallback local admin;
- examples в collapsible `Примеры reverse proxy`;
- Save bar с dirty state.

**Приоритет:** P1.

## 10.28. AI memory

**Файлы:** `SettingsMemoryPage.tsx`, `SettingsMemoryPanel.tsx`, memory sections.

**Проблемы:**

- термины «долговременная память», «автозаметки», «операционная память», «консолидация» и backend `dreams` не образуют понятной модели;
- buttons высотой 28 px;
- одна большая nested SectionCard;
- status daemon отображается badges, но нет clear freshness/last run;
- действия Promote/Archive требуют impact explanation.

**Новый вариант:**

- название «Память AI по серверу»;
- server selector + state: last collection, last consolidation, items, warnings;
- sections: Policy, Collected facts, Patterns, Promoted notes/skills;
- primary action «Обновить память», secondary «Запустить консолидацию»;
- 40 px controls;
- confirmation для promotion with target preview;
- archive supports undo;
- user-facing copy не содержит `dreams`.

**Приоритет:** P2.

## 10.29. Audit and logging

**Файл:** `SettingsAuditPage.tsx`, audit components.

**Что хорошо:** отдельные tabs, search, date range, logging config.

**Проблемы:**

- header снова маленький;
- tabs чрезмерно оформлены отдельной blur-card;
- raw action/category names могут быть техническими;
- save success state локален и кратковременен;
- нет export/pagination/detail drawer в основном flow;
- logging settings и audit events требуют разных mental models.

**Новый вариант:**

- tabs simple underline/segmented;
- Logging: retention, destinations, levels, privacy, Save bar;
- Activity: search, actor, category, action, date, result filters;
- table: time, actor, action, object, result, IP;
- row detail: before/after, correlation ID, metadata;
- export CSV/JSON с permission check;
- user-facing labels mapping, raw code только в details.

**Приоритет:** P1.

## 10.30. 404

**Файл:** `NotFound.tsx`.

**Текущий экран приемлем**, но 9rem 404 больше декоративен, чем полезен.

Улучшить:

- compact title;
- показать requested path;
- различать 404 и permission-denied;
- actions Back / Overview;
- при feature gate не redirect silent, а показать «Нет доступа к разделу».

**Приоритет:** P2.

## 11. Отдельный аудит окон и модалок

| Окно | Решение |
|---|---|
| Server form | переписать в 640 px sheet, 3 секции + connection test |
| Create agent | full-screen wizard, fixed header/footer, autosave, readiness, test run |
| Agent report | quick preview modal + full report route |
| Agent profile | edit sheet с tabs, risk summary |
| MCP form | sheet, live preview, test connection, secrets summary |
| Skill creation | 2-step wizard; file editor отдельно от create dialog |
| Skill validation | dialog только для summary; detailed report как panel |
| Pipeline run | preflight dialog: entry point, context, risks, validate/run |
| Node settings | right inspector, не modal |
| File editor close/delete | UnsavedChanges/DeleteDialog вместо browser confirm |
| User reset password | специальный security dialog вместо prompt/alert |
| Delete user/group/rule | contextual confirm with consequences and object name |

## 12. Технический план refactor

### 12.1. Новый design layer

Создать:

```text
frontend/src/design/
  tokens.css
  status.ts
  copy.ts
  motion.ts

frontend/src/components/system/
  PageHeader.tsx
  PageToolbar.tsx
  ContentPanel.tsx
  ContentSection.tsx
  EntityList.tsx
  DataTable.tsx
  StatusBadge.tsx
  RiskBadge.tsx
  InlineAlert.tsx
  AsyncButton.tsx
  SaveState.tsx
  ConfirmDialog.tsx
  DeleteDialog.tsx
  UnsavedChangesDialog.tsx
  ErrorDetails.tsx
```

### 12.2. Удалить/объединить дубли

- `enterprise-panel`, `workspace-panel`, `corp-card` -> один/два surface primitives;
- несколько status components -> один domain-aware `StatusBadge`;
- Radix Toaster и Sonner -> один notification adapter;
- old `SettingsPage.tsx`, если он точно не маршрутизируется и не импортируется;
- page-local SELECT_CLASS -> shared Select/Combobox;
- scattered `localize` + hardcoded strings -> typed dictionaries.

### 12.3. Forms

Для Server, Agent, MCP, AgentProfile, SSO и Users:

- schema in `feature/schema.ts`;
- server error mapper;
- `FormSection` / `FormField`;
- dirty guard;
- async validation status;
- deterministic footer actions.

### 12.4. Сложное состояние

- Agent wizard: reducer/state machine + RHF;
- Terminal workspace: reducer for tabs/panels/connection state;
- Studio Drafts: URL state + inspector tab state;
- avoid page components with десятками independent `useState`.

### 12.5. Domain status maps

Создать централизованные maps:

```ts
agentRunStatusPresentation(status, lang)
serverHealthPresentation(status, stale, lang)
pipelineRunStatusPresentation(status, lang)
validationPresentation(result, lang)
```

Это уберёт raw `completed`, `failed`, `running` из UI и цветовые расхождения.

### 12.6. Error handling

- global route ErrorBoundary;
- API error normalization: code, title, message, details, correlationId, retryable;
- inline errors for forms;
- page error state for failed query;
- toast only for background/action feedback;
- no raw `error.message` as final user copy without mapping.

## 13. Accessibility

Минимальные правила Definition of Done:

- interactive target >= 40 x 40 px, кроме compact desktop data table >= 36 px;
- body text >= 14 px, metadata >= 12 px;
- visible focus 2 px с offset 2 px;
- status не зависит только от цвета;
- icon-only button имеет accessible name и tooltip;
- secret reveal доступен с keyboard;
- dialog focus trap, initial focus и return focus проверены;
- table headers semantic;
- tabs управляются стрелками;
- graph editor имеет keyboard alternatives для add/select/delete node;
- terminal utility panels доступны без мыши;
- no `tabIndex={-1}` на единственном доступном control;
- screen reader announcements для connection/run status;
- reduced motion respected;
- contrast проверяется автоматически axe + visual token tests.

## 14. Responsive strategy

### Desktop >= 1280

- global sidebar 220-240 px;
- content max 1440;
- optional contextual rail 320-380;
- no double 300 px sidebars.

### Tablet 768-1279

- global sidebar icon rail или drawer;
- contextual nav horizontal/dropdown;
- right rails move to collapsible bottom section;
- tables hide secondary columns, not scale text down.

### Mobile < 768

- full-screen dialogs/sheets;
- bottom/sticky primary action where appropriate;
- entity rows become cards with 2-3 key facts;
- filters open sheet;
- terminal uses full-screen panels and swipe/explicit tabs;
- no horizontal five-step cards; stepper shows current + progress.

## 15. Visual and interaction testing

Расширить Playwright visual suite:

### Viewports

- 1440 x 1000 desktop;
- 1024 x 900 tablet;
- 390 x 844 mobile.

### Обязательные snapshots

- Login local / SSO / error;
- Dashboard user/admin with critical state;
- Servers list empty/populated/filter;
- Server create sheet + validation + test result;
- Terminal connected/disconnected/mobile;
- Agents list;
- Agent wizard каждый шаг + review error;
- Agent run running/failed/completed;
- Studio home/drafts/editor/runs;
- Agent profiles, Skills, MCP, Notifications;
- Settings Users/Groups/Permissions/SSO/Audit;
- MARS wizard/run;
- all confirmation dialogs.

### Interaction tests

- keyboard navigation;
- focus return after dialog;
- dirty guard;
- error mapping;
- retry action;
- schedule builder;
- server test connection;
- agent test run;
- responsive pane switching;
- destructive confirmation.

## 16. План внедрения

### Этап 0. Зафиксировать UX-контракт - P0

- утвердить naming и navigation;
- утвердить tokens, typography, controls;
- создать inventory страниц/состояний;
- заморозить добавление новых page-local visual patterns.

**Результат:** одна спецификация и дизайн-system route.

### Этап 1. Базовая система - P0

- tokens/surfaces/type;
- Button/Input/Select/Status/Alert;
- one toast system;
- Confirm/Delete/Unsaved dialogs;
- PageHeader/Toolbar/ContentPanel;
- remove 9-11 px from primary UI.

**Результат:** новые страницы собираются без уникального CSS.

### Этап 2. Критические операционные flows - P0

1. Servers + Server form.
2. Agent wizard.
3. Agent run/report.
4. Terminal header/panels.
5. Users/password/delete security flows.

**Результат:** основные рабочие сценарии становятся последовательными и безопасными.

### Этап 3. Studio - P1

- Studio IA/Nav;
- landing;
- drafts workspace;
- pipeline toolbar/inspector;
- runs;
- profiles/skills/MCP.

### Этап 4. Settings и secondary modules - P1/P2

- Settings shell;
- AI/Access/SSO/Audit/Memory;
- Notifications;
- MARS restyle;
- Kubernetes hide/onboarding.

### Этап 5. Hardening

- visual suite;
- axe;
- copy lint;
- status mapping tests;
- performance budgets;
- remove legacy CSS/code.

## 17. Рабочий backlog

| ID | Priority | Задача | Size |
|---|---|---|---|
| DS-001 | P0 | Ввести новые semantic surface/text/status tokens | M |
| DS-002 | P0 | Поднять typography minimum и удалить text 9-11 из primary UI | L |
| DS-003 | P0 | Объединить panel/card CSS primitives | M |
| DS-004 | P0 | Переписать Button variants и размеры | S |
| DS-005 | P0 | Единый StatusBadge + domain mappings | M |
| DS-006 | P0 | Оставить один toast adapter | S |
| DS-007 | P0 | Confirm/Delete/Unsaved dialogs | M |
| DS-008 | P0 | Shared Select/Combobox, убрать native mix | L |
| DS-009 | P0 | PageHeader/Toolbar/ContentPanel primitives | M |
| DS-010 | P1 | Skeleton/Empty/Error patterns | M |
| IA-001 | P0 | Утвердить Main nav и Studio subnav | M |
| IA-002 | P0 | Развести «Агенты» и «Профили выполнения» | S |
| IA-003 | P1 | Permission denied вместо silent redirect | S |
| COPY-001 | P0 | Удалить mixed RU/EN из active routes | L |
| COPY-002 | P1 | Typed status/copy dictionaries | M |
| SRV-001 | P0 | Новая server list toolbar/table | L |
| SRV-002 | P0 | Server form sheet + schema | L |
| SRV-003 | P0 | Test connection flow | M |
| TERM-001 | P0 | Двухуровневый TerminalHeader | L |
| TERM-002 | P0 | Utility right panel для Files/AI/Settings | L |
| TERM-003 | P0 | Custom close/delete confirms | M |
| AG-001 | P1 | Новый agent list и filters | L |
| AG-002 | P0 | Переписать Agent wizard state/schema | XL |
| AG-003 | P0 | Новый stepper/right preview/readiness | L |
| AG-004 | P0 | Command validation + risk checks | L |
| AG-005 | P0 | Test run before create | L |
| RUN-001 | P0 | Новый AgentRun overview/tabs | XL |
| RUN-002 | P0 | Report quick preview + full route | L |
| ST-001 | P1 | Упростить Studio landing/nav | L |
| ST-002 | P1 | Drafts inspector tabs и phase progress | L |
| ST-003 | P1 | Pipeline toolbar dirty/validate/run hierarchy | M |
| ST-004 | P1 | Pipeline run filters/mobile detail | L |
| ST-005 | P1 | Rename/redesign execution profiles | L |
| SK-001 | P1 | Разделить Skills catalog и editor routes | L |
| SK-002 | P0 | Dirty guard и custom file delete | M |
| MCP-001 | P1 | Connection health list + detail sheet | L |
| NOTIF-001 | P1 | Channel cards + dirty save bar | L |
| SET-001 | P0 | Переписать SettingsLayout без второй тяжёлой sidebar | L |
| USR-001 | P0 | User table + create/edit drawer | XL |
| USR-002 | P0 | Secure reset password dialog | M |
| GRP-001 | P1 | Group list/detail drawer | L |
| PERM-001 | P0 | Effective permission matrix | XL |
| SSO-001 | P1 | SSO validation/test/enable confirmation | L |
| MEM-001 | P2 | Понятная IA и copy памяти | L |
| AUD-001 | P1 | Audit table/detail/export | L |
| MARS-001 | P2 | Restyle в общий design system | XL |
| K8S-001 | P0 | Скрыть placeholder до готовности или onboarding | S |
| TEST-001 | P0 | Visual suite для core pages и 3 viewports | XL |
| TEST-002 | P0 | Axe/keyboard tests для dialogs/forms/navigation | L |
| CLEAN-001 | P1 | Удалить legacy SettingsPage и мёртвые primitives после проверки imports | M |

## 18. Definition of Done для каждой переработанной страницы

Страница считается готовой только если:

- есть loading, empty, error и permission states;
- один понятный primary action;
- все labels локализованы;
- нет основного текста меньше 12 px;
- controls >= 40 px или обоснованный compact 36 px;
- status имеет текст и icon;
- нет raw browser dialogs;
- нет raw backend errors;
- keyboard flow проверен;
- mobile 390 px проверен;
- tablet 1024 px проверен;
- desktop visual snapshot добавлен;
- опасное действие имеет contextual confirmation;
- dirty form защищена;
- analytics/audit event определён для критического действия.

## 19. Рекомендуемый первый pull request

Не начинать с Dashboard и не пытаться одновременно перекрасить все страницы. Первый PR должен создать foundation без большого product rewrite:

1. Новые tokens и typography.
2. Новый Button, StatusBadge, InlineAlert.
3. Единый Sonner adapter.
4. Confirm/Delete/Unsaved dialogs.
5. PageHeader/Toolbar/ContentPanel.
6. Миграция одной vertical slice - Servers list + Server form.
7. Visual tests desktop/tablet/mobile для этой slice.

После этого второй PR - Agent wizard, третий - Agent run/report, четвёртый - TerminalHeader. Такой порядок быстро создаст видимый результат и одновременно проверит design system на четырёх очень разных типах интерфейса.

## 20. Финальная оценка направления

У проекта нет проблемы «плохой темы» или «нужно подобрать другой оттенок teal». Проблема системная: интерфейс слишком часто оформляет каждую функцию как самостоятельную карточку и каждую страницу как новый продукт. Исправление должно начаться с hierarchy, терминологии, статусов, формы обратной связи и основных journeys. После этого текущая тёмная основа и teal-brand могут остаться - но станут спокойнее, профессиональнее и намного понятнее.

---

## Приложение A. Основные файлы, на которых основан аудит

- `frontend/src/App.tsx`
- `frontend/src/index.css`
- `frontend/DESIGN.md`
- `frontend/src/components/AppLayout.tsx`
- `frontend/src/components/AppSidebar.tsx`
- `frontend/src/components/StudioNav.tsx`
- `frontend/src/components/settings/SettingsLayout.tsx`
- `frontend/src/components/ui/page-shell.tsx`
- `frontend/src/components/ui/button.tsx`
- `frontend/src/components/ui/dialog.tsx`
- `frontend/src/components/ui/toaster.tsx`
- `frontend/src/components/ui/sonner.tsx`
- `frontend/src/pages/Login.tsx`
- `frontend/src/pages/UserDashboard.tsx`
- `frontend/src/pages/AdminDashboard.tsx`
- `frontend/src/pages/Servers.tsx`
- `frontend/src/pages/servers/ServersListTab.tsx`
- `frontend/src/pages/servers/ServerFormDialog.tsx`
- `frontend/src/pages/TerminalPage.tsx`
- `frontend/src/pages/terminal-page/TerminalHeader.tsx`
- `frontend/src/pages/AgentsPage.tsx`
- `frontend/src/pages/agents-page/CreateAgentDialog.tsx`
- `frontend/src/pages/agents-page/AgentWizardProgress.tsx`
- `frontend/src/pages/agents-page/AgentWizardStepContent.tsx`
- `frontend/src/pages/AgentRunPage.tsx`
- `frontend/src/components/studio/AgentReportModal.tsx`
- `frontend/src/pages/StudioPage.tsx`
- `frontend/src/pages/StudioDraftsPage.tsx`
- `frontend/src/pages/PipelineEditorPage.tsx`
- `frontend/src/pages/pipeline-editor/PipelineEditorToolbar.tsx`
- `frontend/src/pages/PipelineRunsPage.tsx`
- `frontend/src/pages/AgentConfigPage.tsx`
- `frontend/src/pages/StudioSkillsPage.tsx`
- `frontend/src/pages/MCPHubPage.tsx`
- `frontend/src/pages/NotificationsSettingsPage.tsx`
- `frontend/src/pages/KubernetesPage.tsx`
- `frontend/src/pages/MarsPage.tsx`
- `frontend/src/pages/MarsRunPage.tsx`
- `frontend/src/pages/settings/*`
- `frontend/src/pages/SettingsUsersPage.tsx`
- `frontend/src/pages/SettingsGroupsPage.tsx`
- `frontend/src/pages/SettingsPermissionsPage.tsx`
- `frontend/e2e/visual.spec.ts`
