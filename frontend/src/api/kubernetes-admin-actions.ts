import { apiFetch } from "@/lib/api";
import type { KubernetesProviderKind } from "@/api/kubernetes";
import type {
  KubernetesAdminOwnershipContext,
  KubernetesAdminResourcePolicy,
  KubernetesAdminResourceTarget,
} from "@/api/kubernetes-admin";

export interface KubernetesAdminDryRunApplyPayload {
  session_id: string;
  manifest_yaml?: string;
  manifest?: Record<string, unknown>;
  namespace?: string;
  resource?: string;
}

export interface KubernetesAdminDryRunDiffSummary {
  available: boolean;
  redacted: boolean;
  submitted_top_level_fields: string[];
  server_top_level_fields: string[];
  changed_top_level_fields: string[];
  server_added_top_level_fields: string[];
  server_removed_top_level_fields: string[];
}

export interface KubernetesAdminDryRunApplyResponse {
  success: boolean;
  mode: "admin_write_preview" | string;
  operation: "dry_run_apply" | string;
  dry_run: true;
  mutates_state: false;
  cluster: { id: string; name: string; rancher_cluster_id: string };
  provider: { id: number; name: string; kind: KubernetesProviderKind };
  target: KubernetesAdminResourceTarget;
  path: string;
  resource: Record<string, unknown>;
  submitted: Record<string, unknown>;
  redacted: boolean;
  diff_summary: KubernetesAdminDryRunDiffSummary;
  ownership: KubernetesAdminOwnershipContext;
  action: { id: string; status: string };
  policy: KubernetesAdminResourcePolicy & {
    requires_write_session: boolean;
    server_side_dry_run: boolean;
  };
}

export interface KubernetesAdminApplyPayload {
  session_id: string;
  dry_run_action_id: string;
  reason: string;
  manifest_yaml?: string;
  manifest?: Record<string, unknown>;
  namespace?: string;
  resource?: string;
}

export interface KubernetesAdminApplyResponse {
  success: boolean;
  mode: "admin_write_apply" | string;
  operation: "apply" | string;
  dry_run: false;
  mutates_state: true;
  cluster: { id: string; name: string; rancher_cluster_id: string };
  provider: { id: number; name: string; kind: KubernetesProviderKind };
  target: KubernetesAdminResourceTarget;
  path: string;
  resource: Record<string, unknown>;
  redacted: boolean;
  ownership: KubernetesAdminOwnershipContext;
  dry_run_proof: { id: string; created_at: string };
  action: { id: string; status: string };
  policy: KubernetesAdminResourcePolicy & {
    requires_write_session: boolean;
    requires_dry_run_proof: boolean;
  };
}

export interface KubernetesAdminScalePayload {
  session_id: string;
  api_version?: string;
  kind: string;
  namespace: string;
  name: string;
  replicas: number;
  reason: string;
  resource?: string;
}

export interface KubernetesAdminRestartPayload {
  session_id: string;
  api_version?: string;
  kind: string;
  namespace: string;
  name: string;
  reason: string;
  resource?: string;
}

export interface KubernetesAdminPatchPayload {
  session_id: string;
  api_version?: string;
  kind: string;
  namespace?: string;
  name: string;
  resource?: string;
  patch_type?: "merge" | "strategic" | "json";
  patch: Record<string, unknown> | Array<Record<string, unknown>>;
  reason: string;
}

export interface KubernetesAdminPatchResponse {
  success: boolean;
  mode: "admin_write_patch" | string;
  operation: "patch" | string;
  mutates_state: true;
  cluster: { id: string; name: string; rancher_cluster_id: string };
  provider: { id: number; name: string; kind: KubernetesProviderKind };
  target: KubernetesAdminResourceTarget;
  path: string;
  patch_type: string;
  resource: Record<string, unknown>;
  redacted: boolean;
  ownership: KubernetesAdminOwnershipContext;
  action: { id: string; status: string };
  policy: KubernetesAdminResourcePolicy & {
    requires_write_session: boolean;
    requires_reason: boolean;
  };
}

export interface KubernetesAdminDeletePayload {
  session_id: string;
  api_version?: string;
  kind: string;
  namespace?: string;
  name: string;
  resource?: string;
  confirmation: string;
  propagation_policy?: "Foreground" | "Background" | "Orphan" | "";
  reason: string;
}

export interface KubernetesAdminDeleteResponse {
  success: boolean;
  mode: "admin_write_delete" | string;
  operation: "delete" | string;
  mutates_state: true;
  cluster: { id: string; name: string; rancher_cluster_id: string };
  provider: { id: number; name: string; kind: KubernetesProviderKind };
  target: KubernetesAdminResourceTarget;
  path: string;
  confirmation: { matched: boolean; expected: string };
  propagation_policy: string;
  result: Record<string, unknown>;
  action: { id: string; status: string };
  policy: KubernetesAdminResourcePolicy & {
    requires_write_session: boolean;
    requires_reason: boolean;
    requires_exact_confirmation: boolean;
    protected_namespaces: string[];
    blocked_kinds: string[];
  };
}

export interface KubernetesAdminWorkloadActionResponse {
  success: boolean;
  mode: "admin_write_workload" | string;
  operation: "scale" | "restart" | string;
  mutates_state: true;
  cluster: { id: string; name: string; rancher_cluster_id: string };
  provider: { id: number; name: string; kind: KubernetesProviderKind };
  target: KubernetesAdminResourceTarget;
  path: string;
  action: { id: string; status: string };
  policy: KubernetesAdminResourcePolicy & { requires_write_session: boolean };
  resource: Record<string, unknown>;
  ownership: KubernetesAdminOwnershipContext;
  replicas?: number;
  restarted_at?: string;
}

export async function dryRunKubernetesAdminApply(clusterId: string, payload: KubernetesAdminDryRunApplyPayload) {
  return apiFetch<KubernetesAdminDryRunApplyResponse>(
    `/api/kubernetes/admin/clusters/${encodeURIComponent(clusterId)}/resources/dry-run-apply/`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function applyKubernetesAdminManifest(clusterId: string, payload: KubernetesAdminApplyPayload) {
  return apiFetch<KubernetesAdminApplyResponse>(
    `/api/kubernetes/admin/clusters/${encodeURIComponent(clusterId)}/resources/apply/`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function patchKubernetesAdminResource(clusterId: string, payload: KubernetesAdminPatchPayload) {
  return apiFetch<KubernetesAdminPatchResponse>(
    `/api/kubernetes/admin/clusters/${encodeURIComponent(clusterId)}/resources/patch/`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function deleteKubernetesAdminResource(clusterId: string, payload: KubernetesAdminDeletePayload) {
  return apiFetch<KubernetesAdminDeleteResponse>(
    `/api/kubernetes/admin/clusters/${encodeURIComponent(clusterId)}/resources/delete/`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function scaleKubernetesAdminWorkload(clusterId: string, payload: KubernetesAdminScalePayload) {
  return apiFetch<KubernetesAdminWorkloadActionResponse>(
    `/api/kubernetes/admin/clusters/${encodeURIComponent(clusterId)}/resources/scale/`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function restartKubernetesAdminWorkload(clusterId: string, payload: KubernetesAdminRestartPayload) {
  return apiFetch<KubernetesAdminWorkloadActionResponse>(
    `/api/kubernetes/admin/clusters/${encodeURIComponent(clusterId)}/resources/restart/`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}
