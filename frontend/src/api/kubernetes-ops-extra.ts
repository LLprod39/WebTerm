/** Extra Kubernetes Ops APIs: metrics snapshots + Helm ownership. */
import { apiFetch } from "@/lib/api";

export interface KubernetesMetricItem {
  name: string;
  namespace?: string;
  usage_normalized?: {
    cpu_millicores?: number | null;
    memory_bytes?: number | null;
  };
  container_count?: number;
  [key: string]: unknown;
}

export interface KubernetesMetricsSummary {
  scope: "nodes" | "pods" | string;
  item_count: number;
  raw_item_count: number;
  container_count: number;
  total_cpu_millicores: number;
  total_memory_bytes: number;
  limit: number;
  truncated: boolean;
}

export interface KubernetesMetricsResponse {
  success: boolean;
  summary?: KubernetesMetricsSummary;
  items?: KubernetesMetricItem[];
  error?: string;
  code?: string;
}

export interface KubernetesHelmRelease {
  release_name: string;
  namespace: string;
  cluster_id?: string;
  cluster_name?: string;
  primary_owner?: string;
  owners?: string[];
  workload_count?: number;
  app_count?: number;
  conflict?: boolean;
  guarded?: boolean;
  health?: string;
  [key: string]: unknown;
}

export interface KubernetesHelmReleasesResponse {
  success: boolean;
  mode?: string;
  summary?: Record<string, unknown>;
  items?: KubernetesHelmRelease[];
  policy?: Record<string, unknown>;
  error?: string;
  code?: string;
}

export async function fetchKubernetesAdminMetrics(
  clusterId: string,
  query: { session_id: string; scope?: "nodes" | "pods"; namespace?: string; limit?: number },
) {
  const params = new URLSearchParams();
  params.set("session_id", query.session_id);
  params.set("scope", query.scope || "nodes");
  if (query.namespace) params.set("namespace", query.namespace);
  if (query.limit) params.set("limit", String(query.limit));
  return apiFetch<KubernetesMetricsResponse>(
    `/api/kubernetes/admin/clusters/${encodeURIComponent(clusterId)}/metrics/?${params.toString()}`,
  );
}

export async function fetchKubernetesHelmReleases(query: {
  cluster_id?: string;
  namespace?: string;
  owner?: string;
  limit?: number;
} = {}) {
  const params = new URLSearchParams();
  if (query.cluster_id) params.set("cluster_id", query.cluster_id);
  if (query.namespace) params.set("namespace", query.namespace);
  if (query.owner) params.set("owner", query.owner);
  if (query.limit) params.set("limit", String(query.limit));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<KubernetesHelmReleasesResponse>(`/api/kubernetes/helm/releases/${suffix}`);
}

export function formatMillicores(value: number | null | undefined): string {
  const n = Number(value || 0);
  if (n >= 1000) return `${(n / 1000).toFixed(2)} CPU`;
  return `${Math.round(n)} mCPU`;
}

export function formatBytes(value: number | null | undefined): string {
  const n = Number(value || 0);
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(2)} GiB`;
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1)} MiB`;
  if (n >= 1024) return `${(n / 1024).toFixed(0)} KiB`;
  return `${n} B`;
}
