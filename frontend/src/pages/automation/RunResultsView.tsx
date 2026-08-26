import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Copy,
  Download,
  ListChecks,
  Loader2,
  PlayCircle,
  RotateCcw,
  Search,
  Server,
  Square,
  Terminal,
  XCircle,
} from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";

import {
  downloadPlaybookRunReport,
  getPlaybookRunReport,
  getPlaybookRunReportHost,
  getPlaybookRunReportLog,
  getPlaybookRunRetryContext,
  type PlaybookHostResult,
  type PlaybookRun,
  type PlaybookRunReportHost,
} from "@/api/playbooks";
import { StatusBadge } from "@/components/system/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { notify } from "@/lib/notify";
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

type ReportTab = "summary" | "execution" | "log";

export function RunResultsView({ lang, run, onBack, onCancel, onRerunFailed, cancelling }: RunResultsViewProps) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get("tab");
  const runStartsLive = run.status === "pending" || run.status === "running";
  const tab: ReportTab = requestedTab === "summary" || requestedTab === "execution" || requestedTab === "log"
    ? requestedTab
    : runStartsLive ? "execution" : "summary";
  const reportQuery = useQuery({
    queryKey: ["playbook-run-report", run.id],
    queryFn: () => getPlaybookRunReport(run.id),
    retry: 3,
    retryDelay: (attempt) => [3_000, 6_000, 12_000][Math.min(attempt, 2)],
    refetchInterval: (query) => query.state.data?.report.progress.is_terminal ? false : 1_500,
  });
  const report = reportQuery.data?.report;
  const status = report?.run.status || run.status;
  const isLive = status === "pending" || status === "running";
  const summary = report?.summary || run.summary || {};
  const progress = report?.progress;
  const statusMeta = RUN_STATUS_META[status];
  const playbookName = report?.run.playbook_name || run.playbook_name;
  const playbookId = report?.run.playbook_id ?? run.playbook_id;
  const canCancel = report?.actions.can_cancel ?? isLive;
  const canExport = report?.actions.can_export ?? !isLive;
  const fallbackHosts = useMemo(() => run.host_results || [], [run.host_results]);
  const hosts = useMemo(() => report?.hosts || fallbackHosts.map(toReportHost), [fallbackHosts, report?.hosts]);
  const [now, setNow] = useState(() => Date.now());
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    if (requestedTab === "summary" || requestedTab === "execution" || requestedTab === "log") return;
    const params = new URLSearchParams(searchParams);
    params.set("tab", tab);
    setSearchParams(params, { replace: true });
  }, [requestedTab, searchParams, setSearchParams, tab]);

  useEffect(() => {
    if (!isLive) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, [isLive]);

  const startedAt = report?.run.started_at || run.started_at || run.created_at;
  const finishedAt = report?.run.finished_at || run.finished_at;
  const duration = typeof report?.run.duration_ms === "number"
    ? formatDuration(report.run.duration_ms)
    : startedAt ? formatDuration(Math.max(0, (finishedAt ? Date.parse(finishedAt) : now) - Date.parse(startedAt))) : "—";
  const hostsTotal = numberValue(summary.hosts_total, progress?.hosts_total, hosts.length);
  const hostsOk = numberValue(summary.hosts_ok, hosts.filter((host) => isSuccess(host.status)).length);
  const hostsFailed = numberValue(summary.hosts_failed, hosts.filter((host) => isFailure(host.status)).length);
  const tasksOk = numberValue(summary.tasks_ok, progress?.counts.ok, hosts.reduce((total, host) => total + host.task_counts.ok, 0));
  const tasksChanged = numberValue(summary.tasks_changed, progress?.counts.changed, hosts.reduce((total, host) => total + host.task_counts.changed, 0));
  const tasksFailed = numberValue(summary.tasks_failed, progress?.counts.failed, hosts.reduce((total, host) => total + host.task_counts.failed, 0));
  const tasksUnreachable = numberValue(summary.tasks_unreachable, progress?.counts.unreachable, hosts.reduce((total, host) => total + host.task_counts.unreachable, 0));
  const tasksSkipped = numberValue(summary.tasks_skipped, progress?.counts.skipped, hosts.reduce((total, host) => total + host.task_counts.skipped, 0));
  const tasksCancelled = numberValue(summary.tasks_cancelled, progress?.counts.cancelled, hosts.reduce((total, host) => total + host.task_counts.cancelled, 0));
  const legacyTotal = run.progress?.tasks_total || null;
  const legacyDone = run.progress?.engine === "shell" ? run.progress.tasks_done : run.progress?.task_number;
  const percent = progress
    ? progress.total_kind === "exact" ? progress.percent : null
    : run.progress?.engine === "shell" && legacyTotal && legacyDone != null
      ? Math.min(100, Math.round((legacyDone / legacyTotal) * 100))
      : null;
  const progressLabel = percent != null
    ? `${percent}%`
    : progress?.total_kind === "estimated" && progress.completed != null && progress.total
      ? tr(`≈ ${progress.completed} из ${progress.total}`, `≈ ${progress.completed} of ${progress.total}`)
      : tr("Выполняется", "In progress");
  const progressAriaText = percent != null
    ? tr(`Выполнено ${percent}%`, `${percent}% complete`)
    : progress?.total_kind === "estimated" && progress.completed != null && progress.total
      ? tr(`Приблизительно выполнено ${progress.completed} из ${progress.total}`, `Approximately ${progress.completed} of ${progress.total} complete`)
      : tr("Выполнение продолжается, общий объём пока неизвестен", "Run in progress; total work is not known yet");
  const failure = report?.failure || (run.error_message ? {
    code: "execution_failed",
    message: run.error_message,
    suggested_action: tr("Откройте проблемный хост и проверьте задачу перед повтором.", "Open the failed host and review the task before retrying."),
    retryable: hostsFailed > 0,
  } : null);
  const retryQuery = useQuery({
    queryKey: ["playbook-run-retry-context", run.id],
    queryFn: () => getPlaybookRunRetryContext(run.id),
    enabled: tab === "summary" && Boolean(failure),
    retry: false,
  });
  const retryContext = retryQuery.data?.retry_context;

  const changeTab = (next: string) => {
    const params = new URLSearchParams(searchParams);
    params.set("tab", next);
    setSearchParams(params, { replace: true });
  };
  const exportReport = async () => {
    setExporting(true);
    try {
      await downloadPlaybookRunReport(run.id);
    } catch (caught) {
      notify.error({
        title: tr("Не удалось скачать отчёт", "Could not download report"),
        description: caught instanceof Error ? caught.message : String(caught),
      });
    } finally {
      setExporting(false);
    }
  };

  return (
    <section className="mx-auto w-full max-w-[1220px] space-y-4">
      <header className="flex flex-col gap-3 border-b border-border/70 pb-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <button type="button" onClick={onBack} className="text-xs text-muted-foreground hover:text-foreground">← {tr("Каталог", "Catalog")}</button>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <h1 className="font-display text-xl font-semibold text-foreground">{playbookName}</h1>
            {isLive ? <Loader2 className="h-4 w-4 animate-spin text-primary" /> : null}
            <StatusBadge label={lang === "ru" ? statusMeta?.labelRu || status : statusMeta?.labelEn || status} tone={statusTone(status)} />
            {(report?.run.options.dry_run ?? run.options?.dry_run) ? <StatusBadge label="check-mode" tone="warning" /> : null}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {tr("Запуск", "Run")} #{run.id}
            {report?.run.revision_id ? ` · ${tr("ревизия", "revision")} #${report.run.revision_id}` : ""}
            {report?.run.binding_profile_id
              ? ` · ${tr("профиль", "profile")} ${report.run.binding_profile_name || `#${report.run.binding_profile_id}`}`
              : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {playbookId ? <Button asChild size="sm" variant="outline"><Link to={`/automation/playbooks/${playbookId}`}>{tr("Открыть проект", "Open project")}</Link></Button> : null}
          {canExport ? <Button size="sm" variant="outline" className="gap-1.5" disabled={exporting} onClick={() => void exportReport()}>{exporting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />}{tr("Скачать отчёт", "Download report")}</Button> : null}
          {canCancel ? <Button size="sm" variant="outline" className="gap-1.5 border-destructive/30 text-destructive" disabled={cancelling || run.cancel_requested} onClick={onCancel}><Square className="h-3.5 w-3.5" />{cancelling || run.cancel_requested ? tr("Останавливаем…", "Stopping…") : tr("Остановить", "Cancel")}</Button> : null}
        </div>
      </header>

      {isLive ? (
        <div className="rounded-lg border border-primary/25 bg-primary/5 px-4 py-3 shadow-elev-1" role="status" aria-live="polite">
          <div className="flex items-center justify-between gap-3 text-xs">
            <span className="min-w-0 truncate font-medium text-foreground">{progress?.task || run.progress?.task || tr("Подготовка запуска…", "Preparing run…")}</span>
            <span className="shrink-0 font-mono text-muted-foreground">{progressLabel}</span>
          </div>
          <div
            className="mt-2 h-2 overflow-hidden rounded-full bg-secondary/70"
            role="progressbar"
            aria-label={tr("Прогресс выполнения", "Run progress")}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={percent == null ? undefined : percent}
            aria-valuetext={progressAriaText}
          >
            {percent == null ? <div className="h-full w-1/3 animate-pulse rounded-full bg-primary/70" /> : <div className="h-full rounded-full bg-primary transition-[width] duration-500" style={{ width: `${Math.max(2, percent)}%` }} />}
          </div>
          <p className="mt-2 text-2xs text-muted-foreground">{progress?.total_kind === "estimated" ? tr("Прогресс приблизительный", "Progress is estimated") : progress?.phase || run.progress?.play || ""}</p>
        </div>
      ) : null}

      {reportQuery.isError ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-sm border border-warning/30 bg-warning/5 px-3 py-2 text-xs text-muted-foreground">
          <span>{tr("Новый формат отчёта временно недоступен — показаны сохранённые данные запуска.", "The new report API is temporarily unavailable; saved run data is shown.")}</span>
          <Button size="sm" variant="ghost" className="h-7" onClick={() => void reportQuery.refetch()}>{tr("Повторить", "Retry")}</Button>
        </div>
      ) : null}

      <Tabs value={tab} onValueChange={changeTab}>
        <TabsList className="w-full justify-start" aria-label={tr("Разделы отчёта", "Report sections")}>
          <TabsTrigger value="summary">{tr("Итог", "Result")}</TabsTrigger>
          <TabsTrigger value="execution">{tr("Выполнение", "Execution")} · {hosts.length}</TabsTrigger>
          <TabsTrigger value="log">{tr("Журнал", "Log")}</TabsTrigger>
        </TabsList>

        <TabsContent value="summary" className="space-y-4 pt-2">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8">
            <Metric icon={Server} label={tr("Хосты", "Hosts")} value={`${hostsOk}/${hostsTotal}`} />
            <Metric icon={CheckCircle2} label="OK" value={tasksOk} tone="success" />
            <Metric icon={ListChecks} label={tr("Изменено", "Changed")} value={tasksChanged} tone="warning" />
            <Metric icon={XCircle} label={tr("Ошибки", "Failed")} value={tasksFailed} tone={tasksFailed > 0 ? "danger" : "neutral"} />
            <Metric icon={AlertTriangle} label={tr("Недоступно", "Unreachable")} value={tasksUnreachable} tone={tasksUnreachable > 0 ? "danger" : "neutral"} />
            <Metric icon={PlayCircle} label={tr("Пропущено", "Skipped")} value={tasksSkipped} />
            <Metric icon={Square} label={tr("Отменено", "Cancelled")} value={tasksCancelled} tone={tasksCancelled > 0 ? "warning" : "neutral"} />
            <Metric icon={Clock} label={tr("Время", "Elapsed")} value={duration} />
          </div>

          {failure ? (
            <section className="rounded-lg border border-destructive/30 bg-destructive/5 p-4">
              <div className="flex items-start gap-3">
                <XCircle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
                <div className="min-w-0 flex-1">
                  <h2 className="text-sm font-semibold text-foreground">{tr("Что произошло", "What happened")}</h2>
                  <p className="mt-1 whitespace-pre-wrap text-sm text-destructive">{failure.message}</p>
                  <p className="mt-2 text-xs leading-5 text-muted-foreground">{failure.suggested_action}</p>
                  {retryQuery.isPending ? <p className="mt-3 flex items-center gap-2 text-xs text-muted-foreground"><Loader2 className="h-3.5 w-3.5 animate-spin" />{tr("Проверяем безопасный повтор…", "Checking safe retry…")}</p> : null}
                  {retryContext?.blockers.length ? <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-muted-foreground">{retryContext.blockers.map((blocker) => <li key={blocker.code}>{blocker.message}</li>)}</ul> : null}
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button size="sm" variant="outline" className="gap-1.5" disabled={retryContext ? !retryContext.can_retry : !failure.retryable} onClick={onRerunFailed}><RotateCcw className="h-3.5 w-3.5" />{tr("Повторить только ошибки", "Retry failed hosts")}</Button>
                    <Button size="sm" variant="ghost" onClick={() => changeTab("execution")}>{tr("Открыть проблемные хосты", "Open failed hosts")}</Button>
                  </div>
                </div>
              </div>
            </section>
          ) : (
            <div className="flex items-center gap-3 rounded-lg border border-success/25 bg-success/5 p-4 text-sm text-foreground"><CheckCircle2 className="h-5 w-5 text-success" />{isLive ? tr("Запуск выполняется. Сводка обновляется автоматически.", "The run is in progress. This summary updates automatically.") : tr("Запуск завершён без зафиксированных ошибок.", "The run finished without recorded failures.")}</div>
          )}

          <details className="rounded-lg border border-border bg-card p-3">
            <summary className="cursor-pointer text-xs font-medium text-muted-foreground">{tr("Технические детали", "Technical details")}</summary>
            <dl className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
              <Detail label={tr("Движок", "Engine")} value={String(progress?.engine || summary.engine || run.progress?.engine || "—")} />
              <Detail label={tr("Ревизия", "Revision")} value={report?.run.revision_id ? `#${report.run.revision_id}` : "—"} />
              <Detail label={tr("Профиль запуска", "Run profile")} value={report?.run.binding_profile_id ? report.run.binding_profile_name || `#${report.run.binding_profile_id}` : tr("Не задан", "Not set")} />
              <Detail label={tr("Статус очереди", "Dispatch status")} value={report?.dispatch?.status || "—"} />
              <Detail label={tr("Начало", "Started")} value={startedAt ? new Date(startedAt).toLocaleString() : "—"} />
              <Detail label={tr("Окончание", "Finished")} value={finishedAt ? new Date(finishedAt).toLocaleString() : "—"} />
            </dl>
          </details>
        </TabsContent>

        <TabsContent value="execution" className="space-y-2 pt-2">
          <ExecutionStageRail lang={lang} phase={progress?.phase || run.progress?.play || ""} status={status} />
          {hosts.length ? hosts.map((host, index) => (
            <HostExecution key={host.server_id ?? `${host.server_name}-${index}`} lang={lang} runId={run.id} host={host} fallback={fallbackHosts.find((item) => item.server_id === host.server_id)} reportAvailable={Boolean(report)} defaultOpen={isFailure(host.status)} />
          )) : <div className="rounded-lg border border-border bg-card py-12 text-center text-sm text-muted-foreground">{isLive ? tr("Ожидаем данные по хостам…", "Waiting for host data…") : tr("Данных по хостам нет", "No host data")}</div>}
        </TabsContent>

        <TabsContent value="log" className="pt-2">
          <RunLog lang={lang} runId={run.id} enabled={tab === "log"} live={isLive} fallback={run.live_log || ""} />
        </TabsContent>
      </Tabs>
    </section>
  );
}

function Metric({ icon: Icon, label, value, tone = "neutral" }: { icon: typeof Server; label: string; value: string | number; tone?: "neutral" | "success" | "warning" | "danger" }) {
  return <div className="rounded-sm border border-border bg-card px-3 py-2.5 shadow-elev-1"><div className={cn("flex items-center gap-1.5 text-2xs uppercase tracking-wider", tone === "success" ? "text-success" : tone === "warning" ? "text-warning" : tone === "danger" ? "text-destructive" : "text-muted-foreground")}><Icon className="h-3 w-3" />{label}</div><div className={cn("mt-1 font-display text-2xl font-semibold tabular-nums", tone === "success" ? "text-success" : tone === "warning" ? "text-warning" : tone === "danger" ? "text-destructive" : "text-foreground")}>{value}</div></div>;
}

function ExecutionStageRail({ lang, phase, status }: { lang: string; phase: string; status: string }) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const normalized = phase.toLowerCase();
  const terminal = !["pending", "running"].includes(status);
  const activeIndex = terminal ? 3 : /queue|pending/.test(normalized) ? 0 : /prepar|preflight|bootstrap|dispatch/.test(normalized) ? 1 : 2;
  const stages = [tr("В очереди", "Queued"), tr("Подготовка", "Preparing"), tr("Выполнение", "Executing"), tr("Завершено", "Finished")];
  return (
    <ol className="grid grid-cols-4 overflow-hidden rounded-lg border border-border bg-card" aria-label={tr("Этапы запуска", "Run stages")}>
      {stages.map((label, index) => <li key={label} className={cn("border-r border-border px-2 py-2 text-center text-2xs last:border-r-0", index < activeIndex ? "bg-success/5 text-success" : index === activeIndex ? "bg-primary/8 font-medium text-primary" : "text-muted-foreground")} aria-current={index === activeIndex ? "step" : undefined}><span className="mr-1 font-mono">{index + 1}</span>{label}</li>)}
    </ol>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-muted-foreground">{label}</dt><dd className="mt-0.5 font-mono text-foreground">{value}</dd></div>;
}

function HostExecution({ lang, runId, host, fallback, reportAvailable, defaultOpen }: { lang: string; runId: number; host: PlaybookRunReportHost; fallback?: PlaybookHostResult; reportAvailable: boolean; defaultOpen: boolean }) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const [open, setOpen] = useState(defaultOpen);
  const detailQuery = useQuery({
    queryKey: ["playbook-run-report-host", runId, host.server_id],
    queryFn: () => getPlaybookRunReportHost(runId, host.server_id as number),
    enabled: open && reportAvailable && host.server_id != null,
    retry: 1,
  });
  const tasks = detailQuery.data?.host.tasks || fallback?.task_results?.map((task) => ({ ...task, name: task.description || task.command })) || [];
  const failed = isFailure(host.status) || host.task_counts.failed > 0;
  return (
    <article className="overflow-hidden rounded-lg border border-border bg-card shadow-elev-1">
      <div className={cn("flex items-center", failed ? "bg-destructive/5" : "bg-surface-0/35")}>
        <button type="button" className="flex min-w-0 flex-1 items-center gap-3 px-4 py-3 text-left" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
          {open ? <ChevronDown className="h-4 w-4 text-muted-foreground" /> : <ChevronRight className="h-4 w-4 text-muted-foreground" />}
          <div className="min-w-0 flex-1"><p className="truncate text-sm font-medium text-foreground">{host.server_name}</p><p className="mt-0.5 truncate font-mono text-2xs text-muted-foreground">{host.host}</p></div>
          <span className="hidden font-mono text-xs text-muted-foreground sm:inline">{host.task_counts.ok}/{host.task_counts.total}</span>
          {failed ? <XCircle className="h-4 w-4 text-destructive" /> : isSuccess(host.status) ? <CheckCircle2 className="h-4 w-4 text-success" /> : <Loader2 className="h-4 w-4 animate-spin text-primary" />}
        </button>
        {host.server_id ? <Link to={`/servers/${host.server_id}/terminal`} className="mr-4 inline-flex h-8 shrink-0 items-center gap-1 rounded-sm border border-border px-2 text-2xs text-muted-foreground hover:text-foreground"><Terminal className="h-3 w-3" />SSH</Link> : null}
      </div>
      {open ? <div className="divide-y divide-border border-t border-border">
        {detailQuery.isPending && reportAvailable ? <p className="flex items-center gap-2 px-4 py-4 text-xs text-muted-foreground"><Loader2 className="h-3.5 w-3.5 animate-spin" />{tr("Загрузка задач…", "Loading tasks…")}</p> : null}
        {detailQuery.isError && !tasks.length ? <div className="flex items-center justify-between gap-2 px-4 py-3 text-xs text-destructive"><span>{tr("Не удалось загрузить детали хоста", "Could not load host details")}</span><Button size="sm" variant="ghost" className="h-7" onClick={() => void detailQuery.refetch()}>{tr("Повторить", "Retry")}</Button></div> : null}
        {tasks.map((task, index) => <div key={`${task.task_id}-${index}`} className="px-4 py-3"><div className="flex items-center gap-2"><span className="rounded-sm bg-secondary px-1.5 py-0.5 font-mono text-2xs text-muted-foreground">#{index + 1}</span><span className="min-w-0 flex-1 truncate text-xs font-medium text-foreground">{task.name}</span><StatusBadge label={task.status} tone={isFailure(task.status) ? "danger" : isSuccess(task.status) ? "success" : "neutral"} /></div>{task.output ? <pre className="mt-2 max-h-52 overflow-auto whitespace-pre-wrap rounded-sm border border-border bg-terminal-bg p-3 font-mono text-2xs text-muted-foreground">{task.output}</pre> : null}</div>)}
        {!detailQuery.isPending && !tasks.length ? <p className="px-4 py-4 text-xs text-muted-foreground">{tr("Подробные результаты ещё не готовы.", "Detailed results are not ready yet.")}</p> : null}
      </div> : null}
    </article>
  );
}

function RunLog({ lang, runId, enabled, live, fallback }: { lang: string; runId: number; enabled: boolean; live: boolean; fallback: string }) {
  const tr = (ru: string, en: string) => (lang === "ru" ? ru : en);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [retryToken, setRetryToken] = useState(0);
  const [search, setSearch] = useState("");
  const cursorRef = useRef(0);
  const retryAttemptRef = useRef(0);
  const liveRef = useRef(live);
  const preRef = useRef<HTMLPreElement>(null);
  const [follow, setFollow] = useState(true);

  useEffect(() => { liveRef.current = live; }, [live]);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    let timer: number | undefined;
    cursorRef.current = 0;
    retryAttemptRef.current = 0;
    setText("");
    setError("");
    const tick = async () => {
      try {
        const response = await getPlaybookRunReportLog(runId, cursorRef.current);
        if (cancelled) return;
        const chunk = response.text || "";
        setText((current) => response.reset_required ? chunk : `${current}${chunk}`);
        cursorRef.current = response.next_cursor;
        retryAttemptRef.current = 0;
        setError("");
        if (response.has_more || liveRef.current) timer = window.setTimeout(() => void tick(), response.has_more ? 80 : 1_500);
      } catch (caught) {
        if (cancelled) return;
        setError(caught instanceof Error ? caught.message : String(caught));
        const delay = [3_000, 6_000, 12_000][Math.min(retryAttemptRef.current, 2)];
        retryAttemptRef.current += 1;
        timer = window.setTimeout(() => void tick(), delay);
      }
    };
    void tick();
    return () => { cancelled = true; if (timer !== undefined) window.clearTimeout(timer); };
  }, [enabled, retryToken, runId]);

  const visibleText = text || fallback;
  const searchedText = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase();
    if (!needle) return visibleText;
    return visibleText.split("\n").filter((line) => line.toLocaleLowerCase().includes(needle)).join("\n");
  }, [search, visibleText]);
  useEffect(() => { if (follow && preRef.current) preRef.current.scrollTop = preRef.current.scrollHeight; }, [follow, searchedText]);
  const copyLog = async () => {
    try {
      await navigator.clipboard.writeText(visibleText);
      notify.success({ title: tr("Журнал скопирован", "Log copied") });
    } catch (caught) {
      notify.error({ title: tr("Не удалось скопировать журнал", "Could not copy log"), description: caught instanceof Error ? caught.message : String(caught) });
    }
  };
  const downloadLog = () => {
    const blob = new Blob([visibleText], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `ansible-run-${runId}-redacted.log`;
    link.hidden = true;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  return (
    <section className="overflow-hidden rounded-lg border border-border bg-card shadow-elev-1">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-3 py-2">
        <div><h2 className="text-sm font-medium text-foreground">{tr("Журнал выполнения", "Execution log")}</h2><p className="mt-0.5 text-2xs text-muted-foreground">{tr("Секреты скрываются сервером перед отправкой.", "Secrets are redacted by the server before delivery.")}</p></div>
        <div className="flex flex-wrap items-center gap-1.5">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input value={search} onChange={(event) => setSearch(event.target.value)} aria-label={tr("Поиск в журнале", "Search log")} placeholder={tr("Поиск", "Search")} className="h-8 w-40 pl-8 text-xs" />
          </div>
          <Button size="icon" variant="ghost" className="h-8 w-8" disabled={!visibleText} aria-label={tr("Копировать доступный журнал", "Copy available log")} onClick={() => void copyLog()}><Copy className="h-3.5 w-3.5" /></Button>
          <Button size="icon" variant="ghost" className="h-8 w-8" disabled={!visibleText} aria-label={tr("Скачать доступный журнал", "Download available log")} onClick={downloadLog}><Download className="h-3.5 w-3.5" /></Button>
          <Button size="sm" variant={follow ? "secondary" : "ghost"} className="h-8" onClick={() => setFollow((value) => !value)}>{tr("Автопрокрутка", "Follow")}</Button>
        </div>
      </div>
      {error ? <div className="flex items-center justify-between gap-2 border-b border-warning/30 bg-warning/5 px-3 py-2 text-xs text-muted-foreground"><span>{tr("Потоковый журнал недоступен; показан сохранённый вывод.", "The streamed log is unavailable; saved output is shown.")}</span><Button size="sm" variant="ghost" className="h-7" onClick={() => setRetryToken((value) => value + 1)}>{tr("Повторить", "Retry")}</Button></div> : null}
      <pre ref={preRef} className="min-h-[28rem] max-h-[65vh] overflow-auto whitespace-pre-wrap bg-terminal-bg p-4 font-mono text-xs leading-5 text-muted-foreground">{searchedText || (search ? tr("Совпадений нет", "No matches") : tr("Ожидание вывода…", "Waiting for output…"))}{live ? <span className="animate-pulse text-primary">▌</span> : null}</pre>
    </section>
  );
}

function toReportHost(host: PlaybookHostResult): PlaybookRunReportHost {
  const tasks = host.task_results || [];
  return {
    server_id: host.server_id,
    server_name: host.server_name,
    host: host.host || "",
    status: host.status,
    task_counts: {
      total: tasks.length,
      ok: tasks.filter((task) => ["success", "completed", "ok"].includes(task.status.toLowerCase())).length,
      changed: tasks.filter((task) => task.status.toLowerCase() === "changed").length,
      failed: tasks.filter((task) => ["error", "failed", "partial"].includes(task.status.toLowerCase())).length,
      unreachable: tasks.filter((task) => task.status.toLowerCase() === "unreachable").length,
      skipped: tasks.filter((task) => task.status === "skipped").length,
      cancelled: tasks.filter((task) => task.status === "cancelled").length,
      running: tasks.filter((task) => task.status === "running").length,
      pending: tasks.filter((task) => task.status === "pending").length,
    },
    first_failure: null,
    detail_url: "",
  };
}

function isSuccess(status: string) { return ["success", "completed", "ok", "changed"].includes(status.toLowerCase()); }
function isFailure(status: string) { return ["error", "failed", "partial", "unreachable"].includes(status.toLowerCase()); }
function numberValue(...values: unknown[]): number { for (const value of values) if (typeof value === "number" && Number.isFinite(value)) return value; return 0; }
function statusTone(status: string): "success" | "danger" | "warning" | "neutral" { return isSuccess(status) ? "success" : isFailure(status) ? "danger" : status === "cancelled" ? "warning" : "neutral"; }
function formatDuration(ms: number): string { const seconds = Math.floor(ms / 1000); const hours = Math.floor(seconds / 3600); const minutes = Math.floor((seconds % 3600) / 60); const rest = seconds % 60; return hours ? `${hours}:${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}` : `${minutes}:${String(rest).padStart(2, "0")}`; }
