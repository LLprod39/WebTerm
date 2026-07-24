import type { StudioPipelineDraftSession } from "@/lib/studioPipelineDraftsApi";
import type { KubernetesAccessPolicy } from "@/api/kubernetes-admin";

export type KubernetesProviderKind = "rancher" | "devtron" | string;
export type KubernetesAuthMode = "none" | "secret_ref" | "oidc" | string;
export type KubernetesHealth = "healthy" | "warning" | "degraded" | "unknown" | string;
export type KubernetesAppOwner = "fleet" | "devtron" | "external" | string;
export type KubernetesWorkloadKind = "deployment" | "statefulset" | "daemonset" | "cronjob" | "job" | "pod" | "unknown" | string;
export type KubernetesNetworkKind = "service" | "ingress" | string;
export type KubernetesFleetStatus = "ready" | "rolling" | "degraded" | "paused" | "unknown" | string;
export type KubernetesReadinessStatus = "ready" | "configured" | "not_configured" | string;
export type KubernetesReadinessCheckStatus = "ready" | "missing" | "manual" | string;
export interface KubernetesReadinessCheck {
  id: string;
  status: KubernetesReadinessCheckStatus;
  detail: string;
  required: boolean;
}
export interface KubernetesWorkerState {
  worker_kind: string;
  worker_key: string;
  status: "missing" | "running" | "idle" | "error" | "stopped" | string;
  is_stale: boolean;
  hostname: string;
  pid: number | null;
  command?: string;
  heartbeat_at: string | null;
  lease_expires_at: string | null;
  last_started_at: string | null;
  last_stopped_at: string | null;
  last_cycle_started_at: string | null;
  last_cycle_finished_at: string | null;
  last_summary: Record<string, unknown>;
  last_error: string;
}

export interface KubernetesReadinessResponse {
  success: boolean;
  status: KubernetesReadinessStatus;
  ready_for_sidebar: boolean;
  /** Closed-pilot mode: production-only release checks waived when env set. */
  pilot_sidebar?: boolean;
  summary: {
    ready: number;
    missing: number;
    manual: number;
    total: number;
    pilot_sidebar?: boolean;
  };
  checks: KubernetesReadinessCheck[];
  worker_state: KubernetesWorkerState;
  access_model?: Record<string, unknown>;
  access_policy?: KubernetesAccessPolicy;
  identity_runtime?: Record<string, unknown>;
  security_review?: Record<string, unknown>;
  terminal_safety?: Record<string, unknown>;
  operator_docs?: Record<string, unknown>;
}

export interface KubernetesProvider {
  id: number;
  name: string;
  kind: KubernetesProviderKind;
  base_url: string;
  enabled: boolean;
  auth_mode: KubernetesAuthMode;
  has_secret_ref: boolean;
  secret_storage: "none" | "external" | "managed" | string;
  labels: Record<string, unknown>;
  last_sync_at: string | null;
  last_error: string;
  provider_health: "healthy" | "error" | "missing" | "stale" | "disabled" | string;
  sync_status: "fresh" | "error" | "missing" | "stale" | "disabled" | string;
  is_stale: boolean;
  sync_age_seconds: number | null;
  sync_stale_after_seconds: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface KubernetesCluster {
  id: string;
  database_id: number;
  name: string;
  environment: string;
  provider: KubernetesProviderKind | "";
  health: KubernetesHealth;
  nodes_ready: number;
  nodes_total: number;
  namespaces: number;
  workloads: number;
  apps: number;
  fleet_bundles: number;
  devtron_apps: number;
  labels: Record<string, unknown>;
  links: Record<string, unknown>;
  last_sync_at: string | null;
  sync_status: "fresh" | "missing" | "stale" | string;
  is_stale: boolean;
  sync_age_seconds: number | null;
  sync_stale_after_seconds: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface KubernetesAppRef {
  id: string;
  database_id: number;
  name: string;
  cluster_id: string;
  cluster_name: string;
  namespace: string;
  environment: string;
  owner: KubernetesAppOwner;
  team: string;
  health: KubernetesHealth;
  version: string;
  links: Record<string, unknown>;
  labels: Record<string, unknown>;
  last_sync_at: string | null;
  sync_status: "fresh" | "missing" | "stale" | string;
  is_stale: boolean;
  sync_age_seconds: number | null;
  sync_stale_after_seconds: number;
}

export interface KubernetesWorkloadRef extends KubernetesAppRef {
  kind: KubernetesWorkloadKind;
  ready: number;
  desired: number;
}

export interface KubernetesFleetBundle {
  id: string;
  database_id: number;
  name: string;
  source: string;
  target: string;
  status: KubernetesFleetStatus;
  ready: number;
  desired: number;
  partitions: Array<Record<string, unknown>>;
  links: Record<string, unknown>;
  labels: Record<string, unknown>;
  last_sync_at: string | null;
  sync_status: "fresh" | "missing" | "stale" | string;
  is_stale: boolean;
  sync_age_seconds: number | null;
  sync_stale_after_seconds: number;
}

export interface KubernetesNamespaceSummary {
  id: string;
  database_id?: number;
  name: string;
  cluster_id?: string;
  cluster_name?: string;
  environment: string;
  health?: KubernetesHealth;
  apps: number;
  workloads?: number;
  healthy: number;
  warning: number;
  degraded: number;
  unknown: number;
  owners: string[];
  teams: string[];
  links?: Record<string, unknown>;
  labels?: Record<string, unknown>;
  last_sync_at: string | null;
}

export interface KubernetesNetworkRef {
  id: string;
  database_id: number;
  cluster_id: string;
  cluster_name: string;
  namespace: string;
  name: string;
  kind: KubernetesNetworkKind;
  environment: string;
  health: KubernetesHealth;
  service_type: string;
  ports: Array<Record<string, unknown> | string | number>;
  hosts: string[];
  endpoints: Array<Record<string, unknown> | string>;
  links: Record<string, unknown>;
  labels: Record<string, unknown>;
  last_sync_at: string | null;
  sync_status: "fresh" | "missing" | "stale" | string;
  is_stale: boolean;
  sync_age_seconds: number | null;
  sync_stale_after_seconds: number;
}

export interface KubernetesPodRef {
  id: string;
  database_id: number;
  cluster_id: string;
  cluster_name: string;
  namespace: string;
  name: string;
  environment: string;
  health: KubernetesHealth;
  phase: string;
  node_name: string;
  pod_ip: string;
  host_ip: string;
  owner_kind: string;
  owner_name: string;
  ready_containers: number;
  total_containers: number;
  restart_count: number;
  images: string[];
  links: Record<string, unknown>;
  labels: Record<string, unknown>;
  last_sync_at: string | null;
  sync_status: "fresh" | "missing" | "stale" | string;
  is_stale: boolean;
  sync_age_seconds: number | null;
  sync_stale_after_seconds: number;
}

export interface KubernetesClusterEvent {
  id: string;
  source: string;
  severity: "info" | "warning" | "error" | string;
  reason: string;
  message: string;
  username: string;
  namespace?: string;
  involved_kind?: string;
  involved_name?: string;
  count?: number;
  payload: Record<string, unknown>;
  created_at: string | null;
}

export interface KubernetesWorkloadDescribePolicy {
  mode: "read_only" | string;
  mutates_state: boolean;
  source: "normalized_inventory" | string;
  blocked_actions: string[];
}

export interface KubernetesManifestPreview {
  apiVersion: string;
  kind: string;
  metadata: {
    name: string;
    namespace: string;
    labels: Record<string, unknown>;
  };
  spec_summary: Record<string, unknown>;
  status_summary: Record<string, unknown>;
}

export interface KubernetesWorkloadDescribeResponse {
  success: boolean;
  target: (KubernetesWorkloadRef | KubernetesAppRef) & { source: "workload" | "app" | string };
  related_events: KubernetesClusterEvent[];
  policy: KubernetesWorkloadDescribePolicy;
  manifest_preview: KubernetesManifestPreview;
}

export interface KubernetesPodLogsPolicy {
  mode: "read_only" | string;
  mutates_state: boolean;
  streaming: boolean;
  source: "rancher_provider_json" | string;
  requested_tail_lines: number;
  max_tail_lines: number;
  blocked_actions: string[];
}

export interface KubernetesPodLogsResponse {
  success: boolean;
  available: boolean;
  source: "not_configured" | "external_link_only" | "provider_snapshot" | "provider_error" | string;
  target: KubernetesPodRef;
  policy: KubernetesPodLogsPolicy;
  provider: { id: number; name: string; kind: KubernetesProviderKind } | null;
  lines: string[];
  line_count: number;
  truncated: boolean;
  message: string;
}

export interface KubernetesAuditEvent {
  id: number;
  action: string;
  username: string;
  provider: string;
  cluster: string;
  payload: Record<string, unknown>;
  created_at: string | null;
}

export interface KubernetesDeepLinkPayload {
  target_type: "provider" | "cluster" | "app" | "workload" | "fleet_bundle" | string;
  target_id?: string | number;
  target_name?: string;
  cluster_id?: string;
  link_key: string;
  url: string;
  provider?: KubernetesProviderKind | "";
}

export interface KubernetesOverviewResponse {
  success: boolean;
  readiness: KubernetesReadinessResponse;
  summary: {
    clusters: number;
    apps: number;
    fleet_rollouts: number;
    incidents: number;
    warnings: number;
    rolling: number;
    paused: number;
    stale: number;
    provider_issues: number;
  };
  providers: KubernetesProvider[];
  clusters: KubernetesCluster[];
  workloads: KubernetesWorkloadRef[];
  apps: KubernetesAppRef[];
  fleet_rollouts: KubernetesFleetBundle[];
}

export interface KubernetesProviderPayload {
  name: string;
  kind: KubernetesProviderKind;
  base_url: string;
  enabled?: boolean;
  auth_mode?: KubernetesAuthMode;
  secret_ref?: string;
  secret_value?: string;
  labels?: Record<string, unknown>;
}

export interface KubernetesSyncResult {
  provider_id: number;
  provider_name: string;
  provider_kind: KubernetesProviderKind;
  success: boolean;
  clusters: number;
  namespaces: number;
  workloads: number;
  pods: number;
  services: number;
  ingresses: number;
  events: number;
  apps: number;
  fleet_bundles: number;
  error: string;
  dry_run: boolean;
}

export interface KubernetesProviderProbeResult {
  provider_id: number;
  provider_name: string;
  provider_kind: KubernetesProviderKind;
  success: boolean;
  status: "ready" | "error" | string;
  path: string;
  item_count: number;
  payload_keys: string[];
  duration_ms: number;
  checked_at: string;
  error: string;
}

export interface KubernetesDiagnosisDraftPayload {
  app_id: string;
}

export interface KubernetesDiagnosisDraftResponse {
  success: boolean;
  draft: StudioPipelineDraftSession;
  target_url: string;
}
