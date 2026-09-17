# Kubernetes Cockpit v1 — технический план

> Статус: **UX v2 в коде** — крупный master-detail кокпит + connect guide + journey.  
> Источник UX: `k8s-cockpit-v2.html`, гайд `k8s-connection-guide.md` / `connectionGuide.ts`.  
> Точка входа: `src/pages/KubernetesCockpitPage.tsx` → `/kubernetes`.

---

## 1. Цель

Заменить текущий тяжёлый Kubernetes UI одним минимальным **кокпитом** на `/kubernetes`, в котором оператор может:

1. выбрать namespace;
2. увидеть поды и их статус;
3. открыть логи пода;
4. получить ИИ-объяснение логов (локальный mock до отдельного endpoint);
5. увидеть события / health overview;
6. видеть UI exec (заглушка без API).

Визуально: строго, светло, минималистично, плотный tool-layout — как в прототипе, в духе Neutral Modern и существующей продуктовой оболочки (sidebar/shell приложения).

---

## 2. Зафиксированные решения (бриф)

| Тема | Решение |
|------|---------|
| Порядок работ | Сначала детальный техплан (этот документ), **потом** код |
| Формат v1 | Один экран-кокпит, не мульти-страница |
| Судьба старого UI | Радикальная замена на главном маршруте; старый operator-кокпит не тащить |
| Инструменты v1 | namespaces, pods, logs, explain-logs, events, exec (UI-stub) |
| Глубина ИИ | Только «Объяснить логи» рядом с логом |
| Второстепенные маршруты | `/kubernetes/admin`, `/fleet`, `/devtron`, `/clusters/:id` — **оставить в роутере, убрать из навигации** |
| Exec | Только UI-заглушка (как в прототипе); API позже |
| Explain backend | Локальный mock на фронте до отдельного endpoint |

---

## 3. Non-goals (явно вне v1)

- Helm wizard, Fleet/Devtron виджеты, agent drawer, action-request / mutate UI на главном экране.
- Live log stream по WebSocket/SSE (в API уже `policy.streaming`, но UI v1 — snapshot + optional poll refresh).
- Реальный pod exec / break-glass API.
- Отдельный backend endpoint для explain (только mock; контракт описать заранее).
- Переписывание Settings → Kubernetes providers (остаётся staff-админкой).
- Удаление файлов admin/fleet/devtron/cluster detail — страницы живут, но скрыты из nav.

---

## 4. Целевой UX (v2)

Один workspace, **крупная типографика**, два фокуса (не пять мелких панелей):

```
┌─────────────────────────────────────────────────────────────┐
│ Header: Kubernetes / Кокпит (type-h1) + «Как подключить»    │
│ Cluster + Namespace (h-12) · pills Ready / Issues / Warnings│
├──────────────────────┬──────────────────────────────────────┤
│ Поды (крупные строки)│ Workbench выбранного пода            │
│ поиск                │ Tabs: Логи | События | Exec          │
│                      │ Логи + CTA «Объяснить»               │
│                      │ Explain inline под логом (mock)      │
└──────────────────────┴──────────────────────────────────────┘
Пустой inventory → ConnectionGuidePanel (данные из connectionGuide.ts)
```

### Поведение

- Смена namespace → сброс выбранного пода / логов / explain / exec target; перезагрузка pods + events.
- Клик по поду → выбор + загрузка логов (`tail` фиксированный, напр. 200).
- «Объяснить логи» → локальный mock-анализ по `lines[]` + метаданным пода; без сетевого вызова.
- Exec: поле + кнопка; при submit — UI-ответ «Exec API появится позже» (или disabled с причиной). Никаких `POST` на backend.
- Accent cobalt (`--accent`) — только на CTA «Объяснить логи» (бюджет акцента как в DS).

### URL state (must)

```
/kubernetes?cluster=<id>&ns=<name>&pod=<id>
```

- Deep-link и шаринг.
- При mount: гидрация из query; при отсутствии — первый ready cluster + первый ns (или empty-state).
- `replace: true` при синхронизации query, чтобы не засорять history на каждый клик пода (клик пода — `push` или `replace` — зафиксировать в реализации: **replace** для pod, **push** только для смены cluster).

---

## 5. Архитектура кода

### 5.1. Маршруты (`src/App.tsx`)

| Path | v1 поведение |
|------|----------------|
| `/kubernetes` | **Новый** `KubernetesCockpitPage` (единственная точка входа в nav) |
| `/kubernetes/admin` | Оставить route + `FeatureGate`; **не** линковать из sidebar / cockpit |
| `/kubernetes/fleet` | То же |
| `/kubernetes/devtron` | То же |
| `/kubernetes/clusters/:clusterId` | То же |
| `/settings/kubernetes` | Без изменений (провайдеры / readiness) |

Навигация: в `src/lib/navigation.ts` уже один пункт `path: "/kubernetes"`.  
Убрать **внутренние** ссылки на admin/fleet/devtron/cluster detail из нового кокпита (в старом `KubernetesCockpitBody` они есть — при замене страницы уйдут сами).

### 5.2. Новая структура файлов (предложение)

```
src/pages/
  KubernetesCockpitPage.tsx          ← тонкая страница: shell + layout + data wiring
  kubernetes-cockpit/
    CockpitHeader.tsx                ← cluster/ns selects, refresh, title
    CockpitStats.tsx                 ← ready / warn / events counts
    PodListPanel.tsx                 ← список подов + selection
    PodLogsPanel.tsx                 ← снимок логов + CTA explain
    ExplainLogsPanel.tsx             ← результат mock
    EventsPanel.tsx                  ← события, фильтр по ns
    ExecStubPanel.tsx                ← UI-заглушка
    useCockpitUrlState.ts            ← cluster/ns/pod ↔ searchParams
    useCockpitQueries.ts             ← react-query ключи и fetch
    explainLogsMock.ts               ← локальный explain
    types.ts                         ← узкие view-модели при необходимости
```

Старый каталог `src/pages/kubernetes-page/**` **не импортировать** в новый кокпит.  
Решение по удалению: поэтапно (см. §9) — сначала переключить route, потом удалить мёртвый код, чтобы не ломать скрытые страницы, которые ещё шарят примитивы.

### 5.3. Shared / keep

Скрытые страницы (`KubernetesAdminPage`, `Fleet`, `Devtron`, `ClusterDetail`) продолжают зависеть от:

- `kubernetes-page/KubernetesShell.tsx`
- `kubernetes-page/KubernetesCockpitPrimitives.tsx`
- `kubernetes-page/kubernetesPageSections.tsx`
- `kubernetes-page/kubernetesDeepLinks.tsx`
- `useKubernetesDeepLinkAudit.ts`

**Правило:** новый кокпит не зависит от этих модулей (чистый старт). Shared-хелперы (`localize`, `StatusBadge`, UI kit) — из `@/components/ui` и `@/lib/i18n`.

Settings Kubernetes (`SettingsKubernetesPage`) — не трогать в v1, кроме случая broken imports после cleanup.

---

## 6. API-контракт v1 (существующий backend)

Базовый префикс: `/api/kubernetes/`. Клиент уже есть в `src/api/kubernetes.ts`.

| UI need | Endpoint / client | Примечание |
|---------|-------------------|------------|
| Readiness / sidebar | `fetchKubernetesReadiness()` | Без изменений |
| Список кластеров | `fetchKubernetesClusters()` | Выбор cluster в header |
| Namespaces | `fetchKubernetesClusterNamespaces(clusterId)` | Select |
| Pods | `fetchKubernetesClusterPods(clusterId)` | **Фильтр по `namespace` на клиенте** (API cluster-scoped) |
| Events | `fetchKubernetesClusterEvents(clusterId)` | Фильтр по `namespace` на клиенте |
| Logs snapshot | `fetchKubernetesPodLogs(podId, tail)` | `lines[]`, `policy`, `available` |
| Explain | — | **Не вызывать** `createKubernetesDiagnosisDraft` (это Studio draft по `app_id`) |
| Exec | — | Нет вызова; stub only |

### 6.1. Gaps / осознанные компромиссы

1. **Нет server-side filter `?namespace=`** для pods/events — клиентский filter достаточен для v1 при умеренном размере ответа. Если payload огромный — follow-up: query param на backend.
2. **Stream logs** — `KubernetesPodLogsPolicy.streaming` часто `false`; UI показывает snapshot + кнопка «Обновить». Не эмулировать бесконечный stream.
3. **Diagnosis API** (`/actions/diagnose/`) завязан на `app_id` и Studio — **не подходит** для «объясни эти строки лога». Отдельный endpoint — post-v1.
4. **Exec API** отсутствует в operator surface (есть admin / break-glass / execute-approved) — вне scope.

### 6.2. React Query keys (канон)

```
["kubernetes", "clusters"]
["kubernetes", "namespaces", clusterId]
["kubernetes", "pods", clusterId]
["kubernetes", "events", clusterId]
["kubernetes", "pod-logs", podId, tail]
```

Invalidate на Refresh: namespaces + pods + events (+ logs если pod выбран).

---

## 7. Explain — локальный mock

Файл: `explainLogsMock.ts`.

### Вход

```ts
{
  podName: string;
  namespace: string;
  phase: string;
  restartCount: number;
  lines: string[];
}
```

### Выход (view-model)

```ts
{
  summary: string;           // 1–2 предложения
  likelyCause: string;       // гипотеза
  signals: string[];         // найденные паттерны из лога
  suggestedChecks: string[]; // 3–5 безопасных проверок (read-only)
  confidence: "low" | "medium" | "high";
  disclaimer: string;        // «локальный анализ, не production AI»
}
```

### Логика (детерминированная, без LLM)

- Сканировать `lines` на известные маркеры: `CrashLoopBackOff`, `OOMKilled`, `ImagePullBackOff`, `ErrImagePull`, `CreateContainerConfigError`, `probe failed`, `connection refused`, `permission denied`, exit codes.
- Учитывать `restartCount` / `phase`.
- Если маркеров нет — `confidence: "low"` + честный «недостаточно сигналов».
- Никаких выдуманных метрик «99.9%» / «10×».

### UI

- Кнопка disabled пока нет `lines.length` или идёт загрузка логов.
- Один accent CTA на экране.
- Результат в правой панели; повторный клик пересчитывает mock.

### Post-v1 контракт (зарезервировать, не реализовывать)

```
POST /api/kubernetes/pods/<pod_id>/explain-logs/
body: { tail?: number, lines?: string[] }
response: { summary, likely_cause, signals[], suggested_checks[], model, audit_id }
```

Когда endpoint появится — заменить тело `explainLogsMock` на `apiFetch`, UI не ломать.

---

## 8. Exec UI-stub

- Поля: команда (text), кнопка «Выполнить», output area.
- Target label: `ns/pod` или «под не выбран».
- Disabled, если нет выбранного пода.
- On submit: показать фиксированное сообщение (RU/EN через `localize`), например:  
  «Выполнение команд в контейнере будет доступно после подключения Exec API.»
- Не читать feature `kubernetes_break_glass` для «разрешить» в v1 (чтобы не создавать ложное ожидание). Опционально: мелкий hint «потребуется break-glass» — без unlock.

---

## 9. План работ по этапам (когда разрешите код)

### Этап A — каркас страницы (1 PR)

1. Добавить `KubernetesCockpitPage` + `kubernetes-cockpit/*` по макету прототипа (layout + empty/loading/error).
2. Переключить `App.tsx` route `/kubernetes` на новую страницу.
3. URL state `cluster` / `ns` / `pod`.
4. Подключить clusters → namespaces → pods/events (client filter).
5. i18n ключи RU/EN для новых строк (или `localize` inline, как в соседних страницах — следовать принятому паттерну файла).

**Критерий Done:** открывается `/kubernetes`, выбирается ns, виден список подов, события фильтруются.

### Этап B — логи + explain mock (1 PR)

1. Выбор пода → `fetchKubernetesPodLogs`.
2. Панель логов (mono, scroll, tail badge, refresh).
3. `explainLogsMock` + панель результата.
4. Empty / error / unavailable (`available: false`) состояния.

**Критерий Done:** сценарий CrashLoop из прототипа воспроизводится на демо/моках e2e.

### Этап C — exec stub + polish (можно вместе с B)

1. ExecStubPanel.
2. Stats strip.
3. A11y: focus rings, aria-labels на selects/buttons, keyboard select в списке подов.
4. Responsive: stack панелей &lt; ~1100px (как в прототипе).

### Этап D — вычистка старого главного UI

1. Удалить / перестать экспортировать код, который использовался **только** старым `KubernetesPage` (Helm на главной, AgentDrawer на главной, MetricsStrip overview-path и т.д.), **не ломая** admin/fleet/devtron/cluster/settings.
2. Обновить unit-тесты `KubernetesPage.test.tsx` → cockpit tests.
3. Обновить e2e visual snapshots для `/kubernetes` (`kubernetes-*-inventory.png`, empty state).
4. Обновить `e2e/support/platformFixtureKubernetes.ts`, если мокам не хватает pods/logs/events shape для нового UI.

### Этап E — скрытые маршруты (проверка)

1. Убедиться, что sidebar / primary nav не содержит admin/fleet/devtron.
2. Пройтись grep по `to="/kubernetes/admin"`, `fleet`, `devtron` в product UI (кроме самих скрытых страниц и settings).
3. Прямой URL скрытых страниц всё ещё работает при feature gate.

---

## 10. Что сносить vs что оставлять

### Снести с главного опыта (не показывать / не импортировать в cockpit)

- `KubernetesPage.tsx` текущая логика overview + agent + helm entry
- `KubernetesCockpitBody` виджеты Fleet/Devtron/Admin shortcuts, topology-heavy chrome
- `KubernetesAgentDrawer` на главной
- `KubernetesHelmWizard` как primary flow с `/kubernetes`
- `KubernetesActionRequestPanel` на главной
- `KubernetesMetricsStrip` sessions/admin metrics на главной (если только для old cockpit)

### Оставить (скрытые / settings)

- `KubernetesAdminPage` + `kubernetes-page/KubernetesAdmin*`
- `KubernetesFleetPage`, `KubernetesDevtronPage`, `KubernetesClusterDetailPage`
- `SettingsKubernetesPage` + provider admin
- API modules: `kubernetes.ts`, `kubernetes-admin*`, `kubernetes-ops-extra`, `kubernetes-actions` (admin/скрытые страницы)

### Переиспользовать идеи, не код

- Паттерны из `KubernetesPodsPanel` / `KubernetesPodLogsPanel` (статус, empty, audit message) — **переписать** в новом минимальном виде под прототип, не копировать карточный шум.

---

## 11. Права и безопасность

| Действие | Feature / policy |
|----------|------------------|
| Открыть `/kubernetes` | `kubernetes` + readiness sidebar (как сейчас) |
| Namespaces / pods / events / logs | Существующие backend permissions на read endpoints |
| Explain mock | Только клиент; не обходит audit логов (logs API уже пишет audit на snapshot) |
| Exec stub | Нет API → нет escalate |
| Скрытые admin routes | Те же `FeatureGate feature="kubernetes"`; deeper gates внутри admin pages без изменений в v1 |

Не ослаблять и не расширять permission model в v1.

---

## 12. Тесты

### Unit / component

- `useCockpitUrlState`: parse/sync query.
- `explainLogsMock`: маркеры CrashLoop / OOM / empty.
- Pod list filter by namespace.
- Exec stub не вызывает fetch (spy на `apiFetch` / MSW).

### E2E / visual

- Переписать сценарии `/kubernetes` empty / healthy / degraded под новый DOM.
- Smoke: выбрать ns → под → логи → explain (mock text visible).
- Проверить, что в sidebar нет пунктов admin/fleet/devtron.
- Прямой заход на `/kubernetes/admin` (staff/feature) — страница не 404 (регрессия keep_hidden).

### Demo mocks

- Расширить `platformFixtureKubernetes.ts`: pods с namespace, logs payload, events с `namespace`.

---

## 13. Критерии приёмки v1

1. Один nav-вход: Kubernetes → новый кокпит.
2. Можно работать: выбрать ns → увидеть поды → логи → explain (mock) → events.
3. Exec виден, но не ходит в сеть.
4. Нет Helm / Fleet / Devtron / Agent / Action-request на главном экране.
5. `/kubernetes/admin|fleet|devtron|clusters/:id` открываются по прямому URL, из nav не торчат.
6. Visual/e2e зелёные под новый UI.
7. Визуально близко к `k8s-cockpit-v1.html` внутри app shell (плотность, светлый фон, один cobalt CTA).

---

## 14. Риски и митигации

| Риск | Митигация |
|------|-----------|
| Большой список pods без server filter | Client filter + поиск по имени; при проблемах — backend `?namespace=` follow-up |
| Старые visual snapshots ломают CI | Этап D: обновить snapshots в том же PR, что UI |
| Скрытые страницы сломаются при агрессивном delete | Сначала route cutover, delete только после graph unused |
| Пользователи ждут «настоящий» AI | Disclaimer на панели explain; mock детерминированный |
| Путаница со старым diagnose → Studio | Не вызывать `createKubernetesDiagnosisDraft` из cockpit |

---

## 15. Рекомендуемый порядок следующего шага

После вашего «ок, можно код»:

1. **Этап A** (каркас + данные ns/pods/events + URL).  
2. Показать в UI и сверить с прототипом.  
3. **Этап B+C** (логи, explain mock, exec stub).  
4. **Этап D+E** (чистка, тесты, скрытые маршруты).

Оценка порядка величины (ориентир): A ≈ 0.5–1 дн., B+C ≈ 1 дн., D+E ≈ 0.5–1 дн. — зависит от объёма snapshot/e2e правок.

---

## 16. Ссылки на артефакты

- UX-прототип: [`k8s-cockpit-v1.html`](./k8s-cockpit-v1.html)
- Nav: `src/lib/navigation.ts` (`id: "kubernetes"` → `/kubernetes`)
- Routes: `src/App.tsx` (`/kubernetes*` блок)
- API client: `src/api/kubernetes.ts`, типы: `src/api/kubernetesTypes.ts`
- Backend urls: `kubernetes_ops/urls.py`

---

*Документ отражает ответы формы `k8s-code-kickoff` от 2026-09-14: `plan_only`, `keep_hidden`, `ui_stub`, `fe_mock`.*
