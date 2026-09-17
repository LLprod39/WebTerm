# Kubernetes: самообслуживание + админская выдача доступа

> Статус: **в реализации** — backend kubeconfig + ACL + UI upload/grants.  
> Дополняет [`KUBERNETES_COCKPIT_V1_PLAN.md`](./KUBERNETES_COCKPIT_V1_PLAN.md).  
> Кокпит UX уже в ритме Servers/Agents; этот документ — **модель подключения и прав**.

---

## 1. Цель одной фразой

Обычный пользователь сам подключает **свой** кластер через **файл kubeconfig** и сразу работает в кокпите (области → поды → логи → ИИ).  
Админ подключает **платформенные** кластеры (в т.ч. через Rancher), видит inventory, настраивает **Devtron / Fleet** только в Settings, и **выдаёт доступ** пользователям (кластер / namespace).  
Никто из обычных пользователей не лезет в Devtron/Fleet/provider-admin.

---

## Progress (реализация)

| Этап | Статус |
|------|--------|
| 1 Backend kubeconfig | Done — `KIND_KUBECONFIG`, `/api/kubernetes/connections/*`, sync namespaces/pods |
| 2 Backend access grants | Done — `K8sClusterAccess`, visibility filter, admin grant/revoke/candidates |
| 3 Frontend user connect | Done — kubeconfig upload instead of Rancher form |
| 4 Frontend admin access UI | Done — Settings → Kubernetes → «Доступ пользователей» |
| 5 Hardening / e2e | Partial — unit API tests; full e2e later |

Открытые вопросы §13 приняты по рекомендации: один context на upload; personal Rancher убран из user UI; grants только users; `expires_at` в модели.

---

## 2. Зафиксированные решения (из брифа)

| Тема | Решение |
|------|---------|
| Как пользователь добавляет кластер | **Файл kubeconfig** (upload / paste), не URL+token Rancher |
| Что видит пользователь | Только **свои** подключения + то, что **выдал админ** |
| Devtron / Fleet | Только **Settings → Kubernetes**, **staff/admin** |
| Кто может «добавить много кластеров / ноды / поды / ns» | **Админ** (платформенный inventory + sync) |
| Выдача доступа | Админ → пользователям (и опционально группам), по аналогии с **ServerShare** |
| Настройки провайдеров платформы | Только админ |
| Вкладка «Подключение» в кокпите | Для **всех** (справка + форма добавления своего kubeconfig) |
| Реализация сейчас | **Нет** — сначала этот план, потом этапы |

---

## 3. Две дорожки (обязательно разделить в голове и в UI)

```
┌──────────────────────────────────────────────────────────────────┐
│ A. Личное подключение (self-service)                             │
│    User → загрузил kubeconfig → «Мои кластеры» → кокпит          │
│    Владелец = пользователь. Может удалить / обновить файл.       │
├──────────────────────────────────────────────────────────────────┤
│ B. Платформенный кластер (admin-managed)                         │
│    Admin → Settings: Rancher/Devtron/Fleet → sync inventory      │
│    Admin → Access: выдать user доступ к cluster (± namespaces) │
│    User → видит кластер в кокпите как «Выдан администратором»    │
└──────────────────────────────────────────────────────────────────┘
```

Смешивать их в одну форму «добавь Rancher» **нельзя** — сейчас `AddClusterPanel` как раз Rancher URL+token; его нужно заменить/развести.

---

## 4. Роли и поверхности продукта

### 4.1 Обычный пользователь (`feature: kubernetes`, не staff)

| Можно | Нельзя |
|-------|--------|
| Открыть `/kubernetes` кокпит | Settings → Kubernetes (providers / Fleet / Devtron / release gate) |
| Вкладка **Подключение**: гайд + **добавить свой kubeconfig** | Маршруты `/kubernetes/fleet`, `/devtron`, `/admin` (даже если URL угадает — 403) |
| Список «Мои кластеры» + «Доступ выдан» | Создавать Devtron/Fleet провайдеры |
| Namespace / pods / logs / events / explain (v1) | Выдавать доступ другим |
| Удалить / обновить **свой** kubeconfig | Видеть чужие kubeconfig / secret_ref |
| | Синхронизировать platform providers «sync all» |

### 4.2 Админ (`is_staff` + kubernetes)

Всё, что у пользователя, **плюс**:

| Можно | Где |
|-------|-----|
| Добавлять платформенные провайдеры (Rancher / Devtron) | Settings → Kubernetes |
| Sync / probe / inventory (ns, nodes, workloads, pods counters) | Settings + скрытые admin-страницы |
| Fleet / Devtron операторские экраны | Settings + прямые URL (не в product nav) |
| Выдавать / отзывать доступ пользователям к cluster / namespace | Settings → Access (новый блок) или панель на cluster |
| Добавлять kubeconfig **от имени платформы** (опционально, редкий путь) | Settings, с пометкой «платформенный», не «личный» |
| Кнопка «Настройки» в шапке кокпита | Только staff |

---

## 5. Модель данных (целевая)

### 5.1 Что уже есть

- `K8sProvider` — только `rancher` | `devtron`, `created_by`, `secret_ref` / ManagedSecret.
- `K8sCluster` — inventory, привязка к Rancher/Devtron id.
- `K8sNamespace` — inventory по cluster.
- Права: feature flags + `is_staff`; `can_connect_clusters` / `can_manage_own_rancher_providers` уже намекают на self-service, но UI/API завязаны на **Rancher**, не kubeconfig.
- **Нет** аналога `ServerShare` для Kubernetes (cluster/namespace ACL).

### 5.2 Что добавить (концептуально)

#### A. Провайдер / соединение типа `kubeconfig`

Новый kind (имя на выбор, зафиксировать в реализации):

- `kind = "kubeconfig"` (предпочтительно) **или** `direct`.

Поля (минимум):

| Поле | Смысл |
|------|--------|
| `name` | Человекочитаемое имя («prod-home», «lab») |
| `created_by` | Владелец личного подключения |
| `scope` | `personal` \| `platform` |
| `secret_ref` | Зашифрованный kubeconfig / token material (как сейчас для Rancher token) |
| `context_name` | Какой context из файла использовать |
| `server_fingerprint` | host API (без секретов) для UI |
| `enabled`, `last_sync_at`, `last_error` | как у других providers |

После сохранения: **probe** → создать/обновить `K8sCluster` row(s) (обычно 1 context = 1 cluster), пометить источник `source: kubeconfig`.

> Важно: это **не** «один admin kubeconfig на всех» из старых architecture docs.  
> Это **scoped credential на владельца** (personal) или явно помеченный platform credential под staff.  
> В ответах API — никогда raw kubeconfig; только `has_secret`, `context`, `server`.

#### B. Таблица доступа (как ServerShare)

`K8sClusterAccess` (название условное):

| Поле | Смысл |
|------|--------|
| `cluster` | FK → K8sCluster |
| `user` | FK → User (позже: group) |
| `granted_by` | кто выдал |
| `namespaces` | JSON list **или** M2M; пустой = весь cluster (read) |
| `can_view_logs` | default true |
| `can_exec` | default false (v1 UI stub всё равно) |
| `expires_at` / `revoked_at` | как у servers |
| `created_at` | audit |

Правило видимости кластера для user:

```
visible =
  (cluster.provider.scope == personal AND provider.created_by == me)
  OR
  (есть активный K8sClusterAccess на меня)
  OR
  (is_staff AND platform inventory — полный staff list)
```

Правило namespace:

```
если access.namespaces пустой → все ns кластера (в рамках RBAC kube-credentials)
если задан список → пересечение inventory ∩ grant
для personal kubeconfig → все ns, которые отдаёт этот credential (kube RBAC режет глубже)
```

#### C. Inventory админа

Админский sync (Rancher/Devtron/kubeconfig-platform) наполняет:

- clusters, namespaces, node counts, workloads/pods summary  
Пользователь **не** «создаёт поды» в WebTerm — он **видит** то, что уже есть в кластере.  
«Добавить поды/ноды» в продуктовом смысле = **подключить кластер и синхронизировать inventory**, не kubectl create из UI в v1.

---

## 6. UX-потоки

### 6.1 Пользователь: «Добавить свой кластер»

Вкладка **Подключение** (или CTA в пустом состоянии):

1. Короткий текст: «Нужен файл `kubeconfig` с вашего компьютера (обычно `~/.kube/config`).»
2. Поле имени + **file upload** (+ опционально paste YAML).
3. Если в файле несколько contexts → выбрать один (select).
4. Кнопка «Подключить» → probe → кластер появляется в фильтре «Кластер».
5. Список «Мои подключения»: имя, API host, статус, «Обновить файл», «Удалить».

Не показывать: Rancher URL, Devtron, Fleet, token Rancher.

### 6.2 Пользователь: «Мне выдали доступ»

В списке кластеров бейдж **«От администратора»**.  
Блок «Подключение» объясняет: «Если кластера нет — попросите админа выдать доступ или загрузите свой kubeconfig.»

### 6.3 Админ: платформа

**Settings → Kubernetes** (как сейчас, плюс):

1. Providers: Rancher / Devtron (существующее).  
2. Fleet / Devtron links — только здесь (и staff-only routes).  
3. **Новый блок «Доступ пользователей»**:
   - выбрать cluster;
   - выбрать user;
   - опционально ограничить namespaces (multi-select из inventory);
   - выдать / отозвать;
   - таблица текущих grants.
4. Опционально: «Платформенный kubeconfig» (редко) — отдельная форма, не в user-facing вкладке.

### 6.4 Кокпит (без смены паттерна Servers)

Вкладки остаются: **Поды | События | Подключение**.

- Фильтр кластеров = union(личные + выданные).  
- Namespace select = разрешённые ns.  
- Шапка: «Настройки» только staff → `/settings/kubernetes`.

---

## 7. API (черновик контракта)

### 7.1 Self-service kubeconfig

| Метод | Путь | Кто | Назначение |
|-------|------|-----|------------|
| POST | `/api/kubernetes/connections/kubeconfig/` | user с `kubernetes` | upload: name, file/text, context |
| GET | `/api/kubernetes/connections/` | user | мои personal + кратко platform grants |
| POST | `/api/kubernetes/connections/{id}/probe/` | owner | проверка |
| POST | `/api/kubernetes/connections/{id}/rotate/` | owner | новый файл |
| DELETE | `/api/kubernetes/connections/{id}/` | owner | удалить + revoke secret |

Ответ create/probe: `{ success, connection: { id, name, context, server, cluster_id?, status }, error? }` — **без** kubeconfig body.

### 7.2 Admin access grants

| Метод | Путь | Кто |
|-------|------|-----|
| GET/POST | `/api/kubernetes/clusters/{id}/access/` | staff |
| POST | `/api/kubernetes/clusters/{id}/access/{grant_id}/revoke/` | staff |
| GET | `/api/kubernetes/access/candidates/` | staff (как server share candidates) |

### 7.3 Существующие read API

`clusters`, `namespaces`, `pods`, `events`, `logs` — **фильтровать на сервере** по visibility (не только на клиенте).  
Сейчас клиентский filter ns — ок для UX, но security boundary = backend.

### 7.4 Providers admin

`POST/PATCH providers` kind `devtron` | platform `rancher` — **staff only**.  
Personal Rancher self-service **выводим из user UI** (заменяем kubeconfig).  
Если нужно оставить Rancher self-service позже — отдельный эпик, не v1 этого плана.

---

## 8. Безопасность (обязательные правила)

1. **Никогда** не отдавать kubeconfig/token в JSON фронту после сохранения.  
2. Хранение только через существующий encrypted secret path (`ManagedSecret` / `secret_ref`).  
3. Redact в логах/audit (уже есть паттерны `kubeconfig` в serializers).  
4. Personal connection: CRUD только `created_by == request.user` (staff может revoke/delete в admin tools).  
5. Platform grants: deny-by-default; нет grant → нет cluster в list.  
6. Upload size limit + YAML parse fail-closed; не принимать бинарники.  
7. Prefer documenting: «кладите в файл SA token / ограниченный context, не cluster-admin».  
8. Не противоречить духу architecture docs: запрещён **общий admin kubeconfig на всю компанию**; personal/platform-scoped — да, с audit.

---

## 9. Состояние «сейчас → цель» (gap)

| Сейчас | Цель |
|--------|------|
| User UI: Rancher URL + API token (`AddClusterPanel`) | User UI: **kubeconfig file** |
| Нет ACL на cluster/namespace | `K8sClusterAccess` + серверный filter |
| Devtron/Fleet в скрытых routes + settings | Оставить **только admin/settings**; user nav чистый |
| `can_manage_own_rancher_providers` | Переименовать/расширить → `can_manage_own_connections` (kubeconfig) |
| Clusters list почти глобальный для feature | Visibility = own + granted (+ staff all) |
| «Подключение» = гайд + Rancher form | Гайд + kubeconfig + (staff) ссылка в Settings |

---

## 10. Этапы реализации (когда скажете «можно»)

### Этап 0 — Согласование (этот документ)

- [ ] Подтвердить: user **только kubeconfig**, не Rancher self-service.  
- [ ] Подтвердить: grant на уровне **cluster + optional namespaces**.  
- [ ] Подтвердить: группы пользователей в v1 **не делаем** (только user), группы — v1.1.

### Этап 1 — Backend: kubeconfig connection

1. Model/kind + secret storage.  
2. Parse kubeconfig (contexts), probe API reachability.  
3. Create/link `K8sCluster`.  
4. CRUD API + permission tests + secret-not-in-response tests.

### Этап 2 — Backend: access grants

1. `K8sClusterAccess` model + admin API.  
2. Filter `clusters/namespaces/pods/events/logs` by visibility.  
3. Staff tests + reader denied tests.

### Этап 3 — Frontend: user connect

1. Заменить `AddClusterPanel` на kubeconfig upload.  
2. Обновить `connectionGuide.ts` / `k8s-connection-guide.md`.  
3. Список «Мои подключения» на вкладке Подключение.  
4. Убрать Rancher-поля из user surface.

### Этап 4 — Frontend: admin access UI

1. Блок в Settings → Kubernetes: выдача доступа.  
2. Бейджи «Мой» / «Выдан» в селекте кластера кокпита.  
3. Staff-only Devtron/Fleet без изменений концепции (уже почти так).

### Этап 5 — Hardening

1. E2E: user upload → видит pods; другой user — нет.  
2. E2E: admin grant namespace → видит только его.  
3. Audit events: connect / rotate / grant / revoke.  
4. Обновить `KUBERNETES_COCKPIT_V1_PLAN.md` статусом.

---

## 11. Non-goals этого плана

- Пользователь создаёт Deployments/Pods из WebTerm.  
- Полноценный multi-tenant kube-RBAC editor.  
- Обязательный Keycloak group → namespace mapping (уже описан в ops docs — позже стыковать с grants).  
- Реальный exec API (остаётся stub).  
- Возврат Fleet/Devtron в product nav.  
- Хранение одного shared admin kubeconfig «на всех».

---

## 12. Критерии готовности

1. Новый user с feature `kubernetes` без staff: загрузил kubeconfig → видит свои ns/pods/logs.  
2. Второй user без grant и без своего файла: пустой список / гайд, 403 на чужой cluster id.  
3. Admin выдал cluster (или ns) → user видит только разрешённое.  
4. User не видит Settings Kubernetes / Fleet / Devtron CTA.  
5. Admin видит Settings + access grants + platform providers.  
6. Ни один API success-response не содержит raw kubeconfig/token.

---

## 13. Открытые вопросы (ответить перед кодом)

1. **Несколько contexts в одном файле** — создавать N connections или один + select context?  
   *Рекомендация:* один upload → выбор context → одна connection; «добавить ещё context» = повторный upload/выбор.  
2. **Personal Rancher** — полностью убрать или оставить advanced?  
   *Рекомендация:* убрать из user UI в этом эпике.  
3. **Группы** — v1 только users?  
   *Рекомендация:* да, только users.  
4. **Истечение grant** — нужно в v1?  
   *Рекомендация:* поле `expires_at` в модели сразу, UI expiry можно во второй итерации.

---

## 14. Следующий шаг

После вашего «ок / поправь X» — реализация **Этап 1** (backend kubeconfig) или сразу **1+3** (backend + user UI), если хотите быстрее увидеть upload в кокпите.  
Access grants (этапы 2+4) логично вторым PR, чтобы не смешивать секрет-upload и ACL.
