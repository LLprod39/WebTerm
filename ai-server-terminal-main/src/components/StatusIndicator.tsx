import { cn } from "@/lib/utils";
import type { ServerStatus } from "@/lib/api";

const statusConfig: Record<ServerStatus, { dotClass: string; label: string }> = {
  online: { dotClass: "status-dot-online", label: "Online" },
  offline: { dotClass: "status-dot-offline", label: "Offline" },
  unknown: { dotClass: "status-dot-unknown", label: "Unknown" },
};

export function StatusIndicator({ status, showLabel = true }: { status: ServerStatus; showLabel?: boolean }) {
  const { dotClass, label } = statusConfig[status];
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={cn("shrink-0", dotClass)} />
      {showLabel && <span className="text-xs text-muted-foreground">{label}</span>}
    </span>
  );
}
