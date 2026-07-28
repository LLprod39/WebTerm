import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { PlaybookDetail } from "@/api/playbooks";
import { PlaybookEditor } from "./PlaybookEditor";
import { detailToPlaybookEditor } from "./playbookEditorState";

vi.mock("@/components/editor/CodeEditor", () => ({
  CodeEditor: (props: {
    content: string;
    readOnly?: boolean;
    ariaLabel?: string;
    onChange?: (value: string) => void;
    onSave?: () => void;
    onDiagnosticsChange?: (diagnostics: unknown[]) => void;
  }) => (
    <div>
      <textarea
        aria-label={props.ariaLabel}
        value={props.content}
        readOnly={props.readOnly}
        onChange={(event) => props.onChange?.(event.target.value)}
        onKeyDown={(event) => {
          if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") props.onSave?.();
        }}
      />
      {props.onDiagnosticsChange ? (
        <button
          type="button"
          onClick={() =>
            props.onDiagnosticsChange?.([
              { from: 4, to: 5, line: 2, column: 3, severity: "error", message: "Syntax error" },
            ])
          }
        >
          emit syntax error
        </button>
      ) : null}
    </div>
  ),
}));

function sourcePlaybook(): PlaybookDetail {
  return {
    id: 12,
    name: "Imported deploy",
    description: "Deploy from YAML",
    kind: "ansible",
    category: "deploy",
    visibility: "private",
    tags: ["deploy"],
    fidelity: {},
    compatibility: { analyzer_version: 2, status: "ready", ready: true, issues: [] },
    active_compatibility_revision: null,
    task_count: 1,
    is_template_clone: false,
    template_slug: "",
    last_run_at: null,
    last_run_status: "",
    created_at: null,
    updated_at: null,
    owner_id: 1,
    tasks: [{ id: "derived", command: "echo stale", description: "Derived step", continue_on_error: false }],
    source_yaml: "- hosts: all\n  tasks: []\n",
    adapted_source_yaml: "",
  };
}

describe("PlaybookEditor YAML mode", () => {
  it("edits executable YAML, keeps the original read-only, and never exposes derived task controls", () => {
    const state = detailToPlaybookEditor(sourcePlaybook());
    const onChange = vi.fn();

    render(
      <PlaybookEditor
        lang="en"
        state={state}
        saving={false}
        dirty
        onChange={onChange}
        onSave={vi.fn()}
        onBack={vi.fn()}
        onRun={vi.fn()}
        title="Edit playbook"
        playbookId={12}
        onCompatibilityApplied={vi.fn()}
      />,
    );

    expect(screen.queryByText("Derived step")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Task 1 command")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Working Ansible YAML editor"), {
      target: { value: "- hosts: web\n  tasks: []\n" },
    });
    expect(onChange).toHaveBeenCalledWith({ sourceYaml: "- hosts: web\n  tasks: []\n" });

    fireEvent.mouseDown(screen.getByRole("tab", { name: "Original" }), { button: 0, ctrlKey: false });
    const original = screen.getByLabelText("Original Ansible YAML, read only");
    expect(original).toHaveValue("- hosts: all\n  tasks: []\n");
    expect(original).toHaveAttribute("readonly");
  });

  it("supports Ctrl+S and reports syntax blockers accessibly", () => {
    const state = detailToPlaybookEditor(sourcePlaybook());
    const onSave = vi.fn();

    render(
      <PlaybookEditor
        lang="en"
        state={state}
        saving={false}
        dirty
        onChange={vi.fn()}
        onSave={onSave}
        onBack={vi.fn()}
        onRun={vi.fn()}
        title="Edit playbook"
        playbookId={12}
        onCompatibilityApplied={vi.fn()}
      />,
    );

    fireEvent.keyDown(screen.getByLabelText("Working Ansible YAML editor"), { key: "s", ctrlKey: true });
    expect(onSave).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: "emit syntax error" }));
    expect(screen.getByText("YAML syntax errors")).toBeInTheDocument();
    expect(screen.getByText(/Line 2, column 3/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("enforces read-only and capability states in the editor controls", () => {
    render(
      <PlaybookEditor
        lang="en"
        state={detailToPlaybookEditor(sourcePlaybook())}
        saving={false}
        dirty
        readOnly
        metadataReadOnly
        canRun={false}
        canValidate={false}
        onChange={vi.fn()}
        onSave={vi.fn()}
        onBack={vi.fn()}
        onRun={vi.fn()}
        title="View playbook"
        playbookId={12}
        onCompatibilityApplied={vi.fn()}
      />,
    );

    expect(screen.getByLabelText("Working Ansible YAML editor")).toHaveAttribute("readonly");
    expect(screen.getByRole("button", { name: "Read only" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Prepare run…" })).toBeDisabled();
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Settings" }), { button: 0, ctrlKey: false });
    expect(screen.getByLabelText("Name *")).toBeDisabled();
  });
});
