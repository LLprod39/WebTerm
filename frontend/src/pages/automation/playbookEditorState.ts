import type {
  PlaybookCategory,
  PlaybookCompatibilityReport,
  PlaybookCompatibilityRevision,
  PlaybookDetail,
  PlaybookDraft,
  PlaybookKind,
  PlaybookTask,
  PlaybookVisibility,
} from "@/api/playbooks";
import { newLocalTaskId } from "./constants";

export interface PlaybookEditorState {
  name: string;
  description: string;
  kind: PlaybookKind;
  category: PlaybookCategory;
  visibility: PlaybookVisibility;
  tagsText: string;
  tasks: PlaybookTask[];
  /** Editable executable YAML for source-backed Ansible playbooks. */
  sourceYaml: string;
  /** Read-only server snapshot captured when the editor was opened/saved. */
  originalSourceYaml: string;
  compatibility: PlaybookCompatibilityReport;
  activeCompatibilityRevision: PlaybookCompatibilityRevision | null;
  savedContentFingerprint: string;
  savedMetadataFingerprint: string;
}

export interface PlaybookSavePayload {
  name: string;
  description: string;
  kind: PlaybookKind;
  category: PlaybookCategory;
  visibility: PlaybookVisibility;
  tags: string[];
  tasks?: PlaybookTask[];
  source_yaml?: string;
}

type FingerprintableEditor = Omit<PlaybookEditorState, "savedContentFingerprint" | "savedMetadataFingerprint">;

export function playbookEditorContentFingerprint(
  state: Pick<PlaybookEditorState, "kind" | "tasks" | "sourceYaml" | "originalSourceYaml">,
): string {
  const sourceBacked = Boolean(state.sourceYaml || state.originalSourceYaml);
  return JSON.stringify(
    sourceBacked
      ? { contentFormat: "ansible_yaml", sourceYaml: state.sourceYaml }
      : { contentFormat: "runbook_json", tasks: state.tasks },
  );
}

export function playbookEditorMetadataFingerprint(
  state: Pick<PlaybookEditorState, "name" | "description" | "category" | "visibility" | "tagsText">,
): string {
  return JSON.stringify({
    name: state.name,
    description: state.description,
    category: state.category,
    visibility: state.visibility,
    tagsText: state.tagsText,
  });
}

export function playbookEditorFingerprint(
  state: Pick<
    PlaybookEditorState,
    | "name"
    | "description"
    | "kind"
    | "category"
    | "visibility"
    | "tagsText"
    | "tasks"
    | "sourceYaml"
    | "originalSourceYaml"
  >,
): string {
  return `${playbookEditorMetadataFingerprint(state)}:${playbookEditorContentFingerprint(state)}`;
}

function withSavedFingerprint(state: FingerprintableEditor): PlaybookEditorState {
  return {
    ...state,
    savedContentFingerprint: playbookEditorContentFingerprint(state),
    savedMetadataFingerprint: playbookEditorMetadataFingerprint(state),
  };
}

export function isSourceBackedPlaybook(state: PlaybookEditorState): boolean {
  return state.kind === "ansible" || Boolean(state.sourceYaml || state.originalSourceYaml);
}

export function isPlaybookEditorDirty(state: PlaybookEditorState): boolean {
  return isPlaybookEditorContentDirty(state) || isPlaybookEditorMetadataDirty(state);
}

export function isPlaybookEditorContentDirty(state: PlaybookEditorState): boolean {
  return playbookEditorContentFingerprint(state) !== state.savedContentFingerprint;
}

export function isPlaybookEditorMetadataDirty(state: PlaybookEditorState): boolean {
  return playbookEditorMetadataFingerprint(state) !== state.savedMetadataFingerprint;
}

export function markPlaybookEditorContentSaved(state: PlaybookEditorState): PlaybookEditorState {
  return { ...state, savedContentFingerprint: playbookEditorContentFingerprint(state) };
}

export function markPlaybookEditorMetadataSaved(state: PlaybookEditorState): PlaybookEditorState {
  return { ...state, savedMetadataFingerprint: playbookEditorMetadataFingerprint(state) };
}

export function applyDraftToPlaybookEditor(
  state: PlaybookEditorState,
  draft: PlaybookDraft,
): PlaybookEditorState {
  const sourceBacked = draft.content_format === "ansible_yaml";
  const tasks = draft.tasks?.length
    ? draft.tasks
    : sourceBacked
      ? []
      : [{ id: newLocalTaskId(), command: "", description: "", continue_on_error: false }];
  const next: PlaybookEditorState = {
    ...state,
    kind: sourceBacked ? "ansible" : "runbook",
    sourceYaml: sourceBacked ? draft.source_yaml : "",
    tasks,
  };
  return markPlaybookEditorContentSaved(next);
}

/**
 * Build an honest save payload: YAML-backed Ansible and structured runbooks are
 * mutually exclusive executable representations.
 */
export function buildPlaybookPayload(state: PlaybookEditorState): PlaybookSavePayload {
  const tags = state.tagsText
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
  const base = {
    name: state.name.trim(),
    description: state.description.trim(),
    category: state.category,
    visibility: state.visibility,
    tags,
  };

  if (isSourceBackedPlaybook(state)) {
    return {
      ...base,
      kind: "ansible",
      source_yaml: state.sourceYaml,
    };
  }

  return {
    ...base,
    kind: "ansible",
    tasks: state.tasks
      .filter((task) => task.command.trim())
      .map((task) => ({
        id: task.id,
        command: task.command.trim(),
        description: task.description.trim(),
        continue_on_error: task.continue_on_error,
      })),
  };
}

export const emptyPlaybookEditor = (): PlaybookEditorState =>
  withSavedFingerprint({
    name: "",
    description: "",
    kind: "runbook",
    category: "custom",
    visibility: "private",
    tagsText: "",
    tasks: [],
    sourceYaml: "",
    originalSourceYaml: "",
    compatibility: {},
    activeCompatibilityRevision: null,
  });

export function detailToPlaybookEditor(playbook: PlaybookDetail): PlaybookEditorState {
  const sourceYaml = playbook.source_yaml || "";
  return withSavedFingerprint({
    name: playbook.name,
    description: playbook.description || "",
    kind: sourceYaml ? "ansible" : playbook.kind,
    category: playbook.category,
    visibility: playbook.visibility,
    tagsText: (playbook.tags || []).join(", "),
    tasks:
      playbook.tasks?.length > 0
        ? playbook.tasks.map((task) => ({
            id: task.id || newLocalTaskId(),
            command: String(task?.command ?? ""),
            description: String(task?.description ?? ""),
            continue_on_error: Boolean(task?.continue_on_error),
          }))
        : sourceYaml
          ? []
          : [{ id: newLocalTaskId(), command: "", description: "", continue_on_error: false }],
    sourceYaml,
    originalSourceYaml: sourceYaml,
    compatibility: playbook.compatibility || {},
    activeCompatibilityRevision: playbook.active_compatibility_revision || null,
  });
}
