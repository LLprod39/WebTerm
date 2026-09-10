# Инвентарь возможностей

Набор функций выведен из backend URL, views, serializers и моделей. Подробные payload и методы — research/*_CONTRACTS.md. Наличие endpoint не означает подтверждённую работоспособность окружения.

| ID | Возможность | Основной контракт | Владелец реализации |
|---|---|---|---|
| AUTH | Session, CSRF, login/logout, expiry | /api/auth/* | app |
| PROJECTS | Выбор проекта, membership, роли | /api/projects/ | governance |
| OVERVIEW | Health, alerts, recent activity | /servers/api/monitoring/dashboard/ | infrastructure |
| SERVERS | Inventory/create/edit/delete, groups | /servers/api/frontend/bootstrap/, create, get/update/delete | infrastructure |
| SERVER_ACCESS | Share, owner transfer, trusted host keys | /servers/api/{id}/shares/, security | infrastructure |
| TERMINAL | SSH sessions, resize, reconnect, clipboard, focused mode | /ws/servers/{id}/terminal/ | infrastructure |
| TERMINAL_EDITOR | Сохранённые настройки, nano/vim interception, remote editor/sudo, AI approvals/replies/report | /api/terminal/preferences/, terminal WS ai_*/agent_* | infrastructure |
| SERVER_GROUP_OPS | Membership roles/revoke, context rules, server moves, durable bulk metadata | /servers/api/groups/* | infrastructure |
| SERVER_FILES | SFTP list/read/write/upload/download/chmod/chown | /servers/api/{id}/files/* | infrastructure |
| SERVER_OPS | Services/processes/logs/docker/network/packages | /servers/api/{id}/ui/* | infrastructure |
| MONITORING | Metrics/history, alerts, watchers, refresh | /servers/api/monitoring/*, health/* | infrastructure |
| PLAYBOOKS | Catalog, revisions, files, import/export, sharing, validation, bindings | /servers/api/playbooks/* | automation |
| PLAYBOOK_RUNS | Preflight, launch, log, cancel, host report | /servers/api/playbooks/runs/* | automation |
| PIPELINES | Catalog, visual graph, validation, save, execution | /api/studio/pipelines/* | automation |
| STUDIO_RUNS | State, node traces, log, cancel, approvals | /api/studio/runs/* | automation |
| DRAFTS | Composition, review, compile and launch | /api/studio/drafts/* | automation |
| SCHEDULES | Triggers, execution profiles | /api/studio/triggers/* | automation |
| SKILLS | Catalog, create/edit, files and workflow | /api/studio/skills/* | automation |
| KUBERNETES | Providers, clusters, namespace, workloads, pods, logs/events, actions | /api/kubernetes/* | infrastructure |
| K8S_ADMIN | Sessions, discovery, YAML, dry-run/apply/patch/scale/delete, recordings | /api/kubernetes/admin/* | infrastructure |
| K8S_REQUESTS | Requests/approvals, controlled native execution, verification | /api/kubernetes/* action requests | infrastructure |
| K8S_DELIVERY | Helm ownership, Fleet, Devtron, diagnosis drafts | /api/kubernetes/* | infrastructure |
| AGENTS | Catalog/config/run/stop, plans, reports and artifacts | /servers/api/agents/* | intelligence |
| AGENT_PROFILES | Studio AgentConfig CRUD and explicit sharing | /api/studio/agents/* | intelligence |
| AGENT_OPERATIONS | Duty briefs, plan tasks, scheduler, dispatch and stale cleanup | /servers/api/agents/* | intelligence |
| CHAT | History, realtime turn, tools, confirmations, context | /api/assistant/chats/, /ws/operator/{id}/ | intelligence |
| MCP | Catalog, configuration, tools and permissions | /api/studio/mcp/* | intelligence |
| MEMORY | Owner snapshots, search, knowledge, admin lifecycle | /servers/api/{id}/memory/* | intelligence |
| MARS | Interview, approved plan, execution and artifacts | /api/mars/* | intelligence |
| USERS | Users/create/edit/delete/password/profile | /api/access/users/* | governance |
| GROUPS | Access groups, members, permission inheritance | /api/access/groups/* | governance |
| PERMISSIONS | Effective/explicit tri-state, provenance | /api/access/permissions/* | governance |
| AUDIT | Who/action/entity/time/result/details, filters | /api/settings/activity/* | governance |
| USER_ACTIVITY | User activity, active in last 5min, AI usage | /api/admin/dashboard/, activity/sessions | governance |
| WORKSPACE_PREFS | Personal section order/column/visibility | /api/dashboard-custom/layout/* | governance |
| SETTINGS | General, AI routing/keys, limits, LDAP/SSO, readiness | /api/settings/* | governance |
| AI_CONNECTIONS | CLI connections/auth/grants/pools/purpose models | backend AI provider APIs | governance |
| PLUGINS | Catalog/install/settings/lifecycle/private packages | /api/plugins/* | governance |

Полное сопоставление подтверждается финальным parity report. Нельзя считать всю строку PASS только по наличию страницы.
