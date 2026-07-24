import { describe, expect, it } from "vitest";

import type { PlaybookDetail } from "@/api/playbooks";
import {
  applyDraftToPlaybookEditor,
  buildPlaybookPayload,
  detailToPlaybookEditor,
  emptyPlaybookEditor,
  isPlaybookEditorContentDirty,
  isPlaybookEditorDirty,
  isPlaybookEditorMetadataDirty,
} from "./playbookEditorState";

function detail(overrides: Partial<PlaybookDetail> = {}): PlaybookDetail {
  return {
    id: 7,
    name: "Deploy",
    description: "",
    kind: "ansible",
    category: "deploy",
    visibility: "private",
    tags: [],
    fidelity: {},
    compatibility: {},
    active_compatibility_revision: null,
    task_count: 1,
    is_template_clone: false,
    template_slug: "",
    last_run_at: null,
    last_run_status: "",
    created_at: null,
    updated_at: null,
    owner_id: 1,
    tasks: [{ id: "derived", command: "echo stale", description: "Derived", continue_on_error: false }],
    source_yaml: "- hosts: all\n  tasks: []\n",
    adapted_source_yaml: "",
    ...overrides,
  };
}

describe("playbook editor executable source", () => {
  it("sends YAML-backed playbooks as source-only payloads", () => {
    const editor = detailToPlaybookEditor(detail({ kind: "runbook" }));
    editor.sourceYaml = "- hosts: web\n  tasks: []\n";

    const payload = buildPlaybookPayload(editor);

    expect(payload).toMatchObject({
      name: "Deploy",
      kind: "ansible",
      source_yaml: "- hosts: web\n  tasks: []\n",
    });
    expect(payload).not.toHaveProperty("tasks");
  });

  it("keeps structured tasks as the sole runbook payload", () => {
    const editor = emptyPlaybookEditor();
    editor.name = "Restart service";
    editor.tasks = [
      { id: "t1", command: " systemctl restart nginx ", description: " Restart ", continue_on_error: false },
    ];

    const payload = buildPlaybookPayload(editor);

    expect(payload).toMatchObject({
      kind: "runbook",
      tasks: [{ id: "t1", command: "systemctl restart nginx", description: "Restart", continue_on_error: false }],
    });
    expect(payload).not.toHaveProperty("source_yaml");
  });

  it("tracks dirty state while preserving a read-only server snapshot", () => {
    const editor = detailToPlaybookEditor(detail());
    expect(editor.originalSourceYaml).toBe(editor.sourceYaml);
    expect(isPlaybookEditorDirty(editor)).toBe(false);

    editor.sourceYaml += "# local edit\n";

    expect(editor.originalSourceYaml).not.toBe(editor.sourceYaml);
    expect(isPlaybookEditorDirty(editor)).toBe(true);
  });

  it("tracks draft content independently from owner-only metadata", () => {
    const editor = detailToPlaybookEditor(detail());
    editor.description = "Owner metadata edit";

    expect(isPlaybookEditorContentDirty(editor)).toBe(false);
    expect(isPlaybookEditorMetadataDirty(editor)).toBe(true);

    const withDraft = applyDraftToPlaybookEditor(editor, {
      id: 3,
      base_revision_id: 9,
      content_format: "ansible_yaml",
      source_yaml: "- hosts: web\n  tasks: []\n",
      tasks: [],
      content_hash: "draft-hash",
      bundle_hash: "",
      version: 2,
      last_editor_id: 4,
      updated_at: "2026-07-24T10:00:00Z",
    });

    expect(withDraft.sourceYaml).toBe("- hosts: web\n  tasks: []\n");
    expect(withDraft.originalSourceYaml).toBe("- hosts: all\n  tasks: []\n");
    expect(isPlaybookEditorContentDirty(withDraft)).toBe(false);
    expect(isPlaybookEditorMetadataDirty(withDraft)).toBe(true);
  });
});
