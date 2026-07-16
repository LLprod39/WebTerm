import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  cleanupStaleAgentRuns,
  deleteAgent,
  fetchAgents,
  fetchAuthSession,
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
import { AgentSystemHealthSection } from "./agents-page/AgentSystemHealthSection";
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
  const { data: authSession } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const isAdmin = Boolean(authSession?.user?.is_staff);

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
  for (const item of runtimeOverview?.items?.active_runs || []) {
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

  const openCreate = () => {
    setCreateOpen(true);
  };

  const launchAgent = async (ag: AgentItem) => {
    const blockedReason = runBlockedReason(ag, lang, { isAdmin });
    if (blockedReason) {
      setActionError(blockedReason);
      return false;
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
        return true;
      }
      await queryClient.invalidateQueries({ queryKey: ["agents"] });
      return true;
    } catch {
      setResult({
        run_id: 0,
        server_name: localize(lang, "Ошибка запуска", "Run error"),
        status: "failed",
        ai_analysis: localize(lang, "Агент не запустился. Проверьте доступ к серверу и настройки агента.", "The agent did not start. Check server access and agent settings."),
        duration_ms: 0,
        commands_output: [],
      });
      setReportModalOpen(true);
      return false;
    } finally {
      setRunningId(null);
    }
  };

  const onRun = async (ag: AgentItem) => {
    await launchAgent(ag);
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

  // Worker/ops diagnostics are admin-only. No "healthy services" strip —
  // show only when something is actually broken (and only to staff).
  const healthSection = isAdmin ? (
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
  ) : null;

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
            <Button className="gap-1.5 shadow-elev-1" onClick={openCreate}>
              <Plus className="h-4 w-4" />
              {t("agent.new")}
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

      {/* Admin-only: only when workers/runtime have problems (no healthy strip). */}
      {healthSection}

      {actionError ? (
        <div className="rounded-sm border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive shadow-elev-1">
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
        <div className="rounded-sm border border-success/30 bg-success/10 px-4 py-3 text-sm text-foreground shadow-elev-1">
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
        <div className="flex items-center gap-3 rounded-sm border border-border bg-card px-4 py-3 shadow-elev-1">
          <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-sm border ${result.status === "completed" ? "border-success/30 bg-success/15 text-success" : "border-destructive/30 bg-destructive/15 text-destructive"}`}>
            {result.status === "completed" ? <CheckCircle2 className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium text-foreground">{result.server_name}</div>
            <div className="text-xs text-muted-foreground">{result.status} · {formatDuration(result.duration_ms)}</div>
          </div>
          {result.run_id > 0 ? (
            <Button size="sm" variant="outline" className="h-9 shrink-0 gap-1.5 text-xs" onClick={() => navigate(`/agents/run/${result.run_id}`)}>
              <FileText className="h-3.5 w-3.5" /> {t("agent.report")}
            </Button>
          ) : (
            <Button size="sm" className="h-9 shrink-0 gap-1.5 text-xs" onClick={() => setReportModalOpen(true)}>
              <FileText className="h-3.5 w-3.5" /> {t("agent.report")}
            </Button>
          )}
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
        isAdmin={isAdmin}
        createdAgentId={createdAgentId}
        runningId={runningId}
        stoppingId={stoppingId}
        activeRunByAgentId={activeRunByAgentId}
        onCreate={openCreate}
        onEdit={setEditingAgent}
        onRun={onRun}
        onStop={onStop}
        onDelete={onDelete}
        onTogglePause={onTogglePause}
      />

      <CreateAgentDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSaved={async ({ id, mode, action, runAfterSave }) => {
          setModeFilter("all");
          setCreatedAgentId(id);
          setCreateOpen(false);
          await queryClient.invalidateQueries({ queryKey: ["agents", "list"] });

          if (action === "create" && runAfterSave) {
            const refreshed = await fetchAgents();
            const created = refreshed.agents.find((agent) => agent.id === id);
            if (created) {
              await launchAgent(created);
            } else {
              // Fallback shell if list is momentarily stale
              await launchAgent({
                id,
                name: "",
                mode,
                mode_display: mode,
                agent_type: "custom",
                agent_type_display: "custom",
                server_count: 0,
                server_ids: [],
                server_names: [],
                schedule_minutes: 0,
                schedule_config: { mode: "manual" },
                is_enabled: true,
                commands: [],
                ai_prompt: "",
                goal: "",
                system_prompt: "",
                max_iterations: 40,
                allow_multi_server: false,
                tools_config: {},
                sudo_policy: "disabled",
                stop_conditions: [],
                skill_slugs: [],
                input_artifacts: [],
                report_delivery: {},
                session_timeout_seconds: 1200,
                max_connections: 5,
                last_run_at: null,
                last_run_status: null,
                last_run_id: null,
                active_run_id: null,
              });
            }
          }

          window.setTimeout(() => setCreatedAgentId((current) => (current === id ? null : current)), 8000);
        }}
      />
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
