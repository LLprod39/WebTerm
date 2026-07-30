# Kubernetes Ops v0.1 Scope

Status: **frozen-read-only for v0.1**
Owner: **@LLprod39**
Decision date: **2026-07-30**

Kubernetes Ops remains in the repository, but v0.1 treats it as a bounded,
read-only cockpit rather than a second write-capable product. This preserves
the already tested inventory and diagnosis value while engineering effort stays
focused on the SSH, agent, playbook, and Studio execution core.

## Included in v0.1

- normalized provider, cluster, namespace, workload, pod, event, Fleet, and
  Devtron inventory reads;
- readiness, provider health, bounded log snapshots, metrics, audit reports,
  and read-only Studio diagnosis drafts;
- dry-run/preflight evidence that does not mutate a cluster;
- request, approval, recording, and report models retained as dormant guarded
  infrastructure so existing migrations and evidence remain compatible.

## Excluded from v0.1

- native apply, patch, scale, restart, delete, cordon, drain, exec, attach,
  port-forward, cluster terminal, node debug, and action-request execution;
- Secret value disclosure;
- new Kubernetes routes, capability families, models, or migrations unless the
  freeze is deliberately revised by the package owner in the same change.

All Admin/native/interactive runtime flags default to `false`, including
`KUBERNETES_ADMIN_MODE_ENABLED`. Production examples must also keep every flag
listed in `config/kubernetes-ops-v0.1-scope.json` false.

## Executable freeze

Run:

```bash
python scripts/check_kubernetes_ops_v01_scope.py
```

The CI check verifies the route-surface digest, fail-closed runtime defaults,
production environment values, blocked native capabilities, documentation, and
CODEOWNERS entry. Any deliberate scope change must update the manifest and this
document under owner review; silently adding a route or enabling a default fails
CI.

## Unfreeze gate

The freeze may be revised only with a named product owner, dedicated release
milestone, production RBAC/credential evidence, rollback and incident runbooks,
full Kubernetes backend and frontend E2E coverage, load/concurrency evidence,
and an explicit decision about which native mutations are supported. Until all
of those exist, v0.1 remains read-only.
