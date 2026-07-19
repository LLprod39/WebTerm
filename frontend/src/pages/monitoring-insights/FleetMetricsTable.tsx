import { Fragment, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Clock3, RotateCcw, Server as ServerIcon } from "lucide-react";

import type { InsightServer } from "@/api/monitoring-insights";
import { Sparkline } from "@/components/dashboard/Sparkline";
import { StatusBadge } from "@/components/ui/page-shell";
import { useI18n, localize } from "@/lib/i18n";
import { cn, relativeTime } from "@/lib/utils";

import { formatBps, formatPercent, formatUptime } from "./insights-format";

const statusTone: Record<InsightServer["status"], "success" | "warning" | "danger" | "neutral"> = {
  healthy: "success",
  warning: "warning",
  critical: "danger",
  unreachable: "danger",
  unknown: "neutral",
};

function valueTone(value: number | null | undefined): string {
  if (value === null || value === undefined) return "text-muted-foreground/60";
  if (value >= 90) return "text-destructive";
  if (value >= 75) return "text-warning";
  return "text-foreground";
}

function scoreToneBg(score: number): string {
  if (score >= 80) return "bg-success";
  if (score >= 60) return "bg-warning";
  return "bg-destructive";
}

function scoreToneText(score: number): string {
  if (score >= 80) return "text-success";
  if (score >= 60) return "text-warning";
  return "text-destructive";
}

/** One clickable cell per server, colored by health score. */
function HealthStrip({ servers, onPick }: { servers: InsightServer[]; onPick: (id: number) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-1 border-b border-border bg-surface-2/30 px-3 py-2">
      {servers.map((server) => (
        <button
          key={server.id}
          type="button"
          title={`${server.name} · ${server.health_score}/100`}
          aria-label={`${server.name}: ${server.health_score}/100`}
          onClick={() => onPick(server.id)}
          className={cn(
            "h-3.5 w-3.5 transition-transform hover:scale-125 focus-visible:scale-125 focus-visible:outline-none",
            scoreToneBg(server.health_score),
            server.status === "unreachable" && "opacity-50",
          )}
        />
      ))}
    </div>
  );
}

function MetricCell({ value, spark }: { value: number | null; spark: number[] }) {
  return (
    <div className="flex items-center justify-end gap-2">
      <span className={cn("font-mono text-xs tabular-nums", valueTone(value))}>{formatPercent(value)}</span>
      {spark.length >= 2 ? (
        <span className={cn("hidden w-14 2xl:block", valueTone(value === null ? null : Math.max(value, ...spark)))}>
          <Sparkline data={spark} height={18} width={56} />
        </span>
      ) : null}
    </div>
  );
}

function DetailChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-sm border border-border bg-surface-1 px-2.5 py-1.5">
      <div className="text-2xs uppercase tracking-[0.1em] text-muted-foreground/70">{label}</div>
      <div className="mt-0.5 font-mono text-xs tabular-nums text-foreground">{value}</div>
    </div>
  );
}

function ExpandedDetails({ server }: { server: InsightServer }) {
  const { lang } = useI18n();
  const topCpu = server.top_processes?.by_cpu ?? [];
  const topMem = server.top_processes?.by_memory ?? [];

  return (
    <div className="space-y-3 border-t border-border bg-surface-1/40 px-4 py-3.5">
      <div className="grid gap-2 sm:grid-cols-3 xl:grid-cols-6">
        <DetailChip label="iowait" value={formatPercent(server.cpu_iowait_percent, 1)} />
        <DetailChip label="steal" value={formatPercent(server.cpu_steal_percent, 1)} />
        <DetailChip label={localize(lang, "сеть ↓/↑", "net ↓/↑")} value={`${formatBps(server.net_rx_bps)} / ${formatBps(server.net_tx_bps)}`} />
        <DetailChip label="tcp est / retrans" value={`${server.tcp_established ?? "—"} / ${server.tcp_retrans_per_sec ?? "—"}`} />
        <DetailChip label="fd" value={formatPercent(server.fd_percent, 1)} />
        <DetailChip
          label={localize(lang, "процессы / зомби", "procs / zombies")}
          value={`${server.process_count ?? "—"} / ${server.zombie_count ?? "—"}`}
        />
      </div>

      {server.disk_mounts.length > 0 ? (
        <div>
          <div className="mb-1.5 text-2xs uppercase tracking-[0.12em] text-muted-foreground/70">
            {localize(lang, "Диски", "Disks")}
          </div>
          <div className="grid gap-1.5 sm:grid-cols-2 xl:grid-cols-3">
            {server.disk_mounts.map((mount) => (
              <div key={mount.mount} className="flex items-center justify-between rounded-sm border border-border bg-card px-2.5 py-1.5">
                <span className="truncate font-mono text-xs text-foreground">{mount.mount}</span>
                <span className="ml-2 shrink-0 font-mono text-xs tabular-nums text-muted-foreground">
                  <span className={valueTone(mount.percent ?? null)}>{formatPercent(mount.percent ?? null)}</span>
                  {typeof mount.used_gb === "number" && typeof mount.total_gb === "number"
                    ? ` · ${mount.used_gb.toFixed(0)}/${mount.total_gb.toFixed(0)} GB`
                    : ""}
                  {typeof mount.inode_percent === "number" ? ` · inode ${mount.inode_percent.toFixed(0)}%` : ""}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {topCpu.length > 0 || topMem.length > 0 ? (
        <div className="grid gap-3 lg:grid-cols-2">
          {[
            { rows: topCpu, title: localize(lang, "Топ по CPU", "Top by CPU") },
            { rows: topMem, title: localize(lang, "Топ по памяти", "Top by memory") },
          ]
            .filter((group) => group.rows.length > 0)
            .map((group) => (
              <div key={group.title}>
                <div className="mb-1.5 text-2xs uppercase tracking-[0.12em] text-muted-foreground/70">{group.title}</div>
                <ul className="space-y-1">
                  {group.rows.slice(0, 5).map((proc) => (
                    <li key={`${group.title}-${proc.pid}`} className="flex items-center justify-between gap-2 font-mono text-xs">
                      <span className="truncate text-foreground">{proc.command}</span>
                      <span className="shrink-0 tabular-nums text-muted-foreground">
                        cpu {proc.cpu_percent.toFixed(1)}% · mem {proc.memory_percent.toFixed(1)}%
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-2xs text-muted-foreground">
        <span>uptime {formatUptime(lang, server.uptime_seconds)}</span>
        <span>
          {localize(lang, "владелец", "owner")}: {server.owner}
        </span>
        {server.sample_at ? (
          <span>
            {localize(lang, "метрики", "metrics")}: {relativeTime(server.sample_at)}
          </span>
        ) : null}
      </div>
    </div>
  );
}

const headerCell = "px-3 py-2 text-2xs font-medium uppercase tracking-[0.12em] text-muted-foreground/70 bg-card";

export function FleetMetricsTable({ servers, className }: { servers: InsightServer[]; className?: string }) {
  const { lang } = useI18n();
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  // Worst health first — the operator's eye lands on trouble immediately.
  const sorted = useMemo(
    () => [...servers].sort((a, b) => a.health_score - b.health_score || a.name.localeCompare(b.name)),
    [servers],
  );

  const toggle = (id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const pickFromStrip = (id: number) => {
    setExpanded((prev) => new Set(prev).add(id));
    requestAnimationFrame(() => {
      document.getElementById(`fleet-row-${id}`)?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  };

  return (
    <section
      className={cn("flex flex-col overflow-hidden rounded-sm border border-border bg-card shadow-elev-1", className)}
    >
      <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border bg-surface-2/40 px-4 py-2">
        <div className="flex items-center gap-2">
          <ServerIcon className="h-3.5 w-3.5 text-primary" aria-hidden />
          <h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-foreground">
            {localize(lang, "Флот", "Fleet")}
          </h2>
          <span className="font-mono text-2xs text-muted-foreground">{servers.length}</span>
        </div>
        <span className="hidden text-2xs text-muted-foreground sm:block">
          {localize(lang, "худшие сверху · клик по строке — детали", "worst first · click a row for details")}
        </span>
      </div>

      {servers.length === 0 ? (
        <div className="px-4 py-8 text-center text-xs text-muted-foreground">
          {localize(lang, "Нет активных серверов.", "No active servers.")}
        </div>
      ) : (
        <>
          <HealthStrip servers={sorted} onPick={pickFromStrip} />
          <div className="min-h-0 flex-1 overflow-auto">
            <table className="w-full min-w-[860px] border-collapse text-sm">
              <thead className="sticky top-0 z-10">
                <tr className="border-b border-border text-left shadow-[0_1px_0_hsl(var(--border))]">
                  <th className={cn(headerCell, "px-4")}>{localize(lang, "Сервер", "Server")}</th>
                  <th className={cn(headerCell, "w-14 text-right")}>{localize(lang, "Здоровье", "Health")}</th>
                  <th className={cn(headerCell, "text-right")}>CPU</th>
                  <th className={cn(headerCell, "text-right")}>RAM</th>
                  <th className={cn(headerCell, "text-right")}>{localize(lang, "Диск", "Disk")}</th>
                  <th className={cn(headerCell, "text-right")}>Swap</th>
                  <th className={cn(headerCell, "text-right")}>{localize(lang, "Ошиб/10м", "Err/10m")}</th>
                  <th className={cn(headerCell, "text-center")}>{localize(lang, "Сигналы", "Signals")}</th>
                  <th className={cn(headerCell, "px-4 text-right")}>{localize(lang, "Прогнозы", "Forecasts")}</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((server) => {
                  const isOpen = expanded.has(server.id);
                  const worstPrediction = server.predictions[0];
                  const Chevron = isOpen ? ChevronDown : ChevronRight;
                  return (
                    <Fragment key={server.id}>
                      <tr
                        id={`fleet-row-${server.id}`}
                        className="cursor-pointer border-b border-border/60 transition-colors hover:bg-surface-1/60 focus-visible:bg-surface-1/60 focus-visible:outline-none"
                        onClick={() => toggle(server.id)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" || event.key === " ") {
                            event.preventDefault();
                            toggle(server.id);
                          }
                        }}
                        tabIndex={0}
                        aria-expanded={isOpen}
                      >
                        <td className="px-4 py-2">
                          <div className="flex items-center gap-2">
                            <Chevron className="h-3.5 w-3.5 shrink-0 text-muted-foreground/60" aria-hidden />
                            <StatusBadge label={server.status} tone={statusTone[server.status]} />
                            <div className="min-w-0">
                              <div className="truncate text-xs font-medium text-foreground">{server.name}</div>
                              <div className="truncate font-mono text-2xs text-muted-foreground">{server.host}</div>
                            </div>
                          </div>
                        </td>
                        <td className="px-3 py-2 text-right">
                          <span className={cn("font-display text-sm font-bold tabular-nums", scoreToneText(server.health_score))}>
                            {server.health_score}
                          </span>
                        </td>
                        <td className="px-3 py-2"><MetricCell value={server.cpu_percent} spark={server.spark.cpu} /></td>
                        <td className="px-3 py-2"><MetricCell value={server.memory_percent} spark={server.spark.mem} /></td>
                        <td className="px-3 py-2">
                          <div className="flex items-center justify-end gap-2">
                            {server.worst_disk ? (
                              <span className="hidden max-w-28 truncate font-mono text-2xs text-muted-foreground 2xl:inline">
                                {server.worst_disk.mount}
                              </span>
                            ) : null}
                            <span className={cn("font-mono text-xs tabular-nums", valueTone(server.worst_disk?.percent ?? null))}>
                              {formatPercent(server.worst_disk?.percent ?? null)}
                            </span>
                          </div>
                        </td>
                        <td className="px-3 py-2 text-right">
                          <span className={cn("font-mono text-xs tabular-nums", valueTone(server.swap_percent))}>
                            {formatPercent(server.swap_percent)}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-right">
                          <span className={cn("font-mono text-xs tabular-nums", (server.journal_err_10m ?? 0) > 0 ? "text-warning" : "text-muted-foreground")}>
                            {server.journal_err_10m ?? "—"}
                          </span>
                        </td>
                        <td className="px-3 py-2">
                          <div className="flex items-center justify-center gap-1.5 text-muted-foreground">
                            {server.reboot_required ? (
                              <span title={localize(lang, "Требуется перезагрузка", "Reboot required")}>
                                <RotateCcw className="h-3.5 w-3.5 text-warning" aria-hidden />
                              </span>
                            ) : null}
                            {server.ntp_synchronized === false ? (
                              <span title={localize(lang, "NTP не синхронизирован", "NTP not synchronized")}>
                                <Clock3 className="h-3.5 w-3.5 text-warning" aria-hidden />
                              </span>
                            ) : null}
                            {!server.reboot_required && server.ntp_synchronized !== false ? (
                              <span className="text-2xs text-muted-foreground/50">—</span>
                            ) : null}
                          </div>
                        </td>
                        <td className="px-4 py-2 text-right">
                          {server.predictions.length > 0 && worstPrediction ? (
                            <StatusBadge
                              label={String(server.predictions.length)}
                              tone={worstPrediction.severity === "critical" ? "danger" : worstPrediction.severity === "warning" ? "warning" : "info"}
                              dot={false}
                            />
                          ) : (
                            <span className="text-2xs text-muted-foreground/50">—</span>
                          )}
                        </td>
                      </tr>
                      {isOpen ? (
                        <tr className="border-b border-border/60">
                          <td colSpan={9} className="p-0">
                            <ExpandedDetails server={server} />
                          </td>
                        </tr>
                      ) : null}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
