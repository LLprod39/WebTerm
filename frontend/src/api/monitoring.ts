import { apiFetch } from "@/lib/api";

// ---------------------------------------------------------------------------
// Monitoring API
// ---------------------------------------------------------------------------

export interface ServerHealth {
  server_id: number;
  server_name: string;
  host: string;
  status: "healthy" | "warning" | "critical" | "unreachable" | "unknown";
  cpu_percent: number | null;
  memory_percent: number | null;
  disk_percent: number | null;
  memory_used_mb?: number | null;
  memory_total_mb?: number | null;
  disk_used_gb?: number | null;
  disk_total_gb?: number | null;
  net_rx_bytes?: number | null;
  net_tx_bytes?: number | null;
  load_1m: number | null;
  uptime_seconds: number | null;
  response_time_ms: number | null;
  checked_at: string | null;
}

export interface ServerAlertItem {
  id: number;
  server_id: number;
  server_name: string;
  alert_type: string;
  severity: "info" | "warning" | "critical";
  title: string;
  message: string;
  is_resolved?: boolean;
  resolved_at?: string | null;
  created_at: string;
  metadata?: Record<string, unknown>;
}

export interface MonitoringDashboard {
  success: boolean;
  servers: ServerHealth[];
  alerts: ServerAlertItem[];
  summary: {
    total_servers: number;
    healthy: number;
    warning: number;
    critical: number;
    unreachable: number;
    unknown: number;
    active_alerts: number;
    avg_cpu: number;
    avg_memory: number;
    avg_disk: number;
  };
  recent_activity: Array<{
    id: number;
    action: string;
    category: string;
    description: string;
    entity_name: string;
    created_at: string;
  }>;
}

export async function fetchMonitoringDashboard() {
  return apiFetch<MonitoringDashboard>("/servers/api/monitoring/dashboard/");
}

export type FleetHealthStatus = ServerHealth["status"];

export interface MonitoringStatusItem {
  server_id: number;
  server_name: string;
  host: string;
  server_type: string;
  status: FleetHealthStatus;
  checked_at: string | null;
  age_seconds: number | null;
  is_stale: boolean;
  response_time_ms: number | null;
  cpu_percent: number | null;
  memory_percent: number | null;
  disk_percent: number | null;
  load_1m?: number | null;
  metrics_checked_at?: string | null;
  metrics_age_seconds?: number | null;
  is_lite: boolean;
}

export interface MonitoringStatusResponse {
  success: boolean;
  servers: MonitoringStatusItem[];
  summary: {
    total_servers: number;
    healthy: number;
    warning: number;
    critical: number;
    unreachable: number;
    unknown: number;
    stale: number;
  };
  meta: {
    stale_after_seconds: number;
    latest_checked_at: string | null;
    has_stale: boolean;
  };
  cached?: boolean;
  queued?: boolean;
  refreshed?: boolean;
}

export async function fetchMonitoringStatus() {
  return apiFetch<MonitoringStatusResponse>("/servers/api/monitoring/status/");
}

export async function refreshMonitoringFleet() {
  return apiFetch<MonitoringStatusResponse>("/servers/api/monitoring/refresh/", {
    method: "POST",
  });
}

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

export async function fetchServerHealth(serverId: number, hours = 24) {
  return apiFetch<{ success: boolean; server_id: number; server_name: string; checks: HealthCheck[] }>(
    `/servers/api/${serverId}/health/?hours=${hours}`,
  );
}

export async function triggerHealthCheck(serverId: number, deep = false) {
  return apiFetch<{ success: boolean; check: HealthCheck }>(`/servers/api/${serverId}/health/check/`, {
    method: "POST",
    body: JSON.stringify({ deep }),
  });
}

export async function fetchAlerts(params?: { server_id?: number; severity?: string; resolved?: boolean; limit?: number }) {
  const q = new URLSearchParams();
  if (params?.server_id) q.set("server_id", String(params.server_id));
  if (params?.severity) q.set("severity", params.severity);
  if (params?.resolved !== undefined) q.set("resolved", String(params.resolved));
  if (params?.limit) q.set("limit", String(params.limit));
  const qs = q.toString();
  return apiFetch<{ success: boolean; alerts: ServerAlertItem[] }>(`/servers/api/alerts/${qs ? `?${qs}` : ""}`);
}

export async function resolveAlert(alertId: number) {
  return apiFetch<{ success: boolean }>(`/servers/api/alerts/${alertId}/resolve/`, { method: "POST" });
}

// ---------------------------------------------------------------------------
// Admin Dashboard API
// ---------------------------------------------------------------------------

export interface AdminDashboardData {
  online_users: { count: number; total_registered: number; users: Array<{ username: string; action: string; time: string }> };
  ai: { requests_today: number };
  terminals: { active: number; connections: Array<{ server: string; user: string; connected_at: string }> };
  agents: { running: number; today: number; succeeded_24h: number; failed_24h: number; success_rate: number };
  api_usage: Record<string, { calls: number; input_tokens: number; output_tokens: number; errors: number; cost_usd: number }>;
  api_calls_today: number;
  providers: Record<string, { enabled: boolean; model: string }>;
  servers: { total: number; active: number };
  tasks: { total: number; in_progress: number };
  hourly_activity: Array<{ hour: string; count: number }>;
  top_users: Array<{ username: string; total: number; ai_requests: number; terminal_sessions: number }>;
  recent_activity: Array<{ user: string; category: string; action: string; time: string }>;
  fleet_health: { avg_cpu: number; avg_memory: number; avg_disk: number; healthy: number; warning: number; critical: number; unreachable: number };
  active_alerts_count: number;
  alerts: Array<{ server: string; type: string; severity: string; title: string; time: string }>;
  app_version: string;
}

export async function fetchAdminDashboard() {
  return apiFetch<{ success: boolean; data: AdminDashboardData }>("/api/admin/dashboard/");
}

export interface AdminUserActivity {
  id: number;
  user_id: number;
  username: string;
  category: string;
  action: string;
  status: string;
  description: string;
  entity_type: string;
  entity_name: string;
  ip_address: string;
  created_at: string;
}

export async function fetchAdminUsersActivity(params?: { user_id?: number; category?: string; search?: string; limit?: number; offset?: number; days?: number }) {
  const q = new URLSearchParams();
  if (params?.user_id) q.set("user_id", String(params.user_id));
  if (params?.category) q.set("category", params.category);
  if (params?.search) q.set("search", params.search);
  if (params?.limit) q.set("limit", String(params.limit));
  if (params?.offset) q.set("offset", String(params.offset));
  if (params?.days) q.set("days", String(params.days));
  const qs = q.toString();
  return apiFetch<{ success: boolean; total: number; events: AdminUserActivity[] }>(`/api/admin/users/activity/${qs ? `?${qs}` : ""}`);
}

export interface AdminUserSession {
  user_id: number;
  username: string;
  email: string;
  is_staff: boolean;
  last_action: string;
  last_category: string;
  last_activity: string;
  active_terminals: number;
  today_actions: number;
}

export async function fetchAdminUsersSessions() {
  return apiFetch<{ success: boolean; online_count: number; total_registered: number; active_today: number; sessions: AdminUserSession[] }>(
    "/api/admin/users/sessions/",
  );
}

// ---------------------------------------------------------------------------
// Dashboard Layout API
// ---------------------------------------------------------------------------

export interface DashboardWidgetConfig {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  visible?: boolean;
  props?: Record<string, unknown>;
}

export interface DashboardLayoutData {
  widgets: DashboardWidgetConfig[];
}

export async function fetchDashboardLayout(type: "admin" | "user") {
  return apiFetch<{ success: boolean; layout: DashboardLayoutData | null }>(`/api/dashboard-custom/layout/${type}/`);
}

export async function saveDashboardLayout(type: "admin" | "user", layout: DashboardLayoutData) {
  return apiFetch<{ success: boolean; created: boolean }>(`/api/dashboard-custom/layout/${type}/`, {
    method: "POST",
    body: JSON.stringify({ layout }),
  });
}

// ---------------------------------------------------------------------------
// Monitoring Config API
// ---------------------------------------------------------------------------

export interface MonitoringConfig {
  success: boolean;
  thresholds: {
    cpu_warn: number;
    cpu_crit: number;
    mem_warn: number;
    mem_crit: number;
    disk_warn: number;
    disk_crit: number;
  };
  stats: {
    total_checks: number;
    active_alerts: number;
    last_check_at: string | null;
    monitored_servers: number;
  };
}

export async function fetchMonitoringConfig() {
  return apiFetch<MonitoringConfig>("/servers/api/monitoring/config/");
}

export async function saveMonitoringConfig(thresholds: Record<string, number>) {
  return apiFetch<{ success: boolean }>("/servers/api/monitoring/config/", {
    method: "POST",
    body: JSON.stringify({ thresholds }),
  });
}

export async function aiAnalyzeServer(serverId: number) {
  return apiFetch<{ success: boolean; analysis: string; server_name: string }>(`/servers/api/${serverId}/ai-analyze/`, {
    method: "POST",
  });
}
