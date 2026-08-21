import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { PlaybookDetail } from "@/api/playbooks";
import { PlaybookEditor } from "./PlaybookEditor";
import { detailToPlaybookEditor, emptyPlaybookEditor } from "./playbookEditorState";

vi.mock("@/components/editor/CodeEditor", () => ({
  CodeEditor: (props: { content: string; readOnly?: boolean; ariaLabel?: string; onChange?: (value: string) => void; onSave?: () => void }) => (
    <textarea
      aria-label={props.ariaLabel}
      value={props.content}
      readOnly={props.readOnly}
      onChange={(event) => props.onChange?.(event.target.value)}
      onKeyDown={(event) => {
        if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") props.onSave?.();
      }}
    />
  ),
}));

vi.mock("./PlaybookCompatibilityPanel", () => ({
  PlaybookCompatibilityPanel: () => <section aria-label="AI check">AI check</section>,
}));

function sourcePlaybook(): PlaybookDetail {
  return {
    id: 12,
    name: "Imported deploy",
    description: "Deploy from YAML",
    kind: "ansible",
    category: "deploy",
    visibility: "private",
    tags: [],
    fidelity: {},
    compatibility: { status: "ready", ready: true, issues: [] },
    active_compatibility_revision: null,
    task_count: 1,
    is_template_clone: false,
    template_slug: "",
    last_run_at: null,
    last_run_status: "",
    created_at: null,
    updated_at: null,
    owner_id: 1,
    tasks: [],
    source_yaml: "- hosts: all\n  tasks: []\n",
    adapted_source_yaml: "",
  };
}

function renderEditor(overrides: Partial<React.ComponentProps<typeof PlaybookEditor>> = {}) {
  const props: React.ComponentProps<typeof PlaybookEditor> = {
    lang: "en",
    state: emptyPlaybookEditor(),
    saving: false,
    dirty: true,
    onChange: vi.fn(),
    onSave: vi.fn(),
    onBack: vi.fn(),
    onRun: vi.fn(),
    playbookId: null,
    onCompatibilityApplied: vi.fn(),
    onImportYaml: vi.fn(),
    onImportProject: vi.fn(),
    ...overrides,
  };
  return { ...render(<PlaybookEditor {...props} />), props };
}

describe("PlaybookEditor minimal Ansible flow", () => {
  it("opens a clean YAML editor with import as secondary actions", () => {
    const { props } = renderEditor();

    expect(screen.getByRole("heading", { name: "Create Ansible" })).toBeInTheDocument();
    expect(screen.getByLabelText("Working Ansible YAML editor")).toHaveValue("");
    expect(screen.queryByText(/template/i)).not.toBeInTheDocument();
    expect(screen.queryByText("Advanced settings")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Load YAML" }));
    fireEvent.click(screen.getByRole("button", { name: "GitLab or archive" }));
    expect(props.onImportYaml).toHaveBeenCalledTimes(1);
    expect(props.onImportProject).toHaveBeenCalledTimes(1);
  });

  it("accepts pasted YAML and exposes AI check before the first save", () => {
    const state = emptyPlaybookEditor();
    state.name = "Deploy";
    state.sourceYaml = "- hosts: all\n  tasks: []\n";
    const { props } = renderEditor({ state });

    expect(screen.getByLabelText("AI check")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Working Ansible YAML editor"), {
      target: { value: "- hosts: web\n  tasks: []\n" },
    });
    expect(props.onChange).toHaveBeenCalledWith({ sourceYaml: "- hosts: web\n  tasks: []\n" });
  });

  it("keeps run unavailable until a saved, unchanged playbook exists", () => {
    renderEditor({ state: detailToPlaybookEditor(sourcePlaybook()), playbookId: 12, dirty: false });

    expect(screen.getByRole("button", { name: "Saved" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Choose servers" })).toBeEnabled();
  });

  it("enforces read-only controls", () => {
    renderEditor({
      state: detailToPlaybookEditor(sourcePlaybook()),
      playbookId: 12,
      readOnly: true,
      metadataReadOnly: true,
    });

    expect(screen.getByLabelText("Working Ansible YAML editor")).toHaveAttribute("readonly");
    expect(screen.getByRole("button", { name: "Load YAML" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "GitLab or archive" })).toBeDisabled();
  });
});
