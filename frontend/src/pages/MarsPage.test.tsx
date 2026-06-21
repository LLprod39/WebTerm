import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/lib/i18n";
import MarsPage from "@/pages/MarsPage";
import { marsApi, type MarsSession, type MarsWorkspace } from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    marsApi: {
      listWorkspaces: vi.fn(),
      listProjects: vi.fn(),
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

const workspace: MarsWorkspace = {
  id: 1,
  name: "Personal workspace",
  root_path: "agent_projects\\mars_workspaces\\user_1",
  read_allow_roots: ["agent_projects\\mars_workspaces\\user_1"],
  write_allow_roots: ["agent_projects\\mars_workspaces\\user_1"],
  deny_globs: [],
  enabled: true,
  created_at: "2026-06-14T00:00:00Z",
  updated_at: "2026-06-14T00:00:00Z",
};

const baseSession: MarsSession = {
  id: 3,
  workspace_id: 1,
  workspace,
  task_brief: "Add a page",
  answers: {},
  interview_questions: [
    {
      id: "success_criteria",
      question: "Какой результат нужен именно для этой страницы?",
      kind: "textarea",
      options: ["Рабочий прототип", "Полноценный MVP"],
      required: true,
    },
    { id: "target_platform", question: "Где это должно работать в первую очередь?", kind: "choice_text", options: ["Web browser", "Mobile browser"], required: true },
    { id: "scope", question: "Что входит в первую версию?", kind: "multi_choice_text", options: ["Основная логика", "Красивый интерфейс"], required: true },
    { id: "interaction", question: "Как пользователь должен управлять или взаимодействовать?", kind: "choice_text", options: ["Клавиатура/мышь", "Touch controls"], required: true },
    { id: "visual_direction", question: "Какой визуальный стиль выбрать?", kind: "choice_text", options: ["Neon arcade", "Минимализм"], required: true },
    { id: "verification", question: "Как MARS должен проверить результат?", kind: "multi_choice_text", options: ["npm run build", "Playwright smoke"], required: true },
  ],
  selected_skill_slugs: [],
  generated_plan: "",
  status: "interview",
  created_at: "2026-06-14T00:00:00Z",
  updated_at: "2026-06-14T00:00:00Z",
};

function renderMarsPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <I18nProvider>
          <MarsPage />
        </I18nProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("MarsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(marsApi.listWorkspaces).mockResolvedValue({ workspaces: [workspace] });
    vi.mocked(marsApi.listProjects).mockResolvedValue({ projects: [] });
    vi.mocked(marsApi.createSession).mockResolvedValue({
      session: baseSession,
      recommended_skills: [],
    });
    vi.mocked(marsApi.answerSession).mockResolvedValue({
      session: {
        ...baseSession,
        answers: { success_criteria: "New page renders." },
        generated_plan: "# MARS execution plan\n\n1. Build page.",
        status: "plan_ready",
      },
    });
    vi.mocked(marsApi.approveSessionPlan).mockResolvedValue({
      session: {
        ...baseSession,
        generated_plan: "# MARS execution plan\n\n1. Build page.",
        status: "approved",
      },
    });
    vi.mocked(marsApi.runSession).mockResolvedValue({
      run: {
        id: 9,
        session_id: 3,
        workspace_id: 1,
        workspace,
        cli_roles: {},
        status: "queued",
        runtime_control: {},
        allow_dirty: false,
        final_report: "",
        codex_summary: "",
        gemini_review: "",
        test_output: "",
        git_before: "",
        git_after: "",
        started_at: null,
        completed_at: null,
        created_at: "2026-06-14T00:00:00Z",
      },
    });
    vi.mocked(marsApi.getRun).mockResolvedValue({
      run: {
        id: 9,
        session_id: 3,
        workspace_id: 1,
        workspace,
        cli_roles: {},
        status: "queued",
        runtime_control: {},
        allow_dirty: false,
        final_report: "",
        codex_summary: "",
        gemini_review: "",
        test_output: "",
        git_before: "",
        git_after: "",
        started_at: null,
        completed_at: null,
        created_at: "2026-06-14T00:00:00Z",
      },
    });
  });

  it("walks through project creation, clarification, spec approval, and build controls", async () => {
    renderMarsPage();

    expect(await screen.findByText("MARS beta - AI-разработка")).toBeInTheDocument();
    expect(screen.getByText("История проектов")).toBeInTheDocument();
    expect(screen.queryByText("План выполнения")).not.toBeInTheDocument();
    expect(screen.queryByText(/Skill routing/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Codex/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Gemini/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Frontend design/i)).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText("C:\\WebTrerm")).not.toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("Например: создать Telegram-бота для заявок или Python-скрипт для отчетов."), {
      target: { value: "Сделай 3D игру змейка в браузере" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Начать уточнение/i }));

    expect((await screen.findAllByText("Какой результат нужен именно для этой страницы?")).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: /Рабочий прототип/i }));
    fireEvent.click(screen.getByRole("button", { name: /Дальше/i }));
    fireEvent.click(screen.getByRole("button", { name: /Web browser/i }));
    fireEvent.click(screen.getByRole("button", { name: /Дальше/i }));
    fireEvent.click(screen.getByRole("button", { name: /Основная логика/i }));
    fireEvent.click(screen.getByRole("button", { name: /Дальше/i }));
    fireEvent.click(screen.getByRole("button", { name: /Клавиатура\/мышь/i }));
    fireEvent.click(screen.getByRole("button", { name: /Дальше/i }));
    fireEvent.click(screen.getByRole("button", { name: /Neon arcade/i }));
    fireEvent.click(screen.getByRole("button", { name: /Собрать план/i }));

    expect(await screen.findByDisplayValue(/MARS execution plan/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Подтвердить план/i }));
    await waitFor(() => expect(marsApi.approveSessionPlan).toHaveBeenCalled());

    fireEvent.click(screen.getByRole("button", { name: /Запустить выполнение/i }));
    await waitFor(() => {
      expect(marsApi.runSession).toHaveBeenCalledWith(3, expect.objectContaining({ allow_dirty: false }));
    });
  });
});
