import { CheckCircle2, FileCode2, FileText, type LucideIcon } from "lucide-react";
import type { AgentInputArtifact } from "@/lib/api";
import { localize } from "@/lib/i18n";

export const ARTIFACT_KINDS: Array<{ kind: AgentInputArtifact["kind"]; labelRu: string; labelEn: string; icon: LucideIcon }> = [
  { kind: "document", labelRu: "Документ", labelEn: "Document", icon: FileText },
  { kind: "task_list", labelRu: "Список задач", labelEn: "Task list", icon: CheckCircle2 },
  { kind: "script", labelRu: "Скрипт", labelEn: "Script", icon: FileCode2 },
];

export type AgentTaskDraft = NonNullable<AgentInputArtifact["tasks"]>[number];

export function artifactKindLabel(kind: AgentInputArtifact["kind"], lang: string) {
  const match = ARTIFACT_KINDS.find((item) => item.kind === kind);
  return match ? localize(lang, match.labelRu, match.labelEn) : kind;
}

export function artifactKindIcon(kind: AgentInputArtifact["kind"]) {
  return ARTIFACT_KINDS.find((item) => item.kind === kind)?.icon || FileText;
}

export function parseTasksFromContent(content: string): AgentTaskDraft[] {
  return String(content || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const clean = line.replace(/^[-*]\s*(\[[ xX]\])?\s*/, "");
      const [title, ...detailsParts] = clean.split(/\s+[—-]\s+/);
      return {
        title: (title || clean).trim(),
        details: detailsParts.join(" - ").trim(),
        done: /^\s*[-*]\s*\[[xX]\]/.test(line),
      };
    })
    .filter((task) => task.title);
}

export function tasksToContent(tasks: AgentTaskDraft[] | undefined): string {
  return (tasks || [])
    .filter((task) => task.title.trim() || (task.details || "").trim())
    .map((task) => {
      const details = (task.details || "").trim();
      return `- [${task.done ? "x" : " "}] ${task.title.trim()}${details ? ` — ${details}` : ""}`;
    })
    .join("\n");
}

export function normalizeArtifactDraft(item: AgentInputArtifact): AgentInputArtifact {
  if (item.kind !== "task_list") return item;
  const tasks = item.tasks?.length ? item.tasks : parseTasksFromContent(item.content || "");
  return { ...item, tasks };
}

export function prepareArtifactForSave(item: AgentInputArtifact): AgentInputArtifact {
  const name = item.name.trim();
  const run_hint = (item.run_hint || "").trim();
  if (item.kind === "task_list") {
    const tasks = (item.tasks || [])
      .map((task) => ({
        title: task.title.trim(),
        details: (task.details || "").trim(),
        done: Boolean(task.done),
      }))
      .filter((task) => task.title || task.details);
    return { ...item, name, run_hint, tasks, content: tasksToContent(tasks) };
  }
  return { ...item, name, run_hint, content: item.content.trim() };
}

export function artifactSummary(item: AgentInputArtifact, lang: string) {
  if (item.kind === "task_list") {
    const total = item.tasks?.length || parseTasksFromContent(item.content || "").length;
    return localize(lang, `${total} задач`, `${total} tasks`);
  }
  const chars = (item.content || "").length;
  if (item.size_bytes) {
    const kb = Math.max(1, Math.round(item.size_bytes / 1024));
    return `${kb} KB · ${chars} chars`;
  }
  return `${chars} chars`;
}
