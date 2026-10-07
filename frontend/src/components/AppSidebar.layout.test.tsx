import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AppSidebar } from "@/components/AppSidebar";
import { SidebarProvider } from "@/components/ui/sidebar";
import { I18nProvider } from "@/lib/i18n";
import { fetchAuthSession, fetchKubernetesReadiness } from "@/lib/api";
import { featureMap } from "@/test/featureFlags";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    authLogout: vi.fn(),
    fetchAuthSession: vi.fn(),
    fetchKubernetesReadiness: vi.fn(),
    fetchProjects: vi.fn(),
  };
});

function renderSidebar(defaultOpen: boolean) {
  vi.mocked(fetchAuthSession).mockResolvedValue({
    authenticated: true,
    user: {
      id: 1,
      username: "admin",
      email: "admin@example.com",
      is_staff: true,
      features: featureMap({
        servers: true,
        dashboard: true,
        agents: true,
        automation: true,
        studio: true,
        chat: true,
        orchestrator: true,
        kubernetes: true,
        mars: true,
        plugins: true,
        settings: true,
      }),
    },
  });
  vi.mocked(fetchKubernetesReadiness).mockResolvedValue({
    success: true,
    status: "ready",
    ready_for_sidebar: true,
    summary: { ready: 1, missing: 0, manual: 0, total: 1 },
    checks: [],
    worker_state: null,
  } as never);

  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/chat"]}>
        <I18nProvider>
          <SidebarProvider defaultOpen={defaultOpen}>
            <AppSidebar />
          </SidebarProvider>
        </I18nProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AppSidebar layout polish", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("keeps a stable brand row without ops-workspace kicker", async () => {
    renderSidebar(true);
    await screen.findByText("WebTerm");
    expect(screen.queryByText("Операционная панель")).not.toBeInTheDocument();
    expect(screen.queryByText(/OPERATIONS/i)).not.toBeInTheDocument();
    const brand = document.querySelector('[data-ui-slot="sidebar-brand"]');
    expect(brand).toHaveClass("h-12");
    expect(within(brand as HTMLElement).getByRole("button", { name: /Свернуть меню|Collapse sidebar/i })).toBeInTheDocument();
  });

  it("hides the dashboard section header that duplicates the sole item", async () => {
    renderSidebar(true);
    const dashboard = await screen.findByTestId("nav-section-dashboard");
    expect(within(dashboard).getAllByText("Панель")).toHaveLength(1);
    // Solo non-duplicate sections keep their labels.
    const extensions = screen.getByTestId("nav-section-extensions");
    expect(within(extensions).getByText("Расширения")).toBeInTheDocument();
  });

  it("uses square icon tiles and section dividers when collapsed", async () => {
    renderSidebar(false);
    const chat = await screen.findByRole("link", { name: "Чат" });
    expect(chat).toHaveClass("h-8", "w-8", "rounded-md");
    const infrastructure = screen.getByTestId("nav-section-infrastructure");
    expect(infrastructure.className).toMatch(/border-t/);
  });
});
