import { Link } from "react-router-dom";
import { ArrowRight, ExternalLink, RotateCcw, Settings2 } from "lucide-react";

import { StatusBadge } from "@/components/system/StatusBadge";
import { Button } from "@/components/ui/button";

import type { PreparedReportMutation } from "./useAgentRunReportController";
import type { ReportActionViewModel, ReportFindingViewModel, ReportViewModel } from "./reportViewModel";

const severityLabels: Record<string, string> = { success: "Норма", info: "Информация", warning: "Предупреждение", high: "Высокий риск", critical: "Критично", fatal: "Критично" };
const confidenceLabels: Record<string, string> = { reported: "Сообщено агентом", derived: "Выведено из данных" };
const priorityLabels: Record<string, string> = { P0: "Срочно", P1: "Важно", P2: "Планово", high: "Важно", medium: "Планово", low: "По возможности" };

function humanLabel(value: string) {
  return value.replace(/[_-]+/g, " ").replace(/^./, (letter) => letter.toLocaleUpperCase("ru-RU"));
}

function EvidenceLinks({ items }: { items: ReportFindingViewModel["evidence"] | ReportActionViewModel["evidence"] }) {
  if (!items.length) return null;
  return (
    <div className="mt-3 flex flex-wrap gap-2" aria-label="Связанные доказательства">
      {items.map((item) => (
        <Link
          key={`${item.kind}-${item.id}`}
          to={item.href}
          className="inline-flex min-h-8 items-center gap-1.5 rounded-sm border border-border bg-surface-0 px-2.5 py-1 text-xs font-medium text-muted-foreground hover:border-primary/40 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {item.label}
          <ArrowRight className="h-3.5 w-3.5" aria-hidden />
        </Link>
      ))}
    </div>
  );
}

function FindingCard({ item }: { item: ReportFindingViewModel }) {
  return (
    <article data-testid="report-finding" className="grid gap-3 rounded-sm border border-border bg-card p-4 shadow-elev-1 xl:grid-cols-[minmax(0,1fr)_9rem_12rem_minmax(10rem,0.55fr)] xl:items-start">
      <div className="min-w-0">
        <h3 className="font-semibold leading-6 text-foreground">{item.title}</h3>
        {item.summary ? <p className="mt-1 text-sm leading-6 text-muted-foreground">{item.summary}</p> : null}
        {item.details ? <p className="mt-1 text-sm leading-6 text-foreground/90">{item.details}</p> : null}
      </div>
      <div><p className="mb-1 text-xs text-muted-foreground xl:hidden">Важность</p><StatusBadge label={severityLabels[item.severity] || humanLabel(item.severity)} tone={item.tone} /></div>
      <dl className="space-y-1 text-xs"><div><dt className="text-muted-foreground">Область</dt><dd className="mt-0.5 font-medium text-foreground/80">{item.scope ? humanLabel(item.scope) : "Не указана"}</dd></div><div><dt className="text-muted-foreground">Основание</dt><dd className="mt-0.5 font-medium text-foreground/80">{confidenceLabels[item.confidence] || (item.confidence ? humanLabel(item.confidence) : "Не указано")}</dd></div></dl>
      <div className="min-w-0"><p className="text-xs text-muted-foreground">Доказательства</p><EvidenceLinks items={item.evidence} /></div>
    </article>
  );
}

function ActionCard({ item, prepare }: { item: ReportActionViewModel; prepare: (kind: PreparedReportMutation) => void }) {
  const cta = item.cta;
  return (
    <article data-testid="report-action" className="grid gap-3 rounded-sm border border-border bg-card p-4 shadow-elev-1 xl:grid-cols-[minmax(0,1fr)_9rem_12rem_minmax(10rem,0.55fr)] xl:items-start">
      <div className="min-w-0">
        <h3 className="font-semibold leading-6 text-foreground">{item.title}</h3>
        {item.summary ? <p className="mt-1 text-sm leading-6 text-muted-foreground">{item.summary}</p> : null}
      </div>
      <div><p className="mb-1 text-xs text-muted-foreground xl:hidden">Приоритет</p><span className="inline-flex min-h-7 items-center rounded-sm border border-border bg-surface-0 px-2 py-1 text-xs font-semibold text-muted-foreground">{priorityLabels[item.priority] || (item.priority ? humanLabel(item.priority) : "Следующий шаг")}</span></div>
      <div className="text-xs"><p className="text-muted-foreground">Ответственный</p><p className="mt-1 font-medium text-foreground/80">{item.owner ? humanLabel(item.owner) : "Оператор"}</p></div>
      <div className="min-w-0"><p className="text-xs text-muted-foreground">Действие</p>{cta.enabled && cta.kind === "retry_delivery" ? (
        <Button type="button" size="sm" variant="outline" className="mt-3 gap-1.5" onClick={() => prepare("retry-delivery")}>
          <RotateCcw className="h-4 w-4" aria-hidden />
          {cta.label || "Повторить доставку"}
        </Button>
      ) : cta.enabled && cta.target && !cta.requiresConfirmation ? (
        <Button size="sm" variant="outline" className="mt-3 gap-1.5" asChild>
          <Link to={cta.target}>
            {cta.label || "Открыть"}
            <ExternalLink className="h-4 w-4" aria-hidden />
          </Link>
        </Button>
      ) : cta.requiresConfirmation ? (
        <p className="mt-3 text-xs font-medium text-warning">Действие требует отдельного подтверждения оператора.</p>
      ) : <EvidenceLinks items={item.evidence} />}</div>
    </article>
  );
}

export function AgentRunResultV2({ viewModel, prepare }: { viewModel: ReportViewModel; prepare: (kind: PreparedReportMutation) => void }) {
  return (
    <div className="space-y-5">
      <section aria-labelledby="decision-brief-heading" className="rounded-sm border border-border bg-card p-4 shadow-elev-1">
        <h2 id="decision-brief-heading" className="font-display text-sm font-semibold text-foreground">Краткий вывод</h2>
        <p className="mt-2 max-w-4xl text-sm leading-6 text-muted-foreground">{viewModel.header.summary}</p>
      </section>

      {viewModel.indicators.length ? (
        <section aria-labelledby="indicators-heading">
          <div className="mb-2 flex items-center justify-between gap-3">
            <h2 id="indicators-heading" className="font-display text-base font-semibold text-foreground">Ключевые показатели</h2>
            <span className="text-xs text-muted-foreground">Показано {viewModel.indicators.length} из максимум 4</span>
          </div>
          <dl data-testid="report-indicators" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {viewModel.indicators.map((indicator) => (
              <div key={`${indicator.role}-${indicator.id}`} className="rounded-sm border border-border bg-card p-3 shadow-elev-1">
                <dt className="text-xs font-medium text-muted-foreground">{indicator.label}</dt>
                <dd className="mt-1 break-words text-lg font-semibold text-foreground">{indicator.value || "—"}{indicator.hint ? <span className="mt-1 block text-xs font-normal leading-5 text-muted-foreground">{indicator.hint}</span> : null}</dd>
              </div>
            ))}
          </dl>
        </section>
      ) : null}

      <div className="space-y-5">
        <section aria-labelledby="findings-heading" className="space-y-3">
          <div className="flex items-baseline justify-between gap-3">
            <h2 id="findings-heading" className="font-display text-base font-semibold text-foreground">Что важно</h2>
            <span className="text-xs text-muted-foreground">{viewModel.findings.length}</span>
          </div>
          {viewModel.findings.length ? viewModel.findings.map((item) => <FindingCard key={item.id} item={item} />) : (
            <div className="rounded-sm border border-dashed border-border p-5 text-sm text-muted-foreground">Значимых находок не выделено.</div>
          )}
        </section>

        <section aria-labelledby="actions-heading" className="space-y-3">
          <div className="flex items-baseline justify-between gap-3">
            <h2 id="actions-heading" className="font-display text-base font-semibold text-foreground">Что делать</h2>
            <span className="text-xs text-muted-foreground">{viewModel.actions.length}</span>
          </div>
          {viewModel.actions.length ? viewModel.actions.map((item) => <ActionCard key={item.id} item={item} prepare={prepare} />) : (
            <div className="rounded-sm border border-dashed border-border p-5 text-sm text-muted-foreground">Следующих действий нет.</div>
          )}
        </section>
      </div>

      {(viewModel.delivery.enabled || viewModel.delivery.status || viewModel.delivery.blockedReason) ? (
        <section aria-labelledby="delivery-heading" className="flex flex-col gap-3 rounded-sm border border-border bg-card p-4 shadow-elev-1 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 id="delivery-heading" className="font-semibold text-foreground">Доставка отчёта</h2>
              <StatusBadge label={viewModel.delivery.label || viewModel.delivery.status || "Не настроена"} tone={viewModel.delivery.tone} />
            </div>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">{viewModel.delivery.summary || viewModel.delivery.blockedReason || viewModel.delivery.nextAction}</p>
          </div>
          {viewModel.delivery.canRetry ? (
            <Button type="button" size="sm" variant="outline" className="shrink-0 gap-1.5" onClick={() => prepare("retry-delivery")}>
              <RotateCcw className="h-4 w-4" aria-hidden />
              Повторить
            </Button>
          ) : viewModel.delivery.blockedReason || !viewModel.delivery.enabled ? (
            <Button size="sm" variant="outline" className="shrink-0 gap-1.5" asChild>
              <Link to={viewModel.delivery.setupUrl || "/settings/notifications"}>
                <Settings2 className="h-4 w-4" aria-hidden />
                Настроить Telegram
              </Link>
            </Button>
          ) : null}
        </section>
      ) : null}

      <footer className="rounded-sm border border-border bg-surface-0 p-4" aria-label="Происхождение отчёта">
        <dl className="grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-4">
          <div><dt className="text-muted-foreground">Период</dt><dd className="mt-1 font-medium text-foreground">{viewModel.run.startedAt ? new Intl.DateTimeFormat("ru-RU", { dateStyle: "short", timeStyle: "short" }).format(new Date(viewModel.run.startedAt)) : "—"} — {viewModel.run.completedAt ? new Intl.DateTimeFormat("ru-RU", { timeStyle: "short" }).format(new Date(viewModel.run.completedAt)) : "сейчас"}</dd></div>
          <div><dt className="text-muted-foreground">Сформирован</dt><dd className="mt-1 font-medium text-foreground">{viewModel.provenance.generatedAt ? new Intl.DateTimeFormat("ru-RU", { dateStyle: "short", timeStyle: "short" }).format(new Date(viewModel.provenance.generatedAt)) : "—"}</dd></div>
          <div><dt className="text-muted-foreground">Режим агента</dt><dd className="mt-1 font-medium text-foreground">{viewModel.run.agentMode ? humanLabel(viewModel.run.agentMode) : "—"}</dd></div>
          <div><dt className="text-muted-foreground">Полнота</dt><dd className="mt-1 font-medium text-foreground">{viewModel.axes.find((axis) => axis.id === "evidence")?.value || "Не указана"}</dd></div>
        </dl>
        <details className="mt-3 border-t border-border pt-3"><summary className="cursor-pointer text-xs font-medium text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">Техническое происхождение</summary><dl className="mt-3 grid gap-3 text-xs sm:grid-cols-2 lg:grid-cols-4"><div><dt className="text-muted-foreground">Источник</dt><dd className="mt-1 break-all font-mono text-foreground">{viewModel.provenance.source || "—"}</dd></div><div><dt className="text-muted-foreground">Ревизия</dt><dd className="mt-1 break-all font-mono text-foreground">{viewModel.provenance.revision || "—"}</dd></div><div><dt className="text-muted-foreground">Граница событий</dt><dd className="mt-1 break-all font-mono text-foreground">{viewModel.provenance.eventWatermark || "—"}</dd></div><div><dt className="text-muted-foreground">SHA-256</dt><dd className="mt-1 break-all font-mono text-foreground">{viewModel.provenance.checksum || "—"}</dd></div></dl></details>
      </footer>
    </div>
  );
}
