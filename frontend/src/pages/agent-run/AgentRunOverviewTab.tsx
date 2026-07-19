import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Clock3,
  FileText,
  ListChecks,
  RefreshCw,
  Server,
} from "lucide-react";

import type { AgentRunReportFinding, AgentRunReportResponse } from "@/lib/api";
import { StatusBadge } from "@/components/system/StatusBadge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { formatDuration } from "./formatters";
import {
  _severityRank,
  actionCount,
  cleanInlineMarkdown,
  diagnosticActions,
  eventDot,
  isMeaningfulReportText,
  primaryOutcomeSummary,
  problemCount,
  severityLabel,
  severityTone,
  stripLeadingTitleHeading,
  toneBox,
} from "./reportShared";

/**
 * «Итог» — first thing the operator sees.
 * Finished: what happened + what to do.
 * Live: what is happening + what to wait for.
 */
export function OverviewTab({
  report,
  onRetryDelivery,
  retryingDelivery,
  onOpenProgress,
  onOpenMaterials,
}: {
  report: AgentRunReportResponse;
  onRetryDelivery: () => void;
  retryingDelivery: boolean;
  onOpenProgress?: () => void;
  onOpenMaterials?: () => void;
}) {
  if (!report.report_state?.report_ready) {
    return (
      <LiveSummary
        report={report}
        onOpenProgress={onOpenProgress}
        onOpenMaterials={onOpenMaterials}
      />
    );
  }

  return <FinishedSummary report={report} onRetryDelivery={onRetryDelivery} retryingDelivery={retryingDelivery} />;
}

function FinishedSummary({
  report,
  onRetryDelivery,
  retryingDelivery,
}: {
  report: AgentRunReportResponse;
  onRetryDelivery: () => void;
  retryingDelivery: boolean;
}) {
  const problems = mergeProblems(report);
  const actions = report.report.recommendations.filter((item) =>
    isMeaningfulReportText(item.description || item.title),
  );
  const fallbackActions = actions.length ? [] : diagnosticActions(report);
  const markdown = stripLeadingTitleHeading(report.report.markdown, report.report.title);
  const nProblems = problemCount(report);
  const nActions = actionCount(report) || fallbackActions.length;

  return (
    <div className="space-y-4">
      {/* One-liner + meta chips */}
      <section className="rounded-sm border border-border bg-card p-5 shadow-elev-1">
        <p className="font-display text-lg font-bold leading-snug tracking-tight text-foreground sm:text-xl">
          {primaryOutcomeSummary(report)}
        </p>
        <div className="mt-4 flex flex-wrap gap-2">
          <MetaChip icon={<Server className="h-3.5 w-3.5" />} label={report.report.meta.server || report.run.server_name || "—"} />
          <MetaChip
            icon={<Clock3 className="h-3.5 w-3.5" />}
            label={report.run.duration_ms > 0 ? formatDuration(report.run.duration_ms) : "—"}
          />
          {nProblems > 0 ? (
            <MetaChip
              icon={<AlertTriangle className="h-3.5 w-3.5" />}
              label={`${nProblems} ${nProblems === 1 ? "проблема" : "проблем"}`}
              tone="warning"
            />
          ) : (
            <MetaChip icon={<CheckCircle2 className="h-3.5 w-3.5" />} label="Без проблем" tone="success" />
          )}
          {nActions > 0 ? (
            <MetaChip icon={<ListChecks className="h-3.5 w-3.5" />} label={`${nActions} действий`} />
          ) : null}
        </div>
      </section>

      {/* What found · What to do */}
      <div className="grid gap-4 lg:grid-cols-2">
        <SimplePanel
          title="Что нашли"
          empty="Критичных находок нет."
          icon={<AlertTriangle className="h-4 w-4" />}
        >
          {problems.length ? (
            <ul className="divide-y divide-border">
              {problems.slice(0, 8).map((item) => (
                <li key={item.id} className="flex gap-3 py-3 first:pt-0 last:pb-0">
                  <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", eventDot(item.severity))} />
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-medium text-foreground">
                        {cleanInlineMarkdown(item.title)}
                      </span>
                      <span className={cn("rounded-sm border px-1.5 py-0.5 text-2xs font-medium", toneBox(item.severity))}>
                        {severityLabel[item.severity]}
                      </span>
                    </div>
                    {item.description && cleanInlineMarkdown(item.description) !== cleanInlineMarkdown(item.title) ? (
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">
                        {cleanInlineMarkdown(item.description)}
                      </p>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          ) : null}
        </SimplePanel>

        <SimplePanel
          title="Что сделать"
          empty="Рекомендаций нет — можно закрыть отчёт."
          icon={<ListChecks className="h-4 w-4" />}
        >
          {actions.length ? (
            <ol className="space-y-0">
              {actions.slice(0, 8).map((item, index) => (
                <li key={item.id} className="flex gap-3 border-b border-border py-3 last:border-b-0 first:pt-0">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-sm border border-primary/35 bg-primary/12 font-mono text-2xs font-semibold text-primary">
                    {index + 1}
                  </span>
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-foreground">
                      {cleanInlineMarkdown(item.title)}
                    </p>
                    {item.description && isMeaningfulReportText(item.description) ? (
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">
                        {cleanInlineMarkdown(item.description)}
                      </p>
                    ) : null}
                  </div>
                </li>
              ))}
            </ol>
          ) : fallbackActions.length ? (
            <ol className="space-y-0">
              {fallbackActions.slice(0, 6).map((text, index) => (
                <li key={`${text}-${index}`} className="flex gap-3 border-b border-border py-3 last:border-b-0 first:pt-0">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-sm border border-primary/35 bg-primary/12 font-mono text-2xs font-semibold text-primary">
                    {index + 1}
                  </span>
                  <p className="text-sm leading-6 text-foreground/90">{text}</p>
                </li>
              ))}
            </ol>
          ) : null}
        </SimplePanel>
      </div>

      <DeliveryLine report={report} onRetry={onRetryDelivery} retrying={retryingDelivery} />

      {/* Details collapsed by default */}
      <details className="group rounded-sm border border-border bg-card shadow-elev-1">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <FileText className="h-4 w-4 text-muted-foreground" />
            <div>
              <p className="text-sm font-semibold text-foreground">Полный текст отчёта</p>
              <p className="text-2xs text-muted-foreground">Markdown от агента — только если нужен полный контекст</p>
            </div>
          </div>
          <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
        </summary>
        <div className="border-t border-border px-5 py-4">
          {markdown ? (
            <div className="prose prose-invert max-w-none prose-sm prose-p:text-foreground/85 prose-li:text-foreground/85 prose-headings:text-foreground">
              <ReactMarkdown>{markdown}</ReactMarkdown>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Текст отчёта пока недоступен.</p>
          )}
        </div>
      </details>
    </div>
  );
}

function LiveSummary({
  report,
  onOpenProgress,
  onOpenMaterials,
}: {
  report: AgentRunReportResponse;
  onOpenProgress?: () => void;
  onOpenMaterials?: () => void;
}) {
  const progress = Math.max(0, Math.min(100, Number(report.report_state?.progress || 0)));
  const current = report.report_state?.current_step || report.report_state?.headline || "Агент работает";
  const next = report.report_state?.next_expected || "";
  const important = report.events.filter((e) => e.important).slice(-5).reverse();
  const stale = report.report_state?.execution_state?.is_stale_candidate;
  const exec = report.report_state?.execution_state;

  return (
    <div className="space-y-4">
      <section className="rounded-sm border border-border bg-card p-5 shadow-elev-1">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge label="В работе" tone="info" pulse />
          {stale ? <StatusBadge label="Возможно завис" tone="warning" /> : null}
        </div>
        <h2 className="mt-3 font-display text-lg font-bold tracking-tight text-foreground sm:text-xl">
          {current}
        </h2>
        {report.report_state?.description ? (
          <p className="mt-2 max-w-3xl text-sm leading-6 text-muted-foreground">
            {report.report_state.description}
          </p>
        ) : null}

        <div className="mt-5">
          <div className="mb-1.5 flex items-center justify-between text-2xs text-muted-foreground">
            <span>Прогресс</span>
            <span className="font-mono">{progress}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-sm border border-border bg-surface-0">
            <div
              className="h-full bg-primary transition-[width] duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>

        {next ? (
          <p className="mt-4 rounded-sm border border-border bg-surface-0 px-3 py-2.5 text-sm text-muted-foreground">
            <span className="font-medium text-foreground">Дальше: </span>
            {next}
          </p>
        ) : null}

        <div className="mt-4 flex flex-wrap gap-2">
          {onOpenProgress ? (
            <Button type="button" size="sm" variant="outline" onClick={onOpenProgress}>
              Ход работы
            </Button>
          ) : null}
          {onOpenMaterials ? (
            <Button type="button" size="sm" variant="ghost" onClick={onOpenMaterials}>
              События и логи
            </Button>
          ) : null}
        </div>
      </section>

      {important.length ? (
        <section className="rounded-sm border border-border bg-card p-5 shadow-elev-1">
          <h3 className="text-sm font-semibold text-foreground">Последнее важное</h3>
          <ol className="mt-3 space-y-2">
            {important.map((event) => (
              <li key={event.id} className="flex gap-3 border-b border-border/70 py-2.5 last:border-0">
                <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", eventDot(event.severity))} />
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-foreground">{event.title || event.message}</p>
                  {event.summary ? (
                    <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2">{event.summary}</p>
                  ) : null}
                </div>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {/* Technical only when something is wrong with execution */}
      {exec && (stale || exec.severity === "critical" || exec.severity === "fatal" || exec.severity === "warning" || exec.severity === "high") ? (
        <details className="rounded-sm border border-border bg-card p-4 text-sm shadow-elev-1">
          <summary className="cursor-pointer font-medium text-muted-foreground">
            Техническое (исполнение)
          </summary>
          <p className="mt-3 text-muted-foreground">{exec.description}</p>
          {exec.next_action ? (
            <p className="mt-2 text-foreground">
              <span className="text-muted-foreground">Действие: </span>
              {exec.next_action}
            </p>
          ) : null}
        </details>
      ) : null}
    </div>
  );
}

function mergeProblems(report: AgentRunReportResponse): AgentRunReportFinding[] {
  const fromFindings = report.report.findings.filter(
    (item) => isMeaningfulReportText(item.title || item.description) && _severityRank(item.severity) >= _severityRank("warning"),
  );
  const fromRisks = report.report.risks.filter((item) => isMeaningfulReportText(item.title || item.description));
  const seen = new Set<string>();
  const out: AgentRunReportFinding[] = [];
  for (const item of [...fromFindings, ...fromRisks].sort(
    (a, b) => _severityRank(b.severity) - _severityRank(a.severity),
  )) {
    const key = cleanInlineMarkdown(item.title || item.description);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(item);
  }
  // If no severe findings, still show mild findings as "what we found"
  if (!out.length) {
    return report.report.findings.filter((item) => isMeaningfulReportText(item.title || item.description)).slice(0, 6);
  }
  return out;
}

function SimplePanel({
  title,
  empty,
  icon,
  children,
}: {
  title: string;
  empty: string;
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-sm border border-border bg-card p-5 shadow-elev-1">
      <div className="mb-3 flex items-center gap-2">
        <span className="text-primary">{icon}</span>
        <h3 className="font-display text-sm font-bold tracking-tight text-foreground">{title}</h3>
      </div>
      {children ?? <p className="text-sm text-muted-foreground">{empty}</p>}
    </section>
  );
}

function MetaChip({
  icon,
  label,
  tone = "neutral",
}: {
  icon: ReactNode;
  label: string;
  tone?: "neutral" | "success" | "warning";
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-sm border px-2.5 py-1 text-2xs font-medium",
        tone === "success" && "border-success/30 bg-success/10 text-success",
        tone === "warning" && "border-warning/35 bg-warning/10 text-warning",
        tone === "neutral" && "border-border bg-surface-0 text-muted-foreground",
      )}
    >
      {icon}
      <span className="max-w-[14rem] truncate">{label}</span>
    </span>
  );
}

function DeliveryLine({
  report,
  onRetry,
  retrying,
}: {
  report: AgentRunReportResponse;
  onRetry: () => void;
  retrying: boolean;
}) {
  const state = report.delivery_state;
  if (!state || !state.enabled) {
    return (
      <p className="text-2xs text-muted-foreground">
        Доставка отчёта (Telegram и др.) не настроена.
      </p>
    );
  }
  const tone = severityTone[state.severity] || "info";
  const canRetry = Boolean(report.report_state?.report_ready && state.status !== "sent");
  return (
    <div className="flex flex-col gap-2 rounded-sm border border-border bg-surface-0 px-3 py-2.5 text-sm sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        <span className="text-muted-foreground">Доставка:</span>
        <StatusBadge label={state.label || state.status || "—"} tone={tone} />
        <span className="truncate text-muted-foreground">{state.description || state.channel || ""}</span>
      </div>
      {canRetry ? (
        <Button size="sm" variant="outline" className="h-8 shrink-0 gap-1.5" disabled={retrying} onClick={onRetry}>
          {retrying ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
          Повторить
        </Button>
      ) : null}
    </div>
  );
}
