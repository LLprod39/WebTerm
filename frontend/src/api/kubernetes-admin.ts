import { apiFetch } from "@/lib/api";
import type { KubernetesProviderKind } from "@/api/kubernetes";
import type { KubernetesAdminResourceDiscoveryResponse } from "@/api/kubernetes-admin-discovery";

export type {
  KubernetesAdminApiResourceCatalogItem,
  KubernetesAdminCrdCatalogItem,
  KubernetesAdminDiscoverySection,
  KubernetesAdminResourceCatalogGroup,
  KubernetesAdminResourceCatalogItem,
  KubernetesAdminResourceCatalogSection,
  KubernetesAdminResourceDiscoveryResponse,
} from "@/api/kubernetes-admin-discovery";

export interface KubernetesAccessPolicy {
  can_read?: boolean;
  can_admin_read?: boolean;
  can_live_resource_get?: boolean;
  can_live_resource_watch?: boolean;
  can_view_full_yaml?: boolean;
  can_stream_logs?: boolean;
  can_admin_write?: boolean;
  can_dry_run_apply?: boolean;
  can_apply_yaml?: boolean;
  can_patch?: boolean;
  can_scale?: boolean;
  can_restart?: boolean;
  can_delete?: boolean;
  can_exec?: boolean;
  can_port_forward?: boolean;
  can_break_glass?: boolean;
  blocked_capabilities?: string[];
  [key: string]: unknown;
}

export type KubernetesAdminSessionMode = "read" | "write" | "break_glass" | string;
export type KubernetesAdminSessionStatus = "pending_approval" | "active" | "expired" | "revoked" | "closed" | string;

export interface KubernetesAdminSession {
  id: string;
  database_id: number;
  mode: KubernetesAdminSessionMode;
  status: KubernetesAdminSessionStatus;
  risk_tier: "low" | "high" | "critical" | string;
  cluster_id: string;
  cluster_name: string;
  provider_id: number | null;
  provider_name: string;
  namespace: string;
  reason: string;
  approval_ref: string;
  approved_by: string;
  approved_at: string | null;
  expires_at: string | null;
  closed_at: string | null;
  allowed_verbs: string[];
  allowed_kinds: string[];
  allowed_namespaces: string[];
  metadata: Record<string, unknown>;
  created_by: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface KubernetesAdminSessionPayload {
  mode: KubernetesAdminSessionMode;
  cluster_id?: string;
  namespace?: string;
  reason?: string;
  ttl_minutes?: number;
  allowed_kinds?: string[];
  allowed_namespaces?: string[];
}

export interface KubernetesAdminSessionClosePayload {
  reason?: string;
}

export interface KubernetesAdminAction {
  id: string;
  database_id: number;
  session_id: string;
  verb: string;
  status: string;
  cluster_id: string;
  cluster_name: string;
  namespace: string;
  resource_api_version: string;
  resource_kind: string;
  resource_name: string;
  request_payload_sanitized: Record<string, unknown>;
  diff_summary: Record<string, unknown>;
  response_summary: Record<string, unknown>;
  exit_code: number | null;
  created_by: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface KubernetesAdminActionQuery {
  session_id?: string;
  cluster_id?: string;
  verb?: string;
  status?: string;
  limit?: number;
  all?: boolean;
}

export interface KubernetesAdminActionTimelineEvent {
  id: number;
  action: string;
  username: string;
  provider: string;
  cluster: string;
  payload: Record<string, unknown>;
  created_at: string | null;
}

export interface KubernetesAdminActionReport {
  action: KubernetesAdminAction;
  session: KubernetesAdminSession;
  timeline: KubernetesAdminActionTimelineEvent[];
  summary: {
    action_id: string;
    session_id: string;
    verb: string;
    status: string;
    timeline_event_count: number;
    has_action_audit_event: boolean;
  };
}

export interface KubernetesAdminResourceTarget {
  api_version: string;
  kind: string;
  resource: string;
  namespace: string;
  name: string;
}

export interface KubernetesAdminResourcePolicy {
  mutates_state: boolean;
  requires_active_admin_session: boolean;
  blocked_actions: string[];
}

export interface KubernetesAdminDryRunPolicy extends KubernetesAdminResourcePolicy {
  requires_write_session: boolean;
  server_side_dry_run: boolean;
}

export interface KubernetesAdminPodLogsPolicy extends KubernetesAdminResourcePolicy {
  streaming: boolean;
  source: string;
  requested_tail_lines: number;
  max_tail_lines: number;
}

export interface KubernetesAdminOwnershipEntity {
  id?: string;
  name?: string;
  namespace?: string;
  kind?: string;
  owner?: string;
  team?: string;
  health?: string;
  version?: string;
  status?: string;
  source?: string;
  target?: string;
  labels?: Record<string, unknown>;
  links?: Record<string, unknown>;
  [key: string]: unknown;
}

export interface KubernetesAdminOwnershipContext {
  owner: string;
  confidence: string;
  change_path: string;
  direct_apply_policy: string;
  current_mode: string;
  warnings: string[];
  evidence: string[];
  workload?: KubernetesAdminOwnershipEntity | null;
  app?: KubernetesAdminOwnershipEntity | null;
  fleet_bundle?: KubernetesAdminOwnershipEntity | null;
}

export interface KubernetesAdminOwnershipSummary {
  owners: Record<string, number>;
  guarded_items: number;
  total: number;
}

export type KubernetesAdminResourceItem = Record<string, unknown> & {
  webterm_ownership?: KubernetesAdminOwnershipContext;
};

export interface KubernetesAdminResourceListResponse {
  success: boolean;
  mode: "admin_read_only" | string;
  operation: "resource_list" | "resource_get" | string;
  cluster: { id: string; name: string; rancher_cluster_id: string };
  provider: { id: number; name: string; kind: KubernetesProviderKind };
  target: KubernetesAdminResourceTarget;
  path: string;
  policy: KubernetesAdminResourcePolicy;
  items?: KubernetesAdminResourceItem[];
  item_count?: number;
  truncated?: boolean;
  resource?: Record<string, unknown>;
  redacted?: boolean;
  ownership?: KubernetesAdminOwnershipContext;
  ownership_summary?: KubernetesAdminOwnershipSummary;
}

export interface KubernetesAdminResourceYamlResponse extends KubernetesAdminResourceListResponse {
  operation: "resource_yaml" | string;
  resource: Record<string, unknown>;
  redacted: boolean;
}

export interface KubernetesAdminResourceEvent {
  name: string;
  namespace: string;
  type: string;
  reason: string;
  message: string;
  source: Record<string, unknown>;
  reporting_controller: string;
  reporting_instance: string;
  involved_object: Record<string, unknown>;
  count: number;
  first_timestamp: string;
  last_timestamp: string;
  event_time: string;
  resource_version: string;
  redacted: boolean;
}

export interface KubernetesAdminResourceEventsSection {
  available: boolean;
  requested: boolean;
  path?: string;
  field_selector?: string;
  limit?: number;
  events: KubernetesAdminResourceEvent[];
  event_count: number;
  truncated: boolean;
  redacted: boolean;
  source?: string;
  error?: Record<string, unknown>;
}

export interface KubernetesAdminResourceDetailResponse extends KubernetesAdminResourceYamlResponse {
  operation: "resource_detail" | string;
  paths: { resource: string; events: string };
  describe: Record<string, unknown>;
  events: KubernetesAdminResourceEventsSection;
}

export type KubernetesAdminSchemaValidationIssue = { path: string; code: string; expected: string; actual: string };

export type KubernetesAdminSchemaValidationResult = {
  status: "valid" | "invalid" | "schema_unavailable" | string; errors: KubernetesAdminSchemaValidationIssue[];
  warnings: string[]; checked_paths: string[]; unsupported_keywords: string[]; error_count: number; max_errors: number;
};

export interface KubernetesAdminSchemaValidationResponse {
  success: boolean; mode: "admin_write_preview" | string; operation: "schema_validate" | string; mutates_state: boolean;
  cluster: { id: string; name: string; rancher_cluster_id: string };
  provider: { id: number; name: string; kind: KubernetesProviderKind };
  target: KubernetesAdminResourceTarget; path: string; schema_available: boolean; schema_source: Record<string, unknown>;
  validation: KubernetesAdminSchemaValidationResult; valid: boolean; redacted: boolean;
  submitted_summary: Record<string, unknown>; action: { id: string; status: string };
  policy: KubernetesAdminDryRunPolicy & { requires_approved_session: boolean };
}

export interface KubernetesAdminPodLogsResponse {
  success: boolean;
  mode: "admin_read_only" | string;
  operation: "pod_logs_snapshot" | string;
  cluster: { id: string; name: string; rancher_cluster_id: string };
  provider: { id: number; name: string; kind: KubernetesProviderKind };
  target: KubernetesAdminResourceTarget & { container?: string };
  path: string;
  available: boolean;
  source: "not_configured" | "provider_snapshot" | "provider_error" | string;
  lines: string[];
  line_count: number;
  truncated: boolean;
  message: string;
  policy: KubernetesAdminPodLogsPolicy;
}

export interface KubernetesAdminResourceWatchEvent {
  type: string;
  object: KubernetesAdminResourceItem;
  resource_version: string;
  redacted: boolean;
}

export interface KubernetesAdminResourceWatchResponse {
  success: boolean;
  mode: "admin_read_only" | string;
  operation: "resource_watch_preview" | string;
  cluster: { id: string; name: string; rancher_cluster_id: string };
  provider: { id: number; name: string; kind: KubernetesProviderKind };
  target: KubernetesAdminResourceTarget;
  path: string;
  available: boolean;
  source: "provider_watch_preview" | "provider_error" | string;
  events: KubernetesAdminResourceWatchEvent[];
  event_count: number;
  truncated: boolean;
  latest_resource_version: string;
  message: string;
  policy: KubernetesAdminResourcePolicy & {
    streaming: boolean;
    future_stream_transport: string;
    max_events: number;
    requested_limit: number;
    timeout_seconds: number;
  };
}

export interface KubernetesAdminCrdResponse extends KubernetesAdminResourceListResponse {
  operation: "crd_list" | string;
  items: KubernetesAdminResourceItem[];
  item_count: number;
}

export interface KubernetesAdminResourceQuery {
  session_id: string;
  api_version?: string;
  kind?: string;
  resource?: string;
  namespace?: string;
  name?: string;
}

export interface KubernetesAdminResourceDetailQuery extends KubernetesAdminResourceQuery {
  include_events?: boolean;
  event_limit?: number;
  include_managed_fields?: boolean;
}

export type KubernetesAdminSchemaValidatePayload = {
  session_id: string; manifest?: Record<string, unknown>; manifest_yaml?: string; namespace?: string; resource?: string;
};

export interface KubernetesAdminPodLogsQuery {
  session_id: string;
  namespace: string;
  pod: string;
  tail?: number;
  container?: string;
}

export interface KubernetesAdminResourceWatchQuery extends KubernetesAdminResourceQuery {
  resource_version?: string;
  limit?: number;
  timeout_seconds?: number;
}

export async function fetchKubernetesAdminSessions() {
  return apiFetch<{ success: boolean; sessions: KubernetesAdminSession[] }>("/api/kubernetes/admin/sessions/");
}

export async function createKubernetesAdminSession(payload: KubernetesAdminSessionPayload) {
  return apiFetch<{ success: boolean; session: KubernetesAdminSession }>("/api/kubernetes/admin/sessions/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function closeKubernetesAdminSession(sessionId: string, payload: KubernetesAdminSessionClosePayload = {}) {
  return apiFetch<{ success: boolean; session: KubernetesAdminSession }>(
    `/api/kubernetes/admin/sessions/${encodeURIComponent(sessionId)}/close/`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function fetchKubernetesAdminActions(query: KubernetesAdminActionQuery = {}) {
  const params = new URLSearchParams();
  if (query.session_id) params.set("session_id", query.session_id);
  if (query.cluster_id) params.set("cluster_id", query.cluster_id);
  if (query.verb) params.set("verb", query.verb);
  if (query.status) params.set("status", query.status);
  if (query.limit) params.set("limit", String(query.limit));
  if (query.all) params.set("all", "1");
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return apiFetch<{ success: boolean; actions: KubernetesAdminAction[]; count: number; limit: number }>(
    `/api/kubernetes/admin/actions/${suffix}`,
  );
}

export async function fetchKubernetesAdminAction(actionId: string) {
  return apiFetch<{ success: boolean; action: KubernetesAdminAction }>(
    `/api/kubernetes/admin/actions/${encodeURIComponent(actionId)}/`,
  );
}

export async function fetchKubernetesAdminActionReport(actionId: string) {
  return apiFetch<{ success: boolean; report: KubernetesAdminActionReport }>(
    `/api/kubernetes/admin/actions/${encodeURIComponent(actionId)}/report/`,
  );
}

export async function fetchKubernetesAdminDiscovery(clusterId: string, sessionId: string) {
  const params = new URLSearchParams({ session_id: sessionId });
  return apiFetch<KubernetesAdminResourceDiscoveryResponse>(
    `/api/kubernetes/admin/clusters/${encodeURIComponent(clusterId)}/discovery/?${params.toString()}`,
  );
}

export async function fetchKubernetesAdminResources(clusterId: string, query: KubernetesAdminResourceQuery) {
  const params = adminResourceParams(query);
  return apiFetch<KubernetesAdminResourceListResponse>(
    `/api/kubernetes/admin/clusters/${encodeURIComponent(clusterId)}/resources/?${params.toString()}`,
  );
}

export async function fetchKubernetesAdminResourceYaml(clusterId: string, query: KubernetesAdminResourceQuery) {
  const params = adminResourceParams(query);
  return apiFetch<KubernetesAdminResourceYamlResponse>(
    `/api/kubernetes/admin/clusters/${encodeURIComponent(clusterId)}/yaml/?${params.toString()}`,
  );
}

export async function fetchKubernetesAdminResourceDetail(clusterId: string, query: KubernetesAdminResourceDetailQuery) {
  const params = adminResourceParams(query);
  if (query.include_events !== undefined) params.set("include_events", query.include_events ? "1" : "0");
  if (query.event_limit) params.set("event_limit", String(query.event_limit));
  if (query.include_managed_fields !== undefined) {
    params.set("include_managed_fields", query.include_managed_fields ? "1" : "0");
  }
  return apiFetch<KubernetesAdminResourceDetailResponse>(
    `/api/kubernetes/admin/clusters/${encodeURIComponent(clusterId)}/resources/detail/?${params.toString()}`,
  );
}

export async function validateKubernetesAdminManifestSchema(
  clusterId: string,
  payload: KubernetesAdminSchemaValidatePayload,
) {
  return apiFetch<KubernetesAdminSchemaValidationResponse>(
    `/api/kubernetes/admin/clusters/${encodeURIComponent(clusterId)}/resources/schema-validate/`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function fetchKubernetesAdminCrds(clusterId: string, sessionId: string) {
  const params = new URLSearchParams({ session_id: sessionId });
  return apiFetch<KubernetesAdminCrdResponse>(
    `/api/kubernetes/admin/clusters/${encodeURIComponent(clusterId)}/crds/?${params.toString()}`,
  );
}

export async function fetchKubernetesAdminPodLogs(clusterId: string, query: KubernetesAdminPodLogsQuery) {
  const params = new URLSearchParams({
    session_id: query.session_id,
    namespace: query.namespace,
    pod: query.pod,
    tail: String(query.tail || 120),
  });
  if (query.container) params.set("container", query.container);
  return apiFetch<KubernetesAdminPodLogsResponse>(
    `/api/kubernetes/admin/clusters/${encodeURIComponent(clusterId)}/logs/?${params.toString()}`,
  );
}

export async function fetchKubernetesAdminResourceWatch(clusterId: string, query: KubernetesAdminResourceWatchQuery) {
  const params = adminResourceParams(query);
  params.set("limit", String(query.limit || 20));
  params.set("timeout_seconds", String(query.timeout_seconds || 10));
  if (query.resource_version) params.set("resource_version", query.resource_version);
  return apiFetch<KubernetesAdminResourceWatchResponse>(
    `/api/kubernetes/admin/clusters/${encodeURIComponent(clusterId)}/watch/?${params.toString()}`,
  );
}

function adminResourceParams(query: KubernetesAdminResourceQuery) {
  const params = new URLSearchParams({ session_id: query.session_id });
  if (query.api_version) params.set("api_version", query.api_version);
  if (query.kind) params.set("kind", query.kind);
  if (query.resource) params.set("resource", query.resource);
  if (query.namespace) params.set("namespace", query.namespace);
  if (query.name) params.set("name", query.name);
  return params;
}

export * from "@/api/kubernetes-admin-actions";
export * from "@/api/kubernetes-admin-nodes";
export * from "@/api/kubernetes-admin-node-maintenance";
