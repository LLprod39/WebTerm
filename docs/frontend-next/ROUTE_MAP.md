# Route map

| Пространство | Пути |
|---|---|
| Auth | /login |
| Overview | / |
| Infrastructure | /infrastructure/servers, /infrastructure/servers/:id, /infrastructure/terminal/:id, /infrastructure/monitoring, /infrastructure/kubernetes |
| Automation | /automation/playbooks, /automation/playbooks/:id, /automation/pipelines, /automation/pipelines/:id, /automation/runs, /automation/drafts, /automation/schedules |
| Intelligence | /intelligence/agents, /intelligence/agents/:id, /intelligence/runs/:id, /intelligence/chat, /intelligence/chat/:id, /intelligence/skills, /intelligence/mcp, /intelligence/memory, /intelligence/mars |
| Governance | /governance/users, /governance/groups, /governance/permissions, /governance/audit, /governance/plugins |
| Settings | /settings/general, /settings/ai, /settings/access, /settings/identity, /settings/readiness, /settings/limits |
| Personal workspace | /settings/workspace |
| Team activity | /governance/activity |
| Agent profiles / operations | /intelligence/profiles; дежурства, планы, расписания и dispatch доступны в рабочих панелях Agents/Chat |
| Kubernetes workflow | /infrastructure/kubernetes/providers, sessions, requests, delivery, activity; detail routes экспортируются kubernetes/routes.tsx |

Точная реализация routes экспортируется feature modules. Guards проверяют effective feature + объектные capabilities. Неизвестный путь даёт понятную 404 со ссылкой на обзор. После повторного входа возвращаем только безопасный внутренний путь. Deep links backend адаптируются через совместимые redirects.
