# ADR-0003: Kubernetes Ops and MARS remain optional bounded contexts

- Status: Accepted
- Date: 2026-07-30
- Decision owners: platform and release maintainers
- Applies to: `kubernetes_ops`, `mars`, production settings, CI and release scope

## Context

WebTerm's supported core is server inventory, SSH/files, monitoring, playbooks, agents, operator chat and Studio. `kubernetes_ops` and `mars` have independent data models, workers, routes and frontend surfaces, but share authentication, projects, managed secrets and release infrastructure with the core. Their source and tests therefore impose maintenance cost even while both domains are disabled in the production release-scope matrix.

Removing either domain now would discard tested implementation without reducing the operational risks that still gate the core. Extracting them now would instead create versioned cross-package contracts before there is a supported customer deployment or a stable external ownership boundary.

## Decision

Keep `kubernetes_ops` and `mars` in the monorepo through the v0.2 release line as **optional bounded contexts**, not as core GA capabilities.

### Kubernetes Ops

- The supported release boundary remains the frozen read-only scope in `KUBERNETES_OPS_V01_SCOPE.md`.
- Production remains fail-closed unless the Kubernetes release flag and its readiness prerequisites are explicitly enabled.
- Existing privileged apply, patch, delete, exec, port-forward and node-maintenance code is retained, but it is not part of the supported release contract. It must not be reachable merely because the Django app is installed.
- Promotion of privileged Kubernetes operations requires a new ADR covering object-scoped authorization, approval TTL, session recording, rollback and live-cluster evidence.

### MARS

- MARS remains disabled in the production release scope and is started only through its explicit deployment profile and feature flag.
- Its agent image, workspace, network/resource policy, approvals and failure recovery remain separate evidence from the WebTerm core.
- MARS routes or models must not become implicit dependencies of core server, terminal, agent or Studio flows.

### Extraction trigger

Extraction is deferred until at least one of these conditions is true:

1. a supported customer deployment requires an independent Kubernetes Ops or MARS release cadence;
2. a separate owning team accepts the domain and its operational support;
3. changes in either domain repeatedly block core releases despite separate test selection.

When extraction is approved, the domain moves to a separately versioned package or plugin with a separate release cycle, CI job, migration compatibility contract and published artifacts. The core coverage ratchet is recalculated from core-owned modules only; the extracted domain receives its own non-decreasing coverage baseline. Cross-domain calls use versioned HTTP/event or plugin-provider contracts rather than direct model imports.

## Consequences

- Repository breadth remains unchanged for now, so dependency and migration updates must continue to account for both apps.
- Release notes must describe Kubernetes Ops and MARS as disabled or preview; source presence is never evidence of availability.
- Core production readiness cannot depend on either domain being enabled.
- New cross-domain foreign keys or imports from core applications into `kubernetes_ops` or `mars` require a superseding ADR.
- Retaining privileged Kubernetes code does not authorize shipping it; fail-closed permission and release-scope tests remain mandatory.

## Verification

- `docs/releases/V0_2_RELEASE_SCOPE.md` lists both domains as disabled.
- `docs/architecture/KUBERNETES_OPS_V01_SCOPE.md` remains the machine-checked Kubernetes release boundary.
- `tests/test_domain_boundary_adr.py` pins this decision in the ADR index and release-scope documents.
