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

describe("PlaybookCompatibilityPanel guarded adaptation", () => {
  it("requires explicit review before applying a guarded proposal", async () => {
    const report = { status: "ready", ready: true, issues: [], host_selectors: ["web"] };
    vi.mocked(adaptPlaybookCompatibility).mockResolvedValue({
      success: true,
      proposal: {
        method: "ai",
        adapted_yaml: "- hosts: web\n  tasks: []\n",
        changes: ["Prepared for WebTerm runtime inventory"],
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

    fireEvent.click(screen.getByRole("button", { name: "Подготовить адаптацию" }));

    await waitFor(() => expect(adaptPlaybookCompatibility).toHaveBeenCalledWith(7));
    expect(applyPlaybookCompatibility).not.toHaveBeenCalled();
    expect(await screen.findByText("Проверьте изменения перед применением")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Показать предложенный YAML"));
    expect(screen.getByText(/hosts: web/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Применить проверенное предложение" }));

    await waitFor(() => expect(applyPlaybookCompatibility).toHaveBeenCalled());
    expect(applyPlaybookCompatibility).toHaveBeenCalledWith(7, {
      adapted_yaml: "- hosts: web\n  tasks: []\n",
      changes: ["Prepared for WebTerm runtime inventory"],
    });
    await waitFor(() => expect(onApplied).toHaveBeenCalled());
  });

  it("keeps compatibility analysis read-only when adaptation is forbidden", () => {
    render(
      <PlaybookCompatibilityPanel
        lang="en"
        playbookId={7}
        sourceYaml="- hosts: web\n  tasks: []\n"
        report={{ analyzer_version: 3, status: "needs_adaptation", issues: [] }}
        canAdapt={false}
        onApplied={vi.fn()}
      />,
    );

    expect(screen.getByRole("button", { name: "Analyze" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Prepare adaptation" })).not.toBeInTheDocument();
  });
});
