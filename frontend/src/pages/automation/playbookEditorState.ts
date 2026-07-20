import type { PlaybookDetail } from "@/api/playbooks";
import type { PlaybookEditorState } from "./PlaybookEditor";
import { newLocalTaskId } from "./constants";

export const emptyPlaybookEditor = (): PlaybookEditorState => ({
  name: "",
  description: "",
  kind: "ansible",
  category: "custom",
  visibility: "private",
  tagsText: "",
  tasks: [{ id: newLocalTaskId(), command: "", description: "", continue_on_error: false }],
  sourceYaml: "",
  compatibility: {},
  activeCompatibilityRevision: null,
});

export function detailToPlaybookEditor(playbook: PlaybookDetail): PlaybookEditorState {
  return {
    name: playbook.name,
    description: playbook.description || "",
    kind: playbook.kind,
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
        : [{ id: newLocalTaskId(), command: "", description: "", continue_on_error: false }],
    sourceYaml: playbook.source_yaml || "",
    compatibility: playbook.compatibility || {},
    activeCompatibilityRevision: playbook.active_compatibility_revision || null,
  };
}
