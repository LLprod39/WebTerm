export interface PluginPublisher {
  id: string;
  name: string;
  website?: string;
  verified?: boolean;
}

export interface PluginPermission {
  scope: string;
  reason: string;
  risk_tier: string;
  granted?: boolean;
  grant_id?: number | null;
}

export interface PluginAction {
  id: string;
  title: string;
  description?: string;
  required_permissions?: string[];
  risk_tier?: string;
  executor_ref?: string;
}

export interface PluginManifestSurfaceMap {
  pages?: Array<Record<string, unknown>>;
  dashboard_widgets?: Array<Record<string, unknown>>;
  connectors?: Array<Record<string, unknown>>;
  studio_nodes?: Array<Record<string, unknown>>;
  agent_tools?: Array<Record<string, unknown>>;
  terminal_actions?: Array<Record<string, unknown>>;
  hooks?: Array<Record<string, unknown>>;
  [key: string]: Array<Record<string, unknown>> | undefined;
}

export interface PluginPackage {
  id: number;
  plugin_id: string;
  version: string;
  name: string;
  slug: string;
  publisher: PluginPublisher;
  source: string;
  package_hash: string;
  signature_payload?: Record<string, unknown>;
  provenance?: Record<string, unknown>;
  attestations?: Array<Record<string, unknown>>;
  sbom?: Record<string, unknown>;
  dependency_scan?: Record<string, unknown>;
  sandbox_policy?: Record<string, unknown>;
  risk_tier: string;
  review_status: string;
  signature_status: string;
  manifest: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface PluginAccessGroup {
  id: number;
  name: string;
}

export interface PluginInstallationScope {
  mode: "global" | "groups" | string;
  groups: PluginAccessGroup[];
  group_ids: number[];
}

export interface PluginInstallation {
  id: number;
  plugin_id: string;
  status: "disabled" | "enabled" | "blocked" | "quarantined" | "uninstalling";
  package: PluginPackage;
  settings: Record<string, unknown>;
  scope?: PluginInstallationScope;
  health_status?: string;
  health_failure_count?: number;
  last_error?: string;
  installed_at?: string | null;
  enabled_at?: string | null;
  disabled_at?: string | null;
  quarantined_at?: string | null;
}

export interface PluginCatalogItem {
  id: string;
  name: string;
  slug: string;
  version: string;
  summary: string;
  description?: string;
  publisher: PluginPublisher;
  categories: string[];
  risk_tier: string;
  permissions: PluginPermission[];
  surfaces: PluginManifestSurfaceMap;
  actions: PluginAction[];
  installation: PluginInstallation | null;
  review_status: string;
  signature_status: string;
  enabled: boolean;
}

export interface PluginCatalogResponse {
  success: boolean;
  plugins: PluginCatalogItem[];
  summary: {
    registered: number;
    enabled: number;
    disabled: number;
  };
}

export interface PluginInstallationsResponse {
  success: boolean;
  installations: PluginInstallation[];
}

export interface PluginInstallationScopeResponse {
  success: boolean;
  scope: PluginInstallationScope;
  available_groups: PluginAccessGroup[];
}

export interface PluginLifecycleImpact {
  installation_id: number;
  plugin_id: string;
  status: string;
  package: {
    id: number;
    version: string;
    review_status: string;
    signature_status: string;
    sandbox_policy?: Record<string, unknown>;
    ready_to_enable: boolean;
    enable_blockers: string[];
  };
  surfaces: {
    counts: Record<string, number>;
    items: PluginManifestSurfaceMap;
  };
  permissions: {
    declared: string[];
    granted: string[];
    missing: string[];
    stale_grants: string[];
  };
  secrets: {
    declared: string[];
    bound: string[];
    missing_required: string[];
  };
  settings: {
    stored_keys: string[];
    declared_keys: string[];
  };
  egress_hosts: string[];
  uninstall: {
    soft_supported: boolean;
    full_supported: boolean;
    reversible: boolean;
  };
}

export interface PluginLifecycleImpactResponse {
  success: boolean;
  impact: PluginLifecycleImpact;
}

export interface PluginReviewPackagesResponse {
  success: boolean;
  packages: PluginPackage[];
  summary: {
    pending: number;
    total: number;
  };
}

export interface PluginPermissionsResponse {
  success: boolean;
  permissions: PluginPermission[];
}

export interface MarketplaceSource {
  id: number;
  name: string;
  source_url: string;
  sync_mode?: "manual" | "remote" | string;
  federated?: boolean;
  credentials_redacted?: boolean;
  is_enabled: boolean;
  last_sync_at?: string | null;
  last_error?: string;
}

export interface MarketplaceCompatibilityReport {
  compatible: boolean;
  errors: string[];
  api_version: string;
  supported_api_versions: string[];
  attestation_policy?: Record<string, unknown>;
}

export interface MarketplaceCompatibilityJob {
  id: number;
  catalog_item_id: number;
  plugin_id: string;
  version: string;
  status: string;
  isolation_mode: string;
  checks: Array<Record<string, unknown>>;
  report: Record<string, unknown>;
  error: string;
  started_at?: string | null;
  completed_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface MarketplaceCatalogItem {
  id: number;
  source: MarketplaceSource;
  plugin_id: string;
  version: string;
  manifest: Record<string, unknown>;
  package_url: string;
  compatibility: Record<string, unknown>;
  compatibility_report: MarketplaceCompatibilityReport;
  review_status: string;
  signature_status: string;
  installed: boolean;
  installation_id?: number | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface MarketplaceSourcesResponse {
  success: boolean;
  sources: MarketplaceSource[];
}

export interface MarketplaceCatalogResponse {
  success: boolean;
  items: MarketplaceCatalogItem[];
  summary: {
    available: number;
  };
}

export interface MarketplaceCatalogDetailResponse {
  success: boolean;
  item: MarketplaceCatalogItem;
}

export interface MarketplaceCompatibilityJobsResponse {
  success: boolean;
  jobs: MarketplaceCompatibilityJob[];
  summary: { total: number };
}

export interface PluginSecretBindingPreview {
  key: string;
  label: string;
  kind: string;
  required: boolean;
  bound: boolean;
  secret_ref: string;
}

export interface PluginSettingsResponse {
  success: boolean;
  settings: Record<string, unknown>;
  schema: Record<string, unknown>;
  secrets: PluginSecretBindingPreview[];
}

export interface PluginSurfacesResponse {
  success: boolean;
  surfaces: {
    pages: Array<Record<string, unknown>>;
    dashboard_widgets: Array<Record<string, unknown>>;
    connectors: Array<Record<string, unknown>>;
    studio_nodes: Array<Record<string, unknown>>;
    agent_tools: Array<Record<string, unknown>>;
    terminal_actions: Array<Record<string, unknown>>;
    hooks: Array<Record<string, unknown>>;
  };
}

export interface PluginPageResponse {
  success: boolean;
  page: Record<string, unknown>;
}

export interface PluginConnectorHealthResponse {
  success: boolean;
  health: {
    plugin_id: string;
    connector_id: string;
    status: "healthy" | "blocked" | string;
    connector: Record<string, unknown>;
    checks: Array<Record<string, unknown>>;
  };
}

export interface PluginTerminalActionExecuteResponse {
  success: boolean;
  status?: string;
  message?: string;
  plugin_id?: string;
  connector_id?: string;
}
