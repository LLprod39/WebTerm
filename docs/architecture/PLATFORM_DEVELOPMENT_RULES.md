# WebTrerm Platform Development Rules

Last reviewed: 2026-06-21

These rules are the shared working contract for changing WebTrerm without damaging the platform architecture.

Use this file before adding or changing:

- pages and navigation;
- dashboard widgets;
- API endpoints;
- backend services;
- Studio pipelines/nodes;
- terminal and AI assistant behavior;
- agent tools;
- server operations;
- integrations;
- permissions;
- settings;
- models and migrations.

The goal is practical: every change should have a clear owner, a narrow code location, permission/safety coverage when needed, and focused verification.

## 1. Default Workflow

Before coding:

1. Identify the owning domain.
2. Find the existing pattern in that domain.
3. Decide whether this is UI, API, service, model, runtime, or integration work.
4. List the files that should change.
5. List the checks that will prove it works.

During coding:

1. Keep the change scoped.
2. Add behavior to focused modules, not compatibility shells.
3. Preserve public imports and routes unless the task is explicitly a breaking change.
4. Add or update tests around the touched behavior.
5. Update docs if the public contract changes.

Before finishing:

1. Run focused tests.
2. Run build/lint when frontend changed.
3. Run architecture guard for architecture-sensitive changes.
4. Check for stale docs/path references.
5. Report what was verified and what was not.

## 2. Ownership Rules

| Area | Owner |
| --- | --- |
| Auth, users, access, settings, admin metrics | `core_ui` |
| Shared LLM/runtime/safety/kernel contracts | `app` |
| Generic tools and execution policy | `app.tools`, `app.agent_kernel`, `app.execution_policy` |
| Servers, terminal, SSH, monitoring, server memory | `servers` |
| Studio pipelines, nodes, MCP, skills, templates | `studio` |
| Frontend app shell and pages | `frontend/src` |
| Deployment/settings | `web_ui`, deploy files, docs |

If work touches two domains, create a contract/provider/hook at the boundary instead of importing one feature app into another.

## 3. Hard Architecture Rules

### R-001: Respect Import Boundaries

Do not create direct imports that violate `.importlinter`.

Important rules:

- `servers` must not import `studio`.
- `studio` must not import `servers`.
- `app.core` must not import feature apps.
- `app.tools` must not import feature apps.
- `core_ui` must not own server or Studio business logic.

Use instead:

- provider protocols;
- gateway interfaces;
- registry injection;
- Django signals;
- service adapters;
- HTTP/API boundaries;
- explicit dependency injection.

### R-002: Do Not Grow Compatibility Files

Compatibility files should stay thin.

Avoid adding new product behavior directly to:

- compatibility barrels;
- `_views_all.py` shims;
- large route components;
- `frontend/src/lib/api.ts`;
- `SSHTerminalConsumer`;
- static mega-catalogs;
- broad "utils" files.

Allowed:

- re-export;
- adapter call;
- one-line registry bridge;
- migration shim with clear removal direction.

### R-003: One Feature, One Owner

Do not scatter one feature across unrelated domains unless there is a real boundary.

Bad:

- add server business logic in `studio`;
- add Studio runtime logic in `servers`;
- add API calls inside React components;
- add permission rules only in frontend.

Good:

- service in owning app;
- thin view/API;
- typed frontend API module;
- focused UI component;
- targeted tests.

### R-004: Public Contract Before Runtime

If other parts of the system will call it, define the contract first:

- request/response shape;
- permissions;
- error behavior;
- audit behavior;
- feature flag/access behavior;
- tests.

## 4. Safety Rules

### R-005: Dangerous Operations Need Policy

This applies to:

- SSH commands;
- file writes;
- sudo;
- package/service/docker operations;
- MCP calls;
- external webhooks;
- email/Telegram/notifications;
- pipeline execution;
- agent tools;
- AI-generated actions.

Every risky path needs:

- permission/capability check;
- risk classification;
- redaction;
- audit event;
- approval/preflight/verification where required.

### R-006: Secrets Never Leave Raw

Do not expose secrets in:

- frontend payloads;
- logs;
- reports;
- LLM prompts;
- memory snapshots;
- audit metadata;
- screenshots;
- docs/examples.

Show only:

- configured/missing;
- redacted value;
- secret key name;
- health status;
- safe error summary.

### R-007: Frontend Gates Are Not Security

Frontend `FeatureGate` improves UX, but backend must enforce access too.

Every protected backend endpoint needs backend permission checks.

### R-008: AI Output Is Untrusted

AI suggestions, generated commands, generated pipeline graphs, and generated reports must pass validation before execution or persistence.

## 5. Backend Rules

### Views

Views should:

- parse request;
- authorize;
- call service/helper;
- return response.

Views should not contain large business logic.

### Services

Services should:

- own business behavior;
- be testable without full UI;
- avoid hidden global state;
- receive dependencies explicitly when practical.

### Models

Model changes require:

- migration;
- `makemigrations --check --dry-run` before claiming no schema change;
- focused API/model tests;
- backward-compatible defaults when data exists.

### Registries

Registries should:

- fail duplicate ids;
- fail unknown ids where runtime correctness matters;
- expose snapshot/restore for tests if global;
- be initialized in app startup or explicit bootstrap, not random imports.

## 6. Frontend Rules

### API Calls

New API calls go into domain modules:

```text
frontend/src/api/
```

Do not expand `frontend/src/lib/api.ts` except compatibility exports.

### Pages

Route/page components should coordinate, not own all behavior.

Extract when state grows:

- controller hooks;
- model helpers;
- focused components;
- formatters;
- API modules.

### UI Behavior

Every interactive UI change should handle:

- loading;
- empty state;
- error state;
- permission denied;
- disabled/unavailable feature;
- mobile and desktop layout if visible to users.

### Runtime Crashes

A missing optional component, unknown widget, unknown node, or failed catalog load must not blank the app.

Render controlled fallback instead.

## 7. Studio Rules

Changing Studio nodes requires checking all affected layers:

- backend node manifest;
- executor registry;
- validation;
- frontend palette/metadata;
- node config panel;
- pipeline assistant catalog if relevant;
- docs/tests.

Do not add a node only to frontend or only to backend.

Unknown node types should fail clearly, not silently skip.

## 8. Terminal And AI Assistant Rules

Terminal/AI changes must preserve:

- WebSocket event contract;
- command safety;
- manual input behavior;
- stop/cancel behavior;
- output redaction/compaction;
- connection cleanup.

Do not add feature-specific logic directly to `SSHTerminalConsumer`.

Use focused modules under:

```text
servers/consumers/ssh_terminal_*.py
servers/services/terminal_*
servers/services/terminal_ai/
frontend/src/components/terminal/
frontend/src/pages/terminal-page/
```

Any AI-generated command execution must pass the same safety/policy path as manual or pipeline execution.

## 9. Dashboard Rules

Dashboard widgets must:

- have stable ids;
- tolerate missing data;
- tolerate removed/disabled widgets in saved layout;
- not do hidden mutations;
- keep render components small;
- fetch data through typed API modules.

Do not hardcode every new widget in multiple unrelated places. Prefer a registry/catalog pattern.

## 10. Integration Rules

External integrations must define:

- auth method;
- secret names;
- health check;
- timeout behavior;
- retry behavior;
- redaction behavior;
- audit category;
- permissions;
- failure mode.

Outbound integrations must never send data unless the user/action has permission.

## 11. Tests And Checks

Minimum checks by change type:

| Change | Minimum checks |
| --- | --- |
| Python service/view | targeted `python -m pytest ...` |
| Django model/migration | `manage.py check`, migration check, focused tests |
| Import/architecture-sensitive | `python scripts\check_architecture_sizes.py --strict-new` |
| Frontend component/page | `npx eslint <files>`, `npm run build`, focused tests if available |
| Studio node | manifest consistency, validation test, executor test |
| Terminal/AI | focused terminal/AI tests plus frontend build if UI changed |
| Integration/egress | permission-deny, redaction, audit, health check tests |
| Docs only | grep stale references and verify paths |

Use WSL `.venv` for backend Django checks in this workspace when needed:

```powershell
wsl -e bash -lc 'cd /mnt/c/WebTrerm && .venv/bin/python manage.py check --settings=web_ui.settings.test'
```

Architecture guard:

```powershell
python scripts\check_architecture_sizes.py --strict-new
```

Frontend:

```powershell
cd frontend
npm run build
```

## 12. Review Checklist

Before accepting a change, ask:

- Is the owner domain correct?
- Did we avoid forbidden cross-app imports?
- Did we keep compatibility files thin?
- Is backend permission enforced?
- Are secrets redacted?
- Are risky actions audited?
- Does the UI handle loading/error/empty/denied states?
- Are unknown/disabled things handled safely?
- Did we run the right focused checks?
- Did docs stay true?

If any answer is unclear, fix that before expanding the feature.

## 13. Anti-Patterns

Avoid:

- adding one more branch to a large central file;
- adding frontend-only permission checks;
- adding API calls inside UI components;
- adding backend behavior just because a frontend needs a shape;
- silently swallowing unknown runtime types;
- using admin status as a replacement for permission scopes;
- putting secrets in examples;
- mixing refactor, redesign, and feature behavior in one change;
- updating docs without checking current repo state.

## 14. Stop Conditions

Stop and rethink when:

- one feature requires editing many central files;
- a test needs excessive monkeypatching of internals;
- a direct forbidden import looks convenient;
- a compatibility file starts growing again;
- a small feature requires broad architecture changes;
- the feature cannot explain its permissions or owner.

These are signals the extension point is wrong or missing.

## 15. Daily Short Rule

For any platform change:

```text
owner -> contract -> focused implementation -> permission/safety -> tests -> docs
```

Not:

```text
quick central edit -> bypass checks -> hope it does not break
```
