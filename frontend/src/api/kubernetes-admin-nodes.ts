import { apiFetch } from "@/lib/api";
import type { KubernetesProviderKind } from "@/api/kubernetes";
import type { KubernetesAdminResourcePolicy, KubernetesAdminResourceTarget } from "@/api/kubernetes-admin";

export interface KubernetesAdminNodeSummary {
  name: string;
  uid: string;
  resource_version: string;
  creation_timestamp: string;
  roles: string[];
  ready: boolean;
  ready_status: string;
  ready_reason: string;
  ready_message: string;
  unschedulable: boolean;
  taints: Array<{ key: string; value: string; effect: string }>;
  taints_truncated: boolean;
  conditions: Array<{ type: string; status: string; reason: string; message: string; last_transition_time: string }>;
  conditions_truncated: boolean;
  capacity: Record<string, string>;
  allocatable: Record<string, string>;
  addresses: Array<{ type: string; address: string }>;
  addresses_truncated: boolean;
  node_info: Record<string, string>;
  label_keys: string[];
  annotation_keys: string[];
  image_count: number;
}

export interface KubernetesAdminNodesResponse {
  success: boolean;
  mode: "admin_read_only" | string;
  operation: "node_list" | string;
  cluster: { id: string; name: string; rancher_cluster_id: string };
  provider: { id: number; name: string; kind: KubernetesProviderKind };
  target: KubernetesAdminResourceTarget;
  path: string;
  nodes: KubernetesAdminNodeSummary[];
  summary: {
    node_count: number;
    raw_node_count: number;
    ready_count: number;
    not_ready_count: number;
    unschedulable_count: number;
    tainted_count: number;
    limit: number;
    truncated: boolean;
  };
  policy: KubernetesAdminResourcePolicy;
}

export interface KubernetesAdminNodesQuery {
  session_id: string;
  limit?: number;
}

export async function fetchKubernetesAdminNodes(clusterId: string, query: KubernetesAdminNodesQuery) {
  const params = new URLSearchParams({ session_id: query.session_id });
  if (query.limit) params.set("limit", String(query.limit));
  return apiFetch<KubernetesAdminNodesResponse>(
    `/api/kubernetes/admin/clusters/${encodeURIComponent(clusterId)}/nodes/?${params.toString()}`,
  );
}
