import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import {
  createKubernetesAdminSession,
  fetchKubernetesAdminDiscovery,
  fetchKubernetesAdminPodLogs,
  fetchKubernetesAdminResourceDetail,
  fetchKubernetesAdminResourceWatch,
  fetchKubernetesAdminResourceYaml,
  fetchKubernetesAdminResources,
  fetchKubernetesAdminSessions,
  fetchKubernetesClusters,
  fetchKubernetesReadiness,
} from "@/api";
import type { KubernetesAdminResourceDetailResponse, KubernetesAdminResourceDiscoveryResponse } from "@/api/kubernetes-admin";
import { I18nProvider } from "@/lib/i18n";
import KubernetesAdminPage from "@/pages/KubernetesAdminPage";

vi.mock("@/api", () => ({
  createKubernetesAdminSession: vi.fn(),
  fetchKubernetesAdminDiscovery: vi.fn(),
  fetchKubernetesAdminPodLogs: vi.fn(),
  fetchKubernetesAdminResourceDetail: vi.fn(),
  fetchKubernetesAdminResourceWatch: vi.fn(),
  fetchKubernetesAdminResourceYaml: vi.fn(),
  fetchKubernetesAdminResources: vi.fn(),
  fetchKubernetesAdminSessions: vi.fn(),
  fetchKubernetesClusters: vi.fn(),
  fetchKubernetesReadiness: vi.fn(),
}));

const cluster = {
  id: "cluster_1",
  database_id: 1,
  name: "prod-kz-1",
  environment: "prod",
  provider: "rancher",
  health: "healthy",
  nodes_ready: 2,
  nodes_total: 2,
  namespaces: 2,
  workloads: 3,
  apps: 3,
  fleet_bundles: 1,
  devtron_apps: 1,
  labels: {},
  links: {},
  last_sync_at: "2026-07-01T07:00:00Z",
  sync_status: "fresh",
  is_stale: false,
  sync_age_seconds: 10,
  sync_stale_after_seconds: 900,
  created_at: null,
  updated_at: null,
};

const session = {
  id: "11111111-1111-1111-1111-111111111111",
  database_id: 1,
  mode: "read",
  status: "active",
  risk_tier: "low",
  cluster_id: "cluster_1",
  cluster_name: "prod-kz-1",
  provider_id: 1,
  provider_name: "rancher-main",
  namespace: "default",
  reason: "",
  approval_ref: "",
  approved_by: "",
  approved_at: null,
  expires_at: "2026-07-01T08:00:00Z",
  closed_at: null,
  allowed_verbs: ["get", "list", "watch", "logs", "yaml"],
  allowed_kinds: ["*"],
  allowed_namespaces: ["*"],
  metadata: {},
  created_by: "admin",
  created_at: "2026-07-01T07:00:00Z",
  updated_at: "2026-07-01T07:00:00Z",
};

const deploymentItem = {
  apiVersion: "apps/v1",
  kind: "Deployment",
  metadata: {
    name: "payments-api",
    namespace: "default",
    creationTimestamp: "2026-07-01T07:00:00Z",
    resourceVersion: "21",
    labels: { token: "[redacted]" },
  },
  spec: { replicas: 2 },
  status: { readyReplicas: 1, replicas: 2 },
  webterm_ownership: {
    owner: "devtron",
    confidence: "normalized_inventory",
    change_path: "devtron_app_flow",
    direct_apply_policy: "blocked_by_default",
    current_mode: "read_only",
    warnings: ["Devtron-owned resource"],
    evidence: ["matched_devtron_app"],
    workload: null,
    app: { id: "app_1", name: "payments-api", namespace: "default", owner: "devtron", labels: { token: "[redacted]" } },
    fleet_bundle: null,
  },
};

const podItem = {
  apiVersion: "v1",
  kind: "Pod",
  metadata: {
    name: "payments-api-abc123",
    namespace: "default",
    creationTimestamp: "2026-07-01T07:01:00Z",
    resourceVersion: "22",
  },
  status: { phase: "Running" },
  webterm_ownership: deploymentItem.webterm_ownership,
};

const widgetItem = {
  apiVersion: "example.com/v1",
  kind: "Widget",
  metadata: {
    name: "main-widget",
    namespace: "default",
    creationTimestamp: "2026-07-01T07:02:00Z",
    resourceVersion: "23",
  },
  status: { phase: "Ready" },
};

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <MemoryRouter>
          <KubernetesAdminPage />
        </MemoryRouter>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("KubernetesAdminPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchKubernetesReadiness).mockResolvedValue({
      success: true,
      status: "configured",
      ready_for_sidebar: false,
      summary: { ready: 10, missing: 0, manual: 0, total: 10 },
      checks: [],
      worker_state: {
        worker_kind: "kubernetes_ops_sync",
        worker_key: "compose",
        status: "running",
        is_stale: false,
        hostname: "worker",
        pid: 123,
        heartbeat_at: "2026-07-01T07:00:00Z",
        lease_expires_at: "2026-07-01T07:05:00Z",
        last_started_at: "2026-07-01T07:00:00Z",
        last_stopped_at: null,
        last_cycle_started_at: "2026-07-01T07:00:00Z",
        last_cycle_finished_at: "2026-07-01T07:01:00Z",
        last_summary: {},
        last_error: "",
      },
      access_policy: {
        can_admin_read: true,
        can_live_resource_watch: true,
        can_view_full_yaml: true,
        can_apply_yaml: false,
        can_exec: false,
        can_port_forward: false,
        blocked_capabilities: ["pod.exec", "port_forward", "apply_yaml"],
      },
    });
    vi.mocked(fetchKubernetesClusters).mockResolvedValue({ success: true, clusters: [cluster] });
    vi.mocked(fetchKubernetesAdminSessions).mockResolvedValue({ success: true, sessions: [] });
    vi.mocked(createKubernetesAdminSession).mockResolvedValue({ success: true, session });
    vi.mocked(fetchKubernetesAdminDiscovery).mockResolvedValue(discoveryFixture());
    vi.mocked(fetchKubernetesAdminResources).mockImplementation(async (_clusterId, query) => resourceListFixture(query));
    vi.mocked(fetchKubernetesAdminResourceDetail).mockImplementation(async (_clusterId, query) => detailFixture(query));
    vi.mocked(fetchKubernetesAdminResourceYaml).mockImplementation(async (_clusterId, query) => yamlFixture(query));
    vi.mocked(fetchKubernetesAdminPodLogs).mockResolvedValue({
      success: true,
      mode: "admin_read_only",
      operation: "pod_logs_snapshot",
      cluster: { id: "cluster_1", name: "prod-kz-1", rancher_cluster_id: "c-prod" },
      provider: { id: 1, name: "rancher-main", kind: "rancher" },
      target: { api_version: "v1", kind: "Pod", resource: "pods", namespace: "default", name: "payments-api-abc123", container: "" },
      path: "/v3/pods/default:payments-api-abc123/logs",
      available: true,
      source: "provider_snapshot",
      lines: ["boot ok", "token=[redacted]", "ready"],
      line_count: 3,
      truncated: false,
      message: "",
      policy: {
        mutates_state: false,
        requires_active_admin_session: true,
        streaming: false,
        source: "rancher_provider_json",
        requested_tail_lines: 120,
        max_tail_lines: 500,
        blocked_actions: ["exec", "attach", "logs_streaming", "follow_stream"],
      },
    });
    vi.mocked(fetchKubernetesAdminResourceWatch).mockImplementation(async (_clusterId, query) => ({
      success: true,
      mode: "admin_read_only",
      operation: "resource_watch_preview",
      cluster: { id: "cluster_1", name: "prod-kz-1", rancher_cluster_id: "c-prod" },
      provider: { id: 1, name: "rancher-main", kind: "rancher" },
      target: {
        api_version: query.api_version || "apps/v1",
        kind: query.kind || "Deployment",
        resource: query.resource || "deployments",
        namespace: query.namespace || "default",
        name: query.name || "",
      },
      path: "/k8s/clusters/c-prod/watch",
      available: true,
      source: "provider_watch_preview",
      events: [
        {
          type: "MODIFIED",
          object: { apiVersion: query.api_version, kind: query.kind, metadata: { name: query.name || "payments-api", namespace: query.namespace || "default", resourceVersion: "22" } },
          resource_version: "22",
          redacted: false,
        },
      ],
      event_count: 1,
      truncated: false,
      latest_resource_version: "22",
      message: "",
      policy: {
        mutates_state: false,
        requires_active_admin_session: true,
        streaming: false,
        future_stream_transport: "websocket_or_sse",
        max_events: 50,
        requested_limit: 20,
        timeout_seconds: 10,
        blocked_actions: ["apply_yaml", "delete", "exec"],
      },
    }));
  });

  it("creates a read session, uses resource_catalog for list/detail, and renders redacted YAML", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "Ресурсы кластера" })).toBeInTheDocument();
    expect((await screen.findAllByText("prod-kz-1")).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: /Создать сессию чтения|Create read session/ }));
    expect(await screen.findByText(session.id)).toBeInTheDocument();

    await waitFor(() => expect(fetchKubernetesAdminDiscovery).toHaveBeenCalledWith("cluster_1", session.id));
    expect(await screen.findByText("Workloads")).toBeInTheDocument();
    expect(await screen.findByText("payments-api")).toBeInTheDocument();
    expect(fetchKubernetesAdminResources).toHaveBeenCalledWith("cluster_1", {
      session_id: session.id,
      api_version: "apps/v1",
      kind: "Deployment",
      resource: "deployments",
      namespace: "default",
    });

    fireEvent.click(screen.getByText("payments-api"));
    await waitFor(() => expect(fetchKubernetesAdminResourceDetail).toHaveBeenCalledWith("cluster_1", {
      session_id: session.id,
      api_version: "apps/v1",
      kind: "Deployment",
      resource: "deployments",
      namespace: "default",
      name: "payments-api",
      include_events: true,
      event_limit: 20,
    }));
    expect((await screen.findAllByText("devtron_app_flow")).length).toBeGreaterThan(0);

    fireEvent.mouseDown(screen.getByRole("tab", { name: "YAML" }));
    expect(await screen.findByText(/"\[redacted\]"/)).toBeInTheDocument();
    expect(fetchKubernetesAdminResourceYaml).toHaveBeenCalledWith("cluster_1", {
      session_id: session.id,
      api_version: "apps/v1",
      kind: "Deployment",
      resource: "deployments",
      namespace: "default",
      name: "payments-api",
    });
  });

  it("runs a pod logs snapshot from the selected catalog resource", async () => {
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /Создать сессию чтения|Create read session/ }));
    expect(await screen.findByText(session.id)).toBeInTheDocument();
    await screen.findByText("payments-api");

    fireEvent.click(screen.getByRole("button", { name: /Pod\s+pods/i }));
    expect(await screen.findByText("payments-api-abc123")).toBeInTheDocument();
    fireEvent.click(screen.getByText("payments-api-abc123"));
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Логи" }));

    expect((await screen.findAllByText("Логи")).length).toBeGreaterThan(0);
    expect((await screen.findAllByText(/token=\[redacted\]/)).length).toBeGreaterThan(0);
    expect(fetchKubernetesAdminPodLogs).toHaveBeenCalledWith("cluster_1", {
      session_id: session.id,
      namespace: "default",
      pod: "payments-api-abc123",
      tail: 120,
    });
  });

  it("preserves exact CRD resource plural for list/detail/watch", async () => {
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /Создать сессию чтения|Create read session/ }));
    expect(await screen.findByText(session.id)).toBeInTheDocument();
    await screen.findByText("payments-api");

    fireEvent.click(screen.getByRole("button", { name: /Widget\s+widgets/i }));
    expect(await screen.findByText("main-widget")).toBeInTheDocument();
    fireEvent.click(screen.getByText("main-widget"));
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Изменения" }));

    expect(await screen.findByText("1 событий")).toBeInTheDocument();
    expect(fetchKubernetesAdminResources).toHaveBeenCalledWith("cluster_1", {
      session_id: session.id,
      api_version: "example.com/v1",
      kind: "Widget",
      resource: "widgets",
      namespace: "default",
    });
    expect(fetchKubernetesAdminResourceWatch).toHaveBeenCalledWith("cluster_1", {
      session_id: session.id,
      api_version: "example.com/v1",
      kind: "Widget",
      resource: "widgets",
      namespace: "default",
      name: "main-widget",
      limit: 20,
      timeout_seconds: 10,
    });
  });
});

function discoveryFixture(): KubernetesAdminResourceDiscoveryResponse {
  return {
    success: true,
    mode: "admin_read_only",
    operation: "discovery",
    cluster: { id: "cluster_1", name: "prod-kz-1", rancher_cluster_id: "c-prod" },
    provider: { id: 1, name: "rancher-main", kind: "rancher" },
    paths: { core: "/k8s/clusters/c-prod/api/v1", groups: "/k8s/clusters/c-prod/apis" },
    core: { resources: [{ name: "pods", kind: "Pod", namespaced: true }] },
    groups: { groups: [{ name: "apps" }] },
    common_resources: [{ api_version: "apps/v1", kind: "Deployment", resource: "deployments", namespaced: true }],
    resource_catalog: {
      status: "ready",
      source: "merged_common_api_crd_discovery",
      item_count: 3,
      counts: { total: 3, cluster_available: 3, common: 2, custom: 1, namespaced: 3, cluster_scoped: 0, with_mutating_verbs: 0 },
      groups: [
        { id: "custom", label: "Custom resources", item_count: 1, cluster_available_count: 1, custom_count: 1, namespaced_count: 1, cluster_scoped_count: 0 },
        { id: "workloads", label: "Workloads", item_count: 2, cluster_available_count: 2, custom_count: 0, namespaced_count: 2, cluster_scoped_count: 0 },
      ],
      group_count: 2,
      truncated: false,
      raw_payload_included: false,
      items: [
        catalogItem("apps/v1:deployments", "apps/v1", "Deployment", "deployments", "workloads", false, ["list", "detail", "yaml", "watch"]),
        catalogItem("v1:pods", "v1", "Pod", "pods", "workloads", false, ["list", "detail", "yaml", "watch", "logs"]),
        catalogItem("example.com/v1:widgets", "example.com/v1", "Widget", "widgets", "custom", true, ["list", "detail", "yaml", "watch"]),
      ],
    },
  };
}

function catalogItem(id: string, apiVersion: string, kind: string, resource: string, uiGroup: string, custom: boolean, safeReadActions: string[]) {
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
    sources: custom ? ["api", "crd"] : ["common", "api"],
    cluster_available: true,
    custom,
    query: { api_version: apiVersion, kind, resource },
  };
}

function resourceListFixture(query: { api_version?: string; kind?: string; resource?: string; namespace?: string }) {
  const items = query.kind === "Pod" ? [podItem] : query.kind === "Widget" ? [widgetItem] : [deploymentItem];
  return {
    success: true,
    mode: "admin_read_only",
    operation: "resource_list",
    cluster: { id: "cluster_1", name: "prod-kz-1", rancher_cluster_id: "c-prod" },
    provider: { id: 1, name: "rancher-main", kind: "rancher" },
    target: {
      api_version: query.api_version || "apps/v1",
      kind: query.kind || "Deployment",
      resource: query.resource || "deployments",
      namespace: query.namespace || "default",
      name: "",
    },
    path: "/k8s/clusters/c-prod/resources",
    policy: { mutates_state: false, requires_active_admin_session: true, blocked_actions: ["apply_yaml", "delete", "exec"] },
    items,
    item_count: items.length,
    truncated: false,
    ownership_summary: query.kind === "Deployment" ? { owners: { devtron: 1 }, guarded_items: 1, total: 1 } : undefined,
  };
}

function detailFixture(query: { api_version?: string; kind?: string; resource?: string; namespace?: string; name?: string }): KubernetesAdminResourceDetailResponse {
  const resource = query.kind === "Widget" ? widgetItem : query.kind === "Pod" ? podItem : deploymentItem;
  return {
    ...yamlFixture(query),
    operation: "resource_detail",
    paths: { resource: "/api/v1/resource", events: "/api/v1/events" },
    describe: { identity: { name: query.name, kind: query.kind } },
    resource,
    events: {
      available: true,
      requested: true,
      events: [
        {
          name: "event-1",
          namespace: query.namespace || "default",
          type: "Warning",
          reason: "Unhealthy",
          message: "Readiness probe failed",
          source: {},
          reporting_controller: "",
          reporting_instance: "",
          involved_object: {},
          count: 2,
          first_timestamp: "2026-07-01T07:00:00Z",
          last_timestamp: "2026-07-01T07:01:00Z",
          event_time: "",
          resource_version: "10",
          redacted: true,
        },
      ],
      event_count: 1,
      truncated: false,
      redacted: true,
    },
  };
}

function yamlFixture(query: { api_version?: string; kind?: string; resource?: string; namespace?: string; name?: string }) {
  const resource = query.kind === "Widget" ? widgetItem : query.kind === "Pod" ? podItem : deploymentItem;
  return {
    success: true,
    mode: "admin_read_only",
    operation: "resource_yaml",
    cluster: { id: "cluster_1", name: "prod-kz-1", rancher_cluster_id: "c-prod" },
    provider: { id: 1, name: "rancher-main", kind: "rancher" },
    target: {
      api_version: query.api_version || "apps/v1",
      kind: query.kind || "Deployment",
      resource: query.resource || "deployments",
      namespace: query.namespace || "default",
      name: query.name || "",
    },
    path: "/k8s/clusters/c-prod/yaml",
    policy: { mutates_state: false, requires_active_admin_session: true, blocked_actions: ["apply_yaml", "delete", "exec"] },
    resource,
    redacted: true,
    ownership: query.kind === "Deployment" ? deploymentItem.webterm_ownership : undefined,
  };
}
