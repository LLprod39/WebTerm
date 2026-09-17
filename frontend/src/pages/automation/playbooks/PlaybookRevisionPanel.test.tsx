import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import type { PlaybookCapabilities, PlaybookDraft, PlaybookRevision } from "@/api/playbooks";
import { PlaybookRevisionPanel } from "./PlaybookRevisionPanel";
import type { PlaybookWorkspaceVersioningController } from "./usePlaybookWorkspaceVersioning";

const ownerCapabilities: PlaybookCapabilities = {
  can_view: true,
  can_edit: true,
  can_validate: true,
  can_publish: true,
  can_run: true,
  can_export: true,
  can_share: true,
  can_delete: true,
  is_owner: true,
};

const revision: PlaybookRevision = {
  id: 12,
  revision_number: 2,
  parent_id: 11,
  content_format: "ansible_yaml",
  content_hash: "revision-hash",
  bundle_hash: "",
  origin_type: "manual",
  message: "Ready for production",
  author_id: 1,
  author_username: "owner",
  created_at: "2026-07-24T10:00:00Z",
};

function controller(overrides: Record<string, unknown> = {}): PlaybookWorkspaceVersioningController {
  return {
    capabilities: ownerCapabilities,
    autosaveStatus: "saved",
    autosaveError: "",
    conflict: null,
    draft: { version: 4 } as PlaybookDraft,
    hasUnrevisionedChanges: false,
    hasUnpublishedRevision: true,
    revisions: [revision],
    publishedRevisionId: 11,
    revisionsLoading: false,
    revisionBusy: null,
    selectedRevision: null,
    setSelectedRevision: vi.fn(),
    acceptServerDraft: vi.fn(),
    keepLocalDraft: vi.fn().mockResolvedValue(undefined),
    createRevision: vi.fn().mockResolvedValue(revision),
    publishRevision: vi.fn().mockResolvedValue(undefined),
    rollbackRevision: vi.fn().mockResolvedValue(undefined),
    openRevision: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  } as unknown as PlaybookWorkspaceVersioningController;
}

function panel(workspace: PlaybookWorkspaceVersioningController) {
  return <PlaybookRevisionPanel lang="en" playbookId={7} workspace={workspace} compatibilityReady={false} onValidate={vi.fn()} />;
}

function renderPanel(workspace: PlaybookWorkspaceVersioningController) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(panel(workspace), { wrapper: ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider> });
}

describe("PlaybookRevisionPanel", () => {
  it("creates and publishes revisions only through explicit actions", async () => {
    const createRevision = vi.fn().mockResolvedValue(revision);
    const publishRevision = vi.fn().mockResolvedValue(undefined);
    renderPanel(controller({ createRevision, publishRevision }));

    fireEvent.change(screen.getByLabelText("New version note"), {
      target: { value: "Release candidate" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create version" }));
    await waitFor(() => expect(createRevision).toHaveBeenCalledWith("Release candidate"));

    fireEvent.click(screen.getByRole("button", { name: "Publish" }));
    expect(publishRevision).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Publish", exact: true }));
    await waitFor(() => expect(publishRevision).toHaveBeenCalledWith(12));
  });

  it("offers both conflict resolutions without applying either automatically", () => {
    const acceptServerDraft = vi.fn();
    const keepLocalDraft = vi.fn().mockResolvedValue(undefined);
    renderPanel(controller({
          autosaveStatus: "conflict",
          conflict: { serverDraft: { version: 7 } as PlaybookDraft, message: "conflict" },
          acceptServerDraft,
          keepLocalDraft,
        }));

    expect(acceptServerDraft).not.toHaveBeenCalled();
    expect(keepLocalDraft).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Use server version" }));
    fireEvent.click(screen.getByRole("button", { name: "Keep my version" }));
    expect(acceptServerDraft).toHaveBeenCalledTimes(1);
    expect(keepLocalDraft).toHaveBeenCalledTimes(1);
  });

  it("hides edit and publish controls from a viewer", () => {
    const capabilities = {
      ...ownerCapabilities,
      can_edit: false,
      can_publish: false,
      can_share: false,
      can_delete: false,
      is_owner: false,
    };
    renderPanel(controller({ capabilities }));

    expect(screen.queryByRole("button", { name: "Create version" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Publish" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open revision 2" })).toBeInTheDocument();
  });

  it("offers sanitized export for an immutable revision when capability allows it", () => {
    const { rerender } = renderPanel(controller({ publishedRevisionId: null }));

    expect(screen.getByRole("button", { name: "Export immutable revision 2" })).toBeInTheDocument();

    rerender(panel(controller({
          publishedRevisionId: null,
          capabilities: { ...ownerCapabilities, can_export: false },
        })));
    expect(screen.queryByRole("button", { name: "Export immutable revision 2" })).not.toBeInTheDocument();
  });
});
