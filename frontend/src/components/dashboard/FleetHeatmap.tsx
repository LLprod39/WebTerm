import { WifiOff } from "lucide-react";
import { Link } from "react-router-dom";

import type { ServerHealth } from "@/api";
import { localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const statusAccent: Record<ServerHealth["status"], string> = {
  healthy: "bg-success",
  warning: "bg-warning",
  critical: "bg-destructive",
  unreachable: "bg-destructive",
  unknown: "bg-muted-foreground/40",
};

function barTone(value: number | null): string {
  if (value === null) return "bg-muted-foreground/25";
  if (value > 85) return "bg-destructive";
  if (value > 65) return "bg-warning";
  return "bg-success";
}

function MicroBar({ label, value }: { label: string; value: number | null }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="w-7 shrink-0 text-2xs font-medium uppercase text-muted-foreground/60">{label}</span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-none bg-surface-0">
        <div
          className={cn("h-full transition-all", barTone(value))}
          style={{ width: `${Math.min(100, Math.max(2, value ?? 0))}%` }}
        />
      </div>
      <span className="w-8 shrink-0 text-right font-mono text-2xs tabular-nums text-muted-foreground">
        {value === null ? "—" : `${Math.round(value)}%`}
      </span>
    </div>
  );
}

/**
 * Fleet at a glance: one compact tile per server with status accent and
 * CPU/RAM/disk micro-bars. Click opens the server terminal.
 */
export function FleetHeatmap({ servers, lang }: { servers: ServerHealth[]; lang: string }) {
  if (servers.length === 0) {
    return (
      <div className="rounded-sm border border-dashed border-border bg-surface-1/60 py-8 text-center text-xs text-muted-foreground">
        {localize(lang, "Нет данных мониторинга — добавьте серверы или запустите проверку.", "No monitoring data — add servers or run a check.")}
      </div>
    );
  }

  return (
    <div className="grid gap-2 [grid-template-columns:repeat(auto-fill,minmax(170px,1fr))]">
      {servers.map((server) => {
        const offline = server.status === "unreachable";
        return (
          <Link
            key={server.server_id}
            to={`/servers/${server.server_id}/terminal`}
            title={`${server.server_name} (${server.host})`}
            className={cn(
              "group relative overflow-hidden rounded-sm border border-border bg-surface-1 px-3 py-2.5 transition-all hover:border-primary/50 hover:shadow-elev-1",
              offline && "opacity-75",
            )}
          >
            <div className={cn("absolute inset-x-0 top-0 h-0.5", statusAccent[server.status])} />
            <div className="flex items-center justify-between gap-2">
              <span className="truncate text-xs font-semibold text-foreground/95">{server.server_name}</span>
              {offline ? (
                <WifiOff className="h-3.5 w-3.5 shrink-0 text-destructive" />
              ) : (
                <span className={cn("h-1.5 w-1.5 shrink-0 rounded-none", statusAccent[server.status])} />
              )}
            </div>
            <div className="mt-0.5 truncate font-mono text-2xs text-muted-foreground/60">{server.host}</div>
            {offline ? (
              <div className="mt-2.5 text-2xs font-medium uppercase tracking-[0.1em] text-destructive">
                {localize(lang, "нет связи", "unreachable")}
              </div>
            ) : (
              <div className="mt-2.5 space-y-1">
                <MicroBar label="CPU" value={server.cpu_percent} />
                <MicroBar label="RAM" value={server.memory_percent} />
                <MicroBar label="HDD" value={server.disk_percent} />
              </div>
            )}
          </Link>
        );
      })}
    </div>
  );
}
