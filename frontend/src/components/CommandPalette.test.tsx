import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { CommandPalette } from "@/components/CommandPalette";

const apiMocks = vi.hoisted(() => ({
  fetchAgents: vi.fn(async () => ({ success: true, agents: [] })),
  fetchFrontendBootstrap: vi.fn(async () => ({ success: true, servers: [], groups: [] })),
  fetchAuthSession: vi.fn(async () => ({
    authenticated: true,
    user: {
      id: 1,
      username: "pilot",
      email: "pilot@example.test",
      is_staff: false,
      features: { automation: true },
    },
  })),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    ...apiMocks,
  };
});
vi.mock("@/lib/i18n", () => ({
  localize: (_lang: string, _ru: string, en: string) => en,
  useI18n: () => ({
    lang: "en",
    setLang: vi.fn(),
    t: (key: string) => ({ "nav.playbooks": "Ansible" }[key] ?? key),
  }),
}));
vi.mock("@/lib/ui-style", () => ({
  isFlowStyle: (style: string) => style.startsWith("flow"),
  useUiStyle: () => ({ style: "flow", setStyle: vi.fn() }),
}));

function PathnameProbe() {
  return <output data-testid="pathname">{useLocation().pathname}</output>;
}

describe("CommandPalette Playbooks navigation", () => {
  it("opens the standalone /automation route", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={["/servers"]}>
          <CommandPalette open onOpenChange={vi.fn()} />
          <PathnameProbe />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    fireEvent.click(await screen.findByText("Ansible"));

    await waitFor(() => {
      expect(screen.getByTestId("pathname")).toHaveTextContent("/automation");
    });
  });

  it("does not fetch or expose servers and agents without their capabilities", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    apiMocks.fetchFrontendBootstrap.mockClear();
    apiMocks.fetchAgents.mockClear();

    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <CommandPalette open onOpenChange={vi.fn()} />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await screen.findByText("Ansible");
    expect(apiMocks.fetchFrontendBootstrap).not.toHaveBeenCalled();
    expect(apiMocks.fetchAgents).not.toHaveBeenCalled();
    expect(screen.queryByText("nav.servers")).not.toBeInTheDocument();
    expect(screen.queryByText("nav.agents")).not.toBeInTheDocument();
  });
});
