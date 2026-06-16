import type { MemorySnapshotItem } from "@/lib/api";

import type { UserKnowledgeFilter } from "./types";

export function matchesKnowledgeQuery(parts: Array<string | null | undefined>, query: string) {
  if (!query) return true;
  return parts.some((part) => String(part || "").toLowerCase().includes(query));
}

export function renderMemorySnapshotContent(item: MemorySnapshotItem) {
  const lines = String(item.content || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  if (String(item.memory_key || "").toLowerCase() === "human_habits") {
    const normalized = lines.map((line) => line.replace(/^-+\s*/, "").trim());
    if (
      normalized.length === 1 &&
      normalized[0].toLowerCase() === "повторяющиеся ручные привычки пока не выделены."
    ) {
      return normalized[0];
    }
  }

  if (String(item.memory_key || "").toLowerCase() === "access") {
    const filtered = lines.filter((line) => {
      const normalized = line.replace(/^-+\s*/, "").trim().toLowerCase();
      if (normalized.startsWith("command used:") || normalized.startsWith("команда:")) {
        return false;
      }
      return !/^(systemctl|journalctl|ss|curl|docker|uptime|df|free|ip)\b/.test(normalized);
    });
    return filtered.join("\n") || String(item.content || "");
  }

  return String(item.content || "");
}

export function memorySnapshotAudienceKind(item: MemorySnapshotItem): Exclude<UserKnowledgeFilter, "all"> {
  const memoryKey = String(item.memory_key || "").toLowerCase();
  const title = String(item.title || "").toLowerCase();
  const blob = `${item.title || ""}\n${item.content || ""}`.toLowerCase();
  if (/профиль|profile|summary|сводка|overview/.test(title)) {
    return "summary";
  }
  if (/риск|risk|issue|incident|alert|замечан/.test(title)) {
    return "risks";
  }
  if (/доступ|access|network|ssh|vpn|порт/.test(title)) {
    return "access";
  }
  if (/инструк|runbook|playbook|workflow|skill|checklist|чеклист/.test(title)) {
    return "instructions";
  }
  if (/изменен|change|deploy|release|migration|rollout|обновл/.test(title)) {
    return "changes";
  }
  if (memoryKey === "access" || /доступ|ssh|порт|network|host:|docker publish/.test(blob)) {
    return "access";
  }
  if (memoryKey === "risks" || /риск|warning|critical|incident|проблем|ошиб/.test(blob)) {
    return "risks";
  }
  if (memoryKey === "recent_changes" || /измен|обновл|запущен контейнер|reload|restart|rollout/.test(blob)) {
    return "changes";
  }
  if (
    memoryKey === "runbook" ||
    item.kind === "pattern" ||
    item.kind === "automation" ||
    item.kind === "skill_draft"
  ) {
    return "instructions";
  }
  return "summary";
}

export function memorySnapshotAudienceLabel(item: MemorySnapshotItem, t: (key: string) => string) {
  switch (memorySnapshotAudienceKind(item)) {
    case "access":
      return t("srv.knowledge_filter_access");
    case "risks":
      return t("srv.knowledge_filter_risks");
    case "changes":
      return t("srv.knowledge_filter_changes");
    case "instructions":
      return t("srv.knowledge_filter_instructions");
    default:
      return t("srv.knowledge_filter_summary");
  }
}

export function memorySnapshotAudienceBadgeClass(item: MemorySnapshotItem) {
  switch (memorySnapshotAudienceKind(item)) {
    case "access":
      return "bg-secondary text-foreground";
    case "risks":
      return "bg-destructive/15 text-destructive";
    case "changes":
      return "bg-secondary text-foreground";
    case "instructions":
      return "bg-primary/15 text-primary";
    default:
      return "bg-secondary text-foreground";
  }
}
