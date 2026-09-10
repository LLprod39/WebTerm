import { api } from "./client";
export interface HealthCheck {
  id: number;
  status: string;
  cpu_percent: number | null;
  memory_percent: number | null;
  disk_percent: number | null;
  load_1m: number | null;
  load_5m: number | null;
  load_15m: number | null;
  memory_used_mb: number | null;
  memory_total_mb: number | null;
  disk_used_gb: number | null;
  disk_total_gb: number | null;
  uptime_seconds: number | null;
  process_count: number | null;
  response_time_ms: number | null;
  is_deep: boolean;
  checked_at: string;
}
export interface Prediction {
  kind: string;
  target: string;
  severity: string;
  eta_days: number | null;
  predicted_for: string | null;
  current_value: number | null;
  threshold: number | null;
  unit: string;
  slope_per_day: number | null;
  confidence: number;
  evidence: Record<string, unknown>;
  server_id: number;
  server_name: string;
}
export interface Certificate {
  id: number;
  server_id: number;
  server_name: string;
  port: number;
  endpoint: string;
  subject: string;
  issuer: string;
  not_after: string | null;
  days_left: number | null;
  sans: string[];
  is_active: boolean;
  changed_at: string | null;
  last_checked_at: string | null;
}
export interface AiInsight {
  id: number;
  kind: string;
  endpoint_key: string;
  server_id: number | null;
  verdict: string;
  content: string;
  error: string;
  model: string;
  created_at: string;
}
export interface InsightServer {
  id: number;
  name: string;
  host: string;
  endpoint_key: string;
  owner: string;
  status: string;
  checked_at: string | null;
  sample_at: string | null;
  has_extended_metrics: boolean;
  health_score: number;
  cpu_percent: number | null;
  cpu_iowait_percent: number | null;
  cpu_steal_percent: number | null;
  cpu_count: number | null;
  load_1m: number | null;
  memory_percent: number | null;
  memory_available_mb: number | null;
  swap_percent: number | null;
  worst_disk: { mount?: string; percent: number } | null;
  net_rx_bps: number | null;
  net_tx_bps: number | null;
  tcp_retrans_per_sec: number | null;
  tcp_established: number | null;
  fd_percent: number | null;
  process_count: number | null;
  zombie_count: number | null;
  journal_err_10m: number | null;
  journal_warn_10m: number | null;
  reboot_required: boolean | null;
  ntp_synchronized: boolean | null;
  uptime_seconds: number | null;
  spark: { cpu: number[]; mem: number[]; disk: number[] };
  predictions: Prediction[];
}
export interface MonitoringAlert {
  id: number;
  server_id: number;
  server_name: string;
  alert_type: string;
  severity: string;
  title: string;
  message: string;
  created_at: string;
  is_resolved: boolean;
  resolved_at: string | null;
  metadata: Record<string, unknown>;
}
export interface Insights {
  generated_at: string;
  cached?: boolean;
  ai: {
    enabled: boolean;
    running: boolean;
    fleet: AiInsight | null;
    by_endpoint: Record<string, AiInsight>;
  };
  summary: {
    servers_total: number;
    healthy: number;
    warning: number;
    critical: number;
    unreachable: number;
    unknown: number;
    fleet_health_score: number;
    fleet_health_worst: number;
    active_alerts: number;
    predictions_total: number;
    predictions_critical: number;
    predictions_warning: number;
    certificates_total: number;
    certificates_expiring_30d: number;
    certificates_changed_7d: number;
  };
  servers: InsightServer[];
  predictions: Prediction[];
  certificates: Certificate[];
  alerts: MonitoringAlert[];
}
export interface WatcherDraft {
  id: number;
  server_id: number;
  server_name: string;
  severity: string;
  recommended_role: string;
  objective: string;
  reasons: string[];
  memory_excerpt: string[];
  status: string;
  acknowledged_at: string | null;
  acknowledged_by: string;
  resolved_at: string | null;
  first_seen_at: string | null;
  last_seen_at: string | null;
  metadata: {
    last_launch_run_id?: number;
    last_launch_agent_id?: number;
    last_launched_at?: string;
    launch_count?: number;
  };
}
export interface Thresholds {
  cpu_warn: number;
  cpu_crit: number;
  mem_warn: number;
  mem_crit: number;
  disk_warn: number;
  disk_crit: number;
}
export interface MonitoringConfig {
  thresholds: Thresholds;
  stats: {
    total_checks: number;
    active_alerts: number;
    last_check_at: string | null;
    monitored_servers: number;
  };
}
export const monitoringExtrasApi = {
  insights: (refresh = false, signal?: AbortSignal) =>
    api.get<Insights>(
      `/servers/api/admin/insights/${refresh ? "?refresh=1" : ""}`,
      signal,
    ),
  runInsights: (serverId?: number) =>
    api.post<{ queued: boolean; running?: boolean }>(
      "/servers/api/admin/insights/ai/run/",
      { ...(serverId ? { server_id: serverId } : {}), force: true },
    ),
  history: (serverId: number, hours: number, signal?: AbortSignal) =>
    api.get<{ server_id: number; server_name: string; checks: HealthCheck[] }>(
      `/servers/api/${serverId}/health/?hours=${hours}`,
      signal,
    ),
  healthCheck: (serverId: number, deep: boolean) =>
    api.post<{ check?: HealthCheck; queued?: boolean; cached?: boolean }>(
      `/servers/api/${serverId}/health/check/`,
      { deep },
    ),
  analyze: (serverId: number) =>
    api.post<{ analysis: string; server_name: string }>(
      `/servers/api/${serverId}/ai-analyze/`,
    ),
  alerts: (params: Record<string, string>, signal?: AbortSignal) =>
    api.get<{ alerts: MonitoringAlert[] }>(
      `/servers/api/alerts/?${new URLSearchParams({ limit: "200", ...params })}`,
      signal,
    ),
  resolve: (id: number) => api.post(`/servers/api/alerts/${id}/resolve/`),
  watchers: (params: Record<string, string>, signal?: AbortSignal) =>
    api.get<{
      summary: {
        open: number;
        acknowledged: number;
        resolved: number;
        suppressed: number;
        total: number;
      };
      drafts: WatcherDraft[];
    }>(
      `/servers/api/watchers/drafts/?${new URLSearchParams({ limit: "200", ...params })}`,
      signal,
    ),
  scan: (serverIds: number[], persist: boolean) =>
    api.post<{
      generated_at: string;
      summary: {
        scanned_servers: number;
        critical: number;
        warning: number;
        drafts: number;
      };
      drafts: Omit<WatcherDraft, "id">[];
      persisted_scan: boolean;
      persisted?: {
        created: number;
        updated: number;
        reopened: number;
        resolved: number;
      };
    }>("/servers/api/watchers/scan/", {
      server_ids: serverIds,
      persist,
      limit: 100,
    }),
  acknowledge: (id: number) =>
    api.post<{ draft: WatcherDraft }>(
      `/servers/api/watchers/drafts/${id}/ack/`,
    ),
  launch: (id: number) =>
    api.post<{
      draft: WatcherDraft;
      agent_id: number;
      run_id: number;
      status: string;
    }>(`/servers/api/watchers/drafts/${id}/launch/`),
  config: (signal?: AbortSignal) =>
    api.get<MonitoringConfig>("/servers/api/monitoring/config/", signal),
  updateConfig: (thresholds: Thresholds) =>
    api.post("/servers/api/monitoring/config/", { thresholds }),
};
