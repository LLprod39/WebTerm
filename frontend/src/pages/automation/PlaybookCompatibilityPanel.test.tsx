import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  adaptPlaybookCompatibility,
  adaptPlaybookSource,
  analyzePlaybookSource,
  applyPlaybookCompatibility,
} from "@/api/playbooks";
import { PlaybookCompatibilityPanel } from "./PlaybookCompatibilityPanel";

vi.mock("@/api/playbooks", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/api/playbooks")>();
  return {
    ...original,
    adaptPlaybookCompatibility: vi.fn(),
    adaptPlaybookSource: vi.fn(),
    analyzePlaybookSource: vi.fn(),
    applyPlaybookCompatibility: vi.fn(),
  };
});

vi.mock("@/lib/notify", () => ({
  notify: { success: vi.fn(), error: vi.fn() },
}));

function renderPanel(node: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

describe("PlaybookCompatibilityPanel guarded adaptation", () => {
  beforeEach(() => vi.clearAllMocks());

  it("requires explicit review before applying a guarded proposal", async () => {
    const report = { status: "ready", ready: true, issues: [], host_selectors: ["web"] };
    vi.mocked(adaptPlaybookCompatibility).mockResolvedValue({
      success: true,
      base: { path: "site.yml", content_hash: "source-hash", draft_version: 4, version: 4, bundle_hash: "bundle-hash", base_revision_id: 10 },
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

    renderPanel(
      <PlaybookCompatibilityPanel
        lang="ru"
        playbookId={7}
        sourceYaml="- hosts: web\n  tasks: []\n"
        report={{ status: "needs_adaptation", issues: [] }}
        onApplied={onApplied}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Подготовить адаптацию" }));

    await waitFor(() => expect(adaptPlaybookCompatibility).toHaveBeenCalledWith(7, { instruction: undefined }));
    expect(applyPlaybookCompatibility).not.toHaveBeenCalled();
    expect(await screen.findByText("Проверьте изменения перед применением")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "YAML diff" })).toBeInTheDocument();
    expect(screen.getAllByText(/hosts: web/).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("button", { name: "Применить проверенное предложение" }));

    await waitFor(() => expect(applyPlaybookCompatibility).toHaveBeenCalled());
    expect(applyPlaybookCompatibility).toHaveBeenCalledWith(7, {
      path: "site.yml",
      adapted_yaml: "- hosts: web\n  tasks: []\n",
      changes: ["Prepared for WebTerm runtime inventory"],
      expected_content_hash: "source-hash",
      expected_bundle_hash: "bundle-hash",
      expected_draft_version: 4,
      base_revision_id: 10,
    });
    await waitFor(() => expect(onApplied).toHaveBeenCalled());
  });

  it("keeps compatibility analysis read-only when adaptation is forbidden", () => {
    renderPanel(
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

  it("checks and adapts unsaved YAML, then puts the accepted proposal back in the editor", async () => {
    const source = "- hosts: web\n  vars:\n    package_name: nginx\n  tasks: []\n";
    const adapted = source.replace("package_name: nginx", 'package_name: "{{ webterm_package_name }}"');
    const report = { status: "needs_adaptation", ready: false, issues: [] };
    vi.mocked(analyzePlaybookSource).mockResolvedValue({ success: true, report });
    vi.mocked(adaptPlaybookSource).mockResolvedValue({
      success: true,
      proposal: {
        method: "ai",
        adapted_yaml: adapted,
        changes: ["Parameterize package name"],
        assumptions: [],
        semantic_guard: { passed: true, violations: [] },
        report,
      },
    });
    const onSourceAccepted = vi.fn();

    renderPanel(
      <PlaybookCompatibilityPanel
        lang="en"
        playbookId={null}
        sourceYaml={source}
        report={report}
        onApplied={vi.fn()}
        onSourceAccepted={onSourceAccepted}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Analyze" }));
    await waitFor(() => expect(analyzePlaybookSource).toHaveBeenCalledWith(source));
    fireEvent.click(screen.getByRole("button", { name: "Prepare adaptation" }));
    await waitFor(() => expect(adaptPlaybookSource).toHaveBeenCalledWith(source, { instruction: undefined }));
    fireEvent.click(await screen.findByRole("button", { name: "Apply reviewed proposal" }));

    expect(onSourceAccepted).toHaveBeenCalledWith(adapted, report);
    expect(applyPlaybookCompatibility).not.toHaveBeenCalled();
  });

  it("shows the semantic-guard rejection reason instead of masking it", async () => {
    vi.mocked(adaptPlaybookSource).mockResolvedValue({
      success: true,
      proposal: {
        method: "ai_rejected",
        adapted_yaml: "",
        changes: [],
        assumptions: [],
        semantic_guard: { passed: false, violations: ["task logic changed"] },
        report: { status: "needs_adaptation", issues: [] },
      },
    });

    renderPanel(
      <PlaybookCompatibilityPanel
        lang="en"
        playbookId={null}
        sourceYaml="- hosts: web\n  tasks: []\n"
        report={{ status: "needs_adaptation", issues: [] }}
        onApplied={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Prepare adaptation" }));
    expect(await screen.findByText("task logic changed")).toBeInTheDocument();
  });
});
