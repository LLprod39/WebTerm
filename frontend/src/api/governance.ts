import { api } from "./client";

export type PermissionMap = Record<string, boolean | null>;
export interface FeatureChoice {
  value: string;
  label: string;
}
export interface AccessUser {
  id: number;
  username: string;
  email: string;
  is_staff: boolean;
  is_active: boolean;
  is_superuser?: boolean;
  date_joined?: string;
  groups: { id: number; name: string }[];
  access_profile: string;
  effective_permissions: Record<string, boolean>;
  explicit_permissions: PermissionMap;
  group_permissions: Record<string, boolean>;
  group_permission_sources: Record<
    string,
    { group_id: number; group_name: string; allowed: boolean }[]
  >;
  permission_sources: Record<string, string>;
}
export interface AccessGroup {
  id: number;
  name: string;
  members: { id: number; username: string }[];
  member_count?: number;
  explicit_permissions: PermissionMap;
}
export interface AccessPermission {
  id: number;
  user_id?: number;
  username?: string;
  group_id?: number;
  group_name?: string;
  feature: string;
  feature_display?: string;
  allowed: boolean;
}
export interface Project {
  id: string;
  name: string;
  slug: string;
  role: string;
  is_active: boolean;
  is_default: boolean;
  member_count: number;
  can_manage: boolean;
  created_at: string;
}
export interface ProjectMember {
  user_id: number;
  username: string;
  email: string;
  role: string;
  is_active: boolean;
  joined_at: string;
}
export interface AuditEvent {
  id: number;
  created_at: string;
  user_id: number | null;
  username: string;
  category: string;
  action: string;
  status: string;
  description: string;
  entity_type: string;
  entity_id: string;
  entity_name: string;
  ip_address: string;
  user_agent: string;
  metadata: Record<string, unknown>;
}
export interface AuditResponse {
  events: AuditEvent[];
  summary: Record<string, number>;
  user_stats: Record<string, unknown>[];
  users: { id: number; username: string }[];
  paging: { limit: number; offset: number; total: number; has_more: boolean };
}
export interface LdapStatus {
  enabled: boolean;
  status: string;
  severity: string;
  backend_loaded: boolean;
  server_configured: boolean;
  search_base_configured: boolean;
  bind_dn_configured: boolean;
  bind_password_configured: boolean;
  start_tls: boolean;
  ignore_cert: boolean;
  ca_cert_configured: boolean;
  missing: string[];
  config_source: string;
}
export interface SettingsResponse {
  config: Record<string, string | number | boolean | null>;
  api_keys: Record<string, boolean>;
  providers: Record<string, unknown>[] | Record<string, unknown>;
  ldap_status: LdapStatus;
}
export interface ReadinessCheck {
  key: string;
  title: string;
  status: string;
  severity: string;
  message: string;
  action_path: string;
  action_label: string;
  details: Record<string, unknown>;
}
export interface ReadinessResponse {
  status: string;
  summary: { ready: number; warning: number; error: number; total: number };
  checks: ReadinessCheck[];
}
export interface AiGrant {
  id: number;
  connection_id: number;
  user: { id: number; username: string } | null;
  group: { id: number; name: string } | null;
  project: { id: number; name: string } | null;
  project_role: string;
  allow_interactive: boolean;
  allow_unattended: boolean;
}
export interface AiConnection {
  id: number;
  public_id: string;
  target_id: string;
  scope: string;
  owner_id: number | null;
  name: string;
  status: string;
  enabled: boolean;
  runtime_version: string;
  auth_revision: number;
  concurrency_limit: number;
  health: Record<string, unknown>;
  limits: Record<string, unknown>;
  last_error_code: string;
  last_verified_at: string | null;
  access: { interactive: boolean; unattended: boolean };
  manageable: boolean;
  created_at: string;
  updated_at: string;
  grants?: AiGrant[];
}
export interface AuthFlow {
  id: string;
  connection_id: number;
  status: string;
  verification_uri: string;
  user_code: string;
  error_code: string;
  expires_at: string | null;
  completed_at: string | null;
}
export interface AiPool {
  id: number;
  name: string;
  target_id: string;
  enabled: boolean;
  manageable: boolean;
  members: {
    id: number;
    connection_id: number;
    connection_name: string;
    status: string;
    enabled: boolean;
    weight: number;
  }[];
}
export interface AiBinding {
  target_id: string;
  connection_id?: number | null;
  pool_id?: number | null;
  model_id?: string | null;
  reasoning_effort?: string | null;
}
export interface AiPreference {
  id: number;
  user_id: number | null;
  project_id: number | null;
  purpose: string;
  binding: AiBinding;
}
export interface AiCatalog {
  targets: { id: string; label: string; kind: string; auth?: string }[];
  purposes: string[];
  scopes: string[];
  models_by_target: Record<
    string,
    { id: string; label?: string; reasoning_efforts: string[] }[]
  >;
}
export interface PluginPackage {
  id: number;
  plugin_id: string;
  version: string;
  name: string;
  publisher: { id: string; name: string };
  source: string;
  risk_tier: string;
  review_status: string;
  signature_status: string;
  manifest: Record<string, unknown>;
  sbom: unknown;
  dependency_scan: unknown;
  provenance: unknown;
  attestations: unknown;
  package_hash: string;
  [key: string]: unknown;
}
export interface PluginInstallation {
  id: number;
  plugin_id: string;
  status: string;
  package: PluginPackage;
  settings: Record<string, unknown>;
  scope: Record<string, unknown>;
  health_status: string;
  health_failure_count: number;
  last_error: string;
  installed_at: string | null;
}
export interface PluginPermission {
  scope: string;
  reason: string;
  risk_tier: string;
  granted: boolean;
  grant_id: number | null;
}
export interface PluginSettings {
  settings: Record<string, unknown>;
  schema: Record<string, unknown>;
  secrets: {
    key: string;
    label: string;
    kind: string;
    required: boolean;
    bound: boolean;
    secret_ref: string;
  }[];
}
export interface MarketplaceSource {
  id: number;
  name: string;
  source_url: string;
  sync_mode: string;
  is_enabled: boolean;
  last_sync_at: string | null;
  last_error: string;
}
export interface MarketplaceItem {
  id: number;
  plugin_id: string;
  version: string;
  manifest: Record<string, unknown>;
  source: MarketplaceSource;
  compatibility: string;
  compatibility_report: unknown;
  review_status: string;
  signature_status: string;
  installed: boolean;
  installation_id: number | null;
}

export const governanceApi = {
  users: (signal?: AbortSignal) =>
    api.get<{ users: AccessUser[]; features: FeatureChoice[] }>(
      "/api/access/users/",
      signal,
    ),
  groups: (signal?: AbortSignal) =>
    api.get<{ groups: AccessGroup[]; features: FeatureChoice[] }>(
      "/api/access/groups/",
      signal,
    ),
  permissions: (signal?: AbortSignal) =>
    api.get<{
      permissions: AccessPermission[];
      group_permissions: AccessPermission[];
      features: FeatureChoice[];
    }>("/api/access/permissions/", signal),
  projects: (signal?: AbortSignal) =>
    api.get<{ projects: Project[]; active_project_id: string | null }>(
      "/api/projects/",
      signal,
    ),
  settings: (signal?: AbortSignal) =>
    api.get<SettingsResponse>("/api/settings/", signal),
  readiness: (signal?: AbortSignal) =>
    api.get<ReadinessResponse>("/api/settings/readiness/", signal),
  audit: (params: URLSearchParams, signal?: AbortSignal) =>
    api.get<AuditResponse>(`/api/settings/activity/?${params}`, signal),
  connections: (signal?: AbortSignal) =>
    api.get<{ connections: AiConnection[] }>(
      "/api/ai/providers/connections/",
      signal,
    ),
  aiCatalog: (signal?: AbortSignal) =>
    api.get<AiCatalog>("/api/ai/providers/catalog/", signal),
  pools: (signal?: AbortSignal) =>
    api.get<{ pools: AiPool[] }>("/api/ai/providers/pools/", signal),
  preferences: (signal?: AbortSignal) =>
    api.get<{
      preferences: AiPreference[];
      workspace_defaults: AiPreference[];
    }>("/api/ai/providers/preferences/", signal),
  installations: (signal?: AbortSignal) =>
    api.get<{ installations: PluginInstallation[] }>(
      "/api/plugins/installed/",
      signal,
    ),
};
