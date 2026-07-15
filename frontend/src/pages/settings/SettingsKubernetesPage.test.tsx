import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import {
  createKubernetesProvider,
  fetchAuthSession,
  fetchKubernetesOverview,
  probeKubernetesProvider,
} from "@/api";
import { I18nProvider } from "@/lib/i18n";
import SettingsKubernetesPage from "@/pages/settings/SettingsKubernetesPage";
import { featureMap } from "@/test/featureFlags";
import type { KubernetesOverviewResponse } from "@/api/kubernetes";

vi.mock("@/api", () => ({
  createKubernetesProvider: vi.fn(),
  deleteKubernetesProvider: vi.fn(),
  fetchAuthSession: vi.fn(),
  fetchKubernetesOverview: vi.fn(),
  probeKubernetesProvider: vi.fn(),
  syncKubernetesProvider: vi.fn(),
  updateKubernetesProvider: vi.fn(),
}));

function providerFixture() {
  return {
    id: 1,
    name: "rancher-main",
    kind: "rancher",
    base_url: "https://rancher.example.test",
    enabled: true,
    auth_mode: "secret_ref",
    has_secret_ref: true,
    secret_storage: "external",
    labels: {},
    last_sync_at: "2026-06-30T08:00:00Z",
    last_error: "",
    provider_health: "healthy",
    sync_status: "fresh",
    is_stale: false,
    sync_age_seconds: 30,
    sync_stale_after_seconds: 900,
    created_at: null,
    updated_at: null,
  };
}

function overviewFixture(): KubernetesOverviewResponse {
  return {
    success: true,
    readiness: {
      success: true,
      status: "configured",
      ready_for_sidebar: false,
      summary: { ready: 7, missing: 0, manual: 1, total: 8 },
      checks: [
        { id: "architecture_guard", status: "ready", detail: "Repository guard is checked.", required: true },
        { id: "rancher_provider", status: "ready", detail: "Rancher provider configured: 1", required: true },
        { id: "devtron_provider", status: "ready", detail: "Devtron provider configured: 1", required: true },
        { id: "provider_health", status: "ready", detail: "Enabled providers have fresh sync metadata.", required: true },
        { id: "read_only_sync", status: "ready", detail: "Normalized inventory rows exist.", required: true },
        { id: "sync_worker", status: "ready", detail: "Kubernetes sync worker is running.", required: true },
        {
          id: "identity_runtime",
          status: "ready",
          detail: "Production OIDC/Keycloak runtime gate is not enforced until production.",
          required: true,
        },
        {
          id: "sidebar_release_scope",
          status: "missing",
          detail: "Release scope is local; production approval is required.",
          required: true,
        },
        {
          id: "release_evidence_artifact",
          status: "ready",
          detail: "Fresh local release evidence artifact found.",
          required: false,
        },
        { id: "studio_automation", status: "missing", detail: "Studio diagnosis draft is not launch-ready.", required: false },
      ],
      worker_state: {
        worker_kind: "kubernetes_ops_sync",
        worker_key: "compose",
        status: "running",
        is_stale: false,
        hostname: "worker",
        pid: 123,
        command: "python manage.py run_kubernetes_ops_sync_worker --daemon",
        heartbeat_at: "2026-06-30T08:00:00Z",
        lease_expires_at: "2026-06-30T08:05:00Z",
        last_started_at: "2026-06-30T07:00:00Z",
        last_stopped_at: null,
        last_cycle_started_at: "2026-06-30T07:59:30Z",
        last_cycle_finished_at: "2026-06-30T08:00:00Z",
        last_summary: { matched: 2, ok: 2, failed: 0, clusters: 1, apps: 3 },
        last_error: "",
      },
    },
    summary: {
      clusters: 1,
      apps: 3,
      fleet_rollouts: 2,
      incidents: 1,
      warnings: 1,
      rolling: 1,
      paused: 0,
      stale: 0,
      provider_issues: 0,
    },
    providers: [providerFixture()],
    clusters: [],
    workloads: [],
    apps: [],
    fleet_rollouts: [],
  };
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <MemoryRouter>
          <SettingsKubernetesPage />
        </MemoryRouter>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("SettingsKubernetesPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchAuthSession).mockResolvedValue({
      authenticated: true,
      user: {
        id: 1,
        username: "admin",
        email: "admin@example.test",
        is_staff: true,
        features: featureMap({ settings: true, kubernetes: true }),
      },
    });
    vi.mocked(fetchKubernetesOverview).mockResolvedValue(overviewFixture());
    vi.mocked(createKubernetesProvider).mockResolvedValue({
      success: true,
      provider: providerFixture(),
    });
    vi.mocked(probeKubernetesProvider).mockResolvedValue({
      success: true,
      probe: {
        provider_id: 1,
        provider_name: "rancher-main",
        provider_kind: "rancher",
        success: true,
        status: "ready",
        path: "/v3/clusters",
        item_count: 2,
        payload_keys: ["data"],
        duration_ms: 12,
        checked_at: "2026-06-30T08:00:00Z",
        error: "",
      },
    });
  });

  it("renders Kubernetes admin setup, worker state, and readiness gates in settings", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "Kubernetes Ops" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Production release gate" })).toBeInTheDocument();
    expect(screen.getAllByText("1 блокер").length).toBeGreaterThan(0);
    expect(screen.queryByText("Release gate checks ещё не пришли из backend readiness.")).not.toBeInTheDocument();
    expect(screen.getAllByText("Production OIDC/Keycloak runtime gate is not enforced until production.").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Release scope is local; production approval is required.").length).toBeGreaterThan(0);
    expect(screen.getByText(/KUBERNETES_OPS_READY_FOR_SIDEBAR=true/)).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Настройка провайдеров" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { level: 2, name: "Sync worker" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Readiness gate" })).toBeInTheDocument();
    expect(screen.getByText("rancher-main")).toBeInTheDocument();
  });

  it("submits admin provider setup from settings without exposing a raw token", async () => {
    renderPage();

    await screen.findByRole("heading", { name: "Настройка провайдеров" });
    fireEvent.change(screen.getByLabelText("Provider base URL"), {
      target: { value: "https://rancher.example.test" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Добавить" }));

    await waitFor(() => {
      expect(createKubernetesProvider).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "rancher-main",
          kind: "rancher",
          base_url: "https://rancher.example.test",
          secret_ref: "env:RANCHER_TOKEN",
        }),
      );
    });
  });

  it("runs provider probe from settings without exposing provider payload", async () => {
    renderPage();

    await screen.findByRole("button", { name: "Probe" });
    fireEvent.click(screen.getByRole("button", { name: "Probe" }));

    await waitFor(() => {
      expect(probeKubernetesProvider).toHaveBeenCalledWith(1);
    });
    expect(await screen.findByText(/items=2/)).toBeInTheDocument();
  });
});
