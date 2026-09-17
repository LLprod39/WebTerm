import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/lib/i18n";
import MarsRunPage from "@/pages/MarsRunPage";
import { marsApi, type MarsWorkspace } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    getMarsRunWsUrl: vi.fn(() => "ws://localhost/ws/mars/runs/7/live/"),
    marsApi: {
      listWorkspaces: vi.fn(),
      createWorkspace: vi.fn(),
      createSession: vi.fn(),
      getSession: vi.fn(),
      answerSession: vi.fn(),
      approveSessionPlan: vi.fn(),
      runSession: vi.fn(),
      getRun: vi.fn(),
      listRunEvents: vi.fn(),
      stopRun: vi.fn(),
    },
  };
});

class WebSocketMock {
  onmessage: ((event: MessageEvent) => void) | null = null;
  close() {}
}

const workspace: MarsWorkspace = {
  id: 1,
  name: "Personal workspace",
  root_path: "agent_projects\\mars_workspaces\\user_1",
  read_allow_roots: ["agent_projects\\mars_workspaces\\user_1"],
  write_allow_roots: ["agent_projects\\mars_workspaces\\user_1"],
  deny_globs: [],
  enabled: true,
  created_at: null,
  updated_at: null,
};

function renderRunPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/mars/runs/7"]}>
        <I18nProvider>
          <Routes>
            <Route path="/mars/runs/:runId" element={<MarsRunPage />} />
          </Routes>
        </I18nProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function activateTab(name: string) {
  fireEvent.mouseDown(screen.getByRole("tab", { name }), { button: 0, ctrlKey: false });
}

describe("MarsRunPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal("WebSocket", WebSocketMock);
    vi.mocked(marsApi.getRun).mockResolvedValue({
      run: {
        id: 7,
        session_id: 3,
        workspace_id: 1,
        workspace,
        cli_roles: {},
        status: "completed",
        runtime_control: {},
        allow_dirty: false,
        final_report: "# MARS final report",
        codex_summary: "Final answer",
        gemini_review: "Quality review ok",
        test_output: "npm test passed",
        git_before: "",
        git_after: " M frontend/src/App.tsx",
        started_at: "2026-06-14T00:00:00Z",
        completed_at: "2026-06-14T00:01:00Z",
        created_at: "2026-06-14T00:00:00Z",
      },
    });
    vi.mocked(marsApi.listRunEvents).mockResolvedValue({
      events: [
        { id: 1, run_id: 7, event_type: "mars_run_started", message: "started", payload: {}, created_at: "2026-06-14T00:00:00Z" },
        { id: 2, run_id: 7, event_type: "codex_stdout", message: "build stream", payload: { text: "build stream" }, created_at: "2026-06-14T00:00:01Z" },
        { id: 3, run_id: 7, event_type: "codex_finished", message: "done", payload: {}, created_at: "2026-06-14T00:00:02Z" },
        { id: 4, run_id: 7, event_type: "gemini_finished", message: "done", payload: {}, created_at: "2026-06-14T00:00:03Z" },
      ],
    });
  });

  it("renders timeline, CLI stream, review, changed files, tests, and final report", async () => {
    renderRunPage();

    expect(await screen.findByText("Рабочая папка: Personal workspace")).toBeInTheDocument();
    expect(screen.queryByText("C:\\WebTrerm")).not.toBeInTheDocument();

    activateTab("Изменения");
    expect(await screen.findByText("frontend/src/App.tsx")).toBeInTheDocument();
    expect(screen.getByText("npm test passed")).toBeInTheDocument();

    activateTab("Логи");
    expect(await screen.findByText(/build stream/)).toBeInTheDocument();

    activateTab("Отчет");
    expect(await screen.findByText("Final answer")).toBeInTheDocument();
    expect(screen.getByText("Quality review ok")).toBeInTheDocument();
    expect(screen.queryByText(/Codex/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Gemini/i)).not.toBeInTheDocument();
    expect(screen.getByText(/MARS final report/)).toBeInTheDocument();
  });
});
