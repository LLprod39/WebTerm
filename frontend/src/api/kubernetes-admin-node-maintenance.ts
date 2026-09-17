import { apiFetch } from "@/lib/api";
import type { KubernetesProviderKind } from "@/api/kubernetes";
import type { KubernetesAdminResourcePolicy, KubernetesAdminResourceTarget } from "@/api/kubernetes-admin";

export type KubernetesAdminNodeMaintenanceAction = "cordon" | "uncordon" | "drain";

export interface KubernetesAdminNodeMaintenancePayload {
  session_id: string;
  node_name: string;
  reason: string;
  confirmation?: string;
  options?: {
    ignore_daemonsets?: boolean;
    delete_emptydir_data?: boolean;
    force?: boolean;
    grace_period_seconds?: number;
    timeout_seconds?: number;
    max_pods?: number;
  };
}

export interface KubernetesAdminNodeMaintenanceResponse {
  success: boolean;
  mode: "admin_break_glass_node_maintenance" | string;
  operation: "node_cordon" | "node_uncordon" | "node_drain" | string;
  status: string;
  cluster: { id: string; name: string; rancher_cluster_id: string };
  provider: { id: number; name: string; kind: KubernetesProviderKind };
  target: KubernetesAdminResourceTarget;
  path: string;
  action: { id: string; status: string };
  node: string;
  unschedulable?: boolean;
  blocked_reason?: string;
  drain_started?: boolean;
  cordoned?: boolean;
  evictions_started?: boolean;
  evictions_requested?: number;
  evictions?: Array<{ namespace: string; name: string; status: string }>;
  pods_considered?: number;
  pods_skipped?: Record<string, number>;
  drain_options?: Record<string, unknown>;
  policy: KubernetesAdminResourcePolicy & {
    requires_break_glass_session: boolean;
    requires_approval: boolean;
    requires_node_scope: boolean;
    uses_eviction_api?: boolean;
    native_node_maintenance_enabled: boolean;
    node_drain_execution_enabled: boolean;
  };
  resource?: Record<string, unknown>;
}

export async function runKubernetesAdminNodeMaintenance(
  clusterId: string,
  action: KubernetesAdminNodeMaintenanceAction,
  payload: KubernetesAdminNodeMaintenancePayload,
) {
  return apiFetch<KubernetesAdminNodeMaintenanceResponse>(
    `/api/kubernetes/admin/clusters/${encodeURIComponent(clusterId)}/nodes/${action}/`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}
