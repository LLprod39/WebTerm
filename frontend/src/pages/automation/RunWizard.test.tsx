import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { previewPlaybookInventory } from "@/api/playbooks";
import type { FrontendServer } from "@/lib/api";
import { RunWizard } from "./RunWizard";

vi.mock("@/api/playbooks", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/api/playbooks")>();
  return { ...original, previewPlaybookInventory: vi.fn() };
});

describe("RunWizard host bindings", () => {
  it("requires every imported host selector and sends runtime bindings to preview", async () => {
    vi.mocked(previewPlaybookInventory).mockResolvedValue({
      success: true,
      inventory: "[wt_web]\nweb-01\n[wt_db]\ndb-01",
      hosts: [],
      count: 2,
      compatibility: { status: "ready", ready: true, issues: [] },
    });
    const servers = [
      { id: 1, name: "web-01", host: "10.0.0.1", status: "online" },
      { id: 2, name: "db-01", host: "10.0.0.2", status: "online" },
    ] as FrontendServer[];
    render(
      <RunWizard
        lang="en"
        playbookId={7}
        playbookName="Deploy"
        servers={servers}
        groups={[]}
        running={false}
        ansibleAvailable
        compatibility={{ host_selectors: ["web", "db"], issues: [] }}
        onBack={vi.fn()}
        onConfirm={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /web-01/i }));
    fireEvent.click(screen.getByRole("button", { name: /db-01/i }));
    const bindings = screen.getAllByRole("combobox");
    fireEvent.change(bindings[0], { target: { value: "server:1" } });
    fireEvent.change(bindings[1], { target: { value: "server:2" } });
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));

    await waitFor(() => expect(previewPlaybookInventory).toHaveBeenCalled());
    expect(vi.mocked(previewPlaybookInventory).mock.calls.at(-1)?.[0]).toMatchObject({
      playbook_id: 7,
      inventory_bindings: {
        web: { server_ids: [1], group_ids: [] },
        db: { server_ids: [2], group_ids: [] },
      },
    });
  });
});
