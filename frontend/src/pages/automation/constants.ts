import type { PlaybookCategory, PlaybookRunStatus } from "@/api/playbooks";

export const CATEGORY_META: Record<
  PlaybookCategory,
  { labelRu: string; labelEn: string; accent: string; kicker: string; bar: string }
> = {
  deploy: { labelRu: "Deploy", labelEn: "Deploy", accent: "text-sky-300", kicker: "bg-sky-500/15 text-sky-300 border-sky-500/30", bar: "bg-sky-400" },
  patch: { labelRu: "Patch", labelEn: "Patch", accent: "text-amber-300", kicker: "bg-amber-500/15 text-amber-300 border-amber-500/30", bar: "bg-amber-400" },
  diagnose: { labelRu: "Diagnose", labelEn: "Diagnose", accent: "text-primary", kicker: "bg-primary/15 text-primary border-primary/30", bar: "bg-primary" },
  security: { labelRu: "Security", labelEn: "Security", accent: "text-rose-300", kicker: "bg-rose-500/15 text-rose-300 border-rose-500/30", bar: "bg-rose-400" },
  maintenance: { labelRu: "Maintenance", labelEn: "Maintenance", accent: "text-violet-300", kicker: "bg-violet-500/15 text-violet-300 border-violet-500/30", bar: "bg-violet-400" },
  custom: { labelRu: "Custom", labelEn: "Custom", accent: "text-muted-foreground", kicker: "bg-secondary text-muted-foreground border-border", bar: "bg-muted-foreground/50" },
};

export const RUN_STATUS_META: Record<
  PlaybookRunStatus,
  { labelRu: string; labelEn: string; className: string; dot: string }
> = {
  pending: { labelRu: "В очереди", labelEn: "Pending", className: "text-muted-foreground", dot: "bg-muted-foreground/60" },
  running: { labelRu: "Идёт", labelEn: "Running", className: "text-primary", dot: "bg-primary animate-pulse" },
  completed: { labelRu: "Успех", labelEn: "Completed", className: "text-emerald-400", dot: "bg-emerald-400" },
  failed: { labelRu: "Ошибка", labelEn: "Failed", className: "text-destructive", dot: "bg-destructive" },
  partial: { labelRu: "Частично", labelEn: "Partial", className: "text-amber-300", dot: "bg-amber-400" },
  cancelled: { labelRu: "Отменён", labelEn: "Cancelled", className: "text-muted-foreground", dot: "bg-muted-foreground/60" },
};

export const CATEGORIES: PlaybookCategory[] = [
  "diagnose",
  "deploy",
  "patch",
  "security",
  "maintenance",
  "custom",
];

export function newLocalTaskId() {
  return `t_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}
