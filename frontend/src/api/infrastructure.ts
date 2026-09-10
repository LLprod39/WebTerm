import { api } from "./client";
export interface ServerRow {
  id: number;
  name: string;
  host: string;
  port: number;
  username: string;
  server_type: string;
  status: string;
  group_id: number | null;
  group_name: string;
  is_shared: boolean;
  can_edit: boolean;
  can_connect_terminal?: boolean;
  has_trusted_host_keys: boolean;
  last_connected: string | null;
  detected_os: string;
  detected_os_pretty: string;
}
export interface ServerGroup {
  id: number | null;
  name: string;
  description: string;
  server_count: number;
  role: string;
  can_edit: boolean;
}
export interface ServerDetail extends Pick<
  ServerRow,
  | "id"
  | "name"
  | "host"
  | "port"
  | "username"
  | "server_type"
  | "group_id"
  | "can_edit"
  | "has_trusted_host_keys"
> {
  is_shared_server: boolean;
  ai_read_only: boolean;
  share_context_enabled: boolean;
  shared_by_username: string;
  auth_method: "password" | "key" | "key_password";
  key_path: string;
  tags: string;
  notes: string;
  corporate_context: string;
  is_active: boolean;
  sudo_auth_mode: string;
  network_config: Record<string, unknown>;
  has_saved_password: boolean;
  has_saved_sudo_password: boolean;
  can_view_password: boolean;
  capabilities: Record<string, boolean>;
  trusted_host_key_fingerprints: string[];
}
export interface Activity {
  id: number;
  action: string;
  status?: string;
  category?: string;
  description: string;
  entity_name: string;
  created_at: string;
}
export interface Bootstrap {
  servers: ServerRow[];
  groups: ServerGroup[];
  stats: { owned: number; shared: number; total: number };
  recent_activity: Activity[];
}
export interface HealthRow {
  id: number;
  server_id?: number;
  server_name?: string;
  name: string;
  host: string;
  status: string;
  cpu_percent: number | null;
  memory_percent: number | null;
  disk_percent: number | null;
  load_1m?: number | null;
  is_stale: boolean;
  checked_at: string | null;
  metrics_checked_at?: string | null;
  uptime_seconds?: number | null;
  error_message?: string;
}
export interface Alert {
  id: number;
  server_id: number;
  server_name: string;
  alert_type: string;
  severity: string;
  title: string;
  message: string;
  created_at: string;
  is_resolved?: boolean;
}
export interface Monitoring {
  servers: HealthRow[];
  alerts: Alert[];
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
  recent_activity: Activity[];
  meta: { stale_after_seconds: number };
}
export interface ServerInput {
  name: string;
  host: string;
  port: number;
  username: string;
  auth_method: string;
  password?: string;
  ssh_private_key?: string;
  key_path?: string;
  group_id?: number | null;
  tags?: string;
  notes?: string;
  corporate_context?: string;
  sudo_auth_mode?: string;
  sudo_password?: string;
  network_config?: Record<string, unknown>;
}
export const infrastructureApi = {
  bootstrap: (signal?: AbortSignal) =>
    api.get<Bootstrap>("/servers/api/frontend/bootstrap/", signal),
  server: (id: number, signal?: AbortSignal) =>
    api.get<ServerDetail>(`/servers/api/${id}/get/`, signal),
  create: (body: ServerInput) =>
    api.post<{ server_id: number }>("/servers/api/create/", body),
  update: (id: number, body: Partial<ServerInput>) =>
    api.post(`/servers/api/${id}/update/`, body),
  remove: (id: number) => api.post(`/servers/api/${id}/delete/`),
  test: (id: number, body: Record<string, unknown> = {}) =>
    api.post<{ success: boolean; message?: string }>(
      `/servers/api/${id}/test/`,
      body,
    ),
  monitoring: (signal?: AbortSignal) =>
    api.get<Monitoring>("/servers/api/monitoring/dashboard/", signal),
  refresh: () => api.post("/servers/api/monitoring/refresh/"),
  check: (id: number) => api.post(`/servers/api/${id}/health/check/`),
  resolveAlert: (id: number) => api.post(`/servers/api/alerts/${id}/resolve/`),
  groupCreate: (body: { name: string; description?: string }) =>
    api.post<{ group_id: number }>("/servers/api/groups/create/", body),
  groupUpdate: (id: number, body: { name: string; description?: string }) =>
    api.post(`/servers/api/groups/${id}/update/`, body),
  groupRemove: (id: number) => api.post(`/servers/api/groups/${id}/delete/`),
};
