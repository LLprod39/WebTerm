import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { CommandPalette } from "@/components/CommandPalette";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    fetchAgents: vi.fn(async () => ({ success: true, agents: [] })),
    fetchFrontendBootstrap: vi.fn(async () => ({ success: true, servers: [], groups: [] })),
  };
});
vi.mock("@/lib/i18n", () => ({
  localize: (_lang: string, _ru: string, en: string) => en,
  useI18n: () => ({ lang: "en", setLang: vi.fn() }),
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

    fireEvent.click(screen.getByText("Playbooks"));

    await waitFor(() => {
      expect(screen.getByTestId("pathname")).toHaveTextContent("/automation");
    });
  });
});
