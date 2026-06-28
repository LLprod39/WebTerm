import { apiFetch } from "@/lib/api";
import type {
  PluginCatalogResponse,
  PluginLifecycleImpactResponse,
  PluginInstallationsResponse,
  PluginInstallationScopeResponse,
  MarketplaceCatalogDetailResponse,
  MarketplaceCatalogResponse,
  MarketplaceCompatibilityJobsResponse,
  MarketplaceSourcesResponse,
  PluginPermissionsResponse,
  PluginReviewPackagesResponse,
  PluginSettingsResponse,
  PluginPageResponse,
  PluginConnectorHealthResponse,
  PluginTerminalActionExecuteResponse,
  PluginSurfacesResponse,
} from "@/plugins/types";

export async function fetchPluginCatalog() {
  return apiFetch<PluginCatalogResponse>("/api/plugins/catalog/");
}

export async function fetchInstalledPlugins() {
  return apiFetch<PluginInstallationsResponse>("/api/plugins/installed/");
}

export async function enablePlugin(installationId: number) {
  return apiFetch<{ success: boolean; installation_id: number; status: string }>(
    `/api/plugins/installed/${installationId}/enable/`,
    { method: "POST" },
  );
}

export async function disablePlugin(installationId: number) {
  return apiFetch<{ success: boolean; installation_id: number; status: string }>(
    `/api/plugins/installed/${installationId}/disable/`,
    { method: "POST" },
  );
}

export async function fetchPluginInstallationScope(installationId: number) {
  return apiFetch<PluginInstallationScopeResponse>(`/api/plugins/installed/${installationId}/scope/`);
}

export async function updatePluginInstallationScope(installationId: number, groupIds: number[]) {
  return apiFetch<{ success: boolean; installation_id: number; scope: PluginInstallationScopeResponse["scope"] }>(
    `/api/plugins/installed/${installationId}/scope/update/`,
    {
      method: "POST",
      body: JSON.stringify({ group_ids: groupIds }),
    },
  );
}

export async function fetchPluginLifecycleImpact(installationId: number) {
  return apiFetch<PluginLifecycleImpactResponse>(`/api/plugins/installed/${installationId}/impact/`);
}

export async function softUninstallPlugin(installationId: number, payload: { revoke_permissions?: boolean; remove_secret_bindings?: boolean } = {}) {
  return apiFetch<{ success: boolean; installation: PluginInstallationsResponse["installations"][number] }>(
    `/api/plugins/installed/${installationId}/soft-uninstall/`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function rollbackPlugin(installationId: number, packageId?: number) {
  return apiFetch<{ success: boolean; installation: PluginInstallationsResponse["installations"][number] }>(
    `/api/plugins/installed/${installationId}/rollback/`,
    {
      method: "POST",
      body: JSON.stringify(packageId ? { package_id: packageId } : {}),
    },
  );
}

export async function fetchPluginReviewPackages() {
  return apiFetch<PluginReviewPackagesResponse>("/api/plugins/review/packages/");
}

export async function reviewPluginPackage(packageId: number, payload: { status: string; notes?: string; rejection_reason?: string; sign_when_verified?: boolean }) {
  return apiFetch<{ success: boolean; package: PluginReviewPackagesResponse["packages"][number] }>(
    `/api/plugins/review/packages/${packageId}/review/`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function signPluginPackage(packageId: number) {
  return apiFetch<{ success: boolean; package: PluginReviewPackagesResponse["packages"][number] }>(
    `/api/plugins/review/packages/${packageId}/sign/`,
    { method: "POST" },
  );
}

export async function verifyPluginPackageSignature(packageId: number) {
  return apiFetch<{ success: boolean; package: PluginReviewPackagesResponse["packages"][number] }>(
    `/api/plugins/review/packages/${packageId}/verify-signature/`,
    { method: "POST" },
  );
}

export async function attestPluginPackage(packageId: number) {
  return apiFetch<{ success: boolean; package: PluginReviewPackagesResponse["packages"][number] }>(
    `/api/plugins/review/packages/${packageId}/attest/`,
    { method: "POST" },
  );
}

export async function securityScanPluginPackage(packageId: number) {
  return apiFetch<{ success: boolean; package: PluginReviewPackagesResponse["packages"][number] }>(
    `/api/plugins/review/packages/${packageId}/security-scan/`,
    { method: "POST" },
  );
}

export async function replayPluginPackageProvenance(packageId: number) {
  return apiFetch<{ success: boolean; package: PluginReviewPackagesResponse["packages"][number] }>(
    `/api/plugins/review/packages/${packageId}/replay-provenance/`,
    { method: "POST" },
  );
}

export function pluginPackageSbomUrl(packageId: number) {
  return `/api/plugins/review/packages/${packageId}/sbom/`;
}

export async function fetchPluginPackageRetention() {
  return apiFetch<{ success: boolean; retention: Record<string, unknown> }>("/api/plugins/packages/retention/");
}

export async function cleanupPluginPackageRetention(payload: { dry_run?: boolean; max_age_days?: number | null } = {}) {
  return apiFetch<{ success: boolean; result: Record<string, unknown> }>("/api/plugins/packages/retention/", {
    method: "POST",
    body: JSON.stringify({ dry_run: true, ...payload }),
  });
}

export async function installRemotePluginPackage(payload: { url: string; expected_sha256: string }) {
  return apiFetch<{ success: boolean; installation_id: number; status: string }>(
    "/api/plugins/packages/install-remote/",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function installLocalPluginPackageUpload(file: File) {
  const form = new FormData();
  form.append("package", file);
  return apiFetch<{
    success: boolean;
    installation_id: number;
    plugin_id: string;
    status: string;
    package: { id: number; version: string; review_status: string; signature_status: string };
  }>("/api/plugins/packages/install-local-upload/", {
    method: "POST",
    body: form,
    timeoutMs: 120_000,
  });
}

export async function quarantinePlugin(pluginId: string, reason = "") {
  return apiFetch<{ success: boolean; installation: PluginInstallationsResponse["installations"][number] }>("/api/plugins/quarantine/", {
    method: "POST",
    body: JSON.stringify({ plugin_id: pluginId, reason }),
  });
}

export async function fetchPluginPermissions(installationId: number) {
  return apiFetch<PluginPermissionsResponse>(`/api/plugins/installed/${installationId}/permissions/`);
}

export async function grantPluginPermission(installationId: number, scope: string) {
  return apiFetch<{ success: boolean; scope: string; granted: boolean }>(
    `/api/plugins/installed/${installationId}/permissions/grant/`,
    {
      method: "POST",
      body: JSON.stringify({ scope }),
    },
  );
}

export async function revokePluginPermission(installationId: number, scope: string) {
  return apiFetch<{ success: boolean; scope: string; granted: boolean }>(
    `/api/plugins/installed/${installationId}/permissions/revoke/`,
    {
      method: "POST",
      body: JSON.stringify({ scope }),
    },
  );
}

export async function runDemoPluginAction() {
  return apiFetch<{ success: boolean; message: string }>("/api/plugins/demo/action/", {
    method: "POST",
  });
}

export async function fetchMarketplaceSources() {
  return apiFetch<MarketplaceSourcesResponse>("/api/plugins/marketplace/sources/");
}

export async function createMarketplaceSource(payload: { name: string; source_url: string; is_enabled?: boolean }) {
  return apiFetch<{ success: boolean; source: MarketplaceSourcesResponse["sources"][number] }>(
    "/api/plugins/marketplace/sources/",
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function syncMarketplaceSource(sourceId: number, payload: Record<string, unknown>) {
  return apiFetch<{ success: boolean; synced: number }>(
    `/api/plugins/marketplace/sources/${sourceId}/sync/`,
    {
      method: "POST",
      body: JSON.stringify(payload),
    },
  );
}

export async function syncFederatedMarketplaceSource(sourceId: number) {
  return apiFetch<{ success: boolean; synced: number; source: MarketplaceSourcesResponse["sources"][number] }>(
    `/api/plugins/marketplace/sources/${sourceId}/sync-remote/`,
    { method: "POST" },
  );
}

export async function fetchMarketplaceCatalog() {
  return apiFetch<MarketplaceCatalogResponse>("/api/plugins/marketplace/catalog/");
}

export async function fetchMarketplaceCatalogItem(itemId: number) {
  return apiFetch<MarketplaceCatalogDetailResponse>(`/api/plugins/marketplace/catalog/${itemId}/`);
}

export async function installMarketplaceItem(itemId: number) {
  return apiFetch<{ success: boolean; installation_id: number; status: string }>(
    `/api/plugins/marketplace/catalog/${itemId}/install/`,
    { method: "POST" },
  );
}

export async function fetchMarketplaceCompatibilityJobs() {
  return apiFetch<MarketplaceCompatibilityJobsResponse>("/api/plugins/marketplace/compatibility-jobs/");
}

export async function runMarketplaceCompatibilityJob(catalogItemId: number) {
  return apiFetch<{ success: boolean; job: MarketplaceCompatibilityJobsResponse["jobs"][number] }>(
    "/api/plugins/marketplace/compatibility-jobs/",
    {
      method: "POST",
      body: JSON.stringify({ catalog_item_id: catalogItemId }),
    },
  );
}

export async function fetchPluginSettings(installationId: number) {
  return apiFetch<PluginSettingsResponse>(`/api/plugins/installed/${installationId}/settings/`);
}

export async function updatePluginSettings(installationId: number, settings: Record<string, unknown>) {
  return apiFetch<{ success: boolean; settings: Record<string, unknown> }>(
    `/api/plugins/installed/${installationId}/settings/update/`,
    {
      method: "POST",
      body: JSON.stringify({ settings }),
    },
  );
}

export async function bindPluginSecret(installationId: number, key: string, secret_ref: string) {
  return apiFetch<PluginSettingsResponse>(
    `/api/plugins/installed/${installationId}/secrets/bind/`,
    {
      method: "POST",
      body: JSON.stringify({ key, secret_ref }),
    },
  );
}

export async function fetchPluginSurfaces() {
  return apiFetch<PluginSurfacesResponse>("/api/plugins/surfaces/");
}

export async function fetchPluginPage(pluginId: string, pageId: string) {
  return apiFetch<PluginPageResponse>(
    `/api/plugins/pages/${encodeURIComponent(pluginId)}/${encodeURIComponent(pageId)}/`,
  );
}

export async function fetchPluginConnectorHealth(pluginId: string, connectorId: string) {
  return apiFetch<PluginConnectorHealthResponse>(
    `/api/plugins/connectors/${encodeURIComponent(pluginId)}/${encodeURIComponent(connectorId)}/health/`,
  );
}

export async function pingPluginConnector(pluginId: string, connectorId: string) {
  return apiFetch<{ success: boolean; status: string; connector_id: string }>(
    `/api/plugins/connectors/${encodeURIComponent(pluginId)}/${encodeURIComponent(connectorId)}/ping/`,
    { method: "POST" },
  );
}

export async function executePluginTerminalAction(pluginId: string, actionId: string) {
  return apiFetch<PluginTerminalActionExecuteResponse>(
    `/api/plugins/terminal-actions/${encodeURIComponent(pluginId)}/${encodeURIComponent(actionId)}/execute/`,
    { method: "POST" },
  );
}
