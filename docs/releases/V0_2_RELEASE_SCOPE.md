# WebTerm v0.2 release-scope matrix

Status: v0.2.0 release candidate; publication requires every gate in `V0_2_RELEASE_CHECKLIST.md`
Last reviewed: 2026-07-30

`GA` means supported inside the controlled single-host pilot boundary. `preview` means opt-in and outside the availability promise. `disabled` means the backend fails closed in the production profile.

## Product domains

| Domain | v0.2 status | Owner | Production boundary | Mandatory evidence |
|---|---|---|---|---|
| Servers inventory and access | GA | `servers` | project-scoped ownership, encrypted credentials, strict host keys | CRUD/RBAC, tenancy and host-key tests |
| SSH terminal and files | GA | `servers` | authenticated WebSocket, read-only AI default, guarded mutations | terminal E2E, command-policy and audit tests |
| Monitoring and alerts | GA | `servers` | Redis and worker readiness | metrics, alert and degraded-worker tests |
| Playbooks | preview | `servers` + frontend | durable queue, private bundles, isolated runner, explicit confirmation | lifecycle, proxy, recovery and Playwright smoke |
| Agents | preview | `servers` + `app` | budgets, fail-closed tools, ephemeral runner | policy, sandbox, fencing and audit-chain tests |
| Chat/operator orchestration | preview | `core_ui` + `app` | opt-in access and action confirmation | access, prompt/tool safety and chat smoke |
| Studio pipelines | preview | `studio` | registered nodes, project isolation, approver separation, secret policy | validation, dry-run, approval and execution tests |
| MCP integrations | preview | `studio` | allowlisted destinations, owner isolation, SSRF controls | transport, egress and ownership tests |
| Plugins | disabled | `plugin_marketplace` + `app.plugins` | external trust and isolated review jobs are still required | fail-closed deploy and trust-chain tests |
| Kubernetes Ops | disabled | `kubernetes_ops` | frozen read-only v0.1 boundary | machine-readable scope and mutation-denial tests |
| MARS | disabled | `mars` | immutable agent image plus isolated policy evidence | image-policy, isolation and approval tests |

## Required foundations

| Foundation | v0.2 status | Owner | Production boundary | Mandatory evidence |
|---|---|---|---|---|
| Authentication and session lifecycle | GA | `core_ui` | CSRF, TLS, login throttling and Redis sessions | auth and brute-force tests |
| Projects and memberships | GA | `core_ui` | active-project membership and cross-project rejection | project tenancy suite |
| Managed secrets | GA | `core_ui` | versioned encryption, HKDF and online rotation | rotation, undecryptable inventory and redaction tests |
| Audit | GA | `core_ui` + domains | append-only events, hash chain and correlation identifiers | integrity, tamper and export tests |
| Settings and readiness | GA | `web_ui` + `core_ui` | dependency-aware readiness and fail-closed production settings | deploy, readiness and negative config tests |
| Supply chain | GA | release workflow | immutable image digests, SBOM, checksums and attestations | successful tag workflow and artifact verification |

## Freeze rules

1. A preview or disabled domain can become GA only with prerequisites, tests, documentation and release evidence in the same reviewed change.
2. Navigation flags never replace backend denial.
3. Failed or missing release evidence keeps the prior status.
4. No unresolved Critical or High security finding is allowed in GA scope.
5. Project isolation does not expand the supported deployment to public multi-tenant or multi-host production.
