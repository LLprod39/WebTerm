export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const secs = Math.floor(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  const remSecs = secs % 60;
  if (mins < 60) return `${mins}m ${remSecs}s`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ${mins % 60}m`;
}

export function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

export function formatCompactDateTime(value?: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function eventTypeClasses(eventType: string): string {
  if (eventType.includes("failed") || eventType.includes("error")) {
    return "border-destructive/30 bg-destructive/10 text-destructive";
  }
  if (eventType.includes("done") || eventType.includes("completed")) {
    return "border-success/30 bg-success/10 text-success";
  }
  if (eventType.includes("start") || eventType.includes("running")) {
    return "border-info/30 bg-info/10 text-info";
  }
  return "border-border/70 bg-card/60 text-muted-foreground";
}
