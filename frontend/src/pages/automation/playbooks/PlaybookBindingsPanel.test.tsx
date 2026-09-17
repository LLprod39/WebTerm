import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { PlaybookBindingProfile, PlaybookCapabilities } from "@/api/playbooks";
import type { FrontendServer } from "@/lib/api";
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

const servers = [{ id: 1, name: "web-01", host: "10.0.0.1", status: "online" }] as FrontendServer[];

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

function renderPanel(workspace: PlaybookWorkspaceVersioningController) {
  return render(
    <PlaybookBindingsPanel
      lang="en"
      workspace={workspace}
      servers={servers}
      groups={[]}
      hostSelectors={["web"]}
    />,
  );
}

function addSecretRow() {
  const addButtons = screen.getAllByRole("button", { name: "Add" });
  fireEvent.click(addButtons.at(-1)!);
}

describe("PlaybookBindingsPanel", () => {
  it("shows only configured secret names and never hydrates a secret value", async () => {
    const saveBinding = vi.fn().mockResolvedValue(true);
    const workspace = controller({ saveBinding });

    renderPanel(workspace);

    expect(screen.getByText("db_password")).toBeInTheDocument();
    expect(screen.queryByText("persisted-secret-value")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    expect(screen.queryByLabelText("New or replaced secrets: value")).not.toBeInTheDocument();
    addSecretRow();

    fireEvent.change(screen.getByLabelText("New or replaced secrets: name"), { target: { value: "api_token" } });
    fireEvent.change(screen.getByLabelText("New or replaced secrets: value"), { target: { value: "one-time-value" } });
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));

    await waitFor(() => expect(saveBinding).toHaveBeenCalledTimes(1));
    expect(saveBinding).toHaveBeenCalledWith(
      expect.objectContaining({ secret_values: { api_token: "one-time-value" } }),
      expect.objectContaining({ id: 5 }),
    );
    expect(screen.queryByDisplayValue("one-time-value")).not.toBeInTheDocument();
  });

  it("does not remove a managed secret when the same save replaces it", async () => {
    const saveBinding = vi.fn().mockResolvedValue(true);
    renderPanel(controller({ saveBinding }));

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.click(screen.getByRole("button", { name: /db_password.*configured/ }));
    addSecretRow();
    fireEvent.change(screen.getByLabelText("New or replaced secrets: name"), { target: { value: "db_password" } });
    fireEvent.change(screen.getByLabelText("New or replaced secrets: value"), { target: { value: "replacement" } });
    fireEvent.click(screen.getByRole("button", { name: "Save profile" }));

    await waitFor(() => expect(saveBinding).toHaveBeenCalledTimes(1));
    const payload = saveBinding.mock.calls[0][0];
    expect(payload.secret_values).toEqual({ db_password: "replacement" });
    expect(payload.remove_secret_names).toBeUndefined();
  });

  it("clears an unsaved secret when the dialog closes", () => {
    renderPanel(controller());

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    addSecretRow();
    fireEvent.change(screen.getByLabelText("New or replaced secrets: value"), { target: { value: "temporary" } });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    expect(screen.queryByLabelText("New or replaced secrets: value")).not.toBeInTheDocument();
  });
});
