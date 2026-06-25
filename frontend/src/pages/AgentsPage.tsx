import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  fetchAgents,
  cleanupStaleAgentRuns,
  deleteAgent,
  runAgent,
  stopAgent,
  type AgentItem,
  type AgentExecutionReadiness,
  type AgentRuntimeOverview,
  type AgentRuntimeRunItem,
  type AgentRunResult,
  type BackgroundWorkerStateRecord,
} from "@/lib/api";
import { agentRunStatusPresentation } from "@/design/status";
import { localize, useI18n } from "@/lib/i18n";
import {
  Bot, Plus, Play, Trash2, RefreshCw, Clock, Eye,
  FileText, Server, X, Square,
  Settings2, CheckCircle2,
  AlertTriangle, Activity, Copy, Cpu, MessageSquare,
} from "lucide-react";
import { AgentReportModal } from "@/components/studio/AgentReportModal";
import { Button } from "@/components/ui/button";
import { DeleteDialog } from "@/components/system/ConfirmDialog";
import { EmptyState, MetricCard, MetricGrid, PageHero, PageShell, QueryStateBlock, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { CreateAgentDialog } from "./agents-page/CreateAgentDialog";
import {
  AGENT_ICONS,
  agentModeLabel,
  formatDuration,
  formatScheduleConfigLabel,
  isAgentScheduled,
  relativeTime,
  sudoAgentOption,
} from "./agents-page/agentPageUtils";

function readinessTone(readiness?: AgentExecutionReadiness): "neutral" | "success" | "warning" | "danger" | "info" {
  if (!readiness?.required) return "neutral";
  if (readiness.ready) return "success";
  if (readiness.severity === "critical" || readiness.severity === "fatal") return "danger";
  if (readiness.severity === "warning" || readiness.severity === "high") return "warning";
  return "info";
}

function workerStateTone(worker?: BackgroundWorkerStateRecord): "neutral" | "success" | "warning" | "danger" | "info" {
  if (!worker || worker.status === "missing") return "warning";
  if (worker.status === "error") return "danger";
  if (worker.is_stale) return "warning";
  if (worker.status === "running") return "success";
  if (worker.status === "stopped") return "warning";
  return "neutral";
}

function runBlockedReason(agent: AgentItem, lang: "ru" | "en") {
  const readiness = agent.execution_readiness;
  if (readiness?.required && !readiness.ready) {
    return readiness.next_action || readiness.description || localize(lang, "Execution worker не готов.", "Execution worker is not ready.");
  }
  if (agent.is_enabled === false) {
    return localize(lang, "Агент выключен.", "Agent is disabled.");
  }
  if (agent.server_count <= 0) {
    return localize(lang, "Выберите хотя бы один сервер.", "Select at least one server.");
  }
  return "";
}

function formatWorkerTime(value: string | null | undefined, lang: "ru" | "en") {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(lang === "ru" ? "ru-RU" : "en-US");
}

function workerSummaryEntries(summary: Record<string, unknown> | undefined) {
  return Object.entries(summary || {})
    .filter(([, value]) => value !== null && value !== undefined && ["string", "number", "boolean"].includes(typeof value))
    .slice(0, 6);
}

function formatRuntimeAge(seconds: number | null | undefined) {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds <= 0) return "0s";
  return formatDuration(seconds * 1000);
}

function severityTone(severity?: string): "neutral" | "success" | "warning" | "danger" | "info" {
  if (severity === "success") return "success";
  if (severity === "warning" || severity === "high") return "warning";
  if (severity === "critical" || severity === "fatal") return "danger";
  if (severity === "info") return "info";
  return "neutral";
}

function runStatusLabel(status: string | null | undefined, lang: "ru" | "en") {
  switch (status) {
    case "running":
      return localize(lang, "Выполняется", "Running");
    case "pending":
      return localize(lang, "В очереди", "Queued");
    case "waiting":
      return localize(lang, "Ждёт ответа", "Needs answer");
    case "plan_review":
      return localize(lang, "План на проверке", "Plan review");
    case "paused":
      return localize(lang, "Пауза", "Paused");
    case "failed":
      return localize(lang, "Ошибка", "Failed");
    case "stopped":
      return localize(lang, "Остановлен", "Stopped");
    case "completed":
      return localize(lang, "Завершён", "Completed");
    default:
      return status || localize(lang, "Активен", "Active");
  }
}

function activeRunStatus(run: AgentRuntimeRunItem | undefined, fallbackActiveRunId: number | null, lang: "ru" | "en") {
  const status = run?.status || (fallbackActiveRunId ? "running" : "");
  const presentation = agentRunStatusPresentation(status);
  return {
    status,
    label: runStatusLabel(status, lang),
    tone: presentation.tone === "ai" ? "info" : presentation.tone,
    pulse: Boolean(presentation.pulse || status === "waiting"),
  } as const;
}

export default function AgentsPage() {
  const { t, lang } = useI18n();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [modeFilter, setModeFilter] = useState<"all" | "mini" | "full" | "multi">("all");
  const [createOpen, setCreateOpen] = useState(false);
  const [editingAgent, setEditingAgent] = useState<AgentItem | null>(null);
  const [createdAgentId, setCreatedAgentId] = useState<number | null>(null);
  const [runningId, setRunningId] = useState<number | null>(null);
  const [stoppingId, setStoppingId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);
  const [cleaningStale, setCleaningStale] = useState(false);
  const [result, setResult] = useState<AgentRunResult | null>(null);
  const [reportModalOpen, setReportModalOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<AgentItem | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["agents", "list"],
    queryFn: () => fetchAgents(),
    refetchInterval: 10_000,
  });

  const allAgents = data?.agents || [];
  const agents = allAgents.filter(
    (a) => modeFilter === "all" || a.mode === modeFilter,
  );
  const activeAgents = allAgents.filter((agent) => agent.active_run_id).length;
  const scheduledAgents = allAgents.filter(isAgentScheduled).length;
  const serverScopeCount = allAgents.reduce((sum, agent) => sum + agent.server_count, 0);
  const executionWarning = allAgents.find(
    (agent) => agent.execution_readiness?.required && !agent.execution_readiness.ready,
  )?.execution_readiness;
  const executionReadiness = allAgents.find((agent) => agent.execution_readiness?.required)?.execution_readiness;
  const workerStates = data?.worker_states || {};
  const runtimeOverview = data?.runtime_overview;
  const activeRunByAgentId = new Map<number, AgentRuntimeRunItem>();
  for (const item of runtimeOverview?.items.active_runs || []) {
    if (item.agent_id) {
      activeRunByAgentId.set(item.agent_id, item);
    }
  }
  const showRuntimeOverview = Boolean(
    runtimeOverview
      && (
        allAgents.length > 0
        || runtimeOverview.summary.active_runs > 0
        || runtimeOverview.summary.queued_dispatches > 0
        || runtimeOverview.summary.claimed_dispatches > 0
        || runtimeOverview.summary.scheduled_due_now > 0
        || runtimeOverview.summary.issues > 0
      ),
  );
  const scheduledWorker = workerStates.scheduled_agents;
  const showScheduledWorker = scheduledAgents > 0 || Boolean(scheduledWorker && scheduledWorker.status !== "missing");

  const onRun = async (ag: AgentItem) => {
    const blockedReason = runBlockedReason(ag, lang);
    if (blockedReason) {
      setActionError(blockedReason);
      return;
    }

    setRunningId(ag.id);
    setActionError(null);
    setActionNotice(null);
    setResult(null);
    try {
      const res = await runAgent(ag.id);
      if (res.runs?.length > 0) {
        setResult(res.runs[0]);
        setReportModalOpen(true);
      }
      if ((ag.mode === "full" || ag.mode === "multi") && res.run_id) {
        navigate(`/agents/run/${res.run_id}`);
        return;
      }
      await queryClient.invalidateQueries({ queryKey: ["agents"] });
    } catch {
      setResult({
        run_id: 0,
        server_name: localize(lang, "Ошибка запуска", "Run error"),
        status: "failed",
        ai_analysis: localize(lang, "Агент не запустился. Проверьте доступ к серверу и настройки агента.", "The agent did not start. Check server access and agent settings."),
        duration_ms: 0,
        commands_output: [],
      });
    } finally {
      setRunningId(null);
    }
  };

  const onStop = async (ag: AgentItem) => {
    if (!ag.active_run_id) {
      setActionError(localize(lang, "У агента нет активного запуска.", "The agent has no active run."));
      return;
    }

    setStoppingId(ag.id);
    setActionError(null);
    setActionNotice(null);
    try {
      await stopAgent(ag.id, ag.active_run_id);
      await queryClient.invalidateQueries({ queryKey: ["agents"] });
    } catch {
      setActionError(localize(lang, "Не удалось остановить активный запуск.", "Failed to stop the active run."));
    } finally {
      setStoppingId(null);
    }
  };

  const onCleanupStale = async () => {
    setCleaningStale(true);
    setActionError(null);
    setActionNotice(null);
    try {
      const response = await cleanupStaleAgentRuns({ limit: 50 });
      const cleaned = response.cleanup.cleaned;
      const canceled = response.cleanup.canceled_dispatches;
      setActionNotice(
        localize(
          lang,
          `Очищено зависших запусков: ${cleaned}; отменено dispatch: ${canceled}.`,
          `Cleaned stale runs: ${cleaned}; canceled dispatches: ${canceled}.`,
        ),
      );
      await queryClient.invalidateQueries({ queryKey: ["agents"] });
    } catch {
      setActionError(localize(lang, "Не удалось очистить зависшие запуски.", "Failed to clean up stale runs."));
    } finally {
      setCleaningStale(false);
    }
  };

  const onDelete = async (agent: AgentItem) => {
    setDeleteTarget(agent);
  };

  const copyExecutionCommand = async (command: string) => {
    if (!command) return;
    try {
      await navigator.clipboard?.writeText(command);
      setActionError(null);
    } catch {
      setActionError(command);
    }
  };

  const confirmDeleteAgent = async () => {
    if (!deleteTarget) return;
    await deleteAgent(deleteTarget.id);
    setDeleteTarget(null);
    await queryClient.invalidateQueries({ queryKey: ["agents"] });
  };

  if (isLoading) return <QueryStateBlock loading loadingText={t("loading")} className="p-6">{null}</QueryStateBlock>;

  return (
    <PageShell width="6xl">
      <PageHero
        kicker="Automation"
        title={t("agent.title")}
        description={localize(
          lang,
          `${allAgents.length} настроено · ${activeAgents} выполняется · ${scheduledAgents} по расписанию`,
          `${allAgents.length} configured · ${activeAgents} running · ${scheduledAgents} scheduled`,
        )}
        actions={
          <div className="flex w-full flex-col gap-2 sm:w-auto sm:flex-row sm:items-center sm:justify-end">
            <div className="inline-flex min-h-10 rounded-lg border border-border bg-secondary/20 p-0.5 text-xs font-semibold">
              {(["all", "mini", "full", "multi"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  aria-pressed={modeFilter === m}
                  onClick={() => setModeFilter(m)}
                  className={`rounded-md px-3 py-1.5 transition-all duration-150 ${modeFilter === m ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"}`}
                >{agentModeLabel(m, lang)}</button>
              ))}
            </div>
            <Button size="icon" variant="ghost" className="h-10 w-10" onClick={() => queryClient.invalidateQueries({ queryKey: ["agents"] })} aria-label={t("udash.refresh")}>
              <RefreshCw className="h-4 w-4" />
            </Button>
            <Button size="sm" className="h-10 gap-1.5 text-sm" onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4" /> {t("agent.new")}
            </Button>
          </div>
        }
      />

      <MetricGrid className="grid-cols-2 xl:grid-cols-4">
        <MetricCard label={t("agent.title")} value={allAgents.length} description={t("agent.view_all")} icon={<Bot className="h-4 w-4" />} />
        <MetricCard label={t("agent.active_runs")} value={activeAgents} description={activeAgents > 0 ? t("agent.working_on") : t("agent.manual")} icon={<Activity className="h-4 w-4" />} tone={activeAgents > 0 ? "info" : "default"} />
        <MetricCard label={t("agent.schedule")} value={scheduledAgents} description={scheduledAgents > 0 ? t("agent.every") : t("agent.manual")} icon={<Clock className="h-4 w-4" />} />
        <MetricCard label={t("nav.servers")} value={serverScopeCount} description={t("agent.servers_lc")} icon={<Server className="h-4 w-4" />} />
      </MetricGrid>

      {showRuntimeOverview && runtimeOverview ? (
        <AgentRuntimeOverviewPanel
          overview={runtimeOverview}
          lang={lang}
          onCopyCommand={copyExecutionCommand}
          onCleanupStale={onCleanupStale}
          cleaningStale={cleaningStale}
        />
      ) : null}

      {executionReadiness ? (
        <ExecutionWorkerPanel
          readiness={executionReadiness}
          lang={lang}
          onCopyCommand={copyExecutionCommand}
        />
      ) : null}

      {showScheduledWorker ? (
        <WorkerRuntimePanel
          title={localize(lang, "Schedule worker", "Schedule worker")}
          description={localize(
            lang,
            "Автозапуск агентов по расписанию",
            "Scheduled agent dispatcher runtime",
          )}
          statusTitle={localize(
            lang,
            scheduledWorker?.status === "running" && !scheduledWorker?.is_stale
              ? "Scheduler принимает расписания"
              : "Scheduler не подтверждён",
            scheduledWorker?.status === "running" && !scheduledWorker?.is_stale
              ? "Scheduler is accepting due agents"
              : "Scheduler is not confirmed",
          )}
          statusDescription={localize(
            lang,
            scheduledWorker?.status === "running" && !scheduledWorker?.is_stale
              ? "Due-агенты будут подхвачены фоновым процессом."
              : "Агенты с расписанием не стартуют автоматически, пока worker не активен.",
            scheduledWorker?.status === "running" && !scheduledWorker?.is_stale
              ? "Due agents will be picked up by the background process."
              : "Scheduled agents will not launch automatically until the worker is active.",
          )}
          worker={scheduledWorker}
          command="python manage.py run_scheduled_agents --daemon --worker-key default"
          icon={<Clock className="h-4 w-4" />}
          lang={lang}
          onCopyCommand={copyExecutionCommand}
        />
      ) : null}

      {executionWarning ? (
        <div className="rounded-lg border border-amber-500/25 bg-amber-500/8 px-4 py-3 text-sm text-amber-100">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <div className="flex items-center gap-2 font-semibold text-foreground">
                <AlertTriangle className="h-4 w-4 text-amber-400" />
                {executionWarning.title}
              </div>
              <p className="mt-1 leading-6 text-muted-foreground">{executionWarning.description}</p>
              {executionWarning.next_action ? (
                <p className="mt-2 break-words font-mono text-xs text-amber-200">{executionWarning.next_action}</p>
              ) : null}
            </div>
            <StatusBadge label={executionWarning.status} tone={readinessTone(executionWarning)} />
          </div>
        </div>
      ) : null}

      {actionError ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <div className="flex items-start justify-between gap-3">
            <div className="flex min-w-0 items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span className="break-words leading-6">{actionError}</span>
            </div>
            <Button
              size="icon"
              variant="ghost"
              className="h-7 w-7 shrink-0 text-destructive hover:text-destructive"
              onClick={() => setActionError(null)}
              aria-label={localize(lang, "Скрыть ошибку", "Dismiss error")}
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      ) : null}

      {actionNotice ? (
        <div className="rounded-lg border border-emerald-500/25 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
          <div className="flex items-start justify-between gap-3">
            <div className="flex min-w-0 items-start gap-2">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-400" />
              <span className="break-words leading-6">{actionNotice}</span>
            </div>
            <Button
              size="icon"
              variant="ghost"
              className="h-7 w-7 shrink-0 text-emerald-100 hover:text-emerald-50"
              onClick={() => setActionNotice(null)}
              aria-label={localize(lang, "Скрыть сообщение", "Dismiss notice")}
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      ) : null}

      {result && !reportModalOpen && (
        <div className="bg-card border border-border rounded-lg px-4 py-3 flex items-center gap-3">
          <div className={`h-8 w-8 rounded-lg flex items-center justify-center shrink-0 ${result.status === "completed" ? "bg-primary/20 text-primary" : "bg-destructive/20 text-destructive"}`}>
            {result.status === "completed" ? <CheckCircle2 className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-foreground">{result.server_name}</div>
            <div className="text-xs text-muted-foreground">{result.status} · {formatDuration(result.duration_ms)}</div>
          </div>
          <Button size="sm" className="h-9 shrink-0 gap-1.5 text-xs" onClick={() => setReportModalOpen(true)}>
            <FileText className="h-3.5 w-3.5" /> {t("agent.report")}
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-9 w-9 shrink-0 text-muted-foreground"
            onClick={() => setResult(null)}
            aria-label={localize(lang, "Скрыть результат запуска", "Dismiss run result")}
          >
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      )}

      {result && (
        <AgentReportModal result={result} open={reportModalOpen} onClose={() => setReportModalOpen(false)} />
      )}
      {agents.length === 0 ? (
        <EmptyState
          icon={<Bot className="h-5 w-5" />}
          title={t("agent.empty")}
          description={modeFilter !== "all" ? t("agent.no_recent") : t("agent.custom_desc")}
          actions={
            <Button size="sm" onClick={() => setCreateOpen(true)} className="gap-1">
              <Plus className="h-3 w-3" /> {t("agent.create_first")}
            </Button>
          }
        />
      ) : (
        <SectionCard title={t("agent.title")} description={localize(lang, `Показано: ${agents.length}`, `${agents.length} visible`)} icon={<Bot className="h-4 w-4" />} bodyClassName="p-0">
          <div className="divide-y divide-border/40">
            {agents.map((ag) => {
              const AgentIcon = AGENT_ICONS[ag.agent_type] || Settings2;
              const isStarting = runningId === ag.id;
              const isStopping = stoppingId === ag.id;
              const isRunning = isStarting || !!ag.active_run_id;
              const blockedReason = runBlockedReason(ag, lang);
              const activeRun = activeRunByAgentId.get(ag.id);
              const activeRunMeta = activeRunStatus(activeRun, ag.active_run_id, lang);
              const activeRunQuestion = String(activeRun?.pending_question || "").trim();
              const activeRunAge = formatRuntimeAge(activeRun?.age_seconds);
              const activeRunCta = activeRunMeta.status === "waiting"
                ? localize(lang, "Ответить", "Answer")
                : activeRunMeta.status === "plan_review"
                  ? localize(lang, "План", "Plan")
                  : localize(lang, "Следить", "Watch");
              return (
                <div
                  key={ag.id}
                  className={`flex flex-col gap-3 px-4 py-3 transition-colors sm:flex-row sm:items-center ${
                    createdAgentId === ag.id
                      ? "bg-primary/8 ring-1 ring-inset ring-primary/25"
                      : "hover:bg-secondary/20"
                  }`}
                >
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-border/60 bg-secondary/30 transition-colors group-hover:bg-secondary/60">
                    <AgentIcon className="h-4 w-4 text-primary" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span className="text-sm font-medium text-foreground">{ag.name}</span>
                      <span className="rounded-md border border-border/50 bg-secondary/40 px-1.5 py-0.5 text-xs font-semibold text-muted-foreground">
                        {agentModeLabel(ag.mode, lang)}
                      </span>
                      {ag.active_run_id && (
                        <StatusBadge label={activeRunMeta.label} tone={activeRunMeta.tone} />
                      )}
                      {ag.execution_readiness?.required ? (
                        <StatusBadge
                          label={ag.execution_readiness.ready ? "worker ok" : "worker wait"}
                          tone={readinessTone(ag.execution_readiness)}
                        />
                      ) : null}
                      <span className="rounded-md border border-border/50 bg-secondary/40 px-1.5 py-0.5 text-xs font-semibold text-muted-foreground">
                        sudo: {localize(lang, sudoAgentOption(ag.sudo_policy).labelRu, sudoAgentOption(ag.sudo_policy).labelEn)}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-muted-foreground mt-0.5">
                      <span className="flex items-center gap-0.5"><Server className="h-2.5 w-2.5" /> {ag.server_count}</span>
                      {ag.last_run_at && <span className="flex items-center gap-0.5"><Clock className="h-2.5 w-2.5" /> {relativeTime(ag.last_run_at)}</span>}
                      {activeRun ? (
                        <span className="flex items-center gap-0.5">
                          <Activity className="h-2.5 w-2.5" />
                          run #{activeRun.run_id} · {activeRunAge}
                        </span>
                      ) : null}
                      {isAgentScheduled(ag) && <span className="flex items-center gap-0.5"><RefreshCw className="h-2.5 w-2.5" /> {formatScheduleConfigLabel(ag.schedule_config, ag.schedule_minutes, lang)}</span>}
                    </div>
                    {ag.goal && <p className="text-xs text-muted-foreground mt-0.5 truncate max-w-md">{ag.goal}</p>}
                    {activeRunQuestion ? (
                      <p className="mt-1 flex max-w-2xl items-start gap-1.5 rounded-md border border-amber-500/20 bg-amber-500/8 px-2 py-1.5 text-xs leading-5 text-amber-100">
                        <MessageSquare className="mt-0.5 h-3 w-3 shrink-0 text-amber-300" />
                        <span className="min-w-0 break-words">
                          {localize(lang, "Вопрос агента:", "Agent question:")} {activeRunQuestion}
                        </span>
                      </p>
                    ) : null}
                    {!ag.active_run_id && blockedReason ? (
                      <p className="mt-1 max-w-2xl break-words font-mono text-xs leading-5 text-amber-300">{blockedReason}</p>
                    ) : null}
                  </div>
                  <div className="flex w-full flex-wrap items-center justify-end gap-2 sm:w-auto sm:shrink-0">
                    {ag.active_run_id ? (
                      <>
                        <Button asChild size="xs" variant="outline" className="gap-1">
                          <Link to={`/agents/run/${ag.active_run_id}`}>
                            {activeRunMeta.status === "waiting" ? <MessageSquare className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
                            {activeRunCta}
                          </Link>
                        </Button>
                        <Button size="xs" variant="outline" className="gap-1 text-red-400" disabled={isStopping} onClick={() => onStop(ag)}>
                          {isStopping ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Square className="h-3 w-3" />} {t("agent.stop")}
                        </Button>
                      </>
                    ) : (
                      <>
                        {ag.last_run_id && (
                          <Button asChild size="xs" variant="ghost" className="gap-1 text-muted-foreground hover:text-foreground">
                            <Link to={`/agents/run/${ag.last_run_id}`}>
                              <FileText className="h-3 w-3" /> {t("agent.report")}
                            </Link>
                          </Button>
                        )}
                        <Button size="xs" variant="ghost" className="gap-1 text-muted-foreground hover:text-foreground" onClick={() => setEditingAgent(ag)}>
                          <Settings2 className="h-3 w-3" /> {localize(lang, "Править", "Edit")}
                        </Button>
                        <Button
                          size="xs"
                          variant="outline"
                          className="gap-1"
                          disabled={isRunning || Boolean(blockedReason)}
                          title={blockedReason || undefined}
                          onClick={() => onRun(ag)}
                        >
                          {isStarting ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />} {t("agent.run")}
                        </Button>
                      </>
                    )}
                    {ag.active_run_id && (
                      <Button size="xs" variant="ghost" className="gap-1 text-muted-foreground hover:text-foreground" onClick={() => setEditingAgent(ag)}>
                        <Settings2 className="h-3 w-3" /> {localize(lang, "Править", "Edit")}
                      </Button>
                    )}
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-8 w-8 text-muted-foreground hover:text-red-400"
                      onClick={() => onDelete(ag)}
                      aria-label={localize(lang, `Удалить ${ag.name}`, `Delete ${ag.name}`)}
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </SectionCard>
      )}

      <CreateAgentDialog open={createOpen} onClose={() => setCreateOpen(false)}
        onSaved={async ({ id, mode }) => {
          setModeFilter("all");
          setCreatedAgentId(id);
          setCreateOpen(false);
          await queryClient.invalidateQueries({ queryKey: ["agents", "list"] });
          if (mode === "full" || mode === "multi") {
            navigate("/agents");
          }
          window.setTimeout(() => setCreatedAgentId((current) => (current === id ? null : current)), 8000);
        }} />
      <CreateAgentDialog
        open={Boolean(editingAgent)}
        initialAgent={editingAgent}
        onClose={() => setEditingAgent(null)}
        onSaved={async ({ id }) => {
          setCreatedAgentId(id);
          setEditingAgent(null);
          await queryClient.invalidateQueries({ queryKey: ["agents", "list"] });
          window.setTimeout(() => setCreatedAgentId((current) => (current === id ? null : current)), 8000);
        }}
      />
      <DeleteDialog
        open={Boolean(deleteTarget)}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        title={localize(lang, "Удалить агента?", "Delete agent?")}
        description={localize(
          lang,
          `Агент "${deleteTarget?.name || ""}" будет удалён. История уже созданных запусков останется доступной в отчётах.`,
          `Agent "${deleteTarget?.name || ""}" will be removed. Existing run history remains available in reports.`,
        )}
        confirmLabel={localize(lang, "Удалить агента", "Delete agent")}
        cancelLabel={localize(lang, "Отмена", "Cancel")}
        onConfirm={confirmDeleteAgent}
      />
    </PageShell>
  );
}

function AgentRuntimeOverviewPanel({
  overview,
  lang,
  onCopyCommand,
  onCleanupStale,
  cleaningStale,
}: {
  overview: AgentRuntimeOverview;
  lang: "ru" | "en";
  onCopyCommand: (command: string) => void;
  onCleanupStale: () => void;
  cleaningStale: boolean;
}) {
  const summary = overview.summary;
  const hasIssues = overview.issues.length > 0;
  const dispatchQueue = summary.queued_dispatches + summary.claimed_dispatches;
  const staleCount = overview.items?.stale_candidates?.length || 0;
  const supervisorCommand = overview.commands?.ops_supervisor || "";

  return (
    <SectionCard
      title={localize(lang, "Agent runtime", "Agent runtime")}
      description={localize(
        lang,
        "Очередь запусков, расписание и блокеры выполнения",
        "Run queue, schedule, and execution blockers",
      )}
      icon={<Activity className="h-4 w-4" />}
      bodyClassName="space-y-4"
    >
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge label={overview.status} tone={severityTone(overview.severity)} />
            {hasIssues ? <StatusBadge label={`${summary.issues} issues`} tone="warning" /> : <StatusBadge label="clear" tone="success" />}
            {staleCount ? <StatusBadge label={`${staleCount} stale`} tone="warning" /> : null}
            <span className="text-sm font-semibold text-foreground">
              {hasIssues
                ? localize(lang, "Есть runtime-блокеры", "Runtime blockers detected")
                : localize(lang, "Очередь без блокеров", "Queue has no blockers")}
            </span>
          </div>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
            {localize(
              lang,
              `${summary.active_runs} активных запусков, ${dispatchQueue} dispatch в очереди, ${summary.scheduled_due_now} due по расписанию.`,
              `${summary.active_runs} active runs, ${dispatchQueue} queued dispatches, ${summary.scheduled_due_now} due scheduled agents.`,
            )}
          </p>
        </div>
        <div className="flex min-w-0 flex-col gap-3 lg:min-w-[520px]">
          <div className="grid min-w-0 grid-cols-2 gap-x-5 gap-y-2 text-xs text-muted-foreground sm:grid-cols-4">
            <WorkerFact label="active" value={String(summary.active_runs)} />
            <WorkerFact label="pending" value={String(summary.pending_runs)} />
            <WorkerFact label="queued" value={String(summary.queued_dispatches)} />
            <WorkerFact label="claimed" value={String(summary.claimed_dispatches)} />
            <WorkerFact label="running" value={String(summary.running_runs)} />
            <WorkerFact label="waiting" value={String(summary.waiting_runs)} />
            <WorkerFact label="scheduled" value={String(summary.scheduled_agents)} />
            <WorkerFact label="due" value={String(summary.scheduled_due_now)} />
          </div>
          {staleCount ? (
            <div className="flex justify-start sm:justify-end">
              <Button
                size="sm"
                variant="outline"
                className="h-9 shrink-0 gap-1.5 border-amber-500/30 text-amber-200 hover:text-amber-100"
                disabled={cleaningStale}
                onClick={onCleanupStale}
              >
                {cleaningStale ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <AlertTriangle className="h-3.5 w-3.5" />}
                {cleaningStale
                  ? localize(lang, "Очищаем", "Cleaning")
                  : localize(lang, "Очистить stale", "Clean stale")}
              </Button>
            </div>
          ) : null}
        </div>
      </div>
      {hasIssues && supervisorCommand ? (
        <div className="rounded-md border border-primary/20 bg-primary/8 px-3 py-3">
          <div className="flex flex-col gap-2 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0">
              <p className="text-sm font-semibold text-foreground">
                {localize(lang, "Рекомендуемый production worker", "Recommended production worker")}
              </p>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                {localize(
                  lang,
                  "Supervisor держит execution-plane, расписания и watchers одним управляемым процессом.",
                  "Supervisor keeps execution-plane, schedules, and watchers under one managed process.",
                )}
              </p>
            </div>
            <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center lg:min-w-[520px]">
              <code className="min-w-0 flex-1 break-words rounded-md border border-border/60 bg-background/50 px-2 py-1.5 text-xs text-primary">
                {supervisorCommand}
              </code>
              <Button
                size="xs"
                variant="outline"
                className="shrink-0 gap-1"
                onClick={() => onCopyCommand(supervisorCommand)}
              >
                <Copy className="h-3 w-3" />
                {localize(lang, "Копировать", "Copy")}
              </Button>
            </div>
          </div>
        </div>
      ) : null}
      {hasIssues ? (
        <div className="grid gap-2 lg:grid-cols-2">
          {overview.issues.slice(0, 4).map((issue) => (
            <div key={issue.id} className="rounded-md border border-amber-500/20 bg-amber-500/8 px-3 py-2">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge label={issue.severity} tone={severityTone(issue.severity)} />
                <span className="text-sm font-semibold text-foreground">{issue.title}</span>
              </div>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">{issue.description}</p>
              {issue.next_action ? (
                <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-center">
                  <code className="min-w-0 flex-1 break-words rounded-md border border-border/60 bg-background/50 px-2 py-1.5 text-xs text-amber-200">
                    {issue.next_action}
                  </code>
                  <Button
                    size="xs"
                    variant="outline"
                    className="shrink-0 gap-1"
                    onClick={() => onCopyCommand(issue.next_action)}
                  >
                    <Copy className="h-3 w-3" />
                    {localize(lang, "Копировать", "Copy")}
                  </Button>
                </div>
              ) : null}
            </div>
          ))}
        </div>
      ) : null}
      <AgentRuntimeItems overview={overview} lang={lang} />
    </SectionCard>
  );
}

function AgentRuntimeItems({ overview, lang }: { overview: AgentRuntimeOverview; lang: "ru" | "en" }) {
  const items = overview.items || {
    active_runs: [],
    queued_dispatches: [],
    scheduled_due: [],
    stale_candidates: [],
  };
  const activeRuns = items.active_runs || [];
  const queuedDispatches = items.queued_dispatches || [];
  const scheduledDue = items.scheduled_due || [];
  const staleCandidates = items.stale_candidates || [];
  const hasItems = activeRuns.length || queuedDispatches.length || scheduledDue.length || staleCandidates.length;

  if (!hasItems) return null;

  return (
    <div className="grid gap-3 xl:grid-cols-3">
      {activeRuns.length ? (
        <RuntimeItemList
          title={localize(lang, "Активные запуски", "Active runs")}
          description={localize(lang, "Что сейчас занимает execution slot", "Currently occupying execution slots")}
        >
          {activeRuns.slice(0, 5).map((run) => (
            <RuntimeItemRow
              key={`run-${run.run_id}`}
              status={run.is_stale_candidate ? "stale" : run.status}
              tone={run.is_stale_candidate ? "warning" : severityTone(run.status === "running" ? "success" : "info")}
              title={run.agent_name}
              meta={[
                `#${run.run_id}`,
                run.server_name || localize(lang, "сервер не указан", "no server"),
                formatRuntimeAge(run.age_seconds),
              ]}
              to={`/agents/run/${run.run_id}`}
              linkLabel={localize(lang, "Следить", "Watch")}
            />
          ))}
        </RuntimeItemList>
      ) : null}

      {queuedDispatches.length ? (
        <RuntimeItemList
          title={localize(lang, "Очередь dispatch", "Dispatch queue")}
          description={localize(lang, "Что ждёт или взято worker'ом", "Queued or claimed by a worker")}
        >
          {queuedDispatches.slice(0, 5).map((dispatch) => (
            <RuntimeItemRow
              key={`dispatch-${dispatch.dispatch_id}`}
              status={dispatch.status}
              tone={severityTone(dispatch.status === "claimed" ? "info" : "warning")}
              title={dispatch.agent_name}
              meta={[
                dispatch.dispatch_kind,
                `run #${dispatch.run_id}`,
                localize(lang, `в очереди ${formatRuntimeAge(dispatch.queued_age_seconds)}`, `queued ${formatRuntimeAge(dispatch.queued_age_seconds)}`),
              ]}
              detail={dispatch.claimed_by ? `worker: ${dispatch.claimed_by}` : ""}
              to={`/agents/run/${dispatch.run_id}`}
              linkLabel={localize(lang, "Run", "Run")}
            />
          ))}
        </RuntimeItemList>
      ) : null}

      {scheduledDue.length ? (
        <RuntimeItemList
          title={localize(lang, "Due расписание", "Due schedule")}
          description={localize(lang, "Кого пора запускать по расписанию", "Agents due for scheduled launch")}
        >
          {scheduledDue.slice(0, 5).map((agent) => (
            <RuntimeItemRow
              key={`scheduled-${agent.agent_id}`}
              status={agent.active_run_id ? agent.active_run_status || "active" : "due"}
              tone={agent.active_run_id ? "info" : "warning"}
              title={agent.agent_name}
              meta={[
                agent.server_names[0] || `${agent.server_count} servers`,
                formatScheduleConfigLabel(agent.schedule_config, agent.schedule_minutes, lang),
                agent.due_age_seconds ? localize(lang, `due ${formatRuntimeAge(agent.due_age_seconds)}`, `due ${formatRuntimeAge(agent.due_age_seconds)}`) : "due now",
              ]}
              to={agent.active_run_id ? `/agents/run/${agent.active_run_id}` : undefined}
              linkLabel={agent.active_run_id ? localize(lang, "Открыть", "Open") : undefined}
            />
          ))}
        </RuntimeItemList>
      ) : null}

      {staleCandidates.length ? (
        <RuntimeItemList
          title={localize(lang, "Зависшие кандидаты", "Stale candidates")}
          description={localize(lang, "Активные строки старше runtime threshold", "Active rows older than runtime threshold")}
        >
          {staleCandidates.slice(0, 5).map((run) => (
            <RuntimeItemRow
              key={`stale-${run.run_id}`}
              status="stale"
              tone="warning"
              title={run.agent_name}
              meta={[`#${run.run_id}`, run.status, formatRuntimeAge(run.age_seconds)]}
              to={`/agents/run/${run.run_id}`}
              linkLabel={localize(lang, "Проверить", "Inspect")}
            />
          ))}
        </RuntimeItemList>
      ) : null}
    </div>
  );
}

function RuntimeItemList({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <div className="min-w-0 rounded-md border border-border/70 bg-background/35">
      <div className="border-b border-border/60 px-3 py-2">
        <p className="text-sm font-semibold text-foreground">{title}</p>
        <p className="mt-0.5 truncate text-xs text-muted-foreground">{description}</p>
      </div>
      <div className="divide-y divide-border/50">{children}</div>
    </div>
  );
}

function RuntimeItemRow({
  status,
  tone,
  title,
  meta,
  detail,
  to,
  linkLabel,
}: {
  status: string;
  tone: "neutral" | "success" | "warning" | "danger" | "info";
  title: string;
  meta: string[];
  detail?: string;
  to?: string;
  linkLabel?: string;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-2 px-3 py-2.5 sm:flex-row sm:items-start sm:justify-between">
      <div className="min-w-0">
        <div className="flex min-w-0 flex-wrap items-center gap-1.5">
          <StatusBadge label={status} tone={tone} />
          <span className="truncate text-sm font-medium text-foreground">{title}</span>
        </div>
        <p className="mt-1 truncate text-xs text-muted-foreground">{meta.filter(Boolean).join(" · ")}</p>
        {detail ? <p className="mt-1 truncate font-mono text-xs text-muted-foreground">{detail}</p> : null}
      </div>
      {to && linkLabel ? (
        <Button asChild size="xs" variant="ghost" className="h-7 shrink-0 gap-1 text-muted-foreground hover:text-foreground">
          <Link to={to}>
            <Eye className="h-3 w-3" />
            {linkLabel}
          </Link>
        </Button>
      ) : null}
    </div>
  );
}

function ExecutionWorkerPanel({
  readiness,
  lang,
  onCopyCommand,
}: {
  readiness: AgentExecutionReadiness;
  lang: "ru" | "en";
  onCopyCommand: (command: string) => void;
}) {
  const worker = readiness.worker;
  const summaryEntries = workerSummaryEntries(worker?.last_summary);
  const command = readiness.next_action.replace(/^.*?:\s*/, "").trim();
  const tone = readinessTone(readiness);

  return (
    <SectionCard
      title={localize(lang, "Execution worker", "Execution worker")}
      description={localize(
        lang,
        "Состояние очереди full/multi-агентов",
        "Full/multi agent queue runtime",
      )}
      icon={<Cpu className="h-4 w-4" />}
      bodyClassName="space-y-4"
    >
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge label={readiness.status} tone={tone} />
            {worker?.is_stale ? <StatusBadge label="stale" tone="warning" /> : null}
            <span className="text-sm font-semibold text-foreground">{readiness.title}</span>
          </div>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">{readiness.description}</p>
          {readiness.next_action ? (
            <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
              <code className="min-w-0 flex-1 break-words rounded-md border border-border/60 bg-background/50 px-2.5 py-2 text-xs text-amber-200">
                {command || readiness.next_action}
              </code>
              <Button
                size="sm"
                variant="outline"
                className="h-9 shrink-0 gap-1.5"
                onClick={() => onCopyCommand(command || readiness.next_action)}
              >
                <Copy className="h-3.5 w-3.5" />
                {localize(lang, "Скопировать", "Copy")}
              </Button>
            </div>
          ) : null}
        </div>
        <div className="grid min-w-0 grid-cols-2 gap-x-5 gap-y-2 text-xs text-muted-foreground sm:grid-cols-3 lg:min-w-[420px]">
          <WorkerFact label="worker" value={worker?.worker_key || "default"} />
          <WorkerFact label="host" value={worker?.hostname || "—"} />
          <WorkerFact label="pid" value={worker?.pid ? String(worker.pid) : "—"} />
          <WorkerFact label="heartbeat" value={formatWorkerTime(worker?.heartbeat_at, lang)} />
          <WorkerFact label="lease" value={formatWorkerTime(worker?.lease_expires_at, lang)} />
          <WorkerFact label="cycle" value={formatWorkerTime(worker?.last_cycle_finished_at, lang)} />
        </div>
      </div>
      {worker?.last_error ? (
        <div className="rounded-md border border-destructive/25 bg-destructive/10 px-3 py-2 text-xs leading-5 text-destructive">
          {worker.last_error}
        </div>
      ) : null}
      {summaryEntries.length ? (
        <div className="flex flex-wrap gap-2">
          {summaryEntries.map(([key, value]) => (
            <span key={key} className="rounded-md border border-border/60 bg-secondary/20 px-2 py-1 text-xs text-muted-foreground">
              <span className="font-mono text-foreground">{key}</span>: {String(value)}
            </span>
          ))}
        </div>
      ) : null}
    </SectionCard>
  );
}

function WorkerRuntimePanel({
  title,
  description,
  statusTitle,
  statusDescription,
  worker,
  command,
  icon,
  lang,
  onCopyCommand,
}: {
  title: string;
  description: string;
  statusTitle: string;
  statusDescription: string;
  worker?: BackgroundWorkerStateRecord;
  command: string;
  icon: ReactNode;
  lang: "ru" | "en";
  onCopyCommand: (command: string) => void;
}) {
  const summaryEntries = workerSummaryEntries(worker?.last_summary);
  const status = worker?.status || "missing";
  const tone = workerStateTone(worker);
  const shouldShowCommand = !worker || worker.is_stale || worker.status === "missing" || worker.status === "stopped" || worker.status === "error";

  return (
    <SectionCard
      title={title}
      description={description}
      icon={icon}
      bodyClassName="space-y-4"
    >
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge label={status} tone={tone} />
            {worker?.is_stale ? <StatusBadge label="stale" tone="warning" /> : null}
            <span className="text-sm font-semibold text-foreground">{statusTitle}</span>
          </div>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">{statusDescription}</p>
          {shouldShowCommand ? (
            <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
              <code className="min-w-0 flex-1 break-words rounded-md border border-border/60 bg-background/50 px-2.5 py-2 text-xs text-amber-200">
                {command}
              </code>
              <Button
                size="sm"
                variant="outline"
                className="h-9 shrink-0 gap-1.5"
                onClick={() => onCopyCommand(command)}
              >
                <Copy className="h-3.5 w-3.5" />
                {localize(lang, "Скопировать", "Copy")}
              </Button>
            </div>
          ) : null}
        </div>
        <div className="grid min-w-0 grid-cols-2 gap-x-5 gap-y-2 text-xs text-muted-foreground sm:grid-cols-3 lg:min-w-[420px]">
          <WorkerFact label="worker" value={worker?.worker_key || "default"} />
          <WorkerFact label="host" value={worker?.hostname || "—"} />
          <WorkerFact label="pid" value={worker?.pid ? String(worker.pid) : "—"} />
          <WorkerFact label="heartbeat" value={formatWorkerTime(worker?.heartbeat_at, lang)} />
          <WorkerFact label="lease" value={formatWorkerTime(worker?.lease_expires_at, lang)} />
          <WorkerFact label="cycle" value={formatWorkerTime(worker?.last_cycle_finished_at, lang)} />
        </div>
      </div>
      {worker?.last_error ? (
        <div className="rounded-md border border-destructive/25 bg-destructive/10 px-3 py-2 text-xs leading-5 text-destructive">
          {worker.last_error}
        </div>
      ) : null}
      {summaryEntries.length ? (
        <div className="flex flex-wrap gap-2">
          {summaryEntries.map(([key, value]) => (
            <span key={key} className="rounded-md border border-border/60 bg-secondary/20 px-2 py-1 text-xs text-muted-foreground">
              <span className="font-mono text-foreground">{key}</span>: {String(value)}
            </span>
          ))}
        </div>
      ) : null}
    </SectionCard>
  );
}

function WorkerFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="font-mono uppercase tracking-wide text-muted-foreground/70">{label}</p>
      <p className="mt-0.5 truncate text-foreground">{value}</p>
    </div>
  );
}
