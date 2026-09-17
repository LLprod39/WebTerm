import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import {
  fetchAuthSession,
  fetchKubernetesClusterEvents,
  fetchKubernetesClusterNamespaces,
  fetchKubernetesClusterPods,
  fetchKubernetesClusters,
  fetchKubernetesConnections,
  fetchKubernetesPodLogs,
  fetchKubernetesProviders,
} from "@/api";
import { I18nProvider } from "@/lib/i18n";
import KubernetesCockpitPage from "@/pages/KubernetesCockpitPage";

vi.mock("@/api", () => ({
  fetchAuthSession: vi.fn(),
  fetchKubernetesClusters: vi.fn(),
  fetchKubernetesClusterNamespaces: vi.fn(),
  fetchKubernetesClusterPods: vi.fn(),
  fetchKubernetesClusterEvents: vi.fn(),
  fetchKubernetesPodLogs: vi.fn(),
  fetchKubernetesProviders: vi.fn(),
  createKubernetesProvider: vi.fn(),
  syncKubernetesProvider: vi.fn(),
  deleteKubernetesProvider: vi.fn(),
  fetchKubernetesConnections: vi.fn(),
  parseKubernetesKubeconfig: vi.fn(),
  createKubernetesKubeconfigConnection: vi.fn(),
  rotateKubernetesConnection: vi.fn(),
  deleteKubernetesConnection: vi.fn(),
  probeKubernetesConnection: vi.fn(),
}));

function renderPage(initial = "/kubernetes") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider>
        <MemoryRouter initialEntries={[initial]}>
          <KubernetesCockpitPage />
        </MemoryRouter>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

const crashPod = {
  id: "pod_crash",
  database_id: 11,
  cluster_id: "cluster_1",
  cluster_name: "prod-eu-1",
  namespace: "production",
  name: "checkout-api-a1",
  environment: "prod",
  health: "degraded",
  phase: "CrashLoopBackOff",
  node_name: "node-a",
  pod_ip: "10.0.1.4",
  host_ip: "10.0.0.8",
  owner_kind: "ReplicaSet",
  owner_name: "checkout-api",
  ready_containers: 0,
  total_containers: 1,
  restart_count: 14,
  images: ["checkout:1"],
  links: {},
  labels: {},
  last_sync_at: null,
  sync_status: "fresh",
  is_stale: false,
  sync_age_seconds: 5,
  sync_stale_after_seconds: 300,
} as const;

describe("KubernetesCockpitPage", () => {
  beforeEach(() => {
    localStorage.setItem("weu_lang", "ru");
    vi.mocked(fetchAuthSession).mockResolvedValue({
      authenticated: true,
      user: {
        id: 1,
        username: "admin",
        email: "admin@example.test",
        is_staff: true,
        features: { kubernetes: true },
      },
    } as never);
    vi.mocked(fetchKubernetesClusters).mockResolvedValue({
      success: true,
      clusters: [
        {
          id: "cluster_1",
          database_id: 1,
          name: "prod-eu-1",
          environment: "prod",
          provider: "rancher",
          health: "healthy",
          nodes_ready: 3,
          nodes_total: 3,
          namespaces: 2,
          workloads: 4,
          apps: 2,
          fleet_bundles: 0,
          devtron_apps: 0,
          labels: {},
          links: {},
          last_sync_at: null,
          sync_status: "fresh",
          is_stale: false,
          sync_age_seconds: 10,
          sync_stale_after_seconds: 300,
          created_at: null,
          updated_at: null,
        },
      ],
    });
    vi.mocked(fetchKubernetesClusterNamespaces).mockResolvedValue({
      success: true,
      cluster: {} as never,
      namespaces: [
        {
          id: "ns_prod",
          name: "production",
          environment: "prod",
          apps: 1,
          healthy: 1,
          warning: 0,
          degraded: 1,
          unknown: 0,
          owners: [],
          teams: [],
          last_sync_at: null,
        },
      ],
    });
    vi.mocked(fetchKubernetesClusterPods).mockResolvedValue({
      success: true,
      cluster: {} as never,
      pods: [crashPod as never],
    });
    vi.mocked(fetchKubernetesClusterEvents).mockResolvedValue({
      success: true,
      cluster: {} as never,
      events: [
        {
          id: "ev1",
          source: "k8s",
          severity: "warning",
          reason: "BackOff",
          message: "Back-off restarting failed container app",
          username: "",
          namespace: "production",
          involved_kind: "Pod",
          involved_name: "checkout-api-a1",
          payload: {},
          created_at: "2026-09-14T18:44:00Z",
        },
      ],
    });
    vi.mocked(fetchKubernetesPodLogs).mockResolvedValue({
      success: true,
      available: true,
      source: "provider_snapshot",
      target: crashPod as never,
      policy: {
        mode: "read_only",
        mutates_state: false,
        streaming: false,
        source: "rancher_provider_json",
        requested_tail_lines: 200,
        max_tail_lines: 500,
        blocked_actions: ["exec"],
      },
      provider: { id: 1, name: "rancher", kind: "rancher" },
      lines: [
        "ERROR dial tcp 10.0.4.22:5432: connect: connection refused",
        "FATAL database unavailable — exiting",
        "Liveness probe failed: HTTP 500",
      ],
      line_count: 3,
      truncated: false,
      message: "",
    });
    vi.mocked(fetchKubernetesProviders).mockResolvedValue({ success: true, providers: [] });
    vi.mocked(fetchKubernetesConnections).mockResolvedValue({
      success: true,
      connections: [],
      granted_clusters: [],
    });
  });

  it("loads cockpit workspace and explains logs via local mock", async () => {
    renderPage("/kubernetes?cluster=cluster_1&ns=production");

    expect(await screen.findByRole("heading", { name: "Kubernetes" })).toBeInTheDocument();
    expect(await screen.findByText("checkout-api-a1")).toBeInTheDocument();
    expect(screen.getAllByText(/Требуют внимания/i).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("option", { name: /checkout-api-a1/i }));
    await waitFor(() => expect(fetchKubernetesPodLogs).toHaveBeenCalledWith("pod_crash", 200));
    expect(await screen.findByText(/connection refused/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Разобрать логи" }));
    expect(await screen.findByText(/Гипотеза/i)).toBeInTheDocument();
    expect(screen.getByText(/mock/i)).toBeInTheDocument();

    fireEvent.click(await screen.findByRole("tab", { name: "Команда" }));
    expect(await screen.findByRole("button", { name: /Выполнить/i })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Выполнить/i }));
    expect(await screen.findByText(/Exec API/i)).toBeInTheDocument();
  });

  it("shows namespace events on events tab", async () => {
    renderPage("/kubernetes?cluster=cluster_1&ns=production&tab=events");
    expect(await screen.findByText(/Back-off restarting failed container/i)).toBeInTheDocument();
  });

  it("shows self-serve add-cluster form for everyone", async () => {
    vi.mocked(fetchKubernetesClusters).mockResolvedValue({ success: true, clusters: [] });
    renderPage("/kubernetes?tab=connect");
    expect(await screen.findByRole("heading", { name: /Добавьте свой кластер через kubeconfig/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Подключить и синхронизировать/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Добавить кластер/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Открыть настройки Kubernetes/i })).toHaveAttribute(
      "href",
      "/settings/kubernetes",
    );
  });

  it("hides admin settings for non-admin but keeps add-cluster", async () => {
    vi.mocked(fetchAuthSession).mockResolvedValue({
      authenticated: true,
      user: {
        id: 2,
        username: "operator",
        email: "ops@example.test",
        is_staff: false,
        features: { kubernetes: true },
      },
    } as never);
    vi.mocked(fetchKubernetesClusters).mockResolvedValue({ success: true, clusters: [] });
    renderPage("/kubernetes?tab=connect");

    expect(await screen.findByRole("heading", { name: /Добавьте свой кластер через kubeconfig/i })).toBeInTheDocument();
    expect(screen.getByText(/Для всех · свои кластеры/i)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Открыть настройки Kubernetes/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /^Настройки$/i })).not.toBeInTheDocument();
  });
});
