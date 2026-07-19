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
  if (pct >= 90) return "bg-rose-500";
  if (pct >= 75) return "bg-amber-500";
  return "bg-emerald-500";
}

function statusTone(status: string): string {
  const s = status.toLowerCase();
  if (s === "healthy") return "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400";
  if (s === "warning") return "bg-amber-500/15 text-amber-700 dark:text-amber-400";
  if (s === "critical") return "bg-rose-500/15 text-rose-600 dark:text-rose-400";
  if (s === "unreachable") return "bg-zinc-500/15 text-zinc-500";
  return "bg-muted text-muted-foreground";
}

function MetricBar({
  label,
  icon,
  pct,
  suffix,
}: {
  label: string;
  icon: ReactNode;
  pct: number | null;
  suffix?: string;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between gap-2 text-[11px]">
        <span className="flex items-center gap-1.5 text-muted-foreground">
          {icon}
          {label}
        </span>
        <span className="font-mono tabular-nums text-foreground/90">
          {pct == null ? "—" : `${pct < 10 ? pct.toFixed(1) : Math.round(pct)}%`}
          {suffix ? <span className="ml-1 text-muted-foreground/70">{suffix}</span> : null}
        </span>
      </div>
      <div className="h-1 overflow-hidden rounded-full bg-muted/60">
        <div
          className={cn("h-full rounded-full transition-all duration-500", barTone(pct))}
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

  // Prefer non-root mounts that are hot; always show root first if present
  const rootMount = mounts.find((m) => m.mount === "/");
  const otherMounts = mounts.filter((m) => m.mount !== "/");
  const orderedMounts = rootMount ? [rootMount, ...otherMounts] : mounts;

  return (
    <div className="max-w-[min(360px,100%)] overflow-hidden rounded-xl border border-border/50 bg-card/40 shadow-sm animate-in fade-in-0 duration-300">
      <div className="flex items-start justify-between gap-2 border-b border-border/40 px-3.5 py-2.5">
        <div className="min-w-0">
          <div className="truncate text-[13px] font-semibold tracking-tight text-foreground">
            {data.name || (data.server_id ? `server #${data.server_id}` : "metrics")}
          </div>
          {data.host ? (
            <div className="truncate font-mono text-[10px] text-muted-foreground/70">{data.host}</div>
          ) : null}
        </div>
        <span
          className={cn(
            "shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium capitalize",
            statusTone(status),
          )}
        >
          {status}
        </span>
      </div>

      <div className="space-y-3 px-3.5 py-3">
        <MetricBar
          label="CPU"
          icon={<Activity className="h-3 w-3" />}
          pct={cpu}
        />
        <MetricBar
          label="RAM"
          icon={<MemoryStick className="h-3 w-3" />}
          pct={mem}
        />
        {root != null && !rootMount ? (
          <MetricBar
            label={localize(lang, "Диск /", "Disk /")}
            icon={<HardDrive className="h-3 w-3" />}
            pct={root}
          />
        ) : null}

        {orderedMounts.length ? (
          <div className="space-y-2 border-t border-border/30 pt-2.5">
            <div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground/60">
              {localize(lang, "Тома", "Mounts")}
            </div>
            {orderedMounts.map((m, i) => {
              const pct = clampPct(m.percent);
              const used =
                m.used_gb != null && m.total_gb != null
                  ? `${Number(m.used_gb).toFixed(0)}/${Number(m.total_gb).toFixed(0)} GB`
                  : undefined;
              return (
                <MetricBar
                  key={`${m.mount || i}`}
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

      {(data.note || data.collected_at) && (
        <div className="border-t border-border/30 px-3.5 py-2 text-[10px] leading-4 text-muted-foreground/70">
          {data.note
            ? data.note
            : data.collected_at
              ? localize(lang, `снимок · ${data.collected_at.slice(0, 19).replace("T", " ")}`, `sample · ${data.collected_at.slice(0, 19).replace("T", " ")}`)
              : null}
        </div>
      )}
    </div>
  );
}
