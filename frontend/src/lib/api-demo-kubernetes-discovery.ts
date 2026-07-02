export function demoKubernetesAdminDiscovery() {
  return {
    success: true,
    mode: "admin_read_only",
    operation: "discovery",
    cluster: { id: "cluster_demo", name: "demo-cluster", rancher_cluster_id: "demo" },
    provider: { id: 0, name: "demo-rancher", kind: "rancher" },
    paths: {
      core: "/k8s/clusters/demo/api/v1",
      groups: "/k8s/clusters/demo/apis",
      crds: "/k8s/clusters/demo/apis/apiextensions.k8s.io/v1/customresourcedefinitions",
    },
    core: { resources: [{ name: "pods", kind: "Pod", namespaced: true }] },
    groups: { groups: [{ name: "apps", versions: [{ groupVersion: "apps/v1", version: "v1" }] }] },
    api_resources: {
      status: "ready",
      items: [
        demoApiResource("v1", "", "v1", "Pod", "pods", ["po"], "core"),
        demoApiResource("apps/v1", "apps", "v1", "Deployment", "deployments", ["deploy"], "group"),
      ],
      item_count: 2,
      truncated: false,
      raw_payload_included: false,
    },
    common_resources: [
      { api_version: "apps/v1", kind: "Deployment", resource: "deployments", namespaced: true },
      { api_version: "v1", kind: "Pod", resource: "pods", namespaced: true },
      { api_version: "v1", kind: "Secret", resource: "secrets", namespaced: true },
    ],
    crd_resources: {
      status: "ready",
      items: [
        {
          api_version: "example.com/v1",
          group: "example.com",
          version: "v1",
          kind: "Widget",
          resource: "widgets",
          namespaced: true,
          scope: "Namespaced",
          short_names: ["wdg"],
          categories: ["all"],
          storage: true,
          crd_name: "widgets.example.com",
        },
      ],
      item_count: 1,
      truncated: false,
      schema_included: false,
    },
    resource_catalog: {
      status: "ready",
      source: "merged_common_api_crd_discovery",
      items: [
        demoCatalogItem("apps/v1:deployments", "apps/v1", "Deployment", "deployments", "workloads", ["common", "api"], false),
        demoCatalogItem("v1:pods", "v1", "Pod", "pods", "workloads", ["common", "api"], false, ["list", "detail", "yaml", "watch", "logs"]),
        demoCatalogItem("v1:secrets", "v1", "Secret", "secrets", "config", ["common"], false),
        demoCatalogItem("example.com/v1:widgets", "example.com/v1", "Widget", "widgets", "custom", ["api", "crd"], true),
      ],
      item_count: 4,
      counts: { total: 4, cluster_available: 3, common: 3, custom: 1, namespaced: 4, cluster_scoped: 0, with_mutating_verbs: 0 },
      groups: [
        demoCatalogGroup("config", "Config", 1, 0, 0, 1, 0),
        demoCatalogGroup("custom", "Custom resources", 1, 1, 1, 1, 0),
        demoCatalogGroup("workloads", "Workloads", 2, 2, 0, 2, 0),
      ],
      group_count: 3,
      truncated: false,
      raw_payload_included: false,
    },
  };
}

function demoApiResource(apiVersion: string, group: string, version: string, kind: string, resource: string, shortNames: string[], source: string) {
  return {
    api_version: apiVersion,
    group,
    version,
    kind,
    resource,
    namespaced: true,
    verbs: ["get", "list", "watch"],
    short_names: shortNames,
    categories: ["all"],
    singular_name: kind.toLowerCase(),
    source,
  };
}

function demoCatalogItem(
  id: string,
  apiVersion: string,
  kind: string,
  resource: string,
  uiGroup: string,
  sources: string[],
  custom: boolean,
  safeReadActions: string[] = ["list", "detail", "yaml", "watch"],
) {
  const [group, version] = apiVersion.includes("/") ? apiVersion.split("/", 2) : ["", apiVersion];
  return {
    id,
    api_version: apiVersion,
    group,
    version,
    kind,
    resource,
    namespaced: true,
    scope: "Namespaced",
    verbs: ["get", "list", "watch"],
    short_names: [],
    categories: [],
    ui_group: uiGroup,
    safe_read_actions: safeReadActions,
    has_mutating_verbs: false,
    sources,
    cluster_available: sources.includes("api") || sources.includes("crd"),
    custom,
    query: { api_version: apiVersion, kind, resource },
  };
}

function demoCatalogGroup(id: string, label: string, itemCount: number, clusterAvailable: number, custom: number, namespaced: number, clusterScoped: number) {
  return {
    id,
    label,
    item_count: itemCount,
    cluster_available_count: clusterAvailable,
    custom_count: custom,
    namespaced_count: namespaced,
    cluster_scoped_count: clusterScoped,
  };
}
