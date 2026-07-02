import type { KubernetesProviderKind } from "@/api/kubernetes";

export interface KubernetesAdminApiResourceCatalogItem {
  api_version: string;
  group: string;
  version: string;
  kind: string;
  resource: string;
  namespaced: boolean;
  verbs: string[];
  short_names: string[];
  categories: string[];
  singular_name?: string;
  source?: string;
}

export interface KubernetesAdminCrdCatalogItem {
  api_version: string;
  group: string;
  version: string;
  kind: string;
  resource: string;
  namespaced: boolean;
  scope: string;
  short_names: string[];
  categories: string[];
  storage?: boolean;
  crd_name?: string;
}

export interface KubernetesAdminResourceCatalogItem extends KubernetesAdminApiResourceCatalogItem {
  id: string;
  scope: string;
  sources: string[];
  cluster_available: boolean;
  custom: boolean;
  ui_group: string;
  safe_read_actions: string[];
  has_mutating_verbs: boolean;
  query: { api_version: string; kind: string; resource: string };
  crd_name?: string;
}

export interface KubernetesAdminResourceCatalogGroup {
  id: string;
  label: string;
  item_count: number;
  cluster_available_count: number;
  custom_count: number;
  namespaced_count: number;
  cluster_scoped_count: number;
}

export interface KubernetesAdminDiscoverySection<TItem> {
  status: string;
  items: TItem[];
  item_count: number;
  truncated: boolean;
  raw_payload_included?: boolean;
  schema_included?: boolean;
  reason?: string;
  path?: string;
}

export interface KubernetesAdminResourceCatalogSection
  extends KubernetesAdminDiscoverySection<KubernetesAdminResourceCatalogItem> {
  source: string;
  counts: {
    total: number;
    cluster_available: number;
    common: number;
    custom: number;
    namespaced: number;
    cluster_scoped: number;
    with_mutating_verbs: number;
  };
  groups: KubernetesAdminResourceCatalogGroup[];
  group_count: number;
  raw_payload_included: false;
}

export interface KubernetesAdminResourceDiscoveryResponse {
  success: boolean;
  mode: "admin_read_only" | string;
  operation: "discovery" | string;
  cluster: { id: string; name: string; rancher_cluster_id: string };
  provider: { id: number; name: string; kind: KubernetesProviderKind };
  paths: { core: string; groups: string; crds?: string };
  core: Record<string, unknown>;
  groups: Record<string, unknown>;
  api_resources?: KubernetesAdminDiscoverySection<KubernetesAdminApiResourceCatalogItem>;
  common_resources: Array<{ api_version: string; kind: string; resource: string; namespaced: boolean }>;
  crd_resources?: KubernetesAdminDiscoverySection<KubernetesAdminCrdCatalogItem>;
  resource_catalog?: KubernetesAdminResourceCatalogSection;
}
