import { api } from "./client";
export type KubeData = Record<string, unknown>;
export interface KubeItem extends KubeData {
  id: string;
  name: string;
  namespace?: string;
  cluster_id?: string;
  cluster_name?: string;
  health?: string;
  kind?: string;
  last_sync_at?: string;
  sync_status?: string;
}
export interface KubeCluster extends KubeItem {
  environment: string;
  provider: string;
  nodes_ready: number;
  nodes_total: number;
  namespaces: number;
  workloads: number;
}
export interface KubeProvider extends KubeData {
  id: number;
  name: string;
  kind: "rancher" | "devtron";
  base_url: string;
  enabled: boolean;
  auth_mode: string;
  has_secret_ref: boolean;
  secret_storage: string;
  labels: KubeData;
  last_sync_at: string | null;
  last_error: string;
  sync_status: string;
}
export interface KubeWorkflow {
  id: string;
  mode: string;
  available: boolean;
  requestable: boolean;
  mutates_state: boolean;
  blocked_reason: string;
  requirements: string[];
  transport_enabled?: boolean;
  runtime_enabled?: boolean;
}
export interface KubeCapabilities {
  modes: { id: string; active: boolean; granted: boolean; purpose: string }[];
  workflows: KubeWorkflow[];
}
export interface KubeSession extends KubeData {
  id: string;
  mode: "read" | "write" | "break_glass";
  status: string;
  cluster_id: string;
  cluster_name: string;
  namespace: string;
  reason: string;
  approval_ref: string;
  approved_by: string;
  expires_at: string;
  allowed_verbs: string[];
  allowed_kinds: string[];
  allowed_namespaces: string[];
  created_by: string;
  created_at: string;
  post_review_required: boolean;
  post_review_status: string;
}
export interface KubeAction extends KubeData {
  id: string;
  session_id: string;
  verb: string;
  status: string;
  cluster_id: string;
  cluster_name: string;
  namespace: string;
  resource_kind: string;
  resource_name: string;
  created_by: string;
  created_at: string;
  post_review_required: boolean;
  post_review_status: string;
  request_payload_sanitized: KubeData;
  diff_summary: KubeData;
  response_summary: KubeData;
}
export interface KubeRecording extends KubeData {
  id: string;
  session_id: string;
  action_id: string;
  operation: string;
  status: string;
  cluster_name: string;
  namespace: string;
  resource_name: string;
  event_count: number;
  transcript_stored: boolean;
  events?: KubeData[];
  created_at: string;
}
export interface KubeResource extends KubeData {
  apiVersion: string;
  kind: string;
  metadata: {
    name: string;
    namespace?: string;
    uid?: string;
    creationTimestamp?: string;
  };
  summary: KubeData;
}
export interface ResourceType {
  id: string;
  api_version: string;
  kind: string;
  resource: string;
  namespaced: boolean;
  cluster_available: boolean;
  ui_group: string;
  verbs: string[];
}
export interface ResourceTarget {
  api_version: string;
  kind: string;
  resource: string;
  namespace: string;
  name: string;
}
const base = "/api/kubernetes/";
export function kubeQuery(
  values: Record<string, string | number | boolean | undefined>,
) {
  const q = new URLSearchParams();
  Object.entries(values).forEach(([k, v]) => {
    if (v !== undefined && v !== "") q.set(k, String(v));
  });
  return q.toString() ? "?" + q.toString() : "";
}
const enc = encodeURIComponent;
export const kubernetesApi = {
  clusters: () => api.get<{ clusters: KubeCluster[] }>(base + "clusters/"),
  cluster: (id: string) =>
    api.get<{ cluster: KubeCluster }>(base + `clusters/${enc(id)}/`),
  inventory: (id: string, kind: string) =>
    api.get<KubeData>(base + `clusters/${enc(id)}/${kind}/`),
  namespace: (cluster: string, id: string) =>
    api.get<KubeData>(base + `clusters/${enc(cluster)}/namespaces/${enc(id)}/`),
  detail: (kind: string, id: string) =>
    api.get<KubeData>(base + `${kind}/${enc(id)}/`),
  podLogs: (id: string, tail = 200) =>
    api.get<KubeData>(base + `pods/${enc(id)}/logs/?tail=${tail}`),
  readiness: () => api.get<KubeData>(base + "readiness/"),
  capabilities: () => api.get<KubeCapabilities>(base + "capabilities/"),
  providers: () => api.get<{ providers: KubeProvider[] }>(base + "providers/"),
  saveProvider: (id: number | undefined, data: KubeData) =>
    id
      ? api.patch<{ provider: KubeProvider }>(base + `providers/${id}/`, data)
      : api.post<{ provider: KubeProvider }>(base + "providers/", data),
  deleteProvider: (id: number) => api.delete(base + `providers/${id}/`),
  probeProvider: (id: number) =>
    api.post<KubeData>(base + `providers/${id}/probe/`, {}),
  syncProvider: (id: number, dry_run = false) =>
    api.post<KubeData>(base + `providers/${id}/sync/`, { dry_run }),
  sessions: (all = false) =>
    api.get<{ sessions: KubeSession[] }>(
      base + "admin/sessions/" + kubeQuery({ all }),
    ),
  session: (id: string) =>
    api.get<{ session: KubeSession }>(base + `admin/sessions/${enc(id)}/`),
  createSession: (data: KubeData) =>
    api.post<{ session: KubeSession }>(base + "admin/sessions/", data),
  sessionAction: (id: string, action: string, data: KubeData) =>
    api.post<KubeData>(base + `admin/sessions/${enc(id)}/${action}/`, data),
  discovery: (cluster: string, session: string) =>
    api.get<{
      resource_catalog: {
        items: ResourceType[];
        status: string;
        truncated: boolean;
      };
    }>(
      base +
        `admin/clusters/${enc(cluster)}/discovery/` +
        kubeQuery({ session_id: session }),
    ),
  resources: (
    cluster: string,
    query: Record<string, string | number | boolean | undefined>,
  ) =>
    api.get<{
      items: KubeResource[];
      continue_token: string;
      truncated: boolean;
      item_count: number;
    }>(base + `admin/clusters/${enc(cluster)}/resources/` + kubeQuery(query)),
  resourceRead: (
    cluster: string,
    action: string,
    query: Record<string, string | number | boolean | undefined>,
  ) =>
    api.get<KubeData>(
      base + `admin/clusters/${enc(cluster)}/${action}/` + kubeQuery(query),
    ),
  resourceWrite: (cluster: string, action: string, data: KubeData) =>
    api.post<KubeData>(
      base + `admin/clusters/${enc(cluster)}/resources/${action}/`,
      data,
    ),
  nodeAction: (cluster: string, action: string, data: KubeData) =>
    api.post<KubeData>(
      base + `admin/clusters/${enc(cluster)}/nodes/${action}/`,
      data,
    ),
  actions: (
    query: Record<string, string | number | boolean | undefined> = {},
  ) =>
    api.get<{ actions: KubeAction[] }>(
      base + "admin/actions/" + kubeQuery({ limit: 100, ...query }),
    ),
  actionReport: (id: string) =>
    api.get<{ report: KubeData }>(base + `admin/actions/${enc(id)}/report/`),
  reviewAction: (id: string, data: KubeData) =>
    api.post<{ action: KubeAction }>(
      base + `admin/actions/${enc(id)}/review/`,
      data,
    ),
  recordings: (
    query: Record<string, string | number | boolean | undefined> = {},
  ) =>
    api.get<{ recordings: KubeRecording[] }>(
      base + "admin/recordings/" + kubeQuery({ limit: 100, ...query }),
    ),
  recording: (id: string) =>
    api.get<{ recording: KubeRecording }>(
      base + `admin/recordings/${enc(id)}/?event_limit=500`,
    ),
  audit: () => api.get<KubeData>(base + "audit/"),
};
