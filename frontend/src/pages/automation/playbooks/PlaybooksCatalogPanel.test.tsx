import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { PlaybooksCatalogPanel, type PlaybooksCatalogPanelProps } from "./PlaybooksCatalogPanel";

function props(overrides: Partial<PlaybooksCatalogPanelProps> = {}): PlaybooksCatalogPanelProps {
  return {
    lang: "en",
    tr: (_ru, en) => en,
    playbooks: [],
    templates: [],
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
    onImportClick: vi.fn(),
    onImportFile: vi.fn(),
    onOpenNew: vi.fn(),
    onOpenGuided: vi.fn(),
    onInstallTemplate: vi.fn(),
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

    expect(screen.getByRole("alert")).toHaveTextContent("Failed to load playbooks");
    expect(screen.getByRole("alert")).toHaveTextContent("503");
    expect(screen.queryByText("Your playbook library is empty")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetryPlaybooks).toHaveBeenCalledTimes(1);
  });
});
