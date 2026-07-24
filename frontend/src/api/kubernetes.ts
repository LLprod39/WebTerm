import { apiFetch } from "@/lib/api";
// Re-export all DTOs so existing `export * from "@/api/kubernetes"` chains keep working.
export * from "./kubernetesTypes";

import type {
  KubernetesReadinessResponse,
  KubernetesOverviewResponse,
  KubernetesProvider,
  KubernetesProviderPayload,
  KubernetesSyncResult,
  KubernetesProviderProbeResult,
  KubernetesDiagnosisDraftPayload,
  KubernetesDiagnosisDraftResponse,
  KubernetesCluster,
  KubernetesNamespaceSummary,
  KubernetesWorkloadRef,
  KubernetesPodRef,
  KubernetesNetworkRef,
  KubernetesClusterEvent,
  KubernetesWorkloadDescribeResponse,
  KubernetesPodLogsResponse,
  KubernetesFleetBundle,
  KubernetesAppRef,
  KubernetesAuditEvent,
  KubernetesDeepLinkPayload,
  KubernetesProviderKind,
} from "./kubernetesTypes";

export async function fetchKubernetesReadiness() {
  return apiFetch<KubernetesReadinessResponse>("/api/kubernetes/readiness/");
}
export async function fetchKubernetesOverview() {
  return apiFetch<KubernetesOverviewResponse>("/api/kubernetes/overview/");
}
export async function fetchKubernetesProviders() {
  return apiFetch<{ success: boolean; providers: KubernetesProvider[] }>("/api/kubernetes/providers/");
}
export async function createKubernetesProvider(payload: KubernetesProviderPayload) {
  return apiFetch<{ success: boolean; provider: KubernetesProvider }>("/api/kubernetes/providers/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateKubernetesProvider(providerId: number, payload: Partial<KubernetesProviderPayload>) {
  return apiFetch<{ success: boolean; provider: KubernetesProvider }>(`/api/kubernetes/providers/${providerId}/`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export async function deleteKubernetesProvider(providerId: number) {
  return apiFetch<{ success: boolean }>(`/api/kubernetes/providers/${providerId}/`, {
    method: "DELETE",
  });
}
export async function syncKubernetesProvider(providerId: number, payload?: { dry_run?: boolean }) {
  return apiFetch<{ success: boolean; results: KubernetesSyncResult[] }>(`/api/kubernetes/providers/${providerId}/sync/`, {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
}
export async function probeKubernetesProvider(providerId: number) {
  return apiFetch<{ success: boolean; probe: KubernetesProviderProbeResult }>(`/api/kubernetes/providers/${providerId}/probe/`, {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function syncKubernetesProviders(payload?: { dry_run?: boolean; kind?: KubernetesProviderKind }) {
  return apiFetch<{ success: boolean; results: KubernetesSyncResult[] }>("/api/kubernetes/sync/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
}

export async function createKubernetesDiagnosisDraft(payload: KubernetesDiagnosisDraftPayload) {
  return apiFetch<KubernetesDiagnosisDraftResponse>("/api/kubernetes/actions/diagnose/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchKubernetesClusters() {
  return apiFetch<{ success: boolean; clusters: KubernetesCluster[] }>("/api/kubernetes/clusters/");
}

export async function fetchKubernetesCluster(clusterId: string) {
  return apiFetch<{ success: boolean; cluster: KubernetesCluster }>(`/api/kubernetes/clusters/${clusterId}/`);
}

export async function fetchKubernetesClusterNamespaces(clusterId: string) {
  return apiFetch<{ success: boolean; cluster: KubernetesCluster; namespaces: KubernetesNamespaceSummary[] }>(
    `/api/kubernetes/clusters/${clusterId}/namespaces/`,
  );
}

export async function fetchKubernetesClusterWorkloads(clusterId: string) {
  return apiFetch<{ success: boolean; cluster: KubernetesCluster; workloads: KubernetesWorkloadRef[] }>(
    `/api/kubernetes/clusters/${clusterId}/workloads/`,
  );
}

export async function fetchKubernetesClusterPods(clusterId: string) {
  return apiFetch<{ success: boolean; cluster: KubernetesCluster; pods: KubernetesPodRef[] }>(
    `/api/kubernetes/clusters/${clusterId}/pods/`,
  );
}

export async function fetchKubernetesClusterNetwork(clusterId: string) {
  return apiFetch<{ success: boolean; cluster: KubernetesCluster; network_refs: KubernetesNetworkRef[] }>(
    `/api/kubernetes/clusters/${clusterId}/network/`,
  );
}

export async function fetchKubernetesClusterEvents(clusterId: string) {
  return apiFetch<{ success: boolean; cluster: KubernetesCluster; events: KubernetesClusterEvent[] }>(
    `/api/kubernetes/clusters/${clusterId}/events/`,
  );
}

export async function fetchKubernetesWorkloadDescribe(workloadId: string) {
  return apiFetch<KubernetesWorkloadDescribeResponse>(`/api/kubernetes/workloads/${workloadId}/describe/`);
}

export async function fetchKubernetesPodLogs(podId: string, tail = 120) {
  return apiFetch<KubernetesPodLogsResponse>(`/api/kubernetes/pods/${podId}/logs/?tail=${encodeURIComponent(String(tail))}`);
}

export async function fetchKubernetesFleetBundles() {
  return apiFetch<{ success: boolean; bundles: KubernetesFleetBundle[] }>("/api/kubernetes/fleet/bundles/");
}

export async function fetchKubernetesDevtronApps() {
  return apiFetch<{ success: boolean; apps: KubernetesAppRef[] }>("/api/kubernetes/devtron/apps/");
}

export async function fetchKubernetesAudit() {
  return apiFetch<{ success: boolean; events: KubernetesAuditEvent[] }>("/api/kubernetes/audit/");
}

export async function recordKubernetesDeepLink(payload: KubernetesDeepLinkPayload) {
  return apiFetch<{ success: boolean; event: KubernetesAuditEvent }>("/api/kubernetes/audit/deeplink/", {
    method: "POST",
    body: JSON.stringify(payload),
    timeoutMs: 5_000,
  });
}
