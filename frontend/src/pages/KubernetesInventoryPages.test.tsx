import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { ReactNode } from "react";

import {
  createKubernetesActionRequest,
  fetchAuthSession,
  fetchKubernetesActionReport,
  fetchKubernetesCluster,
  fetchKubernetesClusterEvents,
  fetchKubernetesClusterNetwork,
  fetchKubernetesClusterNamespaces,
  fetchKubernetesClusterPods,
  fetchKubernetesClusterWorkloads,
  fetchKubernetesDevtronApps,
  fetchKubernetesFleetBundles,
  fetchKubernetesPodLogs,
  fetchKubernetesWorkloadDescribe,
} from "@/api";
import { I18nProvider } from "@/lib/i18n";
import KubernetesClusterDetailPage from "@/pages/KubernetesClusterDetailPage";
import KubernetesDevtronPage from "@/pages/KubernetesDevtronPage";
import KubernetesFleetPage from "@/pages/KubernetesFleetPage";

vi.mock("@/api", () => ({
  approveExternalKubernetesAction: vi.fn(),
  createKubernetesActionRequest: vi.fn(),
  fetchAuthSession: vi.fn(),
  fetchKubernetesActionReport: vi.fn(),
  fetchKubernetesCluster: vi.fn(),
  fetchKubernetesClusterEvents: vi.fn(),
  fetchKubernetesClusterNetwork: vi.fn(),
  fetchKubernetesClusterNamespaces: vi.fn(),
  fetchKubernetesClusterPods: vi.fn(),
  fetchKubernetesClusterWorkloads: vi.fn(),
  fetchKubernetesDevtronApps: vi.fn(),
  fetchKubernetesFleetBundles: vi.fn(),
  fetchKubernetesPodLogs: vi.fn(),
  fetchKubernetesWorkloadDescribe: vi.fn(),
  recordKubernetesDeepLink: vi.fn(),
  verifyExternalKubernetesAction: vi.fn(),
}));

const cluster = {
  id: "cluster_1",
  database_id: 1,
  name: "prod-kz-1",
  environment: "prod",
  provider: "rancher",
  health: "warning",
  nodes_ready: 2,
  nodes_total: 3,
  namespaces: 1,
  workloads: 1,
  apps: 1,
  fleet_bundles: 0,
  devtron_apps: 1,
  labels: {},
  links: {},
  last_sync_at: "2026-06-29T19:00:00Z",
  created_at: null,
  updated_at: null,
};

const app = {
  id: "app_1",
  database_id: 1,
  name: "payments-api",
  cluster_id: "cluster_1",
  cluster_name: "prod-kz-1",
  namespace: "payments",
  environment: "prod",
  owner: "devtron",
  team: "payments",
  health: "warning",
  kind: "deployment",
  ready: 1,
  desired: 2,
  version: "2026.06.30-1",
  links: {},
  labels: {},
  last_sync_at: "2026-06-29T19:00:00Z",
};

function renderRoute(path: string, element: ReactNode) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path={path.includes("clusters") ? "/kubernetes/clusters/:clusterId" : path} element={element} />
          </Routes>
        </MemoryRouter>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("Kubernetes inventory pages", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchAuthSession).mockResolvedValue({
      authenticated: true,
      user: {
        id: 1,
        username: "admin",
        email: "admin@example.com",
        is_staff: true,
        features: { kubernetes: true },
      },
    });
    vi.mocked(fetchKubernetesCluster).mockResolvedValue({ success: true, cluster });
    vi.mocked(createKubernetesActionRequest).mockResolvedValue({
      success: true,
      request: {
        id: "11111111-1111-1111-1111-111111111111",
        database_id: 1,
        action: "k8s.rollout.restart",
        status: "pending_approval",
        risk_tier: "high",
        cluster: "prod-kz-1",
        target: { cluster_id: "cluster_1", namespace: "payments", kind: "deployment", name: "payments-api" },
        preview: {
          blast_radius: "single_workload",
          affected: [{ cluster_id: "cluster_1", namespace: "payments", kind: "deployment", name: "payments-api" }],
          expected_verification: ["workload rollout status", "pod readiness"],
        },
        execution_policy: {
          approval_required: true,
          dry_run_required: true,
          verification_required: true,
          native_execution_enabled: false,
          blocked_reason: "WebTerm currently records the request only.",
        },
        report: {},
        reason: "Operator requested restart approval for payments/payments-api",
        approval_ref: "",
        requested_by: "admin",
        created_at: "2026-06-30T08:00:00Z",
        updated_at: "2026-06-30T08:00:00Z",
      },
    });
    vi.mocked(fetchKubernetesActionReport).mockResolvedValue({
      success: true,
      request_id: "11111111-1111-1111-1111-111111111111",
      status: "pending_approval",
      report: {},
      execution_policy: {
        approval_required: true,
        dry_run_required: true,
        verification_required: true,
        native_execution_enabled: false,
        blocked_reason: "WebTerm currently records the request only.",
      },
      timeline: [
        {
          action: "k8s.action_request.create",
          username: "admin",
          created_at: "2026-06-30T08:00:01Z",
          payload: {
            request_id: "11111111-1111-1111-1111-111111111111",
            status: "pending_approval",
          },
        },
      ],
    });
    vi.mocked(fetchKubernetesClusterNamespaces).mockResolvedValue({
      success: true,
      cluster,
      namespaces: [
        {
          id: "1:payments",
          name: "payments",
          environment: "prod",
          apps: 1,
          healthy: 0,
          warning: 1,
          degraded: 0,
          unknown: 0,
          owners: ["devtron"],
          teams: ["payments"],
          last_sync_at: "2026-06-29T19:00:00Z",
        },
      ],
    });
    vi.mocked(fetchKubernetesClusterWorkloads).mockResolvedValue({ success: true, cluster, workloads: [app] });
    vi.mocked(fetchKubernetesClusterPods).mockResolvedValue({
      success: true,
      cluster,
      pods: [
        {
          id: "pod_1",
          database_id: 1,
          cluster_id: "cluster_1",
          cluster_name: "prod-kz-1",
          namespace: "payments",
          name: "payments-api-abc123",
          environment: "prod",
          health: "warning",
          phase: "Running",
          node_name: "worker-a",
          pod_ip: "10.42.0.12",
          host_ip: "10.0.0.10",
          owner_kind: "ReplicaSet",
          owner_name: "payments-api-abc",
          ready_containers: 1,
          total_containers: 2,
          restart_count: 1,
          images: ["payments-api:2026.06"],
          links: {},
          labels: {},
          last_sync_at: "2026-06-29T19:00:00Z",
          sync_status: "fresh",
          is_stale: false,
          sync_age_seconds: 1,
          sync_stale_after_seconds: 900,
        },
      ],
    });
    vi.mocked(fetchKubernetesClusterNetwork).mockResolvedValue({
      success: true,
      cluster,
      network_refs: [
        {
          id: "network_1",
          database_id: 1,
          cluster_id: "cluster_1",
          cluster_name: "prod-kz-1",
          namespace: "payments",
          name: "payments-api",
          kind: "service",
          environment: "prod",
          health: "healthy",
          service_type: "ClusterIP",
          ports: [{ port: 80, targetPort: 8080 }],
          hosts: [],
          endpoints: [],
          links: {},
          labels: {},
          last_sync_at: "2026-06-29T19:00:00Z",
          sync_status: "fresh",
          is_stale: false,
          sync_age_seconds: 1,
          sync_stale_after_seconds: 900,
        },
      ],
    });
    vi.mocked(fetchKubernetesClusterEvents).mockResolvedValue({
      success: true,
      cluster,
      events: [
        {
          id: "audit_1",
          source: "webterm_audit",
          severity: "info",
          reason: "k8s.cluster.view",
          message: "k8s.cluster.view",
          username: "admin",
          namespace: "payments",
          involved_kind: "Deployment",
          involved_name: "payments-api",
          count: 1,
          payload: {},
          created_at: "2026-06-29T19:01:00Z",
        },
      ],
    });
    vi.mocked(fetchKubernetesPodLogs).mockResolvedValue({
      success: true,
      available: true,
      source: "provider_snapshot",
      target: {
        id: "pod_1",
        database_id: 1,
        cluster_id: "cluster_1",
        cluster_name: "prod-kz-1",
        namespace: "payments",
        name: "payments-api-abc123",
        environment: "prod",
        health: "warning",
        phase: "Running",
        node_name: "worker-a",
        pod_ip: "10.42.0.12",
        host_ip: "10.0.0.10",
        owner_kind: "ReplicaSet",
        owner_name: "payments-api-abc",
        ready_containers: 1,
        total_containers: 2,
        restart_count: 1,
        images: ["payments-api:2026.06"],
        links: {},
        labels: {},
        last_sync_at: "2026-06-29T19:00:00Z",
        sync_status: "fresh",
        is_stale: false,
        sync_age_seconds: 1,
        sync_stale_after_seconds: 900,
      },
      policy: {
        mode: "read_only",
        mutates_state: false,
        streaming: false,
        source: "rancher_provider_json",
        requested_tail_lines: 120,
        max_tail_lines: 500,
        blocked_actions: ["exec", "attach", "logs_streaming", "follow_stream", "port_forward", "delete", "restart", "scale", "apply_yaml"],
      },
      provider: { id: 1, name: "rancher-main", kind: "rancher" },
      lines: ["boot ok", "password=[redacted]"],
      line_count: 2,
      truncated: false,
      message: "",
    });
    vi.mocked(fetchKubernetesWorkloadDescribe).mockResolvedValue({
      success: true,
      target: { ...app, source: "workload" },
      related_events: [
        {
          id: "event_1",
          source: "rancher",
          severity: "warning",
          reason: "Unhealthy",
          message: "Readiness probe failed",
          username: "system",
          namespace: "payments",
          involved_kind: "Deployment",
          involved_name: "payments-api",
          count: 2,
          payload: {},
          created_at: "2026-06-29T19:02:00Z",
        },
      ],
      policy: {
        mode: "read_only",
        mutates_state: false,
        source: "normalized_inventory",
        blocked_actions: ["exec", "logs_streaming", "rollout_restart", "scale", "delete", "apply_yaml", "port_forward"],
      },
      manifest_preview: {
        apiVersion: "apps/v1",
        kind: "Deployment",
        metadata: { name: "payments-api", namespace: "payments", labels: {} },
        spec_summary: { owner: "devtron", desired: 2 },
        status_summary: { health: "warning", ready: 1, desired: 2 },
      },
    });
    vi.mocked(fetchKubernetesFleetBundles).mockResolvedValue({
      success: true,
      bundles: [
        {
          id: "fleet_1",
          database_id: 1,
          name: "fleet-default/ingress-nginx",
          source: "gitrepo/platform",
          target: "prod",
          status: "rolling",
          ready: 1,
          desired: 2,
          partitions: [],
          links: {},
          labels: {},
          last_sync_at: "2026-06-29T19:00:00Z",
        },
      ],
    });
    vi.mocked(fetchKubernetesDevtronApps).mockResolvedValue({ success: true, apps: [app] });
  });

  it("renders cluster detail with namespace, workload, and audit event data", async () => {
    renderRoute("/kubernetes/clusters/cluster_1", <KubernetesClusterDetailPage />);

    expect(await screen.findByRole("heading", { name: "prod-kz-1" })).toBeInTheDocument();
    expect(screen.getAllByText("payments-api").length).toBeGreaterThan(0);
    expect(screen.getByText("payments-api-abc123")).toBeInTheDocument();
    expect(screen.getByText("ClusterIP")).toBeInTheDocument();
    expect(screen.getAllByText("k8s.cluster.view").length).toBeGreaterThan(0);
    expect(fetchKubernetesCluster).toHaveBeenCalledWith("cluster_1");

    fireEvent.click(screen.getByRole("button", { name: /Describe payments-api|Описать payments-api/ }));
    expect(await screen.findByText("Read-only describe")).toBeInTheDocument();
    expect(screen.getByText("Unhealthy")).toBeInTheDocument();
    expect(fetchKubernetesWorkloadDescribe).toHaveBeenCalledWith("app_1");

    fireEvent.click(screen.getByRole("button", { name: /Запросить restart payments-api|Request restart for payments-api/ }));
    expect(await screen.findByText("Заявка на действие")).toBeInTheDocument();
    expect(screen.getByText("execution off")).toBeInTheDocument();
    expect(await screen.findByText("Заявка создана")).toBeInTheDocument();
    expect(fetchKubernetesActionReport).toHaveBeenCalledWith("11111111-1111-1111-1111-111111111111");
    expect(createKubernetesActionRequest).toHaveBeenCalledWith({
      action: "k8s.rollout.restart",
      reason: "Operator requested restart approval for payments/payments-api",
      target: { workload_id: "app_1" },
    });

    fireEvent.click(screen.getByRole("button", { name: "Logs payments-api-abc123" }));
    expect(await screen.findByText("Read-only pod logs")).toBeInTheDocument();
    expect(screen.getByText(/boot ok/)).toBeInTheDocument();
    expect(fetchKubernetesPodLogs).toHaveBeenCalledWith("pod_1");
  });

  it("renders Fleet and Devtron read-only pages", async () => {
    renderRoute("/kubernetes/fleet", <KubernetesFleetPage />);
    expect(await screen.findByText("fleet-default/ingress-nginx")).toBeInTheDocument();

    renderRoute("/kubernetes/devtron", <KubernetesDevtronPage />);
    expect(await screen.findByText("payments-api")).toBeInTheDocument();
  });
});
