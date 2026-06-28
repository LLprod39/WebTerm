import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  cleanupStaleAgentRuns,
  deleteAgent,
  fetchAgents,
  runAgent,
  stopAgent,
  type AgentItem,
  type AgentRuntimeRunItem,
  type AgentRunResult,
} from "@/lib/api";
import { localize, useI18n } from "@/lib/i18n";
import {
  Activity,
  AlertTriangle,
  Bot,
  CheckCircle2,
  Clock,
  FileText,
  Plus,
  RefreshCw,
  Server,
  X,
} from "lucide-react";
import { AgentReportModal } from "@/components/studio/AgentReportModal";
import { Button } from "@/components/ui/button";
import { DeleteDialog } from "@/components/system/ConfirmDialog";
import { MetricCard, MetricGrid, PageHero, PageShell, QueryStateBlock, StatusBadge } from "@/components/ui/page-shell";
import { CreateAgentDialog } from "./agents-page/CreateAgentDialog";
import { AgentListSection } from "./agents-page/AgentListSection";
import { AgentRuntimeOverviewPanel } from "./agents-page/AgentRuntimeOverviewPanel";
import { ExecutionWorkerPanel, WorkerRuntimePanel } from "./agents-page/AgentWorkerPanels";
import {
  agentModeLabel,
  formatDuration,
  isAgentScheduled,
} from "./agents-page/agentPageUtils";
import { readinessTone, runBlockedReason } from "./agents-page/agentRuntimeShared";


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
      <AgentListSection
        agents={agents}
        modeFilter={modeFilter}
        lang={lang}
        t={t}
        createdAgentId={createdAgentId}
        runningId={runningId}
        stoppingId={stoppingId}
        activeRunByAgentId={activeRunByAgentId}
        onCreate={() => setCreateOpen(true)}
        onEdit={setEditingAgent}
        onRun={onRun}
        onStop={onStop}
        onDelete={onDelete}
      />

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
