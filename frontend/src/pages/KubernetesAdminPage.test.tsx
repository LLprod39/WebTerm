import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import {
  createKubernetesAdminSession,
  fetchKubernetesAdminCrds,
  fetchKubernetesAdminDiscovery,
  fetchKubernetesAdminPodLogs,
  fetchKubernetesAdminResourceYaml,
  fetchKubernetesAdminResources,
  fetchKubernetesAdminResourceWatch,
  fetchKubernetesAdminSessions,
  fetchKubernetesClusters,
  fetchKubernetesReadiness,
} from "@/api";
import { I18nProvider } from "@/lib/i18n";
import KubernetesAdminPage from "@/pages/KubernetesAdminPage";

vi.mock("@/api", () => ({
  createKubernetesAdminSession: vi.fn(),
  fetchKubernetesAdminCrds: vi.fn(),
  fetchKubernetesAdminDiscovery: vi.fn(),
  fetchKubernetesAdminPodLogs: vi.fn(),
  fetchKubernetesAdminResourceYaml: vi.fn(),
  fetchKubernetesAdminResources: vi.fn(),
  fetchKubernetesAdminResourceWatch: vi.fn(),
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
    vi.mocked(fetchKubernetesAdminResources).mockResolvedValue({
      success: true,
      mode: "admin_read_only",
      operation: "resource_list",
      cluster: { id: "cluster_1", name: "prod-kz-1", rancher_cluster_id: "c-prod" },
      provider: { id: 1, name: "rancher-main", kind: "rancher" },
      target: { api_version: "apps/v1", kind: "Deployment", resource: "deployments", namespace: "default", name: "" },
      path: "/k8s/clusters/c-prod/apis/apps/v1/namespaces/default/deployments",
      policy: { mutates_state: false, requires_active_admin_session: true, blocked_actions: ["apply_yaml", "delete", "exec"] },
      items: [
        {
          apiVersion: "apps/v1",
          kind: "Deployment",
          metadata: { name: "payments-api", namespace: "default", labels: { token: "[redacted]" } },
          spec: { replicas: 2 },
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
        },
      ],
      item_count: 1,
      truncated: false,
      ownership_summary: { owners: { devtron: 1 }, guarded_items: 1, total: 1 },
    });
    vi.mocked(fetchKubernetesAdminResourceYaml).mockResolvedValue({
      success: true,
      mode: "admin_read_only",
      operation: "resource_yaml",
      cluster: { id: "cluster_1", name: "prod-kz-1", rancher_cluster_id: "c-prod" },
      provider: { id: 1, name: "rancher-main", kind: "rancher" },
      target: { api_version: "apps/v1", kind: "Deployment", resource: "deployments", namespace: "default", name: "payments-api" },
      path: "/k8s/clusters/c-prod/apis/apps/v1/namespaces/default/deployments/payments-api",
      policy: { mutates_state: false, requires_active_admin_session: true, blocked_actions: ["apply_yaml", "delete", "exec"] },
      resource: {
        apiVersion: "apps/v1",
        kind: "Deployment",
        metadata: { name: "payments-api", namespace: "default", labels: { token: "[redacted]" } },
        spec: { replicas: 2 },
      },
      redacted: true,
      ownership: {
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
    });
    vi.mocked(fetchKubernetesAdminCrds).mockResolvedValue({
      success: true,
      mode: "admin_read_only",
      operation: "crd_list",
      cluster: { id: "cluster_1", name: "prod-kz-1", rancher_cluster_id: "c-prod" },
      provider: { id: 1, name: "rancher-main", kind: "rancher" },
      target: { api_version: "apiextensions.k8s.io/v1", kind: "CustomResourceDefinition", resource: "customresourcedefinitions", namespace: "", name: "" },
      path: "/k8s/clusters/c-prod/apis/apiextensions.k8s.io/v1/customresourcedefinitions",
      policy: { mutates_state: false, requires_active_admin_session: true, blocked_actions: ["apply_yaml", "delete", "exec"] },
      items: [],
      item_count: 0,
      truncated: false,
    });
    vi.mocked(fetchKubernetesAdminDiscovery).mockResolvedValue({
      success: true,
      mode: "admin_read_only",
      operation: "discovery",
      cluster: { id: "cluster_1", name: "prod-kz-1", rancher_cluster_id: "c-prod" },
      provider: { id: 1, name: "rancher-main", kind: "rancher" },
      paths: { core: "/k8s/clusters/c-prod/api/v1", groups: "/k8s/clusters/c-prod/apis" },
      core: { resources: [{ name: "pods", kind: "Pod", namespaced: true }] },
      groups: { groups: [{ name: "apps" }] },
      common_resources: [{ api_version: "apps/v1", kind: "Deployment", resource: "deployments", namespaced: true }],
    });
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
    vi.mocked(fetchKubernetesAdminResourceWatch).mockResolvedValue({
      success: true,
      mode: "admin_read_only",
      operation: "resource_watch_preview",
      cluster: { id: "cluster_1", name: "prod-kz-1", rancher_cluster_id: "c-prod" },
      provider: { id: 1, name: "rancher-main", kind: "rancher" },
      target: { api_version: "apps/v1", kind: "Deployment", resource: "deployments", namespace: "default", name: "" },
      path: "/k8s/clusters/c-prod/apis/apps/v1/namespaces/default/deployments",
      available: true,
      source: "provider_watch_preview",
      events: [
        {
          type: "MODIFIED",
          object: { apiVersion: "apps/v1", kind: "Deployment", metadata: { name: "payments-api", namespace: "default", resourceVersion: "22" } },
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
    });
  });

  it("creates a read session, lists resources, and renders redacted YAML", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "Resource explorer" })).toBeInTheDocument();
    expect(await screen.findByText("prod-kz-1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Создать read session|Create read session/ }));

    await waitFor(() => expect(createKubernetesAdminSession).toHaveBeenCalledWith({
      mode: "read",
      cluster_id: "cluster_1",
      namespace: "default",
      ttl_minutes: 60,
      allowed_kinds: ["*"],
      allowed_namespaces: ["*"],
    }));
    expect(await screen.findByText(session.id)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "List" }));
    expect(await screen.findByText("payments-api")).toBeInTheDocument();
    expect(await screen.findByText("Ownership summary")).toBeInTheDocument();
    expect(screen.getAllByText("Devtron").length).toBeGreaterThan(0);
    expect(fetchKubernetesAdminResources).toHaveBeenCalledWith("cluster_1", {
      session_id: session.id,
      api_version: "apps/v1",
      kind: "Deployment",
      namespace: "default",
      name: "",
    });
    expect(screen.getByText(/"\[redacted\]"/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Resource name"), { target: { value: "payments-api" } });
    fireEvent.click(screen.getByRole("button", { name: "YAML" }));
    expect(await screen.findByText("redacted")).toBeInTheDocument();
    expect(await screen.findByText("devtron_app_flow")).toBeInTheDocument();
    expect(fetchKubernetesAdminResourceYaml).toHaveBeenCalledWith("cluster_1", {
      session_id: session.id,
      api_version: "apps/v1",
      kind: "Deployment",
      namespace: "default",
      name: "payments-api",
    });
  });

  it("runs a pod logs snapshot through the active admin session", async () => {
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /Создать read session|Create read session/ }));
    expect(await screen.findByText(session.id)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("combobox", { name: "Resource kind" }));
    fireEvent.click(await screen.findByRole("option", { name: "Pod" }));
    fireEvent.change(screen.getByLabelText("Resource name"), { target: { value: "payments-api-abc123" } });
    fireEvent.click(screen.getByRole("button", { name: "Logs" }));

    expect(await screen.findByText("Logs snapshot")).toBeInTheDocument();
    expect((await screen.findAllByText(/token=\[redacted\]/)).length).toBeGreaterThan(0);
    expect(fetchKubernetesAdminPodLogs).toHaveBeenCalledWith("cluster_1", {
      session_id: session.id,
      namespace: "default",
      pod: "payments-api-abc123",
      tail: 120,
    });
  });

  it("runs a bounded watch preview through the active admin session", async () => {
    renderPage();

    fireEvent.click(await screen.findByRole("button", { name: /Создать read session|Create read session/ }));
    expect(await screen.findByText(session.id)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Watch" }));

    expect((await screen.findAllByText("Watch preview")).length).toBeGreaterThan(0);
    expect(await screen.findByText("1 events")).toBeInTheDocument();
    expect(fetchKubernetesAdminResourceWatch).toHaveBeenCalledWith("cluster_1", {
      session_id: session.id,
      api_version: "apps/v1",
      kind: "Deployment",
      namespace: "default",
      name: "",
      limit: 20,
      timeout_seconds: 10,
    });
  });
});
