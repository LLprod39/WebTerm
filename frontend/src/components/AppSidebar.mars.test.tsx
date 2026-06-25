import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SidebarProvider } from "@/components/ui/sidebar";
import { I18nProvider } from "@/lib/i18n";
import { AppSidebar } from "@/components/AppSidebar";
import { fetchAuthSession, type FeatureFlag } from "@/lib/api";
import { featureMap } from "@/test/featureFlags";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    authLogout: vi.fn(),
    fetchAuthSession: vi.fn(),
  };
});

function renderSidebar(features: Partial<Record<FeatureFlag, boolean>>) {
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

  it("renders MARS when enabled and keeps Chat/Kubernetes hidden until ready", async () => {
    renderSidebar({ servers: true, dashboard: true, agents: true, studio: true, orchestrator: true, kubernetes: true, mars: true, settings: true });

    expect(await screen.findByText("MARS")).toBeInTheDocument();
    expect(screen.queryByText("Чат")).not.toBeInTheDocument();
    expect(screen.queryByText("Кубернетес")).not.toBeInTheDocument();
  });

  it("hides new sidebar items without feature access", async () => {
    renderSidebar({ servers: true, dashboard: true, agents: true, studio: true, orchestrator: false, kubernetes: false, mars: false, settings: true });

    await screen.findByText("Серверы");
    expect(screen.queryByText("Чат")).not.toBeInTheDocument();
    expect(screen.queryByText("Кубернетес")).not.toBeInTheDocument();
    expect(screen.queryByText("MARS")).not.toBeInTheDocument();
  });
});
