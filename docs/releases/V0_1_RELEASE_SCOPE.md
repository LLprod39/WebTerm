# WebTerm v0.1 release-scope matrix

Status: frozen scope candidate; release evidence incomplete
Last reviewed: 2026-07-22

This is a scope classification, not a claim that v0.1 has passed release gates. `GA` means the capability is intended to be supported inside the controlled pilot after every mandatory checklist item passes. `preview` means opt-in, best-effort and outside the pilot availability promise. `disabled` means fail-closed in production until a later release decision.

## Product domains

| Domain | v0.1 status | Owner | Production prerequisites | Mandatory evidence |
|---|---|---|---|---|
| Servers inventory and access | GA | `servers` | PostgreSQL, encrypted credentials, object permissions | CRUD/RBAC API tests, add-server E2E, audit event |
| SSH terminal and files | GA | `servers` | strict host-key policy, WebSocket auth, command/file permissions | terminal/SFTP E2E, host-key security tests, mutation audit |
| Monitoring and alerts | GA | `servers` | scheduler/worker health, Redis, notification policy | metric/alert tests, degraded-worker check, operator smoke |
| Playbooks | preview | `servers` + frontend automation | explicit execution permission and confirmation | dry-run/execute policy tests, UI smoke, audit artifact |
| Agents | preview | `servers` + `app` | configured model provider, budgets, tool policy | deterministic fake-provider tests, guarded tool E2E |
| Chat/operator orchestration | preview | `core_ui` + `app` | opt-in access, provider readiness, action confirmation | access tests, prompt/tool safety tests, chat smoke |
| Studio pipelines | preview | `studio` | registered nodes only, owner isolation, secret policy | validation/execution tests, pipeline E2E, audit trace |
| MCP integrations | preview | `studio` | allowlisted transports/hosts, owner isolation, SSRF controls | transport security tests, ownership tests, degraded-state UI |
| Plugins | disabled | `plugin_marketplace` + `app.plugins` | external signing/KMS, scanner, allowlists, isolated jobs | deploy checks, trust-chain tests, install/rollback/quarantine E2E |
| Kubernetes Ops | disabled | `kubernetes_ops` | separate readiness flag, least-privilege credentials, action approvals | RBAC/read-only/mutation tests, cluster E2E, operator runbook |
| MARS | disabled | `mars` | isolated runtime, per-user workspace, resource/network policy | isolation/approval tests, sandbox evidence, failure recovery |

## Required foundations

| Foundation | v0.1 status | Owner | Production prerequisites | Mandatory evidence |
|---|---|---|---|---|
| Authentication and session lifecycle | GA | `core_ui` | secure cookies, CSRF, TLS, Redis sessions/channels | auth/session security tests and browser E2E |
| RBAC, groups and object permissions | GA | `core_ui` | deny-by-default backend checks | permission matrix tests across every GA mutation |
| Keycloak / LDAP | preview | `core_ui` | configured external IdP, safe fallback policy | integration tests and operator login smoke |
| Managed secrets | GA | `core_ui` | distinct encryption key, rotation and redaction | round-trip/rotation/redaction tests, log scan |
| Audit | GA | `core_ui` + domain emitters | actor, target, outcome and correlation identifiers | schema tests and end-to-end guarded-action trace |
| Settings and readiness | GA | `web_ui` + `core_ui` | production settings fail closed | `check --deploy`, readiness smoke, negative config tests |
| Dashboard | preview | `core_ui` + frontend | no privileged data leakage, graceful degradation | permission/empty/error-state tests |
| Notifications | preview | `core_ui` + domain emitters | configured channel secrets and retry policy | provider fakes, retry/failure tests, operator smoke |

The v0.1 production profile sets `PLUGIN_MARKETPLACE_RELEASE_MODE=disabled`.
In that mode Django does not register plugin API routes or execution providers,
and the authentication payload marks the plugin UI unavailable. Enabling the
mode before the external trust prerequisites are proven is a release-scope
change and requires the promotion process in the freeze rules below.

## Freeze rules

1. Promotion from `preview` or `disabled` to `GA` requires the same pull request to add prerequisites, tests, release artifacts and documentation.
2. A disabled domain must be denied by the backend. A navigation flag alone is insufficient.
3. A failed or missing artifact keeps the capability at its prior status.
4. No unresolved Critical or High security finding is permitted in GA scope.
5. The first pilot release cannot expand scope after release-candidate evidence collection begins.
