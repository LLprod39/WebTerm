import type { WorkspaceAppId, WorkspaceAppStatus } from "./WorkspaceChrome";

// Overview is beta/hidden in pilot; land on Files when the Linux UI opens.
export const DEFAULT_ACTIVE_APP: WorkspaceAppId = "files";

export function workspaceStatusClass(status: WorkspaceAppStatus) {
  if (status === "live") return "border-success/20 bg-success/8 text-success";
  if (status === "ready") return "border-primary/20 bg-primary/8 text-primary";
  if (status === "next") return "border-warning/20 bg-warning/8 text-warning";
  return "border-border bg-secondary/70 text-muted-foreground";
}

export function workspaceStatusLabel(status: WorkspaceAppStatus) {
  if (status === "live") return "Готово";
  if (status === "ready") return "Доступно";
  if (status === "next") return "Запланировано";
  return "Недоступно";
}

const PANEL_HEIGHT_CLASSES: Partial<Record<WorkspaceAppId, string>> = {
  files: "min-h-[32rem]",
  services: "min-h-[32rem]",
  "text-editor": "min-h-[32rem]",
  settings: "min-h-[30rem]",
};

export function panelHeightClass(appId: WorkspaceAppId) {
  return PANEL_HEIGHT_CLASSES[appId] || "min-h-[28rem]";
}
