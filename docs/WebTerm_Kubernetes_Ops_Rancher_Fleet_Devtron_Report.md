# WebTerm Kubernetes Ops

## Интеграция Rancher + Fleet + Devtron

**Отчёт по архитектуре, UX, безопасности и плану внедрения**  
**Дата:** 29 июня 2026  
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

WebTerm не должен пытаться заменить Rancher или Devtron. Он должен стать **единым рабочим cockpit-слоем**, который собирает статусы, даёт быстрые переходы, запускает безопасные runbook-и, ведёт аудит и связывает Kubernetes Ops с существующими возможностями WebTerm: terminal, monitoring, Studio pipelines, permissions и audit.

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

Главная идея: **не переписывать Rancher или Devtron внутри WebTerm**. WebTerm должен быть единой рабочей панелью, которая:

- показывает статусы кластеров, приложений и rollout-ов;
- даёт быстрые переходы в Rancher/Devtron;
- запускает безопасные runbook-и;
- собирает audit trail;
- связывает Kubernetes Ops с существующими Studio/Terminal/Monitoring возможностями;
- добавляет approvals и AI/Ops-автоматизацию поверх готовых Kubernetes-платформ.

Rancher лучше оставить **source of truth** по Kubernetes-кластерам, пользователям, проектам, namespaces, RBAC, lifecycle, monitoring/logging и platform add-ons.

Fleet использовать для **корпоративного GitOps/HelmOps** на множество кластеров.

Devtron использовать для команд разработки и AppOps: **Helm-приложения, values.yaml, deployment history, CI/CD, rollback, logs и debugging**.

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
| Login | Пользователь проходит OIDC/SSO в WebTerm, Rancher и Devtron | WebTerm не хранит пароли и не подменяет identity пользователя |
| Status sync | WebTerm backend читает summary из Rancher/Fleet/Devtron read-only токеном | Минимальные права, меньше риск случайных изменений |
| Write actions | Опасные действия идут через Rancher/Fleet/Devtron или через approved runbook в WebTerm | Есть RBAC, approval и audit |
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

[Open in Rancher] [Open in Devtron] [View Logs]
[Open K8s Terminal] [Run Approved Automation]

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

[Continue rollout] [Pause] [Open in Rancher] [Show diff]
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
| MVP | WebTerm показывает карточки, ссылки `Open in Rancher` / `Open in Devtron` и базовый status sync | Быстро, мало риска, нет борьбы с iframe/CSP | Меньше “вау-эффекта” внутри WebTerm | Низкая/средняя |
| Embedded | Открываем Rancher/Devtron в iframe или full-screen reverse proxy | Похоже на встроенную панель | CSP, cookies, OIDC redirects, WebSocket upgrade, X-Frame-Options | Средняя/высокая |
| Native | WebTerm сам рисует Kubernetes Ops UI, backend читает API Rancher/Fleet/Devtron | Лучший UX, единый audit, свои approvals и automation | Нужно больше backend/frontend кода | Высокая |

## Рекомендованный путь

Начать с:

```text
MVP + deep links + read-only status sync
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
| Platform add-ons | Fleet/Rancher | cert-manager, ingress-nginx, monitoring, logging, external-dns, longhorn, istio | Fleet rollout status + Open in Rancher |
| Security/compliance | Fleet/Rancher | NeuVector, Kubewarden, policy agents, compliance scans | Статус + incidents + restricted actions |
| Product apps | Devtron | backend/frontend/microservices/workers/internal tools | Devtron AppOps cards + logs/history/rollback links |
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
Celery/periodic task
  -> sync Rancher clusters every 60s
  -> sync Fleet bundles every 30s
  -> sync Devtron apps every 60s
  -> write normalized status into WebTerm DB/cache
  -> frontend reads from WebTerm API
```

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

Эта секция привязывает план к реальному состоянию `C:\WebTrerm` на 29 июня 2026, а не к абстрактной схеме.

## 14.1. Что уже есть

| Область | Факт в repo | Вывод для плана |
|---|---|---|
| Навигация | `frontend/src/components/AppSidebar.tsx` содержит `KUBERNETES_NAV_READY = false` | Раздел правильно скрыт до готовности; не включать sidebar до backend/readiness |
| Route | `frontend/src/App.tsx` уже держит `/kubernetes` за `<FeatureGate feature="kubernetes">` | URL существует, но доступ должен оставаться feature-gated |
| Страница | `frontend/src/pages/KubernetesPage.tsx` показывает beta onboarding и статус `Backend не подключён` | Первый production шаг - заменить onboarding на read-only workspace |
| Feature access | `core_ui/models.py` содержит `("kubernetes", "Kubernetes")` и `EXPLICIT_OPT_IN_FEATURES = {"kubernetes", "mars"}` | Даже staff не должен получить Kubernetes автоматически |
| Access engine | `core_ui/access.py` уже централизует `feature_allowed_for_user()` и `build_user_access_payload()` | Использовать существующую модель доступа, не делать отдельный Kubernetes auth path |
| Studio automation | `studio/pilot_capability_packs.py` уже описывает `kubernetes_describe_workload`, `kubernetes_rollout_restart`, `kubernetes_rollout_status` | Kubernetes actions должны идти через MCP/capability pack, approval и verification |
| Tests | Есть `frontend/src/pages/KubernetesPage.test.tsx`, visual snapshot и Studio tests для Kubernetes skeleton | Новый модуль обязан расширять эти тесты, а не обходить их |
| Existing architecture plan | `docs/reports/WEBTERM_AUDIT_DEVELOPMENT_PLAN.md` фиксирует `Kubernetes Read-Only First` | MVP обязан быть read-only: namespaces/workloads/logs/events/describe/AI diagnosis |

## 14.2. Текущий blocker перед большим модулем

Команда:

```powershell
python scripts\check_architecture_sizes.py --strict-new
```

Текущий результат:

```text
Import boundaries: SUCCESS
Architecture Fitness Check: FAILURE
tests\test_ops_agent_memory_patterns.py
GOD-FILE: 533 > 500
```

Это не Kubernetes-файл, но это важный delivery gate. Перед добавлением нового production-модуля нужно вернуть guard в зелёное состояние. Иначе Kubernetes Ops усилит уже существующий архитектурный долг.

## 14.3. Рабочая позиция

Текущий WebTerm готов к Kubernetes Ops как к **новой bounded capability**, но ещё не готов как production Kubernetes control plane.

Правильное состояние перед включением sidebar:

```text
KUBERNETES_NAV_READY = false
  until:
    architecture guard green
    backend read-only endpoints implemented
    provider credentials stored safely
    UI overview renders real normalized data
    tests/e2e cover empty, healthy and degraded states
```

---

# 15. Полноценный implementation plan

## 15.1. Принципы реализации

1. **Read-only first.** Первый релиз только читает: clusters, namespaces, workloads, pods, services, ingress, events, logs, Fleet bundles, Devtron apps.
2. **Provider source of truth.** Rancher владеет cluster/RBAC/lifecycle, Fleet владеет platform GitOps/HelmOps, Devtron владеет AppOps/CI/CD/debug UX.
3. **WebTerm не хранит admin kubeconfig.** Только scoped credentials, provider tokens с минимальными правами и audit.
4. **One release -> one owner.** Fleet и Devtron не должны одновременно менять один Helm release.
5. **PR/GitOps first для плановых изменений.** Production mutations идут через GitOps/MR/approval, а не через свободный `kubectl apply`.
6. **MCP/capability pack first для Studio.** Не добавлять десятки `kubernetes/*` нод, пока `agent/mcp_call` + schema + policy покрывает workflow.
7. **No iframe as core UX.** Deep links и native summaries - основной путь; iframe только как optional console после CSP/cookie/OIDC проверки.
8. **Deny by default.** Если WebTerm не может доказать право на действие, кнопка не показывается или действие блокируется.

## 15.2. Phase 0: readiness и cleanup gate

Цель: подготовить repo и внешний контур так, чтобы Kubernetes Ops не стартовал поверх незакрытого долга.

Задачи:

| Task | Где | Результат |
|---|---|---|
| Split god-file test | `tests/test_ops_agent_memory_patterns.py` | `check_architecture_sizes.py --strict-new` проходит |
| Зафиксировать флаг готовности | `frontend/src/components/AppSidebar.tsx` | `KUBERNETES_NAV_READY` остаётся `false` |
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

Цель: поднять Rancher/Fleet/Devtron как внешние системы, прежде чем WebTerm начнёт агрегировать их данные.

Задачи:

| Система | Что сделать | Done when |
|---|---|---|
| Keycloak/OIDC | Единый realm/client/groups для WebTerm, Rancher, Devtron | Пользователь проходит SSO во все три системы |
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
periodic sync
  -> Rancher clusters/projects/namespaces/workloads
  -> Fleet GitRepo/Bundle/BundleDeployment/HelmOp summary
  -> Devtron apps/environments/deployment status
  -> normalize into WebTerm DB/cache
  -> frontend reads WebTerm API only
```

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

Когда Phase 3 закрыт, можно поменять:

```ts
const KUBERNETES_NAV_READY = true;
```

Но только после backend, tests и e2e.

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

## 15.7. Phase 5: controlled write actions

Цель: включить не все actions, а только ограниченный набор с dry-run, approval, audit и verification.

Action lifecycle:

```text
request -> preflight -> diff/preview -> approval -> execute -> verify -> report -> audit
```

Allowed first:

- `k8s.rollout.restart` for deployment/statefulset/daemonset;
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

## 15.8. Phase 6: logs, exec и terminal bridge

Цель: дать troubleshooting без превращения WebTerm в опасный root shell.

Order:

1. Pod logs read-only через provider/API/deep link.
2. Events/describe/YAML read-only.
3. Limited pod exec only with permission + audit.
4. Session recording/metadata before production exec.
5. Node debug only as break-glass flow.

Terminal decision:

| Capability | MVP | Production later |
|---|---|---|
| logs | WebTerm native read-only + Devtron link | WebTerm stream with saved audit metadata |
| pod exec | Devtron link | WebTerm bridge with approval/session recording |
| cluster terminal | No | SRE-only, TTL, audit, restricted contexts |
| node debug | No | break-glass only |

## 15.9. Phase 7: production hardening

Цель: довести модуль до enterprise-ready состояния.

Checklist:

- encrypted provider credentials or external secret manager;
- token rotation;
- redaction in logs and audit events;
- rate limits and sync backoff;
- provider health probes;
- stale data banners;
- audit retention policy;
- permission matrix tests;
- CSP/CORS/CSRF review;
- threat model for terminal/exec/debug;
- disaster recovery notes for provider outage;
- docs for operators and admins.

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
| P0 | Read-only service credentials | no write verbs needed for MVP |
| P1 | OIDC group mapping | WebTerm/Rancher/Devtron roles documented |
| P1 | Audit dangerous actions | every prod mutation has actor, reason, target, approval |
| P2 | Terminal threat model | exec/debug/port-forward cannot ship without it |

## 16.4. Studio/automation backlog

| Priority | Item | Acceptance |
|---:|---|---|
| P0 | Keep Kubernetes as capability pack | no new service-specific node family by default |
| P0 | Add `kubernetes-safety` skill/resource | current tests no longer report missing safety skill |
| P1 | Bind cockpit context to draft | cluster/namespace/workload prefilled from page |
| P1 | Read-only diagnosis template | no approval needed, report generated |
| P2 | Production rollout restart template | approval + verification + report required |
| P2 | GitOps MR template | patch Helm values in Git, not direct prod apply |

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
GET /api/kubernetes/providers/
GET /api/kubernetes/clusters/
GET /api/kubernetes/clusters/{cluster_id}/
GET /api/kubernetes/clusters/{cluster_id}/namespaces/
GET /api/kubernetes/clusters/{cluster_id}/workloads/
GET /api/kubernetes/clusters/{cluster_id}/events/
GET /api/kubernetes/fleet/bundles/
GET /api/kubernetes/devtron/apps/
GET /api/kubernetes/audit/
```

Later guarded actions:

```text
POST /api/kubernetes/actions/diagnose/
POST /api/kubernetes/actions/request-approval/
POST /api/kubernetes/actions/execute-approved/
GET  /api/kubernetes/actions/{action_id}/status/
GET  /api/kubernetes/actions/{action_id}/report/
```

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
    { "id": "frontend_e2e", "status": "missing" }
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
cert-manager      all ready                         Open in Rancher

Devtron AppOps
payments-api      prod-kz-1     healthy     logs history open
billing-worker    prod-eu-1     degraded    diagnose logs
```

## 18.2. Для разработчика

Разработчик не видит cluster-admin tools. Он видит свои apps, логи, history и links в Devtron:

```text
Devtron AppOps / payments-api

Status: Healthy
Cluster: prod-kz-1
Namespace: payments
Owner: devtron
Last deploy: 2026.06.29-4

[Open in Devtron] [Logs] [Deployment history] [Create diagnosis draft]
```

Если app деградировал, WebTerm предлагает read-only diagnosis draft. Production rollback не выполняется напрямую: сначала Devtron/GitOps context, approval, потом действие в профильной системе или MR.

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

[Show diff] [Open in Rancher] [Request resume approval]
```

SRE может запросить controlled action, но WebTerm показывает diff/affected clusters/rollback plan до approval.

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
- `KUBERNETES_NAV_READY` включается только после backend readiness;
- `/api/kubernetes/readiness/` объясняет статус всех dependencies;
- `/api/kubernetes/overview/` отдаёт normalized summary;
- UI показывает empty, healthy, degraded и provider-error states;
- Rancher/Devtron/Fleet links работают;
- provider tokens не попадают в API responses/logs;
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
| OIDC/RBAC mapping documented | Any multi-user pilot |
| Audit event model active | Any action request |
| Approval + verification tested | Any mutating action |
| Threat model complete | Any exec/node-debug/port-forward |

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

1. Leave Devtron as deep links only.
2. Ship Fleet read-only without pause/resume actions.
3. Ship logs as Devtron links before WebTerm streaming.
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
16. WebTerm local code references checked on 29 June 2026: `frontend/src/pages/KubernetesPage.tsx`, `frontend/src/components/AppSidebar.tsx`, `frontend/src/App.tsx`, `core_ui/models.py`, `core_ui/access.py`, `studio/pilot_capability_packs.py`, `docs/reports/WEBTERM_AUDIT_DEVELOPMENT_PLAN.md`, `docs/architecture/STUDIO_OPS_AUTOMATION_PLATFORM_PLAN.md`.
