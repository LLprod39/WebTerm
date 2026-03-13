import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams, Link } from "react-router-dom";
import { useState, useEffect, useRef } from "react";
import {
  fetchAgentRunDetail,
  fetchAgentRunLog,
  replyToAgent,
  stopAgent,
  updatePipelineTask,
  aiRefinePipelineTask,
  approvePipelinePlan,
  type AgentRunDetail,
} from "@/lib/api";
import {
  Bot, ArrowLeft, Square, Send, Brain, Terminal,
  CheckCircle2, XCircle, Clock, Activity, MessageSquare,
  FileText, AlertTriangle, ChevronRight, RefreshCw,
  Target, Cpu, ChevronDown, ChevronUp, SkipForward,
  RotateCcw, HelpCircle, Layers, Pencil, Trash2, Sparkles, X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import ReactMarkdown from "react-markdown";
import { useI18n } from "@/lib/i18n";

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const secs = Math.floor(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  const remSecs = secs % 60;
  if (mins < 60) return `${mins}m ${remSecs}s`;
  const hrs = Math.floor(mins / 60);
  return `${hrs}h ${mins % 60}m`;
}

function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function formatCompactDateTime(value?: string | null): string {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function statusLabel(status: string): string {
  switch (status) {
    case "plan_review":
      return "review";
    default:
      return status;
  }
}

function statusClasses(status: string): string {
  switch (status) {
    case "running":
      return "border-sky-500/30 bg-sky-500/12 text-sky-300";
    case "paused":
      return "border-amber-500/30 bg-amber-500/12 text-amber-300";
    case "waiting":
      return "border-orange-500/30 bg-orange-500/12 text-orange-300";
    case "plan_review":
      return "border-violet-500/30 bg-violet-500/12 text-violet-300";
    case "completed":
      return "border-emerald-500/30 bg-emerald-500/12 text-emerald-300";
    case "failed":
      return "border-red-500/30 bg-red-500/12 text-red-300";
    case "stopped":
      return "border-border/70 bg-secondary/45 text-muted-foreground";
    default:
      return "border-border/70 bg-secondary/45 text-muted-foreground";
  }
}

export default function AgentRunPage() {
  const { runId } = useParams<{ runId: string }>();
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [replyText, setReplyText] = useState("");
  const [sending, setSending] = useState(false);
  const [stopping, setStopping] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);
  const [activeTab, setActiveTab] = useState<"pipeline" | "report">("pipeline");
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

  const { data: logData } = useQuery({
    queryKey: ["agent-run-log", rid],
    queryFn: () => fetchAgentRunLog(rid),
    enabled: rid > 0 && Boolean(runData?.run),
    retry: false,
    refetchInterval: 2000,
  });

  const run = runData?.run;
  const serverPlanTasks = logData?.plan_tasks || run?.plan_tasks || [];
  const serverPlanTasksSnapshot = JSON.stringify(serverPlanTasks);
  const localPlanTasksSnapshot = localPlanTasks ? JSON.stringify(localPlanTasks) : "";
  // localPlanTasks overrides server data only until fresh server state diverges.
  const planTasks = localPlanTasks ?? serverPlanTasks;
  const isMulti = run?.agent_mode === "multi";
  const isPlanReview = run?.status === "plan_review";
  const isActive = run && ["running", "paused", "waiting", "pending"].includes(run.status);
  const hasReport = run && (run.final_report || run.ai_analysis);

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

  const onApprovePlan = async () => {
    if (!run) return;
    setApproving(true);
    setApproveError(null);
    try {
      await approvePipelinePlan(run.id);
      await queryClient.invalidateQueries({ queryKey: ["agent-run", rid] });
      await queryClient.invalidateQueries({ queryKey: ["agent-run-log", rid] });
    } catch (err: unknown) {
      setApproveError(err instanceof Error ? err.message : "Ошибка запуска выполнения");
    } finally {
      setApproving(false);
    }
  };

  useEffect(() => {
    if (autoScroll && logEndRef.current && activeTab === "pipeline") {
      logEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [planTasks.length, autoScroll, activeTab]);

  const onStop = async () => {
    if (!run) return;
    setStopping(true);
    try {
      await stopAgent(run.agent_id, run.id);
      await queryClient.invalidateQueries({ queryKey: ["agent-run", rid] });
      await queryClient.invalidateQueries({ queryKey: ["agent-run-log", rid] });
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
    } finally {
      setSending(false);
    }
  };

  if (rid <= 0) {
    return (
      <div className="flex h-[calc(100vh-3.5rem)] items-center justify-center bg-background px-4">
        <div className="rounded-2xl border border-border/70 bg-card/70 px-5 py-4 text-sm text-muted-foreground shadow-[0_18px_48px_rgba(0,0,0,0.18)]">
          Некорректный идентификатор запуска.
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
    const message = error instanceof Error ? error.message : "Запуск агента не найден или больше недоступен.";
    return (
      <div className="flex h-[calc(100vh-3.5rem)] items-center justify-center bg-background px-4">
        <div className="max-w-md rounded-2xl border border-border/70 bg-card/70 px-5 py-4 text-sm text-muted-foreground shadow-[0_18px_48px_rgba(0,0,0,0.18)]">
          <div className="mb-2 flex items-center gap-2 text-foreground">
            <AlertTriangle className="h-4 w-4 text-amber-400" />
            <span className="font-medium">Запуск не найден</span>
          </div>
          <p>{message}</p>
          <div className="mt-4">
            <Link to="/agents">
              <Button size="sm" variant="outline" className="gap-1.5">
                <ArrowLeft className="h-3.5 w-3.5" />
                К списку агентов
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
    run.connected_servers.length > 0 ? run.connected_servers.map((server) => server.server_name) : run.server_name ? [run.server_name] : [];

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
                <span className="inline-flex h-7 items-center gap-1 rounded-full border border-violet-500/25 bg-violet-500/10 px-2.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-violet-300">
                  <Layers className="h-3 w-3" />
                  Pipeline
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
                      Pipeline
                      {(isActive || isPlanReview) ? <span className="h-1.5 w-1.5 rounded-full bg-violet-400" /> : null}
                    </span>
                  </button>
                ) : null}
                <button
                  onClick={() => setActiveTab("report")}
                  className={`rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors ${
                    activeTab === "report" ? "bg-background text-foreground" : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  <span className="inline-flex items-center gap-1.5">
                    <FileText className="h-3.5 w-3.5" />
                    {t("agent.report")}
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
            <span>{isMulti ? `${planTasks.length} tasks` : `${run.total_iterations} iterations`}</span>
            <span className="text-muted-foreground/40">·</span>
            <span>{connectedServerNames.length} servers</span>
            <span className="text-muted-foreground/40">·</span>
            <span>{formatCompactDateTime(run.started_at)}</span>

            {connectedServerNames.length > 0 ? (
              <>
                <span className="text-muted-foreground/40">·</span>
                <div className="flex flex-wrap items-center gap-1">
                  {run.connected_servers.length > 0 ? run.connected_servers.map((server) => (
                    <Link key={server.server_id} to={`/servers/${server.server_id}/terminal`}>
                      <span className="inline-flex h-6 items-center gap-1 rounded-full border border-border/70 bg-card/70 px-2 text-[11px] text-muted-foreground transition-colors hover:border-primary/30 hover:bg-primary/10 hover:text-primary">
                        <Terminal className="h-3 w-3" />
                        {server.server_name}
                      </span>
                    </Link>
                  )) : (
                    <span className="inline-flex h-6 items-center gap-1 rounded-full border border-border/70 bg-card/70 px-2 text-[11px] text-muted-foreground">
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
                {runningTasks > 0 ? <span className="text-sky-300">{runningTasks} running</span> : null}
                {failedTasks > 0 ? <span className="text-red-300">{failedTasks} failed</span> : null}
                <button
                  type="button"
                  onClick={() => setAutoScroll((current) => !current)}
                  className={`inline-flex h-6 w-6 items-center justify-center rounded-full border transition-colors ${
                    autoScroll
                      ? "border-violet-500/30 bg-violet-500/10 text-violet-300"
                      : "border-border/70 bg-card/60 text-muted-foreground hover:text-foreground"
                  }`}
                  title={autoScroll ? "Автопрокрутка включена" : "Автопрокрутка выключена"}
                  aria-label={autoScroll ? "Выключить автопрокрутку" : "Включить автопрокрутку"}
                >
                  <RotateCcw className="h-3 w-3" />
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.03),transparent_48%),linear-gradient(180deg,rgba(255,255,255,0.02),transparent_40%)]">
        {activeTab === "pipeline" && isMulti ? (
          <div className="h-full overflow-y-auto">
            <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 px-4 py-5 sm:px-6">
              {isPlanReview && (
                <div className="rounded-[24px] border border-amber-500/30 bg-amber-500/10 p-4 sm:p-5">
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div className="flex min-w-0 gap-3">
                      <div className="mt-0.5 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-amber-500/25 bg-background/40">
                        <AlertTriangle className="h-5 w-5 text-amber-300" />
                      </div>
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-amber-200">Ожидание подтверждения плана</p>
                        <p className="mt-1 text-sm leading-6 text-amber-50/75">
                          Оркестратор составил план из {planTasks.length} задач. Проверьте состав, при необходимости
                          отредактируйте шаги и запустите выполнение.
                        </p>
                        {approveError ? <p className="mt-2 text-sm text-red-300">{approveError}</p> : null}
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-2">
                        <Button
                          size="sm"
                          className="h-10 rounded-xl bg-emerald-600 px-4 text-white hover:bg-emerald-500"
                          onClick={onApprovePlan}
                          disabled={approving}
                        >
                          {approving ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                          {approving ? "Запускаю…" : "Запустить выполнение"}
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-10 rounded-xl border-red-500/30 px-4 text-red-300 hover:bg-red-500/10 hover:text-red-200"
                          onClick={onStop}
                          disabled={stopping}
                        >
                          <Square className="h-3.5 w-3.5" />
                          Отменить
                        </Button>
                      </div>
                    </div>
                </div>
              )}
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
        ) : (
          <div className="h-full overflow-y-auto">
            <ReportView run={run} t={t} />
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Task Edit Modal
// ---------------------------------------------------------------------------

type PlanTask = AgentRunDetail["plan_tasks"][number];

function TaskEditModal({
  task,
  runId,
  onClose,
  onSaved,
}: {
  task: PlanTask;
  runId: number;
  onClose: () => void;
  onSaved: (tasks: PlanTask[]) => void;
}) {
  const [name, setName] = useState(task.name);
  const [description, setDescription] = useState(task.description);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [aiMsg, setAiMsg] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState("");
  const aiInputRef = useRef<HTMLInputElement>(null);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await updatePipelineTask(runId, task.id, { action: "update", name, description });
      onSaved(res.plan_tasks);
      onClose();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Ошибка сохранения");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`Удалить задачу "${task.name}"?`)) return;
    setDeleting(true);
    try {
      const res = await updatePipelineTask(runId, task.id, { action: "delete" });
      onSaved(res.plan_tasks);
      onClose();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Ошибка удаления");
    } finally {
      setDeleting(false);
    }
  };

  const handleAiRefine = async () => {
    if (!aiMsg.trim()) return;
    setAiLoading(true);
    setAiError("");
    try {
      const res = await aiRefinePipelineTask(runId, task.id, aiMsg.trim());
      if (!res.success) {
        setAiError(res.error || "Ошибка ИИ");
        return;
      }
      setName(res.task.name);
      setDescription(res.task.description);
      setAiMsg("");
      onSaved(res.plan_tasks);
    } catch (e: unknown) {
      setAiError(e instanceof Error ? e.message : "Ошибка ИИ");
    } finally {
      setAiLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4 backdrop-blur-sm">
      <div className="w-full max-w-2xl overflow-hidden rounded-[28px] border border-border/70 bg-card/95 shadow-[0_28px_80px_rgba(0,0,0,0.38)]">
        <div className="flex items-start justify-between gap-4 border-b border-border/70 px-5 py-4">
          <div>
            <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Task editor</div>
            <div className="mt-1 text-lg font-semibold text-foreground">Редактировать задачу</div>
            <p className="mt-1 text-sm text-muted-foreground">Измените формулировку шага или уточните его через AI-подсказку.</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-xl border border-border/70 p-2 text-muted-foreground transition-colors hover:border-border hover:bg-background/80 hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="grid gap-5 px-5 py-5 lg:grid-cols-[minmax(0,1fr)_280px]">
          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground">Название</label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="h-11 rounded-2xl border-border/70 bg-background/70"
                placeholder="Название задачи"
              />
            </div>
            <div className="space-y-2">
              <label className="text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground">Описание</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="h-48 w-full resize-none rounded-[22px] border border-border/70 bg-background/70 px-4 py-3 text-sm text-foreground outline-none transition-colors focus:border-violet-500/40 focus:ring-2 focus:ring-violet-500/20"
                placeholder="Опишите что нужно сделать..."
              />
            </div>
          </div>

          <div className="rounded-[24px] border border-violet-500/20 bg-violet-500/8 p-4">
            <div className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.18em] text-violet-300">
              <Sparkles className="h-3.5 w-3.5" />
              AI assistant
            </div>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Опишите изменение простым текстом. AI обновит название и описание задачи, не ломая текущий план.
            </p>
            {aiError ? (
              <div className="mt-3 rounded-2xl border border-red-500/25 bg-red-500/10 px-3 py-2 text-xs text-red-300">
                {aiError}
              </div>
            ) : null}
            <div className="mt-4 space-y-3">
              <Input
                ref={aiInputRef}
                value={aiMsg}
                onChange={(e) => setAiMsg(e.target.value)}
                placeholder="Напр: добавь проверку дискового пространства"
                className="h-11 rounded-2xl border-violet-500/20 bg-background/70 text-sm"
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleAiRefine()}
                disabled={aiLoading}
              />
              <Button
                size="sm"
                className="h-10 w-full rounded-xl bg-violet-600 text-white hover:bg-violet-500"
                onClick={handleAiRefine}
                disabled={aiLoading || !aiMsg.trim()}
              >
                {aiLoading ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                {aiLoading ? "Думает…" : "Применить AI-правку"}
              </Button>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-3 border-t border-border/70 bg-background/35 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <Button
            size="sm"
            variant="destructive"
            className="h-8 px-3 gap-1.5 text-xs"
            onClick={handleDelete}
            disabled={deleting || saving}
          >
            {deleting ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
            Удалить задачу
          </Button>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="ghost" className="h-10 rounded-xl px-4" onClick={onClose} disabled={saving}>
              Отмена
            </Button>
            <Button
              size="sm"
              className="h-10 rounded-xl bg-primary px-4 text-primary-foreground"
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
              Сохранить
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pipeline Flow View (n8n-style vertical chain)
// ---------------------------------------------------------------------------

function PipelineFlowView({
  run,
  planTasks,
  isActive,
  pendingQuestion,
  replyText,
  setReplyText,
  sending,
  onReply,
  onTasksUpdated,
}: {
  run: AgentRunDetail;
  planTasks: PlanTask[];
  isActive: boolean;
  pendingQuestion: string;
  replyText: string;
  setReplyText: (v: string) => void;
  sending: boolean;
  onReply: () => void;
  onTasksUpdated?: (tasks: PlanTask[]) => void;
}) {
  const goal = run.agent_name;
  const isCompleted = run.status === "completed";
  const isFailed = run.status === "failed";
  const [editingTask, setEditingTask] = useState<PlanTask | null>(null);

  const canEdit = planTasks.some(t => t.status === "pending");

  return (
    <div className="rounded-[28px] border border-border/70 bg-card/55 shadow-[0_22px_64px_rgba(0,0,0,0.18)]">
      {editingTask ? (
        <TaskEditModal
          task={editingTask}
          runId={run.id}
          onClose={() => setEditingTask(null)}
          onSaved={(tasks) => {
            setEditingTask(null);
            onTasksUpdated?.(tasks);
          }}
        />
      ) : null}

      <div className="border-b border-border/70 px-5 py-5">
        <div className="grid gap-3 lg:grid-cols-3">
          <div className="rounded-[22px] border border-border/70 bg-background/55 p-4">
            <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Goal</div>
            <div className="mt-2 flex items-start gap-3">
              <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl border border-sky-500/20 bg-sky-500/10">
                <Target className="h-4 w-4 text-sky-300" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground">{run.agent_name}</p>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">{(run as { goal?: string }).goal || goal}</p>
              </div>
            </div>
          </div>
          <div className="rounded-[22px] border border-border/70 bg-background/55 p-4">
            <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Plan state</div>
            <div className="mt-2 flex items-start gap-3">
              <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl border border-violet-500/20 bg-violet-500/10">
                <Brain className="h-4 w-4 text-violet-300" />
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground">
                  {planTasks.length > 0 ? `Создано ${planTasks.length} задач` : "Оркестратор готовит план"}
                </p>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">
                  {canEdit
                    ? "Пока шаги не начали выполняться, их можно уточнять и перестраивать."
                    : "Сейчас отображается живая последовательность исполнения и решений оркестратора."}
                </p>
              </div>
            </div>
          </div>
          <div className="rounded-[22px] border border-border/70 bg-background/55 p-4">
            <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Run signal</div>
            <div className="mt-2 flex items-start gap-3">
              <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl border border-border/70 bg-card/70">
                {isFailed ? (
                  <AlertTriangle className="h-4 w-4 text-red-300" />
                ) : isCompleted ? (
                  <CheckCircle2 className="h-4 w-4 text-emerald-300" />
                ) : (
                  <Activity className="h-4 w-4 text-primary" />
                )}
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-foreground">
                  {isFailed ? "Требует внимания" : isCompleted ? "Завершено" : "В работе"}
                </p>
                <p className="mt-1 text-sm leading-6 text-muted-foreground">
                  {isFailed
                    ? "На одной из стадий возникла ошибка. Проверьте шаги и финальный отчёт."
                    : isCompleted
                      ? "План отработан. Можно перейти к итоговому отчёту и результатам."
                      : "Лента ниже показывает текущее состояние задач и наблюдения оркестратора."}
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="px-4 py-5 sm:px-6">
        <div className="mx-auto max-w-3xl">
          <FlowNode icon={<Target className="h-4 w-4 text-sky-300" />} label="Goal" title={run.agent_name} color="blue" status="done">
            <p className="mt-2 text-sm leading-6 text-muted-foreground">{(run as { goal?: string }).goal || goal}</p>
          </FlowNode>

          <FlowConnector />

          <FlowNode
            icon={<Brain className="h-4 w-4 text-violet-300" />}
            label="Orchestrator"
            title="Планирование"
            color="violet"
            status={planTasks.length > 0 ? "done" : isActive ? "running" : "pending"}
          >
            {planTasks.length > 0 ? (
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <p className="text-sm text-muted-foreground">Создан план из {planTasks.length} задач</p>
                {canEdit ? (
                  <span className="rounded-full border border-violet-500/20 bg-violet-500/10 px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.14em] text-violet-300">
                    pending tasks can be edited
                  </span>
                ) : null}
              </div>
            ) : isActive ? (
              <p className="mt-2 text-sm text-violet-300/80">Разбиваю цель на задачи…</p>
            ) : null}
          </FlowNode>

          {planTasks.map((task, idx) => (
            <div key={task.id}>
              <FlowConnector active={task.status === "running"} />
              <TaskNode
                task={task}
                index={idx}
                onEdit={
                  task.status === "pending" || task.status === "failed" || task.status === "skipped"
                    ? () => setEditingTask(task)
                    : undefined
                }
              />
              {task.orchestrator_decision && task.status !== "done" ? (
                <>
                  <FlowConnector thin />
                  <OrchestratorDecisionNode decision={task.orchestrator_decision} />
                </>
              ) : null}
            </div>
          ))}

          {(isCompleted || isFailed || run.final_report) ? (
            <>
              <FlowConnector />
              <FlowNode
                icon={<FileText className="h-4 w-4 text-emerald-300" />}
                label="Synthesis"
                title="Финальный отчёт"
                color="green"
                status={run.final_report ? "done" : isActive ? "running" : "pending"}
              >
                {run.final_report ? (
                  <p className="mt-2 line-clamp-2 text-sm leading-6 text-muted-foreground">{run.final_report.slice(0, 180)}…</p>
                ) : null}
              </FlowNode>
            </>
          ) : null}

          {isActive && planTasks.length > 0 && !planTasks.some((task) => task.status === "running") ? (
            <div className="flex items-center gap-2 py-5 pl-7 text-sm text-muted-foreground">
              <Brain className="h-4 w-4 text-violet-300" />
              <span>Оркестратор анализирует результаты…</span>
            </div>
          ) : null}

          {pendingQuestion ? (
            <div className="mt-5 rounded-[24px] border border-orange-500/25 bg-orange-500/8 p-4">
              <div className="flex items-start gap-3">
                <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl border border-orange-500/20 bg-background/45">
                  <MessageSquare className="h-4 w-4 text-orange-300" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-[10px] uppercase tracking-[0.18em] text-orange-300">Needs input</div>
                  <p className="mt-2 text-sm leading-6 text-foreground">{pendingQuestion}</p>
                  <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                    <Input
                      value={replyText}
                      onChange={(e) => setReplyText(e.target.value)}
                      placeholder="Ваш ответ…"
                      className="h-11 rounded-2xl bg-background/80"
                      onKeyDown={(e) => e.key === "Enter" && onReply()}
                    />
                    <Button size="sm" className="h-11 rounded-2xl px-4" onClick={onReply} disabled={sending}>
                      {sending ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                      Ответить
                    </Button>
                  </div>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Task Node
// ---------------------------------------------------------------------------

function TaskNode({ task, index, onEdit }: { task: PlanTask; index: number; onEdit?: () => void }) {
  const [expanded, setExpanded] = useState(task.status === "running" || task.status === "done");

  useEffect(() => {
    if (task.status === "running") setExpanded(true);
  }, [task.status]);

  const statusConfig = {
    pending: { icon: <Clock className="h-4 w-4 text-muted-foreground" />, color: "gray" as const, label: "В очереди" },
    running: { icon: <RefreshCw className="h-4 w-4 text-blue-400 animate-spin" />, color: "blue" as const, label: "Выполняется" },
    done: { icon: <CheckCircle2 className="h-4 w-4 text-green-400" />, color: "green" as const, label: "Готово" },
    failed: { icon: <XCircle className="h-4 w-4 text-red-400" />, color: "red" as const, label: "Ошибка" },
    skipped: { icon: <SkipForward className="h-4 w-4 text-yellow-400" />, color: "yellow" as const, label: "Пропущено" },
  };

  const cfg = statusConfig[task.status] || statusConfig.pending;

  return (
    <FlowNode
      icon={cfg.icon}
      label={`Задача ${index + 1}`}
      title={task.name}
      color={cfg.color}
      status={task.status as "pending" | "running" | "done" | "failed" | "skipped"}
      expandable
      expanded={expanded}
      onToggle={() => setExpanded(!expanded)}
      badge={cfg.label}
      onEdit={onEdit}
    >
      {expanded && (
        <div className="mt-3 space-y-3">
          <p className="text-sm leading-6 text-muted-foreground">{task.description}</p>

          {task.thought && task.status === "running" && (
            <div className="rounded-2xl border border-violet-500/20 bg-violet-500/8 px-3 py-3">
              <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-[0.18em] text-violet-300">
                <Brain className="h-3 w-3" />
                Thinking
              </div>
              <p className="text-sm leading-6 text-foreground/85">{task.thought}</p>
            </div>
          )}

          {task.iterations && task.iterations.length > 0 && <TaskIterations iterations={task.iterations} />}

          {task.result && (
            <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/8 px-3 py-3">
              <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-[0.18em] text-emerald-300">
                <CheckCircle2 className="h-3 w-3" />
                Result
              </div>
              <p className="whitespace-pre-wrap text-sm leading-6 text-foreground/85">{task.result}</p>
            </div>
          )}

          {task.error && (
            <div className="rounded-2xl border border-red-500/20 bg-red-500/8 px-3 py-3">
              <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-[0.18em] text-red-300">
                <XCircle className="h-3 w-3" />
                Error
              </div>
              <p className="font-mono text-xs leading-6 text-red-200/85">{task.error}</p>
            </div>
          )}
        </div>
      )}
    </FlowNode>
  );
}

// ---------------------------------------------------------------------------
// Task Iterations (collapsed sub-steps inside a task node)
// ---------------------------------------------------------------------------

function TaskIterations({ iterations }: { iterations: PlanTask["iterations"] }) {
  const [show, setShow] = useState(false);
  return (
    <div className="rounded-2xl border border-border/70 bg-background/45 px-3 py-3">
      <button
        onClick={() => setShow(!show)}
        className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        {show ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        {iterations.length} шаг{iterations.length > 1 && iterations.length < 5 ? "а" : "ов"} выполнения
      </button>
      {show && (
        <div className="mt-3 space-y-2 border-l border-border/60 pl-3">
          {iterations.map((it, i) => (
            <div key={i} className="text-[11px]">
              <div className="flex flex-wrap items-center gap-1.5 text-muted-foreground">
                <span className="font-mono text-[10px]">#{it.iteration}</span>
                {it.action && (
                  <span className="rounded-full border border-sky-500/20 bg-sky-500/10 px-2 py-0.5 font-mono text-[10px] text-sky-300">
                    {it.action}
                  </span>
                )}
              </div>
              {it.thought && <p className="mt-1 pl-1 text-foreground/75">{it.thought.slice(0, 200)}</p>}
              {it.observation && (
                <pre className="mt-1 max-h-24 overflow-y-auto rounded-xl bg-card/70 px-3 py-2 font-mono text-[10px] whitespace-pre-wrap text-muted-foreground">
                  {it.observation.slice(0, 500)}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Orchestrator Decision Node
// ---------------------------------------------------------------------------

function OrchestratorDecisionNode({ decision }: { decision: { action: string; reason?: string; message?: string } }) {
  const decisionConfig: Record<string, { icon: React.ReactNode; label: string; color: string }> = {
    retry: { icon: <RotateCcw className="h-3.5 w-3.5 text-amber-300" />, label: "Повтор", color: "text-amber-300" },
    skip: { icon: <SkipForward className="h-3.5 w-3.5 text-muted-foreground" />, label: "Пропустить", color: "text-muted-foreground" },
    ask_user: { icon: <HelpCircle className="h-3.5 w-3.5 text-orange-300" />, label: "Спросить пользователя", color: "text-orange-300" },
    abort: { icon: <XCircle className="h-3.5 w-3.5 text-red-300" />, label: "Прервать пайплайн", color: "text-red-300" },
  };
  const cfg = decisionConfig[decision.action] || decisionConfig.skip;

  return (
    <div className="ml-7 rounded-2xl border border-dashed border-orange-500/25 bg-orange-500/8 px-4 py-3 text-sm">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.18em] text-violet-300">
        <Brain className="h-3.5 w-3.5" />
        Orchestrator decision
      </div>
      <div className={`mt-2 flex items-center gap-2 font-medium ${cfg.color}`}>
        {cfg.icon} {cfg.label}
      </div>
      {(decision.reason || decision.message) && (
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{decision.reason || decision.message}</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Generic flow node
// ---------------------------------------------------------------------------

type FlowColor = "blue" | "green" | "violet" | "red" | "yellow" | "gray";

const colorMap: Record<FlowColor, { border: string; bg: string; label: string; ring: string }> = {
  blue: { border: "border-sky-500/25", bg: "bg-sky-500/8", label: "text-sky-300", ring: "ring-sky-500/20" },
  green: { border: "border-emerald-500/25", bg: "bg-emerald-500/8", label: "text-emerald-300", ring: "ring-emerald-500/20" },
  violet: { border: "border-violet-500/25", bg: "bg-violet-500/8", label: "text-violet-300", ring: "ring-violet-500/20" },
  red: { border: "border-red-500/25", bg: "bg-red-500/8", label: "text-red-300", ring: "ring-red-500/20" },
  yellow: { border: "border-amber-500/25", bg: "bg-amber-500/8", label: "text-amber-300", ring: "ring-amber-500/20" },
  gray: { border: "border-border/70", bg: "bg-background/45", label: "text-muted-foreground", ring: "ring-border/40" },
};

function FlowNode({
  icon,
  label,
  title,
  color,
  status,
  expandable,
  expanded,
  onToggle,
  badge,
  onEdit,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  title: string;
  color: FlowColor;
  status: "pending" | "running" | "done" | "failed" | "skipped";
  expandable?: boolean;
  expanded?: boolean;
  onToggle?: () => void;
  badge?: string;
  onEdit?: () => void;
  children?: React.ReactNode;
}) {
  const c = colorMap[color];
  const isRunning = status === "running";

  return (
    <div
      className={`rounded-[24px] border ${c.border} ${c.bg} px-4 py-4 transition-all ${isRunning ? `ring-2 ${c.ring}` : ""}`}
    >
      <div
        className={`flex items-start gap-3 ${expandable ? "cursor-pointer select-none" : ""}`}
        onClick={expandable ? onToggle : undefined}
      >
        <div className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl border border-white/5 bg-background/55 ${isRunning ? "animate-pulse" : ""}`}>
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className={`text-[10px] font-medium uppercase tracking-[0.18em] ${c.label}`}>{label}</div>
          <div className="mt-1 text-base font-semibold text-foreground">{title}</div>
        </div>
        {badge && (
          <span className={`rounded-full border px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.14em] ${c.border} ${c.bg} ${c.label}`}>
            {badge}
          </span>
        )}
        {onEdit && (
          <button
            onClick={(e) => { e.stopPropagation(); onEdit(); }}
            className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-lg hover:bg-violet-500/20 text-muted-foreground hover:text-violet-400 shrink-0"
            title="Редактировать задачу"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
        )}
        {expandable && (
          <ChevronRight className={`mt-1 h-4 w-4 shrink-0 text-muted-foreground transition-transform ${expanded ? "rotate-90" : ""}`} />
        )}
      </div>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Connector line between nodes
// ---------------------------------------------------------------------------

function FlowConnector({ active, thin }: { active?: boolean; thin?: boolean }) {
  return (
    <div className="flex justify-start py-1 pl-[1.7rem]">
      <div
        className={`w-px rounded-full ${thin ? "h-5" : "h-7"} ${active ? "bg-sky-400" : "bg-border/60"}`}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.18em] ${statusClasses(status)}`}>
      {statusLabel(status)}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Report view — full-width, no max-w constraint
// ---------------------------------------------------------------------------

function ReportView({ run, t }: {
  run: AgentRunDetail;
  t: (key: string) => string;
}) {
  const report = run.final_report || run.ai_analysis;
  const isComplete = run.status === "completed";
  const isFailed = run.status === "failed";

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-5 px-4 py-5 sm:px-6">
      <div className="rounded-[28px] border border-border/70 bg-card/55 shadow-[0_22px_64px_rgba(0,0,0,0.18)]">
        <div className="border-b border-border/70 px-5 py-5">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <div className="inline-flex items-center gap-2 rounded-full border border-border/70 bg-background/60 px-3 py-1 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
                <FileText className="h-3 w-3" />
                Final report
              </div>
              <div className="mt-4 flex items-start gap-3">
                <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl border ${isComplete ? "border-emerald-500/25 bg-emerald-500/10" : isFailed ? "border-red-500/25 bg-red-500/10" : "border-border/70 bg-background/60"}`}>
                  {isComplete ? <CheckCircle2 className="h-5 w-5 text-emerald-300" /> : isFailed ? <AlertTriangle className="h-5 w-5 text-red-300" /> : <FileText className="h-5 w-5 text-muted-foreground" />}
                </div>
                <div className="min-w-0">
                  <h2 className="text-2xl font-semibold tracking-[-0.03em] text-foreground">{run.agent_name}</h2>
                  <p className="mt-1 text-sm leading-6 text-muted-foreground">
                    Concise execution summary, outputs, and final synthesis for this agent run.
                  </p>
                </div>
              </div>
            </div>
            <StatusBadge status={run.status} />
          </div>
        </div>

        <div className="grid gap-3 px-5 py-5 sm:grid-cols-2 xl:grid-cols-4">
          <MetaCard icon={<Clock className="h-3.5 w-3.5" />} label={t("agent.duration")} value={formatDuration(run.duration_ms)} />
          <MetaCard
            icon={<Activity className="h-3.5 w-3.5" />}
            label={run.agent_mode === "multi" ? "Tasks" : t("agent.iterations")}
            value={run.agent_mode === "multi" ? String(run.plan_tasks?.length || 0) : String(run.total_iterations)}
          />
          <MetaCard
            icon={<Terminal className="h-3.5 w-3.5" />}
            label="Servers"
            value={run.connected_servers.length > 0 ? run.connected_servers.map((s) => s.server_name).join(", ") : run.server_name}
          />
          <MetaCard
            icon={<Clock className="h-3.5 w-3.5" />}
            label={isComplete ? t("agent.completed_at") : t("agent.failed_at")}
            value={formatDateTime(run.completed_at)}
          />
        </div>
      </div>

      {run.agent_mode === "mini" && run.commands_output.length > 0 && (
        <div className="rounded-[28px] border border-border/70 bg-card/55 px-5 py-5 shadow-[0_18px_48px_rgba(0,0,0,0.16)]">
          <div className="mb-4 text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground">Console output</div>
          <div className="space-y-3">
            {run.commands_output.map((cmd, i) => (
              <div key={i} className="overflow-hidden rounded-[22px] border border-border/70 bg-[#0f141c]">
                <div className="flex flex-wrap items-center gap-2 border-b border-white/5 bg-white/[0.03] px-4 py-3">
                  <span className="font-mono text-[10px] text-emerald-300">$</span>
                  <span className="min-w-0 flex-1 break-all font-mono text-xs text-foreground">{cmd.cmd}</span>
                  <span className={`rounded-full px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] ${cmd.exit_code === 0 ? "bg-emerald-500/15 text-emerald-300" : "bg-red-500/15 text-red-300"}`}>
                    exit {cmd.exit_code}
                  </span>
                  <span className="text-[10px] text-muted-foreground">{cmd.duration_ms}ms</span>
                </div>
                {cmd.stdout && <pre className="max-h-56 overflow-x-auto px-4 py-3 font-mono text-[11px] whitespace-pre-wrap text-foreground/80">{cmd.stdout.slice(0, 4000)}</pre>}
                {cmd.stderr && <pre className="border-t border-red-500/10 px-4 py-3 font-mono text-[11px] whitespace-pre-wrap text-red-300/80">{cmd.stderr.slice(0, 800)}</pre>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Report text */}
      {report ? (
        <div className="rounded-[28px] border border-border/70 bg-card/55 px-5 py-6 shadow-[0_18px_48px_rgba(0,0,0,0.16)]">
          <div
            className="
              [&_h1]:mt-0 [&_h1]:mb-4 [&_h1]:text-[26px] [&_h1]:font-semibold [&_h1]:tracking-[-0.04em] [&_h1]:text-foreground
              [&_h2]:mt-10 [&_h2]:mb-3 [&_h2]:border-b [&_h2]:border-border/50 [&_h2]:pb-2 [&_h2]:text-[12px] [&_h2]:font-medium [&_h2]:uppercase [&_h2]:tracking-[0.18em] [&_h2]:text-muted-foreground
              [&_h3]:mt-6 [&_h3]:mb-2 [&_h3]:text-lg [&_h3]:font-semibold [&_h3]:text-foreground
              [&_p]:mb-4 [&_p]:text-[15px] [&_p]:leading-8 [&_p]:text-foreground/82
              [&_ul]:mb-5 [&_ul]:list-disc [&_ul]:space-y-2 [&_ul]:pl-5
              [&_ol]:mb-5 [&_ol]:list-decimal [&_ol]:space-y-2 [&_ol]:pl-5
              [&_li]:text-[15px] [&_li]:leading-8 [&_li]:text-foreground/82
              [&_strong]:font-semibold [&_strong]:text-foreground
              [&_em]:text-foreground/72
              [&_blockquote]:my-6 [&_blockquote]:rounded-r-2xl [&_blockquote]:border-l-2 [&_blockquote]:border-primary/50 [&_blockquote]:bg-background/50 [&_blockquote]:px-5 [&_blockquote]:py-4 [&_blockquote]:text-foreground/72
              [&_code]:rounded-md [&_code]:bg-background/80 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:font-mono [&_code]:text-[13px]
              [&_pre]:my-5 [&_pre]:overflow-x-auto [&_pre]:rounded-[20px] [&_pre]:border [&_pre]:border-border/70 [&_pre]:bg-background/80 [&_pre]:p-5 [&_pre]:font-mono [&_pre]:text-[12px] [&_pre]:leading-6 [&_pre]:text-foreground/78
              [&_hr]:my-8 [&_hr]:border-border/40
              [&_table]:my-6 [&_table]:w-full [&_table]:overflow-hidden [&_table]:rounded-2xl [&_table]:border [&_table]:border-border/60
              [&_thead]:bg-background/80
              [&_th]:border-b [&_th]:border-border/60 [&_th]:px-4 [&_th]:py-3 [&_th]:text-left [&_th]:text-[11px] [&_th]:font-medium [&_th]:uppercase [&_th]:tracking-[0.16em] [&_th]:text-muted-foreground
              [&_td]:border-t [&_td]:border-border/40 [&_td]:px-4 [&_td]:py-3 [&_td]:align-top [&_td]:text-[13px] [&_td]:leading-6 [&_td]:text-foreground/82
            "
          >
            <ReactMarkdown>{report}</ReactMarkdown>
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center rounded-[28px] border border-border/70 bg-card/55 px-6 py-20 text-center shadow-[0_18px_48px_rgba(0,0,0,0.16)]">
          <FileText className="mb-4 h-9 w-9 text-muted-foreground/35" />
          <p className="text-sm text-muted-foreground">
            {["running", "pending"].includes(run.status) ? "Отчёт появится после завершения агента." : "Отчёт недоступен."}
          </p>
        </div>
      )}
    </div>
  );
}

function MetaCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }) {
  return (
    <div className="rounded-[22px] border border-border/70 bg-background/55 px-4 py-4">
      <div className="mb-2 flex items-center gap-2 text-muted-foreground">
        {icon}
        <span className="text-[10px] uppercase tracking-[0.18em]">{label}</span>
      </div>
      <p className="text-sm font-medium leading-6 text-foreground">{value || "—"}</p>
    </div>
  );
}
