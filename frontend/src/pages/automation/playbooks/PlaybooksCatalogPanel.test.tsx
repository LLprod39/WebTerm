import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import type { PlaybookSummary } from "@/api/playbooks";
import { PlaybooksCatalogPanel, type PlaybooksCatalogPanelProps } from "./PlaybooksCatalogPanel";

const project: PlaybookSummary = {
  id: 17,
  name: "Harden SSH",
  description: "Audit and apply the approved SSH baseline",
  kind: "ansible",
  category: "security",
  visibility: "private",
  tags: [],
  fidelity: {},
  compatibility: { ready: true },
  active_compatibility_revision: null,
  task_count: 6,
  is_template_clone: false,
  template_slug: "",
  last_run_at: null,
  last_run_status: "",
  created_at: null,
  updated_at: null,
  owner_id: 1,
};

function props(overrides: Partial<PlaybooksCatalogPanelProps> = {}): PlaybooksCatalogPanelProps {
  return {
    lang: "en",
    tr: (_ru, en) => en,
    playbooks: [],
    recentRuns: [],
    playbooksLoading: false,
    playbooksError: "Request failed with status 503",
    search: "",
    setSearch: vi.fn(),
    categoryFilter: "all",
    setCategoryFilter: vi.fn(),
    showHistory: false,
    setShowHistory: vi.fn(),
    ansible: undefined,
    ansibleAvailable: false,
    onRefreshRuns: vi.fn(),
    onRetryPlaybooks: vi.fn(),
    onOpenNew: vi.fn(),
    onOpenImport: vi.fn(),
    onOpenEdit: vi.fn(),
    onStartRun: vi.fn(),
    onDuplicate: vi.fn(),
    onDelete: vi.fn(),
    onOpenRun: vi.fn(),
    ...overrides,
  };
}

describe("PlaybooksCatalogPanel loading states", () => {
  it("shows a query failure instead of presenting an empty library", () => {
    const onRetryPlaybooks = vi.fn();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <PlaybooksCatalogPanel {...props({ onRetryPlaybooks })} />
      </QueryClientProvider>,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Failed to load projects");
    expect(screen.getByRole("alert")).toHaveTextContent("503");
    expect(screen.queryByText("No projects yet")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetryPlaybooks).toHaveBeenCalledTimes(1);
  });

  it("keeps YAML validation available while clearly reporting an offline execution worker", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <PlaybooksCatalogPanel
          {...props({
            playbooksError: "",
            ansible: { validation_available: true } as PlaybooksCatalogPanelProps["ansible"],
            ansibleAvailable: false,
          })}
        />
      </QueryClientProvider>,
    );

    expect(screen.getByRole("status")).toHaveTextContent("Execution service is unavailable");
    expect(screen.getByRole("status")).toHaveTextContent("Projects and YAML validation remain available");
  });

  it("presents projects as a gallery and exposes one-click category filters", () => {
    const setCategoryFilter = vi.fn();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <PlaybooksCatalogPanel
          {...props({ playbooks: [project], playbooksError: "", ansibleAvailable: true, setCategoryFilter })}
        />
      </QueryClientProvider>,
    );

    expect(screen.getByRole("list", { name: "Ansible projects" })).toBeInTheDocument();
    expect(screen.getByRole("listitem")).toHaveTextContent("Harden SSH");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Security" }));
    expect(setCategoryFilter).toHaveBeenCalledWith("security");
  });

  it("offers adjacent create and import actions without a source-card funnel", () => {
    const onOpenNew = vi.fn();
    const onOpenImport = vi.fn();
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <PlaybooksCatalogPanel {...props({ playbooksError: "", onOpenNew, onOpenImport })} />
      </QueryClientProvider>,
    );

    expect(screen.queryByRole("heading", { name: "Add your own automation" })).not.toBeInTheDocument();
    expect(screen.queryByText(/GitLab project/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Single YAML/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Project archive/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/template/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "Import" })[0]);
    expect(onOpenImport).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getAllByRole("button", { name: "Create from scratch" })[0]);
    expect(onOpenNew).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("link", { name: "Check readiness" })).toHaveAttribute("href", "/settings/readiness");
  });
});
