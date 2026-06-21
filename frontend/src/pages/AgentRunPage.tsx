import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  Bot,
  CheckCircle2,
  FileText,
  Layers,
  RefreshCw,
  RotateCcw,
  Square,
  Terminal,
} from "lucide-react";

import {
  approvePipelinePlan,
  fetchAgentRunDetail,
  fetchAgentRunEvents,
  fetchAgentRunLog,
  replyToAgent,
  stopAgent,
  type AgentRunDetail,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";

import { formatCompactDateTime, formatDuration } from "./agent-run/formatters";
import { PipelineFlowView } from "./agent-run/PipelineFlowView";
import { ReportView } from "./agent-run/ReportView";
import { StatusBadge } from "./agent-run/StatusBadge";
import { TimelineView } from "./agent-run/TimelineView";
import type { AgentRunTab } from "./agent-run/types";

export default function AgentRunPage() {
  const { runId } = useParams<{ runId: string }>();
  const { t } = useI18n();
  const tr = (key: string, vars?: Record<string, string | number>) => {
    let text = t(key);
    if (!vars) return text;
    for (const [name, value] of Object.entries(vars)) {
      text = text.split(`{${name}}`).join(String(value));
    }
    return text;
  };
  const queryClient = useQueryClient();
  const [replyText, setReplyText] = useState("");
  const [sending, setSending] = useState(false);
  const [stopping, setStopping] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [activeTab, setActiveTab] = useState<AgentRunTab>("pipeline");
  const [localPlanTasks, setLocalPlanTasks] = useState<AgentRunDetail["plan_tasks"] | null>(null);
  const [approving, setApproving] = useState(false);
  const [approveError, setApproveError] = useState<string | null>(null);

  const rid = parseInt(runId || "0", 10);

  const { data: runData, isLoading, isError, error } = useQuery({
    queryKey: ["agent-run", rid],
    queryFn: () => fetchAgentRunDetail(rid),
    enabled: rid > 0,
    retry: false,
    refetchInterval: 3000,
  });

  const run = runData?.run;
  const isMulti = run?.agent_mode === "multi";
  const isPlanReview = run?.status === "plan_review";
  const isActive = Boolean(run && ["running", "paused", "waiting", "pending"].includes(run.status));
  const hasReport = Boolean(run && (run.final_report || run.ai_analysis));

  const { data: logData } = useQuery({
    queryKey: ["agent-run-log", rid],
    queryFn: () => fetchAgentRunLog(rid),
    enabled: rid > 0 && Boolean(run),
    retry: false,
    refetchInterval: 2000,
  });
  const { data: eventsData } = useQuery({
    queryKey: ["agent-run-events", rid],
    queryFn: () => fetchAgentRunEvents(rid, 200),
    enabled: rid > 0 && Boolean(run),
    retry: false,
    refetchInterval: isActive ? 2000 : 5000,
  });

  const events = eventsData?.events || [];
  const serverPlanTasks = logData?.plan_tasks || run?.plan_tasks || [];
  const serverPlanTasksSnapshot = JSON.stringify(serverPlanTasks);
  const localPlanTasksSnapshot = localPlanTasks ? JSON.stringify(localPlanTasks) : "";
  // localPlanTasks overrides server data only until fresh server state diverges.
  const planTasks = localPlanTasks ?? serverPlanTasks;

  useEffect(() => {
    if (run && !isActive && !isPlanReview && hasReport) {
      setActiveTab("report");
    } else if (run && isMulti) {
      setActiveTab("pipeline");
    }
  }, [hasReport, isActive, isMulti, isPlanReview, run]);

  useEffect(() => {
    setLocalPlanTasks(null);
  }, [rid]);

  useEffect(() => {
    if (localPlanTasks === null) return;
    if (!serverPlanTasksSnapshot) return;
    if (serverPlanTasksSnapshot !== localPlanTasksSnapshot) {
      setLocalPlanTasks(null);
    }
  }, [localPlanTasks, localPlanTasksSnapshot, serverPlanTasksSnapshot]);

  useEffect(() => {
    if (autoScroll && logEndRef.current && activeTab === "pipeline") {
      logEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [planTasks.length, autoScroll, activeTab]);

  const refreshRunQueries = async () => {
    await queryClient.invalidateQueries({ queryKey: ["agent-run", rid] });
    await queryClient.invalidateQueries({ queryKey: ["agent-run-log", rid] });
    await queryClient.invalidateQueries({ queryKey: ["agent-run-events", rid] });
  };

  const onApprovePlan = async () => {
    if (!run) return;
    setApproving(true);
    setApproveError(null);
    try {
      await approvePipelinePlan(run.id);
      await refreshRunQueries();
    } catch (err: unknown) {
      setApproveError(err instanceof Error ? err.message : t("run.approve_error"));
    } finally {
      setApproving(false);
    }
  };

  const onStop = async () => {
    if (!run) return;
    setStopping(true);
    try {
      await stopAgent(run.agent_id, run.id);
      await refreshRunQueries();
    } finally {
      setStopping(false);
    }
  };

  const onReply = async () => {
    if (!replyText.trim()) return;
    setSending(true);
    try {
      await replyToAgent(rid, replyText.trim());
      setReplyText("");
      await queryClient.invalidateQueries({ queryKey: ["agent-run", rid] });
      await queryClient.invalidateQueries({ queryKey: ["agent-run-events", rid] });
    } finally {
      setSending(false);
    }
  };

  if (rid <= 0) {
    return (
      <div className="flex h-[calc(100vh-3.5rem)] items-center justify-center bg-background px-4">
        <div className="rounded-2xl border border-border/70 bg-card/70 px-5 py-4 text-sm text-muted-foreground shadow-[0_18px_48px_rgba(0,0,0,0.18)]">
          {t("run.invalid_id")}
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex h-[calc(100vh-3.5rem)] items-center justify-center bg-background px-4">
        <div className="flex min-w-[260px] items-center gap-3 rounded-2xl border border-border/70 bg-card/70 px-4 py-3 text-sm text-muted-foreground shadow-[0_18px_48px_rgba(0,0,0,0.18)]">
          <RefreshCw className="h-4 w-4 animate-spin" />
          <span>{t("loading")}</span>
        </div>
      </div>
    );
  }

  if (isError || !run) {
    const message = error instanceof Error ? error.message : t("run.not_found");
    return (
      <div className="flex h-[calc(100vh-3.5rem)] items-center justify-center bg-background px-4">
        <div className="max-w-md rounded-2xl border border-border/70 bg-card/70 px-5 py-4 text-sm text-muted-foreground shadow-[0_18px_48px_rgba(0,0,0,0.18)]">
          <div className="mb-2 flex items-center gap-2 text-foreground">
            <AlertTriangle className="h-4 w-4 text-amber-400" />
            <span className="font-medium">{t("run.not_found_title")}</span>
          </div>
          <p>{message}</p>
          <div className="mt-4">
            <Link to="/agents">
              <Button size="sm" variant="outline" className="gap-1.5">
                <ArrowLeft className="h-3.5 w-3.5" />
                {t("run.back_to_agents")}
              </Button>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const elapsed = run.duration_ms || (Date.now() - new Date(run.started_at).getTime());
  const doneTasks = planTasks.filter((task) => task.status === "done").length;
  const failedTasks = planTasks.filter((task) => task.status === "failed").length;
  const runningTasks = planTasks.filter((task) => task.status === "running").length;
  const progressPercent = planTasks.length > 0 ? (doneTasks / planTasks.length) * 100 : 0;
  const connectedServerNames =
    run.connected_servers.length > 0
      ? run.connected_servers.map((server) => server.server_name)
      : run.server_name
        ? [run.server_name]
        : [];

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col bg-background">
      <div className="border-b border-border/70 bg-background/95 backdrop-blur">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-3 px-4 py-3 sm:px-6">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="min-w-0 flex items-center gap-2">
              <Link to="/agents">
                <Button size="sm" variant="ghost" className="h-8 rounded-lg px-2 text-muted-foreground">
                  <ArrowLeft className="h-3.5 w-3.5" />
                </Button>
              </Link>
              <div className="min-w-0 flex items-center gap-2">
                <Bot className="h-4 w-4 shrink-0 text-primary" />
                <h1 className="truncate text-lg font-semibold tracking-[-0.03em] text-foreground">{run.agent_name}</h1>
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-end gap-2">
              <StatusBadge status={run.status} />
              {isMulti ? (
                <span className="inline-flex min-h-7 items-center gap-1.5 rounded-md border border-[color:var(--wt-ai)] bg-[color:rgb(155_135_245_/_0.10)] px-2.5 py-1 text-xs font-medium leading-4 text-[color:var(--wt-ai)]">
                  <Layers className="h-3 w-3" />
                  {t("run.mode_pipeline")}
                </span>
              ) : null}
              <div className="rounded-xl border border-border/70 bg-card/70 p-0.5">
                {isMulti ? (
                  <button
                    onClick={() => setActiveTab("pipeline")}
                    className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors ${
                      activeTab === "pipeline" ? "bg-background text-foreground" : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    <span className="inline-flex items-center gap-1.5">
                      <Layers className="h-3.5 w-3.5" />
                      {t("run.tab_pipeline")}
                      {isActive || isPlanReview ? <span className="h-1.5 w-1.5 rounded-full bg-violet-400" /> : null}
                    </span>
                  </button>
                ) : null}
                <button
                  onClick={() => setActiveTab("timeline")}
                  className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors ${
                    activeTab === "timeline" ? "bg-background text-foreground" : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <span className="inline-flex items-center gap-1.5">
                    <Activity className="h-3.5 w-3.5" />
                    {t("run.tab_timeline")}
                    {events.length > 0 ? <span className="h-1.5 w-1.5 rounded-full bg-sky-400" /> : null}
                  </span>
                </button>
                <button
                  onClick={() => setActiveTab("report")}
                  className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors ${
                    activeTab === "report" ? "bg-background text-foreground" : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <span className="inline-flex items-center gap-1.5">
                    <FileText className="h-3.5 w-3.5" />
                    {t("run.tab_report")}
                    {hasReport && !isActive ? <CheckCircle2 className="h-3 w-3 text-emerald-300" /> : null}
                  </span>
                </button>
              </div>
              {isActive ? (
                <Button
                  size="sm"
                  variant="destructive"
                  className="h-8 rounded-lg px-3 text-xs"
                  onClick={onStop}
                  disabled={stopping}
                >
                  {stopping ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Square className="h-3.5 w-3.5" />}
                  {t("agent.stop")}
                </Button>
              ) : null}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            <span>{formatDuration(elapsed)}</span>
            <span className="text-muted-foreground/40">·</span>
            <span>{isMulti ? `${planTasks.length} ${t("run.metric_tasks")}` : `${run.total_iterations} ${t("run.metric_iterations")}`}</span>
            <span className="text-muted-foreground/40">·</span>
            <span>{connectedServerNames.length} ${t("run.metric_servers")}</span>
            <span className="text-muted-foreground/40">·</span>
            <span>{formatCompactDateTime(run.started_at)}</span>

            {connectedServerNames.length > 0 ? (
              <>
                <span className="text-muted-foreground/40">·</span>
                <div className="flex flex-wrap items-center gap-1">
                  {run.connected_servers.length > 0 ? run.connected_servers.map((server) => (
                    <Link key={server.server_id} to={`/servers/${server.server_id}/terminal`}>
                      <span className="inline-flex min-h-7 items-center gap-1 rounded-md border border-border/70 bg-card/70 px-2 text-xs text-muted-foreground transition-colors hover:border-primary/30 hover:bg-primary/10 hover:text-primary">
                        <Terminal className="h-3 w-3" />
                        {server.server_name}
                      </span>
                    </Link>
                  )) : (
                    <span className="inline-flex min-h-7 items-center gap-1 rounded-md border border-border/70 bg-card/70 px-2 text-xs text-muted-foreground">
                      <Terminal className="h-3 w-3" />
                      {run.server_name}
                    </span>
                  )}
                </div>
              </>
            ) : null}

            {isMulti ? (
              <div className="ml-auto flex items-center gap-2">
                <div className="h-1.5 w-20 overflow-hidden rounded-full bg-card sm:w-28">
                  <div
                    className="h-full rounded-full bg-violet-400 transition-[width]"
                    style={{ width: `${progressPercent}%` }}
                  />
                </div>
                <span className="font-medium text-foreground/80">
                  {doneTasks}/{planTasks.length}
                </span>
                {runningTasks > 0 ? <span className="text-info">{tr("run.progress_running", { count: runningTasks })}</span> : null}
                {failedTasks > 0 ? <span className="text-destructive">{tr("run.progress_failed", { count: failedTasks })}</span> : null}
                <button
                  type="button"
                  onClick={() => setAutoScroll((current) => !current)}
                  className={`inline-flex h-6 w-6 items-center justify-center rounded-full border transition-colors ${
                    autoScroll
                      ? "border-violet-500/30 bg-violet-500/10 text-violet-300"
                      : "border-border/70 bg-card/60 text-muted-foreground hover:text-foreground"
                  }`}
                  title={autoScroll ? t("run.autoscroll_on") : t("run.autoscroll_off")}
                  aria-label={autoScroll ? t("run.autoscroll_off") : t("run.autoscroll_on")}
                >
                  <RotateCcw className="h-3 w-3" />
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden bg-background">
        {activeTab === "pipeline" && isMulti ? (
          <div className="h-full overflow-y-auto">
            <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 px-4 py-5 sm:px-6">
              {isPlanReview ? (
                <div className="rounded-lg border border-warning/35 bg-warning/10 p-4 sm:p-5">
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div className="flex min-w-0 gap-3">
                      <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-amber-500/25 bg-background/40">
                        <AlertTriangle className="h-5 w-5 text-amber-300" />
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-warning">{t("run.plan_review_title")}</p>
                        <p className="mt-1 text-sm leading-6 text-foreground/85">
                          {t("run.plan_review_desc")}
                        </p>
                        {approveError ? <p className="mt-2 text-sm text-destructive">{approveError}</p> : null}
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        className="h-10 px-4"
                        onClick={onApprovePlan}
                        disabled={approving}
                      >
                        {approving ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                        {approving ? t("run.approving") : t("run.approve")}
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-10 border-destructive/35 px-4 text-destructive hover:bg-destructive/10"
                        onClick={onStop}
                        disabled={stopping}
                      >
                        <Square className="h-3.5 w-3.5" />
                        {t("run.cancel")}
                      </Button>
                    </div>
                  </div>
                </div>
              ) : null}
              <PipelineFlowView
                run={run}
                planTasks={planTasks}
                isActive={!!isActive || isPlanReview}
                pendingQuestion={run.pending_question}
                replyText={replyText}
                setReplyText={setReplyText}
                sending={sending}
                onReply={onReply}
                onTasksUpdated={(tasks) => {
                  setLocalPlanTasks(tasks);
                  queryClient.invalidateQueries({ queryKey: ["agent-run", rid] });
                  queryClient.invalidateQueries({ queryKey: ["agent-run-log", rid] });
                }}
              />
              <div ref={logEndRef} />
            </div>
          </div>
        ) : activeTab === "timeline" ? (
          <div className="h-full overflow-y-auto">
            <TimelineView run={run} events={events} />
          </div>
        ) : (
          <div className="h-full overflow-y-auto">
            <ReportView run={run} t={t} />
          </div>
        )}
      </div>
    </div>
  );
}
