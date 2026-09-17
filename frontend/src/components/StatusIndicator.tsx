import { cn } from "@/lib/utils";
import type { FleetHealthStatus, ServerStatus } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { StatusBadge } from "@/components/system/StatusBadge";
import { fleetHealthPresentation, serverStatusPresentation } from "@/design/status";

export function FleetHealthIndicator({
  status,
  showLabel = true,
  stale = false,
}: {
  status: FleetHealthStatus;
  showLabel?: boolean;
  stale?: boolean;
}) {
  const { t } = useI18n();
  const cfg = fleetHealthPresentation(status);
  const label = stale ? `${t(cfg.labelKey)} · ${t("health.stale")}` : t(cfg.labelKey);

  if (showLabel) {
    return <StatusBadge label={label} tone={cfg.tone} pulse={cfg.pulse} />;
  }

  return (
    <span
      className="inline-flex items-center gap-1.5"
      title={label}
    >
      <span className="relative flex h-2 w-2 shrink-0">
        {cfg.pulse && (
          <span className={cn("absolute inline-flex h-full w-full animate-ping rounded-full opacity-60", cfg.tone === "success" ? "bg-success" : cfg.tone === "warning" ? "bg-warning" : cfg.tone === "danger" ? "bg-destructive" : "bg-muted-foreground/70")} />
        )}
        <span className={cn("relative inline-flex h-2 w-2 rounded-full", cfg.tone === "success" ? "bg-success" : cfg.tone === "warning" ? "bg-warning" : cfg.tone === "danger" ? "bg-destructive" : "bg-muted-foreground/70", stale && "opacity-50")} />
      </span>
    </span>
  );
}

export function StatusIndicator({ status, showLabel = true }: { status: ServerStatus; showLabel?: boolean }) {
  const { t } = useI18n();
  const cfg = serverStatusPresentation(status);

  if (showLabel) {
    return <StatusBadge label={t(cfg.labelKey)} tone={cfg.tone} pulse={cfg.pulse} />;
  }

  return (
    <span className="inline-flex items-center gap-1.5" title={t(cfg.labelKey)}>
      <span className="relative flex h-2 w-2 shrink-0">
        {cfg.pulse && (
          <span className={cn("absolute inline-flex h-full w-full animate-ping rounded-full opacity-60", cfg.tone === "success" ? "bg-success" : cfg.tone === "danger" ? "bg-destructive" : "bg-muted-foreground/70")} />
        )}
        <span className={cn("relative inline-flex h-2 w-2 rounded-full", cfg.tone === "success" ? "bg-success" : cfg.tone === "danger" ? "bg-destructive" : "bg-muted-foreground/70")} />
      </span>
    </span>
  );
}
