import { cn } from "@/lib/utils";
import type { FleetHealthStatus, ServerStatus } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

const statusConfig: Record<ServerStatus, { color: string; labelKey: string; pulse: boolean }> = {
  online: { color: "bg-primary", labelKey: "status.online", pulse: true },
  offline: { color: "bg-destructive", labelKey: "status.offline", pulse: false },
  unknown: { color: "bg-muted-foreground", labelKey: "status.unknown", pulse: false },
};

const fleetHealthConfig: Record<
  FleetHealthStatus,
  { color: string; labelKey: string; pulse: boolean }
> = {
  healthy: { color: "bg-primary", labelKey: "health.healthy", pulse: false },
  warning: { color: "bg-yellow-500", labelKey: "health.warning", pulse: false },
  critical: { color: "bg-destructive", labelKey: "health.critical", pulse: true },
  unreachable: { color: "bg-destructive", labelKey: "health.unreachable", pulse: false },
  unknown: { color: "bg-muted-foreground", labelKey: "health.unknown", pulse: false },
};

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
  const cfg = fleetHealthConfig[status] || fleetHealthConfig.unknown;
  return (
    <span
      className="inline-flex items-center gap-1.5"
      title={stale ? `${t(cfg.labelKey)} · ${t("health.stale")}` : t(cfg.labelKey)}
    >
      <span className="relative flex h-2 w-2 shrink-0">
        {cfg.pulse && (
          <span className={cn("absolute inline-flex h-full w-full animate-ping rounded-full opacity-60", cfg.color)} />
        )}
        <span className={cn("relative inline-flex h-2 w-2 rounded-full", cfg.color, stale && "opacity-50")} />
      </span>
      {showLabel && (
        <span
          className={cn(
            "text-[11px] font-medium",
            status === "healthy"
              ? "text-primary"
              : status === "warning"
                ? "text-yellow-500"
                : status === "critical" || status === "unreachable"
                  ? "text-destructive"
                  : "text-muted-foreground",
          )}
        >
          {t(cfg.labelKey)}
        </span>
      )}
    </span>
  );
}

export function StatusIndicator({ status, showLabel = true }: { status: ServerStatus; showLabel?: boolean }) {
  const { t } = useI18n();
  const cfg = statusConfig[status] || statusConfig.unknown;
  return (
    <span className="inline-flex items-center gap-1.5" title={t(cfg.labelKey)}>
      <span className="relative flex h-2 w-2 shrink-0">
        {cfg.pulse && (
          <span className={cn("absolute inline-flex h-full w-full animate-ping rounded-full opacity-60", cfg.color)} />
        )}
        <span className={cn("relative inline-flex h-2 w-2 rounded-full", cfg.color)} />
      </span>
      {showLabel && (
        <span className={cn(
          "text-[11px] font-medium",
          status === "online" ? "text-primary" : status === "offline" ? "text-destructive" : "text-muted-foreground"
        )}>
          {t(cfg.labelKey)}
        </span>
      )}
    </span>
  );
}
