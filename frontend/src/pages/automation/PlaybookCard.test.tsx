import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { PlaybookCapabilities, PlaybookSummary } from "@/api/playbooks";
import { PlaybookCard } from "./PlaybookCard";

const viewerCapabilities: PlaybookCapabilities = {
  can_view: true,
  can_edit: false,
  can_validate: false,
  can_publish: false,
  can_run: false,
  can_export: true,
  can_share: false,
  can_delete: false,
  is_owner: false,
};

function playbook(capabilities: PlaybookCapabilities): PlaybookSummary {
  return {
    id: 8,
    name: "Shared deploy",
    description: "Read-only playbook",
    kind: "ansible",
    category: "deploy",
    visibility: "shared",
    tags: [],
    fidelity: {},
    compatibility: {},
    active_compatibility_revision: null,
    task_count: 2,
    is_template_clone: false,
    template_slug: "",
    last_run_at: null,
    last_run_status: "",
    created_at: null,
    updated_at: null,
    owner_id: 1,
    capabilities,
  };
}

describe("PlaybookCard capabilities", () => {
  it("shows a view action and hides forbidden run/delete actions", () => {
    render(
      <PlaybookCard
        playbook={playbook(viewerCapabilities)}
        lang="en"
        onOpen={vi.fn()}
        onRun={vi.fn()}
        onDuplicate={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "View" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Run" })).not.toBeInTheDocument();
    fireEvent.pointerDown(screen.getByRole("button", { name: "Playbook actions" }), {
      button: 0,
      ctrlKey: false,
      pointerType: "mouse",
    });
    expect(screen.queryByRole("menuitem", { name: "Delete" })).not.toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Duplicate" })).toBeInTheDocument();
  });

  it("hides duplicate when export capability is absent", () => {
    render(
      <PlaybookCard
        playbook={playbook({ ...viewerCapabilities, can_export: false })}
        lang="en"
        onOpen={vi.fn()}
        onRun={vi.fn()}
        onDuplicate={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    expect(screen.queryByRole("button", { name: "Duplicate" })).not.toBeInTheDocument();
  });

  it("offers configuration instead of claiming execution is available while the worker is offline", () => {
    render(
      <PlaybookCard
        playbook={playbook({ ...viewerCapabilities, can_run: true })}
        lang="en"
        executionReady={false}
        onOpen={vi.fn()}
        onRun={vi.fn()}
        onDuplicate={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Configure" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Run" })).not.toBeInTheDocument();
  });
});
