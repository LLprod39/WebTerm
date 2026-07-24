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
import { notifyWithUndo } from "@/lib/notify-undo";
import { isAgentScheduled } from "./agents-page/agentPageUtils";
import { runBlockedReason } from "./agents-page/agentRuntimeShared";
import type { CreateAgentSavedPayload } from "./agents-page/createAgentDialogTypes";

export function useAgentsPageController() {
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
      // All modes return immediately with a queued run_id; execution is async.
      const res = await runAgent(ag.id);
      const runId = res.run_id || res.runs?.[0]?.run_id;
      await queryClient.invalidateQueries({ queryKey: ["agents"] });
      if (runId) {
        navigate(`/agents/run/${runId}`);
        return true;
      }
      if (res.runs?.length > 0) {
        setResult(res.runs[0]);
        setReportModalOpen(true);
      }
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

    const runId = ag.active_run_id;
    setActionError(null);
    setActionNotice(null);
    // Delayed stop with Undo (5s) — feels safer than an immediate kill.
    notifyWithUndo({
      lang,
      title: localize(lang, `Остановка «${ag.name}»…`, `Stopping “${ag.name}”…`),
      description: localize(lang, "Нажмите «Отменить», чтобы продолжить прогон", "Click Undo to keep the run going"),
      durationMs: 5000,
      onCommit: async () => {
        setStoppingId(ag.id);
        try {
          await stopAgent(ag.id, runId);
          await queryClient.invalidateQueries({ queryKey: ["agents"] });
          setActionNotice(localize(lang, `Агент «${ag.name}» остановлен`, `Agent “${ag.name}” stopped`));
        } catch {
          setActionError(localize(lang, "Не удалось остановить активный запуск.", "Failed to stop the active run."));
        } finally {
          setStoppingId(null);
        }
      },
      onUndo: () => {
        setActionNotice(localize(lang, `Остановка «${ag.name}» отменена`, `Stop of “${ag.name}” cancelled`));
      },
    });
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

  const onCreateSaved = async ({ id, mode, action, runAfterSave }: CreateAgentSavedPayload) => {
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
  };

  const onEditSaved = async ({ id }: CreateAgentSavedPayload) => {
    setCreatedAgentId(id);
    setEditingAgent(null);
    await queryClient.invalidateQueries({ queryKey: ["agents", "list"] });
    window.setTimeout(() => setCreatedAgentId((current) => (current === id ? null : current)), 8000);
  };

  return {
    t,
    lang,
    queryClient,
    navigate,
    modeFilter,
    setModeFilter,
    createOpen,
    setCreateOpen,
    editingAgent,
    setEditingAgent,
    createdAgentId,
    runningId,
    stoppingId,
    actionError,
    setActionError,
    actionNotice,
    setActionNotice,
    cleaningStale,
    result,
    setResult,
    reportModalOpen,
    setReportModalOpen,
    deleteTarget,
    setDeleteTarget,
    isLoading,
    isAdmin,
    allAgents,
    agents,
    activeAgents,
    scheduledAgents,
    pausedAgents,
    failedAgents,
    executionWarning,
    executionReadiness,
    runtimeOverview,
    activeRunByAgentId,
    showRuntimeOverview,
    scheduledWorker,
    showScheduledWorker,
    openCreate,
    onRun,
    onStop,
    onCleanupStale,
    onDelete,
    onTogglePause,
    copyExecutionCommand,
    confirmDeleteAgent,
    onCreateSaved,
    onEditSaved,
  };
}
