/**
 * Server inventory, sharing, group, and direct command API.
 */
import { apiFetch } from "@/lib/api";

export type { SftpEntry, SftpListResponse } from "@/api/server-files";
export * from "@/api/linux-ui";

export type ServerStatus = "online" | "offline" | "unknown";
export type ServerSecretStorageMode = "managed" | "legacy_master_password" | "none";

export interface FrontendServer {
  id: number;
  name: string;
  host: string;
  port: number;
  username: string;
  server_type: "ssh";
  status: ServerStatus;
  group_id: number | null;
  group_name: string;
  is_shared: boolean;
  can_edit: boolean;
  share_context_enabled: boolean;
  shared_by_username: string;
  terminal_path: string;
  minimal_terminal_path: string;
  last_connected: string | null;
  sudo_auth_mode?: "none" | "nopasswd" | "stored_password";
  has_saved_sudo_password?: boolean;
  detected_os?: string;
  detected_os_pretty?: string;
  detected_os_meta?: Record<string, unknown>;
}

export interface ServerDetailsResponse {
  id: number;
  name: string;
  host: string;
  port: number;
  username: string;
  server_type: "ssh";
  auth_method: "password" | "key" | "key_password";
  key_path: string;
  tags: string;
  notes: string;
  group_id: number | null;
  is_active: boolean;
  ai_read_only?: boolean;
  sudo_auth_mode?: "none" | "nopasswd" | "stored_password";
  has_saved_sudo_password?: boolean;
  corporate_context?: string;
  network_config?: Record<string, unknown>;
  has_saved_password?: boolean;
  can_view_password?: boolean;
  password_storage_mode?: ServerSecretStorageMode;
  sudo_password_storage_mode?: ServerSecretStorageMode;
  can_edit?: boolean;
  is_shared_server?: boolean;
  share_context_enabled?: boolean;
  shared_by_username?: string;
}

export type ServerGroupRole = "owner" | "admin" | "member" | "viewer";
export type ServerGroupSubscriptionKind = "follow" | "favorite";

export interface FrontendGroup {
  id: number | null;
  name: string;
  description: string;
  color: string;
  server_count: number;
  role: ServerGroupRole | "";
  can_edit: boolean;
}

export interface FrontendActivity {
  id: number;
  action: string;
  status: "info" | "success" | "error";
  description: string;
  entity_name: string;
  created_at: string | null;
}

export interface FrontendBootstrapResponse {
  success: boolean;
  servers: FrontendServer[];
  groups: FrontendGroup[];
  stats: {
    owned: number;
    shared: number;
    total: number;
  };
  recent_activity: FrontendActivity[];
}

export async function fetchFrontendBootstrap() {
  return apiFetch<FrontendBootstrapResponse>("/servers/api/frontend/bootstrap/");
}

export async function createServer(payload: Record<string, unknown>) {
  return apiFetch<{ success: boolean; server_id: number; message: string }>("/servers/api/create/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateServer(serverId: number, payload: Record<string, unknown>) {
  return apiFetch<{ success: boolean; message: string }>(`/servers/api/${serverId}/update/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function fetchServerDetails(serverId: number) {
  return apiFetch<ServerDetailsResponse>(`/servers/api/${serverId}/get/`);
}

export async function executeServerCommand(serverId: number, command: string, password = "") {
  return apiFetch<{
    success: boolean;
    output?: {
      stdout?: string;
      stderr?: string;
      exit_code?: number;
      [key: string]: unknown;
    };
    error?: string;
  }>(`/servers/api/${serverId}/execute/`, {
    method: "POST",
    body: JSON.stringify({ command, password }),
  });
}

export async function revealServerPassword(serverId: number, masterPassword = "") {
  return apiFetch<{ success: boolean; password?: string; error?: string }>(`/servers/api/${serverId}/reveal-password/`, {
    method: "POST",
    body: JSON.stringify(masterPassword ? { master_password: masterPassword } : {}),
  });
}

export async function listServerShares(serverId: number) {
  return apiFetch<{
    success: boolean;
    shares: Array<{
      id: number;
      user_id: number;
      username: string;
      email: string;
      share_context: boolean;
      can_connect_terminal: boolean;
      can_execute_command: boolean;
      can_read_files: boolean;
      can_write_files: boolean;
      expires_at: string | null;
      created_at: string | null;
      is_active: boolean;
    }>;
  }>(`/servers/api/${serverId}/shares/`);
}

export async function createServerShare(
  serverId: number,
  payload: {
    user: string;
    share_context?: boolean;
    can_connect_terminal?: boolean;
    can_execute_command?: boolean;
    can_read_files?: boolean;
    can_write_files?: boolean;
    expires_at?: string | null;
  },
) {
  return apiFetch<{ success: boolean }>(`/servers/api/${serverId}/share/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function revokeServerShare(serverId: number, shareId: number) {
  return apiFetch<{ success: boolean }>(`/servers/api/${serverId}/shares/${shareId}/revoke/`, { method: "POST" });
}

export async function createServerGroup(payload: {
  name: string;
  description?: string;
  color?: string;
  tag_ids?: number[];
}) {
  return apiFetch<{ success: boolean; group_id?: number; error?: string }>("/servers/api/groups/create/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateServerGroup(
  groupId: number,
  payload: { name?: string; description?: string; color?: string; tag_ids?: number[] },
) {
  return apiFetch<{ success: boolean; error?: string }>(`/servers/api/groups/${groupId}/update/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteServerGroup(groupId: number) {
  return apiFetch<{ success: boolean; error?: string }>(`/servers/api/groups/${groupId}/delete/`, {
    method: "POST",
  });
}

export async function addServerGroupMember(
  groupId: number,
  payload: { user: string; role?: ServerGroupRole },
) {
  return apiFetch<{ success: boolean; error?: string }>(`/servers/api/groups/${groupId}/add-member/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function removeServerGroupMember(groupId: number, userId: number) {
  return apiFetch<{ success: boolean; error?: string }>(`/servers/api/groups/${groupId}/remove-member/`, {
    method: "POST",
    body: JSON.stringify({ user_id: userId }),
  });
}

export async function subscribeServerGroup(groupId: number, kind: ServerGroupSubscriptionKind) {
  return apiFetch<{ success: boolean; error?: string }>(`/servers/api/groups/${groupId}/subscribe/`, {
    method: "POST",
    body: JSON.stringify({ kind }),
  });
}

export async function bulkUpdateServers(payload: {
  server_ids: number[];
  group_id?: number | null;
  tags?: string;
  is_active?: boolean;
}) {
  return apiFetch<{ success: boolean; updated_count?: number; error?: string }>("/servers/api/bulk-update/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function setMasterPassword(masterPassword: string) {
  return apiFetch<{ success: boolean; error?: string }>("/servers/api/master-password/set/", {
    method: "POST",
    body: JSON.stringify({ master_password: masterPassword }),
  });
}

export async function getMasterPasswordStatus() {
  return apiFetch<{ has_master_password: boolean }>("/servers/api/master-password/check/");
}

export async function clearMasterPassword() {
  return apiFetch<{ success: boolean }>("/servers/api/master-password/clear/");
}

export async function testServer(serverId: number, payload: Record<string, unknown> = {}) {
  return apiFetch<{ success: boolean; message?: string; error?: string }>(`/servers/api/${serverId}/test/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteServer(serverId: number) {
  return apiFetch<{ success: boolean; message?: string }>(`/servers/api/${serverId}/delete/`, { method: "POST" });
}
