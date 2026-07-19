import type { FleetHealthStatus, ServerStatus } from "@/lib/api";

export type StatusTone = "neutral" | "success" | "warning" | "danger" | "info" | "ai";

export interface StatusPresentation {
  labelKey: string;
  tone: StatusTone;
  pulse?: boolean;
}

export function serverStatusPresentation(status: ServerStatus): StatusPresentation {
  switch (status) {
    case "online":
      return { labelKey: "status.online", tone: "success", pulse: true };
    case "offline":
      return { labelKey: "status.offline", tone: "danger" };
    case "unknown":
    default:
      return { labelKey: "status.unknown", tone: "neutral" };
  }
}

export function fleetHealthPresentation(status: FleetHealthStatus): StatusPresentation {
  switch (status) {
    case "healthy":
      return { labelKey: "health.healthy", tone: "success" };
    case "warning":
      return { labelKey: "health.warning", tone: "warning" };
    case "critical":
      return { labelKey: "health.critical", tone: "danger", pulse: true };
    case "unreachable":
      return { labelKey: "health.unreachable", tone: "danger" };
    case "unknown":
    default:
      return { labelKey: "health.unknown", tone: "neutral" };
  }
}

export function agentRunStatusPresentation(status: string): StatusPresentation {
  switch (status) {
    case "running":
      return { labelKey: "run.status.running", tone: "info", pulse: true };
    case "pending":
      return { labelKey: "run.status.pending", tone: "neutral" };
    case "paused":
      return { labelKey: "run.status.paused", tone: "warning" };
    case "waiting":
      return { labelKey: "run.status.waiting", tone: "warning" };
    case "plan_review":
      return { labelKey: "run.status.plan_review", tone: "ai" };
    case "completed":
      return { labelKey: "run.status.completed", tone: "success" };
    case "failed":
      return { labelKey: "run.status.failed", tone: "danger" };
    case "stopped":
      return { labelKey: "run.status.stopped", tone: "neutral" };
    default:
      return { labelKey: "run.status.unknown", tone: "neutral" };
  }
}

export const statusToneClasses: Record<StatusTone, { badge: string; icon: string; dot: string }> = {
  neutral: {
    badge: "border-border/70 bg-secondary/55 text-muted-foreground",
    icon: "text-muted-foreground",
    dot: "bg-muted-foreground/70",
  },
  success: {
    badge: "border-success/30 bg-success/10 text-success",
    icon: "text-success",
    dot: "bg-success",
  },
  warning: {
    badge: "border-warning/35 bg-warning/10 text-warning",
    icon: "text-warning",
    dot: "bg-warning",
  },
  danger: {
    badge: "border-destructive/35 bg-destructive/10 text-destructive",
    icon: "text-destructive",
    dot: "bg-destructive",
  },
  info: {
    badge: "border-info/35 bg-info/10 text-info",
    icon: "text-info",
    dot: "bg-info",
  },
  ai: {
    badge: "border-ai/35 bg-ai/10 text-ai",
    icon: "text-ai",
    dot: "bg-ai",
  },
};
