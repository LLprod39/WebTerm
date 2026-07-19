import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SidebarProvider } from "@/components/ui/sidebar";
import { I18nProvider } from "@/lib/i18n";
import { AppSidebar } from "@/components/AppSidebar";
import { fetchAuthSession, fetchKubernetesReadiness, type FeatureFlag } from "@/lib/api";
import { featureMap } from "@/test/featureFlags";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    authLogout: vi.fn(),
    fetchAuthSession: vi.fn(),
    fetchKubernetesReadiness: vi.fn(),
  };
});

function kubernetesReadiness(readyForSidebar: boolean) {
  return {
    success: true,
    status: readyForSidebar ? "ready" : "configured",
    ready_for_sidebar: readyForSidebar,
    summary: { ready: readyForSidebar ? 12 : 11, missing: 0, manual: readyForSidebar ? 0 : 1, total: 12 },
    checks: [],
    worker_state: {
      worker_kind: "kubernetes_ops_sync",
      worker_key: "default",
      status: "running",
      is_stale: false,
      hostname: "worker",
      pid: 1,
      heartbeat_at: "2026-06-30T08:00:00.000Z",
      lease_expires_at: "2026-06-30T08:03:00.000Z",
      last_started_at: "2026-06-30T08:00:00.000Z",
      last_stopped_at: null,
      last_cycle_started_at: "2026-06-30T08:00:00.000Z",
      last_cycle_finished_at: "2026-06-30T08:00:00.000Z",
      last_summary: {},
      last_error: "",
    },
  };
}

function renderSidebar(features: Partial<Record<FeatureFlag, boolean>>, options: { kubernetesReady?: boolean } = {}) {
  vi.mocked(fetchAuthSession).mockResolvedValue({
    authenticated: true,
    user: {
      id: 1,
      username: "admin",
      email: "admin@example.com",
      is_staff: true,
      features: featureMap(features),
    },
  });
  vi.mocked(fetchKubernetesReadiness).mockResolvedValue(kubernetesReadiness(Boolean(options.kubernetesReady)));

  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <I18nProvider>
          <SidebarProvider>
            <AppSidebar />
          </SidebarProvider>
        </I18nProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AppSidebar preview-gated nav", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders MARS when enabled, Chat stays gated, and staff gets Kubernetes without readiness gate", async () => {
    renderSidebar({ servers: true, dashboard: true, agents: true, studio: true, orchestrator: true, kubernetes: true, mars: true, settings: true });

    expect(await screen.findByText("MARS")).toBeInTheDocument();
    expect(screen.queryByText("Чат")).not.toBeInTheDocument();
    // Staff mock always has is_staff=true → Kubernetes is open when feature is on.
    expect(await screen.findByText("Кубернетес")).toBeInTheDocument();
    expect(fetchKubernetesReadiness).not.toHaveBeenCalled();
  });

  it("renders Kubernetes for staff when feature is enabled (no ready_for_sidebar required)", async () => {
    renderSidebar(
      { servers: true, dashboard: true, agents: true, studio: true, orchestrator: true, kubernetes: true, mars: false, settings: true },
      { kubernetesReady: false },
    );

    expect(await screen.findByText("Кубернетес")).toBeInTheDocument();
    expect(fetchKubernetesReadiness).not.toHaveBeenCalled();
  });

  it("gates Kubernetes on readiness for non-staff operators", async () => {
    vi.mocked(fetchAuthSession).mockResolvedValue({
      authenticated: true,
      user: {
        id: 2,
        username: "operator",
        email: "operator@example.com",
        is_staff: false,
        features: featureMap({ servers: true, dashboard: true, agents: true, studio: true, orchestrator: true, kubernetes: true, mars: false, settings: true }),
      },
    });
    vi.mocked(fetchKubernetesReadiness).mockResolvedValue(kubernetesReadiness(false));

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <I18nProvider>
            <SidebarProvider>
              <AppSidebar />
            </SidebarProvider>
          </I18nProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await screen.findByText("Серверы");
    expect(screen.queryByText("Кубернетес")).not.toBeInTheDocument();
    expect(fetchKubernetesReadiness).toHaveBeenCalled();
  });

  it("shows Kubernetes for operators when backend readiness allows sidebar exposure", async () => {
    vi.mocked(fetchAuthSession).mockResolvedValue({
      authenticated: true,
      user: {
        id: 2,
        username: "operator",
        email: "operator@example.com",
        is_staff: false,
        features: featureMap({ servers: true, dashboard: true, agents: true, studio: true, orchestrator: true, kubernetes: true, mars: false, settings: true }),
      },
    });
    vi.mocked(fetchKubernetesReadiness).mockResolvedValue(kubernetesReadiness(true));

    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <I18nProvider>
            <SidebarProvider>
              <AppSidebar />
            </SidebarProvider>
          </I18nProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Кубернетес")).toBeInTheDocument();
    expect(fetchKubernetesReadiness).toHaveBeenCalled();
  });

  it("hides new sidebar items without feature access", async () => {
    renderSidebar({ servers: true, dashboard: true, agents: true, studio: true, orchestrator: false, kubernetes: false, mars: false, settings: true });

    await screen.findByText("Серверы");
    expect(screen.queryByText("Чат")).not.toBeInTheDocument();
    expect(screen.queryByText("Кубернетес")).not.toBeInTheDocument();
    expect(screen.queryByText("MARS")).not.toBeInTheDocument();
  });
});
