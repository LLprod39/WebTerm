import { useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  ListChecks,
  Loader2,
  RotateCcw,
  ScrollText,
  Server,
  Square,
  Terminal,
  XCircle,
} from "lucide-react";
import { Link } from "react-router-dom";
import type { PlaybookRun } from "@/api/playbooks";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { RUN_STATUS_META } from "./constants";

interface RunResultsViewProps {
  lang: string;
  run: PlaybookRun;
  onBack: () => void;
  onCancel: () => void;
  onRerunFailed: () => void;
  cancelling?: boolean;
}

function formatDuration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "0:00";
  const totalSec = Math.floor(ms / 1000);
  const h = Math.floor(totalSec / 3600);
  const m = Math.floor((totalSec % 3600) / 60);
  const s = totalSec % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function RunResultsView({
  lang,
  run,
  onBack,
  onCancel,
  onRerunFailed,
  cancelling,
}: RunResultsViewProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const statusMeta = RUN_STATUS_META[run.status];
  const hosts = useMemo(() => run.host_results || [], [run.host_results]);
  const summary = run.summary || {};
  const progress = useMemo(() => run.progress || {}, [run.progress]);
  const isLive = run.status === "pending" || run.status === "running";
  const hasFailed = (summary.hosts_failed || 0) > 0 || (summary.hosts_partial || 0) > 0;

  // --- live elapsed timer ---
  const [nowTs, setNowTs] = useState(() => Date.now());
  useEffect(() => {
    if (!isLive) return;
    const id = window.setInterval(() => setNowTs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [isLive]);
  const startedTs = run.started_at ? Date.parse(run.started_at) : run.created_at ? Date.parse(run.created_at) : null;
  const endTs = run.finished_at ? Date.parse(run.finished_at) : nowTs;
  const elapsedMs = startedTs ? Math.max(0, endTs - startedTs) : 0;

  // --- progress % (ansible: TASK headers seen / estimate; shell: done steps / total) ---
  const { pct, stepLabel } = useMemo(() => {
    const total = progress.tasks_total || 0;
    const doneRaw = progress.engine === "shell" ? progress.tasks_done ?? 0 : progress.task_number ?? 0;
    if (!isLive) return { pct: 100, stepLabel: "" };
    if (!total || total <= 0) return { pct: null as number | null, stepLabel: doneRaw ? `${doneRaw}` : "" };
    const raw = Math.round((doneRaw / total) * 100);
    return {
      pct: Math.max(2, Math.min(raw, 97)),
      stepLabel: `${Math.min(doneRaw, total)}/${total}`,
    };
  }, [progress, isLive]);

  const counts = progress.counts || {};
  const tasksOk = summary.tasks_ok ?? counts.ok ?? 0;
  const tasksFailed = summary.tasks_failed ?? ((counts.failed ?? 0) + (counts.unreachable ?? 0));
  const tasksSkipped = summary.tasks_skipped ?? counts.skipped ?? 0;
  const hostsTotal = summary.hosts_total ?? progress.hosts_total ?? hosts.length;
  const hostsOk = summary.hosts_ok ?? hosts.filter((h) => h.status === "success").length;
  const hostsFailedN =
    summary.hosts_failed ?? hosts.filter((h) => h.status === "error" || h.status === "failed").length;

  // --- host accordion: auto-open failing hosts, open everything for small runs ---
  const [openHosts, setOpenHosts] = useState<Set<number>>(() => new Set());
  const autoOpened = useRef<Set<number>>(new Set());
  const initialised = useRef(false);
  useEffect(() => {
    if (hosts.length === 0) return;
    setOpenHosts((prev) => {
      const next = new Set(prev);
      if (!initialised.current) {
        initialised.current = true;
        if (hosts.length <= 3) hosts.forEach((h) => next.add(h.server_id));
      }
      for (const h of hosts) {
        const failing = h.status === "error" || h.status === "partial" || h.task_results?.some((t) => t.status === "error");
        if (failing && !autoOpened.current.has(h.server_id)) {
          autoOpened.current.add(h.server_id);
          next.add(h.server_id);
        }
      }
      return next.size === prev.size && [...next].every((id) => prev.has(id)) ? prev : next;
    });
  }, [hosts]);

  const toggleHost = (id: number) => {
    setOpenHosts((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // --- live log console ---
  const liveLog = run.live_log || "";
  const [showLog, setShowLog] = useState(true);
  const [follow, setFollow] = useState(true);
  const logRef = useRef<HTMLPreElement>(null);
  useEffect(() => {
    if (!follow || !showLog) return;
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [liveLog, follow, showLog]);
  const logLineCount = useMemo(() => (liveLog ? liveLog.split("\n").length : 0), [liveLog]);

  const metricTiles: Array<{ key: string; label: string; value: string | number; className?: string; icon: typeof Server }> = [
    { key: "hosts", label: tr("Хосты", "Hosts"), value: `${hostsOk + hostsFailedN + (summary.hosts_partial ?? 0)}/${hostsTotal}`, icon: Server },
    { key: "hosts-ok", label: tr("Хосты OK", "Hosts OK"), value: hostsOk, className: "text-emerald-400", icon: CheckCircle2 },
    { key: "hosts-fail", label: tr("Хосты fail", "Hosts fail"), value: hostsFailedN, className: hostsFailedN > 0 ? "text-destructive" : undefined, icon: XCircle },
    { key: "tasks-ok", label: tr("Задачи OK", "Tasks OK"), value: tasksOk, className: "text-primary", icon: ListChecks },
    { key: "tasks-fail", label: tr("Задачи fail", "Tasks fail"), value: tasksFailed, className: tasksFailed > 0 ? "text-destructive" : undefined, icon: Activity },
    { key: "elapsed", label: tr("Время", "Elapsed"), value: formatDuration(elapsedMs), icon: Clock },
  ];

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <button type="button" onClick={onBack} className="text-xs text-muted-foreground hover:text-foreground">
            ← {tr("Каталог", "Catalog")}
          </button>
          <h2 className="mt-1 flex flex-wrap items-center gap-2 font-display text-lg font-semibold text-foreground">
            {run.playbook_name}
            {isLive ? <Loader2 className="h-4 w-4 animate-spin text-primary" /> : null}
          </h2>
          <p className={cn("mt-0.5 text-sm", statusMeta?.className)}>
            {lang === "ru" ? statusMeta?.labelRu : statusMeta?.labelEn}
            {run.options?.dry_run ? (
              <span className="ml-2 rounded-sm border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 text-2xs text-amber-300">
                check/dry-run
              </span>
            ) : null}
            {run.summary?.engine || progress.engine ? (
              <span className="ml-2 rounded-sm border border-border bg-secondary/40 px-1.5 py-0.5 font-mono text-2xs text-muted-foreground">
                {String(run.summary?.engine || progress.engine)}
                {run.summary?.ansible_method ? `/${String(run.summary.ansible_method)}` : ""}
              </span>
            ) : null}
            <span className="ml-2 font-mono text-2xs text-muted-foreground">#{run.id}</span>
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {isLive ? (
            <Button size="sm" variant="outline" className="h-9 gap-1.5 border-destructive/30 text-destructive" disabled={cancelling || run.cancel_requested} onClick={onCancel}>
              <Square className="h-3.5 w-3.5" />
              {cancelling || run.cancel_requested ? tr("Останавливаю…", "Stopping…") : tr("Остановить", "Cancel")}
            </Button>
          ) : null}
          {!isLive && hasFailed ? (
            <Button size="sm" variant="outline" className="h-9 gap-1.5" onClick={onRerunFailed}>
              <RotateCcw className="h-3.5 w-3.5" />
              {tr("Повторить fail", "Re-run failed")}
            </Button>
          ) : null}
        </div>
      </div>

      {/* Live progress */}
      {isLive ? (
        <div className="space-y-2 rounded-sm border border-primary/25 bg-primary/5 px-4 py-3 shadow-elev-1">
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
            <span className="flex min-w-0 items-center gap-2 font-medium text-foreground">
              <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
              <span className="truncate">
                {progress.task
                  ? `${tr("Задача", "Task")}${stepLabel ? ` ${stepLabel}` : ""} · ${progress.task}`
                  : tr("Подключение и подготовка…", "Connecting & preparing…")}
              </span>
            </span>
            <span className="shrink-0 font-mono text-2xs text-muted-foreground">
              {progress.play ? `PLAY: ${progress.play}` : null}
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-secondary/70">
            {pct === null ? (
              <div className="h-full w-1/3 animate-pulse rounded-full bg-primary/70" />
            ) : (
              <div
                className="h-full rounded-full bg-primary transition-[width] duration-700 ease-out"
                style={{ width: `${pct}%` }}
              />
            )}
          </div>
          <div className="flex flex-wrap gap-3 font-mono text-2xs text-muted-foreground">
            <span className="text-emerald-400">ok={counts.ok ?? tasksOk}</span>
            {(counts.changed ?? 0) > 0 ? <span className="text-amber-300">changed={counts.changed}</span> : null}
            <span className={tasksFailed > 0 ? "text-destructive" : undefined}>failed={tasksFailed}</span>
            {(counts.unreachable ?? 0) > 0 ? (
              <span className="text-destructive">unreachable={counts.unreachable}</span>
            ) : null}
            {tasksSkipped > 0 ? <span>skipped={tasksSkipped}</span> : null}
            <span className="ml-auto flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {formatDuration(elapsedMs)}
            </span>
          </div>
        </div>
      ) : null}

      {/* Metric tiles */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {metricTiles.map((item) => (
          <div key={item.key} className="rounded-sm border border-border bg-card px-3 py-2.5 shadow-elev-1">
            <div className="flex items-center gap-1.5 text-2xs uppercase tracking-wider text-muted-foreground">
              <item.icon className="h-3 w-3" />
              {item.label}
            </div>
            <div className={cn("mt-0.5 font-display text-2xl font-semibold tabular-nums", item.className)}>
              {item.value}
            </div>
          </div>
        ))}
      </div>

      {run.error_message ? (
        <div className="rounded-sm border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {run.error_message}
        </div>
      ) : null}

      {/* Live log console */}
      {liveLog || isLive ? (
        <div className="overflow-hidden rounded-sm border border-border bg-card shadow-elev-1">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-3 py-2">
            <button
              type="button"
              onClick={() => setShowLog((v) => !v)}
              className="flex items-center gap-1.5 text-2xs font-medium uppercase tracking-wider text-muted-foreground hover:text-foreground"
            >
              <ScrollText className="h-3.5 w-3.5" />
              {tr("Живой лог", "Live log")}
              {showLog ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
              <span className="font-mono normal-case tracking-normal">({logLineCount})</span>
            </button>
            {showLog ? (
              <button
                type="button"
                onClick={() => setFollow((v) => !v)}
                className={cn(
                  "rounded-sm border px-2 py-0.5 text-2xs uppercase tracking-wider",
                  follow
                    ? "border-primary/40 bg-primary/10 text-primary"
                    : "border-border text-muted-foreground hover:text-foreground",
                )}
              >
                {tr("Автопрокрутка", "Follow")}
              </button>
            ) : null}
          </div>
          {showLog ? (
            <pre
              ref={logRef}
              className="max-h-80 overflow-auto whitespace-pre-wrap bg-surface-0 px-3 py-2.5 font-mono text-2xs leading-relaxed text-muted-foreground"
            >
              {liveLog || tr("Ожидание вывода…", "Waiting for output…")}
              {isLive ? <span className="animate-pulse text-primary">▌</span> : null}
            </pre>
          ) : null}
        </div>
      ) : null}

      <div className="space-y-2">
        {hosts.map((host) => {
          const open = openHosts.has(host.server_id);
          const taskResults = host.task_results || [];
          const allOk = taskResults.length > 0 && taskResults.every((t) => t.status === "success" || t.status === "skipped");
          const hasErr = taskResults.some((t) => t.status === "error") || host.status === "error";
          const hostRunning = host.status === "running" || host.status === "pending" || taskResults.some((t) => t.status === "running" || t.status === "pending");
          const doneCount = taskResults.filter((t) => t.status === "success" || t.status === "error" || t.status === "skipped").length;
          return (
            <div key={host.server_id} className="overflow-hidden rounded-sm border border-border bg-card shadow-elev-1">
              <button
                type="button"
                onClick={() => toggleHost(host.server_id)}
                className={cn(
                  "flex w-full items-center gap-3 border-b border-border px-4 py-3 text-left",
                  allOk && !hasErr ? "bg-primary/5" : hasErr ? "bg-destructive/5" : "bg-secondary/10",
                )}
              >
                {open ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium text-foreground">{host.server_name}</div>
                  <div className="font-mono text-2xs text-muted-foreground">{host.host}</div>
                </div>
                {taskResults.length > 0 ? (
                  <span className="hidden font-mono text-2xs text-muted-foreground sm:inline">
                    {doneCount}/{taskResults.length}
                  </span>
                ) : null}
                <Link
                  to={`/servers/${host.server_id}/terminal`}
                  onClick={(e) => e.stopPropagation()}
                  className="inline-flex h-8 items-center gap-1 rounded-sm border border-border px-2 text-2xs text-muted-foreground hover:text-foreground"
                >
                  <Terminal className="h-3 w-3" />
                  SSH
                </Link>
                {host.status === "success" || (allOk && !hasErr) ? <CheckCircle2 className="h-4 w-4 text-primary" /> : null}
                {hasErr ? <XCircle className="h-4 w-4 text-destructive" /> : null}
                {!hasErr && hostRunning && isLive ? <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /> : null}
              </button>
              {open ? (
                <div className="divide-y divide-border">
                  {taskResults.map((task, idx) => (
                    <div key={`${task.task_id}-${idx}`} className="px-4 py-3">
                      <div className="mb-1 flex flex-wrap items-center gap-2">
                        <span className="rounded-sm bg-secondary px-1.5 py-0.5 font-mono text-2xs text-muted-foreground">
                          #{idx + 1}
                        </span>
                        {task.description ? (
                          <span className="text-xs text-muted-foreground">{task.description}</span>
                        ) : null}
                        <code className="min-w-0 flex-1 truncate font-mono text-xs text-foreground">{task.command}</code>
                        <span className="ml-auto shrink-0">
                          {task.status === "success" ? <CheckCircle2 className="h-3.5 w-3.5 text-primary" /> : null}
                          {task.status === "error" ? <XCircle className="h-3.5 w-3.5 text-destructive" /> : null}
                          {task.status === "running" ? <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" /> : null}
                          {task.status === "pending" ? (
                            <span className="inline-block h-3.5 w-3.5 rounded-full bg-muted-foreground/20" />
                          ) : null}
                          {task.status === "skipped" ? (
                            <span className="text-2xs text-muted-foreground">{tr("skip", "skip")}</span>
                          ) : null}
                        </span>
                      </div>
                      {task.output ? (
                        <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded-sm border border-border bg-surface-0 p-2.5 font-mono text-2xs text-muted-foreground">
                          {task.output}
                        </pre>
                      ) : null}
                    </div>
                  ))}
                  {taskResults.length === 0 ? (
                    <p className="px-4 py-3 text-xs text-muted-foreground">
                      {isLive ? tr("Ожидание задач…", "Waiting for tasks…") : tr("Нет результатов", "No task results")}
                    </p>
                  ) : null}
                </div>
              ) : null}
            </div>
          );
        })}
        {hosts.length === 0 && isLive ? (
          <div className="flex items-center justify-center gap-2 rounded-sm border border-border bg-card py-12 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
            {tr("Подготовка run…", "Preparing run…")}
          </div>
        ) : null}
      </div>

      {run.inventory_preview ? (
        <details className="rounded-sm border border-border bg-card p-3 shadow-elev-1">
          <summary className="cursor-pointer text-2xs font-medium uppercase tracking-wider text-muted-foreground">
            Inventory
          </summary>
          <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap font-mono text-2xs text-muted-foreground">
            {run.inventory_preview}
          </pre>
        </details>
      ) : null}
    </section>
  );
}
