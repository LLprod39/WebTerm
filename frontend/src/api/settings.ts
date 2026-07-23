/**
 * Platform settings, model catalog, activity audit, and access-management API.
 */
import { apiFetch } from "@/lib/api";

export interface AccessUser {
  id: number;
  username: string;
  email: string;
  is_staff: boolean;
  is_active: boolean;
  is_superuser?: boolean;
  access_profile?: string;
  groups?: Array<{ id: number; name: string }>;
  effective_permissions?: Record<string, boolean>;
  explicit_permissions?: Record<string, boolean>;
  group_permissions?: Record<string, boolean>;
  group_permission_sources?: Record<string, Array<{ group_id: number; group_name: string; allowed: boolean }>>;
  permission_sources?: Record<string, string>;
}

export interface AccessGroup {
  id: number;
  name: string;
  member_count: number;
  members?: Array<{ id: number; username: string }>;
  explicit_permissions?: Record<string, boolean>;
}

export interface AccessPermission {
  id: number;
  user_id: number;
  username: string;
  feature: string;
  feature_display?: string;
  allowed: boolean;
}

export interface AccessGroupPermission {
  id: number;
  group_id: number;
  group_name: string;
  feature: string;
  feature_display?: string;
  allowed: boolean;
}

export interface SettingsConfig {
  default_provider: string;
  internal_llm_provider: string;
  gemini_enabled: boolean;
  grok_enabled: boolean;
  openai_enabled: boolean;
  ollama_enabled: boolean;
  ollama_cloud_enabled?: boolean;
  chat_llm_provider: string;
  chat_llm_model: string;
  agent_llm_provider: string;
  agent_llm_model: string;
  orchestrator_llm_provider: string;
  orchestrator_llm_model: string;
  claude_enabled: boolean;
  chat_model_gemini: string;
  chat_model_grok: string;
  chat_model_openai: string;
  chat_model_claude: string;
  chat_model_ollama: string;
  agent_model_ollama?: string;
  ollama_base_url?: string;
  ollama_runtime_mode?: string;
  ollama_cloud_base_url?: string;
  ollama_think_mode?: string;
  log_terminal_commands: boolean;
  log_ai_assistant: boolean;
  log_agent_runs: boolean;
  log_pipeline_runs: boolean;
  log_auth_events: boolean;
  log_server_changes: boolean;
  log_settings_changes: boolean;
  log_file_operations: boolean;
  log_mcp_calls: boolean;
  log_http_requests: boolean;
  retention_days: number;
  export_format: string;
  openai_reasoning_effort?: string;
  domain_auth_enabled?: boolean;
  domain_auth_header?: string;
  domain_auth_auto_create?: boolean;
  domain_auth_lowercase_usernames?: boolean;
  domain_auth_default_profile?: string;
  agent_active_runs_per_user_limit?: number;
  agent_active_runs_global_limit?: number;
  agent_run_stale_seconds?: number;
  pipeline_active_runs_per_user_limit?: number;
  pipeline_active_runs_global_limit?: number;
  pipeline_run_stale_seconds?: number;
  ssh_terminal_sessions_per_user_limit?: number;
  ssh_terminal_sessions_global_limit?: number;
  ssh_terminal_session_stale_seconds?: number;
  llm_daily_token_limit_per_user?: number;
  mcp_stdio_initialize_timeout_seconds?: number;
  mcp_stdio_request_timeout_seconds?: number;
  mcp_stdio_tool_call_timeout_seconds?: number;
  mcp_process_terminate_timeout_seconds?: number;
  mcp_http_connect_timeout_seconds?: number;
  mcp_http_request_timeout_seconds?: number;
  mcp_http_tool_call_timeout_seconds?: number;
  mcp_http_retry_attempts?: number;
  [key: string]: string | number | boolean | null | undefined;
}

export interface SettingsConfigResponse {
  success: boolean;
  config: SettingsConfig;
  api_keys?: Record<string, boolean>;
  providers?: Record<string, unknown>;
  ldap_status?: {
    enabled: boolean;
    status: "disabled" | "enabled" | "misconfigured";
    severity: "ready" | "warning" | "error";
    backend_loaded: boolean;
    server_configured: boolean;
    search_base_configured: boolean;
    bind_dn_configured: boolean;
    bind_password_configured: boolean;
    start_tls: boolean;
    ignore_cert: boolean;
    ca_cert_configured: boolean;
    missing: string[];
    config_source: "env_startup";
  };
}

export interface ModelsResponse {
  gemini: string[];
  grok: string[];
  openai: string[];
  claude: string[];
  ollama: string[];
  ollama_local?: string[];
  ollama_cloud?: string[];
  current: {
    default_provider: string;
    chat_gemini: string;
    chat_grok: string;
    chat_openai: string;
    chat_claude: string;
    chat_ollama?: string;
    agent_model_ollama?: string;
    ollama_runtime_mode?: string;
    ollama_think_mode?: string;
  };
}

export interface ActivityLogEvent {
  id: number;
  created_at: string;
  timestamp?: string;
  user_id?: number | null;
  username: string;
  category: string;
  action: string;
  status: string;
  description: string;
  entity_type?: string;
  entity_id?: number | string | null;
  entity_name: string;
  ip_address?: string;
  user_agent?: string;
  metadata?: Record<string, unknown>;
}

export interface ActivityLogsResponse {
  success: boolean;
  events: ActivityLogEvent[];
  summary: {
    total_events: number;
    total_users: number;
    login_count?: number;
    assistant_requests?: number;
    server_connections?: number;
    server_changes?: number;
  };
}

export type SettingsReadinessSeverity = "ready" | "warning" | "error";

export interface SettingsReadinessCheck {
  key: string;
  title: string;
  status: string;
  severity: SettingsReadinessSeverity;
  message: string;
  action_path?: string;
  action_label?: string;
  details?: Record<string, unknown>;
}

export interface SettingsReadinessResponse {
  success: boolean;
  status: SettingsReadinessSeverity;
  summary: {
    ready: number;
    warning: number;
    error: number;
    total: number;
  };
  checks: SettingsReadinessCheck[];
}

export type RefreshableProvider = "gemini" | "grok" | "openai" | "claude" | "ollama";

export async function fetchSettings() {
  return apiFetch<SettingsConfigResponse>("/api/settings/");
}

export async function saveSettings(config: Record<string, unknown>) {
  return apiFetch<{ success: boolean; message?: string }>("/api/settings/", {
    method: "POST",
    body: JSON.stringify(config),
  });
}

export async function fetchModels() {
  return apiFetch<ModelsResponse>("/api/models/");
}

export async function refreshModels(provider: RefreshableProvider) {
  return apiFetch<{ success: boolean; provider: string; models: string[]; count: number }>("/api/models/refresh/", {
    method: "POST",
    body: JSON.stringify({ provider }),
  });
}

export async function fetchSettingsActivity(limit = 30, days = 14) {
  return apiFetch<ActivityLogsResponse>(`/api/settings/activity/?limit=${limit}&days=${days}`);
}

export async function fetchSettingsReadiness() {
  return apiFetch<SettingsReadinessResponse>("/api/settings/readiness/");
}

export async function fetchAccessUsers() {
  return apiFetch<{ users: AccessUser[]; features?: Array<{ value: string; label: string }> }>("/api/access/users/");
}

export async function createAccessUser(payload: Record<string, unknown>) {
  return apiFetch<{ success: boolean; user: AccessUser }>("/api/access/users/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateAccessUser(userId: number, payload: Record<string, unknown>) {
  return apiFetch<{ success: boolean; user: AccessUser }>(`/api/access/users/${userId}/`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function deleteAccessUser(userId: number) {
  return apiFetch<{ success: boolean; message: string }>(`/api/access/users/${userId}/`, { method: "DELETE" });
}

export async function setAccessUserPassword(userId: number, password: string) {
  return apiFetch<{ success: boolean; message: string }>(`/api/access/users/${userId}/password/`, {
    method: "POST",
    body: JSON.stringify({ password }),
  });
}

export async function fetchAccessGroups() {
  return apiFetch<{ groups: AccessGroup[]; features?: Array<{ value: string; label: string }> }>("/api/access/groups/");
}

export async function createAccessGroup(payload: Record<string, unknown>) {
  return apiFetch<{ success: boolean; group: AccessGroup }>("/api/access/groups/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateAccessGroup(groupId: number, payload: Record<string, unknown>) {
  return apiFetch<{ success: boolean; group: AccessGroup }>(`/api/access/groups/${groupId}/`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export async function deleteAccessGroup(groupId: number) {
  return apiFetch<{ success: boolean; message: string }>(`/api/access/groups/${groupId}/`, { method: "DELETE" });
}

export async function fetchAccessPermissions() {
  return apiFetch<{
    permissions: AccessPermission[];
    group_permissions?: AccessGroupPermission[];
    features: Array<{ value: string; label: string }>;
  }>("/api/access/permissions/");
}

export async function upsertAccessPermission(payload: { user_id: number; feature: string; allowed: boolean }) {
  return apiFetch<{ success: boolean; permission: AccessPermission }>("/api/access/permissions/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateAccessPermission(permId: number, allowed: boolean) {
  return apiFetch<{ success: boolean; permission: AccessPermission }>(`/api/access/permissions/${permId}/`, {
    method: "PUT",
    body: JSON.stringify({ allowed }),
  });
}

export async function deleteAccessPermission(permId: number) {
  return apiFetch<{ success: boolean; message: string }>(`/api/access/permissions/${permId}/`, {
    method: "DELETE",
  });
}

export async function fetchAccessGroupPermissions() {
  return apiFetch<{ permissions: AccessGroupPermission[]; features: Array<{ value: string; label: string }> }>(
    "/api/access/group-permissions/",
  );
}

export async function upsertAccessGroupPermission(payload: { group_id: number; feature: string; allowed: boolean }) {
  return apiFetch<{ success: boolean; permission: AccessGroupPermission }>("/api/access/group-permissions/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateAccessGroupPermission(permId: number, allowed: boolean) {
  return apiFetch<{ success: boolean; permission: AccessGroupPermission }>(`/api/access/group-permissions/${permId}/`, {
    method: "PUT",
    body: JSON.stringify({ allowed }),
  });
}

export async function deleteAccessGroupPermission(permId: number) {
  return apiFetch<{ success: boolean; message: string }>(`/api/access/group-permissions/${permId}/`, {
    method: "DELETE",
  });
}
