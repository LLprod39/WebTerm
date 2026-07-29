# WebTerm operations control plane roadmap

Status: active product roadmap  
Baseline: published `v0.1.0` plus the unreleased hardening tracked in [PR #26](https://github.com/LLprod39/WebTerm/pull/26)  
Last reviewed: 2026-07-29

This roadmap supersedes the Endpoint Management stage in the older
[WebTerm/RoutineOps competitive plan](WEBTERM_ROUTINEOPS_COMPETITIVE_PLAN.md).
That document remains an implementation history for Stage 1, but its Go endpoint
agent, device gateway and MDM work are not authorized product work.

## Product decision

WebTerm is a self-hosted operations control plane for operator-owned
infrastructure:

> infrastructure state -> diagnosis -> guarded action -> result verification -> audit

The primary resource is an SSH-managed server. Playbooks are the primary
repeatable-action surface. Monitoring, Operator Chat, Agents and Studio support
that same lifecycle; they are not five unrelated products.

The target deployment remains a controlled single-host Docker Compose pilot.
Public multi-tenant SaaS, multi-worker/HA claims, an endpoint agent, WebTerm-on-
Kubernetes deployment and promotion of disabled Plugins or MARS are out of scope
until the gates at the end of this document are met.

## Verified baseline

- `v0.1.0` was published on 2026-07-24 from commit `4317126`, with immutable
  images, install bundles, checksums, SBOMs, provenance and attestations.
- The protected `test` and `main` branches require the 18 product/security checks,
  a pull request, an independent approval, CODEOWNERS, linear history and no admin
  bypass.
- Readiness onboarding, five grouped navigation areas, server search/command
  palette, the Playbooks workspace, production install/recovery/upgrade smokes
  and a published-image Playwright flow already exist.
- Plugins and MARS remain fail-closed in the production profile. Kubernetes,
  Agents, Chat and Studio remain preview capabilities outside the GA pilot promise.
- The 2026-07-29 sealed security review produced a bounded hardening set. Its code
  is unreleased until PR #26 passes every protected gate, receives an independent
  approval and is promoted through a new signed release.

## Release 1: v0.1.1 Pilot Hardening

### Goal

Ship the security and Playbooks hardening as a reproducible controlled-pilot
release, and prove the first operator journey against the real production stack.

### Includes

- Close every confirmed Critical/High item from the sealed review with negative
  regressions and source-to-sink verification.
- Keep dependency audits fail-closed. The React Router advisory exception remains
  valid only for the exact reviewed versions and only while no RSC APIs are used.
- Ship isolated Playbook validation/execution, private bundle storage, exact
  revision execution and durable worker recovery.
- Exercise login -> readiness -> server discovery/addition -> SSH trust -> action
  -> result -> audit in the production-image browser lane.
- Synchronize changelog, release scope, checklist and signed release evidence.

### Excludes

- New resource types or a device agent.
- Public or multi-tenant production claims.
- HA/multi-worker guarantees.
- Promotion of Plugins, MARS or Kubernetes to GA.
- Visual redesign unrelated to the operator journey.

### Definition of Done

- All 18 protected checks pass on the exact candidate SHA.
- Clean install, published-image Playwright, backup/restore and both frozen
  upgrade/rollback fixtures pass.
- No unresolved Critical/High finding exists in GA scope.
- An independent reviewer approves the last push and all conversations are resolved.
- A new tag workflow publishes digest-pinned images and signed release assets;
  the release is not declared by a local test or by merging the PR alone.

## Release 2: v0.2.0 Daily Operations

### Goal

Make the existing server fleet and Playbooks usable as one daily workspace rather
than adding another subsystem.

### Includes

- A server-centered Operations view that combines health, active alerts, recent
  guarded runs, pending approvals and the latest audit outcomes using existing
  domain APIs.
- A shared run/activity vocabulary across commands, Playbooks, Agents and Studio,
  with links back to the target server and immutable evidence.
- Monitoring-to-action flows: diagnose an alert, select a reviewed runbook,
  confirm impact, execute and verify the post-condition.
- Saved server filters and operator-owned views without changing tenancy or
  introducing a second inventory model.
- Explicit loading, empty, denied, disabled and degraded states for every GA flow.

### Excludes

- A general event bus rewrite or microservice split.
- Arbitrary automatic remediation.
- Endpoint management, public plugin marketplace and Kubernetes Admin Mode GA.

### Definition of Done

- The daily flow works on desktop and mobile and is covered by real backend,
  PostgreSQL/Redis and Playwright tests.
- Every mutation is backend-authorized, explicitly confirmed where required and
  emits actor/target/outcome/correlation audit data.
- Retry, duplicate submission, timeout and worker-loss tests prove terminal state
  and idempotency behavior.
- Pilot task success and latency meet the versioned UX/performance budgets.

## Release 3: v0.3.0 Infrastructure Cockpit

### Goal

Turn verified daily-operation data into a fleet cockpit for a larger controlled
pilot without claiming public SaaS or HA support.

### Includes

- Fleet posture and incident views built from current monitoring, audit and run
  records.
- Bounded fan-out Playbook execution with concurrency limits, dry-run/approval,
  partial-failure reporting and explicit retry selection.
- Operator handoff reports containing current state, actions, verification and
  links to immutable evidence.
- Capacity/load qualification for the declared pilot size and documented worker
  sizing/recovery limits.

### Excludes

- Endpoint/MDM agent development.
- WebTerm control-plane deployment to Kubernetes.
- Public multi-tenant billing, marketplace or unconstrained autonomous agents.

### Definition of Done

- Load tests establish an explicit supported pilot envelope; no scale number is
  published before that evidence exists.
- Fan-out operations preserve authorization, bounded concurrency, cancellation,
  idempotency and per-target audit evidence under worker restart.
- Operations, recovery and incident runbooks match the released images and have
  a successful drill artifact.

## Ordered implementation queue

| Order | ID | Work | State | Gate |
|---:|---|---|---|---|
| 1 | H-01 | Remediate the sealed security findings with negative tests | Implemented on PR #26 | Full security/backend/frontend regressions |
| 2 | H-02 | Enforce exact dependency-audit policy and immutable runtime images | Implemented on PR #26 | Python/npm audit and supply-chain jobs |
| 3 | H-03 | Align changelog and release evidence with published `v0.1.0` versus unreleased hardening | Implemented on PR #26 | Documentation contract and identity |
| 4 | H-04 | Add the real production-browser golden path through server SSH action and audit | Next | Production install plus Playwright artifact |
| 5 | H-05 | Pass every required check on one exact PR SHA | Pending CI | 18/18 required checks green |
| 6 | H-06 | Obtain independent last-push approval and promote linearly to `test` | External review | Protected merge succeeds without bypass |
| 7 | H-07 | Prepare synchronized `v0.1.1` identity, notes and generic tag release contract | Pending H-05/H-06 | Identity/docs/release workflow tests |
| 8 | H-08 | Publish and independently verify signed `v0.1.1` artifacts | Pending H-07 | Published-digest smoke and attestations |
| 9 | D-01 | Define one cross-domain run/activity read model without moving domain ownership | Pending v0.1.1 | ADR/API contract and permission tests |
| 10 | D-02 | Build the server-centered Operations view from existing APIs | Pending D-01 | Desktop/mobile states and Playwright |
| 11 | D-03 | Link alert diagnosis to reviewed Playbook selection and guarded execution | Pending D-02 | Policy, approval, negative RBAC and audit tests |
| 12 | D-04 | Add post-condition verification and partial-failure retry selection | Pending D-03 | Integration and worker-restart tests |
| 13 | D-05 | Run the versioned controlled-pilot task study and close observed UX blockers | Pending D-02..D-04 | Real privacy-safe pilot evidence |
| 14 | C-01 | Add fleet posture and bounded fan-out on proven run contracts | Pending v0.2.0 | Load, authorization, idempotency and audit gates |
| 15 | C-02 | Publish the supported pilot envelope and recovery drill evidence | Pending C-01 | Load/recovery artifacts and updated support matrix |

Do not start an item before every earlier item whose gate it depends on is closed.
In particular, no release publication bypasses review, and no Daily Operations UI
may invent a second execution or permission model.

## Gate for any new major subsystem

A new endpoint agent, public plugin platform, WebTerm-on-Kubernetes deployment or
other major bounded context may be proposed only after all of the following are
true:

1. `v0.2.0` has real pilot evidence showing the current operations path is useful.
2. The requested capability cannot be delivered safely by the existing server,
   Playbook, Agent, Studio or Kubernetes preview domains.
3. A named user problem, owner, threat model, lifecycle, data-retention contract
   and decommission path are approved.
4. The current architecture, security, recovery and CI gates remain green without
   weakening ratchets or adding an unreviewed exception.
5. The work is decomposed into bounded PRs; architecture, redesign and behavior
   are not combined into a mega-PR.

Until then, the next WebTerm step is **v0.1.1 Pilot Hardening**, followed by a
server-centered Daily Operations workspace.
