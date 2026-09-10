# Implementation plan

Цель — новый frontend, функциональный паритет с backend. Работа продолжается до закрытия применимых gates.

1. Исследование product/contracts/access/realtime; зафиксировать baseline без изменения пользовательских backend diffs.
2. React/TS/Vite project, tokens/primitives, session/CSRF/API, guards, единый shell, command palette.
3. Overview и Servers: inventory -> create/detail -> capabilities -> terminal/files/operations/monitoring.
4. Automation: playbooks/workspace/run, Studio graph/drafts/trigger/history/skills.
5. Intelligence: agents execution/reports, Operator Chat, MCP, memory, MARS.
6. Kubernetes: реальные discovery/read/actions/admin workflows без выдуманных capabilities.
7. Governance: access inheritance, projects, audit, integrations/settings/plugins.
8. Storybook + meaningful contract/unit/E2E smoke; сборка, lint, typecheck.
9. Real backend smoke, authenticated browser QA, keyboard/light-dark/laptop проверки.
10. Полная сверка inventory, remediation, FINAL_PARITY_REPORT с evidence и внешними runtime gates.

Параллельная разработка разделена по feature directories/API modules. Backend изменён только для трёх объективных совместимых исправлений, перечисленных в API_CONTRACT_MAP. Локальный runtime использует существующее окружение; внешний SSH/cluster/AI launch требует явного тестового target, не используется произвольный production target.

Rollback: frontend build заменяется предыдущим артефактом на уровне deployment; backend и данные не мигрируются. Существующие удаления frontend не отменяются. Никаких действий с remote Git/deployment без отдельного запроса.
