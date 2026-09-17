import { act, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AutomationPage from "@/pages/AutomationPage";
import Servers from "@/pages/Servers";

const playbooksWorkspaceSpy = vi.hoisted(() => vi.fn());

vi.mock("@/pages/automation/PlaybooksWorkspace", () => ({
  PlaybooksWorkspace: (props: Record<string, unknown>) => {
    playbooksWorkspaceSpy(props);
    return <div data-testid="playbooks-workspace">Standalone playbooks workspace</div>;
  },
}));

function PathnameProbe() {
  return <output data-testid="pathname">{useLocation().pathname}</output>;
}

describe("standalone Playbooks route", () => {
  beforeEach(() => {
    playbooksWorkspaceSpy.mockClear();
  });

  it("keeps a direct /automation load on the canonical route and lets the workspace load its inventory", () => {
    render(
      <MemoryRouter initialEntries={["/automation"]}>
        <Routes>
          <Route
            path="/automation/*"
            element={(
              <>
                <AutomationPage />
                <PathnameProbe />
              </>
            )}
          />
        </Routes>
      </MemoryRouter>,
    );

    const workspace = screen.getByTestId("playbooks-workspace");
    expect(screen.getByTestId("pathname")).toHaveTextContent("/automation");
    expect(workspace.parentElement).toHaveClass("max-w-7xl");
    expect(playbooksWorkspaceSpy).toHaveBeenCalledTimes(1);
    expect(playbooksWorkspaceSpy.mock.calls[0]?.[0]).toMatchObject({
      initialView: { mode: "catalog" },
      onViewChange: expect.any(Function),
    });
  });

  it.each([
    ["/automation/playbooks/42", { mode: "edit", playbookId: 42 }],
    ["/automation/runs/91", { mode: "run-results", runId: 91 }],
  ])("restores %s into the matching workspace view after reload", (pathname, expectedView) => {
    render(
      <MemoryRouter initialEntries={[pathname]}>
        <Routes>
          <Route
            path="/automation/*"
            element={(
              <>
                <AutomationPage />
                <PathnameProbe />
              </>
            )}
          />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByTestId("pathname")).toHaveTextContent(pathname);
    expect(playbooksWorkspaceSpy.mock.lastCall?.[0]).toMatchObject({ initialView: expectedView });
  });

  it("updates the canonical URL when the workspace opens a run", () => {
    render(
      <MemoryRouter initialEntries={["/automation"]}>
        <Routes>
          <Route
            path="/automation/*"
            element={(
              <>
                <AutomationPage />
                <PathnameProbe />
              </>
            )}
          />
        </Routes>
      </MemoryRouter>,
    );

    const onViewChange = playbooksWorkspaceSpy.mock.lastCall?.[0]?.onViewChange as
      | ((view: { mode: "run-results"; runId: number }) => void)
      | undefined;
    act(() => onViewChange?.({ mode: "run-results", runId: 17 }));

    expect(screen.getByTestId("pathname")).toHaveTextContent("/automation/runs/17");
  });

  it("redirects the legacy Servers playbook navigation state without mounting a second workspace", async () => {
    render(
      <MemoryRouter initialEntries={[{ pathname: "/servers", state: { mainTab: "playbook" } }]}>
        <Routes>
          <Route path="/servers" element={<Servers />} />
          <Route path="/automation" element={<div>Canonical playbooks route</div>} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Canonical playbooks route")).toBeInTheDocument();
    expect(playbooksWorkspaceSpy).not.toHaveBeenCalled();
  });
});
