# Kubernetes Frontend Parallel UI Plan

Last updated: 2026-07-02

Этот документ - рабочий план для отдельной frontend/UI-сессии. Цель: переделать Kubernetes-раздел в WebTerm-native интерфейс уровня Freelens, но не сломать уже готовый backend, API-контракты, права, audit и release gate.

Главное правило: frontend-сессия может активно менять UI, но не должна менять backend-поведение. Если UI не хватает данных, это оформляется как отдельный backend contract request.

Этот файл можно отдавать второй Codex/UI-сессии как стартовое ТЗ. Backend-сессия в это время может продолжать закрывать release evidence и production gates, а UI-сессия должна работать в режиме frontend-only.

## Текущая стадия

Backend уже достаточно готов, чтобы параллельно начинать UI/UX:

- `/kubernetes` читает нормализованный inventory и action-request данные.
- Admin Mode уже имеет typed clients для sessions, discovery, resource catalog, resource list/YAML/detail, logs, watch preview, actions и node maintenance.
- `/settings/kubernetes` уже отвечает за provider setup, sync worker state и release gates.
- Есть demo fallback для разработки UI без живых Rancher/Devtron/Fleet.
- Production/sidebar включение всё ещё заблокировано release scope/evidence, поэтому UI не должен показывать обычному пользователю, что модуль уже полностью production-ready.

Цель не в том, чтобы открывать Rancher/Devtron/Fleet отдельно или в iframe. Цель - работать с Kubernetes только через WebTerm, а Rancher/Devtron/Fleet использовать как backend-провайдеры данных и безопасных операций.

## Жёсткие правила, чтобы не сломать backend

Frontend-сессия не трогает эти зоны без отдельной backend-задачи:

- `kubernetes_ops/**`
- Django URL/view/serializer/model/migration файлы Kubernetes.
- readiness, provider sync, release evidence, permissions, audit services.
- API endpoint paths, query params, response field names, permission semantics.
- production flags вроде `KUBERNETES_OPS_READY_FOR_SIDEBAR`.
- secret handling, token refs, provider credential storage, external link sanitization.

Если frontend не хватает поля:

1. Сначала пробуем посчитать значение из уже существующих response fields.
2. Если это только для макета, используем demo fallback с тем же shape, что у реального API.
3. Если нужен новый backend field, пишем backend contract request.
4. Не завязываем production UI на поле, которого backend ещё не отдаёт.

Нельзя добавлять "как будто реальные" данные на production-экраны. Demo данные должны оставаться только в demo fallback layer.

## Источники правды по контрактам

Frontend должен считать эти файлы текущим API-контрактом:

| Зона | Файлы |
| --- | --- |
| Normal Kubernetes overview | `frontend/src/api/kubernetes.ts` |
| Action request lifecycle | `frontend/src/api/kubernetes-actions.ts` |
| Admin sessions/resources/logs/watch | `frontend/src/api/kubernetes-admin.ts` |
| Admin discovery/resource picker | `frontend/src/api/kubernetes-admin-discovery.ts` |
| Admin write previews/actions | `frontend/src/api/kubernetes-admin-actions.ts` |
| Node summary and maintenance | `frontend/src/api/kubernetes-admin-nodes.ts`, `frontend/src/api/kubernetes-admin-node-maintenance.ts` |
| Demo/offline разработка | `frontend/src/lib/api-demo-kubernetes.ts`, `frontend/src/lib/api-demo-kubernetes-discovery.ts` |
| Release truth | `artifacts/kubernetes_ops_release_evidence.json`, `artifacts/kubernetes_ops_release_handoff.json` |
| Product/backend roadmap | `docs/WebTerm_Kubernetes_Ops_Rancher_Fleet_Devtron_Report.md`, `docs/architecture/KUBERNETES_LOW_LEVEL_ADMIN_MODE_PLAN.md` |

Frontend может добавлять локальные UI adapters/view models, но API clients должны оставаться тонкими wrapper'ами над backend responses.

## Разделение работы для двух сессий

Так можно безопасно работать параллельно:

| Сессия | Что делает | Что не трогает |
| --- | --- | --- |
| Frontend/UI | `frontend/src/pages/Kubernetes*.tsx`, `frontend/src/pages/kubernetes-page/**`, `frontend/src/pages/settings/SettingsKubernetesPage.tsx`, Kubernetes frontend tests, frontend-only adapters, CSS/component composition | Backend files, API path changes, DB/schema changes, permission behavior |
| Backend | `kubernetes_ops/**`, backend tests, release evidence scripts, production artifacts, backend docs | Большие UI rewrite, визуальные решения, route layout |

Правило конфликтов:

- две сессии не редактируют один и тот же файл одновременно;
- изменения в shared API types должны быть маленькими и additive;
- если API type file начинает конфликтовать, frontend создаёт adapter в `frontend/src/pages/kubernetes-page/`, а не переписывает API contract;
- backend-сессия отдельно сообщает, какие новые поля теперь можно использовать UI.

## Протокол параллельной работы

Перед стартом frontend-сессия делает:

```powershell
git status --short
rg --files frontend/src/pages/kubernetes-page frontend/src/pages | rg "Kubernetes|kubernetes"
```

Затем фиксирует в своём handoff:

- какие frontend-файлы она собирается трогать;
- какие routes меняет;
- какие API clients только читает;
- какие backend contract requests может понадобиться создать.

Во время работы:

- не редактировать `kubernetes_ops/**`;
- не редактировать Django migrations, serializers, urls, permissions, release evidence services;
- не менять endpoint paths, query params, response field names;
- не менять production env flags ради UI;
- не править generated/release artifacts вручную;
- не делать backend mock прямо в production UI path;
- не добавлять реальные provider URLs/tokens/kubeconfig в frontend fixtures.

Если frontend-сессия упирается в недостающее поле, она не "чинит" backend сама. Она:

1. Проверяет, можно ли вывести это из уже существующих полей.
2. Если нельзя, добавляет frontend fallback только для demo/offline режима.
3. Пишет `Backend Contract Request` в этот документ или в handoff.
4. Продолжает UI с graceful empty/unknown state.

Backend-сессия, когда добавляет новый контракт:

- меняет backend tests и release evidence;
- сообщает точный endpoint/field;
- указывает, нужно ли обновить demo fallback;
- не переписывает визуальную структуру UI.

## Backend-Safe Frontend Contract

Frontend должен быть thin consumer, а не второй источник Kubernetes-логики.

Правильная схема:

```text
backend response -> frontend API client -> frontend view model adapter -> components
```

Неправильная схема:

```text
raw provider body -> component parses arbitrary Kubernetes JSON -> component decides permissions
```

Правила:

- API clients в `frontend/src/api/**` не должны содержать бизнес-решения по permissions.
- UI adapters можно добавлять в `frontend/src/pages/kubernetes-page/**`.
- Все dangerous states берутся из backend policy fields: `access_policy`, `execution_policy`, `blocked_reason`, `native_execution_enabled`, `safe_read_actions`, `has_mutating_verbs`.
- UI не должен сам решать, что action безопасен, если backend не отдал это явно.
- Все unknown/partial/missing поля должны рендериться как понятный fallback, а не падать.
- Любой новый backend field должен быть optional на первом frontend шаге, чтобы параллельная ветка не ломала старый backend.

## File Ownership Map

Frontend-сессия может свободно работать здесь:

| Зона | Разрешено |
| --- | --- |
| `frontend/src/pages/KubernetesPage.tsx` | normal cockpit layout, cards, copy, route composition |
| `frontend/src/pages/KubernetesAdminPage.tsx` | admin workspace layout, explorer composition |
| `frontend/src/pages/KubernetesClusterDetailPage.tsx` | cluster detail UI |
| `frontend/src/pages/KubernetesDevtronPage.tsx` | WebTerm-native Devtron app UI |
| `frontend/src/pages/KubernetesFleetPage.tsx` | Fleet rollout UI |
| `frontend/src/pages/settings/SettingsKubernetesPage.tsx` | admin settings/release presentation |
| `frontend/src/pages/kubernetes-page/**` | components, view models, filters, drawers, tables |
| `frontend/src/lib/api-demo-kubernetes*.ts` | demo fallback shape, only if it mirrors real API |
| `frontend/src/pages/*Kubernetes*.test.tsx` | focused frontend regression tests |

Frontend-сессия трогает только по согласованию:

| Зона | Почему осторожно |
| --- | --- |
| `frontend/src/api/kubernetes*.ts` | это API contract layer; изменения должны быть additive |
| `frontend/src/App.tsx` | route/nav changes can affect access gates |
| `frontend/src/components/AppSidebar.tsx` | sidebar depends on release/readiness gates |
| shared design primitives | можно случайно сломать другие разделы WebTerm |

Frontend-сессия не трогает:

| Зона | Причина |
| --- | --- |
| `kubernetes_ops/**` | backend/session/audit/permission source of truth |
| `artifacts/kubernetes_ops_release_*.json` | evidence создаётся backend commands |
| `docs/architecture/KUBERNETES_LOW_LEVEL_ADMIN_MODE_PLAN.md` | backend canonical plan |
| DB migrations/settings/env defaults | backend release responsibility |

## UI State Matrix

Каждый экран Kubernetes должен иметь эти состояния:

| State | Как показывать |
| --- | --- |
| Loading | skeleton/table placeholder без прыжков layout |
| Empty | "нет ресурсов/приложений" и safe next step |
| Healthy | плотный readable inventory без debug noise |
| Degraded | причина, affected namespace/app/resource, safe action |
| Stale | простое "данные устарели", ссылка на settings только для admin |
| Partial | какие части недоступны, но остальное работает |
| Permission denied | объяснить, что нужен доступ, без раскрытия backend internals |
| Release blocked | только в settings/admin context, не на обычном `/kubernetes` |
| Provider error | кратко, без token/URL/provider stack trace |

Это важно для параллельной работы: backend может быть не полностью готов в production evidence, но UI всё равно должен корректно жить на partial/stale/blocked responses.

## Какие страницы за что отвечают

### `/kubernetes`

Обычный operator cockpit.

Показываем:

- health и counts по кластерам;
- активные warnings/degraded workloads/apps;
- Fleet rollout summary;
- Devtron app summary;
- freshness/provider sync warning простыми словами;
- переходы в WebTerm detail pages;
- создание safe action requests.

Не показываем:

- provider setup forms;
- tokens, secret refs, provider URLs;
- raw readiness internals;
- release gate/debug text;
- внешние Rancher/Fleet/Devtron links для обычного пользователя;
- прямые destructive buttons.

### `/kubernetes/admin`

Freelens-like workspace для staff/admin.

Показываем:

- cluster selector;
- active admin session status;
- resource catalog, сгруппированный по `ui_group`;
- namespace/resource filters;
- resource table/list;
- YAML/detail/events side panel;
- bounded logs snapshot;
- bounded watch preview;
- ownership/change-path hints;
- action history/report.

Правила:

- read-only по умолчанию;
- write controls только как preview/request/approval flow, если backend policy не разрешает approved session;
- break-glass UI всегда показывает TTL, reason, scope и audit state.

### `/kubernetes/clusters/:clusterId`

Cluster detail.

Показываем:

- namespaces, workloads, pods, services/ingresses, recent events;
- ownership и app links внутри WebTerm;
- health/freshness;
- вход в Admin Mode, если у пользователя есть право.

### `/kubernetes/devtron`

Devtron applications, но WebTerm-native.

Показываем:

- app health, namespace, team, version, environment;
- diagnosis flow в Studio draft;
- rollback/request buttons только через action request lifecycle;
- без требования отдельно логиниться в Devtron для обычной работы.

### `/kubernetes/fleet`

Fleet rollout view.

Показываем:

- bundle/source/target/status;
- ready/desired progress;
- paused/rolling/degraded states;
- request entry points для pause/resume или GitOps MR flow.

### `/settings/kubernetes`

Admin-only configuration и release readiness.

Показываем:

- providers;
- sync worker;
- readiness checks;
- `production_execution_plan`;
- release evidence status.

Эта страница может быть технической. Обычная `/kubernetes` должна оставаться понятной.

## Рекомендуемая frontend-структура

Текущие route files:

```text
frontend/src/pages/
  KubernetesPage.tsx                  обычный operator cockpit
  KubernetesAdminPage.tsx             admin resource workspace
  KubernetesClusterDetailPage.tsx     cluster detail
  KubernetesDevtronPage.tsx           app view
  KubernetesFleetPage.tsx             rollout view
  settings/SettingsKubernetesPage.tsx admin settings/release

frontend/src/pages/kubernetes-page/
  rows, panels, filters, drawers, action panels, frontend-only adapters
```

Если нужны новые файлы, лучше добавлять так:

```text
frontend/src/pages/kubernetes-page/kubernetesUiModel.ts
frontend/src/pages/kubernetes-page/kubernetesResourceGroups.ts
frontend/src/pages/kubernetes-page/KubernetesResourceExplorer.tsx
frontend/src/pages/kubernetes-page/KubernetesResourceDetailDrawer.tsx
frontend/src/pages/kubernetes-page/KubernetesReleaseGatePanel.tsx
```

Каждый новый файл держим узким по смыслу и меньше project size guard.

## Правила работы с данными

- Использовать реальные TypeScript types из `frontend/src/api/**`.
- Для resource picker использовать `resource_catalog`, а не raw Kubernetes discovery parsing.
- Для list/YAML/detail/watch брать query из `resource_catalog.items[].query`.
- Для кнопок чтения смотреть `safe_read_actions`.
- Для опасных действий смотреть `has_mutating_verbs`, `access_policy`, `execution_policy`.
- Для action UI учитывать `native_execution_enabled`, `blocked_reason`, approval/report lifecycle.
- `links` использовать только после backend sanitization и role filtering.
- Не хранить raw manifests, logs или provider payloads в localStorage.
- Не класть secrets, tokens, kubeconfig content, credentialed URLs в UI state, tests, snapshots.

## План работ по фазам

Работать лучше не "сразу рисуем всё красиво", а слоями. Сначала разложить данные и экраны так, чтобы пользователь понимал Kubernetes-раздел, потом уже доводить визуальный стиль.

### Phase 1: Contract Freeze And UI Shell

- Зафиксировать текущие routes/API clients как базу.
- Держать backend files нетронутыми.
- Если UI нужен удобный shape, добавить frontend-only adapter.
- Проверить, что demo fallback совпадает с real API shape.
- Разделить обычный cockpit, Admin Mode и Settings по смыслу, даже если визуальный стиль ещё сырой.

Acceptance:

```powershell
cd frontend
npm test -- --run src/pages/KubernetesPage.test.tsx src/pages/KubernetesAdminPage.test.tsx src/pages/KubernetesInventoryPages.test.tsx src/pages/settings/SettingsKubernetesPage.test.tsx
```

### Phase 2: Clean Normal Operator Cockpit

- Сделать `/kubernetes` понятным обычному пользователю.
- Оставить только clusters, health, warnings, apps, rollouts, safe next action.
- Убрать config/debug/release language в `/settings/kubernetes`.
- Писать stale state простыми словами: "данные устарели", а не provider internals.
- На первом экране показывать рабочую сводку, а не настройки подключения.
- Все deep links и fallback external links оставить staff/admin-only.

Acceptance:

- Пользователь понимает: что сломано, где, кто владелец, что можно безопасно сделать дальше.
- На `/kubernetes` нет provider setup.

### Phase 3: Freelens-Like Admin Resource Explorer

- Построить левый catalog из `resource_catalog.groups` и `resource_catalog.items`.
- Добавить namespace/resource/name filters.
- Добавить resource list/table с колонками: kind, namespace, name, status, age/freshness, owner/change path.
- Добавить right detail drawer для YAML/detail/events.
- Вызовы строить только через exact query fields: `api_version`, `kind`, `resource`, `namespace`, `name`, `session_id`.
- Не угадывать plural для CRD, если backend catalog уже дал `resource`.
- Держать filters/table/detail drawer как отдельные компоненты, чтобы не раздувать `KubernetesAdminPage.tsx`.

Acceptance:

- CRD работают через exact `resource` plural из catalog.
- UI не угадывает CRD endpoint names.
- Resource picker работает и на demo fallback, и на real API shape.

### Phase 4: Logs, Watch And Diagnostics Panels

- Добавить logs snapshot panel для pods.
- Добавить watch preview panel для выбранных resources.
- Добавить events/ownership panels в resource details.
- Визуально отделить bounded snapshot/preview от будущего unrestricted live streaming.

Acceptance:

- UI ясно показывает, где snapshot/preview, а где настоящий stream ещё недоступен.
- Raw provider body не выводится.

### Phase 5: Safe Action Request UX

- Добавить request-first flows для restart, scale, apply, patch, delete, pause/resume, rollback там, где backend contract уже есть.
- Перед опасной операцией показывать dry-run/schema validation/report.
- Показывать timeline: requested, approved externally, verified externally, rejected/blocked.
- Не показывать direct "execute now", если backend policy явно не разрешает это для active approved session.
- Для обычного пользователя dangerous action должен выглядеть как request/approval, не как админская кнопка.

Acceptance:

- У каждого risky action есть reason, target, preview, policy, audit/report state.
- Blocked action выглядит как намеренно заблокированный, а не как поломанная кнопка.

### Phase 6: Settings Release Gate

- Перевести settings page от raw readiness cards к понятным release steps.
- Использовать `production_execution_plan` и checklist wording вместо разбросанных command snippets.
- Provider setup и sync worker state остаются только здесь.

Acceptance:

- Admin видит, почему sidebar blocked и какой command/evidence step следующий.
- Обычные пользователи не видят release internals.

### Phase 7: Visual QA And Regression Tests

- Добавить/обновить frontend tests для normal user, admin user, degraded data, empty data, provider errors.
- Visual snapshots добавлять после стабилизации структуры.
- Перед handoff запускать build.
- На финальном UI pass проверить desktop и mobile ширины, чтобы таблицы/панели не ломали layout.
- Не делать крупный CSS/design-system refactor в том же PR, где меняется Kubernetes data flow.

Acceptance:

```powershell
cd frontend
npm run build
```

и focused Kubernetes frontend tests pass.

## Recommended UI Work Order

Если frontend-сессия стартует прямо сейчас, порядок такой:

1. Почистить `/kubernetes`: убрать provider setup/debug/release cards с обычного экрана, оставить понятный cockpit.
2. Вынести повторяемые Kubernetes UI primitives в `frontend/src/pages/kubernetes-page/**`.
3. Собрать `KubernetesAdminPage.tsx` как workspace: top toolbar, left resource catalog, center table, right detail drawer.
4. Подключить resource catalog/list/detail через уже существующие admin API clients.
5. Добавить states: empty, stale, provider error, permission denied, partial catalog.
6. Добавить logs/watch panels как bounded preview, без обещания unrestricted stream.
7. Добавить action request panels только поверх существующего backend policy/report lifecycle.
8. После этого делать visual polish: spacing, density, keyboard scanning, icons, responsive behavior.

Не начинать с полного редизайна `/settings/kubernetes`. Settings можно оставить технической страницей до тех пор, пока обычный `/kubernetes` и `/kubernetes/admin` не стали понятными.

## Verification Commands

Минимум для каждого frontend handoff:

```powershell
cd frontend
npm test -- --run src/pages/KubernetesPage.test.tsx src/pages/KubernetesAdminPage.test.tsx src/pages/KubernetesInventoryPages.test.tsx src/pages/settings/SettingsKubernetesPage.test.tsx
```

Перед большим UI handoff:

```powershell
cd frontend
npm run lint
npm run build
```

Если менялись API clients или demo fallback:

```powershell
cd frontend
npm test -- --run src/pages/KubernetesPage.test.tsx src/pages/KubernetesAdminPage.test.tsx src/pages/KubernetesInventoryPages.test.tsx src/pages/settings/SettingsKubernetesPage.test.tsx
```

Если менялись routes/sidebar/access visibility, дополнительно проверить вручную:

- обычный пользователь без Kubernetes access не видит модуль;
- обычный Kubernetes user видит WebTerm-native cockpit без provider setup;
- staff/admin видит settings/release/admin routes;
- release blocked state не превращается в "production ready" UI.

## Backend Contract Request Template

Когда frontend не хватает backend-контракта, использовать такой блок:

```markdown
### Backend Contract Request

- UI screen:
- Existing endpoint:
- Missing field or behavior:
- Why frontend cannot derive it:
- Proposed field shape:
- Permission/role impact:
- Demo fallback update needed:
- Frontend fallback until backend lands:
```

## Что нельзя делать

- Не возвращать provider setup на `/kubernetes`.
- Не делать Rancher/Devtron/Fleet primary user workflow.
- Не hardcode `localhost`, `host.docker.internal`, Rancher URLs или Devtron URLs в UI.
- Не показывать raw token refs, kubeconfigs или secret names обычным пользователям.
- Не переименовывать API response fields из frontend.
- Не менять backend permissions ради появления кнопки.
- Не считать demo fallback доказательством production-ready.
- Не делать вид, что Admin Mode может mutate cluster, если backend policy это блокирует.

## Handoff checklist для параллельных сессий

Frontend-сессия в конце пишет:

- какие файлы изменила;
- какие routes затронула;
- какие API fields использовала;
- какие tests запускала;
- какие backend contract requests появились;
- короткие UI notes/screenshots, если менялась визуальная логика.

Backend-сессия в конце пишет:

- какие endpoints/fields изменила;
- какие permission changes появились;
- что изменилось в release evidence;
- какие demo fallback updates нужны;
- какие tests запускала;
- можно ли frontend уже зависеть от изменения.

## Definition Of Done

Frontend-часть можно считать готовой, когда:

- обычная `/kubernetes` понятна без знания Kubernetes/Rancher internals;
- Admin Mode умеет browse resources как Freelens через backend `resource_catalog`;
- risky operations идут через request/preview/report, а не uncontrolled execution;
- settings владеют provider/release configuration;
- demo fallback повторяет real API shape;
- focused frontend tests и build проходят;
- frontend-only session не меняла backend files без отдельной backend contract task.
