import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { searchPlaybookShareCandidates, type PlaybookCapabilities } from "@/api/playbooks";
import { notify } from "@/lib/notify";
import { PlaybookSharingPanel } from "./PlaybookSharingPanel";
import type { PlaybookWorkspaceVersioningController } from "./usePlaybookWorkspaceVersioning";

vi.mock("@/api/playbooks", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/api/playbooks")>();
  return { ...original, searchPlaybookShareCandidates: vi.fn() };
});

vi.mock("@/lib/notify", () => ({ notify: { error: vi.fn() } }));

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

function controller(overrides: Record<string, unknown> = {}): PlaybookWorkspaceVersioningController {
  return {
    capabilities: ownerCapabilities,
    sharesAccessible: true,
    shares: [],
    shareBusy: false,
    saveShare: vi.fn().mockResolvedValue(true),
    removeShare: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  } as unknown as PlaybookWorkspaceVersioningController;
}

function renderPanel(workspace: PlaybookWorkspaceVersioningController) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PlaybookSharingPanel lang="en" playbookId={7} workspace={workspace} />
    </QueryClientProvider>,
  );
}

describe("PlaybookSharingPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
    });
    vi.mocked(searchPlaybookShareCandidates).mockResolvedValue({
      success: true,
      items: [
        { type: "user", id: 41, label: "Alice Operator", secondary: "alice@example.test" },
        { type: "group", id: 8, label: "SRE", secondary: "group" },
      ],
    });
  });

  it("creates a user grant with use access by default", async () => {
    const saveShare = vi.fn().mockResolvedValue(true);
    renderPanel(controller({ saveShare }));

    fireEvent.click(screen.getByRole("button", { name: "Add access" }));
    fireEvent.change(screen.getByLabelText("Search user"), { target: { value: "Alice" } });
    fireEvent.click(await screen.findByRole("option", { name: /Alice Operator/ }));
    fireEvent.click(screen.getByRole("button", { name: "Save access" }));

    await waitFor(() => expect(saveShare).toHaveBeenCalledTimes(1));
    expect(saveShare).toHaveBeenCalledWith(
      expect.objectContaining({
        principal_type: "user",
        principal_id: 41,
        role: "operator",
        capabilities: expect.objectContaining({ can_run: true, can_validate: true, can_edit: false }),
      }),
    );
  });

  it("offers only users and the two simplified access levels", async () => {
    const saveShare = vi.fn().mockResolvedValue(true);
    renderPanel(controller({ saveShare }));

    fireEvent.click(screen.getByRole("button", { name: "Add access" }));
    expect(screen.queryByRole("combobox", { name: "Access principal" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Search user"), { target: { value: "A" } });
    expect(await screen.findByRole("option", { name: /Alice Operator/ })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /SRE/ })).not.toBeInTheDocument();

    fireEvent.keyDown(screen.getByRole("combobox", { name: "Access level" }), { key: "ArrowDown" });
    expect(screen.getByRole("option", { name: "Use" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("option", { name: "Use + edit" }));
    fireEvent.click(screen.getByRole("option", { name: /Alice Operator/ }));
    fireEvent.click(screen.getByRole("button", { name: "Save access" }));

    await waitFor(() => expect(saveShare).toHaveBeenCalledTimes(1));
    expect(saveShare).toHaveBeenCalledWith(expect.objectContaining({
      principal_type: "user",
      role: "editor",
      capabilities: expect.objectContaining({ can_run: true, can_edit: true, can_manage_shares: false }),
    }));
  });

  it("never interprets typed digits as a principal id and offers no workspace-wide grant", async () => {
    vi.mocked(searchPlaybookShareCandidates).mockResolvedValue({ success: true, items: [] });
    renderPanel(controller());
    fireEvent.click(screen.getByRole("button", { name: "Add access" }));
    fireEvent.change(screen.getByLabelText("Search user"), { target: { value: "41" } });
    expect(screen.getByRole("button", { name: "Save access" })).toBeDisabled();
    expect(screen.queryByRole("option", { name: "Entire workspace" })).not.toBeInTheDocument();
  });

  it("describes fixed roles accurately and omits internal principal ids", () => {
    renderPanel(controller({
      shares: [{
        id: 4,
        role: "viewer",
        principal: { type: "user", id: 41, label: "Alice Operator" },
        capabilities: {
          can_view: true,
          can_edit: false,
          can_validate: false,
          can_publish: false,
          can_run: false,
          can_export: false,
          can_manage_shares: false,
        },
        expires_at: null,
        revoked_at: null,
        created_at: "2026-08-26T10:00:00Z",
      }],
    }));

    expect(screen.getByText("View published content (legacy level)")).toBeInTheDocument();
    expect(screen.queryByText(/#41/)).not.toBeInTheDocument();
  });

  it("reports clipboard failures without an unhandled rejection", async () => {
    vi.mocked(navigator.clipboard.writeText).mockRejectedValueOnce(new Error("denied"));
    renderPanel(controller());

    fireEvent.click(screen.getByRole("button", { name: "Copy internal link" }));

    await waitFor(() => expect(notify.error).toHaveBeenCalledWith({ title: "Could not copy the internal link" }));
  });

  it("does not render share management without can_share", () => {
    const capabilities = { ...ownerCapabilities, can_share: false, is_owner: false };
    const { container } = renderPanel(controller({ capabilities }));

    expect(container).toBeEmptyDOMElement();
  });
});
