# WebTerm Kubernetes Admin Mode: Freelens++ Implementation Plan

Last reviewed: 2026-07-02

## 1. Goal

Build the low-level Admin Mode chapter of the master Kubernetes plan in `docs/WebTerm_Kubernetes_Ops_Rancher_Fleet_Devtron_Report.md`: a WebTerm-only, improved Freelens-style Kubernetes workspace that covers practical cluster-admin workflows while keeping WebTerm's stronger platform controls: feature gates, per-user permissions, audit, approvals, short-lived sessions, Studio/AI diagnosis, and Rancher/Fleet/Devtron backend integration.

This is not a UI polish plan. The first implementation can be visually rough. The priority is that the core workflows work correctly, are testable, and do not leak cluster credentials to the browser.

Target product shape:

```text
WebTerm Kubernetes = single user-facing cockpit and Admin Mode
WebTerm Kubernetes Ops = safe read-only operator cockpit
WebTerm Kubernetes Admin Mode = Freelens++ low-level admin console for trusted users
Rancher = backend cluster source of truth, RBAC, cluster API/proxy, Fleet owner
Fleet = backend GitOps/HelmOps rollout source of truth
Devtron = backend application/AppOps source of truth, app history/logs/rollback/debug context
```

Normal users must work inside WebTerm only. Rancher, Fleet, and Devtron UIs are staff/admin fallback and break-glass paths, not the daily workflow.

### 1.1 Canonical merged plan

This file is the canonical merged implementation plan for the "improved Freelens" part of WebTerm Kubernetes. The broader report in `docs/WebTerm_Kubernetes_Ops_Rancher_Fleet_Devtron_Report.md` explains the business/product integration with Rancher, Fleet and Devtron; this file turns that strategy into the concrete backend, safety, API and test backlog.

Do not split the same decisions across both documents. Keep this rule:

- `docs/WebTerm_Kubernetes_Ops_Rancher_Fleet_Devtron_Report.md` = why the stack exists, what role Rancher/Fleet/Devtron play, what the user sees at product level.
- `docs/architecture/KUBERNETES_LOW_LEVEL_ADMIN_MODE_PLAN.md` = exact Freelens++ execution plan, API contracts, sessions, audit, streaming, write actions, break-glass and test gates.

The final product should not be "WebTerm plus links to Rancher/Devtron". It should be a WebTerm-native Kubernetes workspace that takes the useful daily workflows from Freelens, Rancher, Fleet and Devtron, but runs them through WebTerm's access model, approvals, audit and backend-held credentials.

## 2. Current State In This Worktree

Current implementation is deliberately safe and mostly read-only:

- `kubernetes_ops/` Django app exists with providers, clusters, namespaces, workloads, pods, services/ingresses, events, Fleet bundles, Devtron apps, audit, readiness, release evidence, and guarded action request lifecycle.
- `frontend/src/pages/KubernetesPage.tsx`, `KubernetesAdminPage.tsx`, `KubernetesClusterDetailPage.tsx`, `KubernetesFleetPage.tsx`, `KubernetesDevtronPage.tsx`, and `/settings/kubernetes` exist.
- Provider setup supports Rancher and Devtron with external/managed secret references, probe, dry-run sync, and sync.
- Read-only APIs include overview, clusters, namespaces, namespace detail, workloads, workload detail, pods, pod detail, network, network detail, diagnostics summary, events, Helm release ownership, Fleet bundles, Fleet bundle detail, Devtron apps, Devtron app detail with AppOps delivery context, workload describe snapshot, Admin live describe, bounded pod logs snapshot with multi-container selection, and audit.
- Public/read-only serializers are now user-aware: normal Kubernetes users receive WebTerm-native inventory with empty external `links`, hidden provider `base_url`, sanitized sensitive label/metadata keys and sensitive string values, and `external_links_policy.mode=webterm_native_only`; staff/admin responses keep sanitized Rancher/Fleet/Devtron fallback links without query, fragment, userinfo, token or secret-link leakage. `GET /api/kubernetes/providers/` and provider detail are staff-only config endpoints.
- Existing action requests support restart, scale, controlled patch, controlled delete, guarded dry-run-proof apply, Fleet pause/resume, GitOps MR and Devtron rollback intent. Native action execution is still disabled by default, but `execute-approved` now has opt-in WebTerm-native paths for `k8s.rollout.restart`, `k8s.workload.scale`, non-sensitive `k8s.resource.patch`, `k8s.resource.delete`, and `k8s.resource.apply`: they require `KUBERNETES_ACTION_REQUEST_NATIVE_EXECUTION_ENABLED=true`, the matching Admin native flag, an already approved action request, and an active approved Admin write session whose namespace/kind/verb scope covers the target; otherwise the old fail-closed `execution_disabled_by_policy` behavior remains. In production release mode, prod/prod-like native writes additionally fail before provider/action side effects unless `KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF` is present. Apply action requests reference a fresh owner-matched Admin `dry_run_apply` proof and store only proof metadata/fingerprint, not the raw manifest; execution requires the manifest again at execute time and delegates to the guarded Admin apply service. Patch action requests reject bodies that would require redaction, so action requests do not store or replay Secret/token patch bodies. Delete action requests require exact typed confirmation and block protected namespaces/kinds before approval and native execution. Every controlled action request now carries a metadata-only `rollback_plan`: restart uses rollout recovery/GitOps or Devtron previous version evidence, scale stores previous replicas for scale-back, apply requires rollback source + dry-run proof, patch requires previous snapshot + reverse patch dry-run, and delete requires restore source + dependent health evidence; raw manifest bodies, patch bodies, delete confirmations and secrets are not stored in rollback evidence. Native execution writes both an action-specific `verification_plan` and the linked `rollback_plan` into the report; staff post-action verification can close an `executed_native` request as `verified_native`, and `verify_kubernetes_ops_native_actions` can automatically close it only after fresh read-only inventory proves all action checks, otherwise the plan stays `needs_review`; both paths preserve the linked `K8sAdminAction` id with sanitized evidence. `GET /api/kubernetes/actions/summary/` returns requester-scoped or staff `all=1` metadata-only queue counters for pending approval, approved external, needs verification, blocked, high-risk and production-like attention items without exposing raw target/report payloads. `GET /api/kubernetes/actions/` now returns sanitized requester-scoped action request rows, with staff `all=1` and filters for status/action/risk/cluster/limit. `GET /api/kubernetes/actions/{action_id}/report/` returns requester/staff-only sanitized request, report, execution policy, summary, and bounded audit timeline; non-owners receive 404. Action request scalar text is now guarded too: `reason`, approval summaries, verification summaries, `approval_ref`, and `external_ref` are redacted before storage/response/audit output, and single URL references strip userinfo, query strings and fragments so change-ticket links cannot leak tokens.
- `kubernetes_ops.permissions` keeps `can_exec=false`, `can_port_forward=false`, and `can_node_maintenance=false` by default, blocks `pod.exec`, `port_forward`, `node_maintenance`, `node_drain`, and `cluster_terminal`, and keeps `apply_yaml`/`patch`/`scale`/`rollout_restart`/`delete` blocked unless the matching `KUBERNETES_ADMIN_NATIVE_*_ENABLED=true` flag plus explicit write/break-glass access is present.
- Admin Mode permission flags now exist as explicit opt-in features: `kubernetes_admin_read`, `kubernetes_admin_write`, `kubernetes_break_glass`, and `kubernetes_secret_read`.
- Admin Mode now has a global env kill switch: `KUBERNETES_ADMIN_MODE_ENABLED=false` keeps normal Kubernetes read-only cockpit access available, but turns off Admin read/write/break-glass capabilities, blocks new Admin sessions with `admin_mode_disabled`, and blocks already-active Admin sessions before live provider/resource/metrics calls without deleting session/action data.
- `kubernetes_ops.permissions` exposes Admin Mode policy fields separately from the safe cockpit: `can_admin_read`, `can_live_resource_get`, `can_view_full_yaml`, `can_stream_logs`, `can_admin_write`, `can_dry_run_apply`, `can_break_glass`; native `can_apply_yaml`, `can_patch`, `can_scale`, `can_restart`, `can_delete`, `can_exec`, and `can_port_forward` are runtime-gated and default to `false`.
- `K8sAdminSession`, `K8sAdminAction`, `K8sAdminRecording`, and bounded redacted `K8sAdminRecordingEvent` are implemented in `kubernetes_ops/admin_models.py` with migrations `0009_k8sadminsession_k8sadminaction`, `0010_k8sadminrecording`, and `0011_k8sadminrecordingevent`.
- Admin Mode recording evidence APIs now exist at `GET /api/kubernetes/admin/recordings/` and `GET /api/kubernetes/admin/recordings/{recording_id}/`: owners see their sanitized recording rows, staff can use `all=1`, filters cover session/action/cluster/operation/status, detail returns bounded redacted transcript events, and non-owners receive empty list/404. `cleanup_kubernetes_admin_recordings` and `cleanup_interactive_recordings()` enforce metadata/transcript retention: transcript TTL deletes only event rows and marks the recording transcript as cleaned, while metadata TTL deletes the recording row and cascades events. Readiness now exposes optional `admin_recording_retention` with cleanup commands and expired evidence counts, and terminal safety exposes transcript event limits plus the cleanup command.
- Session lifecycle APIs exist under `/api/kubernetes/admin/sessions/`: create/list/detail/approve/revoke/close/review. Read sessions can become active for `kubernetes_admin_read`; write and break-glass sessions start as `pending_approval` and require reason plus staff approval with `approval_ref`; active sessions can now be closed explicitly without treating normal completion as revoke; closed/revoked/expired break-glass sessions require a staff post-review marker.
- Backend live read-only Admin Mode resource APIs now exist under `/api/kubernetes/admin/clusters/{cluster_id}/`: `discovery/`, `resources/`, `resources/detail/`, `resources/describe/`, `yaml/`, resource `events/`, `crds/`, `nodes/`, and `metrics/`. They require an active admin session, use backend-held Rancher credentials, build Rancher proxy paths, redact Secret/sensitive fields and sensitive string values, write `K8sAdminAction`, and audit metadata only. `resources/detail/` is the first Freelens-like single-object detail contract: sanitized resource, describe-style summary, ownership, and bounded resource Events in one response without raw body audit. `resources/describe/` adds a live read-only describe contract: sanitized identity/spec/status summary, bounded resource Events, and related Pods/ReplicaSets when the active session allows those read scopes; action/audit evidence stores only counts/flags and skipped reasons, not raw object, event or pod body. `nodes/` is the first dedicated node inventory contract: Ready/NotReady, roles, taints, unschedulable state, capacity/allocatable, addresses and nodeInfo summary without raw node body in action/audit evidence. `metrics/` reads `metrics.k8s.io/v1beta1` node/pod usage, normalizes CPU millicores and memory bytes, enforces namespace scope for all-namespace pod metrics, and stores only counts/totals in action/audit evidence. Admin action evidence APIs now expose sanitized action list/detail/report rows to the action owner or staff, and `POST /api/kubernetes/admin/actions/{action_id}/review/` lets staff close dangerous action evidence with sanitized post-review outcome/summary/evidence. Readiness now exposes optional `admin_action_post_review` with pending/completed/not_ready counts and a bounded pending-action preview.
- The Admin resource registry is now separate from path orchestration and covers the common Freelens-style object set: Namespace, Node, Pod, Service, ConfigMap, Secret, ServiceAccount, PVC/PV, Endpoints, LimitRange, ResourceQuota, Deployment, StatefulSet, DaemonSet, ReplicaSet, Job, CronJob, HPA, PDB, Ingress, NetworkPolicy, EndpointSlice, StorageClass, Role/RoleBinding, ClusterRole/ClusterRoleBinding and CRD. Common kubectl aliases such as `ns`, `po`, `svc`, `cm`, `sa`, `pvc`, `pv`, `deploy`, `sts`, `ds`, `rs`, `hpa`, `pdb`, `netpol`, `sc` and `crd` resolve to typed backend refs while namespaced and cluster-scoped Rancher proxy paths stay explicit and tested.
- Admin discovery now returns a safe CRD-backed resource catalog in the same response as core API discovery. The payload exposes only `api_version`, `group`, `version`, `kind`, `resource`, `scope`, `namespaced`, `short_names`, `categories`, `storage` and CRD name; it does not serialize raw CRD schemas, labels, annotations or provider bodies. If the active session cannot read CRDs, or the provider CRD request fails, discovery still succeeds and reports `crd_resources.status=unavailable` with a machine-readable reason.
- Admin discovery also returns `api_resources`, a normalized catalog built from Kubernetes `APIResourceList` payloads for core `/api/v1` and bounded `/apis/{group}/{version}` discovery. It includes only safe selector fields (`api_version`, `group`, `version`, `kind`, `resource`, `namespaced`, `verbs`, `short_names`, `categories`, `singular_name`, `source`), skips subresources such as `pods/status`, and reports `status=partial` with failed group/version ids if one API group cannot be fetched. Raw group-version provider bodies are not serialized to the browser or audit.
- Admin discovery now includes `resource_catalog`, a merged frontend-ready picker contract over static common resources, `api_resources` and `crd_resources`. Each entry has stable `id`, exact `query` values (`api_version`, `kind`, `resource`), scope, verbs, short names/categories, `sources`, `cluster_available`, `custom`, `ui_group`, `safe_read_actions` and `has_mutating_verbs`; duplicates such as static `Pod` plus live API `Pod` are merged, and CRD/API matches such as `Widget/widgets` keep both `api` and `crd` sources. The catalog also exposes bounded aggregate `counts` and `groups` for Workloads, Network, Config, Storage, Security, Policy, Cluster, Custom resources and Other, so the frontend can build a Freelens-like resource picker without parsing raw discovery bodies. Action evidence stores only catalog item/group/custom counts. The catalog reports `partial` when API or CRD discovery is partial/unavailable without exposing raw provider bodies.
- Custom resources can now be opened with the exact CRD plural from discovery. Admin list/get/YAML/detail/describe/events/watch endpoints accept optional `resource`, and WebSocket watch snapshot/follow/continuous paths preserve it too. If `resource` is omitted, common resources keep the old registry/plural fallback; if it is supplied, Rancher proxy paths use that exact plural so irregular CRDs such as `kind=Index`, `resource=indices` do not degrade into guessed paths like `indexes`.
- The TypeScript Admin client contract now mirrors that backend behavior: discovery has typed `api_resources`, `crd_resources` and `resource_catalog` sections, and list/YAML/detail/watch client calls preserve optional `resource` so UI code can pass exact CRD plurals from discovery. Demo/offline Kubernetes fallback returns the same catalog shape for UI development without live providers.
- Admin resource list/get/detail responses now include a safe `summary` contract for table rows and compact detail headers. It is computed from already sanitized resources and includes identity, creation timestamp, generation/resourceVersion, owner references, phase/reason, ready state, bounded condition rows and condition aggregate, replica counters, container names/counts/init-count/images/restarts, Service port summary, Node readiness/roles, workload selector key/strategy/observed-generation summary, storage summary for PVC/PV/StorageClass, Ingress class/host/rule/TLS/backend summary, ConfigMap/Secret metadata key counts, Job/CronJob batch state, HPA target/replica/metric summary, PDB health/disruption summary, NetworkPolicy selector/type/rule counts, RBAC rule/binding risk counters, Endpoints/EndpointSlice readiness and port counts, ResourceQuota/LimitRange key/value summaries, ServiceAccount secret-ref counts without secret names, and bounded redacted label/annotation/spec/status key lists. This lets the frontend render Freelens-like resource tables and degraded-status reasons without parsing arbitrary raw Kubernetes JSON or exposing sensitive strings. Type-specific summary builders now live in `admin_resource_type_summary.py` so the main row summary helper stays below the architecture guard limit. The resource sanitizer depth is bounded at 10 so normal nested Kubernetes fields such as Ingress backend service names survive redaction while deeply nested payloads still truncate.
- Secret values remain redacted by default across resource list/get/YAML/detail responses. Secret lists are explicit metadata-only responses: even with `include_secret_values=1`, list payloads return `secret_values.visible=false` and redact `data`/`binaryData`/`stringData`. A named Secret body can be revealed only when all three gates are present: explicit `kubernetes_secret_read` feature, `KUBERNETES_ADMIN_SECRET_READ_ENABLED=true`, and request `include_secret_values=1`. The reveal applies only to `Secret.data`, `Secret.binaryData`, and `Secret.stringData`; sensitive metadata/annotations still redact, denied reveal requests stop before provider calls, and action/audit summaries store only machine-readable `secret_values_requested`/`secret_values_visible` flags, never raw secret values.
- Admin resource responses now include WebTerm ownership context: list items get `webterm_ownership`, single resource/YAML responses get top-level `ownership`, and lists get `ownership_summary`. The owner model detects normalized Devtron apps, Fleet bundle labels/annotations, external app ownership, Rancher inventory matches, and backend write services now block direct apply/patch/scale/restart/delete for Devtron/Fleet/external-owned resources before provider calls.
- Helm release ownership now has a read-only WebTerm-native endpoint at `GET /api/kubernetes/helm/releases/`: it infers Helm releases from normalized Rancher workloads, Devtron apps and Fleet bundles, applies the one-release-one-owner rule, marks Fleet/Devtron/external/unknown/conflicting releases as guarded, returns `change_path` (`fleet_gitops_or_mr`, `devtron_rollback_or_deploy`, `resolve_owner_before_mutation`, etc.), hides fallback links from normal users, sanitizes labels/links, and audits only release/conflict/owner counts.
- Diagnostics summary now has a read-only WebTerm-native endpoint at `GET /api/kubernetes/diagnostics/summary/`: it accepts cluster/namespace/workload/pod/network scope, builds a compact triage payload from normalized inventory and existing detail contracts, returns health severity, node/readiness gaps, restarts, unhealthy namespace/workload/pod counts, warning-event counts, owner/change-path context and safe next steps, never includes external provider links, and audits only scope ids/counts/finding totals.
- Staff release readiness summary now has a read-only endpoint at `GET /api/kubernetes/release/summary/`: it does not run live provider checks, reads current readiness plus the latest release evidence artifact, groups production blockers into runtime readiness, production scope, release artifact and release evidence buckets, returns required commands/next steps for the Settings UI, returns `progress` with backend DoD percent, runtime-readiness percent, production/sidebar stage and remaining blocker categories, returns `completion_audit` with explicit `core_backend_complete`, `runtime_readiness_complete`, `production_evidence_complete`, `sidebar_enablement_complete` and remaining categories, returns `production_evidence_checklist` with required/present/status for core refs, latest external evidence bundle artifact checks and machine-readable `gap_summary`, returns `operator_command_plan` with production prerequisite/release artifact command phases, recommended next manual/command step and `blocking_summary`, returns `production_execution_plan` with the same blocked-until/phase/command contract as the handoff artifact, and exposes only metadata/status fields so raw release artifact provider tokens, credentialed URLs or env values are not serialized.
- Capability matrix now has a read-only endpoint at `GET /api/kubernetes/capabilities/`: it turns WebTerm feature grants and Kubernetes runtime flags into explicit modes/workflows for the frontend (`safe_cockpit`, live explorer, logs, dry-run/apply/patch/scale/restart/delete, exec, port-forward, node maintenance, terminal/debug, secret values), returns `available`/`requestable`/`blocked_reason`, required feature, runtime/transport flags and session requirements, and never runs live provider checks.
- Admin write preview has started with `POST /api/kubernetes/admin/clusters/{cluster_id}/resources/schema-validate/` and `/resources/dry-run-apply/`: schema validation requires `kubernetes_admin_write` plus an active approved write session, reads CRD `openAPIV3Schema` through the backend Rancher proxy when available, validates bounded `required`/`type`/`enum`/number constraints without returning manifest body, writes metadata-only `K8sAdminAction`/audit, and cannot be used as dry-run proof. Dry-run apply sends Kubernetes server-side apply with `dryRun=All`, returns sanitized submitted/server objects, top-level diff summary and bounded path-level `diff.changes` for UI review, redacts Secret data, writes `K8sAdminAction`, audits only diff counts/metadata, and can be linked to an approval-gated `k8s.resource.apply` request through its proof id/fingerprint.
- Controlled native apply now has a fail-closed backend path at `POST /api/kubernetes/admin/clusters/{cluster_id}/resources/apply/`: by default it returns `native_apply_disabled`; when `KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED=true`, the normal path still requires `kubernetes_admin_write`, an active approved write session, `apply` verb in the session, request reason, a fresh matching dry-run `K8sAdminAction` proof, and Secret-safe audit/action summaries. Emergency dry-run bypass exists only for active approved break-glass sessions when `KUBERNETES_ADMIN_BREAK_GLASS_APPLY_BYPASS_ENABLED=true`; bypassed actions are explicitly marked with `dry_run_bypassed`, `break_glass`, `approval_ref`, and session id in action/report evidence.
- Controlled native patch now has a fail-closed backend path at `POST /api/kubernetes/admin/clusters/{cluster_id}/resources/patch/`: by default it returns `native_patch_disabled`; when `KUBERNETES_ADMIN_NATIVE_PATCH_ENABLED=true`, it requires `kubernetes_admin_write`, an active approved write session, `patch` verb in the session, namespace/kind scope, request reason, bounded patch body size, and Secret-safe metadata-only action/audit summaries.
- Controlled workload mutation backend paths now exist at `POST /api/kubernetes/admin/clusters/{cluster_id}/resources/scale/` and `/restart/`: by default they return `native_scale_disabled` / `native_restart_disabled`; when enabled, they require active approved write sessions, matching verbs, namespace/kind scope, request reason, bounded replicas for scale, and metadata-only audit/action records.
- Controlled native delete now has a fail-closed backend path at `POST /api/kubernetes/admin/clusters/{cluster_id}/resources/delete/`: by default it returns `native_delete_disabled`; when enabled, it requires active approved write sessions, `delete` verb, namespace/kind scope, request reason, exact typed confirmation, protected namespace/kind denylist, and metadata-only audit/action records.
- Controlled node maintenance now has break-glass backend paths at `POST /api/kubernetes/admin/clusters/{cluster_id}/nodes/cordon/`, `/uncordon/`, and `/drain/`: by default they return `native_node_maintenance_disabled`; when `KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED=true`, cordon/uncordon require active approved break-glass sessions, `node` scope, matching verb, request reason, metadata-only audit/action records, and then patch Node `spec.unschedulable`; drain remains blocked with `node_drain_execution_disabled` until `KUBERNETES_ADMIN_NODE_DRAIN_EXECUTION_ENABLED=true`, then lists pods on the node, blocks before cordon/eviction on unsafe DaemonSet/emptyDir/unmanaged/pod-limit/truncated-list conditions, cordons the node, and uses Kubernetes `policy/v1` Eviction API instead of deleting pods so PDBs remain enforced by Kubernetes.
- Privileged service paths (`dry_run_apply`, `apply`, `patch`, `scale`, `restart`, `delete`, `exec`, `port_forward`) now enforce approved-session evidence at service level: a forged/manual `status=active` session without `approval_ref`, `approved_by`, and `approved_at` fails before provider requests or action/audit side effects. Controlled native write paths additionally share prod guards: prod clusters or prod-like namespaces return `production_approval_required` before any Rancher provider request if approval evidence is missing, and production release mode returns `restricted_credential_evidence_required` before provider/action side effects when `KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF` is absent.
- Release evidence now includes a rollback-only `admin_mode_safety` proof: it temporarily enables native Admin Mode flags, creates unapproved active write/break-glass sessions, verifies dry-run/apply/patch/scale/restart/delete/exec/port-forward are blocked before provider/action side effects, verifies prod writes return `production_approval_required`, and rolls back all temporary rows.
- Release evidence now also includes a rollback-only `normal_user_surface` proof: it creates temporary reader/staff users and provider inventory rows, verifies normal users receive WebTerm-native payloads only, verifies provider config/base URLs and external Rancher/Fleet/Devtron links stay hidden from normal users, verifies cluster/app/workload/pod/Fleet/network/Helm/Devtron-detail/diagnostics-summary sensitive-label metadata and sensitive string value redaction, verifies provider `secret_ref` is not serialized to reader/staff frontend payloads, verifies rollback-only token/kubeconfig-like marker values are absent from reader/staff frontend surfaces, verifies fallback deeplink audit is staff-only, verifies staff fallback links are sanitized, and rolls back all temporary rows.
- Release evidence includes a rollback-only `secret_read_controls` proof: it verifies Secret YAML is redacted by default, Secret list stays metadata-only with `secret_values.mode=list_metadata_only`/`visible=false` even when values are requested, raw values do not enter action summaries, reveal is rejected without explicit `kubernetes_secret_read`, reveal is rejected without `KUBERNETES_ADMIN_SECRET_READ_ENABLED=true`, denied reveal does not call the provider transport, and reveal works only when all gates are present.
- Release evidence includes a rollback-only `audit_redaction` proof: it creates a temporary raw `K8sAuditEvent` payload with token/password/bearer/connection-string/credentialed-URL markers, verifies `serialize_audit_event` and `serialize_cluster_event` redact or sanitize them, then removes the temporary audit event and cluster rows.
- Release scope and readiness now expose a structured production gate: production sidebar enablement requires `KUBERNETES_OPS_RELEASE_ENVIRONMENT=production`, `KUBERNETES_OPS_PRODUCTION_APPROVAL_REF`, core evidence refs (`KUBERNETES_OPS_PRODUCTION_EVIDENCE_REF`, identity runtime, live provider, read-only RBAC, Kubernetes MCP, rollback drill and native verification refs), and no local markers. Public readiness output redacts local URL marker values as `[local-url]` while release evidence/handoff still records operator-facing local marker counts.
- Pod exec now has a fail-closed WebSocket bridge foundation at `ws/kubernetes/admin/exec/{session_id}/`: by default it returns `native_exec_disabled`; when `KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=true`, it still requires an active approved break-glass session, `exec` verb, namespace/kind scope, reason, protected namespace denylist and command allow/deny policy. Real provider streaming requires both `KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED=true` and `KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED=true` before provider/action side effects; in production release mode it additionally requires `KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF` before action/provider side effects. With those gates plus `provider_stream=1`, it opens the provider exec stream, sends only redacted stdout/stderr frames to the browser, stores counters/status/exit code in `K8sAdminAction`/`K8sAdminRecording`, and persists bounded redacted `stdin`/`stdout`/`stderr` transcript events in `K8sAdminRecordingEvent`.
- Port-forward now has a fail-closed WebSocket bridge plus opt-in provider tunnel at `ws/kubernetes/admin/port-forward/{session_id}/`: by default it returns `native_port_forward_disabled`; when `KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=true`, it requires an active approved break-glass session, `port_forward` verb, namespace/kind scope, protected namespace denylist, request reason, explicit target allowlist, and bounded duration. Real provider tunnel requires both `KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED=true` and `KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED=true` before provider/action side effects; in production release mode it additionally requires `KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF`, `KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF`, exact non-wildcard target allowlist, default protected namespace coverage, and max duration <=900s before action/provider side effects. With those gates plus `provider_stream=1`, it opens the provider tunnel, closes the provider handle before the final stopped/error event on EOF/cancel/error, and stores byte/duration/status metadata in `K8sAdminAction` plus a linked `K8sAdminRecording` row, not tunnel payload.
- Break-glass cluster terminal now has fail-closed start/stop APIs plus an opt-in WebSocket provider-stream foundation at `ws/kubernetes/admin/terminal/{session_id}/`. REST start validates approved break-glass session evidence, restricted-context safety, reason and centralized recording policy with retention settings, records metadata while terminal transport is disabled, then returns `execution_blocked`. The WebSocket provider stream only opens when `KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED=true`, `KUBERNETES_ADMIN_CLUSTER_TERMINAL_RECORDING_ENABLED=true`, `provider_stream=1`, an active approved break-glass session, Rancher provider `cluster_terminal_path_template`, and production restricted evidence when required are all present; it records bounded redacted `stdin`/`stdout`/`stderr` events in `K8sAdminRecordingEvent` and closes on provider EOF, disconnect, error or session expiry.
- Node debug now has fail-closed start/stop APIs plus an opt-in WebSocket provider-stream foundation at `ws/kubernetes/admin/node-debug/{session_id}/`. REST start validates approved break-glass session evidence, `node` scope, node name, reason and centralized recording policy with retention settings, records metadata while debug transport is disabled, then returns `execution_blocked`. The WebSocket provider stream only opens when `KUBERNETES_ADMIN_NODE_DEBUG_ENABLED=true`, `KUBERNETES_ADMIN_NODE_DEBUG_RECORDING_ENABLED=true`, `provider_stream=1`, an active approved break-glass session, Rancher provider `node_debug_path_template`, and production restricted evidence when required are all present; it records bounded redacted `stdin`/`stdout`/`stderr` events in `K8sAdminRecordingEvent` and closes on provider EOF, disconnect, error or session expiry.
- Rough Admin Mode frontend now exists at `/kubernetes/admin`: it is WebTerm-native, feature-gated by `kubernetes_admin_read`, creates read sessions, selects cluster/kind/namespace/name, runs Discovery/CRDs/List/YAML, and shows owner/path/policy context before the raw JSON/YAML result.
- `kubernetes_ops.services.terminal_safety` has a fail-closed threat model: it exposes native exec, port-forward, cluster-terminal and node-debug runtime flags but deliberately marks readiness missing if policy enables `can_exec` or `can_port_forward` before production controls are complete; terminal safety also embeds `admin_interactive_transport` prerequisites. Production provider-native exec/port-forward transport now fails before action/provider side effects unless `KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF` is set; production port-forward additionally requires `KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF` and exact non-wildcard targets; cluster-terminal/node-debug transport flags additionally require explicit Rancher provider path template contracts before action/audit/provider side effects. Tests still assert no legacy native pod exec/attach/debug REST route exists.
- The current runbook `docs/architecture/KUBERNETES_OPS_OPERATIONS.md` says normal users work inside WebTerm only, while Rancher/Fleet/Devtron remain source-of-truth backend platforms and fallback UIs.
- Local WebTerm runs from `docker-compose.yml`; local Rancher/Fleet/Devtron run adjacent to compose inside `kind-webterm-k8s`, not as ordinary compose services.

Important implication: this plan must add a new guarded Admin Mode instead of silently weakening the existing read-only Kubernetes Ops mode.

### 2.1 Backend Completion Snapshot

As of 2026-07-02, the backend implementation is roughly 85-90% complete for the planned Freelens++ scope if frontend polish is excluded. This estimate is based on the current release evidence, not on UI appearance: local/pre-production backend proof is broad, provider credential storage/rotation is now machine-verified, but production release proof is still intentionally blocked by `release_scope=local`.

What is already backend-usable:

- safe WebTerm-native Kubernetes cockpit: overview, clusters, namespaces, workloads, pods, services/ingresses, events, diagnostics, Helm ownership, Fleet bundles and Devtron app context;
- low-level Admin read mode: sessions, discovery, generic resource list/detail/YAML, CRDs, resource events, node inventory, metrics, logs/watch snapshots and ownership context;
- guarded write/admin paths: schema validation, dry-run apply, apply, patch, scale, restart, delete, cordon/uncordon/drain, exec, port-forward, cluster terminal and node debug, all default-disabled or approval/runtime gated;
- action workflow: request, approval, external verification, opt-in native execution for selected safe classes, rollback plans, native verification plans, action summary/report/timeline and metadata-only audit;
- safety/release layer: normal-user WebTerm-only proof, provider secret redaction, secret-value reveal gates, Admin Mode safety proof, release preflight, production evidence checklist, operator command plan and handoff artifacts.
- production hardening proofs for provider credentials and audit/log redaction: managed provider token storage, rotation, encrypted-at-rest ciphertext checks, no plaintext serialization, fail-safe audit payload redaction, credentialed URL sanitization and rollback cleanup of temporary proof rows.

Backend work still required before calling this production-ready:

- run the same release evidence against non-local production-like Rancher/Fleet/Devtron and Kubernetes MCP endpoints;
- provide reviewed production refs for approval, identity runtime, live provider smoke, read-only RBAC, Kubernetes MCP, rollback drill, native verification and interactive transport gates;
- rerun `verify_kubernetes_ops_external_evidence_bundle`, `verify_kubernetes_ops_release`, preflight and handoff with `KUBERNETES_OPS_RELEASE_ENVIRONMENT=production`;
- only after `production_ready=true`, set `KUBERNETES_OPS_READY_FOR_SIDEBAR=true`;
- keep direct cluster writes, exec, port-forward, terminal and node debug disabled in production unless the matching restricted credential, recording, network-policy and live-smoke evidence is fresh.

So the backend is usable for local/dev testing and UI integration now, but it is not yet a production Freelens replacement until the production evidence gates above are satisfied.

Latest action-request safety evidence:

```text
python -m py_compile kubernetes_ops/services/action_requests.py kubernetes_ops/action_views.py tests/test_kubernetes_ops_action_lifecycle.py tests/test_kubernetes_ops_action_requests.py
docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_action_lifecycle.py tests/test_kubernetes_ops_action_requests.py -q --reuse-db
25 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_action_lifecycle.py tests/test_kubernetes_ops_action_requests.py tests/test_kubernetes_ops_release_evidence.py tests/test_kubernetes_ops_release_evidence_summary.py -q --reuse-db
39 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_action_lifecycle.py tests/test_kubernetes_ops_action_request_workload_actions.py tests/test_kubernetes_ops_action_native_execution.py tests/test_kubernetes_ops_action_requests.py tests/test_kubernetes_ops_release_evidence.py tests/test_kubernetes_ops_release_evidence_summary.py -q --reuse-db
46 passed

docker compose exec -T backend python scripts/check_architecture_sizes.py --strict-new
SUCCESS: All architecture contracts satisfied.

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_action_request_apply.py tests/test_kubernetes_ops_action_request_delete.py tests/test_kubernetes_ops_action_native_execution.py tests/test_kubernetes_ops_action_request_workload_actions.py tests/test_kubernetes_ops_action_requests.py tests/test_kubernetes_ops_release_evidence.py tests/test_kubernetes_ops_release_handoff.py tests/test_kubernetes_ops_permission_matrix.py tests/test_kubernetes_ops_admin_port_forward.py tests/test_kubernetes_ops_admin_port_forward_tunnel_websocket.py -q --reuse-db
70 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_action_requests.py tests/test_kubernetes_ops_action_request_workload_actions.py tests/test_kubernetes_ops_action_request_apply.py tests/test_kubernetes_ops_action_request_delete.py tests/test_kubernetes_ops_action_native_execution.py tests/test_kubernetes_ops_admin_production_approval.py tests/test_kubernetes_ops_release_evidence.py tests/test_kubernetes_ops_release_admin_mode_safety.py tests/test_kubernetes_ops_release_handoff.py tests/test_kubernetes_ops_release_evidence_summary.py tests/test_kubernetes_ops_permission_matrix.py -q --reuse-db
73 passed
```

## 3. Target Capabilities

### 3.1 Freelens-like capabilities to support

P0 usable admin surface:

- browse all common resources by cluster, namespace, kind, label, owner, and health;
- browse CRDs and custom resources;
- fetch full live YAML/JSON for any allowed resource;
- search/filter resources;
- view events and describe-style evidence;
- stream pod logs with follow/tail/container selection;
- view resource diff before applying changes; [backend done: dry-run apply returns sanitized top-level summary plus bounded path-level `diff.changes`, while action/audit store only diff counts/metadata]
- edit/apply YAML with server-side dry-run first;
- scale workload;
- rollout restart deployment/statefulset/daemonset;
- delete resource with strong guardrails;
- open shell exec into pod/container;
- port-forward to pod/service for short-lived debugging sessions;
- surface Rancher/Fleet/Devtron source-of-truth context inside WebTerm, with external UI links only as staff/admin fallback.

P1 advanced admin surface:

- generic API discovery for arbitrary Kubernetes kinds;
- CRD schema-aware YAML validation when schema is available; [backend done: `POST /api/kubernetes/admin/clusters/{cluster_id}/resources/schema-validate/`]
- namespace-scoped terminal with `kubectl`/`helm` disabled by default but available in break-glass mode;
- node view; [backend done: `GET /api/kubernetes/admin/clusters/{cluster_id}/nodes/?session_id=...`]
- node cordon/uncordon and drain request only as break-glass; [backend foundation done: `POST /api/kubernetes/admin/clusters/{cluster_id}/nodes/cordon|uncordon|drain/`; drain execution done behind separate `KUBERNETES_ADMIN_NODE_DRAIN_EXECUTION_ENABLED=true` guard using Kubernetes Eviction API]
- node debug only as break-glass;
- Helm release view via Fleet/Rancher/Devtron ownership data; [backend done: `GET /api/kubernetes/helm/releases/` returns read-only release owner/conflict/change-path policy from normalized Rancher/Fleet/Devtron inventory]
- GitOps MR creation for planned changes instead of direct apply; [backend done: action request returns a sanitized GitLab draft merge-request payload/template without Git writes or cluster mutations]
- production rollout restart template with approval, verification and report gates. [backend done: restart action request preview includes `production_rollout_restart_template`, release `action_controls` proves `restart_template=ready`]

Out of scope for first working version:

- beautiful UI;
- replacing Rancher cluster lifecycle management;
- replacing Devtron CI/CD and app deployment history;
- replacing Fleet as GitOps controller;
- giving raw kubeconfig/token to browser JavaScript.
- making Rancher/Fleet/Devtron UI part of the normal user workflow.

### 3.2 Full function map for the improved Freelens target

The target is not a one-to-one clone of Freelens. The target is "Freelens++ inside WebTerm": the same low-level cluster visibility and admin workflows, plus Rancher/Fleet/Devtron context, plus WebTerm safety controls.

| Source | Functions to absorb into WebTerm | WebTerm improvement |
|---|---|---|
| Freelens | multi-cluster resource explorer, namespaces, workloads, pods, services, ingress, config maps, secrets metadata, CRDs, custom resources, YAML/JSON view, logs, exec, port-forward, events, describe-style evidence, search/filter | no browser kubeconfig, explicit per-user features, short-lived sessions, audit, approvals, owner-aware write policy |
| Rancher | cluster/project/namespace context, node and workload health, Kubernetes API proxy, RBAC/source-of-truth, Fleet ownership, provider links, cluster lifecycle fallback | WebTerm renders daily read/action UX natively; Rancher UI stays staff/admin fallback, not normal workflow |
| Fleet | GitRepo, Bundle, BundleDeployment, HelmOp, rollout partitions, paused/rolling/failed state, target clusters, GitOps source context, pause/resume/change request flow | planned production changes prefer GitOps MR or Fleet workflow instead of direct cluster mutation |
| Devtron | app catalog, environments, Helm app ownership, deployment history, values context, rollback context, logs/debug context, CI/CD evidence | app teams use WebTerm-native AppOps summary and diagnosis first; Devtron UI stays fallback for staff/admin or unsupported flows |
| WebTerm | feature gates, Studio diagnosis, terminal/WebSocket patterns, managed secrets, audit trail, release evidence, approvals, runbooks | single portal, one permission model, one evidence/report trail, safe defaults |

Backend-first target surface:

- inventory: clusters, nodes, namespaces, workloads, pods, services, ingress, network, events, CRDs, custom resources;
- ownership: every resource should explain whether it is WebTerm, Fleet, Devtron, Rancher/platform, external, or unknown owned;
- evidence: describe, events, health, deployment history, logs snapshot/follow, watch preview/follow;
- write preview: server-side dry-run, diff, ownership warnings, production policy, approval requirement;
- controlled writes: apply, patch, scale, restart, delete, Fleet pause/resume/MR, Devtron rollback request;
- break-glass: exec, port-forward, restricted cluster terminal, node debug, node cordon/drain only after TTL/audit/review;
- reporting: every dangerous action produces action report, audit metadata and verification evidence.

Frontend can stay rough until these backend contracts and tests are stable. UI polish starts after the workflows are correct.

## 4. Product Modes

Use three explicit modes. Do not overload the existing `kubernetes` feature flag.

| Mode | Purpose | Allowed actions | Target users |
|---|---|---|---|
| `kubernetes` | Current safe cockpit | Read inventory, snapshots, audit, diagnosis, action requests | Operators, DevOps, developers |
| `kubernetes_admin_read` | Low-level read-only explorer | Live resource list/get/watch/log read, full YAML read, CRD browsing | SRE, platform engineers |
| `kubernetes_admin_write` | Controlled low-level mutation | dry-run/apply, scale, restart, delete, log follow, short pod exec | SRE/platform admins |
| `kubernetes_break_glass` | Emergency cluster-admin session | restricted temporary cluster terminal, node debug, broad verbs | senior on-call only |

Every mode must be visible in readiness/access policy so frontend can hide or show controls without guessing.

## 5. Recommended Architecture

### 5.1 Backend components

Add these focused modules under `kubernetes_ops/`:

```text
kubernetes_ops/
  admin_access.py              # policy matrix and mode checks
  admin_models.py              # optional split if models.py grows
  admin_resource_views.py      # HTTP APIs for discovery/list/get/yaml/diff/apply
  admin_session_views.py       # create/approve/revoke/close/expire admin sessions
  admin_stream_consumers.py    # logs/exec/port-forward WebSocket consumers
  services/
    admin_audit.py
    admin_policy.py
    admin_sessions.py
    admin_rancher_proxy.py
    admin_kubernetes_client.py
    admin_resource_discovery.py
    admin_resource_normalizers.py
    admin_yaml.py
    admin_dry_run.py
    admin_exec.py
    admin_port_forward.py
    admin_watch.py
```

Keep files under the architecture size limit. Split early rather than extending existing large modules.

### 5.2 Provider execution paths

Primary path:

- Use Rancher as the cluster access broker where possible.
- Store Rancher provider tokens only as managed/external secrets.
- Backend calls Rancher/Kubernetes API; browser never receives kubeconfig/token.
- Map WebTerm user permissions to allowed cluster/namespace/kind/verb.
- User-facing resource browsing, YAML, logs, actions, and diagnosis are rendered in WebTerm; Rancher UI links are fallback only.

Secondary path:

- Allow direct Kubernetes API provider only after Rancher path is stable.
- A direct provider should still use a backend-held service account/token with namespace/verb limits.

Devtron path:

- Use Devtron for app-centric context: app details, deployment history, rollback evidence, app logs/debug metadata, Helm values when Devtron is the owner.
- Do not let WebTerm edit a Devtron-owned Helm release behind Devtron's back unless it is a GitOps/MR path.
- Show Devtron context natively in WebTerm first; Devtron UI links are fallback only.

Fleet path:

- Use Fleet/Rancher for GitOps/HelmOps state, bundle status, pause/resume requests, and GitOps MR generation.
- Prefer MR/change request for planned production changes.
- Show Fleet bundle/rollout context natively in WebTerm first; Fleet/Rancher UI links are fallback only.

### 5.3 Transport choices

HTTP APIs:

- discovery;
- resource list/get;
- namespace detail context;
- workload detail context;
- pod detail context;
- service/ingress detail context;
- YAML fetch;
- dry-run apply;
- diff preview;
- create/approve/revoke/close/expire admin sessions;
- action reports.

WebSocket APIs:

- log streaming;
- resource watch;
- pod exec;
- port-forward control channel;
- optional cluster terminal.

Reuse existing Channels/WebSocket patterns from server terminals. Add `kubernetes_ops.routing` and include it from `web_ui.routing`.

### 5.4 Runtime and deployment topology

Local test topology:

```text
------------------------------ Windows / Docker Desktop ------------------------------+
|                                                                                     |
|  docker compose: WebTerm                                                            |
|  backend, frontend, nginx, postgres, redis, workers, kubernetes-ops-sync             |
|                                                                                     |
|  kind-webterm-k8s: Kubernetes test cluster running on Docker container nodes         |
|  Rancher installed by Helm in cattle-system                                         |
|  Fleet enabled through Rancher                                                       |
|  Devtron installed by its operator/chart in devtroncd                                |
|  demo namespaces/apps installed in the same cluster                                  |
|                                                                                     |
|  WebTerm backend -> provider URLs/port-forwards -> Rancher/Fleet/Devtron APIs        |
|  Browser -> WebTerm only                                                            |
|                                                                                     |
+-------------------------------------------------------------------------------------+
```

Important local rules:

- Rancher, Fleet and Devtron are not ordinary WebTerm `docker-compose.yml` services. They run next to WebTerm inside the local kind Kubernetes cluster, which itself runs on Docker.
- Fleet is part of the Rancher/Fleet stack; there is no separate daily Fleet login.
- WebTerm connects to Rancher/Devtron through provider endpoints such as `host.docker.internal` or local port-forwarded service URLs.
- Provider credentials stay in WebTerm ManagedSecret/external refs. They must never be printed into docs, browser responses, frontend state or audit bodies.
- The user opens `http://127.0.0.1:8080/kubernetes` or `/kubernetes/admin` and works in WebTerm. Direct Rancher/Devtron URLs are fallback for staff/admin while building or debugging the platform.
- Local platform readiness is now machine-verifiable with `python scripts/verify_kubernetes_ops_local_platform.py --output artifacts/kubernetes_ops_local_platform_evidence.json`. Run it from the host or another environment that has `kubectl` access to `kind-webterm-k8s`; Docker backend preflight reads the artifact and does not require `kubectl` inside the backend container. The artifact checks context `kind-webterm-k8s`, Rancher namespace/service/deployments, Fleet namespace/services/deployments, and Devtron namespace/services/deployments/statefulset without storing credentials.
- Live provider smoke readiness is now machine-verifiable with `python manage.py verify_kubernetes_ops_live_provider_smoke --output artifacts/kubernetes_ops_live_provider_smoke.json`. This is a separate proof from the local platform check: it verifies enabled WebTerm Rancher/Devtron providers answer backend probes, read-only dry-run sync returns Rancher clusters/namespaces/workloads/pods, Fleet bundles and Devtron apps, and Admin backend paths can read a synced Rancher Pod YAML, bounded logs snapshot and read-only node drain preflight through WebTerm-held credentials without exposing provider tokens or starting cordon/eviction.

Production topology:

```text
User -> WebTerm UI/API -> WebTerm backend providers -> Rancher/Fleet/Devtron/Kubernetes
```

Production rules:

- WebTerm can run in Docker Compose or Kubernetes, but it remains a separate application from Rancher/Fleet/Devtron.
- Rancher is the preferred cluster API broker and RBAC/source-of-truth.
- Fleet remains the GitOps/HelmOps owner for platform charts and rollout state.
- Devtron remains the AppOps/CI/CD owner for application lifecycle and rollback history.
- User login is to WebTerm first. If WebTerm uses LDAP/OIDC/Keycloak, permissions map into WebTerm feature flags and provider roles; if WebTerm uses local accounts, provider access still uses backend service credentials, not copied user passwords.
- Normal workflow must not require opening Rancher, Fleet or Devtron UI. External UIs are staff/admin fallback, migration aid and break-glass evidence paths.

## 6. Data Model Additions

Add migrations for:

### 6.1 `K8sAdminSession`

Fields:

- `session_id UUID`;
- `user`;
- `username_snapshot`;
- `cluster`;
- `namespace`;
- `mode`: `read`, `write`, `break_glass`;
- `status`: `pending_approval`, `active`, `expired`, `revoked`, `closed`;
- `reason`;
- `approval_ref`;
- `approved_by`;
- `approved_at`;
- `expires_at`;
- `allowed_verbs`;
- `allowed_kinds`;
- `allowed_namespaces`;
- `provider`;
- `risk_tier`;
- `created_at`, `updated_at`, `closed_at`.

Rules:

- read sessions can be auto-created for users with `kubernetes_admin_read`;
- write sessions require reason and either staff permission or approval;
- break-glass sessions always require TTL, reason, and post-review marker.

### 6.2 `K8sAdminAction`

Fields:

- `action_id UUID`;
- `session`;
- `user`;
- `cluster`;
- `namespace`;
- `resource_api_version`;
- `resource_kind`;
- `resource_name`;
- `verb`: `get`, `list`, `watch`, `logs`, `exec`, `port_forward`, `dry_run_apply`, `apply`, `patch`, `scale`, `restart`, `delete`;
- `request_payload_sanitized`;
- `response_summary`;
- `diff_summary`;
- `exit_code`;
- `status`: `started`, `succeeded`, `failed`, `blocked`, `expired`;
- `started_at`, `finished_at`.

Rules:

- never store raw secret values or full log content by default;
- store command metadata by default; store only bounded redacted exec transcript events after the recording gate passes, never raw command payload or secrets;
- store YAML diff summary and object metadata, not raw Secret data.

### 6.3 `K8sAdminRecording`

Fields:

- `recording_id UUID`;
- `session`;
- `action`;
- `user`;
- `cluster`;
- `namespace`, `resource_kind`, `resource_name`;
- `operation`: `exec`, `port_forward`, `cluster_terminal`, `node_debug`;
- `status`: `active`, `blocked`, `completed`, `failed`;
- `mode`: `metadata_only` or `transcript_required`;
- `transcript_required`, `transcript_stored`, `payload_stored`;
- `stdin_recording_required`, `stdout_recording_required`;
- `metadata_retention_days`, `transcript_retention_days`;
- `metadata_delete_after`, `transcript_delete_after`;
- `policy_snapshot`;
- `summary`;
- `started_at`, `finished_at`.

Rules:

- this table is durable recording evidence, not the raw recording store;
- never store stdin/stdout/tunnel payload in `summary`;
- link every provider-native exec/port-forward transport attempt to a recording row before opening provider transport;
- link fail-closed cluster-terminal/node-debug start attempts to a blocked recording row;
- expose recording evidence through action reports only after sanitizer.

### 6.4 `K8sAdminRecordingEvent`

Fields:

- `recording`;
- `sequence`;
- `stream`: `stdin`, `stdout`, `stderr`, `status`;
- `data`: redacted, bounded text only;
- `original_length`, `stored_length`;
- `redacted`, `truncated`;
- `metadata`;
- `created_at`.

Rules:

- only create events after `KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED=true` and the provider transport is allowed;
- apply server-side redaction before storing and again before action report output;
- cap per-event length and per-recording event count through `KUBERNETES_ADMIN_TRANSCRIPT_EVENT_MAX_CHARS` and `KUBERNETES_ADMIN_TRANSCRIPT_EVENT_MAX_COUNT`;
- store exec evidence for review, not raw terminal/tunnel payload; port-forward payload remains metadata-only.

### 6.5 `K8sResourceCache` optional

Use only if live list performance is too slow:

- cluster, namespace, group, version, kind, name, uid;
- labels/annotations sanitized;
- owner refs;
- health/status summary;
- last_seen_at.

Do not block first implementation on this cache; live list through Rancher/Kubernetes API is enough for rough UI.

## 7. Permissions And Policy

Extend `kubernetes_ops.permissions` with:

```text
kubernetes_admin_read
kubernetes_admin_write
kubernetes_break_glass
```

Expose policy fields:

```json
{
  "can_admin_read": true,
  "can_live_resource_get": true,
  "can_live_resource_watch": true,
  "can_view_full_yaml": true,
  "can_stream_logs": true,
  "can_admin_write": false,
  "can_dry_run_apply": false,
  "can_apply_yaml": false,
  "can_scale": false,
  "can_patch": false,
  "can_delete": false,
  "can_exec": false,
  "can_port_forward": false,
  "can_break_glass": false
}
```

Policy rules:

- `kubernetes` alone never unlocks low-level controls.
- `kubernetes_admin_read` unlocks full live read/YAML/log stream, but not write/exec/port-forward.
- `kubernetes_admin_write` unlocks server-side `dry-run-apply` inside an active approved write session. Native `apply`, `patch`, `scale`, `restart`, and `delete` additionally require their `KUBERNETES_ADMIN_NATIVE_*_ENABLED=true` flags, matching verbs in the active session, request reason, and metadata-only audit/action records. Future pod exec must stay behind the same session, approval, audit, and verification lifecycle.
- `kubernetes_break_glass` unlocks emergency-only capabilities inside an active approved break-glass session. Apply dry-run bypass is not part of normal break-glass by default; it additionally requires `KUBERNETES_ADMIN_BREAK_GLASS_APPLY_BYPASS_ENABLED=true`, `KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED=true`, `apply` in session verbs, scope checks, reason and audit evidence. Node cordon/uncordon/drain are also break-glass-only: `KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED=true`, `node` scope, matching verb, approval and reason are required; drain execution additionally requires `KUBERNETES_ADMIN_NODE_DRAIN_EXECUTION_ENABLED=true`, exact `drain Node {node}` confirmation, safe preflight over pods on that node, and Kubernetes `policy/v1` Eviction API so PDBs are not bypassed.
- Secrets are special: list metadata is allowed, value/body is redacted by default, and Secret list responses report `secret_values.mode=list_metadata_only` with `visible=false` even when values are requested. Viewing a named Secret body requires separate `kubernetes_secret_read`, `KUBERNETES_ADMIN_SECRET_READ_ENABLED=true`, explicit `include_secret_values=1`, an active Admin read session, and metadata-only audit/action evidence. [done for list/get/YAML/detail backend paths]
- Production namespace write actions should require reason and approval unless explicitly configured as non-prod.

## 8. API Plan

### 8.1 Read-only admin explorer

```text
GET /api/kubernetes/admin/discovery/
GET /api/kubernetes/admin/clusters/{cluster_id}/resources/
GET /api/kubernetes/admin/clusters/{cluster_id}/resources/{api_version}/{kind}/
GET /api/kubernetes/admin/clusters/{cluster_id}/resources/{api_version}/{kind}/{namespace}/{name}/
GET /api/kubernetes/admin/clusters/{cluster_id}/resources/{api_version}/{kind}/{namespace}/{name}/yaml/
GET /api/kubernetes/admin/clusters/{cluster_id}/resources/{api_version}/{kind}/{namespace}/{name}/events/
GET /api/kubernetes/admin/clusters/{cluster_id}/resources/detail/?api_version=...&kind=...&namespace=...&name=...
GET /api/kubernetes/admin/clusters/{cluster_id}/resources/describe/?api_version=...&kind=...&namespace=...&name=...&include_events=1&include_related=1
GET /api/kubernetes/admin/clusters/{cluster_id}/resources/events/?api_version=...&kind=...&namespace=...&name=...
GET /api/kubernetes/admin/clusters/{cluster_id}/crds/
GET /api/kubernetes/admin/clusters/{cluster_id}/nodes/?session_id=...&limit=...
GET /api/kubernetes/admin/clusters/{cluster_id}/metrics/?session_id=...&scope=nodes|pods&namespace=...&name=...
GET /api/kubernetes/diagnostics/summary/?scope=cluster|namespace|workload|pod|network&cluster_id=...&namespace_id=...&workload_id=...&pod_id=...&network_id=...
POST /api/kubernetes/admin/clusters/{cluster_id}/nodes/cordon/
POST /api/kubernetes/admin/clusters/{cluster_id}/nodes/uncordon/
POST /api/kubernetes/admin/clusters/{cluster_id}/nodes/drain/
GET /api/kubernetes/admin/actions/
GET /api/kubernetes/admin/actions/{action_id}/
GET /api/kubernetes/admin/actions/{action_id}/report/
POST /api/kubernetes/admin/actions/{action_id}/review/
GET /api/kubernetes/admin/recordings/
GET /api/kubernetes/admin/recordings/{recording_id}/
```

Query options:

- `namespace`; [done]
- `label_selector`; [done: forwarded as Kubernetes `labelSelector` for resource list]
- `field_selector`; [done: forwarded as Kubernetes `fieldSelector` for resource list]
- `search`; [done: local search over sanitized list rows after Kubernetes selector/pagination response]
- `limit`; [done: bounded, forwarded only when explicitly requested]
- `continue`; [done: forwarded as Kubernetes pagination token and response exposes bounded `continue_token`]
- `include_managed_fields=false`; [done: default redacts `managedFields`; explicit true keeps sanitized managedFields]
- Admin action list also supports `post_review_status=pending|completed|not_ready|required|any|none` and bounded `review_scan_limit` so operators can find dangerous actions that still need review.

Acceptance:

- returns live data or clear provider error;
- handles common resources and CRDs;
- redacts Secret bodies;
- resource detail endpoint combines sanitized live resource, describe-style identity/health/shape summary, ownership context and bounded Events; it stores only metadata counts/flags in action/audit summaries; [done]
- resource live describe endpoint combines sanitized identity/spec/status summary, bounded Events and related Pods/ReplicaSets through backend-held Rancher credentials; it skips related sections if the active session lacks the read scope and stores only metadata counts/flags/skipped reasons in action/audit summaries; [done]
- resource events endpoint queries Kubernetes/Rancher Events with a resource field selector, redacts event messages/source metadata, and stores only metadata counts in action/audit summaries; [done]
- list filtering/pagination uses Kubernetes `labelSelector`, `fieldSelector`, bounded `limit`, `continue` token, local safe `search` over sanitized rows, and optional sanitized `managedFields`; [done]
- records audit metadata for full YAML reads and sensitive resources;
- exposes sanitized `K8sAdminAction` evidence to owner/staff without raw provider payloads;
- exposes `review_summary` and `post_review_status` filters for action evidence queues;
- lets staff with the matching explicit grant complete dangerous action post-review without storing raw secrets in review text or audit payloads.

### 8.2 Controlled write APIs

```text
POST /api/kubernetes/admin/sessions/
POST /api/kubernetes/admin/sessions/{session_id}/approve/
POST /api/kubernetes/admin/sessions/{session_id}/revoke/
POST /api/kubernetes/admin/sessions/{session_id}/close/
POST /api/kubernetes/admin/sessions/{session_id}/review/
POST /api/kubernetes/admin/sessions/{session_id}/restricted-context/
POST /api/kubernetes/admin/sessions/{session_id}/terminal/start/
POST /api/kubernetes/admin/sessions/{session_id}/terminal/stop/
POST /api/kubernetes/admin/sessions/{session_id}/node-debug/start/
POST /api/kubernetes/admin/sessions/{session_id}/node-debug/stop/
POST /api/kubernetes/admin/clusters/{cluster_id}/resources/schema-validate/
POST /api/kubernetes/admin/clusters/{cluster_id}/resources/dry-run-apply/
POST /api/kubernetes/admin/clusters/{cluster_id}/resources/apply/
POST /api/kubernetes/admin/clusters/{cluster_id}/resources/patch/
POST /api/kubernetes/admin/clusters/{cluster_id}/resources/scale/
POST /api/kubernetes/admin/clusters/{cluster_id}/resources/restart/
POST /api/kubernetes/admin/clusters/{cluster_id}/resources/delete/
```

Mutation lifecycle:

```text
request -> policy check -> session check -> dry-run -> diff -> approval/reason -> execute -> verify -> report -> audit
```

Acceptance:

- `dry-run-apply` works before `apply`; [done for server-side dry-run preview]
- `schema-validate` checks CRD `openAPIV3Schema` when available, reports bounded validation errors and never returns/stores raw manifest body; [done]
- `apply` is rejected without active session; [done for runtime-gated apply endpoint]
- `apply` is rejected without fresh matching dry-run proof; [done]
- `scale` and `restart` are rejected unless explicitly runtime-enabled and covered by an active approved write session; [done]
- `delete` requires exact kind/name/namespace confirmation;
- production namespace actions require approval unless policy says otherwise;
- Secret dry-run/apply redacts body in response, audit and diff output; [done for dry-run and runtime-gated apply]
- all failures return actionable error codes.

### 8.3 Streaming APIs

```text
ws/kubernetes/admin/logs/{session_id}/
ws/kubernetes/admin/watch/{session_id}/
ws/kubernetes/admin/exec/{session_id}/
ws/kubernetes/admin/port-forward/{session_id}/
ws/kubernetes/admin/terminal/{session_id}/
```

Log streaming:

- namespace, pod, container, tail, follow;
- read-only admin mode is enough;
- redact obvious tokens in server-side output; keep raw log body out of audit/action records, and add saved stream evidence only behind an explicit retention policy;
- audit start/stop, target, line count, duration, truncation.

Pod exec:

- write or break-glass session required;
- no exec into privileged/system namespaces without break-glass;
- command allowlist for first version: `/bin/sh`, `/bin/bash`, `env`, `printenv`, `ls`, `cat`, `curl`, `wget`, custom command behind policy;
- record command metadata plus bounded redacted `stdin`/`stdout`/`stderr` events after the recording gate passes; never store raw command payload or secrets;
- TTL and idle timeout mandatory.

Port-forward:

- write or break-glass session required;
- target allowlist by namespace/service/pod;
- max duration and idle timeout;
- bind only to backend-managed tunnel endpoint, not arbitrary browser local port;
- audit target, ports, duration, bytes transferred summary.

Cluster terminal:

- break-glass only;
- disabled until resource explorer, logs, YAML, dry-run, and pod exec are stable.

## 9. Rancher/Fleet/Devtron Integration Details

### 9.1 Rancher

Use Rancher for:

- cluster list and metadata;
- Kubernetes API proxy/resource calls;
- workload/pod/service/ingress/event data;
- log streaming when Rancher endpoint supports it;
- namespace/project/RBAC labels;
- admin fallback links back to Rancher UI.

Provider labels should be extended with:

```json
{
  "k8s_api_proxy_template": "/k8s/clusters/{cluster_id}/{path}",
  "resource_list_template": "/k8s/clusters/{cluster_id}/apis/{group}/{version}/namespaces/{namespace}/{plural}",
  "core_resource_list_template": "/k8s/clusters/{cluster_id}/api/{version}/namespaces/{namespace}/{plural}",
  "log_stream_template": "...",
  "exec_template": "...",
  "port_forward_template": "..."
}
```

If Rancher API path differs in the installed version, hide that behind `admin_rancher_proxy.py` and provider labels. Do not hard-code UI URLs as API contracts.

### 9.2 Fleet

Use Fleet for:

- Fleet bundle read;
- bundle pause/resume request preview;
- rollout partition status;
- GitRepo target/source context;
- GitOps MR workflow for planned changes.

Current WebTerm-native backend slice:

- `GET /api/kubernetes/helm/releases/` returns a read-only Helm release ownership view across normalized Rancher workloads, Fleet bundles and Devtron apps, including owner conflict detection and safe `change_path` policy;
- `GET /api/kubernetes/fleet/bundles/` returns the normalized Fleet bundle list;
- `GET /api/kubernetes/fleet/bundles/{bundle_id}/` returns one sanitized read-only GitOps/Fleet detail payload from normalized inventory: bundle, partitions, related Fleet apps, matching workloads, related events, status/health summary and `mutates_state=false` policy;
- normal users get WebTerm-native data only, staff fallback links stay sanitized, and action/audit stores only bundle id/name/status plus related counts.

Do not use direct YAML apply for Fleet-owned releases by default. If a resource has Fleet ownership labels/annotations, show:

```text
This object is GitOps-owned. Prefer GitOps MR instead of direct apply.
```

Allow break-glass override only with explicit reason and audit.

### 9.3 Devtron

Use Devtron for:

- app ownership and app health;
- deployment history context;
- rollback context;
- app logs/debug context;
- Helm values visibility when Devtron owns the app.

Current WebTerm-native backend slice:

- `GET /api/kubernetes/devtron/apps/` returns the normalized Devtron app list;
- `GET /api/kubernetes/devtron/apps/{app_id}/` returns one sanitized read-only AppOps detail payload from normalized inventory: app, cluster, matching workloads, matching pods, related events, health/container/restart summary, and `delivery_context` for chart/release, deployment history, Helm values preview, rollback context and logs/debug links; values bodies are not returned raw, sensitive labels/values are redacted, and `mutates_state=false` policy routes changes to `devtron_rollback_or_deploy`;
- `GET /api/kubernetes/helm/releases/` marks Devtron-owned Helm releases as guarded and routes changes to `devtron_rollback_or_deploy` unless ownership conflicts require `resolve_owner_before_mutation`;
- normal users get WebTerm-native data only, while staff fallback links stay sanitized and audit stores only app id/name/namespace plus related counts.

If a resource is Devtron-owned, prefer Devtron rollback/deploy flows. WebTerm direct apply should be blocked or require break-glass unless the user chooses a GitOps/MR path.

## 10. Frontend Rough MVP

Create rough pages/components without waiting for final UI:

```text
/kubernetes/admin
/kubernetes/admin/clusters/:clusterId
/kubernetes/admin/clusters/:clusterId/resources
/kubernetes/admin/clusters/:clusterId/resources/:apiVersion/:kind/:namespace/:name
/kubernetes/admin/sessions
```

Minimum UI:

- cluster selector;
- namespace selector;
- kind selector;
- table of resources;
- YAML panel using existing CodeMirror YAML dependency;
- buttons: refresh, YAML, events, logs, dry-run, apply, scale, restart, delete, exec, port-forward;
- modal/panel for reason/session creation;
- plain WebSocket terminal/log pane using existing xterm components if possible;
- obvious policy badges: `read-only`, `write session active`, `break-glass`, `expires in`.

Do not spend time on final layout until backend flows pass.

## 11. Implementation Phases

### Phase 0: Plan and safety contract

Deliverables:

- this plan;
- architecture README links this plan;
- runbook gets a section saying Admin Mode is planned but disabled until gates pass.

Tests:

- docs-only verification with grep/file existence.

### Phase 1: Permission/session foundation

Status: implemented on 2026-07-01 as the first Admin Mode backend slice. This does not enable live Kubernetes mutations.

Deliverables:

- feature flags and policy fields; [done]
- `K8sAdminSession`, `K8sAdminAction`; [done]
- admin session create/list/detail/approve/revoke/close/expire foundation APIs; [done]
- readiness exposes admin mode gates separately from current safe cockpit. [done]

Tests:

- users with only `kubernetes` cannot open admin mode; [done]
- `kubernetes_admin_read` can create read session; [done]
- write/break-glass sessions require reason and TTL; [done for reason, bounded TTL, pending approval]
- expired/revoked sessions block actions; [done for Admin services and action-request native executors: `execute-approved` restart/scale/patch/delete/apply delegate to Admin write services, so inactive/expired/revoked write sessions fail before provider calls]
- audit is written for session lifecycle. [done]

Verification run:

```text
docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_sessions.py tests/test_kubernetes_ops_permission_matrix.py tests/test_kubernetes_ops_terminal_safety.py tests/test_kubernetes_ops_action_requests.py -q
26 passed

docker compose exec -T backend python manage.py check
System check identified no issues

docker compose exec -T backend python manage.py makemigrations --check --dry-run
No changes detected

docker compose exec -T backend python scripts/check_architecture_sizes.py --strict-new
SUCCESS: All architecture contracts satisfied.
```

### Phase 2: Live read-only resource explorer

Status: backend foundation and rough `/kubernetes/admin` frontend resource browser implemented on 2026-07-01. This is intentionally not final UI polish; it is the first working WebTerm-native Freelens-like read-only explorer slice.

Deliverables:

- Rancher-backed generic list/get for common resources; [done for backend API]
- discovery endpoint; [done for backend API]
- CRD list; [done for backend API]
- full YAML/JSON read with Secret redaction; [done for backend API; response now includes `manifest` contract with `resource_json_available`, client-side YAML render availability, top-level/metadata keys, Secret body redaction flags, no server-side YAML/raw provider body storage, and `apply_requires_dry_run=true`; explicit named Secret value reveal is fail-closed behind `kubernetes_secret_read` + runtime flag + `include_secret_values=1`]
- single-object detail endpoint with sanitized resource, describe summary, ownership and bounded Events. [done: `/api/kubernetes/admin/clusters/{cluster_id}/resources/detail/`]
- rough frontend resource browser. [done: `/kubernetes/admin` route, session card, cluster/kind/namespace/name controls, result table, JSON/YAML panel]
- Fleet/Devtron/Rancher ownership context for live resource list/get/YAML. [done: `admin_ownership.py`, `webterm_ownership`, `ownership`, `ownership_summary`, frontend owner column and policy panel]
- resource-specific Kubernetes Events through Admin Mode. [done: `/api/kubernetes/admin/clusters/{cluster_id}/resources/events/` with `api_version`, `kind`, `namespace`, `name`, bounded limit, redaction and metadata-only action/audit]
- dedicated Node inventory through Admin Mode. [done: `/api/kubernetes/admin/clusters/{cluster_id}/nodes/` with Ready/NotReady, roles, taints, unschedulable state, capacity/allocatable, addresses, nodeInfo, redaction and metadata-only action/audit]
- dedicated read-only node/pod metrics through Admin Mode. [done: `/api/kubernetes/admin/clusters/{cluster_id}/metrics/?scope=nodes|pods` with `metrics.k8s.io/v1beta1`, normalized CPU/memory totals, namespace scope guard for pod metrics, and metadata-only action/audit]
- break-glass node maintenance foundation. [done: `/api/kubernetes/admin/clusters/{cluster_id}/nodes/cordon/`, `/uncordon/`, `/drain/`; cordon/uncordon patch `spec.unschedulable` only when explicitly enabled, drain is disabled by default and, when separately enabled, cordons plus requests pod evictions through `policy/v1` Eviction API]
- backend resource list filters and pagination. [done: `/api/kubernetes/admin/clusters/{cluster_id}/resources/` supports `label_selector`, `field_selector`, safe local `search`, bounded `limit`, `continue`, and `include_managed_fields`; provider query uses Kubernetes selector names while action summaries store only presence/count metadata]
- grouped resource catalog for the UI picker. [done: Admin discovery `resource_catalog` entries include `ui_group`, `safe_read_actions`, `has_mutating_verbs`, top-level `counts` and group counters without raw provider bodies]
- WebTerm-native first screen; no dependency on opening Rancher/Fleet/Devtron UI. [done for read-only explorer]

Tests:

- list pods/deployments/services/ingresses/configmaps/secrets/crds; [backend common resource path builder done, deployment + CRD covered by tests]
- Secret data redacted; [done]
- missing provider returns controlled error; [done for provider request failures and missing Rancher provider]
- audit written for sensitive YAML reads; [done: `K8sAdminAction` + `K8sAuditEvent` metadata, no raw payload]
- resource events are session-gated, bounded, redacted and do not store event message bodies in action/audit summaries; [done]
- resource detail is session-gated, combines resource/describe/ownership/events, redacts sensitive strings in status/event messages, and stores only metadata counts/flags; [done]
- node view is session-gated, summarizes node health/capacity/taints, redacts sensitive condition/metadata values, and stores only node counters in action/audit summaries; [done]
- metrics view is session-gated, summarizes live node/pod CPU and memory usage through `metrics.k8s.io`, normalizes quantities, blocks all-namespace pod metrics unless the Admin session covers all namespaces, and stores only counts/totals in action/audit summaries; [done]
- node maintenance is disabled by default, requires approved break-glass session, node scope, matching verb, reason, and metadata-only audit; cordon/uncordon use PATCH only when enabled; drain requires exact confirmation and a second runtime flag, blocks unsafe pods before mutation, and uses Eviction API instead of raw delete. [done]
- list filters, search and pagination are session-gated, do not store raw selector/search/token values in action summaries, and keep `managedFields` redacted unless explicitly requested; [done]
- ownership context marks Devtron/Fleet-owned resources and redacts owner metadata; [done]
- frontend test renders resource table, ownership summary, owner badge, and YAML panel. [done]

Verification run:

```text
docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_nodes.py tests/test_kubernetes_ops_admin_resources.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db
32 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_node_maintenance.py tests/test_kubernetes_ops_admin_nodes.py tests/test_kubernetes_ops_admin_action_review_readiness.py tests/test_kubernetes_ops_release_admin_mode_safety.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db
36 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_node_maintenance.py -q --create-db
11 passed
New drain coverage proves disabled-by-default behavior, exact confirmation, approved break-glass/node scope enforcement, gated Eviction API execution, DaemonSet skip, terminal pod skip, truncated pod-list block, and emptyDir preflight block before cordon/eviction.

host-side python scripts/verify_kubernetes_ops_local_platform.py --output artifacts/kubernetes_ops_local_platform_evidence.json
status=ready, checked_at=2026-07-02T10:21:27Z, ready=3, missing=0, total=3 for Rancher/Fleet/Devtron in kind-webterm-k8s

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_local_platform_evidence.py tests/test_kubernetes_ops_release_preflight.py tests/test_kubernetes_ops_release_evidence.py tests/test_kubernetes_ops_release_handoff.py -q --create-db
19 passed

docker compose exec -T backend python manage.py verify_kubernetes_ops_live_provider_smoke --output artifacts/kubernetes_ops_live_provider_smoke.json --no-fail
status=ready, schema=kubernetes_ops.live_provider_smoke.v3, checked_at=2026-07-01T18:09:51Z, enabled_providers=2, provider_probes_ok=2/2, sync_dry_run_ok=2/2, clusters=1, namespaces=31, workloads=21, pods=35, fleet_bundles=1, apps=8, backend_paths_status=ready, backend_path_checks=4/4, live_describe=ready, drain_preflight=read_only_no_cordon_no_eviction

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_live_provider_smoke.py tests/test_kubernetes_ops_release_preflight.py -q --create-db
10 passed

docker compose exec -T backend python manage.py verify_kubernetes_ops_preflight --output artifacts/kubernetes_ops_preflight_evidence.json --no-fail
status=ready, failed=[], generated_at=2026-07-02T12:31:16Z, required command results=14, kubernetes_backend_tests=535 passed + 10 subtests passed, django_check=ready, architecture_guard=ready, migrations_dry_run=ready, readonly_rbac_validate=ready, sync_prune_safety=ready, readonly_rbac_live=ready, local_platform_evidence=ready, live_provider_smoke=ready with backend path smoke v3 and backend_path_checks=4/4, interactive_transport_evidence=ready, interactive_live_smoke=ready with four simulated provider opener checks and four production live transport contracts, interactive_production_controls=ready with four restricted credential/recording/network-policy/provider-contract controls, production_action_evidence=ready with rollback action classes=5, native verification checks=10, action class contracts=5 and blocked action classes=11, external_evidence_bundle=ready

docker compose exec -T backend python manage.py verify_kubernetes_ops_release --output artifacts/kubernetes_ops_release_evidence.json --no-fail
production_ready=false, ready_for_sidebar=false, generated_at=2026-07-02T12:31:39Z, blockers=[readiness:sidebar_release_scope=missing, release_scope:local], preflight=ready, artifact_safety=ready, definition_of_done=ready 13/13, completion_audit core_backend_complete=true / runtime_readiness_complete=true / production_evidence_complete=false / sidebar_enablement_complete=false, readiness=17 ready / 1 missing / 0 manual / 18 total; the remaining readiness check `sidebar_release_scope` is classified as production scope, not a runtime backend gap; identity_runtime now exposes `webterm_login_gateway` and proves WebTerm is the primary login gateway in local/LDAP/Domain SSO modes while Rancher/Fleet/Devtron remain backend-only provider integrations; production_gate is included in readiness evidence, marks target_environment=local, local_indicator_count=8 with public local URLs redacted as `[local-url]`, and lists core production evidence refs that become required only in production, now including rollback drill and native verification refs; provider probes/sync remain ready for local Rancher/Fleet/Devtron evidence; external_evidence_bundle=ready proves six required artifacts are present, including interactive_production_controls and production_action_evidence, and records local_indicator_count=18 without treating it as production approval; staff release readiness summary now exposes `production_evidence_checklist.gap_summary` with `next_gap_id=select_production_environment`, `production_blocking_gap_count=2` and `operator_command_plan.blocking_summary` so UI/operators can see that the current blocker is production scope/local evidence, not missing backend runtime work; Admin live YAML/JSON view now returns a safe `manifest` contract for JSON availability/client YAML rendering/redaction/copy-to-apply guardrails without storing server-side YAML or raw provider bodies; interactive_live_smoke=ready now proves four simulated provider opener checks plus production live transport contracts for exec, port-forward, cluster terminal and node debug without opening a live provider stream; interactive_production_controls=ready proves restricted credential, recording, port-forward network-policy and provider path-template contracts without opening a live provider stream; production_action_evidence now proves blocked action classes=11 for namespace/Helm delete aliases, unrestricted apply/YAML, node debug, port-forward, cluster-admin shell and RBAC edit aliases without provider writes or native mutations; normal_user_surface now records frontend_response_credential_scan.status=ready with surfaces_checked=31 including Helm release ownership, Devtron AppOps delivery, cluster/workload/network diagnostics summary payloads, action summary queue payloads, staff release readiness summary payloads including `production_evidence_checklist`/`operator_command_plan`, and capability matrix payloads, provider_secret_reference_serialized=false and forbidden_values_found=false; provider_secret_lifecycle=ready is now part of completion_audit core_backend_proofs and proves managed provider token storage, rotation, encrypted ciphertext plaintext absence, no plaintext serialization and rollback cleanup; audit_redaction=ready is also part of completion_audit core_backend_proofs and proves fail-safe audit payload redaction plus credentialed URL sanitization for audit/cluster-event serializers; action_controls now prove metadata-only rollback plans, production rollout restart template with approval/verification/report gates, native verification templates, auto-verification, restricted-write gate, Fleet pause/resume request-only previews, GitLab draft MR payload/template with no Git writes or cluster mutations, and Devtron rollback request-only preview with public-only links; Secret list metadata-only proof is ready, and Secret value access is not part of sidebar enablement and remains fail-closed behind `kubernetes_secret_read`, `KUBERNETES_ADMIN_SECRET_READ_ENABLED=true`, and `include_secret_values=1`

docker compose exec -T backend python manage.py render_kubernetes_ops_release_handoff --evidence artifacts/kubernetes_ops_release_evidence.json --output artifacts/kubernetes_ops_release_handoff.md --format markdown
status=blocked, can_enable_sidebar=false, generated_at=2026-07-02T12:31:54Z, blockers=[readiness:sidebar_release_scope=missing, release_scope:local], completion_audit shows core backend/runtime readiness complete but production evidence/sidebar gates incomplete, release_proofs include definition_of_done=ready 13/13, normal_user_surface=ready with credential_scan=ready/surfaces=31/secret_ref_serialized=false/forbidden_values=false, external_evidence_bundle=ready artifacts=6/6, production_action_evidence=ready with rollback_actions=5/native_checks=10/blocked_actions=11/blocked_contract=True, secret_read_controls=ready with list_metadata_only=True, provider_secret_lifecycle=ready with managed rotation proof, audit_redaction=ready with audit serializer redaction and credentialed URL sanitization proof, interactive_live_smoke=ready with simulated_checks=4/live_contracts=4, interactive_production_controls=ready with restricted credential/recording/network-policy/provider-contract controls, and action_controls=ready with apply/delete request proofs plus rollback-plan, restart_template=ready, native verification-plan, auto-verification proof, gitops=gitlab/git_write=false/cluster_mutation=false and restricted_write_gate=ready, production env flags now include KUBERNETES_OPS_PRODUCTION_ROLLBACK_EVIDENCE_REF and KUBERNETES_OPS_PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_REF, next_step=run release evidence in production with non-local Rancher/Devtron/MCP endpoints, approval ref and core evidence refs

python -m py_compile kubernetes_ops/services/admin_resource_registry.py kubernetes_ops/services/admin_resources.py tests/test_kubernetes_ops_admin_resource_registry.py
docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_resource_registry.py tests/test_kubernetes_ops_admin_resources.py -q --reuse-db
15 passed

docker compose exec -T backend sh -lc "python -m pytest tests/test_kubernetes_ops_admin_resource_*.py tests/test_kubernetes_ops_admin_resources.py -q --reuse-db"
27 passed

docker compose exec -T backend python manage.py verify_kubernetes_ops_preflight --output artifacts/kubernetes_ops_preflight_evidence.json
status=ready, failed=[], generated_at=2026-07-02T19:28:50+05:00, kubernetes_backend_tests=546 passed + 10 subtests passed

docker compose exec -T backend python manage.py verify_kubernetes_ops_release --username admin --output artifacts/kubernetes_ops_release_evidence.json
production_ready=false, ready_for_sidebar=false, generated_at=2026-07-02T19:57:54+05:00, blockers=[readiness:sidebar_release_scope=missing, release_scope:local], preflight=ready, root completion_audit present and matches release_summary.completion_audit, root production_execution_plan status=blocked / recommended_next=select_production_environment / phases=4 / commands=10

docker compose exec -T backend python manage.py render_kubernetes_ops_release_handoff --output artifacts/kubernetes_ops_release_handoff.json --format json
status=blocked, can_enable_sidebar=false, generated_at=2026-07-02T19:57:47+05:00, blockers=[readiness:sidebar_release_scope=missing, release_scope:local], completion_audit remaining=[production_evidence, sidebar_enablement], production_execution_plan status=blocked / recommended_next=select_production_environment / phases=4 / commands=10

docker compose exec -T backend python manage.py check
System check identified no issues (0 silenced).

docker compose exec -T backend python manage.py makemigrations --check --dry-run
No changes detected

docker compose exec -T backend python scripts/check_architecture_sizes.py --strict-new
SUCCESS: All architecture contracts satisfied.

npm test -- --run src/pages/KubernetesAdminPage.test.tsx
1 file / 3 tests passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_resources.py tests/test_kubernetes_ops_admin_sessions.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db
20 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_terminal_safety.py tests/test_kubernetes_ops_action_requests.py -q --create-db
12 passed

docker compose exec -T backend python scripts/check_architecture_sizes.py --strict-new
SUCCESS: All architecture contracts satisfied.

npm test -- --run src/pages/KubernetesAdminPage.test.tsx src/pages/KubernetesPage.test.tsx src/pages/KubernetesInventoryPages.test.tsx
3 files / 9 tests passed

npm run build
vite build passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_resources.py -q --create-db
7 passed

docker compose exec -T backend python manage.py check
System check identified no issues

docker compose exec -T backend python manage.py makemigrations --check --dry-run
No changes detected

docker compose exec -T backend python manage.py migrate
Applied core_ui.0017_add_kubernetes_admin_features and kubernetes_ops.0009_k8sadminsession_k8sadminaction on local Docker DB

docker compose restart frontend backend kubernetes-ops-sync nginx
frontend, backend, and nginx healthy after restart

Browser smoke on http://127.0.0.1:8080/kubernetes/admin
Admin read user created an active read session, ran List for apps/v1 Deployment in default namespace through local-rancher-real, received admin_read_only response with blocked apply/patch/scale/delete/exec/port_forward/node_debug policy, and the visible page did not expose kubeconfig, RANCHER_TOKEN, Bearer token, or JWT-looking token.

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_resource_detail.py tests/test_kubernetes_ops_admin_resource_events.py tests/test_kubernetes_ops_admin_resource_list_filters.py tests/test_kubernetes_ops_admin_resources.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db
37 passed
```

### Phase 3: Log streaming and watch

Status: started on 2026-07-01 with a safe Admin Mode pod logs snapshot, bounded resource watch preview, the first WebSocket stream contract, bounded follow/polling mode, opt-in provider-native continuous log follow, and opt-in provider-native continuous resource watch follow. Provider-native exec/port-forward now live in their own guarded phases.

Deliverables:

- bounded Admin Mode pod logs snapshot via Rancher provider JSON template; [done: `/api/kubernetes/admin/clusters/{cluster_id}/logs/`]
- session-gated logs read using active Admin Mode session and `logs` verb; [done]
- log line redaction, tail limit and no log content in audit/action summaries; [done]
- rough frontend `Logs` action for `Kind=Pod` + name on `/kubernetes/admin`; [done]
- bounded Admin Mode resource watch preview via Rancher/Kubernetes watch query; [done: `/api/kubernetes/admin/clusters/{cluster_id}/watch/`]
- session-gated watch read using active Admin Mode session and `watch` verb; [done]
- watch event redaction, event limit and no resource body in audit/action summaries; [done]
- rough frontend `Watch` action on `/kubernetes/admin`; [done]
- WebSocket routes for bounded Admin logs/watch stream batches; [done: `ws/kubernetes/admin/logs/{session_id}/`, `ws/kubernetes/admin/watch/{session_id}/`]
- stream start/stop/fail audit lifecycle with duration and count metadata; [done]
- frontend WebSocket URL helpers for Admin logs/watch streams; [done]
- bounded WebSocket follow/polling mode for Admin logs/watch with max batches; [done]
- stream heartbeat, idle-timeout, max-batch, cancel and client-disconnect close handling for follow/polling mode; [done]
- active admin-session status guard before every bounded follow batch, with normal stop close reasons `admin_session_expired` and `admin_session_not_active`; [done]
- bounded watch follow advances `resourceVersion` from each successful batch into the next provider watch request to avoid replaying the same event window; [done]
- provider client decodes bounded multi-event SSE and Kubernetes NDJSON watch payloads into `items` so watch preview/follow can consume real provider-native event streams without dropping all but the first event; [done]
- Kubernetes watch `BOOKMARK` events update `latest_resource_version` without being exposed as ordinary resource changes; when resource events are truncated, the visible last resourceVersion remains the safe continuation point; [done]
- provider log client accepts bounded plain-text Kubernetes/Rancher pod log payloads in addition to JSON wrappers, then applies existing tail bounds and redaction before response/action/audit summaries; [done]
- bounded logs follow suppresses already-sent overlapping tail lines between provider snapshots and sends only the new suffix as `follow_delta`; [done]
- opt-in provider-native logs follow batch reads from `pod_logs_stream_path_template` when WebSocket query includes `provider_stream=1`, with bounded line count, timeout, redaction and metadata-only audit/action summaries; selected `container` is now carried through REST snapshot, polling follow, provider stream batch and continuous provider stream paths, and WebTerm appends `container=...` to Rancher/Kubernetes log proxy paths when the provider template does not already contain `{container}`; [done]
- provider-native log stream reader reports `truncated=false` when the stream ends exactly at the configured line limit and `truncated=true` only when more bytes/lines are present; [done]
- opt-in provider-native watch follow batch marks Kubernetes watch chunks as `provider_watch_stream_batch` when WebSocket query includes `provider_stream=1`, with resourceVersion continuation and metadata-only audit/action summaries; [done]
- provider-native continuous WebSocket/SSE log follow via one opened provider stream when WebSocket query uses `provider_stream=continuous` or `provider_stream=1&stream_transport=continuous`; [done]
- provider-native continuous resource watch stream via one opened provider watch response when WebSocket query uses `provider_stream=continuous` or `provider_stream=1&stream_transport=continuous`; [done]

Tests:

- logs snapshot opens only for admin-read or higher; [done]
- audit/action metadata contains target/source/line count but no log content; [done]
- provider errors surface cleanly; [done for snapshot path]
- watch preview opens only for admin-read or higher; [done]
- watch preview stores event count/resourceVersion metadata without raw resource body in action summaries; [done]
- stream rejects expired session before provider call or start audit; [done]
- stream audit contains target/duration/line count/event count without raw log/resource body; [done]
- follow stream lifecycle records single start/stop/fail audit, bounded params, and `client_disconnect` close reason without raw batch body; [done]
- bounded follow stream closes without another provider call when the active admin session expires or is closed mid-loop; [done for service helper and real WebSocket consumer]
- bounded watch follow proves resourceVersion progression across real WebSocket batches; [done]
- provider-native watch payload decoding covers multi-event SSE, NDJSON and single-event compatibility; [done]
- watch preview handles Kubernetes `BOOKMARK` resourceVersion advancement without polluting visible event rows; [done]
- pod logs snapshot and Admin logs stream batches accept provider plain-text log payloads with tail bounding, line trimming and secret redaction; [done]
- real WebSocket logs follow proves overlapping tail snapshots are de-duplicated before sending client batches; [done]
- real WebSocket logs follow can use provider-native stream batch reader via `provider_stream=1`; [done]
- provider log stream reader has exact-limit truncation regression tests; [done]
- provider log line stream reads multiple WebSocket batches from one opened provider response instead of reopening the provider per batch; [done]
- real WebSocket logs follow can use provider-native continuous stream reader via `provider_stream=continuous`, with redaction and provider EOF close; [done]
- provider-native continuous log stream closes on idle timeout and closes the provider handle; [done]
- real WebSocket watch follow can use provider-native stream batch reader via `provider_stream=1`; [done]
- provider watch event stream parser reads SSE and NDJSON watch events from one opened provider response; [done]
- real WebSocket watch follow can use provider-native continuous stream reader via `provider_stream=continuous`, with event sanitization, `BOOKMARK` resourceVersion advancement and provider EOF close; [done]
- provider-native continuous watch stream closes on idle timeout and closes the provider handle; [done]

Verification run:

```text
docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_streams.py tests/test_kubernetes_ops_admin_resources.py tests/test_kubernetes_ops_logs.py tests/test_kubernetes_ops_admin_sessions.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db
36 passed

npm test -- --run src/pages/KubernetesAdminPage.test.tsx src/pages/KubernetesPage.test.tsx src/pages/KubernetesInventoryPages.test.tsx
3 files / 11 tests passed

docker compose exec -T backend python scripts/check_architecture_sizes.py --strict-new
SUCCESS: All architecture contracts satisfied.

npm run build
vite build passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_streams.py -q --create-db
13 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_stream_websockets.py -q --create-db
3 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_provider_clients.py tests/test_kubernetes_ops_admin_resources.py tests/test_kubernetes_ops_admin_stream_websockets.py -q --create-db
17 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_watch_normalization.py tests/test_kubernetes_ops_admin_resources.py tests/test_kubernetes_ops_provider_clients.py tests/test_kubernetes_ops_admin_stream_websockets.py tests/test_kubernetes_ops_admin_streams.py -q --create-db
32 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_provider_clients.py tests/test_kubernetes_ops_logs.py tests/test_kubernetes_ops_admin_logs_plain_text.py tests/test_kubernetes_ops_admin_resources.py tests/test_kubernetes_ops_admin_streams.py tests/test_kubernetes_ops_admin_stream_websockets.py -q --create-db
38 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_stream_websockets.py tests/test_kubernetes_ops_admin_streams.py tests/test_kubernetes_ops_provider_clients.py tests/test_kubernetes_ops_logs.py tests/test_kubernetes_ops_admin_logs_plain_text.py -q --create-db
27 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_logs_plain_text.py tests/test_kubernetes_ops_admin_stream_websockets.py tests/test_kubernetes_ops_admin_streams.py tests/test_kubernetes_ops_provider_clients.py tests/test_kubernetes_ops_logs.py -q --create-db
29 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_provider_clients.py -q --create-db
7 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_provider_clients.py tests/test_kubernetes_ops_admin_logs_plain_text.py tests/test_kubernetes_ops_admin_stream_websockets.py -q --create-db
15 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_provider_clients.py tests/test_kubernetes_ops_admin_stream_websockets.py -q --create-db
16 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_provider_clients.py tests/test_kubernetes_ops_admin_stream_websockets.py tests/test_kubernetes_ops_admin_logs_plain_text.py tests/test_kubernetes_ops_admin_streams.py -q --create-db
31 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_watch_stream_batch.py tests/test_kubernetes_ops_admin_stream_websockets.py tests/test_kubernetes_ops_admin_resources.py tests/test_kubernetes_ops_admin_watch_normalization.py tests/test_kubernetes_ops_provider_clients.py -q --create-db
25 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_provider_clients.py tests/test_kubernetes_ops_admin_stream_websockets.py -q --create-db
19 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_provider_clients.py tests/test_kubernetes_ops_admin_stream_websockets.py tests/test_kubernetes_ops_admin_logs_plain_text.py tests/test_kubernetes_ops_admin_streams.py tests/test_kubernetes_ops_admin_watch_stream_batch.py tests/test_kubernetes_ops_admin_watch_normalization.py tests/test_kubernetes_ops_admin_resources.py -q --create-db
48 passed
```

### Phase 4: Dry-run, diff, apply, patch, scale, restart

Status: started on 2026-07-01 with CRD schema-aware manifest validation, safe server-side dry-run apply, sanitized top-level and path-level diff preview, runtime-gated native apply, runtime-gated native patch, and runtime-gated scale/restart backend paths. Real apply/patch/scale/restart stay disabled by default until their explicit `KUBERNETES_ADMIN_NATIVE_*_ENABLED=true` flags are set; delete is covered by the guarded Phase 5 path, while exec/port-forward are separate guarded phases.

Deliverables:

- CRD schema-aware validation preflight; [done: `POST /api/kubernetes/admin/clusters/{cluster_id}/resources/schema-validate/` reads CRD `openAPIV3Schema`, validates bounded `required`/`type`/`enum`/number constraints, stores no raw manifest body, and falls back to `schema_unavailable` when no matching CRD schema exists]
- server-side dry-run apply; [done: `POST /api/kubernetes/admin/clusters/{cluster_id}/resources/dry-run-apply/` returns sanitized submitted/server objects, `diff_summary` and bounded `diff.changes` path-level preview]
- active approved write-session gate for dry-run; [done: service-level guard requires `approval_ref`, `approved_by`, and `approved_at`, not just `status=active`]
- sanitized submitted/server object response and top-level diff preview; [done]
- Secret body redaction in dry-run response/action/audit; [done]
- TypeScript client contract for dry-run apply; [done]
- TypeScript client contract for schema validation; [done]
- runtime-gated apply after active write session and dry-run proof; [done: default disabled by `KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED=false`; emergency break-glass dry-run bypass requires separate `KUBERNETES_ADMIN_BREAK_GLASS_APPLY_BYPASS_ENABLED=true` and records `dry_run_bypassed` evidence]
- keyed dry-run manifest fingerprint so apply can prove the manifest was already dry-run without storing raw Secret data; [done]
- TypeScript client contract for apply; [done]
- runtime-gated scale action via Kubernetes scale subresource; [done: default disabled by `KUBERNETES_ADMIN_NATIVE_SCALE_ENABLED=false`]
- runtime-gated restart action via rollout restart annotation patch; [done: default disabled by `KUBERNETES_ADMIN_NATIVE_RESTART_ENABLED=false`]
- TypeScript client contract for scale/restart; [done]
- runtime-gated patch action via Kubernetes PATCH; [done: default disabled by `KUBERNETES_ADMIN_NATIVE_PATCH_ENABLED=false`]
- TypeScript client contract for patch; [done]
- GitOps-owner detection and Fleet/Devtron warnings; [done for ownership context and backend direct-mutation guard]

Tests:

- schema validation requires active approved write session, does not mutate state, does not return/store raw manifest body, and cannot satisfy apply dry-run proof; [done]
- dry-run blocked without `kubernetes_admin_write` and active approved write session; [done]
- dry-run blocked when service receives a manually active but unapproved write session; [done]
- dry-run respects session namespace/kind scope; [done]
- Secret dry-run redacts data and stores metadata only in action/audit; [done]
- apply blocked while native apply flag is disabled; [done]
- apply blocked without active write session; [done]
- apply blocked without prior successful dry-run unless explicitly approved break-glass bypass is enabled; [done: normal write sessions still require proof; break-glass bypass requires separate flag, active approved break-glass session, `apply` verb, reason and evidence marker]
- apply blocked when manifest changes after dry-run proof; [done]
- patch blocked while native patch flag is disabled; [done]
- patch respects session namespace/kind scope and allowed verbs; [done]
- Secret patch redacts response/action/audit and stores patch body metadata only; [done]
- scale/restart blocked while runtime flags are disabled; [done]
- scale/restart respect session namespace/kind scope and allowed verbs; [done]
- scale validates bounded replica count; [done]
- privileged dry-run/write/break-glass services require approved-session evidence before provider/action side effects; [done: common `admin_write_approval` helper requires `approval_ref`, `approved_by` and `approved_at` for dry-run/apply/patch/scale/restart/delete/exec/port-forward; prod/prod-like write misses return `production_approval_required`]
- Fleet/Devtron/external-owned object blocks direct apply/patch/scale/restart/delete before provider call; [done]
- Secret diffs redact data; [done for dry-run and apply action/audit]
- audit and action report contain lifecycle evidence; [backend action request list/status/report and Admin action evidence/report APIs done with owner/staff visibility, sanitized request/report/policy/session payloads, filters, and bounded action timelines; next for full report UI]

Verification run:

```text
docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_dry_run.py tests/test_kubernetes_ops_admin_resources.py tests/test_kubernetes_ops_admin_sessions.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db
30 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_apply.py tests/test_kubernetes_ops_admin_dry_run.py tests/test_kubernetes_ops_admin_sessions.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db
23 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_workload_actions.py tests/test_kubernetes_ops_admin_apply.py tests/test_kubernetes_ops_admin_dry_run.py tests/test_kubernetes_ops_admin_sessions.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db
29 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_production_approval.py tests/test_kubernetes_ops_admin_apply.py tests/test_kubernetes_ops_admin_patch.py tests/test_kubernetes_ops_admin_workload_actions.py tests/test_kubernetes_ops_admin_delete.py tests/test_kubernetes_ops_admin_owner_guard.py -q --create-db
26 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_dry_run.py tests/test_kubernetes_ops_admin_apply.py tests/test_kubernetes_ops_admin_patch.py tests/test_kubernetes_ops_admin_workload_actions.py tests/test_kubernetes_ops_admin_delete.py tests/test_kubernetes_ops_admin_exec.py tests/test_kubernetes_ops_admin_port_forward.py tests/test_kubernetes_ops_admin_production_approval.py -q --create-db
42 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_schema_validation.py tests/test_kubernetes_ops_admin_dry_run.py tests/test_kubernetes_ops_admin_apply.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db
33 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_release_evidence.py tests/test_kubernetes_ops_release_admin_mode_safety.py tests/test_kubernetes_ops_release_evidence_summary.py tests/test_kubernetes_ops_release_handoff.py tests/test_kubernetes_ops_release_preflight.py -q --create-db
20 passed

docker compose exec -T backend python manage.py check
System check identified no issues (0 silenced).

docker compose exec -T backend python manage.py makemigrations --check --dry-run
No changes detected

docker compose exec -T backend python scripts/check_architecture_sizes.py --strict-new
SUCCESS: All architecture contracts satisfied.

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_patch.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db
14 passed
```

### Phase 5: Delete with guardrails

Status: implemented on 2026-07-01 as a runtime-gated backend path. Real delete stays disabled by default until `KUBERNETES_ADMIN_NATIVE_DELETE_ENABLED=true`; even then it blocks Namespace/cluster-scoped/system-resource deletes, protected namespaces, missing exact confirmation, missing reason, expired sessions, and out-of-scope namespace/kind targets before provider calls.

Deliverables:

- delete endpoint; [done: `POST /api/kubernetes/admin/clusters/{cluster_id}/resources/delete/`]
- typed confirmation requirement; [done: `delete {Kind} {namespace}/{name}`]
- namespace/system-resource denylist; [done: protected namespaces plus cluster-kind denylist]
- finalizer/orphan/cascade options only after explicit selection; [done for explicit `propagation_policy`; finalizer mutation remains unsupported]
- TypeScript client contract for delete; [done]

Tests:

- delete blocked while native delete flag is disabled; [done]
- delete namespace remains blocked outside break-glass; [done: Namespace kind blocked]
- delete resource requires exact confirmation string; [done]
- system namespaces denied; [done]
- delete respects session namespace/kind scope and allowed verbs; [done]
- audit includes reason, target, and result; [done]

Verification run:

```text
docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_delete.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db
16 passed
```

### Phase 6: Pod exec

Status: foundation implemented on 2026-07-01 as a fail-closed WebSocket bridge. Default policy returns `native_exec_disabled`; with `KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED=true`, the bridge validates approved break-glass session evidence (`approval_ref`, `approved_by`, `approved_at`), namespace/kind scope, reason, protected namespace denylist, and command allow/deny rules, writes `K8sAdminAction`/`K8sAdminRecording`/audit evidence, then returns `execution_blocked` unless the separate stream gate is enabled. Opt-in provider-native exec streaming now exists only when `KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED=true`, `KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED=true`, and the WebSocket request asks for `provider_stream=1`; the recording gate is checked before provider/action side effects. In production release mode, the provider stream also requires `KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF` before action/provider side effects. When allowed, it emits redacted stdout/stderr frames, stores metadata counters/status/exit code in action/recording evidence, and persists bounded redacted stdin/stdout/stderr events in `K8sAdminRecordingEvent`.

Deliverables:

- WebSocket exec bridge; [foundation done: `ws/kubernetes/admin/exec/{session_id}/`]
- per-session TTL/idle timeout; [done for active-session gate, exec stream idle timeout and disconnect close]
- transcript/metadata retention setting; [foundation done: centralized recording policy, `K8sAdminRecording`, `K8sAdminRecordingEvent`, `KUBERNETES_ADMIN_INTERACTIVE_METADATA_RETENTION_DAYS` / `KUBERNETES_ADMIN_INTERACTIVE_TRANSCRIPT_RETENTION_DAYS`, bounded event limits, and bounded redacted exec/terminal/node-debug event storage; raw full transcript body storage is intentionally not enabled]
- owner/staff recording evidence API; [done: `/api/kubernetes/admin/recordings/` and `/api/kubernetes/admin/recordings/{recording_id}/`]
- recording retention cleanup; [done: `cleanup_interactive_recordings()` and `cleanup_kubernetes_admin_recordings`, transcript TTL removes events, metadata TTL removes recording rows]
- command allowlist/denylist; [done: default allow/deny lists plus settings]
- namespace/kind restrictions. [done for break-glass session scope and protected namespace denylist]
- provider-native Kubernetes exec stream. [done behind `KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED=true` + `KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED=true` + `provider_stream=1`; production mode additionally requires `KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF` before action/provider side effects]

Tests:

- no exec while native exec flag is disabled; [done]
- no exec without break-glass session; [done]
- no exec with manually active but unapproved break-glass session; [done]
- no exec after session expiry; [covered by session active-state gate; add WebSocket close test with real stream]
- privileged/system namespace blocked unless break-glass; [done for protected namespaces even with break-glass]
- command denylist and shell inline execution blocked; [done]
- exec stream requires separate streaming flag before provider/action side effects; [done]
- exec stream requires separate recording flag before provider/action side effects; [done: `exec_recording_required`]
- provider exec stream reads stdout/stderr/status frames, redacts output sent over WebSocket and stores action/audit/recording summaries with recording policy; [done]
- production provider exec stream is blocked before action/provider side effects when restricted credential evidence is missing; [done]
- exec stdin/stdout/stderr transcript events are persisted only as bounded redacted `K8sAdminRecordingEvent` rows and exposed through sanitized action report evidence; [done]
- direct recording list/detail APIs enforce owner/staff visibility and sanitize event data/metadata before output; [done]
- recording retention cleanup dry-run/apply deletes only expired evidence according to metadata/transcript cutoffs; [done]
- dangerous Admin actions can be closed with sanitized post-review evidence through `POST /api/kubernetes/admin/actions/{action_id}/review/`; [done]
- transcript/metadata retained according to setting; [metadata retention settings and bounded redacted exec/terminal/node-debug event rows done; full raw transcript body storage remains intentionally out of scope]
- disconnect closes backend stream. [done for provider handle and action close summary]

Verification run:

```text
docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_exec.py tests/test_kubernetes_ops_admin_streams.py tests/test_kubernetes_ops_terminal_safety.py tests/test_kubernetes_ops_permission_matrix.py tests/test_kubernetes_ops_admin_delete.py tests/test_kubernetes_ops_admin_patch.py tests/test_kubernetes_ops_admin_workload_actions.py tests/test_kubernetes_ops_admin_apply.py tests/test_kubernetes_ops_admin_dry_run.py tests/test_kubernetes_ops_admin_sessions.py -q --create-db
60 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_exec.py tests/test_kubernetes_ops_admin_exec_stream_websocket.py tests/test_kubernetes_ops_provider_clients.py -q --create-db
22 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_exec.py tests/test_kubernetes_ops_admin_exec_stream_websocket.py tests/test_kubernetes_ops_admin_stream_websockets.py tests/test_kubernetes_ops_provider_clients.py tests/test_kubernetes_ops_admin_port_forward.py tests/test_kubernetes_ops_terminal_safety.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db
60 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_exec_stream_websocket.py tests/test_kubernetes_ops_admin_port_forward_tunnel_websocket.py tests/test_kubernetes_ops_admin_exec.py tests/test_kubernetes_ops_admin_port_forward.py tests/test_kubernetes_ops_admin_node_debug.py tests/test_kubernetes_ops_admin_terminal.py tests/test_kubernetes_ops_terminal_safety.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db
60 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_exec.py tests/test_kubernetes_ops_admin_port_forward.py tests/test_kubernetes_ops_admin_exec_stream_websocket.py tests/test_kubernetes_ops_admin_port_forward_tunnel_websocket.py tests/test_kubernetes_ops_admin_terminal.py tests/test_kubernetes_ops_admin_node_debug.py tests/test_kubernetes_ops_admin_actions.py -q --create-db
42 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_exec_stream_websocket.py tests/test_kubernetes_ops_admin_actions.py tests/test_kubernetes_ops_admin_exec.py -q --create-db
18 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_recordings.py -q --create-db
6 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_actions.py tests/test_kubernetes_ops_admin_exec_stream_websocket.py tests/test_kubernetes_ops_admin_recordings.py -q --create-db
15 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_exec.py tests/test_kubernetes_ops_admin_port_forward.py tests/test_kubernetes_ops_admin_exec_stream_websocket.py tests/test_kubernetes_ops_admin_port_forward_tunnel_websocket.py tests/test_kubernetes_ops_admin_terminal.py tests/test_kubernetes_ops_admin_node_debug.py tests/test_kubernetes_ops_admin_actions.py tests/test_kubernetes_ops_admin_recordings.py -q --create-db
48 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_recording_readiness.py tests/test_kubernetes_ops_terminal_safety.py tests/test_kubernetes_ops_operator_docs.py -q --create-db
14 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_action_review_readiness.py tests/test_kubernetes_ops_admin_recordings.py tests/test_kubernetes_ops_admin_actions.py tests/test_kubernetes_ops_admin_exec_stream_websocket.py tests/test_kubernetes_ops_admin_recording_readiness.py tests/test_kubernetes_ops_operator_docs.py -q --create-db
27 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_actions.py -q --create-db
10 passed
```

### Phase 7: Port-forward

Status: backend tunnel slice implemented on 2026-07-01. Default policy returns `native_port_forward_disabled`; with `KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED=true`, the bridge validates approved break-glass session evidence (`approval_ref`, `approved_by`, `approved_at`), namespace/kind scope, protected namespace denylist, target allowlist, target port, max duration, reason, and metadata-only audit/action/recording evidence. Real tunnel traffic only runs when the separate `KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED=true` and `KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED=true` flags are set and the WebSocket request explicitly uses `provider_stream=1`; the recording gate is checked before provider/action side effects. In production release mode, the tunnel also requires `KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF`, `KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF`, exact non-wildcard `KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS`, default protected namespace coverage, and max duration <=900s before action/provider side effects. The tunnel stores only byte/duration/status recording metadata without payload bytes.

Deliverables:

- WebSocket/control-plane route; [foundation done: `ws/kubernetes/admin/port-forward/{session_id}/`]
- target allowlist; [done: `KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS`]
- max duration; [done: `KUBERNETES_ADMIN_PORT_FORWARD_MAX_DURATION_SECONDS`]
- audit bytes/duration metadata; [done for provider tunnel EOF/stop path with `K8sAdminRecording` and recording policy]
- rough frontend endpoint panel. [next]
- provider-native tunnel transport. [done behind `KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED=true` + `KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED=true` + `provider_stream=1`; production mode additionally requires `KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF`, `KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF`, exact non-wildcard target allowlist, protected namespace policy, and <=900s max duration before action/provider side effects]

Tests:

- no port-forward while native port-forward flag is disabled; [done]
- no port-forward without break-glass session; [done]
- no port-forward with manually active but unapproved break-glass session; [done]
- no provider tunnel without separate tunnel flag before action/provider side effects; [done]
- no provider tunnel without separate recording flag before action/provider side effects; [done: `port_forward_recording_required`]
- production provider tunnel is blocked before action/provider side effects when restricted credential evidence is missing; [done]
- production provider tunnel is blocked before action/provider side effects when port-forward network policy evidence is missing; [done]
- production readiness rejects wildcard port-forward allowlists; [done]
- invalid target denied; [done for target allowlist and port range]
- protected namespace denied; [done]
- TTL closes tunnel; [done: explicit tunnel expiry regression returns `admin_session_expired` and closes provider handle]
- provider EOF closes tunnel and closes provider handle; [done]
- client-to-provider bytes and provider-to-client bytes are counted without storing payload; [done]
- audit metadata is recorded. [done for blocked bridge metadata and provider tunnel byte/duration metadata]

Verification run:

```text
docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_port_forward.py tests/test_kubernetes_ops_admin_exec.py tests/test_kubernetes_ops_admin_streams.py tests/test_kubernetes_ops_terminal_safety.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db
40 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_port_forward.py tests/test_kubernetes_ops_admin_port_forward_tunnel_websocket.py tests/test_kubernetes_ops_provider_clients.py -q --create-db
24 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_port_forward.py tests/test_kubernetes_ops_admin_port_forward_tunnel_websocket.py tests/test_kubernetes_ops_admin_exec.py tests/test_kubernetes_ops_admin_exec_stream_websocket.py tests/test_kubernetes_ops_admin_stream_websockets.py tests/test_kubernetes_ops_provider_clients.py tests/test_kubernetes_ops_terminal_safety.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db
66 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_exec_stream_websocket.py tests/test_kubernetes_ops_admin_port_forward_tunnel_websocket.py tests/test_kubernetes_ops_admin_exec.py tests/test_kubernetes_ops_admin_port_forward.py tests/test_kubernetes_ops_admin_node_debug.py tests/test_kubernetes_ops_admin_terminal.py tests/test_kubernetes_ops_terminal_safety.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db
60 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_exec.py tests/test_kubernetes_ops_admin_port_forward.py tests/test_kubernetes_ops_admin_exec_stream_websocket.py tests/test_kubernetes_ops_admin_port_forward_tunnel_websocket.py tests/test_kubernetes_ops_admin_terminal.py tests/test_kubernetes_ops_admin_node_debug.py tests/test_kubernetes_ops_admin_actions.py -q --create-db
42 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_interactive_transport_readiness.py tests/test_kubernetes_ops_admin_exec.py tests/test_kubernetes_ops_admin_exec_stream_websocket.py tests/test_kubernetes_ops_admin_port_forward.py tests/test_kubernetes_ops_admin_port_forward_tunnel_websocket.py tests/test_kubernetes_ops_terminal_safety.py tests/test_kubernetes_ops_operator_docs.py -q --create-db
45 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_interactive_transport_readiness.py tests/test_kubernetes_ops_admin_port_forward.py tests/test_kubernetes_ops_terminal_safety.py tests/test_kubernetes_ops_release_handoff.py -q --create-db
31 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_interactive_transport_readiness.py tests/test_kubernetes_ops_admin_port_forward.py tests/test_kubernetes_ops_terminal_safety.py tests/test_kubernetes_ops_release_handoff.py tests/test_kubernetes_ops_release_evidence_summary.py -q --create-db
38 passed
```

### Phase 8: Break-glass cluster terminal and node debug

Status: started on 2026-07-01 with the mandatory break-glass post-review backend gate. Break-glass sessions now carry `post_review_required=true` while pending/active/closed, expose `post_review_status`, and can be marked reviewed only by staff with `kubernetes_break_glass` after the session is closed, revoked, or expired. Cluster terminal now has a fail-closed start/stop lifecycle foundation plus an opt-in WebSocket provider-stream foundation: `POST /api/kubernetes/admin/sessions/{session_id}/terminal/start/` validates the approved break-glass session and restricted context, records metadata-only action/audit plus `K8sAdminRecording` with centralized recording policy and retention values while transport is disabled, and returns `execution_blocked`; `ws/kubernetes/admin/terminal/{session_id}/?provider_stream=1` can open a provider stream only when `KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED=true`, `KUBERNETES_ADMIN_CLUSTER_TERMINAL_RECORDING_ENABLED=true`, provider contract label `cluster_terminal_path_template` with `{cluster_id}` and `{namespace}`, and, in production release mode, `KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF` are present before action/audit/provider side effects. `terminal/stop/` rejects non-running terminals and audits the stop attempt. Node debug now has the same fail-closed lifecycle plus an opt-in WebSocket provider-stream foundation: `POST /api/kubernetes/admin/sessions/{session_id}/node-debug/start/` validates approved break-glass session evidence, `node` scope, node name and reason, records metadata-only action/audit plus `K8sAdminRecording` with centralized recording policy and retention values while transport is disabled, and returns `execution_blocked`; `ws/kubernetes/admin/node-debug/{session_id}/?provider_stream=1` can open a provider stream only when `KUBERNETES_ADMIN_NODE_DEBUG_ENABLED=true`, `KUBERNETES_ADMIN_NODE_DEBUG_RECORDING_ENABLED=true`, provider contract label `node_debug_path_template` with `{cluster_id}` and `{node_name}`, and, in production release mode, `KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF` are present before action/audit/provider side effects. Both WebSocket streams store bounded redacted `stdin`/`stdout`/`stderr` events, complete/fail the linked action and recording, close the provider handle on EOF/error/disconnect/session expiry, and remain disabled by default until production live provider evidence approves them.

Restricted kube context foundation is now also implemented as a metadata-only plan endpoint: `POST /api/kubernetes/admin/sessions/{session_id}/restricted-context/`. It requires an active approved break-glass session with exactly one namespace, returns namespace-scoped ServiceAccount/Role/RoleBinding manifests with TTL annotations, includes only read rules plus explicit `pods/exec`/`pods/portforward` subresource create rules when present in the session scope, and fails validation on ClusterRole, wildcard, Secret, node, attach, or base-resource write access. It does not apply the manifest and does not return kubeconfig or token material.

Deliverables:

- break-glass request/approval; [done via Admin Mode sessions]
- short-lived restricted kube context; [foundation done: metadata-only RBAC plan, no apply/token/kubeconfig]
- cluster terminal; [fail-closed lifecycle plus WebSocket provider-stream foundation done: start/stop API, opt-in provider stream behind terminal + recording flags and provider contract, redacted recording events]
- node debug only when explicitly enabled; [fail-closed lifecycle plus WebSocket provider-stream foundation done: start/stop API, node target validation, opt-in provider stream behind debug + recording flags and provider contract, redacted recording events]
- mandatory post-review marker. [done: `POST /api/kubernetes/admin/sessions/{session_id}/review/`]

Tests:

- unavailable without `kubernetes_break_glass`; [done for session creation and post-review reviewer]
- always requires reason, TTL, approval; [done for session creation/approval and fail-closed terminal/node-debug REST plus WebSocket provider-stream foundations]
- no silent extension after expiry; [done: expired pending sessions are marked `expired` before approval and cannot be silently activated or extended]
- readiness reports break-glass controls; [done for exec/port-forward/cluster-terminal/node-debug flags and blocked capabilities]
- audit proves request/start/stop/review. [done for create/approve/close/post-review, fail-closed cluster terminal/node-debug start/stop attempts, and opt-in provider-stream start/stop action/recording evidence]
- restricted context is namespace-scoped and rejects wildcard/protected namespaces, ClusterRole, Secret/node access, attach, and base-resource writes. [done]
- terminal WebSocket stream remains fail-closed until `KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED=true`, `KUBERNETES_ADMIN_CLUSTER_TERMINAL_RECORDING_ENABLED=true`, Rancher provider `cluster_terminal_path_template`, production restricted evidence when required, and `provider_stream=1`. [done: recording/restricted-evidence/provider-contract gates run before action/audit/provider side effects; provider stream records redacted events]
- node debug WebSocket stream remains fail-closed until `KUBERNETES_ADMIN_NODE_DEBUG_ENABLED=true`, `KUBERNETES_ADMIN_NODE_DEBUG_RECORDING_ENABLED=true`, Rancher provider `node_debug_path_template`, production restricted evidence when required, and `provider_stream=1`. [done: recording/restricted-evidence/provider-contract gates run before action/audit/provider side effects; provider stream records redacted events]

Verification run:

```text
docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_sessions.py tests/test_kubernetes_ops_terminal_safety.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db
35 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_sessions.py -q --create-db
15 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_restricted_context.py tests/test_kubernetes_ops_admin_sessions.py tests/test_kubernetes_ops_terminal_safety.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db
39 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_terminal.py tests/test_kubernetes_ops_admin_restricted_context.py tests/test_kubernetes_ops_admin_sessions.py tests/test_kubernetes_ops_terminal_safety.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db
44 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_node_debug.py tests/test_kubernetes_ops_admin_terminal.py tests/test_kubernetes_ops_admin_restricted_context.py tests/test_kubernetes_ops_admin_sessions.py tests/test_kubernetes_ops_terminal_safety.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db
51 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_terminal.py tests/test_kubernetes_ops_admin_node_debug.py tests/test_kubernetes_ops_admin_interactive_transport_readiness.py tests/test_kubernetes_ops_terminal_safety.py -q --create-db
38 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_terminal_node_debug_websocket.py tests/test_kubernetes_ops_admin_terminal.py tests/test_kubernetes_ops_admin_node_debug.py tests/test_kubernetes_ops_admin_interactive_transport_readiness.py tests/test_kubernetes_ops_terminal_safety.py -q --create-db
41 passed

docker compose exec -T backend python manage.py check
System check identified no issues (0 silenced).

docker compose exec -T backend python manage.py makemigrations --check --dry-run
No changes detected

docker compose exec -T backend python scripts/check_architecture_sizes.py --strict-new
SUCCESS: All architecture contracts satisfied.
```

## 12. Required Refactors To Existing Tests

Older tests intentionally asserted that no native admin routes existed. That is no longer the target: guarded Admin Mode routes now exist, while legacy direct pod exec/attach/debug REST routes must stay absent. Keep changing tests carefully:

- `tests/test_kubernetes_ops_terminal_safety.py`
  - keep default read-only posture disabled;
  - add separate tests showing admin routes exist but are denied without admin session;
  - fail if `kubernetes` alone enables exec/port-forward.

- `tests/test_kubernetes_ops_permission_matrix.py`
  - add admin-read/admin-write/break-glass policies;
  - keep staff-without-explicit-feature denied;
  - keep provider admin actions staff-only unless explicitly changed.

- `tests/test_kubernetes_ops_action_requests.py`
  - keep current action-request skeleton valid;
  - add native execution path only when session, dry-run, approval, and policy are satisfied.

- `tests/test_kubernetes_ops_logs.py`
  - keep bounded snapshot endpoint;
  - add streaming endpoint tests separately.

- `tests/test_kubernetes_ops_release_evidence.py`
  - release evidence must continue to pass for safe cockpit even if Admin Mode is disabled;
  - add optional Admin Mode evidence only when enabled.
  - keep `normal_user_surface` required for release; failures must add blocker `normal_user_surface:<status>` and keep sidebar blocked.

## 13. Release Gates

Admin Mode cannot be considered ready until:

- architecture guard passes;
- migrations pass;
- all existing Kubernetes Ops tests pass;
- new admin permission/session tests pass;
- read-only explorer and node maintenance foundation tested against mocked provider responses; [done for rough List/YAML UI, resource detail/events, Node view, cordon/uncordon/drain foundation, gated Eviction API drain execution, plus Devtron/Fleet ownership context]
- real local Rancher/Devtron smoke proves list/get/log/describe path; [done for live provider smoke v3: provider probes, read-only dry-run sync, synced Rancher Pod YAML/get path, bounded logs snapshot, live read-only describe, and read-only node drain preflight through Admin backend services; streaming follow remains separate Admin stream evidence]
- no frontend response exposes provider token/kubeconfig; [done: `normal_user_surface` release proof now creates provider `secret_ref` plus token/kubeconfig-like marker values inside rollback-only fixtures, scans reader/staff frontend-facing provider/cluster/app/workload/pod/network/Fleet/Helm/Devtron-detail/diagnostics-summary/action-summary/staff-release-summary payloads, and records `frontend_response_credential_scan.status=ready` only when secret refs and forbidden credential values are absent]
- Secret bodies are redacted by default; [done, with Secret list metadata-only proof even when values are requested, optional named Secret reveal behind explicit `kubernetes_secret_read` and runtime flag; release evidence now proves denied reveal stops before provider calls and raw values stay out of action summaries]
- action audit rows are created for session, read-sensitive, dry-run write preview, exec, and tunnel flows; [done for sessions/read/dry-run preview/exec stream metadata/port-forward bridge metadata/provider tunnel byte metadata]
- WebSocket sessions close on TTL/expiry/revoke/explicit close; [done for bounded logs/watch follow, provider EOF/disconnect for exec/tunnel, explicit port-forward tunnel expiry regression, and provider handle close before final port-forward stopped/error events]
- runbook documents emergency disablement. [done: fast disable includes `KUBERNETES_ADMIN_MODE_ENABLED=false`, sidebar lock, feature removal path and proof checks]
- normal-user acceptance proves the workflow stays inside WebTerm, with external UIs available only as staff/admin fallback; [backend done and release-evidence-backed by `normal_user_surface`: reader overview/cluster/app/workload/pod/network/Fleet/Helm/Devtron-detail/diagnostics-summary payloads hide external links and provider config, public serializers redact token-like label/metadata fields, reader cannot call fallback deeplink audit, staff sees sanitized fallback links without query/token/userinfo and can audit fallback opens]
- production handoff lists `KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF` as a required evidence reference before any production interactive transport, lists `KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF` before any production port-forward tunnel, and release summary explains `readiness:admin_interactive_transport=missing`; [done]

Production enablement should require:

```text
KUBERNETES_ADMIN_MODE_ENABLED=true
KUBERNETES_ADMIN_WRITE_ENABLED=true
KUBERNETES_BREAK_GLASS_ENABLED=false  # only true for tested emergency environments
```

Default production posture should stay read-only until explicit rollout.

Latest focused release handoff/readiness evidence:

```text
docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_release_evidence.py tests/test_kubernetes_ops_release_handoff.py tests/test_kubernetes_ops_release_evidence_summary.py tests/test_kubernetes_ops_release_preflight.py tests/test_kubernetes_ops_admin_interactive_transport_readiness.py tests/test_kubernetes_ops_operator_docs.py -q --create-db
27 passed
```

Latest focused WebTerm-only normal-user API evidence:

```text
docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_api.py tests/test_kubernetes_ops_permission_matrix.py tests/test_kubernetes_ops_describe.py tests/test_kubernetes_ops_logs.py -q --create-db
40 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_api.py tests/test_kubernetes_ops_audit.py tests/test_kubernetes_ops_permission_matrix.py tests/test_kubernetes_ops_describe.py tests/test_kubernetes_ops_logs.py tests/test_kubernetes_ops_security_review.py -q --create-db
50 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_describe.py tests/test_kubernetes_ops_logs.py tests/test_kubernetes_ops_frontend_e2e.py tests/test_kubernetes_ops_security_review.py tests/test_kubernetes_ops_permission_matrix.py -q --create-db
32 passed
```

Latest focused WebTerm-only Fleet detail API evidence:

```text
docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_fleet_bundle_detail.py tests/test_kubernetes_ops_api.py tests/test_kubernetes_ops_action_requests.py -q --reuse-db
30 passed
```

Latest focused WebTerm-only namespace detail API evidence:

```text
docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_namespace_detail.py tests/test_kubernetes_ops_api.py -q --reuse-db
19 passed
```

Latest focused WebTerm-only pod detail API evidence:

```text
docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_pod_detail.py tests/test_kubernetes_ops_logs.py tests/test_kubernetes_ops_api.py -q --reuse-db
24 passed
```

Latest focused WebTerm-only workload detail API evidence:

```text
docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_workload_detail.py tests/test_kubernetes_ops_describe.py tests/test_kubernetes_ops_api.py -q --reuse-db
22 passed
```

Latest focused WebTerm-only network detail API evidence:

```text
docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_network_detail.py tests/test_kubernetes_ops_api.py -q --reuse-db
18 passed
```

Latest WebTerm-only read-only detail regression evidence:

```text
docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_network_detail.py tests/test_kubernetes_ops_namespace_detail.py tests/test_kubernetes_ops_workload_detail.py tests/test_kubernetes_ops_pod_detail.py tests/test_kubernetes_ops_api.py -q --reuse-db
28 passed
```

Latest focused WebTerm-only normal-user release evidence:

```text
docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_release_evidence.py tests/test_kubernetes_ops_release_evidence_summary.py tests/test_kubernetes_ops_release_handoff.py tests/test_kubernetes_ops_release_normal_user_surface.py tests/test_kubernetes_ops_release_readiness_summary.py tests/test_kubernetes_ops_release_external_evidence_bundle.py tests/test_kubernetes_ops_capabilities.py tests/test_kubernetes_ops_api.py tests/test_kubernetes_ops_permission_matrix.py tests/test_kubernetes_ops_helm_ownership.py tests/test_kubernetes_ops_devtron_app_detail.py tests/test_kubernetes_ops_diagnostics_summary.py tests/test_kubernetes_ops_action_requests.py tests/test_kubernetes_ops_action_summary.py -q --reuse-db
96 passed
```

Latest focused Admin Mode disablement evidence:

```text
docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_permission_matrix.py tests/test_kubernetes_ops_admin_sessions.py tests/test_kubernetes_ops_admin_metrics.py tests/test_production_worker_topology.py -q --reuse-db
48 passed

docker compose exec -T backend python -m pytest tests/test_kubernetes_ops_admin_restricted_context.py tests/test_kubernetes_ops_admin_dry_run.py tests/test_kubernetes_ops_admin_apply.py tests/test_kubernetes_ops_admin_exec.py tests/test_kubernetes_ops_admin_port_forward.py tests/test_kubernetes_ops_admin_metrics.py tests/test_kubernetes_ops_permission_matrix.py -q --reuse-db
62 passed

docker compose exec -T backend python manage.py check
System check identified no issues

docker compose exec -T backend python manage.py makemigrations kubernetes_ops core_ui --check --dry-run
No changes detected

docker compose exec -T backend python scripts/check_architecture_sizes.py --strict-new
SUCCESS: All architecture contracts satisfied.
```

## 14. Minimal Working Slice

If the goal is "works first, ugly UI later", build in this exact order:

1. Add `kubernetes_admin_read` and admin sessions. [done: feature flags, session/action models, lifecycle APIs, tests]
2. Add live resource list/get/YAML via Rancher provider. [backend done: discovery/resources/yaml/crds endpoints]
3. Add rough `/kubernetes/admin` table and YAML panel. [done: rough route, session flow, Discovery/CRDs/List/YAML controls, redacted result panel, frontend test, Docker browser smoke]
4. Add WebTerm-native Fleet/Devtron ownership context on resource/app pages. [done for Admin live resource list/get/YAML plus read-only Helm release owner/conflict view at `GET /api/kubernetes/helm/releases/`; richer app/resource page UX can improve later]
5. Add log streaming. [done for backend stream layer: bounded Admin pod logs snapshot, bounded resource watch preview, WebSocket batch, bounded polling follow, provider-native continuous log follow and provider-native continuous watch follow; final UI polish can come later]
6. Add dry-run apply and diff preview. [done for server-side dry-run preview]
7. Add apply/patch/scale/restart with active write session. [backend done as runtime-gated paths; action-request verification/report backend is in place for restart/scale/patch/delete plus dry-run-proof apply and native post-action verification plans; final UI polish next]
8. Add pod exec. [backend done behind separate stream flag: fail-closed WebSocket bridge + break-glass/session/command guards + opt-in provider stdout/stderr/status stream; restricted production credentials/final UX next]
9. Add port-forward. [backend done behind separate tunnel flag: fail-closed WebSocket bridge + break-glass/session/target allowlist guards + opt-in provider tunnel with byte metadata and deterministic provider-handle cleanup; frontend/network policy/live provider evidence next]
10. Add delete. [backend done as runtime-gated guarded Admin path and approval-gated action-request path]
11. Add node view, node maintenance, and break-glass terminal/node debug last. [read-only Node view backend done; cordon/uncordon/drain foundation done; drain execution done behind separate flag through Kubernetes Eviction API; live provider drain preflight evidence done as read-only no-cordon/no-eviction smoke; terminal/node-debug fail-closed lifecycle plus opt-in WebSocket provider-stream foundation done; production live provider evidence and final UX next]

Stop after step 5 if the first demo only needs to prove "Freelens-like read/admin explorer". Do not start pod exec before session TTL/audit are implemented.

## 15. Main Risks

| Risk | Why it matters | Control |
|---|---|---|
| Browser receives kubeconfig/token | Full cluster compromise | backend-only credentials, never serialize tokens |
| `kubernetes` feature silently becomes admin | too much access for existing users | separate feature flags and tests |
| Secret data leaks in YAML/diff/logs | credential exposure | redaction by default, separate secret-read permission |
| Direct apply fights Fleet/Devtron | GitOps drift and outages | owner detection, MR-first default, break-glass override |
| Exec becomes privilege escalation path | namespace/cluster compromise | session, TTL, restricted SA, transcript/audit |
| Port-forward bypasses network controls | lateral movement | allowlist, TTL, metadata audit |
| Generic CRDs break UI assumptions | fragile resource browser | generic JSON/YAML fallback first |
| Provider API paths differ by version | brittle integration | provider labels/templates and focused proxy module |

## 16. Definition Of Done

This section is now machine-verifiable through `definition_of_done` in `artifacts/kubernetes_ops_release_evidence.json` and the release handoff. Latest local evidence: `status=ready`, `ready=13`, `missing=0`, `total=13`; production sidebar remains blocked only by local release scope evidence, not by DoD coverage.

The implementation is complete when a trusted admin can, from WebTerm:

1. open Admin Mode only with explicit admin feature access; [done: `definition_of_done.explicit_admin_access=ready`]
2. select Rancher-backed cluster and namespace; [done: `definition_of_done.rancher_cluster_namespace=ready`]
3. browse common resources and CRDs; [done: `definition_of_done.resources_and_crds=ready`]
4. open full redacted YAML for a resource; [done: `definition_of_done.redacted_yaml=ready`]
5. stream logs; [done: `definition_of_done.log_streaming=ready`]
6. dry-run apply YAML and see diff; [done: `definition_of_done.dry_run_apply_diff=ready`]
7. execute an approved write action with audit; [done: `definition_of_done.approved_write_action=ready`]
8. open pod exec in an active time-limited session; [done: `definition_of_done.pod_exec_session=ready`]
9. open a short-lived port-forward session; [done: `definition_of_done.port_forward_session=ready`]
10. prove every action has audit metadata; [done: `definition_of_done.action_audit_metadata=ready`]
11. prove WebTerm is the primary login gateway and Rancher/Fleet/Devtron are backend-only provider integrations; [done: `definition_of_done.webterm_login_gateway=ready`]
12. prove regular Kubernetes users still only get safe cockpit behavior; [done: `definition_of_done.regular_user_safe_cockpit=ready`]
13. disable Admin Mode via env/feature without deleting data. [done: `KUBERNETES_ADMIN_MODE_ENABLED=false` disables policy/session/resource gates while preserving existing session/action rows]

## 17. References Checked

Local code/docs checked on 2026-07-01:

- `kubernetes_ops/urls.py`
- `kubernetes_ops/permissions.py`
- `kubernetes_ops/consumers.py`
- `kubernetes_ops/routing.py`
- `kubernetes_ops/services/admin_streams.py`
- `kubernetes_ops/admin_watch_views.py`
- `kubernetes_ops/services/admin_watch.py`
- `kubernetes_ops/services/admin_logs.py`
- `kubernetes_ops/services/admin_recording.py`
- `kubernetes_ops/services/admin_resources.py`
- `kubernetes_ops/services/terminal_safety.py`
- `kubernetes_ops/services/action_requests.py`
- `kubernetes_ops/services/logs.py`
- `kubernetes_ops/services/describe.py`
- `kubernetes_ops/services/provider_clients.py`
- `kubernetes_ops/models.py`
- `frontend/src/api/kubernetes.ts`
- `frontend/src/api/kubernetes-actions.ts`
- `frontend/src/pages/KubernetesAdminPage.tsx`
- `frontend/src/pages/KubernetesAdminPage.test.tsx`
- `frontend/src/pages/KubernetesPage.tsx`
- `frontend/src/pages/KubernetesClusterDetailPage.tsx`
- `frontend/src/pages/settings/SettingsKubernetesPage.tsx`
- `docs/WebTerm_Kubernetes_Ops_Rancher_Fleet_Devtron_Report.md`
- `docs/architecture/KUBERNETES_OPS_OPERATIONS.md`
- `tests/test_kubernetes_ops_terminal_safety.py`
- `tests/test_kubernetes_ops_permission_matrix.py`
- `tests/test_kubernetes_ops_action_requests.py`
- `tests/test_kubernetes_ops_logs.py`
- `tests/test_kubernetes_ops_describe.py`
- `requirements-mini.txt`
- `frontend/package.json`
- `web_ui/routing.py`
- `servers/routing.py`

External product references checked on 2026-06-30:

- Freelens official project/docs: graphical Kubernetes IDE for managing and monitoring Kubernetes clusters.
- Rancher Manager docs/API: Rancher remains cluster management/API/RBAC source of truth.
- Fleet docs: Fleet remains GitOps/HelmOps rollout source of truth.
- Devtron docs: Devtron remains AppOps/resource-browser/logs/history/rollback source of truth.
