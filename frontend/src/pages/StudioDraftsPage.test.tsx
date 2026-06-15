import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import StudioDraftsPage from "@/pages/StudioDraftsPage";
import * as draftApi from "@/lib/studioPipelineDraftsApi";

const toastMock = vi.fn();

vi.mock("@/components/StudioNav", () => ({
  StudioNav: () => <div>StudioNav</div>,
}));

vi.mock("@/components/studio/DraftGraphCanvas", () => ({
  DraftGraphCanvas: ({ session }: { session: { title?: string } | null }) => (
    <div data-testid="draft-graph">{session?.title || "empty graph"}</div>
  ),
}));

vi.mock("@/hooks/use-toast", () => ({
  useToast: () => ({ toast: toastMock }),
}));

vi.mock("@/lib/i18n", () => ({
  useI18n: () => ({ lang: "en", setLang: () => undefined, t: (key: string) => key }),
  localize: (lang: string, ru: string, en: string) => (lang === "ru" ? ru : en),
}));

vi.mock("@/lib/studioPipelineDraftsApi", () => ({
  studioPipelineDrafts: {
    list: vi.fn(),
    create: vi.fn(),
    get: vi.fn(),
    discard: vi.fn(),
    revise: vi.fn(),
    validate: vi.fn(),
    useTemplate: vi.fn(),
    apply: vi.fn(),
  },
}));

function renderPage(path = "/studio/drafts") {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <StudioDraftsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function draftSession() {
  return {
    id: 5,
    status: "ready",
    intent: "create",
    title: "Existing draft",
    user_goal: "Create a daily health report",
    source_pipeline_id: null,
    applied_pipeline_id: null,
    selected_node_id: "",
    created_at: "2026-04-10T10:00:00Z",
    updated_at: "2026-04-10T10:05:00Z",
    applied_at: null,
    latest_revision: {
      id: 9,
      session_id: 5,
      user_message: "Create a daily health report",
      created_at: "2026-04-10T10:05:00Z",
      preview_nodes: [
        { id: "manual_start", type: "trigger/manual", position: { x: 0, y: 0 }, data: { label: "Manual start" } },
        { id: "report", type: "output/report", position: { x: 240, y: 0 }, data: { label: "Report" } },
      ],
      preview_edges: [{ id: "e1", source: "manual_start", target: "report", sourceHandle: "out" }],
      response: {
        reply: "Draft ready.",
        target_node_id: null,
        node_patch: {},
        graph_patch: {
          anchor_node_id: null,
          nodes: [
            { ref: "manual_start", type: "trigger/manual", label: "Manual start", data: {} },
            { ref: "report", type: "output/report", label: "Report", data: {} },
          ],
          edges: [{ source: "manual_start", target: "report" }],
        },
        warnings: [],
        validation: { ok: true, errors: [], warnings: [] },
        risk: { level: "safe", items: [] },
        patch_summary: "Creates a manual report pipeline.",
        selected_template: {
          slug: "pilot-service-config-validate-restart",
          name: "Pilot: Service Config Validate And Restart",
          source: "manual_template_switch",
        },
        template_recommendations: [
          {
            slug: "pilot-service-config-validate-restart",
            name: "Pilot: Service Config Validate And Restart",
            description: "Service config validate and restart",
            node_types: ["ops/server_snapshot", "ops/service_action", "ops/http_check"],
          },
        ],
      },
    },
  };
}

describe("StudioDraftsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(draftApi.studioPipelineDrafts.list).mockResolvedValue([]);
  });

  it("renders the graph-first cockpit empty state", async () => {
    renderPage();

    expect(await screen.findByText(/Pipeline drafts/i)).toBeInTheDocument();
    expect(screen.getByTestId("draft-graph")).toHaveTextContent("empty graph");
    expect(screen.getByLabelText("Pipeline task")).toBeInTheDocument();
  });

  it("loads an existing draft and revises it instead of creating a new session", async () => {
    const currentDraft = draftSession();
    const revisedSession = {
      ...currentDraft,
      user_goal: "Add Telegram delivery",
      latest_revision: {
        ...currentDraft.latest_revision,
        id: 10,
        user_message: "Add Telegram delivery",
        response: {
          ...currentDraft.latest_revision.response,
          patch_summary: "Adds Telegram delivery.",
        },
      },
    };
    vi.mocked(draftApi.studioPipelineDrafts.list).mockResolvedValue([currentDraft] as never);
    vi.mocked(draftApi.studioPipelineDrafts.get).mockResolvedValue(currentDraft as never);
    vi.mocked(draftApi.studioPipelineDrafts.revise).mockResolvedValue(revisedSession as never);

    renderPage("/studio/drafts?draft=5");

    expect((await screen.findAllByText("Existing draft")).length).toBeGreaterThan(0);
    const prompt = screen.getByLabelText("Pipeline task");
    fireEvent.change(prompt, { target: { value: "Add Telegram delivery" } });
    fireEvent.click(screen.getByRole("button", { name: /Revise draft/i }));

    await waitFor(() => {
      expect(draftApi.studioPipelineDrafts.revise).toHaveBeenCalledWith(
        5,
        expect.objectContaining({
          pipeline_name: "Existing draft",
          user_message: "Add Telegram delivery",
          draft_mode: true,
        }),
      );
    });
    expect(draftApi.studioPipelineDrafts.create).not.toHaveBeenCalled();
  });

  it("treats open questions as an answer flow", async () => {
    const currentDraft = {
      ...draftSession(),
      status: "needs_input",
      latest_revision: {
        ...draftSession().latest_revision,
        response: {
          ...draftSession().latest_revision.response,
          questions: ["Укажи Keycloak realm.", "Укажи действие: add или remove."],
        },
      },
    };
    vi.mocked(draftApi.studioPipelineDrafts.list).mockResolvedValue([currentDraft] as never);
    vi.mocked(draftApi.studioPipelineDrafts.get).mockResolvedValue(currentDraft as never);
    vi.mocked(draftApi.studioPipelineDrafts.revise).mockResolvedValue({
      ...currentDraft,
      status: "ready",
      latest_revision: {
        ...currentDraft.latest_revision,
        response: {
          ...currentDraft.latest_revision.response,
          questions: [],
        },
      },
    } as never);

    renderPage("/studio/drafts?draft=5");

    expect(await screen.findByText(/Answer draft questions/i)).toBeInTheDocument();
    expect(screen.getByText(/Missing details/i)).toBeInTheDocument();
    expect(screen.getAllByText("Укажи Keycloak realm.")).toHaveLength(1);
    expect(screen.getAllByText("Укажи действие: add или remove.")).toHaveLength(1);
    fireEvent.change(screen.getByLabelText("Question 1 answer"), { target: { value: "realm prod" } });
    fireEvent.change(screen.getByLabelText("Question 2 answer"), { target: { value: "operation add" } });
    fireEvent.click(screen.getByRole("button", { name: /Answer questions/i }));

    await waitFor(() => {
      expect(draftApi.studioPipelineDrafts.revise).toHaveBeenCalledWith(
        5,
        expect.objectContaining({
          user_message: [
            "Q1: Укажи Keycloak realm.\nA1: realm prod",
            "Q2: Укажи действие: add или remove.\nA2: operation add",
          ].join("\n\n"),
          draft_mode: true,
        }),
      );
    });
  });

  it("can request the provider-free deterministic compiler", async () => {
    const createdDraft = {
      ...draftSession(),
      id: 7,
      title: "Operations runbook",
      user_goal: "Restart nginx after approval",
    };
    vi.mocked(draftApi.studioPipelineDrafts.create).mockResolvedValue(createdDraft as never);

    renderPage();

    const prompt = await screen.findByLabelText("Pipeline task");
    fireEvent.change(prompt, { target: { value: "Restart nginx after approval" } });
    fireEvent.click(screen.getByRole("button", { name: /Quick template/i }));

    await waitFor(() => {
      expect(draftApi.studioPipelineDrafts.create).toHaveBeenCalledWith(
        expect.objectContaining({
          user_message: "Restart nginx after approval",
          compiler_mode: "deterministic",
        }),
      );
    });
  });

  it("prefills a new draft from capability links", async () => {
    vi.mocked(draftApi.studioPipelineDrafts.create).mockResolvedValue({
      ...draftSession(),
      id: 8,
      title: "Kubernetes operations",
      user_goal: "Create a Kubernetes diagnosis workflow",
    } as never);

    renderPage("/studio/drafts?title=Kubernetes%20operations&prompt=Create%20a%20Kubernetes%20diagnosis%20workflow");

    const prompt = await screen.findByLabelText("Pipeline task");
    expect(prompt).toHaveValue("Create a Kubernetes diagnosis workflow");
    fireEvent.click(screen.getByRole("button", { name: /Quick template/i }));

    await waitFor(() => {
      expect(draftApi.studioPipelineDrafts.create).toHaveBeenCalledWith(
        expect.objectContaining({
          pipeline_name: "Kubernetes operations",
          user_message: "Create a Kubernetes diagnosis workflow",
          compiler_mode: "deterministic",
        }),
      );
    });
  });

  it("validates an active draft without applying it", async () => {
    const currentDraft = draftSession();
    vi.mocked(draftApi.studioPipelineDrafts.list).mockResolvedValue([currentDraft] as never);
    vi.mocked(draftApi.studioPipelineDrafts.get).mockResolvedValue(currentDraft as never);
    vi.mocked(draftApi.studioPipelineDrafts.validate).mockResolvedValue({
      draft: {
        ...currentDraft,
        latest_revision: {
          ...currentDraft.latest_revision,
          response: {
            ...currentDraft.latest_revision.response,
            dry_run: {
              ok: true,
              executed: false,
              mode: "validate_only",
              checks: ["graph_contract", "references", "risk_review"],
              message: "Dry-run validation checked graph structure.",
            },
          },
        },
      },
      validation: { ok: true, errors: [], warnings: [] },
      risk: { level: "safe", items: [] },
      dry_run: {
        ok: true,
        executed: false,
        mode: "validate_only",
        checks: ["graph_contract", "references", "risk_review"],
        message: "Dry-run validation checked graph structure.",
      },
    } as never);

    renderPage("/studio/drafts?draft=5");

    expect((await screen.findAllByText("Existing draft")).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: /Validate dry-run/i }));

    await waitFor(() => {
      expect(draftApi.studioPipelineDrafts.validate).toHaveBeenCalledWith(5);
    });
    expect(draftApi.studioPipelineDrafts.apply).not.toHaveBeenCalled();
  });

  it("switches an active draft to the selected pilot skeleton", async () => {
    const currentDraft = draftSession();
    const switchedDraft = {
      ...currentDraft,
      latest_revision: {
        ...currentDraft.latest_revision,
        id: 11,
        response: {
          ...currentDraft.latest_revision.response,
          patch_summary: "Pilot template skeleton: Pilot: Service Config Validate And Restart",
        },
      },
    };
    vi.mocked(draftApi.studioPipelineDrafts.list).mockResolvedValue([currentDraft] as never);
    vi.mocked(draftApi.studioPipelineDrafts.get).mockResolvedValue(currentDraft as never);
    vi.mocked(draftApi.studioPipelineDrafts.useTemplate).mockResolvedValue(switchedDraft as never);

    renderPage("/studio/drafts?draft=5");

    expect(await screen.findByText("Pilot template")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Use template/i }));

    await waitFor(() => {
      expect(draftApi.studioPipelineDrafts.useTemplate).toHaveBeenCalledWith(
        5,
        "pilot-service-config-validate-restart",
      );
    });
    expect(draftApi.studioPipelineDrafts.apply).not.toHaveBeenCalled();
  });
});
