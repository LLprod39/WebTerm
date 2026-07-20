import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { adaptPlaybookCompatibility, applyPlaybookCompatibility } from "@/api/playbooks";
import { PlaybookCompatibilityPanel } from "./PlaybookCompatibilityPanel";

vi.mock("@/api/playbooks", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/api/playbooks")>();
  return {
    ...original,
    adaptPlaybookCompatibility: vi.fn(),
    applyPlaybookCompatibility: vi.fn(),
  };
});

vi.mock("@/lib/notify", () => ({
  notify: { success: vi.fn(), error: vi.fn() },
}));

describe("PlaybookCompatibilityPanel one-click adaptation", () => {
  it("adapts and immediately applies the guarded proposal without user instructions", async () => {
    const report = { status: "ready", ready: true, issues: [], host_selectors: ["web"] };
    vi.mocked(adaptPlaybookCompatibility).mockResolvedValue({
      success: true,
      proposal: {
        method: "ai",
        adapted_yaml: "- hosts: web\n  tasks: []\n",
        changes: ["Prepared for WebTrerm runtime inventory"],
        assumptions: [],
        semantic_guard: { passed: true, differences: [] },
        report,
      },
    });
    vi.mocked(applyPlaybookCompatibility).mockResolvedValue({
      success: true,
      playbook: { id: 7, name: "Deploy", playbook_type: "imported" } as never,
      revision: { id: 11, report } as never,
    });
    const onApplied = vi.fn();

    render(
      <PlaybookCompatibilityPanel
        lang="ru"
        playbookId={7}
        sourceYaml="- hosts: web\n  tasks: []\n"
        report={{ status: "needs_adaptation", issues: [] }}
        onApplied={onApplied}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Автоадаптировать" }));

    await waitFor(() => expect(adaptPlaybookCompatibility).toHaveBeenCalledWith(7));
    expect(applyPlaybookCompatibility).toHaveBeenCalledWith(7, {
      adapted_yaml: "- hosts: web\n  tasks: []\n",
      changes: ["Prepared for WebTrerm runtime inventory"],
    });
    await waitFor(() => expect(onApplied).toHaveBeenCalled());
  });
});
