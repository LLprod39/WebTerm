# Kubernetes Ops Operations Runbook

This runbook is the operator/admin handoff for WebTerm Kubernetes Ops. It covers the current MVP operating mode: WebTerm is the user-facing Kubernetes cockpit, backed by provider sync, diagnosis drafts, safety gates, and audited fallback links. It is not a replacement for Rancher, Fleet, Devtron, or GitOps ownership.

## 1. Scope And Operating Mode

Current production posture:

- WebTerm owns cockpit views, normalized inventory, readiness, audit, and Studio diagnosis draft entrypoints.
- Rancher remains the source of truth for clusters, lifecycle, RBAC, projects, namespaces, Fleet, and platform add-ons.
- Fleet remains the GitOps/HelmOps control plane for platform rollouts.
- Devtron remains the AppOps/CI/CD/debug UI for application teams.
- Normal users work inside WebTerm only. Rancher, Fleet, and Devtron UIs are admin/break-glass fallback paths, not the daily operator workflow.
- WebTerm authentication may be LDAP/OIDC/Keycloak or local WebTerm users. WebTerm does not mirror user passwords into Rancher or Devtron; backend provider credentials and read-only service accounts are used for provider access.
- WebTerm native Kubernetes exec, attach, port-forward, cluster terminal, node debug, node maintenance, raw shell `kubectl describe`, raw YAML editing, rollout restart, scale, delete, and apply are disabled by policy. Admin Mode live describe is allowed only as a read-only provider GET/list API behind active session checks and metadata-only audit.

MVP-safe actions:

- read Kubernetes Ops readiness;
- read normalized provider health, clusters, namespaces, workloads, pods, services/ingresses, events, Fleet bundles, and Devtron apps through WebTerm-native APIs;
- use audited Rancher/Devtron/Fleet deep links only as staff/admin fallback while WebTerm-native views are being completed; normal user API responses hide those external URLs and cannot write fallback deeplink audit events;
- read bounded pod log snapshots when a Rancher provider exposes a JSON log endpoint template;
- read Admin Mode node/pod CPU and memory metrics through WebTerm when `metrics.k8s.io/v1beta1` is available; metrics access requires an active Admin session, all-namespace pod metrics require an all-namespaces session, and audit/action evidence stores only counts and totals;
- create a read-only Studio diagnosis draft for a known app.

## 2. Production Configuration Checklist

Before enabling the sidebar:

1. Run migrations:

   ```bash
   python manage.py migrate
   ```

2. Configure provider secrets using external references or managed encrypted values. Do not put raw tokens in API responses, docs, logs, commits, or screenshots.

3. Configure at least one enabled Rancher provider and one enabled Devtron provider through the admin-only provider API/UI.

4. Confirm the login and RBAC access model before any multi-user pilot. Preferred production mode is shared LDAP/OIDC/Keycloak identity into WebTerm, with matching groups documented for Rancher/Devtron. A local WebTerm-only login is also valid for internal/pilot use, but provider access must still go through backend service credentials/read-only service accounts, not copied user passwords. WebTerm must stay deny-by-default, Rancher/Devtron stay the source of truth for platform/app permissions, and WebTerm must not hold admin kubeconfig.

5. Render and review the read-only Kubernetes RBAC manifest for the pilot cluster. This does not apply anything by itself:

   ```bash
   python manage.py render_kubernetes_ops_readonly_rbac \
     --output artifacts/kubernetes_ops_readonly_rbac.yaml
   python manage.py render_kubernetes_ops_readonly_rbac --validate-only
   python scripts/verify_kubernetes_ops_readonly_rbac_live.py --apply
   ```

   The generated ServiceAccount/ClusterRole/ClusterRoleBinding must allow only `get`, `list`, and `watch`, and must not include `pods/exec`, `pods/attach`, `pods/portforward`, or write verbs.

6. Configure production env:

   ```text
   KUBERNETES_OPS_SYNC_INTERVAL_SECONDS=300
   KUBERNETES_OPS_SYNC_MAX_BACKOFF_SECONDS=900
   KUBERNETES_OPS_AUDIT_RETENTION_DAYS=365
   KUBERNETES_OPS_RELEASE_ENVIRONMENT=local
   KUBERNETES_OPS_PRODUCTION_APPROVAL_REF=
   KUBERNETES_OPS_RELEASE_EVIDENCE_MAX_AGE_SECONDS=86400
   KUBERNETES_ADMIN_MODE_ENABLED=false
   KUBERNETES_OPS_READY_FOR_SIDEBAR=false
   ```

7. Keep `KUBERNETES_OPS_RELEASE_ENVIRONMENT=local` and `KUBERNETES_OPS_READY_FOR_SIDEBAR=false` until readiness proves the required gates and visual evidence is current. For production approval set `KUBERNETES_OPS_RELEASE_ENVIRONMENT=production` and `KUBERNETES_OPS_PRODUCTION_APPROVAL_REF=<change-or-approval-id>` only after collecting evidence from the real production providers, real read-only Kubernetes RBAC proof, and real Kubernetes MCP endpoint.

8. Start the sync worker:

   ```bash
   python manage.py run_kubernetes_ops_sync_worker --daemon --interval 300
   ```

   Container production can use the declared `kubernetes-ops-sync` service.

9. Run a one-shot dry check before a full worker rollout:

   ```bash
   python manage.py sync_kubernetes_ops --dry-run
   ```

10. Configure the read-only Kubernetes MCP binding for Studio diagnosis drafts:

   ```bash
   python manage.py ensure_kubernetes_ops_studio_binding --username <staff-user>
   ```

   Local Docker uses `http://mcp-demo:8765/mcp` by default. Production should pass the real read-only Kubernetes MCP JSON-RPC endpoint with `--url` or `KUBERNETES_OPS_MCP_URL`.

11. Run focused release checks:

   ```bash
   python manage.py check
   python scripts/check_architecture_sizes.py --strict-new
   pytest tests/test_kubernetes_ops_api.py tests/test_kubernetes_ops_sync.py
   ```

12. Collect one bounded preflight-evidence artifact. This records the required local release checks: Django check, architecture guard, migration dry-run, full Kubernetes backend tests, read-only RBAC validation, sync-prune safety, live read-only RBAC proof, local Rancher/Fleet/Devtron platform evidence, and live provider smoke evidence:

   ```bash
   python manage.py verify_kubernetes_ops_preflight \
     --output artifacts/kubernetes_ops_preflight_evidence.json
   ```

   The command exits non-zero while preflight checks fail. It intentionally does not run itself and does not run the final release-evidence command.

13. Collect one bounded release-evidence artifact. This performs live provider probes, a sync dry-run, readiness collection, a read-only Kubernetes MCP diagnosis smoke call, action-control proof, WebTerm-only normal-user surface proof, release-scope proof, and references the current preflight artifact:

   ```bash
   python manage.py verify_kubernetes_ops_release \
     --username <staff-user> \
     --output artifacts/kubernetes_ops_release_evidence.json
   ```

   The command exits non-zero while blockers remain. Use `--no-fail` only for exploratory diagnostics, not for release approval.

14. Render the operator handoff package from the release evidence artifact:

   ```bash
   python manage.py render_kubernetes_ops_release_handoff \
     --output artifacts/kubernetes_ops_release_handoff.md
   ```

   This handoff does not approve production by itself. It summarizes current blockers, exact required commands, production env flags, external evidence still required, and the safety guards that must remain true before `KUBERNETES_OPS_READY_FOR_SIDEBAR=true`. The handoff must list `KUBERNETES_OPS_PRODUCTION_ROLLBACK_EVIDENCE_REF` and `KUBERNETES_OPS_PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_REF` before production sidebar enablement, `KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF` before any production interactive transport is enabled, and `KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF` before any production port-forward tunnel is enabled.

## 3. Readiness And Release Gates

Use:

```text
GET /api/kubernetes/readiness/
```

Release interpretation:

- `architecture_guard` must be ready before merge.
- `permission_matrix` must be ready for the current operator.
- `access_model` must be ready before any multi-user pilot; it documents Keycloak/OIDC groups, WebTerm feature/staff rules, Rancher/Devtron role mapping, and read-only service-account constraints.
- `rancher_provider` and `devtron_provider` must be ready before sidebar enablement.
- `provider_health` must be ready and fresh before production pilot.
- `read_only_sync` must contain real normalized rows before pilot.
- `sync_worker` must be running and not stale before sidebar enablement.
- `security_review` should stay ready; wildcard trusted origins or missing CSRF/clickjacking middleware are release blockers.
- `terminal_exec_threat_model` should stay ready, meaning exec/debug/port-forward remain disabled.
- `admin_recording_retention` should stay ready, meaning Admin Mode recording metadata/transcript cleanup commands are available and current expired counts are visible.
- `operator_docs` should stay ready so admins have the current recovery path.
- `studio_automation` is optional for cockpit read-only launch, but must be ready before advertising diagnosis draft automation.
- `frontend_e2e` is ready only when the Kubernetes visual tests and snapshot artifacts for settings, empty, healthy, and degraded states exist in the release workspace.
- `sidebar_release_scope` must be ready before sidebar enablement; local/pilot env and configured local provider/cluster markers are allowed for testing but block production navigation.
- `release_evidence_artifact` is checked by runtime readiness. While the sidebar flag is off it verifies artifact freshness only; when `KUBERNETES_OPS_READY_FOR_SIDEBAR=true`, it requires a fresh `production_ready=true` artifact whose `release_scope.approval_ref` matches `KUBERNETES_OPS_PRODUCTION_APPROVAL_REF`.
- `release_evidence_artifact` also requires the artifact `schema_version` to match the current backend release contract; this prevents an old JSON artifact from approving a newer sidebar gate.
- The release artifact also references `artifacts/kubernetes_ops_preflight_evidence.json`. That preflight artifact must be `ready` and must match both `kubernetes_ops.release_preflight.v1` and the active release-evidence schema version.
- New release artifacts must include `normal_user_surface.status=ready`. If a blocker like `normal_user_surface:failed` appears, keep the sidebar disabled and fix the WebTerm-only normal-user API surface before any multi-user pilot.

Do not enable `KUBERNETES_OPS_READY_FOR_SIDEBAR=true` until required checks are ready and frontend visual snapshots match the target state.

### OIDC/RBAC Access Model

This is the required production mapping before a multi-user pilot:

| Keycloak group | WebTerm permission | Rancher role | Devtron role | WebTerm capability |
|---|---|---|---|---|
| `webterm-kubernetes-readers` | feature `kubernetes`, non-staff | project/cluster read-only | application view + logs | read inventory, events, bounded log snapshots, action approval requests |
| `webterm-kubernetes-admins` | feature `kubernetes` + staff | cluster/project admin outside WebTerm | environment admin outside WebTerm | provider config/sync/probe and external action verification |
| `webterm-studio-kubernetes-operators` | `kubernetes` + `studio_pipelines` + `studio_mcp` | read-only evidence source | read-only app evidence source | read-only Studio diagnosis through Kubernetes MCP |

Read-only service-account contract:

- name: `webterm-kubernetes-readonly`;
- scope: namespace/project scoped per pilot cluster;
- allowed verbs: `get`, `list`, `watch`;
- denied verbs: `create`, `update`, `patch`, `delete`, `deletecollection`, `escalate`, `bind`, `impersonate`;
- denied subresources: `pods/exec`, `pods/attach`, `pods/portforward`.

Render/validate command:

```bash
python manage.py render_kubernetes_ops_readonly_rbac --output artifacts/kubernetes_ops_readonly_rbac.yaml
python manage.py render_kubernetes_ops_readonly_rbac --validate-only
python scripts/verify_kubernetes_ops_readonly_rbac_live.py --apply
```

The live proof writes `artifacts/kubernetes_ops_readonly_rbac_live_evidence.json`. Release evidence treats that file as required: allowed read checks must be `yes`, and write/exec/escalate checks must be `no`.

Final enablement requires `verify_kubernetes_ops_release` to report `production_ready=true` against the target production providers and real Kubernetes MCP endpoint. The artifact includes `release_scope`; local/kind/localhost/fixture markers keep `production_ready=false` even when other checks pass.

### Local Test Foundation

The current local evidence environment is separate from production approval. It exists to test WebTerm integration paths against real Kubernetes/Rancher/Devtron services before production credentials are available.

Current local stack:

- WebTerm itself runs from `docker-compose.yml`: Postgres, Redis, backend, frontend, nginx, scheduled workers, `kubernetes-ops-sync`, and local MCP helpers.
- The test Kubernetes platform is adjacent to that compose stack, not embedded as ordinary compose services: kind creates Docker containers for the Kubernetes cluster.
- Rancher, Fleet, cert-manager, and Devtron run inside that kind Kubernetes cluster as Helm/Kubernetes workloads. Fleet is part of Rancher, not a separate login surface.
- WebTerm reaches those local platform services through host-exposed URLs and tunnels such as `host.docker.internal` and Devtron port-forwarding.
- kind context: `kind-webterm-k8s`;
- Kubernetes: `v1.34.0`;
- Rancher: `v2.14.3` in namespace `cattle-system`;
- cert-manager: `v1.20.3` in namespace `cert-manager`;
- Devtron OSS: chart `devtron/devtron-operator` `0.23.2`, app `2.1.1`, namespace `devtroncd`;
- WebTerm Rancher provider: `local-rancher-real`, base URL `https://host.docker.internal:8443`, token stored as `managed:kubernetes-provider-token:{id}`.
- WebTerm Devtron provider: `local-devtron-real`, base URL `http://host.docker.internal:18091`, session password stored as `managed:kubernetes-provider-token:{id}`, labels include `auth_strategy=devtron_session`, probe `/orchestrator/devtron/auth/verify/v2`, apps path `/orchestrator/application?clusterIds=1`, and cluster alias `default_cluster -> local`.

Local fallback access:

These URLs are for admin/debug fallback. The planned product workflow is WebTerm-only; normal users should not need to open Rancher, Fleet, or Devtron directly.

```powershell
# Rancher UI
https://host.docker.internal:8443/dashboard

# Devtron UI, start a local tunnel when needed
kubectl port-forward -n devtroncd svc/devtron-service 18091:80
http://127.0.0.1:18091/dashboard

# Devtron admin password, local only
kubectl -n devtroncd get secret devtron-secret -o jsonpath='{.data.ADMIN_PASSWORD}' |
  ForEach-Object { [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String($_)) }
```

Local WebTerm sync proof:

```bash
# Run this on the host or another environment that has kubectl access to kind-webterm-k8s.
python manage.py verify_kubernetes_ops_local_platform \
  --output artifacts/kubernetes_ops_local_platform_evidence.json --no-fail
python manage.py verify_kubernetes_ops_live_provider_smoke \
  --output artifacts/kubernetes_ops_live_provider_smoke.json --no-fail

# Docker backend preflight reads these artifacts from artifacts/. The backend container
# does not need kubectl installed for the local platform check.
python manage.py sync_kubernetes_ops --provider-id <local-rancher-real-id>
python manage.py sync_kubernetes_ops --provider-id <local-devtron-real-id>
python manage.py verify_kubernetes_ops_preflight \
  --output artifacts/kubernetes_ops_preflight_evidence.json --no-fail
python manage.py verify_kubernetes_ops_release --username admin \
  --output artifacts/kubernetes_ops_release_evidence.json --no-fail
```

Latest local evidence from `artifacts/kubernetes_ops_release_evidence.json`:

- local platform evidence: `artifacts/kubernetes_ops_local_platform_evidence.json`, schema `kubernetes_ops.local_platform_evidence.v1`, generated on `2026-07-01T09:00:16Z`, status `ready`, summary `ready=3`, `missing=0`, `total=3`; it proves `rancher` in `cattle-system`, `fleet` in `cattle-fleet-system`, and `devtron` in `devtroncd` have their expected namespaces, services and ready workloads in context `kind-webterm-k8s`;
- live provider smoke evidence: `artifacts/kubernetes_ops_live_provider_smoke.json`, schema `kubernetes_ops.live_provider_smoke.v3`, checked on `2026-07-01T18:09:51Z`, status `ready`, summary `enabled_providers=2`, `provider_probes_ok=2/2`, `sync_dry_run_ok=2/2`, `clusters=1`, `namespaces=31`, `workloads=21`, `pods=35`, `fleet_bundles=1`, `apps=8`, `backend_paths_status=ready`, `backend_path_checks=4/4`; it proves WebTerm's enabled `local-rancher-real` and `local-devtron-real` providers can probe and dry-run sync Rancher/Fleet/Devtron data, then read a synced Rancher Pod YAML, bounded logs snapshot, live read-only describe, and read-only node drain preflight through Admin backend services without exposing raw tokens or starting cordon/eviction;
- generated at `2026-07-01T18:10:41Z`;
- schema version: `kubernetes_ops.release_evidence.v2`; release contract records required commands for `manage.py check`, architecture guard, migration dry-run, Kubernetes backend tests, read-only RBAC validation, live RBAC proof, local platform evidence, live provider smoke evidence, interactive transport prerequisite evidence, interactive live-smoke evidence, external evidence bundle collection, preflight evidence collection, and release evidence collection;
- referenced preflight artifact: `artifacts/kubernetes_ops_preflight_evidence.json`, generated at `2026-07-01T18:21:52Z`, schema version `kubernetes_ops.release_preflight.v1`, status `ready`, failed checks `[]`; the full Kubernetes backend sweep reports `420 passed, 7 subtests passed`, runs with `timeout_seconds=1200`, and sets only `POSTGRES_STATEMENT_TIMEOUT_MS=0` for that subprocess so long test teardown flushes are not killed by the production PostgreSQL statement timeout;
- real Rancher provider probe: `local-rancher-real`, `/v3/clusters`, `success=true`;
- real Devtron provider probe: `local-devtron-real`, `/orchestrator/devtron/auth/verify/v2`, `success=true`;
- real Rancher dry-run sync: `clusters=1`, `namespaces=31`, `workloads=21`, `pods=35`, `services=24`, `ingresses=3`, `events=3`, `fleet_bundles=1`;
- real Devtron dry-run sync: `apps=8`;
- current saved read-only inventory is pruned after successful sync and now matches the active local evidence counts: `namespaces=31`, `workloads=21`, `pods=35`, `events=3`, `apps=8`, `fleet_bundles=1`; pruning affects only WebTerm's local read-only inventory rows and never deletes Kubernetes/Rancher/Devtron resources;
- action controls proof: `ready`, runs inside transaction rollback, leaves no persistent action/cluster rows, keeps `native_execution_enabled=false`, redacts secret external evidence, blocks execute attempts as `execution_blocked`, generates a sanitized GitOps MR template with `native_execution_mode=external_gitops`, proves Fleet pause/resume requests stay `pending_approval` with `blast_radius=fleet_bundle`, proves Devtron rollback request stays `pending_approval` with `native_execution_mode=external_devtron` plus public-only rollback links, and leaves production sidebar enablement dependent on separate rollback/native verification evidence refs;
- post-review and retention proof: `ready`, runs inside transaction rollback, creates one final break-glass exec action plus one expired transcript recording, proves the action appears in the pending post-review queue, proves review payload and recording event redaction, then runs retention dry-run/apply and deletes one expired transcript event without persistent rows;
- external evidence bundle: `ready`, writes `artifacts/kubernetes_ops_external_evidence_bundle.json`, checked at `2026-07-02T03:25:54Z`, verifies the live provider, read-only RBAC, interactive transport, interactive live-smoke and production action evidence artifacts are present, reports `artifact_ready_count=5/5`, `missing_required_ref_count=0` in local mode, records `local_indicator_count=16`, and makes rollback/native verification refs required only in production so operators cannot confuse local evidence with production approval;
- interactive transport prerequisite evidence: `ready`, writes `artifacts/kubernetes_ops_interactive_transport_evidence.json`, verifies current exec/port-forward/cluster-terminal/node-debug prerequisite gates without opening live streams, reports `enabled_transport_count=0`, `blocker_count=0`, and keeps `provider_stream_opened=false`;
- interactive live-smoke evidence: `ready`, writes `artifacts/kubernetes_ops_interactive_live_smoke.json`, verifies exec, port-forward tunnel, cluster-terminal and node-debug provider openers with four simulated provider requests, reports `simulated_provider_requests_safe=true`, keeps `live_provider_stream_opened=false`, and records `production_live_provider_evidence=false` until an external production live-smoke ref is provided;
- interactive shell stream proof: `ready`, runs inside transaction rollback, temporarily creates a Rancher provider with terminal/node-debug path-template contracts plus approved break-glass sessions, verifies cluster terminal and node debug stream contexts create exactly two actions, two recordings and four redacted transcript events, proves provider requests are POST/stdin/tty-safe, and leaves persistent rows absent;
- normal-user surface proof: current release artifact includes rollback-only `normal_user_surface.status=ready` evidence that proves normal users receive no provider config/base URLs or external Rancher/Fleet/Devtron links, cannot write fallback deeplink audit events, and staff/admin fallback links are sanitized;
- readiness summary: `ready=17`, `missing=1`, `manual=0`, `total=18`; the missing required check is `sidebar_release_scope` because this artifact is local evidence, not production approval;
- access model readiness: `ready`; Keycloak/OIDC groups, WebTerm feature/staff rules, Rancher/Devtron role mapping, and read-only service-account constraints are documented and fail-closed; read-only RBAC manifest validation is `ready` for `webterm-kubernetes-readonly`;
- live read-only RBAC proof: `ready` on context `kind-webterm-k8s`; ServiceAccount `system:serviceaccount:webterm-system:webterm-kubernetes-readonly` has `allowed_count=7`, `denied_count=7`, and no live `kubectl auth can-i` errors;
- release scope: `local`, target environment `local`, local indicator count `8`; this proves the local stack is useful for integration testing but not for production approval;
- remaining local release blockers: `readiness:sidebar_release_scope=missing` and `release_scope:local`.
- handoff artifact: `artifacts/kubernetes_ops_release_handoff.md` is generated from current release evidence and reports `status=blocked`, `can_enable_sidebar=false`, blockers `readiness:sidebar_release_scope=missing` and `release_scope:local`; it now includes a `Release Proofs` section with `action_controls=ready`, `admin_mode_safety=ready`, `post_review_retention=ready`, `external_evidence_bundle=ready`, `interactive_transport_evidence=ready`, `interactive_live_smoke=ready`, `interactive_shell_streams=ready`, and `normal_user_surface=ready`.

`sidebar_release_scope` also inspects enabled provider names/base URLs, cluster context/name values, and the current owned Kubernetes MCP URL. Even with `KUBERNETES_OPS_RELEASE_ENVIRONMENT=production`, `KUBERNETES_OPS_PRODUCTION_APPROVAL_REF` and `KUBERNETES_OPS_READY_FOR_SIDEBAR=true`, local markers such as `host.docker.internal`, `localhost`, `kind-*`, `local-*`, `mcp-demo` or fixture names keep the sidebar locked.
Runtime readiness adds `release_evidence_artifact` outside the release artifact itself to avoid self-reference. The live local API currently reports that artifact check as `ready` and optional because the artifact is fresh, but it becomes required when the sidebar flag is enabled.

Do not copy local bootstrap passwords or provider tokens into docs, commits, screenshots, or support replies.

## 4. Provider Outage Disaster Recovery

Symptoms:

- readiness `provider_health` reports `error`, `missing`, or `stale`;
- overview shows `provider_issues > 0`;
- provider cards show stale sync status or `last_error`;
- sync worker cycles report repeated failures.

Immediate response:

1. Keep WebTerm in read-only mode. Do not create mutation shortcuts.
2. Confirm whether the outage is Rancher, Devtron, Fleet, network, DNS, token, or WebTerm worker.
3. Use admin-only provider probe for the affected provider:

   ```text
   POST /api/kubernetes/providers/{provider_id}/probe/
   ```

4. If probe fails with auth errors, rotate the provider token using managed secret update or external secret rotation.
5. If probe succeeds but sync is stale, restart the `kubernetes-ops-sync` worker and watch readiness.
6. If Rancher is down, use Rancher DR procedure outside WebTerm; WebTerm should show stale cached rows and audited deep links only.
7. If Devtron is down, app history/log links may fail; use Rancher/Fleet read-only evidence where available.
8. If Fleet data is stale, do not continue a rollout from WebTerm. Validate in Rancher/Fleet first.

Operator communication:

- Tell users which provider is stale and the last successful sync time.
- Mark WebTerm Kubernetes data as stale in the incident note.
- Use external Rancher/Devtron status pages or platform incident channels for root-cause ownership.

Recovery proof:

- provider probe succeeds;
- `provider_health` is ready;
- `sync_worker` is running and not stale;
- `overview.summary.provider_issues == 0`;
- representative cluster/app/Fleet rows show fresh `last_sync_at`.

## 5. Sync Worker Recovery

One-shot validation:

```bash
python manage.py sync_kubernetes_ops --dry-run
python manage.py sync_kubernetes_ops
```

Worker recovery:

1. Check whether another worker holds the lease.
2. Stop duplicate workers.
3. Start one worker:

   ```bash
   python manage.py run_kubernetes_ops_sync_worker --daemon --interval 300
   ```

4. Watch readiness `worker_state`:

   - `status=running`;
   - `is_stale=false`;
   - `last_cycle_finished_at` updates;
   - `consecutive_failures` stops increasing.

Repeated failure behavior:

- the worker backs off up to `KUBERNETES_OPS_SYNC_MAX_BACKOFF_SECONDS`;
- readiness exposes failure streak and next delay;
- do not bypass backoff by starting many workers.

## 6. Token Rotation And Secret Handling

Allowed storage:

- `env:NAME`;
- `vault://...`;
- `secret://...`;
- `k8s://...`;
- cloud secret references;
- `managed:kubernetes-provider-token:{id}` generated by WebTerm.

Forbidden:

- raw provider token in `secret_ref`;
- kubeconfig in API response;
- query-string tokens in audit payload;
- log snapshots containing bearer tokens, passwords, API keys, or kubeconfig material.

Rotation steps:

1. Create or fetch the new token in the provider system.
2. Update the provider with `secret_value` or an external secret reference.
3. Run provider probe.
4. Run one-shot sync.
5. Check readiness and provider freshness.
6. Verify audit contains metadata only, not the token.

## 7. Audit Retention

Dry-run first:

```bash
python manage.py cleanup_kubernetes_ops_audit
```

Apply only after reviewing counts:

```bash
python manage.py cleanup_kubernetes_ops_audit --apply
```

Policy:

- default retention is `KUBERNETES_OPS_AUDIT_RETENTION_DAYS=365`;
- audit cleanup must not expose payload secrets;
- keep longer retention only when legal/compliance requires it;
- export evidence before cleanup if an incident or dispute is open.

### Admin Recording Retention

Admin Mode interactive evidence has two retention layers:

- metadata retention deletes the `K8sAdminRecording` row and cascades its events;
- transcript retention deletes only `K8sAdminRecordingEvent` rows and marks the recording transcript as cleaned.

Dry-run first:

```bash
python manage.py cleanup_kubernetes_admin_recordings
```

Inventory-only:

```bash
python manage.py cleanup_kubernetes_admin_recordings --inventory
```

Apply only after reviewing counts:

```bash
python manage.py cleanup_kubernetes_admin_recordings --apply
```

Policy:

- default metadata retention is `KUBERNETES_ADMIN_INTERACTIVE_METADATA_RETENTION_DAYS=365`;
- default transcript retention is `KUBERNETES_ADMIN_INTERACTIVE_TRANSCRIPT_RETENTION_DAYS=30`;
- default event bounds are `KUBERNETES_ADMIN_TRANSCRIPT_EVENT_MAX_CHARS=2000` and `KUBERNETES_ADMIN_TRANSCRIPT_EVENT_MAX_COUNT=2000`;
- recording cleanup must not expose event payload secrets;
- keep longer retention only when legal/compliance requires it;
- export incident evidence before cleanup if an investigation is open.

## 8. Terminal And Debug Policy

Current policy:

- ordinary users stay in the read-only WebTerm Kubernetes cockpit;
- `KUBERNETES_ADMIN_MODE_ENABLED=false` is the global Admin Mode kill switch; it keeps normal read-only cockpit access available but disables Admin read/write/break-glass capabilities, blocks new Admin sessions, and blocks existing active Admin sessions before any provider call;
- native write actions stay disabled by default until their matching `KUBERNETES_ADMIN_NATIVE_*_ENABLED=true` flag and explicit Admin Mode grant are present;
- node maintenance stays disabled by default until `KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED=true`; even then cordon/uncordon require approved break-glass node scope, and drain execution additionally requires `KUBERNETES_ADMIN_NODE_DRAIN_EXECUTION_ENABLED=true`, exact confirmation, pod preflight, and Kubernetes `policy/v1` Eviction API so PDBs stay authoritative;
- logs/watch/resource-events can use bounded Admin Mode snapshots/follow streams with active sessions and metadata-only audit;
- exec and port-forward are break-glass-only bridges and stay fail-closed unless their native, stream/tunnel and recording gates are all enabled;
- cluster terminal and node debug have metadata-only fail-closed REST start/stop lifecycle endpoints plus opt-in WebSocket provider-stream foundations; the streams stay disabled by default and open only when the matching transport flag, recording flag, provider path-template contract, active approved break-glass session and production restricted-evidence gate are satisfied before action/audit/provider side effects;
- no attach route exists.

Planned low-level admin work lives in `docs/architecture/KUBERNETES_LOW_LEVEL_ADMIN_MODE_PLAN.md`. That plan is not an enablement signal: Admin Mode remains disabled until its separate permissions, admin sessions, TTL, approval, audit, stream handling, and release gates are implemented and tested.

Before any future production exec bridge, all controls must exist:

- separate `k8s.exec` permission;
- human approval with reason, target, TTL, and blast radius;
- session recording or command transcript retention;
- restricted kube context/service account with namespace and verb allowlist;
- `KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF` pointing to the reviewed restricted credential/live RBAC proof before provider-native exec, port-forward, cluster terminal, or node debug transport is enabled in production;
- `KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF` pointing to the reviewed network policy/egress proof before any production provider-native port-forward tunnel, plus exact non-wildcard `KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS`, default protected namespace coverage, and max duration <=900s;
- audit event for request, approval, start, stop, exit code, and verification;
- break-glass workflow for node debug;
- post-incident review for emergency access.

Until then, use WebTerm read-only inventory, logs/describe/resource-event snapshots, bounded Admin Mode follow streams where configured, and audited Rancher/Devtron fallback links for staff/admin only. Cluster terminal and node debug WebSocket streams may be tested in local/dev only behind their explicit flags and provider contracts; production enablement still requires restricted credential evidence and release approval.

Interactive transport readiness:

- Readiness exposes optional check `admin_interactive_transport`.
- In local/dev mode, provider-native exec/port-forward stream tests can run without production evidence.
- In production mode (`KUBERNETES_OPS_RELEASE_ENVIRONMENT=production`), enabled interactive transports are blocked before action/provider side effects unless the matching recording flag is enabled and `KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF` is set.
- Enabled cluster terminal additionally requires each enabled Rancher provider to define `cluster_terminal_path_template` with `{cluster_id}` and `{namespace}`; enabled node debug requires `node_debug_path_template` with `{cluster_id}` and `{node_name}`. Missing or unsafe templates keep `admin_interactive_transport` missing before action/audit/provider side effects.
- Production port-forward tunnel has an additional readiness policy: `KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF` must be set, `KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS` must be non-empty and non-wildcard, protected namespaces must include the default system namespaces, and `KUBERNETES_ADMIN_PORT_FORWARD_MAX_DURATION_SECONDS` must be <=900.
- The evidence ref should point to an approved artifact or ticket proving the restricted ServiceAccount/context, namespace scope, allowed subresources, denied Secrets/nodes/attach/base writes, TTL and rollback cleanup.
- Release handoff and release summary expose this same gate: `readiness:admin_interactive_transport=missing` tells the operator to disable the transport or provide recording gates plus the required restricted credential evidence, provider path-template contracts, and port-forward network-policy evidence.

Admin action post-review:

- Use `GET /api/kubernetes/admin/actions/?all=1&post_review_status=pending` to find final dangerous Admin actions that still need review. `completed`, `not_ready`, `required`, `any`, and `none` are also supported for queue checks.
- Readiness also exposes optional check `admin_action_post_review`; status `manual` means at least one dangerous action still needs review or the bounded scan was truncated.
- Use `POST /api/kubernetes/admin/actions/{action_id}/review/` after a dangerous Admin action reaches a final status.
- Body fields: `outcome` (`accepted`, `verified`, `needs_followup`, `incident_created`), required `summary`, optional `evidence_ref`, optional `follow_up_ref`.
- Review is staff-only. Write actions require `kubernetes_admin_write`; break-glass session actions, exec, port-forward, node maintenance, cluster terminal and node debug require `kubernetes_break_glass`.
- Review text and evidence references are redacted before storage, audit and report output.
- The action list exposes `review_summary`; the action report at `GET /api/kubernetes/admin/actions/{action_id}/report/` exposes `post_review_status`, `has_post_review`, sanitized action evidence, recordings and timeline.

External action verification:

- WebTerm may record that an approved action was executed outside WebTerm in Rancher, Fleet, Devtron, or GitOps.
- Use `POST /api/kubernetes/actions/{request_id}/approve-external/` with staff access and `approval_ref` to record external approval. This marks the request `approved_external` and still keeps `native_execution_enabled=false`.
- Use `POST /api/kubernetes/actions/{request_id}/verify-external/` after external execution to store sanitized outcome, evidence, checks, and external reference. Verification requires the request to be `approved_external`.
- This updates the action request report and audit trail only. It must not be treated as WebTerm native execution, and it must not call Kubernetes mutation APIs.
- Action status/report reads are scoped: the requester and staff can read the request; other Kubernetes readers get `request_not_found` even when they know the UUID.
- The action report endpoint includes a bounded audit timeline for the request, including create, approve, verify, reject, and blocked execution events when present.
- Terminal action reports are immutable through the public action endpoints: after `verified_external`, `verification_failed`, or `execution_blocked`, later execute/verify calls are rejected with `action_request_not_pending` and audited instead of overwriting the report.
- Sensitive evidence keys such as token, secret, password, authorization, cookie, and credentials are redacted before storage/response.
- GitOps merge-request actions validate repository, branch, path, and change summary; reject repository URLs with embedded credentials; strip query/fragment parts; and return only a title/description/checklist preview. WebTerm does not write to Git.
- `verify_kubernetes_ops_release` includes a rollback-only action-controls proof for this contract: approval request creation, external approval recording, external verification redaction, disabled native execution, blocked native execute attempt, terminal-report overwrite rejection, sanitized GitOps MR template, and no persistent proof rows.

## 9. Rollback And Disablement

Fast disable:

1. Set:

   ```text
   KUBERNETES_OPS_RELEASE_ENVIRONMENT=local
   KUBERNETES_OPS_READY_FOR_SIDEBAR=false
   KUBERNETES_ADMIN_MODE_ENABLED=false
   ```

2. Restart the web process if env is not hot-reloaded.
3. Keep API feature-gated; remove explicit `kubernetes`, `kubernetes_admin_read`, `kubernetes_admin_write`, or `kubernetes_break_glass` access from affected users/groups if necessary.
4. Stop the sync worker if provider calls are causing load:

   ```bash
   docker compose --env-file .env.production -f docker-compose.production.yml stop kubernetes-ops-sync
   ```

5. Do not delete normalized rows during incident triage; stale data can be useful evidence.

Rollback proof:

- sidebar is hidden;
- users without explicit feature get 403;
- Admin Mode policy reports `admin_mode_enabled=false`, new Admin sessions return `admin_mode_disabled`, and old active Admin sessions cannot read live resources or metrics;
- readiness explains missing/stale gates;
- worker is stopped or healthy;
- no raw secrets are present in responses or audit.

## 10. Operator Daily Checklist

Daily:

- open Kubernetes Ops readiness;
- confirm provider health is fresh;
- confirm `kubernetes-ops-sync` worker heartbeat is current;
- review stale provider/resource warnings;
- review recent `k8s.provider.*`, `k8s.deeplink.open`, `k8s.pod.logs.snapshot`, and `k8s.diagnosis_draft.create` audit rows;
- check audit retention dry-run counts when near policy boundaries;
- verify no native exec/debug routes or UI actions were enabled outside the approved roadmap;
- keep Rancher/Fleet/Devtron as source of truth for actual mutations.
