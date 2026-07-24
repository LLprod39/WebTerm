import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { PlaybookBindingProfile, PlaybookCapabilities } from "@/api/playbooks";
import { PlaybookBindingsPanel } from "./PlaybookBindingsPanel";
import type { PlaybookWorkspaceVersioningController } from "./usePlaybookWorkspaceVersioning";

const capabilities: PlaybookCapabilities = {
  can_view: true,
  can_edit: false,
  can_validate: false,
  can_publish: false,
  can_run: true,
  can_export: true,
  can_share: false,
  can_delete: false,
  is_owner: false,
};

function profile(): PlaybookBindingProfile {
  return {
    id: 5,
    name: "Production",
    is_default: true,
    selector_mappings: { web: { server_ids: [1], group_ids: [] } },
    variable_values: { release: "2026.07" },
    secret_variables: ["db_password"],
    options: { concurrency: 3, become: true, dry_run: false },
    version: 2,
    content_hash: "binding-hash",
    updated_at: "2026-07-24T10:00:00Z",
  };
}

function controller(overrides: Record<string, unknown> = {}): PlaybookWorkspaceVersioningController {
  return {
    capabilities,
    bindingsAccessible: true,
    bindings: [profile()],
    bindingBusy: false,
    saveBinding: vi.fn().mockResolvedValue(true),
    removeBinding: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  } as unknown as PlaybookWorkspaceVersioningController;
}

describe("PlaybookBindingsPanel", () => {
  it("shows only configured secret names and never hydrates a secret value", async () => {
    const saveBinding = vi.fn().mockResolvedValue(true);
    const workspace = controller({ saveBinding });

    render(<PlaybookBindingsPanel lang="en" workspace={workspace} />);

    expect(screen.getByText(/db_password: configured/)).toBeInTheDocument();
    expect(screen.queryByText("persisted-secret-value")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    const secretValue = screen.getByLabelText("New secret value");
    expect(secretValue).toHaveValue("");

    fireEvent.change(screen.getByLabelText("Secret variable name"), { target: { value: "api_token" } });
    fireEvent.change(secretValue, { target: { value: "one-time-value" } });
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));

    await waitFor(() => expect(saveBinding).toHaveBeenCalledTimes(1));
    expect(saveBinding).toHaveBeenCalledWith(
      expect.objectContaining({ secret_values: { api_token: "one-time-value" } }),
      expect.objectContaining({ id: 5 }),
    );
    expect(screen.queryByDisplayValue("one-time-value")).not.toBeInTheDocument();
  });

  it("clears an unsaved secret when the dialog closes", () => {
    render(<PlaybookBindingsPanel lang="en" workspace={controller()} />);

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("New secret value"), { target: { value: "temporary" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    expect(screen.getByLabelText("New secret value")).toHaveValue("");
  });
});
