import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { FirstRunReadinessGate } from "@/components/FirstRunReadinessGate";
import { fetchAuthSession, fetchSettingsReadiness } from "@/api";
import { I18nProvider } from "@/lib/i18n";
import { featureMap } from "@/test/featureFlags";

vi.mock("@/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api")>();
  return { ...actual, fetchAuthSession: vi.fn(), fetchSettingsReadiness: vi.fn() };
});

function renderGate() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/dashboard?range=day"]}>
        <I18nProvider>
          <Routes>
            <Route
              path="/dashboard"
              element={(
                <FirstRunReadinessGate>
                  <div>Dashboard content</div>
                </FirstRunReadinessGate>
              )}
            />
            <Route path="/settings/readiness" element={<div>First-run wizard</div>} />
          </Routes>
        </I18nProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("FirstRunReadinessGate", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.clearAllMocks();
    vi.mocked(fetchAuthSession).mockResolvedValue({
      authenticated: true,
      user: { id: 7, username: "admin", email: "admin@example.com", is_staff: true, features: featureMap({ settings: true }) },
    });
  });

  it("automatically sends an unready admin to the first-run wizard", async () => {
    vi.mocked(fetchSettingsReadiness).mockResolvedValue({
      success: true,
      status: "warning",
      summary: { ready: 1, warning: 1, error: 0, total: 2 },
      checks: [],
    });

    renderGate();

    expect(await screen.findByText("First-run wizard")).toBeInTheDocument();
    expect(fetchSettingsReadiness).toHaveBeenCalledOnce();
  });

  it("opens the workspace and records a ready first run", async () => {
    vi.mocked(fetchSettingsReadiness).mockResolvedValue({
      success: true,
      status: "ready",
      summary: { ready: 2, warning: 0, error: 0, total: 2 },
      checks: [],
    });

    renderGate();

    expect(await screen.findByText("Dashboard content")).toBeInTheDocument();
    await waitFor(() => expect(window.localStorage.getItem("webterm.first-run-readiness.v1.7")).toBe("seen"));
  });
});
