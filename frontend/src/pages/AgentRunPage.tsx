import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  Clipboard,
  Download,
  FileArchive,
  FileCode2,
  FileText,
  FolderArchive,
  List,
  ListFilter,
  MessageSquare,
  RefreshCw,
  Search,
  Send,
  Server,
  Shield,
  Square,
  Terminal,
  WrapText,
  Workflow,
} from "lucide-react";

import {
  approvePipelinePlan,
  backendPath,
  cleanupStaleAgentRuns,
  fetchAgentRunReport,
  replyToAgent,
  retryAgentRunReportDelivery,
  stopAgent,
  type AgentRunReportArtifact,
  type AgentRunReportEvent,
  type AgentRunReportFinding,
  type AgentRunReportLog,
  type AgentRunReportResponse,
  type AgentRunReportSeverity,
  type AgentRunReportStep,
} from "@/lib/api";
import { agentRunStatusPresentation, type StatusTone } from "@/design/status";
import { StatusBadge } from "@/components/system/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

import { formatCompactDateTime, formatDuration } from "./agent-run/formatters";

type ReportTab = "overview" | "events" | "logs" | "artifacts" | "agent";

const tabItems: Array<{ value: ReportTab; label: string; icon: LucideIcon }> = [
  { value: "overview", label: "Обзор", icon: FileText },
  { value: "events", label: "События", icon: List },
  { value: "logs", label: "Логи", icon: Terminal },
  { value: "artifacts", label: "Артефакты", icon: FolderArchive },
  { value: "agent", label: "Ход агента", icon: Workflow },
];

const severityTone: Record<AgentRunReportSeverity, StatusTone> = {
  success: "success",
  info: "info",
  warning: "warning",
  high: "warning",
  critical: "danger",
  fatal: "danger",
};

const severityLabel: Record<AgentRunReportSeverity, string> = {
  success: "OK",
  info: "Info",
  warning: "Warning",
  high: "High",
  critical: "Critical",
  fatal: "Fatal",
};

const EVENT_PAGE_SIZE = 60;
const LOG_PAGE_SIZE = 30;

const eventModeLabel = {
  brief: "Важные",
  all: "Все",
  debug: "Debug",
};

const eventPhaseLabel: Record<string, string> = {
  queued: "Очередь",
  starting: "Старт",
  planning: "Планирование",
  plan_review: "Подтверждение",
  executing: "Выполнение",
  waiting: "Ожидание",
  synthesizing: "Отчёт",
  delivery: "Доставка",
  ready: "Готово",
  failed: "Ошибка",
  stopped: "Остановлен",
  activity: "Активность",
};

const eventCategoryLabel: Record<string, string> = {
  agent: "Агент",
  command: "Команды",
  dispatch: "Dispatch",
  report: "Отчёт",
  system: "Система",
  task: "Задачи",
  worker: "Worker",
};

function saveBlob(name: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name || "agent-run-artifact.txt";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function downloadTextFile(name: string, content: string, contentType: string) {
  saveBlob(name, new Blob([content || ""], { type: contentType || "text/plain;charset=utf-8" }));
}

async function downloadArtifact(artifact: AgentRunReportArtifact) {
  if (artifact.download_url) {
    const response = await fetch(backendPath(artifact.download_url), { credentials: "include" });
    if (!response.ok) {
      throw new Error(`Не удалось скачать ${artifact.name}: HTTP ${response.status}`);
    }
    saveBlob(artifact.name, await response.blob());
    return;
  }
  downloadTextFile(artifact.name, artifact.content, artifact.content_type);
}

async function downloadArtifactBundle(report: AgentRunReportResponse) {
  const url = report.artifact_state?.bundle_download_url;
  if (!url) return false;
  const response = await fetch(backendPath(url), { credentials: "include" });
  if (!response.ok) {
    throw new Error(`Не удалось скачать пакет артефактов: HTTP ${response.status}`);
  }
  saveBlob(`agent-run-${report.run.id}-artifacts.zip`, await response.blob());
  return true;
}

async function copyText(value: string) {
  await navigator.clipboard?.writeText(value);
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function stripLeadingTitleHeading(markdown: string, title: string) {
  const normalizedTitle = title.trim();
  if (!markdown || !normalizedTitle) return markdown;
  return markdown.replace(new RegExp(`^#\\s+${escapeRegExp(normalizedTitle)}\\s*\\n+`, "i"), "");
}

function cleanInlineMarkdown(value: string) {
  return String(value || "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

function primaryOutcomeSummary(report: AgentRunReportResponse) {
  return (
    cleanInlineMarkdown(report.report.root_cause || "") ||
    cleanInlineMarkdown(report.report.summary) ||
    cleanInlineMarkdown(report.report_state?.description || "") ||
    "Отчёт пока формируется."
  );
}

function riskLabel(report: AgentRunReportResponse) {
  if (report.report.severity === "success" && !report.report.risks.length) return "OK";
  return severityLabel[report.report.severity] || report.report.severity || "Info";
}

function reportSignalCount(report: AgentRunReportResponse) {
  const signalKpi = report.report.kpis.find((item) => {
    const id = String(item.id || "").toLowerCase();
    const label = String(item.label || "").toLowerCase();
    return id.includes("signal") || id.includes("сигнал") || label.includes("signal") || label.includes("сигнал");
  });
  const parsed = Number(String(signalKpi?.value || "").replace(/[^\d]/g, ""));
  if (Number.isFinite(parsed) && parsed > 0) return parsed;
  return report.events.length + report.logs.length;
}

function diagnosticProblem(report: AgentRunReportResponse) {
  const severeFinding = [...report.report.findings]
    .sort((a, b) => _severityRank(b.severity) - _severityRank(a.severity))
    .find((item) => cleanInlineMarkdown(item.title));
  return (
    cleanInlineMarkdown(report.report.root_cause || "") ||
    cleanInlineMarkdown(severeFinding?.title || "") ||
    cleanInlineMarkdown(report.report.summary) ||
    cleanInlineMarkdown(report.report_state?.headline || "") ||
    "Причина пока не определена."
  );
}

function diagnosticImpact(report: AgentRunReportResponse) {
  const risk = [...report.report.risks]
    .sort((a, b) => _severityRank(b.severity) - _severityRank(a.severity))
    .find((item) => cleanInlineMarkdown(item.title || item.description));
  return (
    cleanInlineMarkdown(risk?.description || "") ||
    cleanInlineMarkdown(risk?.title || "") ||
    cleanInlineMarkdown(report.report.subtitle) ||
    cleanInlineMarkdown(report.report_state?.next_expected || "") ||
    "Влияние пока не выделено."
  );
}

function diagnosticActions(report: AgentRunReportResponse) {
  const actions = report.report.recommendations
    .map((item) => cleanInlineMarkdown(item.description || item.title))
    .filter(Boolean);
  if (actions.length) return actions;
  const nextExpected = cleanInlineMarkdown(report.report_state?.next_expected || "");
  return nextExpected ? [nextExpected] : [];
}

function diagnosticEvidenceItems(report: AgentRunReportResponse) {
  const fromFindings = report.report.findings.map((item, index) => ({
    text: cleanInlineMarkdown(item.description || item.title),
    time: evidenceTime(report.events[index]?.created_at || report.run.completed_at || report.run.started_at),
    severity: item.severity,
  }));
  const findings = fromFindings.filter((item) => item.text);
  if (findings.length) return findings;

  const fromEvents = report.events.filter((event) => event.important).map((event) => ({
    text: cleanInlineMarkdown(event.summary || event.title || event.message),
    time: evidenceTime(event.created_at),
    severity: event.severity,
  }));
  const events = fromEvents.filter((item) => item.text);
  if (events.length) return events;

  return report.logs.map((log) => ({
    text: cleanInlineMarkdown(log.stderr || log.stdout || log.command || log.title),
    time: evidenceTime(log.timestamp || report.run.completed_at || report.run.started_at),
    severity: log.severity,
  })).filter((item) => item.text);
}

function evidenceTime(value?: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}

export default function AgentRunPage() {
  const { runId } = useParams<{ runId: string }>();
  const rid = parseInt(runId || "0", 10);
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<ReportTab>("overview");
  const [stopping, setStopping] = useState(false);
  const [approving, setApproving] = useState(false);
  const [cleaningStale, setCleaningStale] = useState(false);
  const [retryingDelivery, setRetryingDelivery] = useState(false);
  const [replyText, setReplyText] = useState("");
  const [replying, setReplying] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionNotice, setActionNotice] = useState<string | null>(null);

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["agent-run-report", rid],
    queryFn: () => fetchAgentRunReport(rid),
    enabled: rid > 0,
    retry: false,
    refetchInterval: (query) => {
      const status = query.state.data?.run?.status;
      return status && ["running", "pending", "paused", "waiting", "plan_review"].includes(status) ? 2500 : false;
    },
  });

  const run = data?.run;
  const isActive = Boolean(run && ["running", "pending", "paused", "waiting"].includes(run.status));
  const isPlanReview = run?.status === "plan_review";

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["agent-run-report", rid] });
    await queryClient.invalidateQueries({ queryKey: ["agents"] });
  };

  const onStop = async () => {
    if (!run) return;
    setStopping(true);
    setActionError(null);
    setActionNotice(null);
    try {
      await stopAgent(run.agent_id, run.id);
      await refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Stop failed");
    } finally {
      setStopping(false);
    }
  };

  const onApprove = async () => {
    if (!run) return;
    setApproving(true);
    setActionError(null);
    setActionNotice(null);
    try {
      await approvePipelinePlan(run.id);
      await refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : t("run.approve_error"));
    } finally {
      setApproving(false);
    }
  };

  const onCleanupStale = async () => {
    setCleaningStale(true);
    setActionError(null);
    setActionNotice(null);
    try {
      const response = await cleanupStaleAgentRuns({ limit: 50 });
      setActionNotice(`Очищено stale-запусков: ${response.cleanup.cleaned}; отменено dispatch: ${response.cleanup.canceled_dispatches}.`);
      await refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Не удалось очистить stale-запуск.");
    } finally {
      setCleaningStale(false);
    }
  };

  const onRetryDelivery = async () => {
    if (!run) return;
    setRetryingDelivery(true);
    setActionError(null);
    setActionNotice(null);
    try {
      await retryAgentRunReportDelivery(run.id);
      setActionNotice("Доставка отчёта запущена повторно.");
      await refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Не удалось повторить доставку отчёта.");
    } finally {
      setRetryingDelivery(false);
    }
  };

  const onReply = async () => {
    if (!run) return;
    const answer = replyText.trim();
    if (!answer) {
      setActionNotice(null);
      setActionError("Введите ответ для агента.");
      return;
    }
    setReplying(true);
    setActionError(null);
    setActionNotice(null);
    try {
      await replyToAgent(run.id, answer);
      setReplyText("");
      setActionNotice("Ответ отправлен агенту.");
      await refresh();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : "Не удалось отправить ответ агенту.");
    } finally {
      setReplying(false);
    }
  };

  const copyText = async (value: string) => {
    if (!value) return;
    try {
      await navigator.clipboard?.writeText(value);
      setActionNotice("Скопировано.");
      setActionError(null);
    } catch {
      setActionNotice(null);
      setActionError(value);
    }
  };

  if (rid <= 0) {
    return <StateBlock title={t("run.invalid_id")} />;
  }

  if (isLoading) {
    return <StateBlock title={t("loading")} icon={<RefreshCw className="h-4 w-4 animate-spin" />} />;
  }

  if (isError || !data || !run) {
    const message = error instanceof Error ? error.message : t("run.not_found");
    return <StateBlock title={t("run.not_found_title")} description={message} danger />;
  }

  const status = agentRunStatusPresentation(run.status);

  return (
    <div
      data-agent-run-scroll
      className="h-full min-h-0 overflow-y-auto overflow-x-hidden bg-background [scrollbar-gutter:stable]"
    >
      <header className="sticky top-0 z-20 border-b border-border/70 bg-background/95 backdrop-blur">
        <div className="mx-auto flex w-full max-w-[1680px] flex-col gap-3 px-4 py-3 sm:px-6 2xl:px-8">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="truncate text-2xl font-semibold tracking-[-0.02em] text-foreground sm:text-3xl">
                  {data.report.title || run.agent_name}
                </h1>
                <StatusBadge label={t(status.labelKey)} tone={status.tone} pulse={status.pulse} />
                <StatusBadge
                  label={severityLabel[data.report.severity] || data.report.severity}
                  tone={severityTone[data.report.severity] || "neutral"}
                />
              </div>
              <p className="mt-1 max-w-4xl text-sm leading-6 text-muted-foreground">{primaryOutcomeSummary(data)}</p>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              {isPlanReview ? (
                <Button size="sm" className="h-9 gap-1.5" onClick={onApprove} disabled={approving}>
                  {approving ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                  {approving ? t("run.approving") : t("run.approve")}
                </Button>
              ) : null}
              {isActive || isPlanReview ? (
                <Button size="sm" variant="destructive" className="h-9 gap-1.5" onClick={onStop} disabled={stopping}>
                  {stopping ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Square className="h-3.5 w-3.5" />}
                  {t("agent.stop")}
                </Button>
              ) : null}
              {data.report_state?.execution_state?.can_cleanup ? (
                <Button size="sm" variant="outline" className="h-9 gap-1.5 border-amber-500/30 text-amber-200 hover:text-amber-100" onClick={onCleanupStale} disabled={cleaningStale}>
                  {cleaningStale ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <AlertTriangle className="h-3.5 w-3.5" />}
                  {cleaningStale ? "Очищаем" : "Очистить stale"}
                </Button>
              ) : null}
              <Button size="icon" variant="outline" className="h-9 w-9" onClick={() => void refresh()} aria-label={t("udash.refresh")}>
                <RefreshCw className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {actionError ? <div className="text-sm text-destructive">{actionError}</div> : null}
          {actionNotice ? <div className="text-sm text-emerald-300">{actionNotice}</div> : null}
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-[1680px] flex-col gap-4 px-4 py-5 sm:px-6 2xl:px-8">
        <ReportMetricCards report={data} />
        <PendingQuestionPanel
          report={data}
          answer={replyText}
          submitting={replying}
          onAnswerChange={setReplyText}
          onSubmit={onReply}
        />
        <LiveRunBanner
          report={data}
          onOpenTab={setActiveTab}
          onCleanupStale={onCleanupStale}
          cleaningStale={cleaningStale}
          onCopyText={copyText}
        />

        <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as ReportTab)} className="space-y-4">
          <TabsContent value="overview">
            <OverviewTab report={data} onRetryDelivery={onRetryDelivery} retryingDelivery={retryingDelivery} />
          </TabsContent>
          <TabsContent value="events">
            <EventsTab report={data} />
          </TabsContent>
          <TabsContent value="logs">
            <LogsTab report={data} logs={data.logs} />
          </TabsContent>
          <TabsContent value="artifacts">
            <ArtifactsTab report={data} />
          </TabsContent>
          <TabsContent value="agent">
            <AgentStepsTab report={data} steps={data.agent_steps} />
          </TabsContent>

          <TabsList className="h-auto w-full justify-start gap-1 overflow-x-auto p-1.5 sm:w-auto">
            {tabItems.map((item) => {
              const Icon = item.icon;
              return (
                <TabsTrigger key={item.value} value={item.value} className="h-10 gap-2 px-3 text-sm">
                  <Icon className="h-4 w-4" />
                  {item.label}
                </TabsTrigger>
              );
            })}
          </TabsList>
        </Tabs>
      </main>
    </div>
  );
}

function StateBlock({ title, description, icon, danger = false }: { title: string; description?: string; icon?: ReactNode; danger?: boolean }) {
  return (
    <div className="flex h-[calc(100vh-3.5rem)] items-center justify-center bg-background px-4">
      <div className="max-w-md rounded-lg border border-border/70 bg-card/90 px-5 py-4 text-sm text-muted-foreground shadow-[0_18px_48px_rgba(0,0,0,0.18)]">
        <div className="mb-1 flex items-center gap-2 font-medium text-foreground">
          {icon || <AlertTriangle className={cn("h-4 w-4", danger ? "text-destructive" : "text-warning")} />}
          {title}
        </div>
        {description ? <p>{description}</p> : null}
      </div>
    </div>
  );
}

function PendingQuestionPanel({
  report,
  answer,
  submitting,
  onAnswerChange,
  onSubmit,
}: {
  report: AgentRunReportResponse;
  answer: string;
  submitting: boolean;
  onAnswerChange: (value: string) => void;
  onSubmit: () => void;
}) {
  const question = String(report.run.pending_question || "").trim();
  if (!question || report.run.status !== "waiting") return null;

  return (
    <section className="enterprise-panel border-amber-500/35 bg-amber-500/5 p-4 sm:p-5">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(320px,520px)]">
        <div className="min-w-0">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <StatusBadge label="Агент ждёт ответа" tone="warning" pulse />
            <span className="rounded-md border border-amber-500/25 bg-amber-500/10 px-2.5 py-1 text-xs font-medium text-amber-200">
              human-in-the-loop
            </span>
          </div>
          <div className="flex gap-3">
            <MessageSquare className="mt-0.5 h-4 w-4 shrink-0 text-amber-300" />
            <div className="min-w-0">
              <h3 className="text-base font-semibold text-foreground">Вопрос агента</h3>
              <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-foreground/85">{question}</p>
            </div>
          </div>
        </div>

        <form
          className="min-w-0 space-y-3 rounded-lg border border-border/70 bg-background/45 p-3"
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit();
          }}
        >
          <Textarea
            value={answer}
            onChange={(event) => onAnswerChange(event.target.value)}
            placeholder="Введите ответ агенту"
            aria-label="Ответ агенту"
            className="min-h-[104px] resize-y"
            disabled={submitting}
          />
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs leading-5 text-muted-foreground">
              После отправки запуск вернётся в выполнение, а ответ попадёт в события отчёта.
            </p>
            <Button type="submit" size="sm" className="h-9 shrink-0 gap-1.5" disabled={submitting || !answer.trim()}>
              {submitting ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              {submitting ? "Отправляем" : "Отправить ответ"}
            </Button>
          </div>
        </form>
      </div>
    </section>
  );
}

function ReportMetricCards({ report }: { report: AgentRunReportResponse }) {
  const cards = [
    {
      id: "risk",
      label: "Риск",
      value: riskLabel(report),
      hint: report.report.severity === "success" ? "Норма" : "Критический",
      icon: Shield,
      tone: severityTone[report.report.severity] || "neutral",
    },
    {
      id: "signals",
      label: "Сигналы",
      value: String(reportSignalCount(report)),
      hint: "Всего сигналов",
      icon: Activity,
      tone: "info" as StatusTone,
    },
    {
      id: "duration",
      label: "Длительность",
      value: report.run.duration_ms > 0 ? formatDuration(report.run.duration_ms) : "—",
      hint: "Время выполнения",
      icon: Clock3,
      tone: "info" as StatusTone,
    },
    {
      id: "server",
      label: "Сервер",
      value: report.report.meta.server || report.run.server_name || "—",
      hint: "UNIX",
      icon: Server,
      tone: "neutral" as StatusTone,
    },
  ];

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {cards.map((card) => (
        <MetricCard key={card.id} {...card} />
      ))}
    </div>
  );
}

function MetricCard({
  label,
  value,
  hint,
  icon: Icon,
  tone,
}: {
  label: string;
  value: string;
  hint: string;
  icon: LucideIcon;
  tone: StatusTone;
}) {
  return (
    <div className="enterprise-panel flex min-h-[118px] items-center gap-4 p-5">
      <div className={cn("flex h-14 w-14 shrink-0 items-center justify-center rounded-lg border", toneBoxFromStatusTone(tone))}>
        <Icon className="h-7 w-7" />
      </div>
      <div className="min-w-0">
        <p className="text-sm leading-5 text-muted-foreground">{label}</p>
        <p className="mt-1 truncate text-2xl font-semibold tracking-[-0.01em] text-foreground">{value || "—"}</p>
        <p className="mt-1 truncate text-sm text-muted-foreground">{hint}</p>
      </div>
    </div>
  );
}

function LiveRunBanner({
  report,
  onOpenTab,
  onCleanupStale,
  cleaningStale,
  onCopyText,
}: {
  report: AgentRunReportResponse;
  onOpenTab: (tab: ReportTab) => void;
  onCleanupStale: () => void;
  cleaningStale: boolean;
  onCopyText: (value: string) => void;
}) {
  if (report.report_state?.report_ready) return null;
  const state = report.report_state?.execution_state;
  const problemEvents = report.events.filter((event) => _severityRank(event.severity) >= _severityRank("warning")).length;
  const failedLogs = report.logs.filter((log) => Number(log.exit_code || 0) !== 0).length;
  const activeSteps = report.agent_steps.filter((step) => ["running", "pending", "waiting"].includes(step.status)).length;
  const progress = Math.max(0, Math.min(100, Number(report.report_state?.progress || 0)));
  const statusTone = severityTone[state?.severity || report.report.severity] || "info";

  return (
    <div className="enterprise-panel p-4 sm:p-5">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_auto]">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge label="Отчёт формируется" tone="info" pulse />
            <StatusBadge label={state?.title || report.report_state?.headline || report.report.status_label} tone={statusTone} />
          </div>
          <div className="mt-3 flex gap-3">
            <Activity className="mt-0.5 h-4 w-4 shrink-0 text-info" />
            <p className="max-w-5xl text-sm leading-6 text-muted-foreground">
              {state?.description || report.report_state?.description || report.report.summary}
            </p>
          </div>
          <div className="mt-4 max-w-4xl">
            <div className="mb-2 flex items-center justify-between gap-3 text-xs text-muted-foreground">
              <span className="truncate">{report.report_state?.current_step || "Ожидаем следующее событие агента"}</span>
              <span className="font-mono">{progress}%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full border border-border/70 bg-background/65">
              <div className="h-full rounded-full bg-info transition-[width]" style={{ width: `${progress}%` }} />
            </div>
          </div>
        </div>

        <div className="grid min-w-[min(100%,28rem)] gap-2 sm:grid-cols-2">
          <LiveMetric label="Dispatch" value={state?.dispatch?.status || report.run.dispatch?.status || "—"} />
          <LiveMetric label="Worker" value={state?.worker?.worker_key || state?.worker?.status || "—"} tone={state?.worker_ready ? "success" : "warning"} />
          <LiveMetric label="Runtime" value={state?.runtime_age || "—"} tone={state?.is_stale_candidate ? "warning" : "info"} />
          <LiveMetric label="Stale after" value={state?.stale_after || "—"} tone={state?.is_stale_candidate ? "warning" : "info"} />
          <LiveMetric label="Сигналы" value={String(problemEvents + failedLogs)} tone={problemEvents + failedLogs > 0 ? "warning" : "success"} />
          <LiveMetric label="Шаги" value={String(activeSteps)} />
        </div>
      </div>

      <div className="mt-4 flex flex-col gap-3 border-t border-border/70 pt-4 lg:flex-row lg:items-center lg:justify-between">
        <p className="min-w-0 text-sm leading-6 text-muted-foreground">
          {report.report_state?.next_expected || "Дождитесь завершения агента. Финальный markdown и артефакты появятся после сохранения отчёта."}
        </p>
        <div className="flex shrink-0 flex-wrap gap-2">
          {state?.next_action ? (
            <Button size="sm" variant="outline" className="h-9 gap-1.5" onClick={() => onCopyText(state.next_action)}>
              <Clipboard className="h-4 w-4" />
              Скопировать действие
            </Button>
          ) : null}
          {state?.can_cleanup ? (
            <Button size="sm" variant="outline" className="h-9 gap-1.5 border-amber-500/30 text-amber-200 hover:text-amber-100" onClick={onCleanupStale} disabled={cleaningStale}>
              {cleaningStale ? <RefreshCw className="h-4 w-4 animate-spin" /> : <AlertTriangle className="h-4 w-4" />}
              {cleaningStale ? "Очищаем" : "Очистить stale"}
            </Button>
          ) : null}
          <Button size="sm" variant="outline" className="h-9 gap-1.5" onClick={() => onOpenTab("events")}>
            <List className="h-4 w-4" />
            События
          </Button>
          <Button size="sm" variant="outline" className="h-9 gap-1.5" onClick={() => onOpenTab("logs")}>
            <Terminal className="h-4 w-4" />
            Логи
          </Button>
          <Button size="sm" variant="outline" className="h-9 gap-1.5" onClick={() => onOpenTab("artifacts")}>
            <FolderArchive className="h-4 w-4" />
            Артефакты
          </Button>
        </div>
      </div>
    </div>
  );
}

function LiveMetric({ label, value, tone = "info" }: { label: string; value: string; tone?: StatusTone }) {
  return (
    <div className={cn("min-w-0 rounded-lg border p-3", toneBoxFromStatusTone(tone))}>
      <p className="text-[11px] font-semibold uppercase tracking-wide opacity-80">{label}</p>
      <p className="mt-1 truncate font-mono text-sm font-semibold">{value || "—"}</p>
    </div>
  );
}

function OverviewTab({
  report,
  onRetryDelivery,
  retryingDelivery,
}: {
  report: AgentRunReportResponse;
  onRetryDelivery: () => void;
  retryingDelivery: boolean;
}) {
  if (!report.report_state?.report_ready) {
    return <LiveOverviewTab report={report} onRetryDelivery={onRetryDelivery} retryingDelivery={retryingDelivery} />;
  }

  const markdown = stripLeadingTitleHeading(report.report.markdown, report.report.title);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_520px]">
        <div className="space-y-2">
          <SummaryPanel report={report} />
          <ChecklistPanel report={report} />
          <EvidencePanel report={report} />
        </div>
        <div className="space-y-4">
          <ProblemsPanel report={report} />
          <ActionPlanPanel report={report} />
        </div>
      </div>
      <DeliveryInline report={report} onRetry={onRetryDelivery} retrying={retryingDelivery} />
      <FinalMarkdownDisclosure markdown={markdown} />
    </div>
  );
}

function LiveOverviewTab({
  report,
  onRetryDelivery,
  retryingDelivery,
}: {
  report: AgentRunReportResponse;
  onRetryDelivery: () => void;
  retryingDelivery: boolean;
}) {
  const importantEvents = report.events.filter((event) => event.important).slice(-6).reverse();
  const problemEvents = report.events.filter((event) => severityTone[event.severity] === "danger" || severityTone[event.severity] === "warning");
  const activeSteps = report.agent_steps.filter((step) => ["running", "pending", "waiting"].includes(step.status)).slice(0, 5);

  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_420px]">
      <div className="space-y-4">
        <div className="enterprise-panel p-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="min-w-0">
              <h3 className="text-base font-semibold text-foreground">{report.report_state?.headline || "Запуск активен"}</h3>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">{report.report_state?.description}</p>
            </div>
            <StatusBadge label={report.report.status_label} tone={severityTone[report.report.severity]} />
          </div>
          <div className="mt-5 grid gap-3 sm:grid-cols-3">
            <ReportStat label="События" value={String(report.events.length)} hint={`${importantEvents.length} важных`} />
            <ReportStat label="Логи" value={String(report.logs.length)} hint={report.logs.some((log) => log.exit_code !== 0) ? "есть ошибки" : "без ошибок"} />
            <ReportStat label="Шаги" value={String(report.agent_steps.length)} hint={activeSteps[0]?.status_label || "ожидаем"} />
          </div>
        </div>

        <div className="enterprise-panel p-5">
          <h3 className="text-base font-semibold text-foreground">Последние важные события</h3>
          <RecentEventsList events={importantEvents} empty="Пока есть только технические события запуска." />
        </div>

        {problemEvents.length ? (
          <CompactFindingPanel title="Проблемные сигналы" empty="Проблемных сигналов нет." items={report.report.findings} />
        ) : null}
      </div>

      <div className="space-y-4">
        <ExecutionStatePanel report={report} />
        <DeliveryInline report={report} onRetry={onRetryDelivery} retrying={retryingDelivery} />

        <div className="enterprise-panel p-5">
          <h3 className="text-base font-semibold text-foreground">Что дальше</h3>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            {report.report_state?.next_expected || "Дождитесь следующего события агента."}
          </p>
          {activeSteps.length ? (
            <ol className="mt-4 space-y-2">
              {activeSteps.map((step) => (
                <li key={step.id} className="flex items-start gap-3 rounded-lg border border-border/70 bg-background/45 p-3">
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border/70 bg-card/70 font-mono text-xs text-muted-foreground">
                    {step.index}
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm font-medium leading-5 text-foreground">{step.title}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{step.status_label || step.status}</p>
                  </div>
                </li>
              ))}
            </ol>
          ) : null}
        </div>

        <CompactFindingPanel title="Риски сейчас" empty="Критических рисков не отмечено." items={report.report.risks} />
      </div>
    </div>
  );
}

function SummaryPanel({ report }: { report: AgentRunReportResponse }) {
  const summaryLines = [
    diagnosticProblem(report),
    diagnosticImpact(report),
    report.report.root_cause ? `Причина: ${cleanInlineMarkdown(report.report.root_cause)}` : "",
  ].filter(Boolean);

  return (
    <ReportSectionPanel icon={FileText} iconTone="info" title="Краткий итог">
      <div className="space-y-1.5 text-sm leading-6 text-foreground/82">
        {summaryLines.slice(0, 3).map((line, index) => (
          <p key={`${line}-${index}`}>{line}</p>
        ))}
      </div>
    </ReportSectionPanel>
  );
}

function ChecklistPanel({ report }: { report: AgentRunReportResponse }) {
  const actions = diagnosticActions(report).slice(0, 4);

  return (
    <ReportSectionPanel icon={CheckCircle2} iconTone="neutral" title="Что проверить">
      {actions.length ? (
        <ol className="space-y-0">
          {actions.map((action, index) => (
            <li key={`${action}-${index}`} className="flex gap-3 border-b border-border/55 py-2.5 last:border-b-0">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-primary/30 bg-primary/15 font-mono text-xs font-semibold text-primary">
                {index + 1}
              </span>
              <span className="min-w-0 text-sm leading-6 text-foreground/82">{action}</span>
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-sm text-muted-foreground">Рекомендации не сформированы.</p>
      )}
    </ReportSectionPanel>
  );
}

function EvidencePanel({ report }: { report: AgentRunReportResponse }) {
  const evidence = diagnosticEvidenceItems(report).slice(0, 3);
  return (
    <ReportSectionPanel icon={Search} iconTone="success" title="Доказательства">
      {evidence.length ? (
        <ul className="overflow-hidden rounded-md border border-border/60">
          {evidence.map((item, index) => (
            <li key={`${item.text}-${index}`} className="flex gap-3 border-b border-border/55 px-3 py-2.5 last:border-b-0">
              <span className={cn("mt-2 h-2 w-2 shrink-0 rounded-full", eventDot(item.severity))} />
              <div className="min-w-0 flex-1">
                <p className="break-words text-sm leading-5 text-foreground/86">{item.text}</p>
              </div>
              <span className="shrink-0 font-mono text-xs text-muted-foreground">{item.time}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">Доказательства не выделены. Проверьте вкладки событий и логов.</p>
      )}
    </ReportSectionPanel>
  );
}

function ProblemsPanel({ report }: { report: AgentRunReportResponse }) {
  const items = report.report.risks.length ? report.report.risks : report.report.findings.filter((item) => _severityRank(item.severity) >= _severityRank("warning"));
  return (
    <ReportSectionPanel icon={AlertTriangle} iconTone="warning" title="Проблемы и риски">
      {items.length ? (
        <ul className="divide-y divide-border/55">
          {items.slice(0, 5).map((item) => (
            <li key={item.id} className="flex gap-3 py-3 first:pt-0 last:pb-0">
              <span className="mt-2 h-2 w-2 shrink-0 rounded-full bg-warning" />
              <p className="text-sm leading-6 text-foreground/82">
                {cleanInlineMarkdown(item.description || item.title)}
              </p>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">Критических рисков не отмечено.</p>
      )}
    </ReportSectionPanel>
  );
}

function ActionPlanPanel({ report }: { report: AgentRunReportResponse }) {
  const actions = report.report.recommendations;
  return (
    <ReportSectionPanel icon={CheckCircle2} iconTone="success" title="План действий">
      {actions.length ? (
        <ol className="divide-y divide-border/55">
          {actions.slice(0, 5).map((item) => (
            <li key={item.id} className="flex gap-3 py-3 first:pt-0 last:pb-0">
              <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-success" />
              <p className="text-sm leading-6 text-foreground/82">
                {cleanInlineMarkdown(item.description || item.title)}
              </p>
            </li>
          ))}
        </ol>
      ) : (
        <p className="text-sm text-muted-foreground">Рекомендации не сформированы.</p>
      )}
    </ReportSectionPanel>
  );
}

function ReportSectionPanel({
  icon: Icon,
  iconTone,
  title,
  children,
}: {
  icon: LucideIcon;
  iconTone: StatusTone;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="enterprise-panel p-5">
      <div className="flex gap-4">
        <div className={cn("flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border", toneBoxFromStatusTone(iconTone))}>
          <Icon className="h-5 w-5" />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="text-lg font-semibold tracking-[-0.01em] text-foreground">{title}</h3>
          <div className="mt-3">{children}</div>
        </div>
      </div>
    </section>
  );
}

function CompactFindingPanel({ title, empty, items }: { title: string; empty: string; items: AgentRunReportFinding[] }) {
  return (
    <div className="enterprise-panel p-5">
      <h3 className="text-base font-semibold text-foreground">{title}</h3>
      {items.length ? (
        <ul className="mt-4 space-y-3">
          {items.map((item) => (
            <li key={item.id} className="flex gap-3">
              <span className={cn("mt-2 h-2 w-2 shrink-0 rounded-full", eventDot(item.severity))} />
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium leading-6 text-foreground">{cleanInlineMarkdown(item.title)}</span>
                  <span className={cn("rounded border px-1.5 py-0.5 text-[11px] font-medium", toneBox(item.severity))}>
                    {severityLabel[item.severity]}
                  </span>
                </div>
                {item.description ? <p className="text-xs leading-5 text-muted-foreground">{cleanInlineMarkdown(item.description)}</p> : null}
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 text-sm text-muted-foreground">{empty}</p>
      )}
    </div>
  );
}

function FinalMarkdownDisclosure({ markdown }: { markdown: string }) {
  return (
    <details className="enterprise-panel group">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 p-5">
        <div>
          <h3 className="text-base font-semibold text-foreground">Полный markdown-отчёт</h3>
          <p className="mt-1 text-sm text-muted-foreground">Техническая версия отчёта скрыта, чтобы не превращать обзор в простыню логов.</p>
        </div>
        <span className="shrink-0 rounded-md border border-border/70 bg-background/45 px-3 py-1.5 text-xs font-medium text-muted-foreground group-open:text-foreground">
          Показать
        </span>
      </summary>
      <div className="border-t border-border/70 p-5 pt-4">
        {markdown ? (
          <div className="prose prose-invert max-w-none prose-headings:tracking-normal prose-p:text-foreground/82 prose-li:text-foreground/82 prose-strong:text-foreground">
            <ReactMarkdown>{markdown}</ReactMarkdown>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">Markdown-отчёт пока недоступен.</p>
        )}
      </div>
    </details>
  );
}

function DeliveryInline({
  report,
  onRetry,
  retrying,
}: {
  report: AgentRunReportResponse;
  onRetry: () => void;
  retrying: boolean;
}) {
  const state = report.delivery_state;
  if (!state) return null;
  const tone = severityTone[state.severity] || "info";
  const canRetry = Boolean(state.enabled && report.report_state?.report_ready && state.status !== "sent");
  return (
    <div className="flex flex-col gap-2 rounded-md border border-border/60 bg-background/35 px-3 py-2 text-sm text-muted-foreground sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <span className="font-medium text-foreground">Доставка отчёта:</span>
        <StatusBadge label={state.label || state.status || "—"} tone={tone} />
        <span className="truncate">
          {state.enabled ? state.description || state.channel || "включена" : "выключена"}
        </span>
      </div>
      {canRetry ? (
        <Button size="sm" variant="outline" className="h-8 shrink-0 gap-1.5" disabled={retrying} onClick={onRetry}>
          {retrying ? <RefreshCw className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          {retrying ? "Отправляем" : "Повторить"}
        </Button>
      ) : null}
    </div>
  );
}

function ExecutionStatePanel({ report }: { report: AgentRunReportResponse }) {
  const state = report.report_state?.execution_state;
  if (!state) return null;
  const workerLabel = state.worker?.worker_key || state.worker?.status || "—";
  const dispatchLabel = state.dispatch?.status || "—";
  return (
    <div className="enterprise-panel p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h3 className="text-base font-semibold text-foreground">Исполнение</h3>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">{state.description}</p>
        </div>
        <StatusBadge label={severityLabel[state.severity] || state.severity} tone={severityTone[state.severity] || "neutral"} />
      </div>

      <dl className="mt-4 grid gap-2 text-xs sm:grid-cols-2">
        <MetaMini label="Dispatch" value={dispatchLabel} />
        <MetaMini label="Worker" value={workerLabel} />
        <MetaMini label="В очереди" value={state.queued_for || "—"} />
        <MetaMini label="Heartbeat" value={state.heartbeat_age || "—"} />
      </dl>

      {state.next_action ? (
        <div className="mt-4 rounded-lg border border-border/70 bg-background/45 p-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Следующее действие</p>
          <p className="mt-1 break-words text-sm leading-6 text-foreground">{state.next_action}</p>
        </div>
      ) : null}
    </div>
  );
}

function MetaMini({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-lg border border-border/70 bg-background/45 p-3">
      <dt className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="mt-1 truncate font-mono text-xs text-foreground">{value || "—"}</dd>
    </div>
  );
}

function ReportStat({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-lg border border-border/70 bg-background/45 p-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-semibold text-foreground">{value}</p>
      <p className="mt-0.5 truncate text-xs text-muted-foreground">{hint}</p>
    </div>
  );
}

function RecentEventsList({ events, empty }: { events: AgentRunReportEvent[]; empty: string }) {
  if (!events.length) {
    return <p className="mt-3 text-sm text-muted-foreground">{empty}</p>;
  }
  return (
    <ol className="mt-4 space-y-2">
      {events.map((event) => (
        <li key={event.id} className="flex gap-3 rounded-lg border border-border/70 bg-background/45 p-3">
          <span className={cn("mt-1 h-2 w-2 shrink-0 rounded-full", eventDot(event.severity))} />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-medium leading-5 text-foreground">{event.title || event.message}</p>
              <StatusBadge label={severityLabel[event.severity]} tone={severityTone[event.severity]} />
            </div>
            {event.summary ? <p className="mt-1 text-xs leading-5 text-muted-foreground">{event.summary}</p> : null}
          </div>
          <span className="shrink-0 text-xs text-muted-foreground">{formatCompactDateTime(event.created_at)}</span>
        </li>
      ))}
    </ol>
  );
}

function EventsTab({ report }: { report: AgentRunReportResponse }) {
  const [filter, setFilter] = useState<AgentRunReportSeverity | "all">("all");
  const [mode, setMode] = useState<"brief" | "all" | "debug">("brief");
  const [query, setQuery] = useState("");
  const [visibleCount, setVisibleCount] = useState(EVENT_PAGE_SIZE);

  const summary = useMemo(() => normalizeEventSummary(report), [report]);
  const phaseMeta = useMemo(() => {
    const map = new Map<string, { label: string; count: number; important: number; problems: number }>();
    for (const group of report.event_groups || []) {
      map.set(String(group.phase || "activity"), {
        label: group.label || eventPhaseLabel[String(group.phase)] || String(group.phase || "activity"),
        count: Number(group.count || group.events?.length || 0),
        important: Number(group.important || 0),
        problems: Number(group.problems || 0),
      });
    }
    return map;
  }, [report.event_groups]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return report.events.filter((event) => {
      if (filter !== "all" && event.severity !== filter) return false;
      if (mode === "brief" && !event.important) return false;
      if (!q) return true;
      return eventSearchText(event).includes(q);
    });
  }, [filter, mode, query, report.events]);

  const visible = filtered.slice(0, visibleCount);
  const hasMore = visible.length < filtered.length;
  const grouped = groupEventsByPhase(visible, phaseMeta);
  const categoryEntries = Object.entries(summary.categories || {});
  const phaseEntries = report.event_groups?.length
    ? report.event_groups
    : grouped.map((group) => ({
        phase: group.phase,
        label: group.label,
        count: group.events.length,
        important: group.events.filter((event) => event.important).length,
        problems: group.events.filter((event) => _severityRank(event.severity) >= _severityRank("warning")).length,
      }));
  const latestImportant = summary.latest_important;

  return (
    <div className="enterprise-panel overflow-hidden">
      <div className="border-b border-border/70 p-4">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <div>
            <h3 className="text-base font-semibold text-foreground">Хронология событий</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              {report.events.length} событий в журнале, показано {visible.length} из {filtered.length}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex flex-wrap items-center gap-1 rounded-lg border border-border/70 bg-background/45 p-1">
              {(["brief", "all", "debug"] as const).map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => {
                    setMode(item);
                    setVisibleCount(EVENT_PAGE_SIZE);
                  }}
                  className={cn(
                    "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                    mode === item ? "bg-card text-foreground" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {eventModeLabel[item]}
                </button>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-1 rounded-lg border border-border/70 bg-background/45 p-1">
              <ListFilter className="ml-1 h-3.5 w-3.5 text-muted-foreground" />
              {(["all", "critical", "high", "warning", "info", "success"] as const).map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => {
                    setFilter(item);
                    setVisibleCount(EVENT_PAGE_SIZE);
                  }}
                  className={cn(
                    "rounded-md px-2 py-1 text-xs font-medium transition-colors",
                    filter === item ? "bg-card text-foreground" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {item === "all" ? "Severity" : severityLabel[item]}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-4 grid gap-3 xl:grid-cols-[minmax(0,1fr)_auto]">
          <div className="relative min-w-0">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setVisibleCount(EVENT_PAGE_SIZE);
              }}
              placeholder="Поиск по событиям, задачам, фазам и payload"
              className="pl-9"
            />
          </div>
          <div className="grid min-w-[360px] grid-cols-3 gap-2 max-sm:min-w-0">
            <EventMiniStat label="Важные" value={summary.important} />
            <EventMiniStat label="Проблемы" value={summary.problems} />
            <EventMiniStat label="Debug" value={summary.debug} />
          </div>
        </div>

        {latestImportant ? (
          <div className="mt-4 rounded-lg border border-border/70 bg-background/45 p-3">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0">
                <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Последний важный сигнал</p>
                <p className="mt-1 break-words text-sm font-medium leading-6 text-foreground">
                  {latestImportant.title || latestImportant.message}
                </p>
                {latestImportant.summary ? <p className="mt-1 max-w-5xl text-xs leading-5 text-muted-foreground">{latestImportant.summary}</p> : null}
              </div>
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                <StatusBadge label={severityLabel[latestImportant.severity]} tone={severityTone[latestImportant.severity]} />
                <span className="whitespace-nowrap text-xs text-muted-foreground">{formatCompactDateTime(latestImportant.created_at)}</span>
              </div>
            </div>
          </div>
        ) : null}

        {phaseEntries.length ? (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {phaseEntries.map((phase) => (
              <span
                key={String(phase.phase)}
                className={cn(
                  "rounded-md border px-2 py-1 text-xs",
                  Number(phase.problems || 0) > 0
                    ? "border-warning/35 bg-warning/10 text-warning"
                    : "border-border/70 bg-background/45 text-muted-foreground",
                )}
              >
                {phase.label || eventPhaseLabel[String(phase.phase)] || String(phase.phase)}: {phase.count}
                {Number(phase.problems || 0) > 0 ? ` · ${phase.problems} проблем` : ""}
              </span>
            ))}
          </div>
        ) : null}

        {categoryEntries.length ? (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {categoryEntries.map(([category, count]) => (
              <span key={category} className="rounded-md border border-border/70 bg-background/45 px-2 py-1 text-xs text-muted-foreground">
                {eventCategoryLabel[category] || category}: {count}
              </span>
            ))}
          </div>
        ) : null}
      </div>

      <div className="p-4">
        {visible.length ? (
          <div className="space-y-5">
            {grouped.map((group) => (
              <section key={group.phase} className="min-w-0">
                <div className="mb-3 flex items-center gap-3">
                  <span className="rounded-md border border-border/70 bg-secondary/45 px-2.5 py-1 text-xs font-semibold text-foreground">
                    {group.label}
                  </span>
                  <span className="font-mono text-xs text-muted-foreground">{group.events.length}</span>
                  <span className="h-px min-w-8 flex-1 bg-border/70" />
                </div>
                <ol className="space-y-0">
                  {group.events.map((event, index) => (
                    <EventTimelineItem
                      key={event.id}
                      event={event}
                      debugOpen={mode === "debug"}
                      showTechnical={mode !== "brief"}
                      last={index === group.events.length - 1}
                    />
                  ))}
                </ol>
              </section>
            ))}
          </div>
        ) : (
          <div className="workspace-empty text-sm text-muted-foreground">
            {mode === "brief" ? "Важных событий пока нет. Переключите на «Все», чтобы увидеть технический журнал." : "События не найдены."}
          </div>
        )}
        {hasMore ? (
          <div className="mt-4 flex justify-center">
            <Button variant="outline" size="sm" onClick={() => setVisibleCount((value) => value + EVENT_PAGE_SIZE)}>
              Показать ещё {Math.min(EVENT_PAGE_SIZE, filtered.length - visible.length)}
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function EventMiniStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border/70 bg-background/45 px-3 py-2">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-0.5 font-mono text-sm font-semibold text-foreground">{value}</p>
    </div>
  );
}

function EventTimelineItem({
  event,
  debugOpen,
  showTechnical,
  last,
}: {
  event: AgentRunReportEvent;
  debugOpen: boolean;
  showTechnical: boolean;
  last: boolean;
}) {
  const hasPayload = Object.keys(event.payload || {}).length > 0;
  const showDetails = showTechnical || debugOpen;
  return (
    <li className="grid grid-cols-[20px_minmax(0,1fr)] gap-3">
      <div className="relative flex justify-center">
        <span className={cn("mt-3 h-2.5 w-2.5 rounded-full ring-4 ring-background", eventDot(event.severity))} />
        {!last ? <span className="absolute top-6 bottom-0 w-px bg-border/70" /> : null}
      </div>
      <article className="mb-3 min-w-0 rounded-lg border border-border/70 bg-background/45 px-4 py-3">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="mb-1.5 flex flex-wrap items-center gap-2">
              <StatusBadge label={severityLabel[event.severity]} tone={severityTone[event.severity]} />
              <span className="rounded-md border border-border/70 bg-card/60 px-2 py-0.5 font-mono text-xs text-muted-foreground">
                {eventCategoryLabel[event.category] || event.category || "event"}
              </span>
              {event.task_id !== null ? <span className="font-mono text-xs text-muted-foreground">task #{event.task_id}</span> : null}
              {event.important ? <span className="text-xs font-medium text-foreground">важное</span> : null}
            </div>
            <p className="break-words text-sm font-medium leading-6 text-foreground">{event.title || event.message}</p>
            {event.summary ? <p className="mt-1 max-w-4xl break-words text-xs leading-5 text-muted-foreground">{event.summary}</p> : null}
          </div>
          <span className="shrink-0 whitespace-nowrap text-xs text-muted-foreground">{formatCompactDateTime(event.created_at)}</span>
        </div>

        {showDetails ? (
          <details className="group mt-2" open={debugOpen}>
            <summary className="inline-flex cursor-pointer list-none items-center gap-2 font-mono text-xs text-muted-foreground hover:text-foreground">
              <span>{event.event_type}</span>
              {hasPayload ? <span className="text-muted-foreground/70">payload</span> : null}
            </summary>
            {hasPayload ? (
              <pre className="mt-2 max-h-56 max-w-full overflow-auto rounded-lg border border-border/70 bg-card/60 p-3 font-mono text-xs leading-5 text-muted-foreground">
                {JSON.stringify(event.payload, null, 2)}
              </pre>
            ) : (
              <p className="mt-2 text-xs text-muted-foreground">Технический payload пуст.</p>
            )}
          </details>
        ) : null}
      </article>
    </li>
  );
}

function eventSearchText(event: AgentRunReportEvent) {
  return [
    event.title,
    event.summary,
    event.message,
    event.event_type,
    event.category,
    event.phase,
    event.source,
    event.task_id,
    JSON.stringify(event.payload || {}),
  ]
    .filter((value) => value !== null && value !== undefined)
    .join("\n")
    .toLowerCase();
}

function normalizeEventSummary(report: AgentRunReportResponse) {
  if (report.event_summary) {
    return {
      total: Number(report.event_summary.total || report.events.length),
      important: Number(report.event_summary.important || 0),
      problems: Number(report.event_summary.problems || 0),
      debug: Number(report.event_summary.debug || 0),
      categories: report.event_summary.categories || {},
      severities: report.event_summary.severities || {},
      latest: report.event_summary.latest || null,
      latest_important: report.event_summary.latest_important || report.event_summary.latest || null,
    };
  }
  const categories: Record<string, number> = {};
  const severities: Record<string, number> = {};
  let important = 0;
  let problems = 0;
  let debug = 0;
  let latestImportant: AgentRunReportEvent | null = null;
  for (const event of report.events) {
    const category = event.category || "agent";
    categories[category] = (categories[category] || 0) + 1;
    severities[event.severity] = (severities[event.severity] || 0) + 1;
    if (event.important) {
      important += 1;
      latestImportant = event;
    }
    if (_severityRank(event.severity) >= _severityRank("warning")) problems += 1;
    if (Object.keys(event.payload || {}).length > 0) debug += 1;
  }
  return {
    total: report.events.length,
    important,
    problems,
    debug,
    categories,
    severities,
    latest: report.events[report.events.length - 1] || null,
    latest_important: latestImportant || report.events[report.events.length - 1] || null,
  };
}

function groupEventsByPhase(
  events: AgentRunReportEvent[],
  phaseMeta: Map<string, { label: string; count: number; important: number; problems: number }>,
) {
  const groups: Array<{ phase: string; label: string; events: AgentRunReportEvent[] }> = [];
  for (const event of events) {
    const phase = event.phase || "activity";
    const current = groups[groups.length - 1];
    if (!current || current.phase !== phase) {
      groups.push({ phase, label: phaseMeta.get(phase)?.label || eventPhaseLabel[phase] || phase, events: [event] });
    } else {
      current.events.push(event);
    }
  }
  return groups;
}

function LogsTab({ report, logs }: { report: AgentRunReportResponse; logs: AgentRunReportLog[] }) {
  const [query, setQuery] = useState("");
  const [wrap, setWrap] = useState(true);
  const [copied, setCopied] = useState<string | null>(null);
  const [visibleCount, setVisibleCount] = useState(LOG_PAGE_SIZE);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return logs;
    return logs.filter((log) => `${log.title}\n${log.command}\n${log.stdout}\n${log.stderr}`.toLowerCase().includes(q));
  }, [logs, query]);
  const visible = filtered.slice(0, visibleCount);
  const hasMore = visible.length < filtered.length;

  const copyLog = async (log: AgentRunReportLog) => {
    await copyText(`$ ${log.command}\n\n${log.stdout || ""}\n${log.stderr || ""}`.trim());
    setCopied(log.id);
    window.setTimeout(() => setCopied(null), 1200);
  };

  return (
    <div className="enterprise-panel overflow-hidden">
      <div className="flex flex-col gap-3 border-b border-border/70 p-4 sm:flex-row sm:items-center">
        <div className="relative min-w-0 flex-1">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setVisibleCount(LOG_PAGE_SIZE);
            }}
            placeholder="Поиск по командам и output"
            className="pl-9"
          />
        </div>
        <Button variant={wrap ? "default" : "outline"} size="sm" className="h-10 gap-1.5" onClick={() => setWrap((value) => !value)}>
          <WrapText className="h-4 w-4" />
          Wrap
        </Button>
      </div>
      <div className="space-y-3 p-4">
        {visible.length ? visible.map((log) => (
          <div key={log.id} className="overflow-hidden rounded-lg border border-border/70 bg-[#0f141c]">
            <div className="flex flex-wrap items-center gap-2 border-b border-white/5 bg-white/[0.03] px-4 py-3">
              <StatusBadge label={log.exit_code === 0 ? "Завершено" : `Код ${log.exit_code}`} tone={log.exit_code === 0 ? "success" : "danger"} />
              <span className="min-w-0 flex-1 break-all font-mono text-xs text-foreground">{log.command || log.title}</span>
              <span className="text-xs text-muted-foreground">{formatDuration(log.duration_ms)}</span>
              <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => void copyLog(log)} aria-label="Copy log">
                {copied === log.id ? <Check className="h-3.5 w-3.5 text-success" /> : <Clipboard className="h-3.5 w-3.5" />}
              </Button>
            </div>
            {log.stdout ? (
              <pre className={cn("max-h-80 overflow-auto px-4 py-3 font-mono text-xs leading-5 text-foreground/80", wrap && "whitespace-pre-wrap")}>
                {log.stdout}
              </pre>
            ) : null}
            {log.stderr ? (
              <pre className={cn("max-h-60 overflow-auto border-t border-destructive/20 px-4 py-3 font-mono text-xs leading-5 text-destructive", wrap && "whitespace-pre-wrap")}>
                {log.stderr}
              </pre>
            ) : null}
          </div>
        )) : <EmptyRunDataPanel report={report} kind="logs" />}
        {hasMore ? (
          <div className="flex justify-center">
            <Button variant="outline" size="sm" onClick={() => setVisibleCount((value) => value + LOG_PAGE_SIZE)}>
              Показать ещё {Math.min(LOG_PAGE_SIZE, filtered.length - visible.length)}
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function ArtifactsTab({ report }: { report: AgentRunReportResponse }) {
  const artifacts = report.artifacts;
  const ready = Boolean(report.artifact_state?.ready ?? report.report_state?.artifacts_ready ?? report.report_state?.report_ready);
  const [downloadError, setDownloadError] = useState("");
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const handleDownload = async (artifact: AgentRunReportArtifact) => {
    setDownloadError("");
    setDownloadingId(artifact.id);
    try {
      await downloadArtifact(artifact);
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : "Не удалось скачать артефакт.");
    } finally {
      setDownloadingId(null);
    }
  };

  const handleDownloadAll = async () => {
    setDownloadError("");
    setDownloadingId("all");
    try {
      const downloadedBundle = await downloadArtifactBundle(report);
      if (!downloadedBundle) {
        for (const artifact of artifacts) {
          await downloadArtifact(artifact);
        }
      }
    } catch (error) {
      setDownloadError(error instanceof Error ? error.message : "Не удалось скачать артефакты.");
    } finally {
      setDownloadingId(null);
    }
  };

  if (!ready) {
    return (
      <div className="enterprise-panel overflow-hidden">
        <div className="border-b border-border/70 p-4">
          <h3 className="text-base font-semibold text-foreground">{report.artifact_state?.title || "Артефакты ещё не готовы"}</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            {report.artifact_state?.description || "Артефакты появятся после финального отчёта."}
          </p>
        </div>
        <div className="workspace-empty m-4 text-sm text-muted-foreground">
          <p className="font-medium text-foreground">{report.artifact_state?.empty_title || "Артефакты появятся после финального отчёта"}</p>
          <p className="mt-1">{report.artifact_state?.empty_description || report.report_state?.next_expected}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="enterprise-panel overflow-hidden">
      <div className="flex items-center justify-between border-b border-border/70 p-4">
        <div>
          <h3 className="text-base font-semibold text-foreground">{report.artifact_state?.title || "Артефакты запуска"}</h3>
          <p className="mt-1 text-sm text-muted-foreground">
            {report.artifact_state?.description || "Файлы собраны из сохранённых данных запуска"}
            {report.artifact_state?.bundle_ready && report.artifact_state?.total_size_label ? (
              <span className="ml-2 text-muted-foreground/80">
                {report.artifact_state.artifact_count || artifacts.length} файлов · {report.artifact_state.total_size_label}
              </span>
            ) : null}
            {report.artifact_state?.manifest_ready ? (
              <span className="ml-2 text-success">manifest проверен</span>
            ) : null}
          </p>
        </div>
        {artifacts.length ? (
          <Button
            size="sm"
            className="h-10 gap-1.5"
            disabled={downloadingId !== null}
            onClick={() => void handleDownloadAll()}
          >
            <Download className="h-4 w-4" />
            {downloadingId === "all" ? "Скачивание" : "Скачать всё"}
          </Button>
        ) : null}
      </div>
      {downloadError ? <div className="border-b border-border/70 px-4 py-3 text-sm text-destructive">{downloadError}</div> : null}
      {artifacts.length ? (
        <ul className="divide-y divide-border/70">
          {artifacts.map((artifact) => (
            <li key={artifact.id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border/70 bg-secondary/45 text-primary">
                {artifact.name.endsWith(".json") ? <FileCode2 className="h-5 w-5" /> : artifact.name.endsWith(".zip") ? <FileArchive className="h-5 w-5" /> : <FileText className="h-5 w-5" />}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="break-all font-mono text-sm font-medium text-foreground">{artifact.name}</span>
                  <span className="rounded-md border border-border/70 bg-background/45 px-2 py-0.5 text-xs text-muted-foreground">{artifact.type}</span>
                  {artifact.truncated ? <span className="text-xs text-warning">truncated</span> : null}
                </div>
                <p className="mt-1 text-sm text-muted-foreground">{artifact.description}</p>
                <p className="mt-1 flex flex-wrap gap-x-3 gap-y-1 font-mono text-xs text-muted-foreground">
                  <span>{artifact.size_label}</span>
                  {artifact.checksum_sha256 ? <span>sha256:{artifact.checksum_sha256.slice(0, 12)}</span> : null}
                </p>
              </div>
              <Button
                size="sm"
                variant="outline"
                className="h-10 gap-1.5"
                disabled={downloadingId !== null}
                onClick={() => void handleDownload(artifact)}
              >
                <Download className="h-4 w-4" />
                {downloadingId === artifact.id ? "Скачивание" : "Скачать"}
              </Button>
            </li>
          ))}
        </ul>
      ) : (
        <div className="workspace-empty m-4 text-sm text-muted-foreground">Артефакты не сформированы.</div>
      )}
    </div>
  );
}

function AgentStepsTab({ report, steps }: { report: AgentRunReportResponse; steps: AgentRunReportStep[] }) {
  const [filter, setFilter] = useState<"all" | "active" | "problems" | "done">("all");
  const [query, setQuery] = useState("");
  const stats = useMemo(() => buildStepStats(steps), [steps]);
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return steps.filter((step) => {
      if (filter === "active" && !stepIsActive(step)) return false;
      if (filter === "problems" && !stepIsProblem(step)) return false;
      if (filter === "done" && !stepIsDone(step)) return false;
      if (!q) return true;
      return stepSearchText(step).includes(q);
    });
  }, [filter, query, steps]);

  return (
    <div className="enterprise-panel overflow-hidden">
      <div className="border-b border-border/70 p-4">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0">
            <h3 className="text-base font-semibold text-foreground">Ход агента</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              {steps.length ? `${stats.done} из ${steps.length} шагов завершено` : "Шаги появятся после планирования или выполнения команд."}
            </p>
          </div>
          {steps.length ? (
            <div className="grid min-w-[420px] grid-cols-4 gap-2 max-sm:min-w-0 max-sm:grid-cols-2">
              <StepMiniStat label="Готово" value={stats.done} />
              <StepMiniStat label="Активно" value={stats.active} />
              <StepMiniStat label="Риски" value={stats.problems} />
              <StepMiniStat label="Прогресс" value={`${stats.progress}%`} />
            </div>
          ) : null}
        </div>

        {steps.length ? (
          <>
            <div className="mt-4">
              <div className="mb-2 flex items-center justify-between gap-3 text-xs text-muted-foreground">
                <span className="truncate">{stats.current?.title || "Все шаги обработаны"}</span>
                <span className="font-mono">{stats.progress}%</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full border border-border/70 bg-background/65">
                <div className="h-full rounded-full bg-info transition-[width]" style={{ width: `${stats.progress}%` }} />
              </div>
            </div>

            <div className="mt-4 overflow-x-auto pb-1">
              <ol className="grid min-w-max auto-cols-[180px] grid-flow-col gap-2">
                {steps.map((step) => (
                  <li key={step.id} className={cn("rounded-lg border p-3", stepRailClass(step))}>
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <span className="font-mono text-xs">{String(step.index).padStart(2, "0")}</span>
                      <span className={cn("h-2 w-2 rounded-full", eventDot(step.severity))} />
                    </div>
                    <p className="line-clamp-2 min-h-10 text-xs font-medium leading-5">{step.title}</p>
                    <p className="mt-1 truncate text-[11px] text-muted-foreground">{step.status_label || step.status}</p>
                  </li>
                ))}
              </ol>
            </div>

            <div className="mt-4 flex flex-col gap-3 xl:flex-row xl:items-center">
              <div className="relative min-w-0 flex-1">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Поиск по шагам, командам и результатам"
                  className="pl-9"
                />
              </div>
              <div className="flex flex-wrap items-center gap-1 rounded-lg border border-border/70 bg-background/45 p-1">
                <ListFilter className="ml-1 h-3.5 w-3.5 text-muted-foreground" />
                {(["all", "active", "problems", "done"] as const).map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => setFilter(item)}
                    className={cn(
                      "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                      filter === item ? "bg-card text-foreground" : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {stepFilterLabel[item]}
                  </button>
                ))}
              </div>
            </div>
          </>
        ) : null}
      </div>

      <div className="p-4">
        {steps.length ? (
          filtered.length ? (
            <ol className="space-y-3">
              {filtered.map((step, index) => (
                <StepTimelineItem key={step.id} step={step} last={index === filtered.length - 1} />
              ))}
            </ol>
          ) : (
            <div className="workspace-empty text-sm text-muted-foreground">Шаги по текущему фильтру не найдены.</div>
          )
        ) : (
          <EmptyRunDataPanel report={report} kind="steps" />
        )}
      </div>
    </div>
  );
}

const stepFilterLabel = {
  all: "Все",
  active: "Активные",
  problems: "Риски",
  done: "Готово",
};

function StepMiniStat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-lg border border-border/70 bg-background/45 px-3 py-2">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-0.5 font-mono text-sm font-semibold text-foreground">{value}</p>
    </div>
  );
}

function StepTimelineItem({ step, last }: { step: AgentRunReportStep; last: boolean }) {
  const hasDetails = Boolean(step.description || step.command || step.details || step.error);
  return (
    <li className="grid grid-cols-[28px_minmax(0,1fr)] gap-3">
      <div className="relative flex justify-center">
        <span className={cn("mt-4 flex h-7 w-7 items-center justify-center rounded-full border bg-background font-mono text-[11px]", stepIndexClass(step))}>
          {step.index}
        </span>
        {!last ? <span className="absolute top-12 bottom-0 w-px bg-border/70" /> : null}
      </div>
      <article className="min-w-0 rounded-lg border border-border/70 bg-background/45">
        <details className="group" open={stepIsActive(step) || stepIsProblem(step)}>
          <summary className="flex cursor-pointer list-none flex-col gap-3 p-4 lg:flex-row lg:items-center">
            <StatusBadge label={step.status_label || step.status} tone={severityTone[step.severity]} />
            <div className="min-w-0 flex-1">
              <p className="break-words text-sm font-medium leading-6 text-foreground">{step.title}</p>
              {step.command ? <p className="truncate font-mono text-xs text-muted-foreground">{step.command}</p> : null}
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2 text-xs text-muted-foreground">
              {step.started_at ? <span>{formatCompactDateTime(step.started_at)}</span> : null}
              <span className="font-mono">{formatDuration(step.duration_ms)}</span>
            </div>
          </summary>

          <div className="border-t border-border/70 p-4">
            {hasDetails ? (
              <>
                {step.description ? <p className="mb-3 text-sm leading-6 text-muted-foreground">{step.description}</p> : null}
                {step.command ? (
                  <pre className="mb-3 max-h-48 overflow-auto rounded-lg border border-border/70 bg-card/65 p-3 font-mono text-xs leading-5 text-primary">
                    {step.command}
                  </pre>
                ) : null}
                {step.details ? (
                  <p className="whitespace-pre-wrap break-words text-sm leading-6 text-foreground/82">{step.details}</p>
                ) : null}
                {step.error ? (
                  <div className="mt-3 rounded-lg border border-destructive/30 bg-destructive/10 p-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-destructive">Ошибка</p>
                    <p className="mt-1 whitespace-pre-wrap break-words text-sm leading-6 text-destructive">{step.error}</p>
                  </div>
                ) : null}
              </>
            ) : (
              <p className="text-sm text-muted-foreground">Детали шага ещё не сохранены.</p>
            )}
          </div>
        </details>
      </article>
    </li>
  );
}

function buildStepStats(steps: AgentRunReportStep[]) {
  const done = steps.filter(stepIsDone).length;
  const active = steps.filter(stepIsActive).length;
  const problems = steps.filter(stepIsProblem).length;
  const current =
    steps.find((step) => step.status === "running" || step.status === "waiting") ||
    steps.find(stepIsProblem) ||
    steps.find((step) => step.status === "pending") ||
    steps[steps.length - 1] ||
    null;
  const progress = steps.length ? Math.round((done / steps.length) * 100) : 0;
  return { done, active, problems, current, progress };
}

function stepIsDone(step: AgentRunReportStep) {
  return ["done", "completed", "success"].includes(step.status) || step.severity === "success";
}

function stepIsProblem(step: AgentRunReportStep) {
  return step.status === "failed" || _severityRank(step.severity) >= _severityRank("warning");
}

function stepIsActive(step: AgentRunReportStep) {
  return ["running", "pending", "waiting", "plan_review"].includes(step.status);
}

function stepSearchText(step: AgentRunReportStep) {
  return [step.title, step.description, step.command, step.status, step.status_label, step.details, step.error]
    .filter(Boolean)
    .join("\n")
    .toLowerCase();
}

function stepRailClass(step: AgentRunReportStep) {
  if (stepIsProblem(step)) return "border-destructive/35 bg-destructive/10 text-destructive";
  if (step.status === "running") return "border-info/35 bg-info/10 text-info";
  if (stepIsDone(step)) return "border-success/35 bg-success/10 text-success";
  return "border-border/70 bg-background/45 text-muted-foreground";
}

function stepIndexClass(step: AgentRunReportStep) {
  if (stepIsProblem(step)) return "border-destructive/40 text-destructive";
  if (step.status === "running") return "border-info/40 text-info";
  if (stepIsDone(step)) return "border-success/40 text-success";
  return "border-border/70 text-muted-foreground";
}

function EmptyRunDataPanel({ report, kind }: { report: AgentRunReportResponse; kind: "logs" | "steps" }) {
  const active = !report.report_state?.is_terminal && !report.report_state?.report_ready;
  const title = kind === "logs" ? "Логи ещё не записаны" : "Шаги агента ещё не сохранены";
  const terminalTitle = kind === "logs" ? "Логи не найдены" : "Шаги агента не найдены";
  const description = active
    ? report.report_state?.next_expected || "Данные появятся после того, как агент начнёт выполнять команды и задачи."
    : "В этом запуске backend не сохранил данные для этой вкладки.";

  return (
    <div className="workspace-empty text-sm text-muted-foreground">
      <p className="font-medium text-foreground">{active ? title : terminalTitle}</p>
      <p className="mt-1 max-w-2xl leading-6">{description}</p>
    </div>
  );
}

function eventDot(severity: AgentRunReportSeverity) {
  switch (severityTone[severity]) {
    case "success":
      return "bg-success";
    case "warning":
      return "bg-warning";
    case "danger":
      return "bg-destructive";
    case "info":
      return "bg-info";
    default:
      return "bg-muted-foreground";
  }
}

function _severityRank(severity: AgentRunReportSeverity) {
  switch (severity) {
    case "success":
      return 0;
    case "info":
      return 1;
    case "warning":
      return 2;
    case "high":
      return 3;
    case "critical":
      return 4;
    case "fatal":
      return 5;
    default:
      return 1;
  }
}

function toneBox(severity: AgentRunReportSeverity) {
  switch (severityTone[severity]) {
    case "success":
      return "border-success/30 bg-success/10 text-success";
    case "warning":
      return "border-warning/35 bg-warning/10 text-warning";
    case "danger":
      return "border-destructive/35 bg-destructive/10 text-destructive";
    case "info":
      return "border-info/35 bg-info/10 text-info";
    default:
      return "border-border/70 bg-secondary/50 text-muted-foreground";
  }
}

function toneBoxFromStatusTone(tone: StatusTone) {
  switch (tone) {
    case "success":
      return "border-success/30 bg-success/10 text-success";
    case "warning":
      return "border-warning/35 bg-warning/10 text-warning";
    case "danger":
      return "border-destructive/35 bg-destructive/10 text-destructive";
    case "info":
      return "border-info/35 bg-info/10 text-info";
    default:
      return "border-border/70 bg-secondary/50 text-muted-foreground";
  }
}
