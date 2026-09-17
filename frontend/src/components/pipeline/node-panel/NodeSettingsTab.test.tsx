import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";

import { NodeSettingsTab } from "./NodeSettingsTab";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    fetchAuthSession: vi.fn(),
  };
});

function renderTab() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  return render(
    <NodeSettingsTab
      lang="en"
      data={{ label: "Triage", max_iterations: 6, provider: "auto", model: "" }}
      agents={[]}
      selectedAgent={null}
      mcpList={[]}
      servers={[]}
      selectedSkills={[]}
      onSet={vi.fn()}
      onSetMany={vi.fn()}
      onOpenPoliciesTab={vi.fn()}
    />,
    { wrapper },
  );
}

describe("NodeSettingsTab model and limits gate", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.fetchAuthSession).mockResolvedValue({
      authenticated: true,
      user: {
        id: 2,
        username: "user",
        email: "user@example.test",
        is_staff: false,
        can_manage_ai_routing: false,
        features: {},
      },
    } as never);
  });

  it("never shows provider cards or iteration stepper — models live in Settings → AI", async () => {
    renderTab();

    expect(
      await screen.findByText(/Provider and model cannot be chosen here/i),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText(/Decrease iterations/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Increase iterations/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Editing here is not available/i)).toBeInTheDocument();
    expect(screen.queryByText(/^Auto$/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Gemini$/i)).not.toBeInTheDocument();
  });
});
