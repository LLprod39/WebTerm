import type { ReactNode } from "react";
import { Activity, HardDrive, MemoryStick } from "lucide-react";

import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export type MetricsSnapshot = {
  server_id?: number;
  name?: string;
  host?: string;
  status?: string;
  cpu_percent?: number | null;
  mem_percent?: number | null;
  disk_percent?: number | null;
  disk_mounts?: Array<{
    mount?: string;
    percent?: number | null;
    used_gb?: number | null;
    total_gb?: number | null;
  }>;
  collected_at?: string | null;
  note?: string | null;
};

function clampPct(v: number | null | undefined): number | null {
  if (v == null || Number.isNaN(Number(v))) return null;
  return Math.max(0, Math.min(100, Number(v)));
}

function barTone(pct: number | null): string {
  if (pct == null) return "bg-muted-foreground/25";
  if (pct >= 90) return "bg-destructive";
  if (pct >= 75) return "bg-warning";
  return "bg-success";
}

function statusTone(status: string): string {
  const s = status.toLowerCase();
  if (s === "healthy") return "bg-success/15 text-success";
  if (s === "warning") return "bg-warning/15 text-warning";
  if (s === "critical") return "bg-destructive/15 text-destructive";
  if (s === "unreachable") return "bg-muted text-muted-foreground";
  return "bg-muted text-muted-foreground";
}

function formatPct(pct: number | null): string {
  if (pct == null) return "—";
  return `${pct < 10 ? pct.toFixed(1) : Math.round(pct)}%`;
}

function MetricBar({
  label,
  icon,
  pct,
  suffix,
  dense = false,
}: {
  label: string;
  icon: ReactNode;
  pct: number | null;
  suffix?: string;
  dense?: boolean;
}) {
  return (
    <div className={dense ? "space-y-0.5" : "space-y-1"}>
      <div className="flex items-center justify-between gap-2 text-[10.5px]">
        <span className="flex min-w-0 items-center gap-1 text-muted-foreground">
          {icon}
          <span className="truncate">{label}</span>
        </span>
        <span className="shrink-0 font-mono tabular-nums text-foreground/90">
          {formatPct(pct)}
          {suffix ? <span className="ml-1 text-muted-foreground/70">{suffix}</span> : null}
        </span>
      </div>
      <div className="h-1 overflow-hidden rounded-full bg-muted/60">
        <div
          className={cn("h-full rounded-full", barTone(pct))}
          style={{ width: pct == null ? "0%" : `${pct}%` }}
        />
      </div>
    </div>
  );
}

/**
 * Compact metrics card for operator.server_metrics — not a terminal session.
 */
export function MetricsSnapshotCard({ data }: { data: MetricsSnapshot }) {
  const { lang } = useI18n();
  const cpu = clampPct(data.cpu_percent);
  const mem = clampPct(data.mem_percent);
  const root = clampPct(data.disk_percent);
  const mounts = (data.disk_mounts || [])
    .filter((m) => m && (m.mount || m.percent != null))
    .slice(0, 6);
  const status = String(data.status || "unknown");

  const rootMount = mounts.find((m) => m.mount === "/");
  const otherMounts = mounts.filter((m) => m.mount !== "/");
  const orderedMounts = rootMount ? [rootMount, ...otherMounts] : mounts;
  const showRootBar = root != null && !rootMount;
  const stamp = data.collected_at
    ? data.collected_at.slice(0, 19).replace("T", " ")
    : null;

  return (
    <div className="w-full max-w-[360px] overflow-hidden rounded-sm border border-border/50 bg-card/40">
      <div className="flex items-center justify-between gap-2 px-2.5 py-1.5">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-1.5">
            <span className="truncate text-[12px] font-semibold tracking-tight text-foreground">
              {data.name || (data.server_id ? `server #${data.server_id}` : "metrics")}
            </span>
            <span
              className={cn(
                "shrink-0 rounded-sm px-1.5 py-px text-[10px] font-medium capitalize",
                statusTone(status),
              )}
            >
              {status}
            </span>
          </div>
          {data.host || stamp || data.note ? (
            <div className="mt-0.5 truncate font-mono text-[10px] text-muted-foreground/70">
              {[data.host, data.note || (stamp ? localize(lang, `снимок · ${stamp}`, `sample · ${stamp}`) : null)]
                .filter(Boolean)
                .join(" · ")}
            </div>
          ) : null}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 border-t border-border/30 px-2.5 py-2">
        <MetricBar dense label="CPU" icon={<Activity className="h-3 w-3" />} pct={cpu} />
        <MetricBar dense label="RAM" icon={<MemoryStick className="h-3 w-3" />} pct={mem} />
        {showRootBar ? (
          <MetricBar
            dense
            label={localize(lang, "Диск", "Disk")}
            icon={<HardDrive className="h-3 w-3" />}
            pct={root}
          />
        ) : orderedMounts[0] ? (
          <MetricBar
            dense
            label={String(orderedMounts[0].mount || localize(lang, "Диск", "Disk"))}
            icon={<HardDrive className="h-3 w-3" />}
            pct={clampPct(orderedMounts[0].percent)}
            suffix={
              orderedMounts[0].used_gb != null && orderedMounts[0].total_gb != null
                ? `${Number(orderedMounts[0].used_gb).toFixed(0)}/${Number(orderedMounts[0].total_gb).toFixed(0)}G`
                : undefined
            }
          />
        ) : (
          <MetricBar dense label={localize(lang, "Диск", "Disk")} icon={<HardDrive className="h-3 w-3" />} pct={null} />
        )}
      </div>

      {orderedMounts.length > 1 ? (
        <div className="space-y-1 border-t border-border/30 px-2.5 py-1.5">
          {orderedMounts.slice(1, 3).map((m, i) => {
            const pct = clampPct(m.percent);
            const used =
              m.used_gb != null && m.total_gb != null
                ? `${Number(m.used_gb).toFixed(0)}/${Number(m.total_gb).toFixed(0)} GB`
                : undefined;
            return (
              <MetricBar
                key={`${m.mount || i}`}
                dense
                label={String(m.mount || "—")}
                icon={<HardDrive className="h-3 w-3 opacity-60" />}
                pct={pct}
                suffix={used}
              />
            );
          })}
        </div>
      ) : null}
    </div>
  );
}
