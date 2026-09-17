import type { PlaybookCategory, PlaybookRunStatus } from "@/api/playbooks";

export const CATEGORY_META: Record<
  PlaybookCategory,
  { labelRu: string; labelEn: string; accent: string; kicker: string; bar: string }
> = {
  deploy: { labelRu: "Развёртывание", labelEn: "Deploy", accent: "text-info", kicker: "bg-info/15 text-info border-info/30", bar: "bg-info" },
  patch: { labelRu: "Обновление", labelEn: "Patch", accent: "text-warning", kicker: "bg-warning/15 text-warning border-warning/30", bar: "bg-warning" },
  diagnose: { labelRu: "Диагностика", labelEn: "Diagnose", accent: "text-primary", kicker: "bg-primary/15 text-primary border-primary/30", bar: "bg-primary" },
  security: { labelRu: "Безопасность", labelEn: "Security", accent: "text-destructive", kicker: "bg-destructive/15 text-destructive border-destructive/30", bar: "bg-destructive" },
  maintenance: { labelRu: "Обслуживание", labelEn: "Maintenance", accent: "text-ai", kicker: "bg-ai/15 text-ai border-ai/30", bar: "bg-ai" },
  custom: { labelRu: "Другое", labelEn: "Custom", accent: "text-muted-foreground", kicker: "bg-secondary text-muted-foreground border-border", bar: "bg-muted-foreground/50" },
};

export const RUN_STATUS_META: Record<
  PlaybookRunStatus,
  { labelRu: string; labelEn: string; className: string; dot: string }
> = {
  pending: { labelRu: "В очереди", labelEn: "Pending", className: "text-muted-foreground", dot: "bg-muted-foreground/60" },
  running: { labelRu: "Идёт", labelEn: "Running", className: "text-primary", dot: "bg-primary animate-pulse" },
  completed: { labelRu: "Успех", labelEn: "Completed", className: "text-success", dot: "bg-success" },
  failed: { labelRu: "Ошибка", labelEn: "Failed", className: "text-destructive", dot: "bg-destructive" },
  partial: { labelRu: "Частично", labelEn: "Partial", className: "text-warning", dot: "bg-warning" },
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
