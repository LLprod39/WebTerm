import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { Activity, AlertTriangle, Clipboard, Clock3, FolderArchive, List, MessageSquare, RefreshCw, Send, Server, Shield, Terminal } from "lucide-react";

import type { AgentRunReportResponse } from "@/lib/api";
import type { StatusTone } from "@/design/status";
import { StatusBadge } from "@/components/system/StatusBadge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

import { formatDuration } from "./formatters";
import { _severityRank, reportSignalCount, riskLabel, severityTone, toneBoxFromStatusTone, type ReportTab } from "./reportShared";


export function StateBlock({ title, description, icon, danger = false }: { title: string; description?: string; icon?: ReactNode; danger?: boolean }) {
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

export function PendingQuestionPanel({
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

export function ReportMetricCards({ report }: { report: AgentRunReportResponse }) {
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

export function MetricCard({
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

export function LiveRunBanner({
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

export function LiveMetric({ label, value, tone = "info" }: { label: string; value: string; tone?: StatusTone }) {
  return (
    <div className={cn("min-w-0 rounded-lg border p-3", toneBoxFromStatusTone(tone))}>
      <p className="text-2xs font-semibold uppercase tracking-wide opacity-80">{label}</p>
      <p className="mt-1 truncate font-mono text-sm font-semibold">{value || "—"}</p>
    </div>
  );
}

