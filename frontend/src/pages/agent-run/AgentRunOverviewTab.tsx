import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import type { LucideIcon } from "lucide-react";
import { AlertTriangle, CheckCircle2, FileText, RefreshCw, Search } from "lucide-react";

import type { AgentRunReportEvent, AgentRunReportFinding, AgentRunReportResponse } from "@/lib/api";
import type { StatusTone } from "@/design/status";
import { StatusBadge } from "@/components/system/StatusBadge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { formatCompactDateTime, formatDuration } from "./formatters";
import {
  _severityRank,
  cleanInlineMarkdown,
  diagnosticActions,
  diagnosticEvidenceItems,
  diagnosticImpact,
  diagnosticProblem,
  eventDot,
  severityLabel,
  severityTone,
  stripLeadingTitleHeading,
  toneBox,
  toneBoxFromStatusTone,
} from "./reportShared";


export function OverviewTab({
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

