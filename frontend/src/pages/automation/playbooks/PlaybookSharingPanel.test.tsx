import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { PlaybookCapabilities, PlaybookSharePrincipalType } from "@/api/playbooks";
import { PlaybookSharingPanel } from "./PlaybookSharingPanel";
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

describe("PlaybookSharingPanel", () => {
  it.each([
    ["user", "41", { principal_type: "user", principal_id: 41 }],
    ["group", "8", { principal_type: "group", principal_id: 8 }],
    ["workspace", "", { principal_type: "workspace" }],
  ] as Array<[PlaybookSharePrincipalType, string, Record<string, unknown>]>) (
    "creates a %s grant with an explicit principal",
    async (principalType, principalId, expected) => {
      const saveShare = vi.fn().mockResolvedValue(true);
      render(<PlaybookSharingPanel lang="en" workspace={controller({ saveShare })} />);

      fireEvent.click(screen.getByRole("button", { name: "Add access" }));
      fireEvent.change(screen.getByLabelText("Principal"), { target: { value: principalType } });
      if (principalId) {
        fireEvent.change(screen.getByLabelText("User/group ID"), { target: { value: principalId } });
      }
      fireEvent.change(screen.getByLabelText("Role"), { target: { value: "operator" } });
      fireEvent.click(screen.getByRole("button", { name: "Save access" }));

      await waitFor(() => expect(saveShare).toHaveBeenCalledTimes(1));
      expect(saveShare).toHaveBeenCalledWith(
        expect.objectContaining({
          ...expected,
          role: "operator",
          capabilities: expect.objectContaining({ can_run: true, can_validate: true, can_edit: false }),
        }),
      );
    },
  );

  it("does not render share management without can_share", () => {
    const capabilities = { ...ownerCapabilities, can_share: false, is_owner: false };
    const { container } = render(
      <PlaybookSharingPanel lang="en" workspace={controller({ capabilities })} />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
