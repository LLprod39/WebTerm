import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SidebarProvider } from "@/components/ui/sidebar";
import { I18nProvider } from "@/lib/i18n";
import { AppSidebar } from "@/components/AppSidebar";
import { fetchAuthSession } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    authLogout: vi.fn(),
    fetchAuthSession: vi.fn(),
  };
});

function renderSidebar(features: Record<string, boolean>) {
  vi.mocked(fetchAuthSession).mockResolvedValue({
    authenticated: true,
    user: {
      id: 1,
      username: "admin",
      email: "admin@example.com",
      is_staff: true,
      features,
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

describe("AppSidebar MARS and Kubernetes nav", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders new sidebar items only when feature access is enabled", async () => {
    renderSidebar({ servers: true, dashboard: true, agents: true, studio: true, kubernetes: true, mars: true, settings: true });

    expect(await screen.findByText("Кубернетес")).toBeInTheDocument();
    expect(screen.getByText("MARS")).toBeInTheDocument();
  });

  it("hides new sidebar items without feature access", async () => {
    renderSidebar({ servers: true, dashboard: true, agents: true, studio: true, kubernetes: false, mars: false, settings: true });

    await screen.findByText("Серверы");
    expect(screen.queryByText("Кубернетес")).not.toBeInTheDocument();
    expect(screen.queryByText("MARS")).not.toBeInTheDocument();
  });
});
