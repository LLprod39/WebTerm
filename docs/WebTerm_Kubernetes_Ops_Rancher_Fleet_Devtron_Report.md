# WebTerm Kubernetes Ops

## Интеграция Rancher + Fleet + Devtron

**Отчёт по архитектуре, UX, безопасности и плану внедрения**
**Дата:** 1 июля 2026
**Платформа:** <https://github.com/LLprod39/WebTerm/tree/test>

---

## Короткий вердикт

Да, **Rancher + Fleet + Devtron можно подключить к WebTerm**.

Правильная модель:

```text
WebTerm = единый cockpit / портал / автоматизации / аудит / AI Ops
Rancher = управление Kubernetes-кластерами, доступами, RBAC, monitoring, cluster lifecycle
Fleet   = корпоративный GitOps / HelmOps engine поверх Rancher
Devtron = AppOps / CI/CD / Helm UI / логи / terminal / debugging для приложений
```

WebTerm не должен пытаться заменить Rancher или Devtron как control-plane/source-of-truth. Он должен стать **единым рабочим cockpit-слоем**, где пользователь видит статусы, логи, диагностику, approvals и runbook-и без ежедневного открытия Rancher/Fleet/Devtron UI; внешние UI остаются staff/admin fallback.

Единый execution backlog для улучшенной версии Freelens внутри WebTerm ведётся в `docs/architecture/KUBERNETES_LOW_LEVEL_ADMIN_MODE_PLAN.md`. Этот отчёт фиксирует продуктовую и интеграционную модель Rancher/Fleet/Devtron, а low-level план содержит конкретные API, session lifecycle, audit, streaming, write guards, break-glass и test gates.

---

## Содержание

1. [Executive Summary](#1-executive-summary)
2. [Целевая роль каждого компонента](#2-целевая-роль-каждого-компонента)
3. [Целевая архитектура](#3-целевая-архитектура)
4. [Как это будет выглядеть в WebTerm](#4-как-это-будет-выглядеть-в-webterm)
5. [Интеграционные уровни: MVP, Embedded, Native](#5-интеграционные-уровни-mvp-embedded-native)
6. [Backend и Frontend изменения в WebTerm](#6-backend-и-frontend-изменения-в-webterm)
7. [SSO, RBAC и модель доступа](#7-sso-rbac-и-модель-доступа)
8. [HelmOps и владение релизами](#8-helmops-и-владение-релизами)
9. [Терминалы, logs, exec и WebSocket](#9-терминалы-logs-exec-и-websocket)
10. [Безопасность и корпоративные ограничения](#10-безопасность-и-корпоративные-ограничения)
11. [Пошаговый план внедрения](#11-пошаговый-план-внедрения)
12. [Риски и меры снижения](#12-риски-и-меры-снижения)
13. [Финальная рекомендация](#13-финальная-рекомендация)
14. [Текущее состояние WebTerm в этом repo](#14-текущее-состояние-webterm-в-этом-repo)
15. [Полноценный implementation plan](#15-полноценный-implementation-plan)
16. [Product backlog по модулям](#16-product-backlog-по-модулям)
17. [Контракты данных и API](#17-контракты-данных-и-api)
18. [Как будет выглядеть готовая система](#18-как-будет-выглядеть-готовая-система)
19. [Definition of Done и проверки](#19-definition-of-done-и-проверки)
20. [Источники](#20-источники)

---

# 1. Executive Summary

Подключить **Rancher**, **Fleet** и **Devtron** к WebTerm можно, и архитектурно это выглядит логично: три внешние Kubernetes-системы не заменяют WebTerm, а становятся специализированными подсистемами вокруг него.

Главная идея: **не переписывать Rancher или Devtron внутри WebTerm**, но и не заставлять обычного пользователя открывать их отдельно. WebTerm должен быть единой рабочей панелью, которая:

- показывает статусы кластеров, приложений и rollout-ов;
- даёт WebTerm-native работу с Kubernetes Ops без ежедневного перехода в Rancher/Devtron;
- запускает безопасные runbook-и;
- собирает audit trail;
- связывает Kubernetes Ops с существующими Studio/Terminal/Monitoring возможностями;
- добавляет approvals и AI/Ops-автоматизацию поверх готовых Kubernetes-платформ.

Rancher лучше оставить **source of truth** по Kubernetes-кластерам, пользователям, проектам, namespaces, RBAC, lifecycle, monitoring/logging и platform add-ons.

Fleet использовать для **корпоративного GitOps/HelmOps** на множество кластеров.

Devtron использовать для команд разработки и AppOps: **Helm-приложения, values.yaml, deployment history, CI/CD, rollback, logs и debugging**.

Для пользователя целевая модель такая: он логинится в WebTerm и работает только в WebTerm. Rancher, Fleet и Devtron остаются backend/source-of-truth платформами, а их собственные UI нужны только для staff/admin fallback, break-glass и ручной проверки во время внедрения.

| Компонент | Роль в итоговой платформе | Основная ценность |
|---|---|---|
| WebTerm | Единый cockpit, dashboard, automation, approvals, audit, terminal-паттерны | Один вход для операторов, DevOps, SRE и AI/runbook automation |
| Rancher | Управление Kubernetes-кластерами, RBAC, projects/namespaces, lifecycle, catalog/apps | Enterprise control plane для Kubernetes |
| Fleet | GitOps/HelmOps engine поверх Rancher | Массовый rollout Helm/GitOps на dev/stage/prod/customer clusters |
| Devtron | AppOps, Helm UI, CI/CD, logs, terminal/debugging | Удобная self-service панель для команд разработки |

> **Главное правило владения:** один Helm release должен иметь одного владельца. Если release управляется Fleet, Devtron может показывать его read-only, но не должен делать upgrade/delete. Если приложение управляется Devtron, Fleet не должен применять поверх него другой chart с тем же release name.

---

# 2. Целевая роль каждого компонента

## 2.1. WebTerm

Текущий WebTerm уже имеет естественную основу для cockpit-слоя:

- React/Vite frontend;
- Django backend;
- Django Channels / WebSocket;
- SSH terminal;
- monitoring;
- Studio pipelines;
- agents;
- permissions;
- audit middleware.

Поэтому Kubernetes Ops можно добавить как отдельный модуль, не ломая существующую архитектуру.

WebTerm должен быть:

```text
единая витрина + действия + аудит + автоматизации
```

А не:

```text
ещё один полный Kubernetes dashboard с нуля
```

## 2.2. Rancher

Rancher должен быть главным **Kubernetes management plane**.

Он отвечает за:

- импорт и управление кластерами;
- RKE2/K3s/managed/existing clusters;
- централизованную аутентификацию;
- RBAC;
- projects/namespaces;
- catalog/apps;
- monitoring/logging;
- lifecycle операций;
- platform add-ons;
- enterprise governance.

В WebTerm Rancher лучше показывать через:

- агрегированные статусы;
- deep links;
- ограниченные API-вызовы;
- карточки кластеров;
- ссылки на projects, namespaces, workloads и apps.

## 2.3. Fleet

Fleet должен отвечать за корпоративный **GitOps/HelmOps**.

Fleet подходит для:

- platform charts;
- стандартных add-ons;
- security/observability компонентов;
- управляемых rollout-ов по группам кластеров;
- HelmOp;
- GitRepo;
- Bundles;
- rollout strategy;
- массового управления dev/stage/prod/customer clusters.

Для production лучше проектировать HelmOps через Fleet, а не через ручное нажатие `upgrade` в UI.

## 2.4. Devtron

Devtron стоит использовать как **AppOps-портал** для команд разработки.

Он закрывает:

- Helm apps;
- Chart Store;
- values.yaml;
- deployment history;
- status;
- update/upgrade/delete;
- logs;
- pod terminal;
- debug terminal;
- CI/CD;
- GitOps visibility.

В WebTerm Devtron лучше отображать как application-слой:

- app cards;
- статусы;
- ссылки на logs;
- ссылки на history;
- rollback links;
- переходы в Devtron UI.

---

# 3. Целевая архитектура

## 3.1. Общая схема

```text
                         +--------------------+
                         |   Keycloak / OIDC  |
                         |   единый SSO       |
                         +---------+----------+
                                   |
        +--------------------------+--------------------------+
        |                          |                          |
+-------v--------+        +--------v--------+        +--------v--------+
|    WebTerm     |        |    Rancher      |        |    Devtron      |
| Cockpit/API    |        | Cluster Mgmt    |        | AppOps/Helm UI  |
| Audit/Studio   |        | RBAC/Fleet      |        | CI/CD/Debug     |
+-------+--------+        +--------+--------+        +--------+--------+
        |                          |                          |
        | API / deep links         | Fleet CRDs               | API / deep links
        |                          |                          |
        +-------------+------------+------------+-------------+
                      |                         |
              +-------v--------+        +-------v--------+
              | Fleet          |        | Devtron        |
              | GitOps/HelmOps |        | AppOps flows   |
              +-------+--------+        +-------+--------+
                      |                         |
        +-------------v-------------------------v-------------+
        |          Downstream Kubernetes clusters              |
        |      dev / stage / prod / customer / edge            |
        +------------------------------------------------------+
```

## 3.2. Рекомендуемые домены

```text
webterm.company.com   -> WebTerm: cockpit, automation, audit
rancher.company.com   -> Rancher Manager: cluster management, RBAC, Fleet
devtron.company.com   -> Devtron: AppOps, Helm UI, CI/CD, debugging
keycloak.company.com  -> OIDC/SSO для всех систем
```

Subdomain-подход предпочтительнее path proxy.

Лучше так:

```text
webterm.company.com
rancher.company.com
devtron.company.com
```

Хуже так:

```text
company.com/webterm
company.com/rancher
company.com/devtron
```

Причина: Rancher/Devtron/OIDC/WebSocket/cookies/CSP обычно проще и безопаснее настроить на отдельных доменах, чем пытаться держать все панели на путях вида `/rancher` и `/devtron`.

## 3.3. Основные потоки

| Поток | Как должен работать | Почему так безопаснее |
|---|---|---|
| Login | Пользователь логинится в WebTerm: LDAP/OIDC/Keycloak или local WebTerm account | Пользовательский пароль не копируется в Rancher/Devtron, WebTerm остаётся единой точкой входа |
| Provider access | WebTerm backend читает Rancher/Fleet/Devtron через service credentials/read-only service accounts | Минимальные права, меньше риск случайных изменений |
| Daily UX | Обычный пользователь работает в WebTerm-native страницах, без открытия Rancher/Fleet/Devtron UI | Один audit, одна permission model, меньше путаницы |
| Fallback | Rancher/Devtron/Fleet UI можно открыть только staff/admin как audited fallback или break-glass | Сохраняем аварийный путь, но не делаем его основной работой |
| Write actions | Опасные действия идут через approved runbook/GitOps/MR flow в WebTerm, а фактический owner остаётся Rancher/Fleet/Devtron/GitOps | Есть RBAC, approval и audit |
| Terminal/debug | Только через отдельные permissions и audit events | exec/node-debug несут высокий риск privilege escalation |

---

# 4. Как это будет выглядеть в WebTerm

В WebTerm стоит добавить новый верхнеуровневый раздел:

```text
Kubernetes Ops
├── Overview
├── Clusters
├── Fleet HelmOps
├── Devtron AppOps
├── Terminals & Logs
├── Automations
└── Audit
```

Это будет не копия Rancher/Devtron, а единая витрина, которая связывает кластеры, приложения, rollout-ы, терминалы, автоматизации и аудит.

## 4.1. Overview

```text
+-------------------------------------------------------------------+
| Kubernetes Ops                                                     |
|                                                                    |
| [12 Clusters] [184 Apps] [7 Fleet Rollouts] [3 Incidents]          |
|                                                                    |
| prod-kz-1: Degraded  | prod-eu-1: Healthy | stage-1: Healthy       |
| Open Rancher         | Open Devtron       | View Logs              |
|                                                                    |
| Fleet Rollouts                                                     |
| cert-manager 1.16.x     dev OK -> stage OK -> prod pending         |
| ingress-nginx 4.12.x    dev OK -> stage degraded -> prod blocked   |
|                                                                    |
| Recent AppOps                                                      |
| payments-api     prod-kz-1     deployed by Devtron     healthy     |
| billing-worker   prod-eu-1     degraded                logs        |
+-------------------------------------------------------------------+
```

`Overview` должен быть нативной страницей WebTerm. Он показывает summary, health, ссылки и действия, но не заставляет пользователя вручную открывать три разные панели.

## 4.2. Страница кластера

```text
Kubernetes Ops / Clusters / prod-kz-1

Status: Degraded
Provider: Rancher
Environment: Production
Nodes: 8/9 Ready
Apps: 47
Fleet bundles: 12
Devtron apps: 35

[Inventory] [Workloads] [Logs] [Events]
[Request Admin Session] [Run Approved Automation]

Tabs: Overview | Namespaces | Workloads | Helm Apps | Fleet | Events | Audit
```

На странице кластера WebTerm показывает агрегированные статусы и безопасные action-кнопки.

Глубокое управление остаётся в профильных системах:

| Действие | Где лучше делать |
|---|---|
| cluster lifecycle | Rancher |
| RBAC/project management | Rancher |
| storage/nodes/networking | Rancher |
| platform HelmOps | Fleet |
| app Helm values/history | Devtron |
| app logs/debug | Devtron или WebTerm terminal с audit |
| automation/approval/runbook | WebTerm |

## 4.3. Fleet HelmOps

```text
Kubernetes Ops / Fleet HelmOps

Name              Source             Target       Status
cert-manager      Helm repo          all          Ready
ingress-nginx     OCI registry       prod-*       Rolling
monitoring        GitRepo/platform   all          Ready
external-dns      Helm repo          stage        Failed

Rollout: ingress-nginx 4.12.x
  dev clusters      OK 4/4 ready
  stage clusters    WARN 2/3 ready
  prod clusters     paused / waiting

[Request continue approval] [Request pause approval] [Show diff] [Bundle targets]
```

Этот раздел нужен platform team. Он должен показывать не только сам факт Helm release, а состояние rollout-а по окружениям и группам кластеров.

## 4.4. Devtron AppOps

```text
Kubernetes Ops / Devtron AppOps

Search: payments
Filter: prod-kz-1 / namespace payments / team backend

App              Cluster     Namespace    Status      Actions
payments-api     prod-kz-1   payments     Healthy     logs exec history
payments-worker  prod-kz-1   payments     Degraded    logs debug rollback
payments-ui      stage-1     web          Healthy     open values
```

Этот раздел нужен разработчикам и DevOps-командам. Devtron должен оставаться удобным UI для Helm apps, values.yaml, deployment history, CI/CD, logs и debugging.

---

# 5. Интеграционные уровни: MVP, Embedded, Native

| Уровень | Что делаем | Плюсы | Минусы | Сложность |
|---|---|---|---|---|
| MVP | WebTerm показывает native overview, inventory, apps, Fleet rollout summaries, logs snapshots и diagnosis drafts; external links остаются fallback | Быстро, мало риска, нет борьбы с iframe/CSP | Нужно честно ограничить функции, которых ещё нет native | Низкая/средняя |
| Embedded | Открываем Rancher/Devtron в iframe или full-screen reverse proxy | Похоже на встроенную панель | CSP, cookies, OIDC redirects, WebSocket upgrade, X-Frame-Options | Средняя/высокая |
| Native | WebTerm сам рисует Kubernetes Ops UI, backend читает API Rancher/Fleet/Devtron | Лучший UX, единый audit, свои approvals и automation | Нужно больше backend/frontend кода | Высокая |

## Рекомендованный путь

Начать с:

```text
MVP WebTerm-native read-only cockpit + audited fallback links
```

После стабилизации добавить нативные страницы:

```text
Overview
Clusters
Fleet HelmOps
Devtron AppOps
Audit
```

Embedded iframe использовать только как опциональный full-screen console, если корректно настроятся:

- headers;
- cookies;
- CSP;
- OIDC redirects;
- WebSocket upgrade.

---

# 6. Backend и Frontend изменения в WebTerm

## 6.1. Новый Django app

```text
kubernetes_ops/
├── models.py
├── permissions.py
├── audit.py
├── urls.py
├── views.py
└── services/
    ├── rancher_client.py
    ├── fleet_client.py
    ├── devtron_client.py
    └── cluster_registry.py
```

Backend WebTerm должен быть агрегатором статусов и координатором безопасных действий, а не универсальным Kubernetes admin-proxy.

Для production желательно использовать:

- read-only service account;
- короткоживущие provider tokens;
- минимальные права;
- encrypted secrets;
- external secret store/Vault;
- audit trail на каждое действие.

## 6.2. Предлагаемые модели

```python
class K8sProvider(models.Model):
    name = models.CharField(max_length=100)
    kind = models.CharField(
        choices=[
            ("rancher", "Rancher"),
            ("devtron", "Devtron"),
        ]
    )
    base_url = models.URLField()
    enabled = models.BooleanField(default=True)


class K8sCluster(models.Model):
    name = models.CharField(max_length=120)
    environment = models.CharField(max_length=50)  # dev/stage/prod
    rancher_cluster_id = models.CharField(max_length=120, blank=True)
    devtron_cluster_id = models.CharField(max_length=120, blank=True)
    labels = models.JSONField(default=dict)


class K8sAppRef(models.Model):
    name = models.CharField(max_length=160)
    namespace = models.CharField(max_length=120)
    cluster = models.ForeignKey(K8sCluster, on_delete=models.CASCADE)
    owner = models.CharField(
        choices=[
            ("fleet", "Fleet"),
            ("devtron", "Devtron"),
            ("external", "External"),
        ]
    )
    external_url = models.URLField(blank=True)


class K8sAuditEvent(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=120)
    cluster = models.ForeignKey(K8sCluster, null=True, on_delete=models.SET_NULL)
    provider = models.CharField(max_length=50)
    payload = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
```

## 6.3. Frontend-модуль

```text
frontend/src/features/kubernetes/
├── pages/
│   ├── KubernetesOverviewPage.tsx
│   ├── ClusterDetailPage.tsx
│   ├── FleetHelmOpsPage.tsx
│   ├── DevtronAppsPage.tsx
│   ├── K8sTerminalPage.tsx
│   └── K8sAuditPage.tsx
├── components/
│   ├── ClusterHealthCard.tsx
│   ├── FleetRolloutTable.tsx
│   ├── HelmAppTable.tsx
│   ├── ExternalConsoleFrame.tsx
│   └── OpenInProviderButton.tsx
└── api.ts
```

## 6.4. API endpoints в WebTerm

Примерный набор endpoint-ов:

```text
GET  /api/kubernetes/overview/
GET  /api/kubernetes/clusters/
GET  /api/kubernetes/clusters/{id}/
GET  /api/kubernetes/clusters/{id}/apps/
GET  /api/kubernetes/helm/releases/
GET  /api/kubernetes/fleet/rollouts/
GET  /api/kubernetes/fleet/bundles/
GET  /api/kubernetes/devtron/apps/
GET  /api/kubernetes/audit/
POST /api/kubernetes/actions/{action}/request-approval/
POST /api/kubernetes/actions/{action}/execute/
```

На MVP этапе лучше оставить только `GET` endpoints и external links. `POST` действия включать после модели RBAC/approval/audit.

---

# 7. SSO, RBAC и модель доступа

Лучший вариант: единый **Keycloak/OIDC** для WebTerm, Rancher и Devtron.

Пользователь должен логиниться своим корпоративным аккаунтом, а права должны синхронизироваться через группы.

```text
Keycloak / OIDC
  ├── WebTerm permissions
  ├── Rancher global/cluster/project roles
  └── Devtron permissions / permission groups
```

## 7.1. Рекомендуемые permissions в WebTerm

| Permission в WebTerm | Назначение | Кому давать |
|---|---|---|
| `k8s.view` | Смотреть кластеры, apps, rollouts | Developers, DevOps, SRE |
| `k8s.logs.view` | Смотреть pod/app logs | Developers, DevOps, SRE |
| `k8s.exec.pod` | exec в pod/container | DevOps/SRE, ограниченно |
| `k8s.terminal.cluster` | Cluster terminal с kubectl/helm/netshoot | SRE/Platform only |
| `k8s.terminal.node_debug` | Node debug shell | Только emergency/SRE с approval |
| `k8s.helm.deploy` | Helm deploy/update через утвержденный workflow | DevOps/platform по окружениям |
| `k8s.fleet.rollout.pause` | Остановить rollout | Platform/SRE |
| `k8s.fleet.rollout.resume` | Продолжить rollout | Platform/SRE + approval для prod |
| `k8s.admin` | Администрирование интеграции | Минимальный круг админов |

## 7.2. Не хранить admin kubeconfig в WebTerm

Опасная анти-модель:

```text
WebTerm backend хранит один admin kubeconfig
Все пользователи делают действия через него
```

Правильная модель:

```text
User -> SSO -> WebTerm role
User -> SSO -> Rancher role
User -> SSO -> Devtron role
```

WebTerm может иметь только:

- минимальные service credentials для чтения summary/status;
- отдельные service credentials для строго разрешённых automation-flow;
- audit на каждое действие;
- approval для production-действий.

## 7.3. Проверяемый MVP access model

Этот mapping нужен как release gate перед multi-user pilot. Он не включает реальный production SSO сам по себе, но фиксирует, какие группы должны быть заведены в Keycloak/OIDC и как они должны совпадать с WebTerm, Rancher и Devtron.

Keycloak group -> WebTerm feature -> Rancher/Devtron role:

| Keycloak group | WebTerm | Rancher | Devtron | Разрешено в WebTerm | Запрещено в WebTerm |
|---|---|---|---|---|---|
| `webterm-kubernetes-readers` | feature `kubernetes`, не staff | project/cluster read-only | application view + logs | overview, inventory, events, bounded logs, action approval request | provider write, native rollout restart, exec, apply yaml, delete |
| `webterm-kubernetes-admins` | feature `kubernetes` + staff | cluster/project admin outside WebTerm | environment admin outside WebTerm | provider config/sync/probe, external action verification | native rollout restart, exec, cluster terminal, node debug |
| `webterm-studio-kubernetes-operators` | `kubernetes` + `studio_pipelines` + `studio_mcp` | read-only evidence source | read-only app evidence source | read-only Studio diagnosis draft through Kubernetes MCP | rollout/restart MCP, apply yaml MCP, exec MCP |

Read-only service account contract for WebTerm/Rancher provider evidence:

| Area | Contract |
|---|---|
| Name | `webterm-kubernetes-readonly` |
| Render command | `python manage.py render_kubernetes_ops_readonly_rbac --output artifacts/kubernetes_ops_readonly_rbac.yaml` |
| Validate command | `python manage.py render_kubernetes_ops_readonly_rbac --validate-only` |
| Live proof command | `python scripts/verify_kubernetes_ops_readonly_rbac_live.py --apply` |
| Scope | namespace/project scoped per pilot cluster |
| Allowed verbs | `get`, `list`, `watch` |
| Allowed resources | namespaces, pods, services, ingresses, events, deployments, statefulsets, daemonsets, replicasets |
| Denied verbs/subresources | create, update, patch, delete, deletecollection, escalate, bind, impersonate, `pods/exec`, `pods/attach`, `pods/portforward` |

`kubernetes_ops.services.access_model` теперь проверяет эту матрицу как readiness gate `access_model`. `kubernetes_ops.services.readonly_rbac` строит и валидирует Kubernetes ServiceAccount/ClusterRole/ClusterRoleBinding manifest: если появится write verb или exec/attach/portforward subresource, readiness должен перейти в `missing` и не дать включить sidebar. `kubernetes_ops.services.readonly_rbac_live` дополнительно проверяет live cluster через `kubectl auth can-i`: read verbs должны быть `yes`, write/exec/escalate checks должны быть `no`.

---

# 8. HelmOps и владение релизами

При одновременном использовании Fleet и Devtron нужно заранее разделить, кто владеет какими Helm releases.

Это критично, чтобы не получить:

- drift;
- непредсказуемые rollback-и;
- гонки контроллеров;
- разные values из разных систем;
- конфликт release name / namespace;
- потерю контроля над production.

## 8.1. Матрица владения

| Категория release | Владелец | Примеры | Как показывать в WebTerm |
|---|---|---|---|
| Platform add-ons | Fleet/Rancher | cert-manager, ingress-nginx, monitoring, logging, external-dns, longhorn, istio | Fleet rollout status + bundle targets; Rancher fallback only for staff/admin |
| Security/compliance | Fleet/Rancher | NeuVector, Kubewarden, policy agents, compliance scans | Статус + incidents + restricted actions |
| Product apps | Devtron | backend/frontend/microservices/workers/internal tools | WebTerm AppOps cards + logs/history/rollback context; Devtron fallback only for staff/admin |
| Экспериментальные dev apps | Devtron или отдельный sandbox Fleet | test apps, temporary charts | Отдельно маркировать `owner=sandbox` |

## 8.2. Главное правило

```text
one Helm release -> one owner
```

Плохо:

```text
Fleet применяет release payments-api
Devtron тоже делает upgrade release payments-api
```

Хорошо:

```text
Fleet управляет ingress-nginx / cert-manager / monitoring
Devtron управляет payments-api / billing-worker / frontend
```

## 8.3. Labels/annotations для владельца

Желательно ввести стандартные labels/annotations:

```yaml
metadata:
  labels:
    webterm.io/owner: fleet
    webterm.io/team: platform
    webterm.io/environment: prod
  annotations:
    webterm.io/source: rancher-fleet
    webterm.io/change-policy: approval-required
```

Для Devtron-managed приложений:

```yaml
metadata:
  labels:
    webterm.io/owner: devtron
    webterm.io/team: payments
    webterm.io/environment: prod
  annotations:
    webterm.io/source: devtron
    webterm.io/change-policy: app-team-controlled
```

## 8.4. Текущий backend contract в WebTerm

В текущей реализации это правило уже имеет read-only backend contract:

```text
GET /api/kubernetes/helm/releases/
```

Endpoint собирает Helm release view из нормализованного inventory:

- Rancher/Kubernetes workloads;
- Fleet bundles;
- Devtron app refs.

Он возвращает `release_name`, `cluster`, `namespace`, `owners`, `primary_owner`, `conflict`, `one_release_one_owner`, связанные workloads/apps/bundles и policy:

- `fleet_gitops_or_mr` для Fleet-owned релизов;
- `devtron_rollback_or_deploy` для Devtron-owned релизов;
- `resolve_owner_before_mutation` если один release одновременно выглядит Fleet- и Devtron-owned;
- `webterm_admin_session` только для не конфликтующих Rancher/WebTerm-owned объектов.

Обычный пользователь получает WebTerm-native данные без внешних Rancher/Fleet/Devtron links. Staff fallback links остаются sanitized: без query string, token, userinfo и fragment. Audit сохраняет только counts/owners/filters, а не raw manifests или секреты.

---

# 9. Терминалы, logs, exec и WebSocket

У WebTerm уже есть терминальная модель через WebSocket/xterm.js.

Kubernetes-терминалы можно встроить двумя путями:

1. Открывать Devtron/Rancher terminal как deep link.
2. Реализовать собственный audited terminal в WebTerm через backend bridge.

## 9.1. Что делать сначала

| Сценарий | Где делать вначале | Когда переносить в WebTerm |
|---|---|---|
| Pod logs | Devtron deep link + WebTerm summary | Когда нужен единый audit/report |
| Pod exec | Devtron / ограниченный WebTerm bridge | Когда есть точные permissions и запись сессий |
| Cluster terminal | Devtron только для super-admin/SRE | После approval engine и audit trail |
| Node debug | Не давать в MVP | Только emergency flow с approval, TTL и записью |
| Port-forward | Не в MVP | После threat model и сетевых ограничений |

## 9.2. Риск Devtron Debug Mode

Devtron cluster terminal/debug mode может дать интерактивный shell на node с unrestricted access.

В корпоративном WebTerm такой сценарий должен быть закрыт:

- отдельным permission;
- approval flow;
- TTL;
- записью audit event;
- session recording;
- ограничением окружений;
- break-glass процедурой.

## 9.3. WebSocket bridge в WebTerm

Если делать Kubernetes exec/logs внутри WebTerm, архитектура может выглядеть так:

```text
Browser xterm.js
  -> WebTerm Channels WebSocket
    -> permissions check
    -> approval check, если prod/опасное действие
    -> audit event start
    -> Kubernetes exec/log stream
    -> audit event end + session metadata
```

Минимальные данные audit event:

```json
{
  "user": "ivan.petrov",
  "action": "k8s.exec.pod",
  "cluster": "prod-kz-1",
  "namespace": "payments",
  "pod": "payments-api-7b8c9d",
  "container": "app",
  "started_at": "2026-06-29T10:00:00Z",
  "ended_at": "2026-06-29T10:05:30Z",
  "approval_id": "apr_123",
  "reason": "incident INC-421"
}
```

---

# 10. Безопасность и корпоративные ограничения

## 10.1. Secrets

Все provider tokens хранить encrypted-at-rest, лучше через:

- Vault;
- External Secrets;
- cloud secret manager;
- sealed secrets;
- short-lived credentials.

Не хранить admin kubeconfig в обычной БД.

## 10.2. SSO

Использовать Keycloak/OIDC как единый IdP.

Не делать отдельные локальные пароли для ежедневной работы.

## 10.3. Network

Rancher, Devtron и WebTerm держать за:

- TLS;
- ingress;
- corporate VPN/ZTNA, если нужно;
- WAF, если применимо;
- корректным `ALLOWED_HOSTS`;
- CORS/CSP;
- rate limits.

## 10.4. Iframe

Не считать iframe главным способом интеграции.

Проблемные зоны:

- `Content-Security-Policy`;
- `X-Frame-Options`;
- cookies;
- `SameSite`;
- OIDC redirects;
- WebSocket upgrade;
- CSRF;
- mixed content.

Deep links + native summary pages должны быть основным путём.

## 10.5. Audit

Все dangerous actions нужно писать в WebTerm audit + provider audit/logs:

- `exec`;
- `delete`;
- `upgrade prod`;
- `resume rollout`;
- `node debug`;
- `port-forward`;
- `delete namespace`;
- `delete helm release`;
- `change RBAC`.

## 10.6. Approvals

Для production-действий добавить human approval в WebTerm Studio:

- кто запросил;
- что изменится;
- diff;
- окно выполнения;
- rollback plan;
- affected clusters;
- affected namespaces;
- affected Helm releases;
- ссылка на incident/change request.

## 10.7. Rate limits и sync

Status sync делать через кэш/фоновые задачи, а не дёргать Rancher/Devtron API на каждый refresh UI.

Пример:

```text
python manage.py run_kubernetes_ops_sync_worker --daemon --interval 60
  -> sync Rancher clusters/projects/namespaces/workloads
  -> sync Fleet bundles/rollout state
  -> sync Devtron apps/environments/deployment status
  -> write normalized status into WebTerm DB/cache
  -> frontend reads from WebTerm API
```

Если production topology уже использует Celery beat/cron/systemd/compose workers, эта команда подключается туда как отдельный read-only worker. UI refresh не должен напрямую дёргать Rancher/Devtron.

---

# 11. Пошаговый план внедрения

| Этап | Что сделать | Результат | Сложность |
|---|---|---|---|
| 0. Подготовка | Выбрать домены, TLS, Keycloak/OIDC, окружение для Rancher/Devtron | Базовая инфраструктурная схема | Средняя |
| 1. Rancher | Развернуть Rancher, импортировать тестовый кластер, настроить пользователей/группы/RBAC | Rancher как source of truth по кластерам | Средняя |
| 2. Fleet | Настроить GitRepo/HelmOp для platform charts, labels clusters, rollout strategy | Корпоративный HelmOps/GitOps foundation | Средняя/высокая |
| 3. Devtron | Подключить Devtron к тем же кластерам, настроить SSO/RBAC/projects/environments | AppOps/Helm UI для команд | Средняя |
| 4. WebTerm MVP | Добавить Kubernetes Ops: links, cards, cluster/app/rollout summary read-only | Единая витрина без опасных write actions | Средняя |
| 5. WebTerm Native | Fleet rollout table, Devtron apps table, cluster detail pages, audit events | Полезный cockpit вместо набора ссылок | Высокая |
| 6. Automation | Approval flows, runbooks, preflight checks, rollback actions, reports | Главная ценность WebTerm поверх Kubernetes stack | Высокая |

## 11.1. Первый production-ready milestone

MVP должен быть read-only:

- отображение кластеров;
- отображение приложений;
- Fleet rollout status;
- health;
- deep links;
- базовый audit просмотра/переходов;
- синхронизация групп/permissions.

Write actions, exec и node debug лучше не включать до завершения модели:

- RBAC;
- audit;
- approval;
- секреты;
- threat model;
- session recording, если нужен terminal.

---

# 12. Риски и меры снижения

| Риск | Проявление | Митигировать так |
|---|---|---|
| Двойное владение Helm release | Fleet и Devtron перезаписывают друг друга | Owner label/registry, правило one release -> one owner, read-only отображение чужих releases |
| Разъезд RBAC | В WebTerm кнопка видна, а в Rancher/Devtron прав нет или наоборот | Группы из Keycloak, синхронная матрица ролей, deny-by-default в WebTerm |
| iframe ломается | Не открывается UI, проблемы с cookies/CSP/OIDC | Deep links как fallback, native summary pages как основной путь |
| Terminal privilege escalation | Обычный пользователь получает node shell | Separate permissions, approval, TTL, session recording, audit |
| Секреты утекли | Provider API token или kubeconfig лежит в БД/логах | Vault, secret redaction, rotation, no admin kubeconfig |
| API перегрузка | WebTerm часто дергает Rancher/Devtron | Кэш, фоновые sync tasks, rate limit, incremental updates |
| Слишком тяжёлый стек | Три панели сложно поддерживать | Чёткое разделение ролей и постепенное внедрение: Rancher+Fleet first, Devtron optional for AppOps |

---

# 13. Финальная рекомендация

Да, связка **Rancher + Fleet + Devtron** подходит для богатого корпоративного Kubernetes/HelmOps сценария в WebTerm.

Рекомендованный порядок:

```text
1. Rancher как control plane
2. Fleet как HelmOps/GitOps engine
3. WebTerm read-only cockpit
4. Devtron как AppOps-модуль для команд разработки
5. WebTerm native dashboards + automation + approvals
```

Если нужно сократить стек, минимальная сильная конфигурация:

```text
WebTerm + Rancher + Fleet
```

Devtron добавлять тогда, когда появится явная потребность в developer self-service:

- Helm UI;
- CI/CD;
- deployment history;
- rollback;
- logs;
- debugging;
- app-level operations.

Самая важная продуктовая ценность WebTerm в этой схеме — не “ещё один Kubernetes dashboard”, а единый cockpit для инфраструктуры:

- статусы;
- ссылки;
- approvals;
- runbooks;
- terminal-аудит;
- AI Ops;
- отчёты после действий;
- связка Kubernetes Ops с остальной инфраструктурой.

Итоговая роль:

```text
WebTerm  = cockpit / automation / approvals / audit / AI Ops
Rancher  = clusters / RBAC / lifecycle / platform management
Fleet    = GitOps + HelmOps at scale
Devtron  = AppOps / Helm UI / CI-CD / logs / debug
```

---

# 14. Текущее состояние WebTerm в этом repo

Эта секция привязывает план к реальному состоянию `C:\WebTrerm` на 1 июля 2026, а не к абстрактной схеме.

## 14.1. Что уже есть

| Область | Факт в repo | Вывод для плана |
|---|---|---|
| Route | `frontend/src/App.tsx` уже держит `/kubernetes` и `/kubernetes/admin` за `<FeatureGate feature="kubernetes">`; Admin Mode дополнительно требует backend policy `kubernetes_admin_read` | Обычный cockpit и low-level Admin Mode существуют как разные режимы, доступ должен оставаться feature-gated |
| Sidebar | `frontend/src/components/AppSidebar.tsx` показывает Kubernetes nav только при explicit feature + `/api/kubernetes/readiness/.ready_for_sidebar=true` | Больше нет hardcoded `KUBERNETES_NAV_READY=false`; production включает nav через backend readiness + env override |
| Страница | `frontend/src/pages/KubernetesPage.tsx` показывает operator-facing read-only cockpit поверх `/api/kubernetes/overview/`: clusters, apps, Fleet rollouts, incidents и degraded apps без provider forms/readiness internals | Sidebar всё ещё нельзя включать до provider sync, e2e evidence и external platform setup |
| Admin settings | `frontend/src/pages/settings/SettingsKubernetesPage.tsx` вынесла provider setup, sync worker и readiness gate в `/settings/kubernetes` | Обычный оператор не видит конфигурационную кашу на `/kubernetes`; admin управляет Rancher/Devtron sync из Settings |
| Feature access | `core_ui/models.py` содержит `("kubernetes", "Kubernetes")`, `kubernetes_admin_read`, `kubernetes_admin_write`, `kubernetes_break_glass`; все Kubernetes/Admin Mode flags входят в `EXPLICIT_OPT_IN_FEATURES` | Даже staff не должен получить Kubernetes или low-level Admin Mode автоматически |
| Access engine | `core_ui/access.py` уже централизует `feature_allowed_for_user()` и `build_user_access_payload()` | Использовать существующую модель доступа, не делать отдельный Kubernetes auth path |
| Studio automation | `studio/pilot_capability_packs.py` уже описывает `kubernetes_describe_workload`, `kubernetes_rollout_restart`, `kubernetes_rollout_status` | Kubernetes actions должны идти через MCP/capability pack, approval и verification |
| Tests | Есть `frontend/src/pages/KubernetesPage.test.tsx`, `frontend/src/pages/KubernetesAdminPage.test.tsx`, backend API tests и architecture guard | Новый модуль обязан расширять эти тесты, а не обходить их |
| Existing architecture plan | `docs/reports/WEBTERM_AUDIT_DEVELOPMENT_PLAN.md` фиксирует `Kubernetes Read-Only First` | MVP обязан быть read-only: namespaces/workloads/logs/events/describe/AI diagnosis |

## 14.2. Текущий blocker перед большим модулем

Команда:

```powershell
python scripts\check_architecture_sizes.py --strict-new
```

Изначальный blocker:

```text
Import boundaries: SUCCESS
Architecture Fitness Check: FAILURE
tests\test_ops_agent_memory_patterns.py
GOD-FILE: 533 > 500
```

Он закрыт split-ом operational playbook tests в `tests/test_ops_agent_memory_playbooks.py`.

Текущий результат после implementation slice:

```text
Import boundaries: SUCCESS
Architecture Fitness Check: SUCCESS
All architecture contracts satisfied.
```

Этот gate остаётся обязательным перед каждым следующим Kubernetes slice.

## 14.3. Рабочая позиция

Текущий WebTerm готов к Kubernetes Ops как к **новой bounded capability**, но ещё не готов как production Kubernetes control plane.

Правильное состояние перед включением sidebar:

```text
ready_for_sidebar = false
  until:
    architecture guard green                    [done]
    backend read-only endpoints implemented     [done]
    periodic sync worker implemented            [done]
    production worker topology declared         [done: compose + Render worker]
    provider credentials stored safely           [done: external refs or ManagedSecret]
    provider health/stale checks implemented    [done]
    native Rancher namespaces/workloads sync     [done: read-only K8sNamespace/K8sWorkloadRef inventory]
    native Rancher/Kubernetes events sync        [done: read-only K8sEvent inventory + cluster events API]
    audited provider deep links                  [done: Open/Logs/History/Fleet links write sanitized audit events]
    Studio read-only diagnosis draft action      [done: cockpit -> PipelineDraftSession, no PipelineRun]
    Studio automation readiness surfaced         [done: feature flags + skill + tested owned MCP binding check]
    production sync worker heartbeating
    UI overview renders real normalized data     [done for normalized DB rows]
    tests/e2e cover settings, empty, healthy and degraded states [done: readiness validates spec + snapshots]
```

## 14.4. Реализовано в текущем implementation slice

Это первый рабочий read-only слой, а не полный production control plane.

| Область | Реализовано |
|---|---|
| Backend app | Новый bounded app `kubernetes_ops` с models, serializers, readiness/overview services, provider sync, urls, admin и миграцией |
| Models | `K8sProvider`, `K8sCluster`, `K8sNamespace`, `K8sWorkloadRef`, `K8sPodRef`, `K8sNetworkRef`, `K8sEvent`, `K8sAppRef`, `K8sFleetBundle`, `K8sAuditEvent`, `K8sAdminSession`, `K8sAdminAction`, `K8sAdminRecording`, `K8sAdminRecordingEvent` |
| API | `GET /api/kubernetes/readiness/`, `release/summary/`, `overview/`, `clusters/`, `clusters/{id}/...`, `clusters/{id}/namespaces/{namespace_id}/`, `workloads/{id}/describe/`, `pods/{id}/logs/`, `network/{id}/`, `diagnostics/summary/`, `fleet/bundles/`, `fleet/bundles/{bundle_id}/`, `devtron/apps/`, `devtron/apps/{app_id}/`, `audit/`; `GET /api/kubernetes/providers/` и provider detail теперь staff/admin-only config endpoints; `GET /api/kubernetes/release/summary/` тоже staff-only и отдаёт read-only operator summary из readiness + release evidence artifact без live provider checks и без raw artifact payload, включая `progress.stage`, backend DoD percent, runtime-readiness percent, remaining blocker categories for UI status, `completion_audit` с явными flags по core backend/runtime/production evidence/sidebar enablement, `production_evidence_checklist` с required/present/status для production refs/latest external evidence bundle artifact checks без env values, `operator_command_plan` с production prerequisite/release artifact command phases plus recommended next action и `production_execution_plan` с blocked-until conditions plus 4 production phases/10 commands; `POST /api/kubernetes/audit/deeplink/` тоже staff/admin-only и пишет sanitized audit для fallback external links; `POST /api/kubernetes/providers/{id}/probe/` выполняет admin-only live provider probe без сохранения payload; `POST /api/kubernetes/actions/diagnose/` создаёт Studio draft для app diagnosis; action request lifecycle добавил `GET /api/kubernetes/actions/summary/`, `GET /api/kubernetes/actions/`, `request-approval/`, `approve-external/`, `verify-external/`, `status/`, `report/` с requester/staff visibility, metadata-only action queues and sanitized payloads; readiness/overview отдают `access_policy`, readiness отдаёт `worker_state`, `security_review` для CSP/CORS/CSRF posture, `terminal_safety` для exec/debug threat model и `operator_docs` для runbook/DR handoff; public serializers now enforce WebTerm-only UX for normal users: external Rancher/Fleet/Devtron `links` are empty, provider `base_url` is hidden, and staff/admin fallback links are sanitized without query/fragment/userinfo or sensitive link keys; cluster namespaces/workloads/pods/network/events отдают native Rancher inventory при наличии rows и fallback на Devtron/app/audit refs там, где native rows ещё нет; namespace/workload/pod/network/app/Fleet detail отдаёт sanitized normalized snapshot, policy и related events без обращения к live cluster; diagnostics summary отдаёт compact read-only triage по cluster/namespace/workload/pod/network без external links; pod logs endpoint отдаёт bounded read-only snapshot через provider JSON template без exec/streaming, а external fallback links присутствуют только в staff/admin responses; Admin Mode добавил session lifecycle `create/list/detail/approve/revoke/close/review/restricted-context`, fail-closed cluster terminal lifecycle `terminal/start` + `terminal/stop`, fail-closed node debug lifecycle `node-debug/start` + `node-debug/stop`, sanitized action evidence/report `GET /api/kubernetes/admin/actions/`, `/actions/{action_id}/`, `/actions/{action_id}/report/`, live resource explorer `discovery/resources/resources/detail/resources/describe/yaml/crds/resources/events/nodes`, break-glass node maintenance `nodes/cordon`, `nodes/uncordon`, `nodes/drain`, session-gated pod logs snapshot `GET /api/kubernetes/admin/clusters/{cluster_id}/logs/`, bounded resource watch preview `GET /api/kubernetes/admin/clusters/{cluster_id}/watch/`, runtime-gated `POST /api/kubernetes/admin/clusters/{cluster_id}/resources/apply/`, `/patch/`, `/scale/`, `/restart/`, `/delete/` и WebSocket routes `ws/kubernetes/admin/logs/{session_id}/`, `ws/kubernetes/admin/watch/{session_id}/`, `ws/kubernetes/admin/exec/{session_id}/`, `ws/kubernetes/admin/port-forward/{session_id}/` с bounded batch/follow-polling mode для logs/watch и fail-closed exec/port-forward bridges для break-glass validation, redaction, limits и audit/action/stream metadata без log/resource/command-args/tunnel content |
| Read-only detail APIs | `GET /api/kubernetes/clusters/{cluster_id}/namespaces/{namespace_id}/`, `GET /api/kubernetes/workloads/{workload_id}/`, `GET /api/kubernetes/pods/{pod_id}/`, `GET /api/kubernetes/network/{network_id}/`, `GET /api/kubernetes/fleet/bundles/{bundle_id}/`, `GET /api/kubernetes/devtron/apps/{app_id}/` return WebTerm-native sanitized detail context with metadata-only audit evidence; `GET /api/kubernetes/diagnostics/summary/` returns read-only triage for cluster/namespace/workload/pod/network scope with health severity, node/readiness gaps, restarts, unhealthy namespace/workload/pod counts, warning-event counts, owner/change-path context and safe next steps; Devtron detail now includes read-only AppOps `delivery_context` for chart/release, deployment history, Helm values preview, rollback context and logs/debug links |
| Provider sync | `RancherClient`, `DevtronClient`, flexible normalizers, ORM upsert service, `sync_kubernetes_ops` one-shot command и `run_kubernetes_ops_sync_worker` periodic worker; Rancher sync читает clusters, namespaces, workloads, pods, services, ingresses, events и Fleet bundles через configurable provider paths; Rancher 2.14 native proxy paths `/k8s/clusters/<id>/...` поддержаны для namespace/deployment/pod/service/ingress/event payloads; local self-signed Rancher допускается только через provider label `tls_verify=false`; Devtron sync поддерживает legacy Bearer GET и real Devtron session auth через `/orchestrator/api/v1/session`, `argocd.token` cookie, `text/event-stream` `data: {...}` payloads, `result.helmApps` и cluster alias map; daemon worker имеет failure backoff и пишет `consecutive_failures`/`next_delay_seconds` в heartbeat summary |
| Deployment topology | `docker-compose.yml`, `docker-compose.production.yml` и `render.yaml` имеют отдельный `kubernetes-ops-sync` worker; `.env.production.example` содержит `KUBERNETES_OPS_SYNC_INTERVAL_SECONDS`, `KUBERNETES_OPS_SYNC_MAX_BACKOFF_SECONDS`, `KUBERNETES_OPS_AUDIT_RETENTION_DAYS`, `KUBERNETES_OPS_RELEASE_ENVIRONMENT=local`, `KUBERNETES_OPS_PRODUCTION_APPROVAL_REF=`, `KUBERNETES_OPS_RELEASE_EVIDENCE_MAX_AGE_SECONDS=86400`, `KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED=false`, `KUBERNETES_ADMIN_BREAK_GLASS_APPLY_BYPASS_ENABLED=false`, `KUBERNETES_ADMIN_DRY_RUN_PROOF_MAX_AGE_SECONDS=1800`, `KUBERNETES_ADMIN_NATIVE_PATCH_ENABLED=false`, `KUBERNETES_ADMIN_PATCH_MAX_BODY_BYTES=65536`, `KUBERNETES_ADMIN_NATIVE_SCALE_ENABLED=false`, `KUBERNETES_ADMIN_NATIVE_RESTART_ENABLED=false`, `KUBERNETES_ADMIN_SCALE_MAX_REPLICAS=100`, `KUBERNETES_ADMIN_NATIVE_DELETE_ENABLED=false`, `KUBERNETES_ADMIN_DELETE_PROTECTED_NAMESPACES=...`, `KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED=false`, `KUBERNETES_ADMIN_NODE_DRAIN_EXECUTION_ENABLED=false`, `KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=false`, `KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED=false`, `KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED=false`, `KUBERNETES_ADMIN_EXEC_PROTECTED_NAMESPACES=...`, `KUBERNETES_ADMIN_EXEC_ALLOWED_COMMANDS=...`, `KUBERNETES_ADMIN_EXEC_DENIED_COMMANDS=...`, `KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=false`, `KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED=false`, `KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED=false`, `KUBERNETES_ADMIN_PORT_FORWARD_PROTECTED_NAMESPACES=...`, `KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS=`, `KUBERNETES_ADMIN_PORT_FORWARD_MAX_DURATION_SECONDS=900`, `KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF=`, `KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED=false`, `KUBERNETES_ADMIN_CLUSTER_TERMINAL_RECORDING_ENABLED=false`, `KUBERNETES_ADMIN_NODE_DEBUG_ENABLED=false`, `KUBERNETES_ADMIN_NODE_DEBUG_RECORDING_ENABLED=false`, `KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF=`, `KUBERNETES_ADMIN_INTERACTIVE_METADATA_RETENTION_DAYS=365`, `KUBERNETES_ADMIN_INTERACTIVE_TRANSCRIPT_RETENTION_DAYS=30`, `KUBERNETES_ADMIN_TRANSCRIPT_EVENT_MAX_CHARS=2000`, `KUBERNETES_ADMIN_TRANSCRIPT_EVENT_MAX_COUNT=2000` и `KUBERNETES_OPS_READY_FOR_SIDEBAR=false`; `KUBERNETES_ADMIN_NODE_DRAIN_EXECUTION_ENABLED` остаётся отдельным вторым ключом после node maintenance, потому что drain уже делает cordon plus `policy/v1` Eviction requests |
| Production evidence env refs | `.env.production.example` и Render common env group теперь явно объявляют `KUBERNETES_OPS_PRODUCTION_EVIDENCE_REF`, `KUBERNETES_OPS_IDENTITY_RUNTIME_EVIDENCE_REF`, `KUBERNETES_OPS_LIVE_PROVIDER_EVIDENCE_REF`, `KUBERNETES_OPS_READONLY_RBAC_EVIDENCE_REF`, `KUBERNETES_OPS_KUBERNETES_MCP_EVIDENCE_REF`, `KUBERNETES_OPS_PRODUCTION_ROLLBACK_EVIDENCE_REF`, `KUBERNETES_OPS_PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_REF`, `KUBERNETES_ADMIN_INTERACTIVE_LIVE_SMOKE_EVIDENCE_REF` и `KUBERNETES_ADMIN_INTERACTIVE_LIVE_SMOKE_REQUIRED=false`, чтобы production rollout видел все refs, которые проверяет `verify_kubernetes_ops_external_evidence_bundle` и sidebar release scope. |
| Production rollback/native verification refs | `release_scope`, `readiness`, `verify_kubernetes_ops_external_evidence_bundle` и `render_kubernetes_ops_release_handoff` теперь требуют в production отдельные evidence refs для rollback drill (`KUBERNETES_OPS_PRODUCTION_ROLLBACK_EVIDENCE_REF`) и native post-action verification (`KUBERNETES_OPS_PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_REF`). В local эти refs отображаются как optional и не блокируют разработку, но production-ready без них невозможен. |
| Admin Mode kill switch | `KUBERNETES_ADMIN_MODE_ENABLED=false` добавлен в settings, `.env.production.example` и Render env group: normal read-only Kubernetes cockpit остаётся доступным, но Admin read/write/break-glass policy становится false, новые Admin sessions возвращают `admin_mode_disabled`, а уже существующие active sessions блокируются до live provider/resource/metrics calls без удаления session/action данных. |
| Provider config | Admin-only create/read/update/delete/sync/probe endpoints для локальной provider-конфигурации; обычный пользователь с `kubernetes` видит только provider health/summary внутри overview без `base_url`, labels или secret refs |
| Access | Все endpoints закрыты `login_required` + `require_feature("kubernetes")`; staff без explicit feature получает 403; `kubernetes_ops.permissions` публикует текущую policy matrix: read-only inventory/log snapshots доступны explicit Kubernetes users, provider config/sync/probe и fallback deeplink audit доступны только staff + Kubernetes, Studio diagnosis требует `studio_pipelines`; Admin Mode policy fields (`can_admin_read`, `can_live_resource_get`, `can_view_full_yaml`, `can_view_secret_values`, `can_stream_logs`, `can_admin_write`, `can_dry_run_apply`, `can_break_glass`) отделены от safe cockpit; `can_view_secret_values` включается только при `kubernetes_secret_read` + `KUBERNETES_ADMIN_SECRET_READ_ENABLED=true` + Admin read access; `can_apply_yaml`, `can_patch`, `can_scale`, `can_restart`, `can_delete` включаются только при explicit write feature + соответствующих `KUBERNETES_ADMIN_NATIVE_*_ENABLED=true` flags; `can_exec` включается только при `kubernetes_break_glass` + `KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=true`; `can_port_forward` включается только при `kubernetes_break_glass` + `KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=true`; `can_node_maintenance` включается только при `kubernetes_break_glass` + `KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED=true`, а `can_node_drain` дополнительно требует `KUBERNETES_ADMIN_NODE_DRAIN_EXECUTION_ENABLED=true`; drain всё равно требует approved break-glass session, `node` scope, exact confirmation and reason; terminal readiness остаётся fail-closed до production stream/tunnel/recording controls |
| Admin Mode foundation | Добавлены `kubernetes_ops/admin_models.py`, `K8sAdminSession`, `K8sAdminAction`, `K8sAdminRecording`, `K8sAdminRecordingEvent`, migrations `0009_k8sadminsession_k8sadminaction`, `0010_k8sadminrecording` и `0011_k8sadminrecordingevent`, serializer/admin support и API `/api/kubernetes/admin/sessions/`, detail, `approve/`, `revoke/`, `close/`, `review/`, `restricted-context/`, `terminal/start/`, `terminal/stop/`, `node-debug/start/`, `node-debug/stop/`; read session активируется только при `kubernetes_admin_read`, write/break-glass стартуют как `pending_approval`, требуют `reason`, TTL и staff approval с `approval_ref`; active session можно закрыть штатно, с `closed_at` и audit, не превращая завершение работы в revoke; break-glass sessions получают `post_review_required=true` и после close/revoke/expire требуют staff post-review с outcome/summary/evidence ref; restricted context endpoint строит namespace-scoped ServiceAccount/Role/RoleBinding plan с TTL annotations, без apply/token/kubeconfig, и валидирует запрет ClusterRole, Secrets, nodes, attach, wildcard и base-resource writes; cluster terminal start валидирует approved break-glass + restricted context, пишет metadata-only `K8sAdminAction`/`K8sAdminRecording`/audit и централизованный recording policy с retention values, но возвращает `execution_blocked`; если transport flag включен, recording gate, provider `cluster_terminal_path_template` contract и production restricted evidence проверяются до action/audit/provider side effects; stop без live terminal возвращает `cluster_terminal_not_running` и audit; node debug start валидирует approved break-glass + node scope + node name/reason, пишет metadata-only `K8sAdminAction`/`K8sAdminRecording`/audit и централизованный recording policy с retention values, но возвращает `execution_blocked`; если debug transport flag включен, recording gate, provider `node_debug_path_template` contract и production restricted evidence проверяются до action/audit/provider side effects; stop без live debug возвращает `node_debug_not_running` и audit; session lifecycle пишет audit; privileged service paths дополнительно проверяют approved-session evidence (`approval_ref`, `approved_by`, `approved_at`) и не доверяют одному `status=active`; live write paths остаются fail-closed runtime-gated; exec/port-forward bridges проверяют break-glass/session/scope/policy, реальные provider stream/tunnel запускаются только за отдельными transport + recording opt-in флагами, а exec stream пишет bounded redacted stdin/stdout/stderr events без raw payload |
| Admin live read-only explorer | Добавлены backend endpoints `/api/kubernetes/admin/clusters/{cluster_id}/discovery/`, `resources/`, `resources/detail/`, `resources/describe/`, `yaml/`, `crds/`, `nodes/`, `resources/events/`, `logs/`, `watch/`: они требуют active Admin Mode session, ходят к Rancher через backend-held provider credentials, строят `/k8s/clusters/{id}/api...` / `/apis...` paths, поддерживают common resources + CRDs, редактируют Secret `data`/`stringData`/sensitive keys, sensitive strings вроде `password=...`/`token=...`, log lines и watch/event objects, пишут `K8sAdminAction` и audit metadata без raw YAML/log/resource/event/node content в audit; `nodes/` отдаёт WebTerm-native node summary: Ready/NotReady, roles, taints, unschedulable, capacity/allocatable, addresses и nodeInfo; resource list/get/YAML/detail/describe теперь добавляет WebTerm ownership/describe context по normalized Devtron apps, Fleet bundle labels/annotations, external owner refs и Rancher inventory; `resources/detail/` отдаёт один Freelens-like объект: sanitized resource, describe identity/health/shape summary, ownership и bounded Events; `resources/describe/` отдаёт live read-only describe summary + bounded Events + related Pods/ReplicaSets when the active session allows those scopes, while action/audit evidence stores only counts/flags/skipped reasons |
| Admin read-only metrics | Добавлен backend endpoint `/api/kubernetes/admin/clusters/{cluster_id}/metrics/?scope=nodes|pods&namespace=...&name=...`: он требует active Admin Mode session, читает `metrics.k8s.io/v1beta1` через Rancher proxy/backend-held credentials, нормализует CPU в millicores и memory в bytes, считает bounded totals/counts, блокирует all-namespace pod metrics без all-namespaces Admin session и пишет в `K8sAdminAction`/audit только counts/totals без raw metrics body |
| Admin action evidence | Добавлены `GET /api/kubernetes/admin/actions/`, `GET /api/kubernetes/admin/actions/{action_id}/`, `GET /api/kubernetes/admin/actions/{action_id}/report/` и `POST /api/kubernetes/admin/actions/{action_id}/review/`: владелец action/session видит свои sanitized `K8sAdminAction` rows, staff может смотреть все через `all=1`, фильтры поддерживают `session_id`, `cluster_id`, `verb`, `status`, `post_review_status`, `review_scan_limit`, `limit`; list отдаёт `review_summary`, чтобы быстро увидеть pending/completed/not_ready evidence queue; readiness отдаёт optional `admin_action_post_review` check с pending/completed/not_ready counts, pending URL и bounded pending-action preview; report возвращает sanitized action, session, linked `K8sAdminRecording` rows, bounded redacted `K8sAdminRecordingEvent` rows for exec evidence and bounded timeline из session lifecycle + audit events с matching `action_id`; review endpoint staff-only, требует `kubernetes_admin_write` для write actions или `kubernetes_break_glass` для break-glass actions, хранит sanitized outcome/summary/evidence; чужой обычный пользователь получает пустой список/404, а payloads повторно проходят sanitizer перед отдачей |
| Admin recording evidence | Добавлены `GET /api/kubernetes/admin/recordings/` и `GET /api/kubernetes/admin/recordings/{recording_id}/`: владелец recording/session/action видит свои sanitized recording rows, staff может смотреть все через `all=1`, фильтры поддерживают `session_id`, `action_id`, `cluster_id`, `operation`, `status`, `limit`; detail отдаёт bounded redacted events с `event_limit`, list не тащит event body; non-owner получает пустой список/404; `cleanup_interactive_recordings()` и команда `cleanup_kubernetes_admin_recordings` делают dry-run/apply retention cleanup: transcript TTL удаляет только event rows и помечает recording как cleaned, metadata TTL удаляет recording row вместе с events; readiness отдаёт optional check `admin_recording_retention` с cleanup командами и expired counts |
| Admin write preview/apply/workload actions | Добавлен безопасный endpoint `POST /api/kubernetes/admin/clusters/{cluster_id}/resources/schema-validate/`: он требует explicit `kubernetes_admin_write` и active approved write session, читает CRD `openAPIV3Schema` через Rancher proxy, проверяет bounded `required`/`type`/`enum`/number constraints, возвращает только validation summary/errors без raw manifest body и пишет metadata-only `K8sAdminAction`/audit как read-style schema validation, поэтому этот action не является dry-run proof; добавлен безопасный endpoint `POST /api/kubernetes/admin/clusters/{cluster_id}/resources/dry-run-apply/`: он требует explicit `kubernetes_admin_write` и active approved write session, делает Kubernetes server-side apply через Rancher proxy только с `dryRun=All`, возвращает sanitized submitted/server resource, top-level `diff_summary` и bounded path-level `diff.changes` для UI review, редактирует Secret body, пишет `K8sAdminAction` со статусом `dry_run` и audit metadata без raw manifest body/full diff changes; добавлен runtime-gated `POST /api/kubernetes/admin/clusters/{cluster_id}/resources/apply/`, который по умолчанию закрыт, а при `KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED=true` в обычном режиме требует active approved write session, `apply` verb, reason и свежий matching dry-run proof с keyed manifest fingerprint; emergency dry-run bypass существует только для active approved break-glass session при отдельном `KUBERNETES_ADMIN_BREAK_GLASS_APPLY_BYPASS_ENABLED=true` и пишет `dry_run_bypassed`/`break_glass`/`approval_ref` evidence; добавлен runtime-gated `/patch/`, который по умолчанию закрыт, а при `KUBERNETES_ADMIN_NATIVE_PATCH_ENABLED=true` требует active approved write session, `patch` verb, reason, namespace/kind scope, bounded patch body и metadata-only audit без raw patch body; добавлены runtime-gated `/scale/` и `/restart/`, которые по умолчанию закрыты и при включении требуют active approved write session, matching verb, reason, namespace/kind scope и metadata-only audit; добавлен runtime-gated `/delete/`, который по умолчанию закрыт, а при `KUBERNETES_ADMIN_NATIVE_DELETE_ENABLED=true` требует active approved write session, `delete` verb, exact typed confirmation, reason, namespace/kind scope, protected namespace/kind denylist и metadata-only audit; добавлены break-glass node maintenance endpoints `/nodes/cordon/`, `/nodes/uncordon/`, `/nodes/drain/`: по умолчанию закрыты, при `KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED=true` cordon/uncordon требуют approved break-glass session, `node` scope, matching verb и reason, then patch Node `spec.unschedulable`; drain требует exact confirmation and stays blocked as `node_drain_execution_disabled` until `KUBERNETES_ADMIN_NODE_DRAIN_EXECUTION_ENABLED=true`; when enabled it lists pods on the node, blocks before mutation on DaemonSet/emptyDir/unmanaged/pod-limit/truncated-list hazards, cordons the node, and posts Kubernetes `policy/v1` Eviction objects instead of deleting pods so PDBs remain authoritative; общий `admin_write_approval` helper теперь до provider/action side effects требует `approval_ref`, `approved_by` и `approved_at` для schema-validate/dry-run/apply/patch/scale/restart/delete/exec/port-forward/node maintenance; prod-cluster/prod-like namespace write miss возвращает `production_approval_required`; `admin_owner_guard` теперь блокирует прямой apply/patch/scale/restart/delete для Devtron/Fleet/external-owned ресурсов до provider call и возвращает `owner_direct_mutation_blocked` с `change_path`; pod exec foundation добавлен как fail-closed WebSocket bridge с break-glass/session/command guard и opt-in provider stdout/stderr/status stream за отдельными `KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED` + `KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED`; port-forward foundation добавлен как fail-closed WebSocket bridge с break-glass/session/target allowlist guard и opt-in provider tunnel за отдельными `KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED` + `KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED` |
| Admin stream bridge | Добавлены `kubernetes_ops.consumers`, `kubernetes_ops.routing`, `kubernetes_ops.services.admin_streams`, `kubernetes_ops.services.admin_exec`, `kubernetes_ops.services.admin_recording`, `kubernetes_ops.services.admin_interactive_transport_readiness` и `kubernetes_ops.services.admin_port_forward`: WebSocket routes для Admin logs/watch требуют authenticated user + active Admin Mode session, отправляют `stream_started`, bounded `log_batch`/`watch_batch`, `stream_heartbeat`, `stream_stopped`, поддерживают bounded `follow=1` polling mode с `max_batches`, `poll_interval_seconds`, `idle_timeout_seconds`, пишут `k8s.admin_stream.*` audit lifecycle с duration/count/source/target metadata, закрывают cancel/client disconnect как stop-event с `close_reason=client_disconnect`, не сохраняют raw log lines или resource body и reject-ят expired session до provider call/start audit; `ws/kubernetes/admin/exec/{session_id}/` проверяет native exec flag, active approved break-glass session evidence, `exec` verb, namespace/kind scope, protected namespace denylist, reason and command allow/deny policy, пишет `K8sAdminAction`/`K8sAdminRecording`/audit и без отдельного streaming flag возвращает `exec_blocked`; при `KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED=true` + `provider_stream=1` дополнительно требует `KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED=true` до provider/action side effects, а в production release mode ещё требует `KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF` до provider/action side effects; при успешных gates отдаёт redacted stdout/stderr/status frames и хранит recording policy + counters/status/exit_code in action/recording evidence плюс bounded redacted stdin/stdout/stderr events в `K8sAdminRecordingEvent`; `ws/kubernetes/admin/port-forward/{session_id}/` проверяет native port-forward flag, active approved break-glass session evidence, `port_forward` verb, Pod/Service target, namespace/kind scope, protected namespace denylist, explicit target allowlist, bounded duration and ports, пишет metadata-only `K8sAdminAction`/`K8sAdminRecording`/audit и без отдельного tunnel flag возвращает `port_forward_blocked`; при `KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED=true` + `provider_stream=1` дополнительно требует `KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED=true` до provider/action side effects, а в production release mode ещё требует `KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF`, `KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF`, exact non-wildcard allowlist, default protected namespace coverage и <=900s duration до provider/action side effects; при успешных gates открывает provider tunnel, передает data frames в base64 и хранит только recording policy + bytes/status/close metadata без payload |
| Admin Mode frontend | Добавлен rough WebTerm-native route `/kubernetes/admin`: feature-gated экран создаёт read session, выбирает cluster/kind/namespace/name, запускает Discovery/CRDs/List/YAML, Logs snapshot для `Kind=Pod` и bounded Watch preview, показывает result table + JSON/YAML panel, policy badges, owner column, ownership summary, logs snapshot/watch preview panel и path/policy panel для Devtron/Fleet/Rancher owners; live browser smoke на `http://127.0.0.1:8080/kubernetes/admin` под `codex-k8s-smoke` создал active read session и выполнил `List` через `local-rancher-real` без вывода kubeconfig, `RANCHER_TOKEN`, Bearer token или JWT-looking token |
| CSP/CORS/CSRF review | `kubernetes_ops.services.security_review` проверяет CSRF middleware, отсутствие wildcard trusted origins, bounded credentialed CORS, clickjacking middleware, secure-cookie posture for production, and native/deeplink no-iframe mode; `tests/test_kubernetes_ops_security_review.py` enforce-ит CSRF для unsafe Kubernetes endpoints |
| Terminal/exec threat model | `kubernetes_ops.services.terminal_safety` публикует fail-closed report: native exec/attach/streaming/port-forward/cluster terminal/node debug выключены по умолчанию; отдельные flags `KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED`, `KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED`, `KUBERNETES_ADMIN_CLUSTER_TERMINAL_RECORDING_ENABLED`, `KUBERNETES_ADMIN_NODE_DEBUG_RECORDING_ENABLED`, `KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF`, `KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF`, retention values `KUBERNETES_ADMIN_INTERACTIVE_METADATA_RETENTION_DAYS`/`KUBERNETES_ADMIN_INTERACTIVE_TRANSCRIPT_RETENTION_DAYS`, transcript event bounds и `cleanup_kubernetes_admin_recordings --apply` команда видны в policy; readiness отдаёт optional `admin_interactive_transport` report, который в production блокирует enabled exec stream/port-forward tunnel/terminal/node debug без recording gate и restricted credential evidence, а production port-forward дополнительно блокирует без network-policy evidence и exact non-wildcard allowlist; если `KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=true`/`KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=true` и policy даёт `can_exec`/`can_port_forward`, readiness становится `missing`, пока не закрыты production controls: separate permission, approval, TTL, session recording/transcript retention, restricted kube context/network policy, audit lifecycle and break-glass review |
| Operator/DR docs | `docs/architecture/KUBERNETES_OPS_OPERATIONS.md` содержит production configuration checklist, readiness gates, provider outage DR, sync worker recovery, token rotation, audit retention, terminal policy, rollback/disablement and daily operator checklist; `kubernetes_ops.services.operator_docs` проверяет обязательные разделы и отдаёт readiness check `operator_docs` |
| Secret safety | Provider API отдаёт `has_secret_ref`/`secret_storage`, но не отдаёт `secret_ref` или raw token/kubeconfig; config API принимает external secret refs (`env:`, `vault://`, etc.) или `secret_value`, который сразу сохраняется encrypted-at-rest в `ManagedSecret` |
| Rotation | Staff может отправить новый `secret_value` через provider update; backend ротирует managed token, audit пишет только metadata |
| Audit retention | `cleanup_kubernetes_ops_audit` применяет retention для `K8sAuditEvent`: dry-run по умолчанию, `--apply` для удаления, срок задаётся `KUBERNETES_OPS_AUDIT_RETENTION_DAYS` |
| Access model | `kubernetes_ops.services.access_model` фиксирует проверяемый Keycloak/OIDC -> WebTerm -> Rancher/Devtron mapping, read-only service account contract и readiness gate `access_model`; `kubernetes_ops.services.identity_runtime` добавляет production-only gate `identity_runtime` и поле `webterm_login_gateway`: в local режиме он не блокирует разработку, а в production принимает безопасный WebTerm gateway через Domain SSO/OIDC или LDAP, при этом normal users не логинятся отдельно в Rancher/Fleet/Devtron, browser не получает provider credentials, а доступ идет через WebTerm feature permissions/admin sessions и backend-held service credentials; `render_kubernetes_ops_readonly_rbac` генерирует/валидирует read-only ServiceAccount/ClusterRole/ClusterRoleBinding manifest; `verify_kubernetes_ops_readonly_rbac_live.py --apply` проверяет live `kubectl auth can-i` allow/deny matrix; native mutations/exec остаются `false` |
| Freshness gates | Provider/resource serializers отдают `sync_status`, `is_stale`, `sync_age_seconds`; readiness имеет required `provider_health`; overview summary считает `stale` и `provider_issues`; stale threshold задаётся `KUBERNETES_OPS_STALE_AFTER_SECONDS`; admin-only provider probe даёт live endpoint evidence перед production enablement |
| Studio bridge | `actions/diagnose/` создаёт только `PipelineDraftSession`: graph `manual -> agent/mcp_call(kubernetes_describe_workload READ_ONLY) -> agent/llm_query -> output/report`; `Pipeline` и `PipelineRun` не создаются, rollout/restart tools отсутствуют |
| Studio safety | `studio/skills/kubernetes-safety/SKILL.md` добавлен как read-only-first runtime policy; diagnosis draft attach-ит `skill_slugs=["kubernetes-safety"]` |
| Studio readiness | `/api/kubernetes/readiness/` теперь отдаёт optional check `studio_automation`: проверяет `studio_pipelines`, `studio_mcp`, наличие `kubernetes-safety` и tested owned Kubernetes MCP binding; команда `ensure_kubernetes_ops_studio_binding` создаёт local/Docker binding и проверяет tool `kubernetes_describe_workload`; статус может быть `ready`, `missing` или `manual`, но не блокирует read-only cockpit |
| Release evidence | `verify_kubernetes_ops_preflight` was refreshed at `2026-07-02T19:28:50+05:00` with `status=ready`, `failed=[]`, `14` command results and `546 passed + 10 subtests`; `verify_kubernetes_ops_external_evidence_bundle` was refreshed at `2026-07-02T11:49:43Z` with `artifact_ready_count=6/6`, `missing_required_ref_count=0` in local mode and `local_indicator_count=18`; `verify_kubernetes_ops_release` was refreshed at `2026-07-02T19:57:54+05:00` with `production_ready=false`, `ready_for_sidebar=false`, blockers `readiness:sidebar_release_scope=missing` and `release_scope:local`, `artifact_safety=ready`, `preflight=ready`, root `completion_audit` stored alongside `release_summary.completion_audit`, root `production_execution_plan` stored with `status=blocked`, `recommended_next=select_production_environment`, `blocked_until_count=7`, `phase_count=4`, and `command_count=10`, `definition_of_done=ready 13/13`, `identity_runtime=ready` with `webterm_login_gateway.mode=local`, `normal_user_surface=ready`, `secret_read_controls=ready` with Secret list metadata-only proof, `provider_secret_lifecycle=ready` with managed provider token storage/rotation/cleanup proof, `audit_redaction=ready` with fail-safe audit payload redaction plus credentialed URL sanitization proof, and `frontend_response_credential_scan.status=ready` across `31` surfaces including Helm release ownership, Devtron AppOps delivery, cluster/workload/network diagnostics summary payloads, action summary queue payloads, staff release readiness summary payloads with `production_evidence_checklist.gap_summary`/`operator_command_plan.blocking_summary`, and capability matrix payloads; Admin live YAML/JSON view includes a safe `manifest` contract without server-side YAML/raw provider body storage; `interactive_live_smoke` proves `4` simulated provider openers plus `4` production live transport contracts for exec, port-forward, cluster terminal and node debug; `interactive_production_controls` proves `4` control contracts for restricted credentials, recording policy, port-forward network policy and provider path contracts without opening live streams; `production_action_evidence` proves rollback action classes `5`, native verification checks `10`, action class contracts `5` and blocked action classes `11`; production enablement still requires non-local Rancher/Fleet/Devtron/MCP/RBAC/SSO-or-LDAP/rollback/native-verification evidence refs and `KUBERNETES_OPS_READY_FOR_SIDEBAR=true` only after `production_ready=true`. |
| WebTerm-only normal-user release proof | `verify_kubernetes_ops_release` теперь добавляет rollback-only `normal_user_surface` evidence: temporary reader/staff/provider rows доказывают, что normal users получают только WebTerm-native payloads, не видят provider config/base URLs/external Rancher/Fleet/Devtron links, cluster/app/workload/pod/Fleet/network/Helm/Devtron-detail/diagnostics-summary public payloads redact token-like labels/metadata and sensitive string values, provider `secret_ref` не сериализуется в reader/staff frontend payloads, rollback-only token/kubeconfig-like marker values отсутствуют в reader/staff frontend surfaces, normal users не могут писать fallback deeplink audit, а staff/admin fallback links sanitized without query/token/userinfo/sensitive link keys; failure добавляет blocker `normal_user_surface:<status>` и release summary next step. |
| Capability matrix | `GET /api/kubernetes/capabilities/` is a WebTerm-native read-only endpoint for frontend gating: it maps current WebTerm feature grants and Kubernetes runtime flags into explicit modes/workflows (`safe_cockpit`, live explorer, logs, dry-run/apply/patch/scale/restart/delete, exec, port-forward, node maintenance, terminal/debug and secret values), returns availability/requestability/blocked reasons and session/runtime requirements, and does not call Rancher/Fleet/Devtron live providers. |
| Release handoff | `render_kubernetes_ops_release_handoff` reads `artifacts/kubernetes_ops_release_evidence.json` and writes `artifacts/kubernetes_ops_release_handoff.md`/JSON with status, blockers, next steps, required commands, production env flags, missing production refs, external evidence requirements, safety guards, Completion Audit and Release Proofs; current handoff JSON/Markdown was regenerated at `2026-07-02T19:57:47+05:00` and remains `status=blocked`, `can_enable_sidebar=false`, blockers `readiness:sidebar_release_scope=missing` and `release_scope:local`; Completion Audit says core backend and runtime readiness are complete while production evidence and sidebar enablement are incomplete; `production_execution_plan` is included with `status=blocked`, `recommended_next=select_production_environment`, `blocked_until_count=7`, `phase_count=4`, and `command_count=10`, so operators get a deterministic production sequence instead of a vague release note; Release Proofs include `definition_of_done=ready` with `ready=13/13`, `normal_user_surface=ready` with `credential_scan=ready`, `surfaces=31`, `secret_ref_serialized=false`, `forbidden_values=false`, `external_evidence_bundle=ready` with `artifacts=6/6`, `production_action_evidence=ready` with `rollback_actions=5`, `native_checks=10`, `blocked_actions=11`, `blocked_contract=true`, `secret_read_controls=ready`, `provider_secret_lifecycle=ready`, `audit_redaction=ready`, `interactive_live_smoke=ready`, `interactive_production_controls=ready`, and `action_controls=ready`; required production env flags include production evidence, identity runtime, live provider, read-only RBAC, Kubernetes MCP, rollback drill, native verification, restricted credential, port-forward network policy and interactive live-smoke evidence refs. |
| Latest release refresh | Full local preflight was regenerated at `2026-07-02T19:28:50+05:00` with `status=ready`, `failed=[]`, and `546 passed + 10 subtests`; `verify_kubernetes_ops_release` regenerated `artifacts/kubernetes_ops_release_evidence.json` at `2026-07-02T19:57:54+05:00` with `production_ready=false`, `ready_for_sidebar=false`, blockers `readiness:sidebar_release_scope=missing` and `release_scope:local`, `artifact_safety=ready`, `preflight=ready`, root `completion_audit` present, root `production_execution_plan` present, `definition_of_done_status=ready`, `definition_of_done_ready=13/13`, `production_restart_template_status=ready`, `secret_read_controls.list_metadata_only=True`, `provider_lifecycle_status=ready`, `provider_secret_lifecycle.rotation_supported=True`, `audit_redaction_status=ready`, and `frontend_payload_scan_status=ready` with `surfaces_checked=31`; handoff JSON/Markdown were regenerated at `2026-07-02T19:57:47+05:00` and remain `status=blocked`, `can_enable_sidebar=false` with the same local-only blockers plus a machine-readable `production_execution_plan`. Earlier supporting artifacts remain ready: `interactive_live_smoke=ready live_contracts=4`, `interactive_production_controls=ready control_contracts=4`, `production_action_evidence=ready rollback_actions=5/native_checks=10/blocked_actions=11`, and `external_evidence_bundle=ready artifacts=6/6`. |
| Latest backend resource-registry refresh | `admin_resource_registry` split the common resource/kubectl-alias registry out of `admin_resources.py` and added PVC/PV, ServiceAccount, Endpoints, LimitRange, ResourceQuota, ReplicaSet, HPA, PDB, NetworkPolicy, EndpointSlice, StorageClass, RBAC roles/bindings and CRD aliases. Focused checks passed: `python -m py_compile kubernetes_ops/services/admin_resource_registry.py kubernetes_ops/services/admin_resources.py tests/test_kubernetes_ops_admin_resource_registry.py`, `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_resource_registry.py tests/test_kubernetes_ops_admin_resources.py -q --reuse-db` -> `15 passed`, `docker compose exec -T backend sh -lc "python -m pytest tests/test_kubernetes_ops_admin_resource_*.py tests/test_kubernetes_ops_admin_resources.py -q --reuse-db"` -> `27 passed`, `manage.py check` -> no issues, `makemigrations kubernetes_ops --check --dry-run` -> no changes, `scripts/check_architecture_sizes.py --strict-new` -> green. Latest full preflight/release refresh is `2026-07-02T19:28:50+05:00` / `2026-07-02T19:57:54+05:00`: `546 passed + 10 subtests`, `production_ready=false`, `ready_for_sidebar=false`, blockers `readiness:sidebar_release_scope=missing` and `release_scope:local`; handoff remains `status=blocked`, `can_enable_sidebar=false`. |
| Latest CRD discovery refresh | Admin discovery now combines core API discovery, grouped API discovery, static common resources and a safe CRD-backed resource catalog. `crd_resources` exposes only group/version/kind/plural/scope/aliases metadata, never raw CRD schema, annotations or labels; if the active Admin session cannot read CRDs, discovery still returns `success=true` with `crd_resources.status=unavailable`. Focused checks passed: `python -m py_compile kubernetes_ops/services/admin_crd_discovery.py kubernetes_ops/services/admin_resources.py tests/test_kubernetes_ops_admin_resource_discovery.py`, `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_resource_discovery.py tests/test_kubernetes_ops_admin_resource_registry.py tests/test_kubernetes_ops_admin_resources.py -q --reuse-db` -> `17 passed`, `docker compose exec -T backend sh -lc "python -m pytest tests/test_kubernetes_ops_admin_resource_*.py tests/test_kubernetes_ops_admin_resources.py -q --reuse-db"` -> `29 passed`, `manage.py check` -> no issues, `makemigrations kubernetes_ops --check --dry-run` -> no changes, `scripts/check_architecture_sizes.py --strict-new` -> green. |
| Latest API resource discovery refresh | Admin discovery now also returns `api_resources`: a bounded safe catalog from Kubernetes `APIResourceList` for `/api/v1` and `/apis/{group}/{version}`. It includes api version, kind, plural resource, namespaced flag, verbs, short names, categories and singular name; it skips subresources and never serializes raw group-version discovery bodies. If one group/version fails, the catalog is `partial` with bounded failed ids instead of breaking the whole discovery response. Focused checks passed: `python -m py_compile kubernetes_ops/services/admin_api_discovery.py kubernetes_ops/services/admin_resources.py tests/test_kubernetes_ops_admin_resource_discovery.py`, `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_resource_discovery.py tests/test_kubernetes_ops_admin_resources.py -q --reuse-db` -> `14 passed`, `docker compose exec -T backend sh -lc "python -m pytest tests/test_kubernetes_ops_admin_resource_*.py tests/test_kubernetes_ops_admin_resources.py -q --reuse-db"` -> `29 passed`, custom-resource/discovery subset -> `4 passed`, `manage.py check` -> no issues, `makemigrations kubernetes_ops --check --dry-run` -> no changes, `scripts/check_architecture_sizes.py --strict-new` -> green. |
| Latest merged resource catalog refresh | Admin discovery now includes `resource_catalog`, a frontend-ready merged picker contract over static common resources, Kubernetes `api_resources` and CRD-backed `crd_resources`. Entries carry stable id, exact query fields (`api_version`, `kind`, `resource`), namespaced/scope, verbs, short names, categories, source list, `cluster_available`, `custom`, `ui_group`, `safe_read_actions` and `has_mutating_verbs`; common/API duplicates and API/CRD duplicates are deduped. The catalog also exposes bounded `counts` and `groups` for Workloads, Network, Config, Storage, Security, Policy, Cluster, Custom resources and Other, and action evidence stores only catalog item/group/custom counts. This gives the frontend enough backend truth to render a Freelens-like picker without raw provider bodies. Latest focused checks passed: `python -m py_compile kubernetes_ops/services/admin_resource_catalog.py kubernetes_ops/services/admin_resources.py tests/test_kubernetes_ops_admin_resource_discovery.py`, `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_resource_discovery.py tests/test_kubernetes_ops_admin_resources.py -q --reuse-db` -> `14 passed`, `scripts/check_architecture_sizes.py --strict-new` -> green. |
| Latest custom-resource path refresh | Admin read endpoints now accept optional `resource` from CRD discovery, so custom resources use the exact CRD plural instead of guessed kind pluralization. This applies to list/get, YAML, detail, live describe, resource events, REST watch preview, WebSocket watch snapshot/follow and provider-native continuous watch. Focused checks passed: `python -m py_compile kubernetes_ops/services/admin_resources.py kubernetes_ops/services/admin_resource_detail.py kubernetes_ops/services/admin_resource_describe.py kubernetes_ops/services/admin_resource_events.py kubernetes_ops/services/admin_watch.py kubernetes_ops/admin_resource_views.py kubernetes_ops/admin_watch_views.py kubernetes_ops/services/admin_streams.py kubernetes_ops/consumers.py kubernetes_ops/continuous_watch_streams.py tests/test_kubernetes_ops_admin_custom_resources.py`, `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_custom_resources.py tests/test_kubernetes_ops_admin_resource_discovery.py tests/test_kubernetes_ops_admin_resource_registry.py tests/test_kubernetes_ops_admin_resources.py -q --reuse-db` -> `19 passed`, extended admin resource/watch/stream set -> `55 passed`, `manage.py check` -> no issues, `makemigrations kubernetes_ops --check --dry-run` -> no changes, `scripts/check_architecture_sizes.py --strict-new` -> green. |
| Latest resource summary refresh | Admin list/get/detail responses now include safe resource `summary` payloads for table rows and compact detail headers. The summary is computed after resource sanitizer and includes identity, creation timestamp, generation/resourceVersion, owner references, phase/reason, ready state, bounded condition rows and condition aggregate, replica counters, container count/names/init-count/images/restarts, Service ports, Node readiness/roles, workload selector key/strategy/observed-generation summary, storage summary for PVC/PV/StorageClass, Ingress class/host/rule/TLS/backend summary, ConfigMap/Secret metadata key counts, Job/CronJob batch state, HPA target/replica/metric summary, PDB health/disruption summary, NetworkPolicy selector/type/rule counts, RBAC rule/binding risk counters, Endpoints/EndpointSlice readiness and port counts, ResourceQuota/LimitRange key/value summaries, ServiceAccount secret-ref counts without secret names, and bounded redacted metadata/spec/status key lists without exposing raw provider bodies or sensitive strings. Type-specific summary builders now live in `admin_resource_type_summary.py`, keeping `admin_resource_summary.py` below the architecture guard limit while preserving the same response contract. Resource sanitizer depth is now bounded at 10 so normal nested Kubernetes fields such as Ingress backend service names survive redaction while deeper payloads still truncate. Focused checks passed: `python -m py_compile kubernetes_ops/services/admin_resource_sanitizer.py kubernetes_ops/services/admin_resource_summary.py kubernetes_ops/services/admin_resource_type_summary.py tests/test_kubernetes_ops_admin_resource_summary.py tests/test_kubernetes_ops_admin_resources.py tests/test_kubernetes_ops_admin_resource_detail.py tests/test_kubernetes_ops_admin_custom_resources.py`, `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_resource_summary.py tests/test_kubernetes_ops_admin_resources.py tests/test_kubernetes_ops_admin_resource_detail.py tests/test_kubernetes_ops_admin_custom_resources.py -q --reuse-db` -> `22 passed`, extended admin resource/custom set -> `35 passed`, `manage.py check` -> no issues, `makemigrations kubernetes_ops --check --dry-run` -> no changes, `scripts/check_architecture_sizes.py --strict-new` -> green. |
| Frontend API | `frontend/src/api/kubernetes.ts`, `frontend/src/api/kubernetes-admin.ts`, `frontend/src/api/kubernetes-admin-discovery.ts`, `frontend/src/api/kubernetes-admin-nodes.ts`, `frontend/src/api/kubernetes-admin-node-maintenance.ts`, `frontend/src/api/kubernetes-admin-actions.ts` и `frontend/src/api/kubernetes-actions.ts` с typed client functions, Admin Mode session/resource/resource detail/node summary/node maintenance/ownership/logs/watch/schema-validate/dry-run-apply/apply/patch/scale/restart/delete types, Admin discovery `api_resources`/`crd_resources`/`resource_catalog` types, exact CRD plural `resource` query support for list/YAML/detail/watch, Admin logs/watch WebSocket URL helpers включая bounded follow params, exec and port-forward WebSocket URL helpers for the fail-closed bridges, action request list/status/report/timeline/external approval/external verification types и export через `@/api` |
| Frontend pages | `KubernetesPage` теперь operator-facing: summary cards, freshness warnings, clusters, degraded workloads/apps, Devtron apps и Fleet rollouts без provider setup/readiness internals; главный статус говорит `Только просмотр`, а не release/readiness gate; provider/source/gate/sync-worker wording убран с основного экрана; старый неиспользуемый frontend roadmap с ложными `missing` для Rancher/Fleet/Devtron sync удалён из shared Kubernetes sections; `AppRow` больше не сжимает имя сервиса кнопками/бейджами: имя идёт отдельной строкой, а действия расположены ниже, что зафиксировано RU visual snapshots; блок `Требует внимания` берёт реальные degraded Rancher workloads, не считает Devtron `unknown` health проблемой и умеет создать `Запрос restart` approval request для workload без execution; `KubernetesActionRequestPanel` после создания заявки читает `GET /api/kubernetes/actions/{id}/report/` и показывает bounded audit timeline (`Заявка создана`, external approve/verify/reject events) + sanitized report payload без execution button; staff-only блок `Внешний lifecycle` записывает external approval (`approval_ref`, summary) и external verification (outcome, summary, external evidence ref) через backend endpoints, но не показывает native execute controls; `SettingsKubernetesPage` в `/settings/kubernetes` содержит admin-only provider setup/sync/probe, sync worker state и readiness gate; sidebar item управляется backend `ready_for_sidebar`; Devtron app row имеет action `Диагноз` для создания Studio draft; добавлены native read-only routes `/kubernetes/clusters/:clusterId`, `/kubernetes/fleet`, `/kubernetes/devtron`; cluster detail показывает native workload kind, ready/desired, Pods runtime inventory, bounded read-only pod logs snapshot panel, Services/Ingress inventory, read-only describe panel, native event namespace/count и `Запрос restart` approval request для deployment/statefulset/daemonset без execution button; provider/cluster/app/Fleet external link rows now depend on backend `external_links_policy`: normal users receive no external URLs, staff/admin receive audited sanitized fallback links; runtime smoke на `http://127.0.0.1:8080/kubernetes` после frontend/nginx restart доказал отсутствие `Настройка провайдеров`, `Readiness gate`, `Sync worker`, `Kubernetes beta`, screenshot: `artifacts/kubernetes-runtime-8080-operator.png`; action report smoke доказал timeline на `http://127.0.0.1:8080/kubernetes`, screenshot: `artifacts/kubernetes-action-report-timeline-8080.png`; external lifecycle smoke доказал create -> approve -> verify без Execute, screenshot: `artifacts/kubernetes-external-lifecycle-8080.png` |
| Settings release gate | `SettingsKubernetesPage` дополнительно показывает admin-only `Production release gate`: проверки `identity_runtime`/`sidebar_release_scope`/`release_evidence_artifact`, команды `verify_kubernetes_ops_preflight`, `verify_kubernetes_ops_release` и production env flags `KUBERNETES_OPS_RELEASE_ENVIRONMENT`, `KUBERNETES_OPS_PRODUCTION_APPROVAL_REF`, `KUBERNETES_OPS_READY_FOR_SIDEBAR`; release-gate/status badges теперь используют русский plural label (`1 блокер`, `2 блокера`, `5 блокеров`) вместо mixed `blockers`; unit test проверяет, что при наличии backend release checks не показывается placeholder `Release gate checks ещё не пришли`; live browser smoke на `http://127.0.0.1:8080/settings/kubernetes` сохранил screenshot `artifacts/kubernetes-settings-release-gate-8080.png` |
| Frontend e2e evidence | readiness check `frontend_e2e` проверяет наличие Kubernetes visual tests и snapshot artifacts для `/settings/kubernetes`, empty, healthy и degraded states; Kubernetes visual tests теперь запускают RU locale для `/kubernetes` и `/settings/kubernetes`; visual fixture содержит production release-gate checks `identity_runtime`, `release_evidence_artifact`, `sidebar_release_scope`, поэтому Settings snapshot показывает настоящий sidebar blocker вместо placeholder `Release gate checks ещё не пришли`; latest Playwright subset: `npm run test:e2e:visual -- --grep "kubernetes"` -> 4 passed |
| Demo/offline | Kubernetes demo fallback вынесен в `api-demo-kubernetes.ts`; он возвращает safe not-configured Kubernetes overview, demo Admin Mode resource ownership, demo Admin logs snapshot и demo Watch preview, чтобы rough explorer в demo/offline режиме показывал тот же owner/path/log/watch policy смысл; локальный `mcp-demo` exposes read-only `kubernetes_describe_workload` для Studio diagnosis smoke |
| Tests | Backend API tests including diagnosis draft, provider sync/worker/action request tests, Admin Mode session/resource/logs/watch/stream/follow/exec/port-forward foundation tests, release evidence/preflight/scope, Studio diagnosis rollback proof, Kubernetes overview/detail page tests including diagnosis and restart approval actions, settings release-gate UI, visual snapshots for settings/empty/healthy/degraded, frontend build, live browser smoke и architecture guard проходят; latest release evidence/Admin Mode safety check: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_release_evidence.py tests/test_kubernetes_ops_release_admin_mode_safety.py tests/test_kubernetes_ops_release_evidence_summary.py tests/test_kubernetes_ops_release_handoff.py tests/test_kubernetes_ops_release_preflight.py -q --create-db` -> `20 passed`; latest Admin Mode approved-session/write/break-glass guard check: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_dry_run.py tests/test_kubernetes_ops_admin_apply.py tests/test_kubernetes_ops_admin_patch.py tests/test_kubernetes_ops_admin_workload_actions.py tests/test_kubernetes_ops_admin_delete.py tests/test_kubernetes_ops_admin_exec.py tests/test_kubernetes_ops_admin_port_forward.py tests/test_kubernetes_ops_admin_production_approval.py -q --create-db` -> `42 passed`; latest Admin Mode production-approval/write guard check: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_production_approval.py tests/test_kubernetes_ops_admin_apply.py tests/test_kubernetes_ops_admin_patch.py tests/test_kubernetes_ops_admin_workload_actions.py tests/test_kubernetes_ops_admin_delete.py tests/test_kubernetes_ops_admin_owner_guard.py -q --create-db` -> `26 passed`; latest Admin Mode backend safety/write/stream/exec/port-forward check: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_port_forward.py tests/test_kubernetes_ops_admin_exec.py tests/test_kubernetes_ops_admin_streams.py tests/test_kubernetes_ops_terminal_safety.py tests/test_kubernetes_ops_permission_matrix.py tests/test_kubernetes_ops_admin_delete.py tests/test_kubernetes_ops_admin_patch.py tests/test_kubernetes_ops_admin_workload_actions.py tests/test_kubernetes_ops_admin_apply.py tests/test_kubernetes_ops_admin_dry_run.py tests/test_kubernetes_ops_admin_sessions.py -q --create-db` -> `69 passed`; latest interactive recording gate check: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_exec_stream_websocket.py tests/test_kubernetes_ops_admin_port_forward_tunnel_websocket.py tests/test_kubernetes_ops_admin_exec.py tests/test_kubernetes_ops_admin_port_forward.py tests/test_kubernetes_ops_admin_node_debug.py tests/test_kubernetes_ops_admin_terminal.py tests/test_kubernetes_ops_terminal_safety.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db` -> `60 passed`; latest durable recording evidence check: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_exec.py tests/test_kubernetes_ops_admin_port_forward.py tests/test_kubernetes_ops_admin_exec_stream_websocket.py tests/test_kubernetes_ops_admin_port_forward_tunnel_websocket.py tests/test_kubernetes_ops_admin_terminal.py tests/test_kubernetes_ops_admin_node_debug.py tests/test_kubernetes_ops_admin_actions.py -q --create-db` -> `42 passed`; latest Admin Mode frontend check: `npm test -- --run src/pages/KubernetesAdminPage.test.tsx src/pages/KubernetesPage.test.tsx src/pages/KubernetesInventoryPages.test.tsx` -> 3 files / 11 tests passed; latest architecture/system checks: `manage.py check` -> no issues, `makemigrations --check --dry-run` -> no changes, `scripts/check_architecture_sizes.py --strict-new` -> success; latest release/preflight/handoff/operator docs check: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_release_preflight.py tests/test_kubernetes_ops_release_handoff.py tests/test_kubernetes_ops_operator_docs.py -q --create-db` -> `11 passed`; previous Docker backend preflight run: `verify_kubernetes_ops_preflight` -> `142 passed`, `status=ready`, `failed=[]`; latest targeted Studio/release check: `pytest tests/test_kubernetes_ops_release_evidence.py tests/test_kubernetes_ops_release_evidence_summary.py tests/test_kubernetes_ops_release_studio_diagnosis.py tests/test_kubernetes_ops_studio_drafts.py -q` -> `15 passed`; latest targeted frontend check: `npm test -- --run src/pages/settings/SettingsKubernetesPage.test.tsx src/pages/KubernetesPage.test.tsx src/pages/KubernetesInventoryPages.test.tsx` -> 3 files / 11 tests passed; latest visual check: `npm run test:e2e:visual -- --grep "kubernetes"` -> 4 passed; latest frontend production build: `npm run build` -> passed; Docker `frontend`, `backend`, `kubernetes-ops-sync` and `nginx` were healthy after restart |
| Skill validation | `python manage.py validate_skills kubernetes-safety` проходит без warning/error; полный `python manage.py validate_skills` теперь проходит с `0 error(s)`; оставшиеся старые skill issues являются warning-only debt |

Latest focused Admin node view evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_nodes.py tests/test_kubernetes_ops_admin_resources.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db` -> `32 passed`; `manage.py check` -> no issues; `makemigrations --check --dry-run` -> no changes; `scripts/check_architecture_sizes.py --strict-new` -> success; `npm test -- --run src/pages/KubernetesAdminPage.test.tsx` from `frontend/` -> 1 file / 3 tests passed.

Latest focused Admin metrics evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_metrics.py tests/test_kubernetes_ops_admin_nodes.py tests/test_kubernetes_ops_admin_resource_detail.py tests/test_kubernetes_ops_permission_matrix.py -q --reuse-db` -> `31 passed`; `manage.py check` -> no issues; `makemigrations kubernetes_ops core_ui --check --dry-run` -> no changes; `scripts/check_architecture_sizes.py --strict-new` -> success; `py_compile` for `kubernetes_ops/services/admin_metrics.py`, Admin resource views/routes and the metrics tests -> success.

Latest focused Admin Mode disablement evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_permission_matrix.py tests/test_kubernetes_ops_admin_sessions.py tests/test_kubernetes_ops_admin_metrics.py tests/test_production_worker_topology.py -q --reuse-db` -> `48 passed`; `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_restricted_context.py tests/test_kubernetes_ops_admin_dry_run.py tests/test_kubernetes_ops_admin_apply.py tests/test_kubernetes_ops_admin_exec.py tests/test_kubernetes_ops_admin_port_forward.py tests/test_kubernetes_ops_admin_metrics.py tests/test_kubernetes_ops_permission_matrix.py -q --reuse-db` -> `62 passed`; `manage.py check` -> no issues; `makemigrations kubernetes_ops core_ui --check --dry-run` -> no changes; `scripts/check_architecture_sizes.py --strict-new` -> success; `py_compile` for the policy/session/resource/settings/tests touched by `KUBERNETES_ADMIN_MODE_ENABLED` -> success.

Latest focused Admin node maintenance evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_node_maintenance.py tests/test_kubernetes_ops_admin_nodes.py tests/test_kubernetes_ops_admin_action_review_readiness.py tests/test_kubernetes_ops_release_admin_mode_safety.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db` -> `36 passed`. This proves node maintenance is disabled by default, cordon/uncordon require approved break-glass node scope before provider PATCH, drain requires exact confirmation and records blocked metadata while its second execution flag is disabled, and release safety blocks unapproved node cordon before provider/action side effects. Latest drain execution check: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_node_maintenance.py -q --create-db` -> `11 passed`; it proves gated drain uses `GET pods` by node selector, blocks `emptyDir` pods and truncated pod lists before cordon/eviction unless explicitly allowed/complete, skips DaemonSet/terminal pods, cordons the node, and posts `policy/v1` Eviction requests instead of raw pod deletes.

Latest focused Admin live describe evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_resource_describe_live.py -q --reuse-db` -> `3 passed`; `python -m py_compile kubernetes_ops/admin_resource_views.py kubernetes_ops/urls.py kubernetes_ops/services/admin_resource_describe.py kubernetes_ops/services/admin_resource_describe_related.py` -> passed; `python scripts/check_architecture_sizes.py --strict-new` -> success. This proves `resources/describe/` is active-session gated, combines live provider resource/events/related Pods/ReplicaSets, redacts sensitive strings, and keeps action/audit evidence metadata-only.

Latest local platform evidence/preflight contract check: host-side `python scripts/verify_kubernetes_ops_local_platform.py --output artifacts/kubernetes_ops_local_platform_evidence.json` wrote `artifacts/kubernetes_ops_local_platform_evidence.json` at `2026-07-02T10:21:27Z` -> `status=ready`, `ready=3`, `missing=0`, `total=3` for Rancher/Fleet/Devtron in `kind-webterm-k8s`; `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_local_platform_evidence.py tests/test_kubernetes_ops_release_preflight.py -q --reuse-db` -> `10 passed`.

Latest live provider smoke evidence: `docker compose exec -T backend python manage.py verify_kubernetes_ops_live_provider_smoke --output artifacts/kubernetes_ops_live_provider_smoke.json` wrote schema `kubernetes_ops.live_provider_smoke.v3` at `2026-07-01T18:09:51Z` with `status=ready`, `enabled_providers=2`, `provider_probes_ok=2/2`, `sync_dry_run_ok=2/2`, `clusters=1`, `namespaces=31`, `workloads=21`, `pods=35`, `fleet_bundles=1`, `apps=8`, `backend_paths_status=ready`, `backend_path_checks=4/4`; focused backend check `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_live_provider_smoke.py tests/test_kubernetes_ops_admin_resource_describe_live.py -q --reuse-db` -> `7 passed`. This proves the local WebTerm provider layer can read real local Rancher/Fleet/Devtron data, then fetch a synced Rancher Pod YAML, bounded logs snapshot, live read-only describe and read-only node drain preflight through Admin backend services with backend-held credentials; it is still local evidence, not production approval.

Latest preflight evidence with live provider smoke included: `docker compose exec -T backend python manage.py verify_kubernetes_ops_preflight --output artifacts/kubernetes_ops_preflight_evidence.json --no-fail` -> `status=ready`, `failed=[]`, generated `2026-07-02T12:31:16Z`; all `14` required command results are green, including `django_check`, `architecture_guard`, `migrations_dry_run`, `readonly_rbac_validate`, `sync_prune_safety`, `readonly_rbac_live`, `local_platform_evidence`, `live_provider_smoke`, `interactive_transport_evidence`, `interactive_live_smoke`, `interactive_production_controls`, `production_action_evidence`, and `external_evidence_bundle`. The full Kubernetes backend regression inside preflight passed `535` tests plus `10` subtests with `timeout_seconds=1200` and `POSTGRES_STATEMENT_TIMEOUT_MS=0`; `interactive_live_smoke` proves `4` simulated provider opener checks plus `4` production live transport contracts, `interactive_production_controls` proves `4` restricted-credential/recording/network-policy/provider-contract controls, and `production_action_evidence` proves `5` rollback action classes, `10` native verification checks, `5` action-class contracts and `11` blocked-action contracts.

Latest release evidence refresh: `docker compose exec -T backend python manage.py verify_kubernetes_ops_release --output artifacts/kubernetes_ops_release_evidence.json --no-fail` wrote schema `kubernetes_ops.release_evidence.v2` at `2026-07-02T12:31:39Z` with `production_ready=false`, `ready_for_sidebar=false`, blockers `readiness:sidebar_release_scope=missing` and `release_scope:local`, preflight `status=ready`, `artifact_safety.status=ready`, readiness summary `ready=17`, `missing=1`, `manual=0`, `total=18`, local provider probes/sync still ready, `identity_runtime.status=ready` with `webterm_login_gateway.mode=local`, `definition_of_done.status=ready` with `ready=13`, `missing=0`, `total=13`, and Release Proofs ready for action controls, admin mode safety, post-review retention, external evidence bundle, production action evidence, interactive transport/live-smoke, interactive shell streams, normal user surface, secret read controls, provider secret lifecycle and audit redaction. `release_summary.completion_audit` is now stored in the release artifact and handoff: core backend and runtime readiness are complete, while production evidence and sidebar enablement remain incomplete because the scope is local; the remaining `sidebar_release_scope` check is production-scope gating, not a runtime backend gap. `external_evidence_bundle` now has `artifact_ready_count=6/6`, including `interactive_production_controls` and `production_action_evidence`; it records `local_indicator_count=18` without treating local evidence as production approval. Staff release readiness now exposes `production_evidence_checklist.gap_summary` with `next_gap_id=select_production_environment`, `production_blocking_gap_count=2`, and `operator_command_plan.blocking_summary`, so the UI can show that the remaining gate is production scope/local evidence rather than missing runtime backend work. Admin live YAML/JSON view now includes a safe `manifest` contract: sanitized JSON is available, client-side YAML rendering is allowed from that sanitized resource, server-side YAML/raw provider body storage stays false, Secret payload redaction is explicit, and direct copy-to-apply remains discouraged because apply still requires dry-run proof. `interactive_live_smoke` stores explicit live transport contracts for exec, port-forward, cluster terminal and node debug: local mode proves opener contract coverage without opening a live provider stream, while production still requires reviewed live-smoke evidence before enabling streams. `interactive_production_controls` stores explicit contracts for restricted credential evidence, recording policy, port-forward network-policy evidence and provider path templates without opening a live provider stream. `production_action_evidence` stores blocked-action contracts for `delete_namespace`, `delete_helm_release`, `helm.delete`, `helm_release.delete`, `kubectl.apply`, `apply_yaml`, `node_debug`, `port_forward`, `cluster_admin_shell`, `rbac.edit` and `edit_rbac`; loader validation fails if any of those contracts are missing or imply provider writes/native mutation. `secret_read_controls` also proves Secret list metadata-only behavior: `include_secret_values=1` on a Secret list still returns `secret_values.mode=list_metadata_only`, `visible=false`, redacted bodies and boolean-only action summary flags. `provider_secret_lifecycle` is included in `completion_audit.core_backend_proofs` and proves managed provider token storage, rotation, encrypted ciphertext plaintext absence, no plaintext serialization and rollback cleanup; the release summary exposes the safe machine field `provider_lifecycle_status=ready` so artifact safety does not flag a sensitive-key name. `audit_redaction` is also included in `completion_audit.core_backend_proofs` and proves `serialize_audit_event` plus `serialize_cluster_event` remove token/password/bearer/connection-string markers and sanitize credentialed URLs; the release summary exposes `audit_redaction_status=ready`. `action_controls` proves `production_restart_template_status=ready` with approval, verification, report and safe-template gates. The normal-user proof reports `frontend_response_credential_scan.status=ready` with `surfaces_checked=31`, `provider_secret_reference_serialized=false`, and `forbidden_values_found=false`; those surfaces now include Helm release ownership, Devtron AppOps delivery, cluster/workload/network diagnostics summary payloads, action summary queue payloads, staff release readiness summary payloads with `production_evidence_checklist`/`operator_command_plan`, and capability matrix payloads. In local mode the rollback/native verification refs are visible but optional; in production `KUBERNETES_OPS_PRODUCTION_ROLLBACK_EVIDENCE_REF` and `KUBERNETES_OPS_PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_REF` become required alongside approval/provider/RBAC/WebTerm login gateway/MCP evidence. Handoff JSON was regenerated at `2026-07-02T12:31:54Z` and remains `status=blocked`, `can_enable_sidebar=false`; the next step is production evidence on non-local Rancher/Devtron/MCP endpoints with approval, core refs, rollback drill evidence and native verification evidence.

Latest focused capability matrix evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_capabilities.py -q --reuse-db` -> `4 passed`. This proves `GET /api/kubernetes/capabilities/` is read-only, feature-gated, exposes modes/workflows/runtime flags for safe cockpit/Admin Read/Admin Write/break-glass/secret-read, respects the Admin Mode kill switch, and does not serialize external hosts or token-like values.

Latest focused Admin stream WebSocket evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_stream_websockets.py -q --create-db` -> `3 passed`. This proves the real ASGI consumers stop bounded logs/watch follow with `admin_session_expired` / `admin_session_not_active`, skip the next provider call when the admin session expires or is closed after stream start, and advance watch `resourceVersion` between bounded provider watch batches.

Latest Admin recording evidence check: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_recordings.py -q --create-db` -> `6 passed`; related action/exec/recording regression: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_actions.py tests/test_kubernetes_ops_admin_exec_stream_websocket.py tests/test_kubernetes_ops_admin_recordings.py -q --create-db` -> `15 passed`; expanded interactive admin regression with recordings: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_exec.py tests/test_kubernetes_ops_admin_port_forward.py tests/test_kubernetes_ops_admin_exec_stream_websocket.py tests/test_kubernetes_ops_admin_port_forward_tunnel_websocket.py tests/test_kubernetes_ops_admin_terminal.py tests/test_kubernetes_ops_admin_node_debug.py tests/test_kubernetes_ops_admin_actions.py tests/test_kubernetes_ops_admin_recordings.py -q --create-db` -> `48 passed`.

Latest Admin recording readiness check: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_recording_readiness.py tests/test_kubernetes_ops_terminal_safety.py tests/test_kubernetes_ops_operator_docs.py -q --create-db` -> `14 passed`; related action-review/recording/exec/readiness regression: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_action_review_readiness.py tests/test_kubernetes_ops_admin_recordings.py tests/test_kubernetes_ops_admin_actions.py tests/test_kubernetes_ops_admin_exec_stream_websocket.py tests/test_kubernetes_ops_admin_recording_readiness.py tests/test_kubernetes_ops_operator_docs.py -q --create-db` -> `27 passed`.

Latest focused Admin action post-review evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_actions.py -q --create-db` -> `10 passed`. This proves `POST /api/kubernetes/admin/actions/{action_id}/review/` stores sanitized outcome/summary/evidence on the action, writes sanitized audit metadata, exposes review status in the action report, rejects non-staff owners, requires `kubernetes_break_glass` for break-glass action review, and lets staff list pending/completed/not_ready action review queues through `post_review_status`.

Latest focused provider stream decoding evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_provider_clients.py tests/test_kubernetes_ops_admin_resources.py tests/test_kubernetes_ops_admin_stream_websockets.py -q --create-db` -> `17 passed`. This proves the provider client can decode bounded multi-event SSE and Kubernetes NDJSON watch payloads into `items`, while keeping the existing single-object JSON/SSE contract intact.

Latest focused watch normalization evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_watch_normalization.py tests/test_kubernetes_ops_admin_resources.py tests/test_kubernetes_ops_provider_clients.py tests/test_kubernetes_ops_admin_stream_websockets.py tests/test_kubernetes_ops_admin_streams.py -q --create-db` -> `32 passed`. This proves Kubernetes watch `BOOKMARK` events advance `latest_resource_version` for the next bounded watch request without appearing as normal resource-change rows, while truncated resource events keep the visible last resourceVersion as the safe continuation point.

Latest focused Admin resource events evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_resource_events.py tests/test_kubernetes_ops_admin_resources.py -q --create-db` -> `15 passed`. This proves resource-specific Kubernetes Events are fetched through Rancher proxy with field selectors, require active Admin Mode read sessions, redact messages/source metadata, and store only metadata counts in action/audit rows.

Latest focused Admin resource list filter evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_resource_list_filters.py tests/test_kubernetes_ops_admin_resource_events.py tests/test_kubernetes_ops_admin_resources.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db` -> `34 passed`. This proves Admin resource list supports Kubernetes `labelSelector`, `fieldSelector`, safe local `search`, bounded `limit`, `continue` pagination token, optional sanitized `managedFields`, and does not store raw selector/search/token values in action summaries.

Latest focused Devtron AppOps detail evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_devtron_app_detail.py -q --reuse-db` -> `3 passed`. This proves `GET /api/kubernetes/devtron/apps/{app_id}/` returns sanitized app/workload/pod/event context plus read-only `delivery_context` for chart/release, history, values preview, rollback and logs, hides external links from normal users, keeps staff fallback links sanitized, redacts sensitive values, and audits only metadata counts.

Latest focused diagnostics summary evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_diagnostics_summary.py -q --reuse-db` -> `6 passed`. This proves `GET /api/kubernetes/diagnostics/summary/` returns read-only triage for cluster/workload/pod/namespace/network scope with health severity, node/readiness gaps, restarts, unhealthy namespace/workload/pod counts, warning-event counts, owner/change-path context, safe next steps, no external links and metadata-only audit.

Latest focused release readiness summary evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_release_readiness_summary.py -q --reuse-db` -> `5 passed`. This proves `GET /api/kubernetes/release/summary/` is staff-only, read-only, does not run live provider checks, groups readiness/production/artifact/evidence blockers for the Settings UI, returns required commands/next steps plus machine-readable `progress` (`runtime_readiness_incomplete` vs `core_backend_ready_production_blocked`, backend DoD percent, runtime-readiness percent and remaining blocker categories), returns `completion_audit` that explicitly separates completed core backend/runtime readiness from incomplete production/sidebar gates, classifies `sidebar_release_scope` as production scope rather than runtime missing work, returns `production_evidence_checklist` for core refs/external evidence bundle artifacts without env values plus `gap_summary` (`next_gap_id`, missing ref/artifact counts, local indicator count, next command ids), returns `operator_command_plan` with recommended next manual/command action, evidence/release command phases and `blocking_summary`, returns `production_execution_plan` with the same deterministic blocked-until/phase/command contract used by handoff artifacts, and does not serialize raw token-like values from the release evidence artifact.

Latest focused backend-workstream release evidence: `C:\Python313\python.exe -m pytest tests/test_kubernetes_ops_release_readiness_summary.py tests/test_kubernetes_ops_release_evidence_execution_plan.py tests/test_kubernetes_ops_release_evidence_summary.py tests/test_kubernetes_ops_release_evidence.py tests/test_kubernetes_ops_release_handoff.py -q` -> `24 passed`. This proves `GET /api/kubernetes/release/summary/`, `verify_kubernetes_ops_release`, its operator stdout summary and `render_kubernetes_ops_release_handoff` now expose safe `backend_workstream` metadata: backend completion status, core backend proof counts/percent, runtime-readiness completion, remaining backend gaps, external production/sidebar blockers, safe frontend continuation flag and next backend/production-evidence step. The field is safe for release artifact and handoff output, so saved evidence can distinguish "backend scope complete" from "production evidence still required" without serializing tokens, provider URLs or raw artifact payloads.

Latest focused plain-text log evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_provider_clients.py tests/test_kubernetes_ops_logs.py tests/test_kubernetes_ops_admin_logs_plain_text.py tests/test_kubernetes_ops_admin_resources.py tests/test_kubernetes_ops_admin_streams.py tests/test_kubernetes_ops_admin_stream_websockets.py -q --create-db` -> `38 passed`. This proves bounded Kubernetes pod logs can come from provider JSON wrappers or plain-text Kubernetes/Rancher log endpoints, with the same tail bounds, line trimming, redaction and metadata-only action/audit summaries.

Latest focused logs follow evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_stream_websockets.py tests/test_kubernetes_ops_admin_streams.py tests/test_kubernetes_ops_provider_clients.py tests/test_kubernetes_ops_logs.py tests/test_kubernetes_ops_admin_logs_plain_text.py -q --create-db` -> `27 passed`. This proves bounded WebTerm logs follow suppresses overlapping tail lines between provider snapshots and sends only the new suffix as `follow_delta`, while keeping session-expiry, stream audit, plain-text logs and watch resourceVersion checks green.

Latest focused provider-native log stream batch evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_logs_plain_text.py tests/test_kubernetes_ops_admin_stream_websockets.py tests/test_kubernetes_ops_admin_streams.py tests/test_kubernetes_ops_provider_clients.py tests/test_kubernetes_ops_logs.py -q --create-db` -> `29 passed`. This proves WebTerm logs follow can opt into `pod_logs_stream_path_template` with `provider_stream=1`, bounded timeout, line limits, redaction and metadata-only action/audit summaries.

Latest focused multi-container Admin logs evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_logs_plain_text.py tests/test_kubernetes_ops_admin_streams.py tests/test_kubernetes_ops_admin_stream_websockets.py -q --reuse-db` -> `28 passed`. This proves selected `container` is preserved through Admin logs snapshot/follow/provider-stream paths and is appended to Rancher/Kubernetes log proxy URLs when the provider template does not already include `{container}`.

Latest focused provider stream bounds evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_provider_clients.py -q --create-db` -> `7 passed`. This proves the provider-native log stream reader reports `truncated=false` when the stream ends exactly at the configured line limit and `truncated=true` only when more bytes/lines are present.

Latest focused provider stream slice evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_provider_clients.py tests/test_kubernetes_ops_admin_logs_plain_text.py tests/test_kubernetes_ops_admin_stream_websockets.py -q --create-db` -> `15 passed`. This rechecks the provider client decoder, Admin log stream batch path and real WebSocket provider-stream opt-in together after the bounded truncation fix.

Latest focused provider-native continuous log follow evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_provider_clients.py tests/test_kubernetes_ops_admin_stream_websockets.py -q --create-db` -> `16 passed`. This proves WebTerm logs follow can opt into one opened provider stream with `provider_stream=continuous`, emit multiple sanitized WebSocket `log_batch` messages from that one response, close cleanly on provider EOF, and close the provider handle on idle timeout.

Latest focused Admin stream suite evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_provider_clients.py tests/test_kubernetes_ops_admin_stream_websockets.py tests/test_kubernetes_ops_admin_logs_plain_text.py tests/test_kubernetes_ops_admin_streams.py -q --create-db` -> `31 passed`. This rechecks continuous logs together with existing plain-text logs, stream lifecycle/audit summaries, session expiry and bounded follow behavior.

Latest focused provider-native watch stream batch evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_watch_stream_batch.py tests/test_kubernetes_ops_admin_stream_websockets.py tests/test_kubernetes_ops_admin_resources.py tests/test_kubernetes_ops_admin_watch_normalization.py tests/test_kubernetes_ops_provider_clients.py -q --create-db` -> `25 passed`. This proves WebTerm watch follow can opt into `provider_watch_stream_batch` with `provider_stream=1`, resourceVersion continuation, sanitized event rows and metadata-only action/audit summaries.

Latest focused provider-native continuous watch follow evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_provider_clients.py tests/test_kubernetes_ops_admin_stream_websockets.py -q --create-db` -> `19 passed`. This proves WebTerm watch follow can opt into one opened provider watch stream with `provider_stream=continuous`, parse SSE and NDJSON watch events from that one response, sanitize event objects, advance `latest_resource_version` through `BOOKMARK`, close cleanly on provider EOF, and close the provider handle on idle timeout.

Latest focused Admin stream/read suite evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_provider_clients.py tests/test_kubernetes_ops_admin_stream_websockets.py tests/test_kubernetes_ops_admin_logs_plain_text.py tests/test_kubernetes_ops_admin_streams.py tests/test_kubernetes_ops_admin_watch_stream_batch.py tests/test_kubernetes_ops_admin_watch_normalization.py tests/test_kubernetes_ops_admin_resources.py -q --create-db` -> `48 passed`. This rechecks continuous logs/watch together with existing plain-text logs, stream lifecycle/audit summaries, session expiry, bounded follow, watch normalization and Admin resource read behavior.

Latest focused provider-native exec stream evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_exec.py tests/test_kubernetes_ops_admin_exec_stream_websocket.py tests/test_kubernetes_ops_provider_clients.py -q --create-db` -> `22 passed`. This proves WebTerm exec remains blocked by default, requires the separate `KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED=true` flag before provider/action side effects, then can opt into provider stdout/stderr/status frames with `provider_stream=1`, redacts streamed output, stores metadata-only action/audit summaries, and closes the provider handle on WebSocket disconnect.

Latest focused Admin exec/terminal safety suite evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_port_forward.py tests/test_kubernetes_ops_admin_port_forward_tunnel_websocket.py tests/test_kubernetes_ops_admin_exec.py tests/test_kubernetes_ops_admin_exec_stream_websocket.py tests/test_kubernetes_ops_admin_stream_websockets.py tests/test_kubernetes_ops_provider_clients.py tests/test_kubernetes_ops_terminal_safety.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db` -> `66 passed`. This rechecks opt-in exec streaming and opt-in port-forward tunnel together with existing logs/watch WebSocket behavior, provider parser contracts, terminal safety report and permission matrix.

Latest focused interactive transport prerequisite evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_interactive_transport_readiness.py tests/test_kubernetes_ops_admin_port_forward.py tests/test_kubernetes_ops_terminal_safety.py tests/test_kubernetes_ops_release_handoff.py tests/test_kubernetes_ops_release_evidence_summary.py -q --create-db` -> `38 passed`. This proves production provider-native exec/port-forward transport is blocked before action/provider side effects without `KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF`; production port-forward additionally requires `KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF`, exact non-wildcard targets, protected namespace coverage and <=900s TTL; enabled cluster-terminal/node-debug additionally require explicit Rancher provider path-template contracts.

Latest release handoff/readiness evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_release_evidence.py tests/test_kubernetes_ops_release_handoff.py tests/test_kubernetes_ops_release_evidence_summary.py tests/test_kubernetes_ops_release_preflight.py tests/test_kubernetes_ops_admin_interactive_transport_readiness.py tests/test_kubernetes_ops_operator_docs.py -q --reuse-db` -> `35 passed`. This proves the operator handoff exposes `KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF`, `KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF`, external restricted-credential/network-policy proof requirements, provider path-template contracts for terminal/node-debug, interactive-transport safety guards and a direct next step for `readiness:admin_interactive_transport=missing`.

Latest focused action-request native restart/scale/patch/delete evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_action_request_delete.py tests/test_kubernetes_ops_action_native_execution.py tests/test_kubernetes_ops_action_request_workload_actions.py tests/test_kubernetes_ops_permission_matrix.py -q --reuse-db` -> `30 passed`. This proves `execute-approved` remains blocked by default, while the opt-in `k8s.rollout.restart`, `k8s.workload.scale`, non-sensitive `k8s.resource.patch`, and controlled `k8s.resource.delete` paths can execute through an active approved Admin write session, write linked `K8sAdminAction` rows, record `k8s.action_request.execute_native`, return sanitized `executed_native` request/report output, and enforce exact delete confirmation plus protected namespace/kind guards; release evidence also proves scale, patch and delete request previews.

Latest WebTerm-only normal-user API evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_api.py tests/test_kubernetes_ops_permission_matrix.py tests/test_kubernetes_ops_describe.py tests/test_kubernetes_ops_logs.py -q --create-db` -> `40 passed`; `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_describe.py tests/test_kubernetes_ops_logs.py tests/test_kubernetes_ops_frontend_e2e.py tests/test_kubernetes_ops_security_review.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db` -> `32 passed`. This proves normal Kubernetes users do not receive provider config/base URLs or external Rancher/Fleet/Devtron links, while staff/admin fallback links are sanitized.

Latest focused namespace detail API evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_namespace_detail.py tests/test_kubernetes_ops_api.py -q --reuse-db` -> `19 passed`. This proves `GET /api/kubernetes/clusters/{cluster_id}/namespaces/{namespace_id}/` returns sanitized WebTerm-native namespace context, hides fallback links from normal users, sanitizes staff links, keeps action policy read-only, and records metadata-only audit counts.

Latest focused pod detail API evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_pod_detail.py tests/test_kubernetes_ops_logs.py tests/test_kubernetes_ops_api.py -q --reuse-db` -> `24 passed`. This proves `GET /api/kubernetes/pods/{pod_id}/` returns sanitized WebTerm-native Pod runtime context, hides fallback links from normal users, keeps `/logs/` routing green, keeps action policy read-only, and records metadata-only audit counts.

Latest focused workload detail API evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_workload_detail.py tests/test_kubernetes_ops_describe.py tests/test_kubernetes_ops_api.py -q --reuse-db` -> `22 passed`. This proves `GET /api/kubernetes/workloads/{workload_id}/` returns sanitized WebTerm-native workload runtime context, hides fallback links from normal users, keeps `/describe/` routing green, keeps action policy read-only, and records metadata-only audit counts.

Latest focused network detail API evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_network_detail.py tests/test_kubernetes_ops_api.py -q --reuse-db` -> `18 passed`. This proves `GET /api/kubernetes/network/{network_id}/` returns sanitized WebTerm-native Service/Ingress runtime context, hides fallback links from normal users, sanitizes staff links, keeps action policy read-only, and records metadata-only audit counts.

Latest read-only detail regression evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_network_detail.py tests/test_kubernetes_ops_namespace_detail.py tests/test_kubernetes_ops_workload_detail.py tests/test_kubernetes_ops_pod_detail.py tests/test_kubernetes_ops_api.py -q --reuse-db` -> `28 passed`. This keeps namespace/workload/pod/network detail contracts green together.

Latest focused Fleet detail API evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_fleet_bundle_detail.py tests/test_kubernetes_ops_api.py tests/test_kubernetes_ops_action_requests.py -q --reuse-db` -> `30 passed`. This proves the new Fleet bundle detail endpoint returns sanitized WebTerm-native GitOps context, hides fallback links from normal users, sanitizes staff links, keeps action policy read-only, and records metadata-only audit counts.

Latest WebTerm-only normal-user release evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_release_evidence.py tests/test_kubernetes_ops_release_evidence_summary.py tests/test_kubernetes_ops_release_handoff.py tests/test_kubernetes_ops_release_normal_user_surface.py tests/test_kubernetes_ops_release_readiness_summary.py tests/test_kubernetes_ops_release_external_evidence_bundle.py tests/test_kubernetes_ops_capabilities.py tests/test_kubernetes_ops_api.py tests/test_kubernetes_ops_permission_matrix.py tests/test_kubernetes_ops_helm_ownership.py tests/test_kubernetes_ops_devtron_app_detail.py tests/test_kubernetes_ops_diagnostics_summary.py tests/test_kubernetes_ops_action_requests.py tests/test_kubernetes_ops_action_summary.py -q --reuse-db` -> `96 passed`. This now proves `frontend_response_credential_scan.status=ready`: provider `secret_ref` and rollback-only token/kubeconfig-like marker values are absent from reader/staff frontend-facing payloads, including Helm release ownership, Devtron AppOps delivery, cluster/workload/network diagnostics summary payloads, metadata-only action summary queue payloads, staff release readiness summary payloads, production evidence checklist and capability matrix payloads, while normal users stay WebTerm-native, staff fallback links stay sanitized, and release handoff renders `credential_scan=ready` with `surfaces=31`.

Latest focused provider-native port-forward tunnel evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_port_forward.py tests/test_kubernetes_ops_admin_port_forward_tunnel_websocket.py tests/test_kubernetes_ops_provider_clients.py -q --create-db` -> `24 passed`. This proves WebTerm port-forward remains blocked by default, requires the separate `KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED=true` flag before action/provider side effects, then can opt into provider tunnel data frames with `provider_stream=1`, stores only byte/status/close metadata, and closes the provider handle on tunnel stop or admin-session expiry.

Latest focused break-glass post-review evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_sessions.py tests/test_kubernetes_ops_terminal_safety.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db` -> `35 passed`. This proves break-glass sessions carry a pending post-review marker, active sessions cannot be reviewed early, only staff with break-glass access can complete review after close/revoke/expire, and review writes sanitized audit metadata.

Latest focused restricted kube context evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_restricted_context.py tests/test_kubernetes_ops_admin_sessions.py tests/test_kubernetes_ops_terminal_safety.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db` -> `39 passed`. This proves the restricted context endpoint requires an active approved break-glass session, rejects wildcard namespaces, returns only namespace-scoped ServiceAccount/Role/RoleBinding manifests without kubeconfig/token material, and fails closed on ClusterRole, Secret, node, attach, wildcard, or base-resource write access.

Latest focused cluster terminal lifecycle evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_terminal.py tests/test_kubernetes_ops_admin_node_debug.py tests/test_kubernetes_ops_admin_interactive_transport_readiness.py tests/test_kubernetes_ops_terminal_safety.py -q --create-db` -> `38 passed`. This proves cluster terminal start validates approved break-glass plus restricted context, records metadata-only blocked action/audit with recording policy while transport is disabled, rejects enabled transport before action/audit when recording, provider path-template contract or production restricted evidence is missing, and terminal stop is rejected/audited when no live terminal exists.

Latest focused break-glass terminal/node-debug lifecycle evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_terminal.py tests/test_kubernetes_ops_admin_node_debug.py tests/test_kubernetes_ops_admin_interactive_transport_readiness.py tests/test_kubernetes_ops_terminal_safety.py -q --create-db` -> `38 passed`. This proves node debug start requires approved break-glass session evidence, `node` scope, valid node name and reason, writes metadata-only blocked action/audit with recording policy while transport is disabled, rejects enabled debug transport before action/audit when recording, provider path-template contract or production restricted evidence is missing, and stop is rejected/audited when no live debug session exists.

Latest focused cluster terminal/node-debug WebSocket provider-stream evidence: `docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_terminal_node_debug_websocket.py tests/test_kubernetes_ops_admin_terminal.py tests/test_kubernetes_ops_admin_node_debug.py tests/test_kubernetes_ops_admin_interactive_transport_readiness.py tests/test_kubernetes_ops_terminal_safety.py -q --create-db` -> `41 passed`. This proves `ws/kubernetes/admin/terminal/{session_id}/` and `ws/kubernetes/admin/node-debug/{session_id}/` can open opt-in provider streams only after the matching transport and recording flags, active approved break-glass session, provider path-template contract and production restricted-evidence gate are satisfied; the streams redact browser frames, store bounded redacted `stdin`/`stdout`/`stderr` transcript events, complete/fail the linked action and recording, and reject before provider/action side effects when the provider contract is missing.

Что намеренно ещё не сделано:

- production-проверка на внешних production Rancher/Fleet/Devtron endpoints через `verify_kubernetes_ops_preflight --output ...` и затем `verify_kubernetes_ops_release --output ...`; local Docker evidence artifacts уже обновлены и включают настоящий local Rancher + real local Devtron provider, но `release_scope:local` специально блокирует production-ready до запуска на выбранной production-среде с `KUBERNETES_OPS_RELEASE_ENVIRONMENT=production`, `KUBERNETES_OPS_PRODUCTION_APPROVAL_REF=<approval-id>` и свежим release artifact младше `KUBERNETES_OPS_RELEASE_EVIDENCE_MAX_AGE_SECONDS`;
- production live evidence для реального, не demo, Kubernetes MCP binding и read-only diagnosis draft через тот же release-evidence artifact; local Docker evidence уже закрывает MCP smoke и non-persistent Studio draft proof через `mcp-demo` + `ensure_kubernetes_ops_studio_binding`, но `release_scope` и runtime `sidebar_release_scope` считают `mcp-demo` local marker и не пропускают его в production-ready;
- production SSO/Keycloak runtime values: gate `identity_runtime` уже реализован и в production будет требовать `DOMAIN_AUTH_ENABLED=true`, trusted identity header, safe default profile, HTTPS Keycloak URL/realm и TLS verify, но реальные production значения ещё не заведены в этом local evidence;
- `KUBERNETES_OPS_READY_FOR_SIDEBAR=true` в production env;
- финальный удобный красивый Admin Mode UX, richer ownership UX на всех app/resource pages и live watch/follow panels; первый ownership-контекст для Admin resource list/get/YAML, первый Admin pod logs snapshot, bounded watch preview и WebSocket bounded follow bridge уже есть, но это функциональный MVP, не итоговый Freelens++ интерфейс;
- отдельный UI просмотра записей/action post-review и production retention cleanup для exec/terminal: backend policy, recording gates, retention values, action-level post-review endpoint, `K8sAdminRecording` metadata rows и bounded redacted `K8sAdminRecordingEvent` для exec уже есть, но полный raw transcript body специально не сохраняется;
- любые native live write actions сверх runtime-gated apply/patch/scale/restart/delete and break-glass node maintenance paths; production-live provider evidence для exec/port-forward/cluster-terminal/node-debug ещё не закрыт, хотя backend opt-in streams уже есть. Admin Mode сессии и live endpoints уже умеют create/approve/revoke/close/expire, discovery/list/get/yaml/crds/live describe/log snapshot/watch preview, `dry-run-apply` с `dryRun=All`, fail-closed `apply` после dry-run proof, fail-closed `patch` через Kubernetes PATCH, fail-closed `scale` через scale subresource, fail-closed rollout `restart` через annotation patch, fail-closed `delete` с exact confirmation/denylist, break-glass node `cordon`/`uncordon` через Node `spec.unschedulable` behind `KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED=true`, gated `drain` behind `KUBERNETES_ADMIN_NODE_DRAIN_EXECUTION_ENABLED=true` with pod preflight and Kubernetes Eviction API/PDB enforcement, fail-closed exec bridge с break-glass/session/command guard и opt-in provider exec stream behind separate `KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED` + `KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED`, fail-closed port-forward bridge с break-glass/session/target allowlist guard и opt-in provider tunnel behind separate `KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED` + `KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED`, fail-closed cluster terminal/node-debug REST lifecycle plus opt-in WebSocket provider streams behind separate transport + recording flags and provider path-template contracts, а rough frontend умеет session/List/YAML/Logs snapshot/Watch preview flow, но пока не выполняет UI apply/patch/scale/restart/delete/exec/port-forward/terminal/node-debug/node maintenance; Secret list остаётся metadata-only и возвращает `secret_values.visible=false` даже при `include_secret_values=1`, Secret values по умолчанию redacted, а named Secret YAML/detail/get может вернуть `data`/`binaryData`/`stringData` только при `kubernetes_secret_read`, `KUBERNETES_ADMIN_SECRET_READ_ENABLED=true` и `include_secret_values=1`, при этом audit/action summaries хранят только boolean-флаги без raw values; logs сейчас доступны как bounded read-only snapshot через `pod_logs_path_template` или default Rancher Kubernetes proxy path `/k8s/clusters/{cluster_id}/api/v1/namespaces/{namespace}/pods/{pod_name}/log?tailLines={tail}`, bounded provider stream batch при `provider_stream=1` или opt-in continuous provider stream при `provider_stream=continuous`, watch сейчас доступен как bounded preview через Rancher/Kubernetes watch query, bounded provider stream batch при `provider_stream=1` или opt-in continuous provider stream при `provider_stream=continuous`, WebSocket умеет bounded batch, bounded polling follow, continuous logs/watch follow, opt-in exec stdout/stderr/status frames с записью redacted events, opt-in port-forward data frames и opt-in terminal/node-debug shell frames через `stream_started`/`exec_started`/`port_forward_started`/`terminal_started`/`node_debug_started` -> `log_batch`/`watch_batch`/`exec_output`/`port_forward_data`/`cluster_terminal_output`/`node_debug_output` + heartbeat -> stopped events; обычный cockpit describe остаётся normalized snapshot, а Admin Mode `resources/describe/` уже делает live read-only describe через provider GET/list calls, не через shell `kubectl describe`.

---

# 15. Полноценный implementation plan

Этот документ является master-plan для Kubernetes направления. Детальный low-level/Admin Mode план живёт в `docs/architecture/KUBERNETES_LOW_LEVEL_ADMIN_MODE_PLAN.md`, но не является отдельной стратегией: это Freelens++ глава этого master-plan. Любые будущие задачи по resource explorer, YAML, log streaming, exec, port-forward, apply/delete, terminal и node debug должны сохранять общую модель: обычный пользователь работает в WebTerm, а Rancher/Fleet/Devtron UI остаются staff/admin fallback.

## 15.0. Единый большой план: WebTerm Freelens++

Дальше планируем это как один продукт, а не как набор отдельных панелей:

```text
WebTerm Kubernetes Ops = обычный безопасный cockpit
WebTerm Kubernetes Admin Mode = улучшенная Freelens-версия внутри WebTerm
Rancher = backend/source-of-truth для clusters/RBAC/API proxy/Fleet
Fleet = backend/source-of-truth для GitOps/HelmOps rollout
Devtron = backend/source-of-truth для AppOps/CI-CD/history/rollback/debug context
```

Канонический backlog для low-level/Admin Mode находится в `docs/architecture/KUBERNETES_LOW_LEVEL_ADMIN_MODE_PLAN.md`. Этот отчёт фиксирует общую архитектуру и роль Rancher/Fleet/Devtron, а Admin Mode план фиксирует конкретные API, permissions, sessions, audit, tests и порядок реализации. Если нужно добавить новую Kubernetes-функцию, сначала обновлять Admin Mode план, затем кратко синхронизировать этот master-report.

Что берём в улучшенную Freelens-версию:

| Блок | Что должно быть в WebTerm-native UX |
|---|---|
| Freelens-like explorer | clusters, namespaces, workloads, pods, services, ingress, events, CRDs, custom resources, YAML/JSON, search/filter, logs, watch, exec, port-forward |
| Rancher context | cluster/project/RBAC context, Rancher API proxy, node/workload health, provider fallback links, Fleet ownership |
| Fleet context | GitRepo, Bundle, BundleDeployment, HelmOp, rollout partitions, paused/rolling/failed status, GitOps MR/change path |
| Devtron context | apps, environments, Helm values/history, deployment evidence, rollback context, app logs/debug context |
| WebTerm controls | feature flags, short-lived sessions, approval, audit, no browser kubeconfig/token, Studio diagnosis, action reports |

Фронт можно пока держать грубым. Приоритет сейчас: backend-контракты, безопасность, real provider smoke, audit/evidence и тесты. Красивый и удобный UI делается после того, как workflows реально работают и не обходят WebTerm policy.

Как это поднимается рядом:

- локально WebTerm идёт через `docker-compose.yml`;
- тестовый Kubernetes-кластер идёт через kind на Docker;
- Rancher/Fleet/Devtron ставятся внутрь kind-кластера Helm/operator-ом, а не как обычные compose-сервисы WebTerm;
- WebTerm backend подключается к ним через provider endpoints/port-forward и ManagedSecret/external refs;
- пользователь открывает только WebTerm (`/kubernetes`, `/kubernetes/admin`), а Rancher/Devtron/Fleet UI остаются fallback для staff/admin.

## 15.1. Принципы реализации

1. **Read-only first.** Первый релиз только читает: clusters, namespaces, workloads, pods, services, ingress, events, logs, Fleet bundles, Devtron apps.
2. **Provider source of truth.** Rancher владеет cluster/RBAC/lifecycle, Fleet владеет platform GitOps/HelmOps, Devtron владеет AppOps/CI/CD/debug UX.
3. **WebTerm не хранит admin kubeconfig.** Только scoped credentials, provider tokens с минимальными правами и audit.
4. **One release -> one owner.** Fleet и Devtron не должны одновременно менять один Helm release.
5. **PR/GitOps first для плановых изменений.** Production mutations идут через GitOps/MR/approval, а не через свободный `kubectl apply`.
6. **MCP/capability pack first для Studio.** Не добавлять десятки `kubernetes/*` нод, пока `agent/mcp_call` + schema + policy покрывает workflow.
7. **WebTerm-only normal UX.** Обычный пользователь не открывает Rancher/Fleet/Devtron отдельно; native WebTerm views являются основным путём, external links остаются staff/admin fallback.
8. **Deny by default.** Если WebTerm не может доказать право на действие, кнопка не показывается или действие блокируется.

## 15.2. Phase 0: readiness и cleanup gate

Цель: подготовить repo и внешний контур так, чтобы Kubernetes Ops не стартовал поверх незакрытого долга.

Задачи:

| Task | Где | Результат |
|---|---|---|
| Split god-file test | `tests/test_ops_agent_memory_patterns.py` | `check_architecture_sizes.py --strict-new` проходит |
| Зафиксировать флаг готовности | `frontend/src/components/AppSidebar.tsx` + `/api/kubernetes/readiness/` | Sidebar слушает backend `ready_for_sidebar`; env override остаётся `false` до production approval |
| Описать env contract | docs + `.env.production.example` при реализации | `RANCHER_BASE_URL`, `DEVTRON_BASE_URL`, sync intervals, secret refs |
| Выбрать домены | infra docs | `webterm.*`, `rancher.*`, `devtron.*`, `keycloak.*` |
| Выбрать pilot cluster | Rancher/Fleet/Devtron | один non-prod cluster для MVP |
| Обновить источники | этот документ | убрать устаревшие Devtron links, держать актуальные docs |

Acceptance:

- architecture guard green;
- текущая Kubernetes beta страница всё ещё не доступна из sidebar;
- есть список pilot clusters/namespaces/apps;
- есть mapping Keycloak groups -> WebTerm/Rancher/Devtron roles.

## 15.3. Phase 1: external platform foundation

Цель: поднять Rancher/Fleet/Devtron как backend/source-of-truth платформы, прежде чем WebTerm начнёт агрегировать их данные. Обычный пользователь при этом работает только через WebTerm; внешние UI остаются admin/break-glass fallback.

Задачи:

| Система | Что сделать | Done when |
|---|---|---|
| Login/RBAC | WebTerm принимает LDAP/OIDC/Keycloak или local WebTerm login; provider access идёт через service credentials/read-only service accounts | Пользователь работает в WebTerm, права проверяются WebTerm policy + provider RBAC, пароли не копируются в Rancher/Devtron |
| Rancher | Установить/проверить Rancher, импортировать pilot cluster, настроить cluster/project roles | Rancher видит cluster health, namespaces, projects |
| Fleet | Включить Fleet, добавить GitRepo/HelmOp для 2-3 platform charts | Видны bundles, BundleDeployment readiness, rollout partitions |
| Devtron | Подключить тот же pilot cluster, настроить environments/projects/RBAC | Devtron показывает application lifecycle, deploy/history/logs |
| Ownership registry | Ввести label/annotation contract | Fleet-owned и Devtron-owned releases не конфликтуют |

Первый pilot stack:

```text
Cluster: stage-webterm-ops
Fleet-owned: cert-manager, ingress-nginx, external-dns, monitoring
Devtron-owned: demo-api, demo-worker, demo-ui
WebTerm-owned: no direct Helm ownership in MVP
```

Current local implementation status:

- WebTerm поднимается через `docker-compose.yml`: Postgres, Redis, backend, frontend, nginx, workers, `kubernetes-ops-sync`, local MCP helpers;
- Rancher/Fleet/Devtron не являются обычными сервисами `docker-compose.yml`; локально они подняты рядом, внутри kind Kubernetes cluster, который сам работает на Docker containers;
- Fleet идёт как часть Rancher/Fleet stack, отдельного ежедневного логина во Fleet нет;
- WebTerm подключается к этим локальным платформам через provider endpoints (`host.docker.internal`, Devtron port-forward) и хранит provider credentials как ManagedSecret/external refs;
- local Docker DB применил Admin Mode migrations `core_ui.0017_add_kubernetes_admin_features` и `kubernetes_ops.0009_k8sadminsession_k8sadminaction`; после restart `frontend`, `backend`, `kubernetes-ops-sync` и `nginx` endpoint `http://127.0.0.1:8080/kubernetes/admin` открывает rough WebTerm-native Admin Mode explorer;
- local smoke user `codex-k8s-smoke` получил explicit `kubernetes` + `kubernetes_admin_read`, создал active read session и выполнил read-only `List` для `apps/v1 Deployment` через provider `local-rancher-real`; response имел `admin_read_only` policy и blocked `apply_yaml`, `patch`, `scale`, `delete`, `exec`, `port_forward`, `node_debug`;
- Admin Mode resource API теперь добавляет ownership context: Devtron-owned/Fleet-owned ресурсы получают правильный `change_path` (`devtron_app_flow` или `fleet_gitops_or_mr`) и `direct_apply_policy=blocked_by_default`, frontend `/kubernetes/admin` показывает owner summary/owner badge/policy panel перед JSON, а backend write paths дополнительно блокируют direct mutation для Devtron/Fleet/external owners до provider call;
- Admin Mode write preview начал Phase 4: `dry-run-apply` принимает YAML/object manifest, требует active approved write session, вызывает Kubernetes/Rancher только с `dryRun=All`, показывает sanitized diff summary и пишет `K8sAdminAction`/audit metadata без raw Secret body;
- local test Kubernetes cluster `kind-webterm-k8s` поднят через kind на Kubernetes `v1.34.0`;
- local platform evidence теперь собирается host-side командой `python scripts/verify_kubernetes_ops_local_platform.py --output artifacts/kubernetes_ops_local_platform_evidence.json`; текущий artifact `kubernetes_ops.local_platform_evidence.v1` от `2026-07-02T10:21:27Z` имеет `status=ready`, `ready=3`, `missing=0`, `total=3` и проверяет Rancher/Fleet/Devtron namespaces, services and workloads без raw credentials;
- live provider smoke evidence теперь собирается командой `python manage.py verify_kubernetes_ops_live_provider_smoke --output artifacts/kubernetes_ops_live_provider_smoke.json`; текущий artifact `kubernetes_ops.live_provider_smoke.v3` от `2026-07-01T18:09:51Z` имеет `status=ready`, `provider_probes_ok=2/2`, `sync_dry_run_ok=2/2`, `fleet_bundles=1`, `apps=8`, `backend_paths_status=ready`, `backend_path_checks=4/4` и проверяет уже не только установку платформы в kind, а реальный backend provider path WebTerm -> Rancher/Fleet/Devtron плюс Rancher Pod YAML/log snapshot, live read-only describe и read-only node drain preflight через Admin backend services;
- pilot namespaces/apps применены: `webterm-stage/demo-api`, `webterm-prod/payments-api`, intentionally degraded `webterm-prod/broken-worker`;
- `cert-manager` `v1.20.3` установлен в namespace `cert-manager`;
- Rancher `v2.14.3` установлен Helm-чартом в namespace `cattle-system`, endpoint `https://host.docker.internal:8443/dashboard` отвечает `200`;
- Rancher API token сохранён в WebTerm ManagedSecret для provider `local-rancher-real`; raw token не хранится в документе, API response или audit;
- WebTerm `local-rancher-real` provider синкает настоящий Rancher 2.14 через native proxy paths; current read-only sync rows: `namespaces=31`, `workloads=21`, `pods=34`, `services=24`, `ingresses=3`, `events=8`, `fleet_bundles=1`;
- Devtron OSS operator chart `0.23.2` / app `2.1.1` установлен в namespace `devtroncd`; `devtron`, `kubelink`, `dashboard`, `argocd-dex-server` и `postgresql` pods находятся в `Running`, migrations `Completed`;
- Devtron dashboard проверен через `kubectl port-forward -n devtroncd svc/devtron-service 18091:80`: `http://127.0.0.1:18091/dashboard` отвечает `200`;
- WebTerm `local-devtron-real` provider использует real Devtron session auth (`/orchestrator/api/v1/session`), probe `/orchestrator/devtron/auth/verify/v2` и apps endpoint `/orchestrator/application?clusterIds=1`; current read-only sync даёт `apps=8`, cluster alias `default_cluster -> local`;
- Keycloak/OIDC mapping для Rancher/Devtron пока не включён как реальный shared-platform SSO runtime; проверяемый MVP access model уже зафиксирован в разделе 7.3 и readiness gate `access_model`, а production-only runtime gate `identity_runtime` теперь проверяет WebTerm login gateway: local для dev, LDAP при настроенном `django_auth_ldap`, либо Domain SSO/OIDC с trusted header и HTTPS Keycloak runtime values перед sidebar enablement. Обычный пользователь не логинится отдельно в Rancher/Fleet/Devtron; WebTerm использует backend-held provider credentials и свои feature/admin-session permissions. Local evidence использует bootstrap/local admin только для test foundation setup.

## 15.4. Phase 2: WebTerm backend read-only aggregator

Цель: добавить backend-слой, который читает Rancher/Fleet/Devtron и отдаёт нормализованные данные frontend-у.

Рекомендуемая структура:

```text
kubernetes_ops/
├── models.py
├── permissions.py
├── urls.py
├── views.py
├── serializers.py
├── audit.py
├── sync.py
└── services/
    ├── rancher_client.py
    ├── fleet_client.py
    ├── devtron_client.py
    ├── normalizer.py
    └── ownership.py
```

Если repo policy не хочет новый Django app, допустимый вариант - `servers/services/kubernetes_ops/` + `core_ui` routes. Но bounded app чище: это отдельная capability с собственными models, permissions, sync и tests.

MVP models:

| Model | Назначение |
|---|---|
| `K8sProvider` | Rancher/Devtron endpoint, enabled flag, auth mode, secret ref |
| `K8sCluster` | Normalized cluster id/name/environment/provider refs/labels |
| `K8sNamespace` | Namespace inventory, owner/team/environment labels |
| `K8sWorkloadRef` | Deployment/statefulset/daemonset/pod summary |
| `K8sAppRef` | Devtron/Fleet/app/Helm ownership mapping |
| `K8sFleetBundle` | Fleet bundle, target, readiness, rollout stage |
| `K8sAuditEvent` | WebTerm-visible event for view/deeplink/sync/action request |

Sync model:

```text
run_kubernetes_ops_sync_worker / production scheduler
  -> Rancher clusters/projects/namespaces/workloads
  -> Fleet GitRepo/Bundle/BundleDeployment/HelmOp summary
  -> Devtron apps/environments/deployment status
  -> normalize into WebTerm DB/cache
  -> frontend reads WebTerm API only
```

Текущий implementation slice уже реализует этот read-only inventory path для Rancher namespaces/workloads/pods/services/ingresses:

- migration `0002_k8snamespace_k8sworkloadref` добавляет `K8sNamespace` и `K8sWorkloadRef`;
- migration `0003_k8sevent` добавляет `K8sEvent` для read-only Kubernetes/Rancher events;
- migration `0004_k8snetworkref` добавляет `K8sNetworkRef` для read-only Service/Ingress inventory;
- migration `0005_k8spodref` добавляет `K8sPodRef` для read-only pod runtime inventory: phase, node, pod IP, owner, containers, restarts и images;
- Rancher provider labels могут переопределить `namespaces_path`, `workloads_path`, `pods_path`, `services_path`, `ingresses_path`, `events_path`, optional `pod_logs_path_template` и optional `probe_path`;
- Rancher 2.14+ native Kubernetes proxy paths поддержаны: `/k8s/clusters/local/api/v1/namespaces`, `/k8s/clusters/local/apis/apps/v1/deployments`, `/k8s/clusters/local/api/v1/pods`, `/k8s/clusters/local/api/v1/services`, `/k8s/clusters/local/apis/networking.k8s.io/v1/ingresses`, `/k8s/clusters/local/api/v1/events`;
- native Kubernetes events normalizer обрезает длинные `reportingComponent`/involved fields под DB limits, чтобы real controller names не ломали sync;
- Devtron provider labels могут переопределить `apps_path`, optional `probe_path`, `auth_strategy=devtron_session`, `login_path`, `auth_username`, `session_token_header`, `session_cookie_name` и `cluster_name_map`;
- sync summary, worker heartbeat summary и provider admin panel показывают `namespaces`/`workloads`/`pods`/`services`/`ingresses`/`events` counts;
- cluster detail API предпочитает native Rancher inventory, но сохраняет fallback на Devtron `K8sAppRef`, если native workload rows ещё не пришли.

Не делать:

- browser -> Rancher direct API;
- browser -> Kubernetes API direct;
- one admin kubeconfig for all users;
- sync on every page refresh;
- write actions в первом backend slice.

## 15.5. Phase 3: native WebTerm frontend workspace

Цель: заменить beta onboarding на рабочий read-only cockpit.

Структура:

```text
frontend/src/features/kubernetes/
├── api.ts
├── types.ts
├── pages/
│   ├── KubernetesOverviewPage.tsx
│   ├── KubernetesClustersPage.tsx
│   ├── KubernetesClusterDetailPage.tsx
│   ├── FleetHelmOpsPage.tsx
│   ├── DevtronAppOpsPage.tsx
│   └── KubernetesAuditPage.tsx
└── components/
    ├── ClusterHealthSummary.tsx
    ├── ProviderLinkButton.tsx
    ├── FleetRolloutTable.tsx
    ├── DevtronAppTable.tsx
    ├── OwnershipBadge.tsx
    └── K8sEmptyState.tsx
```

UX states:

| State | Что видит пользователь |
|---|---|
| No provider configured | Настройка недоступна обычному пользователю; admin видит checklist |
| Provider unreachable | Warning banner + last successful sync timestamp |
| No clusters | Empty state с action для admin |
| Healthy | Overview cards, cluster/app/fleet tables, deep links |
| Degraded | Incident-style summary, events/log links, suggested read-only diagnosis |
| Permission denied | Clear access message, no hidden broken actions |

Когда Phase 3 закрыт, можно включить production env:

```text
KUBERNETES_OPS_RELEASE_ENVIRONMENT=production
KUBERNETES_OPS_PRODUCTION_APPROVAL_REF=<approval-id>
KUBERNETES_OPS_READY_FOR_SIDEBAR=true
```

Но только после backend readiness, tests, e2e evidence, external provider/MCP evidence и `release_scope=ready`.

## 15.6. Phase 4: Studio automation и AI Ops

Цель: связать Kubernetes cockpit с уже существующим Studio automation stack.

Использовать текущий подход:

```text
Kubernetes task
  -> capability pack
  -> agent/mcp_call
  -> read-only inspect
  -> analysis
  -> human approval for mutation
  -> MCP/GitOps action
  -> verification
  -> report/audit
```

Первый набор runbooks:

| Runbook | Default mode | Mutating? | Approval |
|---|---:|---:|---:|
| CrashLoop diagnosis | Read-only | No | No |
| Rollout status report | Read-only | No | No |
| Fleet rollout diff summary | Read-only | No | No |
| Restart non-prod workload | Assisted | Yes | Optional by env |
| Restart prod workload | Assisted | Yes | Required |
| Pause/resume Fleet rollout | Assisted | Yes | Required for prod |
| Create GitLab MR for Helm values change | PR-first | Yes, in Git only | Required before MR |

Important: production remediation should prefer GitLab MR/Fleet rollout over direct Kubernetes mutation.

Текущий implementation slice уже закрыл первый read-only entrypoint:

- `POST /api/kubernetes/actions/diagnose/` принимает `app_id` из Kubernetes cockpit;
- backend prefill-ит `cluster`, `namespace`, `kind`, `name`, `team`, `health`, `version` из normalized `K8sAppRef`/`K8sCluster`;
- создаётся только `PipelineDraftSession`, без `Pipeline`, без `PipelineRun`, без runtime execution;
- generated graph использует generic Studio nodes: `trigger/manual`, `agent/mcp_call`, `agent/llm_query`, `output/report`;
- MCP tool строго read-only: `kubernetes_describe_workload`, `permission_mode=READ_ONLY`, `mutates_state=false`, `operation_kind=kubernetes.workload.describe`;
- owned Kubernetes MCP auto-binding выбирается только если он доступен пользователю; иначе draft остаётся `needs_input` с `resource_plan.missing`;
- local/Docker bootstrap выполняется командой `python manage.py ensure_kubernetes_ops_studio_binding --username <staff-user>`; она выдаёт `kubernetes`, `studio_pipelines`, `studio_mcp`, создаёт owned `Kubernetes MCP`, проверяет `tools/list` и требует tool `kubernetes_describe_workload`;
- `studio/skills/kubernetes-safety/SKILL.md` добавлен как runtime policy resource; draft attach-ит `skill_slugs=["kubernetes-safety"]`, поэтому validation больше не падает на missing skill и Kubernetes MCP mutation patterns получают read-only preflight guardrail.
- readiness показывает `studio_automation` как optional operational check: без user context это `manual`, без feature/skill/MCP это `missing`, с tested owned Kubernetes MCP это `ready`; UI выводит этот gate рядом с остальными readiness checks.

## 15.7. Phase 5: controlled write actions

Цель: включить не все actions, а только ограниченный набор с dry-run, approval, audit и verification.

Action lifecycle:

```text
request -> preflight -> diff/preview -> approval -> execute -> verify -> report -> audit
```

Allowed first:

- `k8s.rollout.restart` for deployment/statefulset/daemonset;
- `k8s.workload.scale` for deployment/statefulset/replicaset;
- `k8s.resource.patch` for non-sensitive namespace-scoped resource patch previews;
- `fleet.rollout.pause`;
- `fleet.rollout.resume`;
- `gitops.create_merge_request`;
- `devtron.open_rollback` as deep link, not native rollback execution.

Still blocked:

- delete namespace;
- delete Helm release;
- unrestricted `kubectl apply`;
- node debug;
- port-forward;
- cluster-admin shell;
- editing RBAC through WebTerm.

Current implementation status:

- Admin Mode Phase 4 includes `POST /api/kubernetes/admin/clusters/{cluster_id}/resources/schema-validate/`, `/dry-run-apply/`, runtime-gated `/apply/`, `/patch/`, `/scale/`, `/restart/` and `/delete/`: schema validation reads CRD `openAPIV3Schema` when available and stores only validation metadata, dry-run performs server-side validation only, and native mutations stay disabled by default. When explicitly enabled, native mutations require active approved write session, request reason, scoped namespace/kind/verb and metadata-only audit before calling Rancher/Kubernetes. Normal apply requires a fresh matching dry-run proof; apply dry-run bypass is emergency-only and requires both `KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED=true` and `KUBERNETES_ADMIN_BREAK_GLASS_APPLY_BYPASS_ENABLED=true`, plus an active approved break-glass session with `apply` verb;
- `K8sActionRequest` stores approval-gated action requests with sanitized target, preview, risk tier, execution policy and report fields; scalar request/report text is guarded as well: `reason`, approval/verification summaries, `approval_ref`, and `external_ref` are redacted before storage/response/audit output, while single URL references drop userinfo, query strings and fragments to avoid ticket-link token leakage;
- `POST /api/kubernetes/actions/request-approval/` accepts only the controlled action set, including guarded single-resource delete and guarded single-resource apply through a linked dry-run proof, runs preflight/preview and writes `k8s.action_request.create` audit events;
- unsafe actions like namespace delete, unrestricted YAML apply, node debug, port-forward and cluster-admin shell are rejected and audited as `k8s.action_request.rejected`;
- `POST /api/kubernetes/actions/{action_id}/approve-external/` lets staff record approval for execution outside WebTerm; it requires `approval_ref`, stores only the safe/redacted approval reference and summary, marks the request `approved_external`, writes sanitized audit and keeps `native_execution_enabled=false`;
- `POST /api/kubernetes/actions/execute-approved/` remains fail-closed by default and still records `execution_disabled_by_policy` without calling Kubernetes/Rancher/Fleet/Devtron mutation APIs when native action execution is not explicitly enabled. The first opt-in native paths are limited to `k8s.rollout.restart`, `k8s.workload.scale`, non-sensitive `k8s.resource.patch`, guarded `k8s.resource.delete`, and guarded `k8s.resource.apply`: they require `KUBERNETES_ACTION_REQUEST_NATIVE_EXECUTION_ENABLED=true`, the matching Admin native flag, an already approved action request, and an active approved Admin write session whose verb/namespace/kind scope covers the target workload/resource; delete additionally requires exact confirmation and protected namespace/kind checks; apply additionally requires the manifest again at execution time and reuses the linked dry-run proof through Admin apply, while the approval request stores only proof metadata/fingerprint, not the raw manifest; on success they mark the request `executed_native`, store the linked `K8sAdminAction` id in the report, and still require post-action verification evidence;
- `POST /api/kubernetes/actions/{action_id}/verify-external/` lets staff record the result of an approved action executed outside WebTerm in Rancher/Fleet/Devtron/GitOps or close WebTerm-native execution after post-action checks. For external actions it requires `approved_external`, stores sanitized evidence plus safe/redacted external references and summaries, marks `verified_external` or `verification_failed`, writes sanitized audit, and keeps `native_execution_enabled=false`; for native workload/resource actions it accepts `executed_native`, preserves `native_execution_performed_by_webterm=true`, records `native_verification_recorded=true`, marks the report `verification_plan` as verified/failed, and marks successful evidence as `verified_native`;
- `gitops.create_merge_request` now validates repository/branch/path/change inputs, rejects path traversal and embedded credentials, strips query fragments from repository URLs, and produces a GitLab draft merge-request API payload/title/description/checklist/verification plan without writing to Git or mutating the cluster;
- action lifecycle is fail-closed: terminal requests such as `verified_external`, `verification_failed` and `execution_blocked` cannot be overwritten by later execute/verify calls; rejected transitions are audited and return `action_request_not_pending`;
- `verify_kubernetes_ops_release` now includes an `action_controls` proof inside a rollback transaction: creates approval requests, records external approval, verifies external evidence redaction, proves default native execution is disabled, proves execution is blocked without the opt-in path, proves controlled delete preview requires exact confirmation, proves guarded apply request preview links a dry-run proof without storing raw manifest, proves terminal request reports cannot be overwritten, proves GitLab draft MR payload/template generation without Git writes or cluster mutations, and leaves no persistent action/cluster rows;
- `GET /api/kubernetes/actions/` exposes sanitized action request rows only for the requester by default; staff can use `all=1` and filters for `status`, `action`, `cluster_id`, `risk_tier`, and `limit`.
- `GET /api/kubernetes/actions/{action_id}/status/` and `/report/` expose the sanitized request state only to the requester or staff; other Kubernetes readers receive `request_not_found`, so action/report metadata is not discoverable by UUID guessing.
- `GET /api/kubernetes/actions/{action_id}/report/` returns requester/staff-only sanitized request, report, execution policy, summary and bounded audit `timeline`, so operators can see create -> approve -> verify/reject events without querying the raw audit table or exposing raw tokens from audit payloads.
- Cluster workload UI now exposes `Запрос restart` only for normalized deployment/statefulset/daemonset rows. The button creates the same approval request and shows risk, affected objects, verification checks and `native_execution_enabled=false`; it does not execute a rollout.
- Frontend request panel now follows the safe report path: after `request-approval` it calls `GET /api/kubernetes/actions/{action_id}/report/`, shows `Отчёт и audit`, renders bounded timeline events such as `Заявка создана`, and never exposes native execute controls.
- Staff-only frontend lifecycle controls record external approval and verification through `approve-external` / `verify-external`; they require approval/evidence text, refresh the report timeline, and still never expose `execute-approved` or any native mutation button.
- Live smoke on `http://127.0.0.1:8080/kubernetes/clusters/cluster_1` is green after Docker frontend/backend restart: login as `admin`, click `Запрос restart`, `POST /api/kubernetes/actions/request-approval/` returns `201`, panel shows `PENDING_APPROVAL` and `EXECUTION OFF`, and there is no `Execute` button.

## 15.8. Phase 6: logs, exec и terminal bridge

Цель: дать troubleshooting без превращения WebTerm в опасный root shell.

Order:

1. Pod logs read-only через WebTerm provider/API snapshot.
2. Events/describe/YAML read-only.
3. Limited pod exec only with permission + audit.
4. Session recording/metadata before production exec.
5. Node debug only as break-glass flow.

Terminal decision:

| Capability | MVP | Production later |
|---|---|---|
| logs/watch | WebTerm native read-only snapshot/preview + bounded follow stream + opt-in provider-native continuous log/watch follow | Saved stream evidence and richer live panel UX |
| pod exec | Fail-closed WebTerm bridge + opt-in provider stdout/stderr/status stream behind separate streaming and recording flags; stores only bounded redacted stdin/stdout/stderr events | Restricted provider credentials, terminal transcript UX, retention cleanup and final review UX |
| port-forward | Fail-closed WebTerm bridge + opt-in provider tunnel behind separate tunnel and recording flags: break-glass/session/target allowlist validation, TTL bounds, byte/duration audit; production readiness now requires network-policy evidence, exact non-wildcard targets, protected namespace coverage and <=900s TTL | Live provider evidence and final UX |
| cluster terminal | Fail-closed REST lifecycle plus opt-in WebSocket provider stream: validates break-glass + restricted context, requires recording flag and provider `cluster_terminal_path_template`, stores bounded redacted stdin/stdout/stderr recording events, and keeps production restricted-evidence gates before action/audit/provider side effects | Production live provider evidence, final SRE UX, TTL/audit/post-review polish |
| node debug | Fail-closed REST lifecycle plus opt-in WebSocket provider stream: validates break-glass + node scope/name/reason, requires recording flag and provider `node_debug_path_template`, stores bounded redacted stdin/stdout/stderr recording events, and keeps production restricted-evidence gates before action/audit/provider side effects | Production live provider evidence, final SRE UX, recording and post-review polish |

Текущий implementation slice закрыл bounded WebTerm snapshot, bounded Admin stream bridge, opt-in provider-native continuous log follow, opt-in provider-native continuous watch follow, opt-in provider exec stream, opt-in provider port-forward tunnel, opt-in provider cluster terminal stream и opt-in provider node debug stream; external provider links остаются только staff/admin fallback:

- Devtron app normalizer сохраняет `devtron_app`, `logs`, `history`, `values` links, если provider payload их отдаёт;
- Devtron app detail теперь отдаёт WebTerm-native `delivery_context`: chart/release, deployment history evidence, Helm values preview без raw body, rollback strategy/approval context, logs/debug related pods, staff-only sanitized fallback links и policy `change_path=devtron_rollback_or_deploy`;
- `GET /api/kubernetes/diagnostics/summary/` отдаёт compact read-only triage по cluster/namespace/workload/pod/network из normalized inventory: health severity, node/readiness gaps, restarts, unhealthy namespace/workload/pod counts, warning-event counts, owner/change-path context, safe next steps, WebTerm endpoints and `mutates_state=false` policy; external provider links не включаются, audit хранит только ids/counts/finding totals;
- Rancher event normalizer сохраняет `source`, `severity`, `reason`, `namespace`, involved object, count и timestamps в `K8sEvent`;
- `GET /api/kubernetes/workloads/{id}/describe/` отдаёт read-only describe snapshot из normalized `K8sWorkloadRef`/`K8sAppRef`: target metadata, sanitized labels, policy `mutates_state=false`, blocked actions, manifest preview и related events; external links скрыты для normal users и отдаются только staff/admin как sanitized fallback;
- `GET /api/kubernetes/admin/clusters/{cluster_id}/resources/describe/?session_id=...&api_version=...&kind=...&namespace=...&name=...` отдаёт Admin Mode live read-only describe через backend-held Rancher credentials: identity/spec/status summary, bounded resource Events, related Pods and ReplicaSets when the active session allows those scopes, skipped reasons when it does not, and metadata-only `K8sAdminAction`/audit evidence without raw object/event/pod body;
- `GET /api/kubernetes/pods/{id}/` отдаёт read-only Pod runtime detail из normalized inventory: Pod, owner workload/app, sibling pods, related services/ingresses, related events, restart/container/image summary, logs snapshot pointer and `mutates_state=false` policy; external links скрыты для normal users и отдаются только staff/admin как sanitized fallback;
- `GET /api/kubernetes/pods/{id}/logs/?tail=N` отдаёт bounded read-only pod logs snapshot: максимум 500 lines, redaction строк, policy `streaming=false`, blocked `exec/attach/follow_stream/port_forward/delete/restart/scale/apply_yaml`, audit пишет только metadata без log content;
- `GET /api/kubernetes/admin/clusters/{cluster_id}/logs/?session_id=...&namespace=...&pod=...&tail=N` отдаёт Admin Mode bounded pod logs snapshot через active Admin Mode session и verb `logs`; response/action/audit сохраняют только metadata, не log content;
- `GET /api/kubernetes/admin/clusters/{cluster_id}/watch/?session_id=...&api_version=...&kind=...&namespace=...&limit=N` отдаёт Admin Mode bounded resource watch preview через active Admin Mode session и verb `watch`; response редактирует event objects, action/audit сохраняют только metadata/event count/latest resourceVersion, не raw resource body;
- `ws/kubernetes/admin/logs/{session_id}/` и `ws/kubernetes/admin/watch/{session_id}/` подключены в ASGI routing как первый Admin stream bridge: они проверяют authenticated user + active Admin Mode session, отдают bounded batch или bounded polling follow (`follow=1`, `max_batches`, `poll_interval_seconds`, `idle_timeout_seconds`) и пишут stream start/stop/fail audit metadata без raw body; logs и watch также поддерживают opt-in one-connection provider stream через `provider_stream=continuous` или `provider_stream=1&stream_transport=continuous`, где WebTerm читает несколько sanitized `log_batch`/`watch_batch` из одного открытого provider response, обновляет watch `latest_resource_version` через `BOOKMARK` и закрывает handle на provider EOF/idle timeout; cancel/client disconnect закрывается stop-event с `close_reason=client_disconnect`, а истёкшая или вручную закрытая admin session останавливает follow-loop без следующего provider call с `close_reason=admin_session_expired` или `admin_session_not_active`;
- `ws/kubernetes/admin/exec/{session_id}/` подключён как fail-closed exec bridge: default `KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=false` даёт `native_exec_disabled`; при включении flag bridge требует active approved break-glass session, `exec` verb, namespace/kind scope, reason, protected namespace denylist и command allow/deny policy, пишет `K8sAdminAction`/`K8sAdminRecording`/audit и без `KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED=true` возвращает `exec_blocked`; даже при streaming flag provider stream не стартует без `KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED=true` и возвращает `exec_recording_required` до provider/action side effects; при обоих флагах и `provider_stream=1` WebTerm открывает provider exec stream, отправляет клиенту redacted stdout/stderr/status frames, закрывает provider handle на EOF/idle/disconnect, сохраняет recording policy + metadata counters/status/exit_code и пишет bounded redacted stdin/stdout/stderr events в `K8sAdminRecordingEvent` без raw payload;
- `ws/kubernetes/admin/port-forward/{session_id}/` подключён как fail-closed port-forward bridge: default `KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=false` даёт `native_port_forward_disabled`; при включении native flag bridge требует active approved break-glass session, `port_forward` verb, Pod/Service target, namespace/kind scope, reason, protected namespace denylist, target allowlist, bounded duration and ports, пишет metadata-only `K8sAdminAction`/`K8sAdminRecording`/audit и без `KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED=true` возвращает `port_forward_blocked`; даже при tunnel flag provider tunnel не стартует без `KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED=true` и возвращает `port_forward_recording_required` до provider/action side effects; в production release mode provider tunnel дополнительно блокируется до action/provider side effects без `KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF`, `KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF`, exact non-wildcard `KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS`, default protected namespace coverage и max duration <=900s; при всех gate и `provider_stream=1` WebTerm открывает provider tunnel, передает data frames в base64, закрывает provider handle до финального stopped/error event на EOF/idle/disconnect/cancel и сохраняет recording policy + bytes/status/close metadata без tunnel payload;
- `POST /api/kubernetes/admin/sessions/{session_id}/terminal/start/` и `/terminal/stop/` подключены как fail-closed cluster terminal lifecycle: start требует approved break-glass session + restricted context + reason/recording policy, пишет metadata-only action/recording/audit с retention values и возвращает `execution_blocked`; stop без live terminal возвращает `cluster_terminal_not_running` и audit;
- `POST /api/kubernetes/admin/sessions/{session_id}/node-debug/start/` и `/node-debug/stop/` подключены как fail-closed node debug lifecycle: start требует approved break-glass session + `node` scope + valid node name + reason/recording policy, пишет metadata-only action/recording/audit с retention values и возвращает `execution_blocked`; stop без live debug возвращает `node_debug_not_running` и audit;
- `ws/kubernetes/admin/terminal/{session_id}/` и `ws/kubernetes/admin/node-debug/{session_id}/` подключены как opt-in provider streams: default path без `provider_stream=1` возвращает blocked REST-style response, а provider stream требует matching transport flag, matching recording flag, active approved break-glass session, provider path-template contract, request reason, production `KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF` when required, then sends redacted output frames and stores bounded redacted `stdin`/`stdout`/`stderr` events in `K8sAdminRecordingEvent`;
- native log fetch использует `pod_logs_path_template`, если Rancher provider labels его содержит, иначе падает на default Kubernetes proxy path `/k8s/clusters/{cluster_id}/api/v1/namespaces/{namespace}/pods/{pod_name}/log?tailLines={tail}`; provider-native batch/continuous follow дополнительно использует `pod_logs_stream_path_template`, например Kubernetes proxy `/api/v1/namespaces/{namespace}/pods/{pod_name}/log?follow=1&tailLines={tail}`; REST snapshot, polling follow, provider stream batch and continuous provider stream carry selected `container`, and WebTerm appends `container=...` to Kubernetes log proxy paths when a provider template does not already contain `{container}`; provider endpoint может вернуть JSON object с `lines`, `logs`, `log`, `content` или `data`, либо bounded plain text log body; WebTerm всё равно применяет tail limit, line trimming, redaction и metadata-only audit/action summaries;
- если Rancher provider не привязан к Pod или provider request отдаёт ошибку, endpoint возвращает safe `available=false` и audit event без утечки query/fragment tokens; sanitized fallback links присутствуют только в staff/admin responses;
- cluster detail UI имеет `Describe` action для workload/app rows и показывает этот snapshot без запуска live Kubernetes API call;
- cluster detail UI имеет `Logs` action для pod rows и показывает WebTerm logs snapshot без запуска terminal bridge; staff/admin дополнительно могут видеть fallback links;
- provider, cluster, app/workload и Fleet rows могут хранить absolute `http(s)` fallback links, но public serializers скрывают их от normal users и чистят query/fragment/userinfo/sensitive link keys для staff/admin;
- `POST /api/kubernetes/audit/deeplink/` пишет `k8s.deeplink.open` event и сохраняет URL без query/fragment, чтобы audit не утаскивал tokens;
- Raw text `kubectl describe` execution and real node debug transport are still blocked; WebTerm now has a native Admin live describe API based on read-only provider GET/list calls, not a shell command. Provider-native port-forward tunnel already exists only as a backend opt-in path, and production readiness still separately requires network-policy evidence and exact allowlist; production exec/port-forward/cluster-terminal/node-debug нельзя включать широко до approval/TTL/session-recording/restricted-context/audit/break-glass controls и live provider evidence.

## 15.9. Phase 7: production hardening

Цель: довести модуль до enterprise-ready состояния.

Checklist:

- encrypted provider credentials or external secret manager; [done for provider config: managed provider tokens are encrypted server-side or referenced externally, release `provider_secret_lifecycle` proves plaintext is not in ciphertext or serialized payloads]
- token rotation; [done for managed provider tokens: staff API supports rotate/delete, release `provider_secret_lifecycle` proves rotation and rollback cleanup]
- redaction in logs and audit events; [done: log snapshots/streams redact secret-like lines, audit serializers now fail-safe redact token/password/bearer/connection-string markers and sanitize credentialed URLs; release `audit_redaction` proves rollback cleanup]
- rate limits and sync backoff; [done for periodic sync worker: repeated failed cycles back off up to `KUBERNETES_OPS_SYNC_MAX_BACKOFF_SECONDS` and expose failure streak/next delay in worker summary]
- provider health probes; [done for sync metadata + admin-only live endpoint probe; still requires real production providers to prove green state]
- stale data banners; [done for normalized inventory freshness]
- audit retention policy; [done for `K8sAuditEvent`: `cleanup_kubernetes_ops_audit --apply`, default dry-run, `KUBERNETES_OPS_AUDIT_RETENTION_DAYS=365`]
- permission matrix tests; [done for API surface: `tests/test_kubernetes_ops_permission_matrix.py` covers explicit feature gate, read-only endpoints, admin-only provider actions, Studio diagnosis feature, and `access_policy` metadata]
- CSP/CORS/CSRF review; [done for Kubernetes Ops API posture: readiness `security_review`, CSRF middleware regression tests for unsafe endpoints, bounded CORS/trusted-origin checks, no-iframe MVP mode]
- threat model for terminal/exec/debug; [done for fail-closed MVP: readiness `terminal_safety`, regression tests assert no legacy direct pod exec/attach/debug REST routes, exec and port-forward WebSocket bridges validate and block before stream/tunnel, cluster terminal/node debug REST lifecycle routes validate and block before transport, and report lists threat scenarios plus production prerequisites; native production exec/port-forward/terminal/node-debug remain blocked until those controls are implemented]
- disaster recovery notes for provider outage; [done in `docs/architecture/KUBERNETES_OPS_OPERATIONS.md`: provider outage DR, sync worker recovery, token rotation, rollback/disablement and recovery proof]
- docs for operators and admins; [done: readiness `operator_docs` validates required runbook sections and exposes the runbook path]

---

# 16. Product backlog по модулям

## 16.1. Backend backlog

| Priority | Item | Files/area | Acceptance |
|---:|---|---|---|
| P0 | Architecture guard cleanup | tests | `check_architecture_sizes.py --strict-new` green |
| P0 | Provider config model | `kubernetes_ops/models.py` | Rancher/Devtron providers saved without raw secret exposure |
| P0 | Read-only clients | `services/rancher_client.py`, `fleet_client.py`, `devtron_client.py` | unit tests with mocked responses |
| P0 | Normalized overview API | `/api/kubernetes/overview/` | frontend gets one stable payload |
| P0 | Cluster list/detail API | `/api/kubernetes/clusters/` | supports empty, healthy, degraded |
| P1 | Namespace detail API | `/api/kubernetes/clusters/{cluster_id}/namespaces/{namespace_id}/` | namespace, apps, workloads, pods, network and events in one read-only payload |
| P1 | Workload detail API | `/api/kubernetes/workloads/{workload_id}/` | workload, owner apps, pods, services and events in one read-only payload |
| P1 | Pod detail API | `/api/kubernetes/pods/{pod_id}/` | pod runtime summary, owner workload/app, sibling pods, services and events in one read-only payload |
| P1 | Network detail API | `/api/kubernetes/network/{network_id}/` | service/ingress runtime summary, owner apps, workloads, pods, related network refs and events in one read-only payload |
| P1 | Fleet bundle API | `/api/kubernetes/fleet/bundles/` | shows rollout partitions/readiness |
| P1 | Devtron app API | `/api/kubernetes/devtron/apps/` | app status, env, team, deep links |
| P1 | Audit events | `K8sAuditEvent` | view/deeplink/action request recorded |
| P2 | Action request/approval | `actions/request-approval` | no direct execution without policy |
| P2 | MCP resource binding | Studio integration | Kubernetes cockpit can start draft with context |

## 16.2. Frontend backlog

| Priority | Item | Files/area | Acceptance |
|---:|---|---|---|
| P0 | Move current onboarding into empty-state | `frontend/src/features/kubernetes` | no lost beta UX |
| P0 | Overview page | `KubernetesOverviewPage.tsx` | cluster/app/rollout health visible |
| P0 | Cluster table/detail | pages + components | status, labels, provider links |
| P1 | Fleet HelmOps table | `FleetHelmOpsPage.tsx` | target clusters, status, rollout stage |
| P1 | Devtron AppOps table | `DevtronAppOpsPage.tsx` | app, env, namespace, health, links |
| P1 | Stale provider state | banners/components | last sync and provider error visible |
| P1 | Permission-aware actions | buttons/components | unauthorized actions absent/disabled with reason |
| P2 | Automation entrypoints | Studio links | "Diagnose", "Create runbook", "Open draft" |
| P2 | Visual/e2e coverage | Playwright | screenshots for empty/healthy/degraded |

## 16.3. Security/access backlog

| Priority | Item | Acceptance |
|---:|---|---|
| P0 | Keep `kubernetes` explicit opt-in | Staff users do not get implicit access |
| P0 | Provider secrets never returned to UI | API snapshots contain no tokens/kubeconfig |
| P0 | Read-only service credentials | implemented: `render_kubernetes_ops_readonly_rbac` produces a ServiceAccount/ClusterRole/ClusterRoleBinding manifest with only `get/list/watch`; validator fails on write verbs and exec/attach/port-forward subresources |
| P1 | OIDC group mapping | implemented: `access_model` readiness documents Keycloak groups, WebTerm feature/staff rules, Rancher/Devtron roles and read-only service account constraints |
| P1 | Audit dangerous actions | every prod mutation has actor, reason, target, approval |
| P2 | Terminal threat model | exec/debug/port-forward cannot ship without it |

## 16.4. Studio/automation backlog

| Priority | Item | Acceptance |
|---:|---|---|
| P0 | Keep Kubernetes as capability pack | no new service-specific node family by default |
| P0 | Add `kubernetes-safety` skill/resource | implemented: filesystem skill exists, draft attaches it, tests validate runtime policy metadata |
| P1 | Bind cockpit context to draft | implemented: app row sends `app_id`; draft pre-fills cluster/namespace/workload context |
| P1 | Read-only diagnosis template | implemented: no approval, no mutation, report generated after read-only inspect + analysis |
| P1 | Studio automation readiness | implemented: readiness checks feature flags, safety skill and owned Kubernetes MCP binding without blocking cockpit |
| P2 | Production rollout restart template | implemented: rollout restart action preview contains `production_rollout_restart_template`; release `action_controls` proves approval, verification, report and safe template gates |
| P2 | GitOps MR template | implemented: action request validates repo/branch/path/changes, rejects credentialed repo URLs and path traversal, strips query tokens, and returns a GitLab draft merge-request payload without writing to Git or mutating the cluster |

---

# 17. Контракты данных и API

## 17.1. Normalized objects

Frontend не должен знать детали Rancher/Fleet/Devtron API. Он должен получать WebTerm-owned contracts.

Cluster summary:

```json
{
  "id": "cluster_prod_kz_1",
  "name": "prod-kz-1",
  "environment": "prod",
  "provider": "rancher",
  "health": "degraded",
  "nodes_ready": 8,
  "nodes_total": 9,
  "namespaces": 42,
  "workloads": 311,
  "apps": 47,
  "fleet_bundles": 12,
  "devtron_apps": 35,
  "labels": {
    "region": "kz",
    "tier": "prod"
  },
  "links": {
    "rancher": "https://rancher.company.com/...",
    "devtron": "https://devtron.company.com/..."
  },
  "last_sync_at": "2026-06-29T14:00:00Z"
}
```

App summary:

```json
{
  "id": "app_payments_api_prod_kz_1",
  "name": "payments-api",
  "cluster_id": "cluster_prod_kz_1",
  "namespace": "payments",
  "environment": "prod",
  "owner": "devtron",
  "team": "payments",
  "health": "healthy",
  "version": "2026.06.29-4",
  "links": {
    "devtron_app": "https://devtron.company.com/...",
    "logs": "https://devtron.company.com/..."
  }
}
```

Fleet rollout summary:

```json
{
  "id": "fleet_ingress_nginx",
  "name": "ingress-nginx",
  "source": "gitrepo/platform",
  "target": "prod-*",
  "status": "rolling",
  "ready": 18,
  "desired": 22,
  "partitions": [
    { "name": "dev", "status": "ready", "ready": 4, "desired": 4 },
    { "name": "stage", "status": "degraded", "ready": 2, "desired": 3 },
    { "name": "prod", "status": "paused", "ready": 0, "desired": 15 }
  ],
  "links": {
    "rancher_fleet": "https://rancher.company.com/..."
  }
}
```

## 17.2. API surface

MVP:

```text
GET /api/kubernetes/readiness/
GET /api/kubernetes/overview/
GET /api/kubernetes/clusters/
GET /api/kubernetes/clusters/{cluster_id}/
GET /api/kubernetes/clusters/{cluster_id}/namespaces/
GET /api/kubernetes/clusters/{cluster_id}/namespaces/{namespace_id}/
GET /api/kubernetes/clusters/{cluster_id}/workloads/
GET /api/kubernetes/clusters/{cluster_id}/pods/
GET /api/kubernetes/clusters/{cluster_id}/network/
GET /api/kubernetes/clusters/{cluster_id}/events/
GET /api/kubernetes/workloads/{workload_id}/
GET /api/kubernetes/workloads/{workload_id}/describe/
GET /api/kubernetes/pods/{pod_id}/
GET /api/kubernetes/pods/{pod_id}/logs/?tail=120
GET /api/kubernetes/network/{network_id}/
GET /api/kubernetes/diagnostics/summary/?scope=cluster|namespace|workload|pod|network&cluster_id=...&namespace_id=...&workload_id=...&pod_id=...&network_id=...
GET /api/kubernetes/fleet/bundles/
GET /api/kubernetes/fleet/bundles/{bundle_id}/
GET /api/kubernetes/devtron/apps/
GET /api/kubernetes/devtron/apps/{app_id}/
GET /api/kubernetes/audit/
POST /api/kubernetes/actions/diagnose/
```

Provider config/probe and external fallback deeplink audit are staff/admin-only:

```text
GET /api/kubernetes/providers/
GET /api/kubernetes/providers/{provider_id}/
POST /api/kubernetes/providers/{provider_id}/probe/
POST /api/kubernetes/audit/deeplink/
```

Admin Mode API:

```text
GET  /api/kubernetes/admin/sessions/
POST /api/kubernetes/admin/sessions/
GET  /api/kubernetes/admin/sessions/{session_id}/
POST /api/kubernetes/admin/sessions/{session_id}/approve/
POST /api/kubernetes/admin/sessions/{session_id}/revoke/
POST /api/kubernetes/admin/sessions/{session_id}/close/
POST /api/kubernetes/admin/sessions/{session_id}/review/
POST /api/kubernetes/admin/sessions/{session_id}/restricted-context/
POST /api/kubernetes/admin/sessions/{session_id}/terminal/start/
POST /api/kubernetes/admin/sessions/{session_id}/terminal/stop/
POST /api/kubernetes/admin/sessions/{session_id}/node-debug/start/
POST /api/kubernetes/admin/sessions/{session_id}/node-debug/stop/
GET  /api/kubernetes/admin/actions/
GET  /api/kubernetes/admin/actions/{action_id}/
GET  /api/kubernetes/admin/actions/{action_id}/report/
POST /api/kubernetes/admin/actions/{action_id}/review/
GET  /api/kubernetes/admin/clusters/{cluster_id}/discovery/?session_id=...
GET  /api/kubernetes/admin/clusters/{cluster_id}/resources/?session_id=...&api_version=...&kind=...&label_selector=...&field_selector=...&search=...&limit=...&continue=...
GET  /api/kubernetes/admin/clusters/{cluster_id}/yaml/?session_id=...&api_version=...&kind=...&namespace=...&name=...
GET  /api/kubernetes/admin/clusters/{cluster_id}/resources/detail/?session_id=...&api_version=...&kind=...&namespace=...&name=...
GET  /api/kubernetes/admin/clusters/{cluster_id}/resources/describe/?session_id=...&api_version=...&kind=...&namespace=...&name=...
GET  /api/kubernetes/admin/clusters/{cluster_id}/resources/events/?session_id=...&api_version=...&kind=...&namespace=...&name=...
GET  /api/kubernetes/admin/clusters/{cluster_id}/crds/?session_id=...
GET  /api/kubernetes/admin/clusters/{cluster_id}/nodes/?session_id=...&limit=...
POST /api/kubernetes/admin/clusters/{cluster_id}/nodes/cordon/
POST /api/kubernetes/admin/clusters/{cluster_id}/nodes/uncordon/
POST /api/kubernetes/admin/clusters/{cluster_id}/nodes/drain/
GET  /api/kubernetes/admin/clusters/{cluster_id}/logs/?session_id=...&namespace=...&pod=...&container=...&tail=120
GET  /api/kubernetes/admin/clusters/{cluster_id}/watch/?session_id=...&api_version=...&kind=...&namespace=...
POST /api/kubernetes/admin/clusters/{cluster_id}/resources/schema-validate/
POST /api/kubernetes/admin/clusters/{cluster_id}/resources/dry-run-apply/
POST /api/kubernetes/admin/clusters/{cluster_id}/resources/apply/
POST /api/kubernetes/admin/clusters/{cluster_id}/resources/patch/
POST /api/kubernetes/admin/clusters/{cluster_id}/resources/scale/
POST /api/kubernetes/admin/clusters/{cluster_id}/resources/restart/
POST /api/kubernetes/admin/clusters/{cluster_id}/resources/delete/
ws   /ws/kubernetes/admin/logs/{session_id}/
ws   /ws/kubernetes/admin/watch/{session_id}/
ws   /ws/kubernetes/admin/exec/{session_id}/
ws   /ws/kubernetes/admin/port-forward/{session_id}/
ws   /ws/kubernetes/admin/terminal/{session_id}/
ws   /ws/kubernetes/admin/node-debug/{session_id}/
```

Namespace detail endpoint returns one WebTerm-native read-only namespace context from normalized inventory: sanitized namespace, apps, workloads, pods, services/ingresses, related native/audit events, owner/team/kind summaries, and policy `mutates_state=false`; action/audit stores only cluster/namespace id and related counts. Workload detail endpoint returns one WebTerm-native read-only runtime context from normalized inventory: sanitized workload, owner apps, related Pods, related services/ingresses, related native/audit events, readiness/container/restart summary and policy `mutates_state=false`; action/audit stores only workload id/name/kind/namespace and related counts. Pod detail endpoint returns one WebTerm-native read-only runtime context from normalized inventory: sanitized Pod, owner workloads/apps, sibling Pods, related services/ingresses, related native/audit events, restart/container/image summary, logs snapshot pointer and policy `mutates_state=false`; action/audit stores only pod id/name/namespace and related counts. Network detail endpoint returns one WebTerm-native read-only Service/Ingress context from normalized inventory: sanitized network object, owner apps, related workloads, matching Pods, related services/ingresses, related native/audit events, port/host/endpoint/runtime summary and policy `mutates_state=false`; action/audit stores only network id/name/kind/namespace and related counts. Fleet bundle detail endpoint returns one WebTerm-native read-only GitOps/Fleet context from normalized inventory: sanitized bundle, rollout partitions, related Fleet apps, matching workloads, related native/audit events, health/readiness summary, and policy `mutates_state=false`; action/audit stores only bundle id/name/status and related counts. Devtron app detail endpoint returns one WebTerm-native read-only AppOps context from normalized inventory: sanitized Devtron app, cluster, matching workloads, matching pods, related native/audit events, health/container/restart summary, `delivery_context` for chart/release, deployment history, Helm values preview, rollback and logs/debug links, and policy `mutates_state=false` with `change_path=devtron_rollback_or_deploy`; values bodies are not returned raw and action/audit stores only app id/name/namespace, delivery capability names and related counts. Resource list endpoint supports Kubernetes selectors, search and pagination: `label_selector` -> `labelSelector`, `field_selector` -> `fieldSelector`, local safe `search` over sanitized rows, bounded `limit`, `continue` token, and `include_managed_fields`; action summaries store only selector/search/token presence and counts, not raw selector or search values. Resource detail endpoint combines sanitized live resource, describe identity/health/shape summary, ownership and bounded Events in one WebTerm-native response; it redacts Secret fields plus sensitive strings in status/event messages and stores only counts/flags in `K8sAdminAction` and audit. Resource live describe endpoint adds live identity/spec/status summary, bounded Events, and related Pods/ReplicaSets when session scope allows those read paths; it stores only metadata counts/flags/skipped reasons in action/audit evidence. Resource events endpoint queries Kubernetes/Rancher Events for one resource through a bounded `fieldSelector`, redacts event messages/source metadata, returns only safe event summaries to the browser, and stores only metadata counts in `K8sAdminAction` and audit. Node view endpoint returns a dedicated safe node inventory summary through Rancher proxy: Ready/NotReady, roles, taints, unschedulable state, capacity/allocatable, addresses and nodeInfo, while action/audit evidence stores only node counters. Node maintenance endpoints are break-glass-only: `cordon` and `uncordon` patch Node `spec.unschedulable` only when `KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED=true`; `drain` requires exact confirmation, stays blocked until `KUBERNETES_ADMIN_NODE_DRAIN_EXECUTION_ENABLED=true`, then lists pods by `spec.nodeName`, blocks unsafe DaemonSet/emptyDir/unmanaged/pod-limit/truncated-list plans before cordon/eviction, cordons the node, and uses Kubernetes `policy/v1` Eviction requests so PDBs remain enforced. `schema-validate` reads matching CRD `openAPIV3Schema` through Rancher when available, validates bounded `required`/`type`/`enum`/number rules, returns only validation metadata/errors, does not mutate state, and does not return/store raw manifest body. `dry-run-apply` uses server-side `dryRun=All`, returns sanitized diff metadata, and does not mutate cluster state. `apply`, `patch`, `scale`, `restart`, and `delete` are present as fail-closed backend paths: they return `native_*_disabled` until their matching `KUBERNETES_ADMIN_NATIVE_*_ENABLED=true` flag is set, then still require an active approved write session, matching verb, request reason, and metadata-only audit. Normal apply requires a fresh matching dry-run proof; break-glass dry-run bypass exists only when `KUBERNETES_ADMIN_BREAK_GLASS_APPLY_BYPASS_ENABLED=true` and records `dry_run_bypassed` evidence. `exec` is present as a fail-closed WebSocket bridge: it returns `native_exec_disabled` by default, validates break-glass/session/namespace/command policy when `KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=true`, returns `execution_blocked` unless `KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED=true` and `provider_stream=1` are both present, then still returns `exec_recording_required` before provider/action side effects unless `KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED=true`; when all gates pass it stores recording policy, metadata counters/status/exit_code, and bounded redacted stdin/stdout/stderr transcript events without raw payload. `port-forward` is also present as a fail-closed WebSocket bridge: it returns `native_port_forward_disabled` by default, validates break-glass/session/namespace/target allowlist/port policy when `KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=true`, returns `execution_blocked` unless `KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED=true` and `provider_stream=1` are both present, then still returns `port_forward_recording_required` before provider/action side effects unless `KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED=true`; when all gates pass it stores recording policy plus bytes/status/close metadata without tunnel payload. `terminal/start` and `node-debug/start` are metadata-only fail-closed lifecycle endpoints while their transport flags are disabled. `terminal` and `node-debug` WebSocket provider streams are present behind `provider_stream=1`, the matching transport and recording flags, provider path-template contract, active approved break-glass session, and production restricted-evidence gate; when all gates pass they store bounded redacted stdin/stdout/stderr transcript events and close/fail the linked action/recording on EOF, disconnect, error or session expiry.

Dangerous Admin action evidence can now be closed separately from the session through `POST /api/kubernetes/admin/actions/{action_id}/review/`: staff with `kubernetes_admin_write` can review write actions, staff with `kubernetes_break_glass` can review break-glass actions, and review text/evidence is redacted before storage, audit and report output.

Admin resource registry now covers the common Freelens-style object set for live explorer paths: Namespace, Node, Pod, Service, ConfigMap, Secret, ServiceAccount, PVC/PV, Endpoints, LimitRange, ResourceQuota, Deployment, StatefulSet, DaemonSet, ReplicaSet, Job, CronJob, HPA, PDB, Ingress, NetworkPolicy, EndpointSlice, StorageClass, Role/RoleBinding, ClusterRole/ClusterRoleBinding and CRD. Kubectl aliases such as `ns`, `po`, `svc`, `cm`, `sa`, `pvc`, `pv`, `deploy`, `sts`, `ds`, `rs`, `hpa`, `pdb`, `netpol`, `sc` and `crd` resolve to typed refs, and tests cover namespaced plus cluster-scoped Rancher proxy paths.

Later guarded actions:

```text
POST /api/kubernetes/actions/diagnose/
GET  /api/kubernetes/actions/
POST /api/kubernetes/actions/request-approval/
POST /api/kubernetes/actions/{action_id}/approve-external/
POST /api/kubernetes/actions/execute-approved/
POST /api/kubernetes/actions/{action_id}/verify-external/
GET  /api/kubernetes/actions/{action_id}/status/
GET  /api/kubernetes/actions/{action_id}/report/
```

`request-approval`, requester/staff action list, external `approve-external`, default policy-blocked `execute-approved`, external/native `verify-external`, `status` and `report` endpoints are now present as a safe Phase 5 skeleton. The list/status/report endpoints return sanitized request/report/policy payloads and do not expose other users' action metadata to ordinary readers. The report endpoint includes a bounded sanitized audit timeline plus sanitized request/report/policy summary for the request. The release verifier proves the default contract with a non-persistent `action_controls` smoke: approval preview is generated for restart, scale, non-sensitive patch, guarded dry-run-proof apply and guarded delete, external approval is recorded, external evidence is sanitized, native execution stays disabled by default, execute attempts are blocked without the opt-in path, terminal reports cannot be overwritten, metadata-only rollback plans exist without raw manifest/patch/delete confirmation payload, native verification-plan templates exist for restart/apply without payload storage, auto-verification can close a fresh read-only inventory proof as `verified_native`, production restricted-write gate blocks native writes without `KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF`, and GitOps MR templates are generated as GitLab draft payloads without Git writes, cluster mutations or repository token leakage. WebTerm can record external approval and verification evidence, and the first native action-request execution paths now exist only for rollout restart, workload scale, non-sensitive patch, guarded single-resource apply and guarded single-resource delete behind `KUBERNETES_ACTION_REQUEST_NATIVE_EXECUTION_ENABLED=true` plus the matching Admin write-session gates; apply requests store only dry-run proof metadata/fingerprint and require the manifest again at execute time; successful native execution can now be closed as `verified_native` either by sanitized staff evidence or by `verify_kubernetes_ops_native_actions` when all read-only checks pass, while weak evidence remains `needs_review` and preserves the linked Admin action id plus rollback plan. Broader native execution remains blocked until production live verification/rollback rollout is implemented end to end.

## 17.3. Readiness endpoint

`/api/kubernetes/readiness/` должен объяснять, почему nav ещё нельзя включать.

Example:

```json
{
  "ready_for_sidebar": false,
  "checks": [
    { "id": "architecture_guard", "status": "fail", "detail": "tests/test_ops_agent_memory_patterns.py 533 > 500" },
    { "id": "rancher_provider", "status": "missing" },
    { "id": "devtron_provider", "status": "missing" },
    { "id": "read_only_sync", "status": "missing" },
    { "id": "studio_automation", "status": "manual", "required": false },
    { "id": "frontend_e2e", "status": "manual", "required": false }
  ]
}
```

---

# 18. Как будет выглядеть готовая система

## 18.1. Для оператора

Оператор заходит в WebTerm и видит раздел `Kubernetes Ops` в левой навигации. Первый экран не является marketing page и не является iframe. Это плотный рабочий cockpit:

```text
Kubernetes Ops

[Clusters 12] [Apps 184] [Fleet rollouts 7] [Incidents 3] [Stale providers 0]

Critical / Degraded
prod-kz-1    Degraded    8/9 nodes ready    2 failing apps    Open
prod-eu-1    Warning     14/14 nodes ready   1 paused rollout  Open

Fleet Rollouts
ingress-nginx     stage degraded, prod paused     Show diff
cert-manager      all ready                         Details

Devtron AppOps
payments-api      prod-kz-1     healthy     logs history
billing-worker    prod-eu-1     degraded    diagnose logs
```

## 18.2. Для разработчика

Разработчик не видит cluster-admin tools. Он видит свои apps, логи, deployment history и diagnosis внутри WebTerm:

```text
Devtron AppOps / payments-api

Status: Healthy
Cluster: prod-kz-1
Namespace: payments
Owner: devtron
Last deploy: 2026.06.29-4

[Logs] [Deployment history] [Values] [Create diagnosis draft]
```

Если app деградировал, WebTerm предлагает read-only diagnosis draft. Production rollback не выполняется напрямую: сначала Devtron/GitOps context внутри WebTerm, approval, потом действие в профильной системе или MR. External Devtron UI остаётся fallback для staff/admin.

## 18.3. Для platform/SRE

SRE видит Fleet и cluster-level health:

```text
Fleet HelmOps / ingress-nginx

Source: gitrepo/platform
Target: prod-*
Status: Rolling / prod paused

Partitions:
dev      ready 4/4
stage    degraded 2/3
prod     paused 0/15

[Show diff] [Bundle targets] [Request resume approval]
```

SRE может запросить controlled action, но WebTerm показывает diff/affected clusters/rollback plan до approval. External Rancher/Fleet UI остаётся fallback для staff/admin.

## 18.4. Для admin

Admin видит readiness/config:

```text
Kubernetes Ops / Settings

Rancher provider: connected
Devtron provider: connected
Fleet sync: OK
Last sync: 44s ago
OIDC groups: mapped
Architecture guard: green
Secrets: external refs

[Run read-only sync] [Rotate token] [View audit]
```

---

# 19. Definition of Done и проверки

## 19.1. MVP DoD

MVP считается готовым только если:

- `python scripts\check_architecture_sizes.py --strict-new` зелёный;
- sidebar включается только через backend `ready_for_sidebar` и production env `KUBERNETES_OPS_READY_FOR_SIDEBAR=true`;
- `/api/kubernetes/readiness/` объясняет статус всех dependencies;
- `/api/kubernetes/overview/` отдаёт normalized summary;
- UI показывает empty, healthy, degraded и provider-error states;
- Rancher/Devtron/Fleet links работают;
- provider tokens не попадают в API responses/logs;
- release evidence содержит `normal_user_surface.status=ready` и `secret_read_controls.status=ready`: normal users получают WebTerm-native ответы без provider config/external links, staff/admin fallback links sanitized, Secret lists stay metadata-only, Secret values redacted by default and named reveal is gated;
- обычный staff user без explicit `kubernetes` permission не видит раздел;
- e2e snapshot обновлён с реальным Overview, а не только onboarding;
- документация содержит runbook установки и rollback toggle.

## 19.2. Test matrix

| Layer | Tests |
|---|---|
| Backend unit | clients, normalizer, ownership, permission checks |
| Backend API | readiness, overview, clusters, fleet, devtron, audit |
| Security | no secret leakage, denied access, scoped credentials |
| Frontend unit | tables/cards/empty states/permission-aware buttons |
| E2E | `/kubernetes` hidden without access, visible with access+ready, degraded state screenshot |
| Studio | Kubernetes draft uses `agent/mcp_call`, approval, verification, report |
| Architecture | import-linter and god-file guard |

## 19.3. Release gates

| Gate | Required before |
|---|---|
| Architecture guard green | Any Kubernetes backend merge |
| Read-only sync stable | Sidebar ready flag |
| Preflight evidence artifact ready | Release evidence collection |
| Production release evidence artifact ready | Sidebar ready flag |
| WebTerm-only normal-user surface proof ready | Sidebar ready flag and any multi-user pilot |
| OIDC/RBAC mapping documented | Any multi-user pilot; enforced by readiness `access_model` |
| Audit event model active | Any action request |
| Approval + verification tested | Any mutating action |
| Threat model + recording gates complete | Any production exec/node-debug/port-forward/terminal transport |

## 19.4. Rollout plan

```text
Week 1:
  Sprint 0 cleanup + provider/domain/OIDC decisions

Week 2:
  Rancher/Fleet/Devtron pilot setup + ownership labels

Week 3:
  WebTerm backend read-only sync + normalized APIs

Week 4:
  WebTerm native Overview/Clusters/Fleet/Devtron pages

Week 5:
  Studio diagnosis runbooks + audit + reports

Week 6:
  Guarded non-prod actions, then production approval flow
```

If time is tight, cut scope in this order:

1. Ship Devtron data as WebTerm-native read-only summaries first; keep Devtron links as staff/admin fallback.
2. Ship Fleet read-only without pause/resume actions.
3. Ship logs as WebTerm bounded snapshots where possible; keep Devtron/Rancher links as fallback before streaming.
4. Keep all mutations out of MVP.

Do not cut:

- explicit opt-in;
- no admin kubeconfig;
- architecture guard;
- read-only first;
- one Helm release owner.

---

# 20. Источники

1. WebTerm GitHub repository: <https://github.com/LLprod39/WebTerm/tree/test>
2. Rancher GitHub repository: <https://github.com/rancher/rancher>
3. Rancher Manager Overview: <https://ranchermanager.docs.rancher.com/getting-started/overview>
4. Rancher Cluster and Project Roles: <https://ranchermanager.docs.rancher.com/how-to-guides/new-user-guides/authentication-permissions-and-global-configuration/manage-role-based-access-control-rbac/cluster-and-project-roles>
5. Rancher Helm Charts and Apps: <https://ranchermanager.docs.rancher.com/how-to-guides/new-user-guides/helm-charts-in-rancher>
6. Fleet CRD Reference: <https://fleet.rancher.io/ref-crds>
7. Fleet HelmOp documentation: <https://fleet.rancher.io/helm-ops>
8. Fleet GitRepo Targets documentation: <https://fleet.rancher.io/gitrepo-targets>
9. Devtron GitHub repository: <https://github.com/devtron-labs/devtron>
10. Devtron Docs: <https://docs.devtron.ai/>
11. Devtron Application Management: <https://docs.devtron.ai/docs/user-guide/app-management>
12. Devtron Infrastructure Management: <https://docs.devtron.ai/docs/user-guide/infra-management>
13. Devtron Chart Store / Helm chart deployment: <https://docs.devtron.ai/docs/user-guide/deploy-chart>
14. Devtron Cluster Terminal: <https://docs.devtron.ai/docs/user-guide/resource-browser/cluster-terminal>
15. Devtron Global Configurations and SSO/RBAC index: <https://docs.devtron.ai/docs/user-guide/global-configurations>
16. WebTerm local code references checked on 30 June 2026: `kubernetes_ops/views.py`, `kubernetes_ops/urls.py`, `frontend/src/pages/KubernetesPage.tsx`, `frontend/src/pages/kubernetes-page/kubernetesPageSections.tsx`, `frontend/src/api/kubernetes.ts`, `frontend/src/components/AppSidebar.tsx`, `frontend/src/App.tsx`, `core_ui/models.py`, `core_ui/access.py`, `studio/pilot_capability_packs.py`, `docs/reports/WEBTERM_AUDIT_DEVELOPMENT_PLAN.md`, `docs/architecture/STUDIO_OPS_AUTOMATION_PLATFORM_PLAN.md`.
