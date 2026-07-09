import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  cleanupStaleAgentRuns,
  deleteAgent,
  fetchAgents,
  runAgent,
  stopAgent,
  updateAgent,
  type AgentItem,
  type AgentRuntimeRunItem,
  type AgentRunResult,
} from "@/lib/api";
import { localize, useI18n } from "@/lib/i18n";
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  Plus,
  RefreshCw,
  X,
} from "lucide-react";
import { AgentReportModal } from "@/components/studio/AgentReportModal";
import { Button } from "@/components/ui/button";
import { DeleteDialog } from "@/components/system/ConfirmDialog";
import { PageShell, SoftHeader, StatStrip, StatStripItem } from "@/components/ui/page-shell";
import { SkeletonList } from "@/components/ui/list-state";
import { CreateAgentDialog } from "./agents-page/CreateAgentDialog";
import { AgentListSection } from "./agents-page/AgentListSection";
import { AgentSystemHealthSection, countAgentSystemProblems } from "./agents-page/AgentSystemHealthSection";
import {
  formatDuration,
  isAgentScheduled,
} from "./agents-page/agentPageUtils";
import { runBlockedReason } from "./agents-page/agentRuntimeShared";


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
  const pausedAgents = allAgents.filter((agent) => agent.schedule_state === "paused").length;
  const failedAgents = allAgents.filter((agent) => {
    const status = String(agent.last_run_status || "").toLowerCase();
    return !agent.active_run_id && ["failed", "error", "stopped"].includes(status);
  }).length;
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

  const onTogglePause = async (agent: AgentItem) => {
    setActionError(null);
    setActionNotice(null);
    try {
      await updateAgent(agent.id, { is_enabled: !agent.is_enabled });
      await queryClient.invalidateQueries({ queryKey: ["agents"] });
    } catch {
      setActionError(
        localize(
          lang,
          agent.is_enabled ? "Не удалось поставить расписание на паузу." : "Не удалось возобновить расписание.",
          agent.is_enabled ? "Failed to pause the schedule." : "Failed to resume the schedule.",
        ),
      );
    }
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

  if (isLoading) {
    return (
      <PageShell width="7xl" className="space-y-4">
        <SkeletonList rows={6} />
      </PageShell>
    );
  }

  const systemProblems = countAgentSystemProblems({
    runtimeOverview,
    executionReadiness: executionReadiness || executionWarning,
    scheduledWorker,
    showScheduledWorker,
  });
  const healthSection = (
    <AgentSystemHealthSection
      runtimeOverview={runtimeOverview}
      showRuntimeOverview={showRuntimeOverview}
      executionReadiness={executionReadiness || executionWarning}
      scheduledWorker={scheduledWorker}
      showScheduledWorker={showScheduledWorker}
      lang={lang}
      onCopyCommand={copyExecutionCommand}
      onCleanupStale={onCleanupStale}
      cleaningStale={cleaningStale}
    />
  );

  return (
    <PageShell width="7xl" className="space-y-4">
      <SoftHeader
        compact
        title={t("agent.title")}
        count={allAgents.length > 0 ? allAgents.length : undefined}
        subtitle={localize(lang, "Команды и задачи на ваших серверах", "Commands and tasks on your servers")}
        actions={
          <>
            <Button size="icon" variant="ghost" onClick={() => queryClient.invalidateQueries({ queryKey: ["agents"] })} aria-label={t("udash.refresh")}>
              <RefreshCw className="h-4 w-4" />
            </Button>
            <Button className="gap-1.5" onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4" /> {t("agent.new")}
            </Button>
          </>
        }
      />

      {allAgents.length > 0 ? (
        <StatStrip>
          <StatStripItem
            label={localize(lang, "Всего", "Total")}
            value={allAgents.length}
            hint={localize(lang, "профили", "profiles")}
          />
          <StatStripItem
            label={localize(lang, "Выполняется", "Running")}
            value={activeAgents}
            tone={activeAgents > 0 ? "info" : "default"}
            hint={localize(lang, "активные запуски", "active runs")}
          />
          <StatStripItem
            label={localize(lang, "Расписание", "Scheduled")}
            value={scheduledAgents}
            tone={scheduledAgents > 0 ? "success" : "default"}
            hint={
              pausedAgents > 0
                ? localize(lang, `${pausedAgents} на паузе`, `${pausedAgents} paused`)
                : localize(lang, "по расписанию", "on schedule")
            }
          />
          <StatStripItem
            label={localize(lang, "Сбой / стоп", "Failed / stop")}
            value={failedAgents}
            tone={failedAgents > 0 ? "danger" : "default"}
            hint={localize(lang, "последний запуск", "last run")}
          />
        </StatStrip>
      ) : null}

      {systemProblems > 0 ? healthSection : null}

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
        <div className="rounded-lg border border-success/25 bg-success/10 px-4 py-3 text-sm text-foreground">
          <div className="flex items-start justify-between gap-3">
            <div className="flex min-w-0 items-start gap-2">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" />
              <span className="break-words leading-6">{actionNotice}</span>
            </div>
            <Button
              size="icon"
              variant="ghost"
              className="h-7 w-7 shrink-0"
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
        totalCount={allAgents.length}
        modeFilter={modeFilter}
        onModeFilterChange={setModeFilter}
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
        onTogglePause={onTogglePause}
      />

      {systemProblems === 0 ? healthSection : null}

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
