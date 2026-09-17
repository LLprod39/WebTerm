import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  FileText,
  ListChecks,
} from "lucide-react";

import type { AgentRunReportBlock } from "@/api/agent-report-v2-types";
import { Sparkline } from "@/components/dashboard/Sparkline";
import { cn } from "@/lib/utils";

import { cleanInlineMarkdown, stripLeadingTitleHeading } from "./reportShared";
import { stripReportBlocksFence } from "./reportBlocks";

const severityLabels: Record<string, string> = {
  success: "Норма",
  info: "Инфо",
  warning: "Внимание",
  high: "Важно",
  critical: "Критично",
  fatal: "Критично",
  ok: "Норма",
  warn: "Важно",
  danger: "Критично",
};

const severityDot: Record<string, string> = {
  success: "bg-success",
  info: "bg-info",
  warning: "bg-warning",
  high: "bg-warning",
  critical: "bg-destructive",
  fatal: "bg-destructive",
  ok: "bg-success",
  warn: "bg-warning",
  danger: "bg-destructive",
};

const barTone: Record<string, string> = {
  success: "bg-success",
  ok: "bg-success",
  info: "bg-info",
  warning: "bg-warning",
  high: "bg-warning",
  warn: "bg-warning",
  critical: "bg-destructive",
  danger: "bg-destructive",
  fatal: "bg-destructive",
};

/**
 * Renders composable report blocks. Agent chooses which widgets to emit;
 * UI stays one shell — different tasks just ship different block lists.
 */
export function ReportBlocks({
  blocks,
  documentTitle,
  runId,
  documentHref,
}: {
  blocks: AgentRunReportBlock[];
  documentTitle?: string;
  runId?: number;
  documentHref?: string;
}) {
  if (!blocks.length) return null;

  const halfPair: AgentRunReportBlock[] = [];
  const nodes: ReactNode[] = [];

  const flushPair = () => {
    if (!halfPair.length) return;
    nodes.push(
      <div key={`pair-${halfPair.map((b) => b.id).join("-")}`} className="grid gap-4 lg:grid-cols-2">
        {halfPair.map((block) => (
          <div key={block.id}>{renderBlock(block, { documentTitle, runId, documentHref })}</div>
        ))}
      </div>,
    );
    halfPair.length = 0;
  };

  blocks.forEach((block) => {
    if (block.span === "half" && (block.type === "findings" || block.type === "actions" || block.type === "callout" || block.type === "kv")) {
      halfPair.push(block);
      if (halfPair.length === 2) flushPair();
      return;
    }
    flushPair();
    nodes.push(
      <div key={block.id}>{renderBlock(block, { documentTitle, runId, documentHref })}</div>,
    );
  });
  flushPair();

  return (
    <div className="space-y-4" data-testid="report-blocks">
      {nodes}
    </div>
  );
}

function renderBlock(
  block: AgentRunReportBlock,
  ctx: { documentTitle?: string; runId?: number; documentHref?: string },
) {
  switch (block.type) {
    case "verdict":
      return <VerdictBlock block={block} />;
    case "metrics":
      return <MetricsBlock block={block} />;
    case "findings":
      return <FindingsBlock block={block} />;
    case "actions":
      return <ActionsBlock block={block} />;
    case "before_after":
      return <BeforeAfterBlock block={block} />;
    case "bars":
      return <BarsBlock block={block} />;
    case "chart":
      return <ChartBlock block={block} />;
    case "kv":
      return <KvBlock block={block} />;
    case "table":
      return <TableBlock block={block} />;
    case "callout":
      return <CalloutBlock block={block} />;
    case "checklist":
      return <ChecklistBlock block={block} />;
    case "done_steps":
      return <DoneStepsBlock block={block} />;
    case "code":
      return <CodeBlock block={block} />;
    case "markdown":
      return <MarkdownBlock block={block} documentTitle={ctx.documentTitle} documentHref={ctx.documentHref} />;
    default:
      return null;
  }
}

function VerdictBlock({ block }: { block: AgentRunReportBlock }) {
  return (
    <section className="rounded-sm border border-border bg-card p-5 shadow-elev-1" data-block="verdict">
      {block.title ? <p className="mb-2 text-2xs font-medium uppercase tracking-wider text-muted-foreground">{block.title}</p> : null}
      <p className="font-display text-lg font-bold leading-snug tracking-tight text-foreground sm:text-xl">
        {cleanInlineMarkdown(block.text || "")}
      </p>
    </section>
  );
}

function MetricsBlock({ block }: { block: AgentRunReportBlock }) {
  const items = (block.items || []).slice(0, 4) as Array<{ label?: string; value?: string; hint?: string }>;
  if (!items.length) return null;
  return (
    <dl className="grid gap-px overflow-hidden rounded-sm border border-border bg-border sm:grid-cols-2 lg:grid-cols-4" data-block="metrics">
      {items.map((item, i) => (
        <div key={`${item.label}-${i}`} className="min-w-0 bg-surface-0 px-3 py-2.5">
          <dt className="truncate text-2xs text-muted-foreground">{item.label}</dt>
          <dd className="mt-0.5 truncate font-mono text-sm font-semibold text-foreground">{item.value}</dd>
          {item.hint ? <p className="mt-0.5 truncate text-2xs text-muted-foreground">{item.hint}</p> : null}
        </div>
      ))}
    </dl>
  );
}

function FindingsBlock({ block }: { block: AgentRunReportBlock }) {
  const items = (block.items || []) as Array<{ title?: string; summary?: string; tone?: string; meta?: string }>;
  return (
    <Panel title={block.title || "Что нашли"} count={items.length} icon={<AlertTriangle className="h-4 w-4" />} empty="Критичных находок нет.">
      {items.length ? (
        <ul className="divide-y divide-border">
          {items.map((item, i) => (
            <li key={`${item.title}-${i}`} className="flex gap-3 py-3 first:pt-0 last:pb-0">
              <span className={cn("mt-1.5 h-2 w-2 shrink-0 rounded-full", severityDot[item.tone || ""] || "bg-muted-foreground")} aria-hidden />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-foreground">{cleanInlineMarkdown(item.title || "")}</span>
                  {item.tone || item.meta ? (
                    <span className="rounded-sm border border-border px-1.5 py-0.5 text-2xs font-medium text-muted-foreground">
                      {severityLabels[item.tone || ""] || item.meta || item.tone}
                    </span>
                  ) : null}
                </div>
                {item.summary ? <p className="mt-1 text-xs leading-5 text-muted-foreground">{cleanInlineMarkdown(item.summary)}</p> : null}
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </Panel>
  );
}

function ActionsBlock({ block }: { block: AgentRunReportBlock }) {
  const items = (block.items || []) as Array<{ title?: string; summary?: string }>;
  return (
    <Panel title={block.title || "Что сделать"} count={items.length} icon={<ListChecks className="h-4 w-4" />} empty="Рекомендаций нет — можно закрыть отчёт.">
      {items.length ? (
        <ol>
          {items.map((item, i) => (
            <li key={`${item.title}-${i}`} className="flex gap-3 border-b border-border py-3 first:pt-0 last:border-b-0">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-sm border border-primary/35 bg-primary/12 font-mono text-2xs font-semibold text-primary">
                {i + 1}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-foreground">{cleanInlineMarkdown(item.title || "")}</p>
                {item.summary ? <p className="mt-1 text-xs leading-5 text-muted-foreground">{cleanInlineMarkdown(item.summary)}</p> : null}
              </div>
            </li>
          ))}
        </ol>
      ) : null}
    </Panel>
  );
}

function BeforeAfterBlock({ block }: { block: AgentRunReportBlock }) {
  return (
    <section className="rounded-sm border border-border bg-card p-5 shadow-elev-1" data-block="before_after">
      {block.title ? <h2 className="mb-3 font-display text-sm font-bold tracking-tight text-foreground">{block.title}</h2> : null}
      <div className="grid gap-3 sm:grid-cols-[1fr_auto_1fr] sm:items-center">
        <div className="rounded-sm border border-border bg-surface-0 px-4 py-3">
          <p className="text-2xs uppercase tracking-wider text-muted-foreground">{block.before?.label || "Было"}</p>
          <p className="mt-1 font-mono text-base font-semibold text-foreground">{block.before?.value}</p>
        </div>
        <ArrowRight className="mx-auto hidden h-4 w-4 text-muted-foreground sm:block" aria-hidden />
        <div className="rounded-sm border border-border bg-surface-0 px-4 py-3">
          <p className="text-2xs uppercase tracking-wider text-muted-foreground">{block.after?.label || "Стало"}</p>
          <p className="mt-1 font-mono text-base font-semibold text-foreground">{block.after?.value}</p>
        </div>
      </div>
    </section>
  );
}

function BarsBlock({ block }: { block: AgentRunReportBlock }) {
  const items = (block.items || []).slice(0, 6) as Array<{ label?: string; value?: number; max?: number; unit?: string; tone?: string }>;
  return (
    <section className="rounded-sm border border-border bg-card p-5 shadow-elev-1" data-block="bars">
      {block.title ? <h2 className="mb-3 font-display text-sm font-bold tracking-tight text-foreground">{block.title}</h2> : null}
      <ul className="space-y-3">
        {items.map((item, i) => {
          const max = item.max && item.max > 0 ? item.max : 100;
          const value = Math.max(0, Number(item.value) || 0);
          const pct = Math.min(100, Math.round((value / max) * 100));
          return (
            <li key={`${item.label}-${i}`}>
              <div className="mb-1 flex items-baseline justify-between gap-2">
                <span className="text-sm text-foreground">{item.label}</span>
                <span className="font-mono text-xs text-muted-foreground">
                  {value}
                  {item.unit || ""}
                </span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-border" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
                <div className={cn("h-full rounded-full transition-[width]", barTone[item.tone || ""] || "bg-primary")} style={{ width: `${pct}%` }} />
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function ChartBlock({ block }: { block: AgentRunReportBlock }) {
  const series = (block.series || []).filter((n) => Number.isFinite(n));
  if (series.length < 2) return null;
  const last = series[series.length - 1];
  const min = Math.min(...series);
  const max = Math.max(...series);
  const fmt = (n: number) => {
    const v = Math.abs(n) < 10 ? n.toFixed(1) : String(Math.round(n));
    return block.unit === "%" ? `${v}%` : block.unit ? `${v} ${block.unit}` : v;
  };
  return (
    <figure className="overflow-hidden rounded-sm border border-border bg-card shadow-elev-1" data-block="chart">
      <figcaption className="flex flex-wrap items-start justify-between gap-3 border-b border-border px-5 py-4">
        <div className="min-w-0">
          <h2 className="font-display text-sm font-bold tracking-tight text-foreground">{block.title || "Метрика"}</h2>
          <p className="mt-1 text-2xs text-muted-foreground">
            {block.summary || `Диапазон ${fmt(min)} — ${fmt(max)}`}
          </p>
        </div>
        <div className="text-right">
          <p className="text-2xs uppercase tracking-wider text-muted-foreground">Сейчас</p>
          <p className="font-mono text-xl font-semibold tabular-nums text-foreground">{fmt(last)}</p>
        </div>
      </figcaption>
      <div className="px-5 py-4 text-primary">
        <Sparkline data={series} height={88} width={560} strokeWidth={1.75} className="h-20 w-full" />
      </div>
    </figure>
  );
}

function KvBlock({ block }: { block: AgentRunReportBlock }) {
  const items = (block.items || []) as Array<{ key?: string; value?: string }>;
  return (
    <section className="rounded-sm border border-border bg-card p-5 shadow-elev-1" data-block="kv">
      {block.title ? <h2 className="mb-3 font-display text-sm font-bold tracking-tight text-foreground">{block.title}</h2> : null}
      <dl className="grid gap-2 sm:grid-cols-2">
        {items.map((item, i) => (
          <div key={`${item.key}-${i}`} className="min-w-0 rounded-sm border border-border bg-surface-0 px-3 py-2">
            <dt className="truncate text-2xs text-muted-foreground">{item.key}</dt>
            <dd className="mt-0.5 truncate font-mono text-sm text-foreground">{item.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function TableBlock({ block }: { block: AgentRunReportBlock }) {
  const columns = block.columns || [];
  const rows = (block.rows || []).map((row) => (Array.isArray(row) ? row : (row as { cells?: string[] }).cells || []));
  return (
    <section className="overflow-hidden rounded-sm border border-border bg-card shadow-elev-1" data-block="table">
      {block.title ? <h2 className="border-b border-border px-5 py-3 font-display text-sm font-bold tracking-tight text-foreground">{block.title}</h2> : null}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[28rem] text-left text-sm">
          {columns.length ? (
            <thead>
              <tr className="border-b border-border bg-surface-0 text-2xs uppercase tracking-wider text-muted-foreground">
                {columns.map((col) => (
                  <th key={col} className="px-4 py-2.5 font-medium">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
          ) : null}
          <tbody>
            {rows.map((cells, i) => (
              <tr key={i} className="border-b border-border last:border-b-0">
                {cells.map((cell, j) => (
                  <td key={j} className={cn("px-4 py-2.5 text-foreground/90", j === 0 ? "font-medium" : "font-mono text-xs")}>
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function CalloutBlock({ block }: { block: AgentRunReportBlock }) {
  const tone = String(block.tone || "info");
  return (
    <aside
      className={cn(
        "rounded-sm border px-4 py-3 text-sm leading-6",
        tone === "warning" || tone === "warn" || tone === "high"
          ? "border-warning/35 bg-warning/10 text-foreground"
          : tone === "critical" || tone === "danger" || tone === "fatal"
            ? "border-destructive/35 bg-destructive/10 text-foreground"
            : tone === "success" || tone === "ok"
              ? "border-success/30 bg-success/10 text-foreground"
              : "border-border bg-surface-0 text-foreground/90",
      )}
      data-block="callout"
    >
      {block.title ? <p className="mb-1 text-2xs font-semibold uppercase tracking-wider text-muted-foreground">{block.title}</p> : null}
      <p>{cleanInlineMarkdown(block.text || "")}</p>
    </aside>
  );
}

function ChecklistBlock({ block }: { block: AgentRunReportBlock }) {
  const items = (block.items || []) as Array<{ text?: string; done?: boolean }>;
  return (
    <section className="rounded-sm border border-border bg-card p-5 shadow-elev-1" data-block="checklist">
      {block.title ? <h2 className="mb-3 font-display text-sm font-bold tracking-tight text-foreground">{block.title}</h2> : null}
      <ul className="space-y-2">
        {items.map((item, i) => (
          <li key={i} className="flex items-start gap-2.5 text-sm">
            {item.done ? (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden />
            ) : (
              <span className="mt-0.5 h-4 w-4 shrink-0 rounded-full border border-border" aria-hidden />
            )}
            <span className={cn(item.done && "text-muted-foreground line-through")}>{item.text}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function DoneStepsBlock({ block }: { block: AgentRunReportBlock }) {
  const steps = block.steps || [];
  return (
    <section className="rounded-sm border border-border bg-card p-5 shadow-elev-1" data-block="done_steps">
      {block.title ? <h2 className="mb-3 font-display text-sm font-bold tracking-tight text-foreground">{block.title}</h2> : null}
      <ol className="space-y-3">
        {steps.map((step, i) => (
          <li key={i} className="flex gap-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-sm border border-success/35 bg-success/12 font-mono text-2xs font-semibold text-success">
              {i + 1}
            </span>
            <div className="min-w-0">
              <p className="text-sm font-medium text-foreground">{step.title}</p>
              {step.detail ? <p className="mt-0.5 text-xs text-muted-foreground">{step.detail}</p> : null}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function CodeBlock({ block }: { block: AgentRunReportBlock }) {
  return (
    <section className="overflow-hidden rounded-sm border border-border bg-card shadow-elev-1" data-block="code">
      <div className="flex items-center justify-between border-b border-border px-4 py-2">
        <p className="text-2xs font-medium uppercase tracking-wider text-muted-foreground">{block.title || block.language || "Вывод"}</p>
      </div>
      <pre className="max-h-56 overflow-auto px-4 py-3 font-mono text-xs leading-5 text-foreground/85">{block.code}</pre>
    </section>
  );
}

function MarkdownBlock({
  block,
  documentTitle,
  documentHref,
}: {
  block: AgentRunReportBlock;
  documentTitle?: string;
  documentHref?: string;
}) {
  const markdown = stripLeadingTitleHeading(stripReportBlocksFence(block.text || ""), documentTitle || "");
  if (!markdown) return null;
  return (
    <details className="group rounded-sm border border-border bg-card shadow-elev-1" data-block="markdown">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4">
        <div className="flex items-center gap-2.5">
          <FileText className="h-4 w-4 text-muted-foreground" aria-hidden />
          <div>
            <p className="text-sm font-semibold text-foreground">{block.title || "Полный текст отчёта"}</p>
            <p className="text-2xs text-muted-foreground">Markdown агента — блоки сверху ускоряют скан</p>
          </div>
        </div>
        <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-open:rotate-180" aria-hidden />
      </summary>
      <div className="border-t border-border px-5 py-4">
        <div className="prose prose-invert max-w-none prose-sm prose-headings:scroll-mt-20 prose-headings:text-foreground prose-p:text-foreground/85 prose-li:text-foreground/85 prose-pre:max-h-[32rem] prose-pre:overflow-auto prose-table:block prose-table:overflow-x-auto prose-th:whitespace-nowrap prose-td:align-top">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
        </div>
        {documentHref ? (
          <p className="mt-4 text-xs text-muted-foreground">
            <Link className="font-medium text-primary underline-offset-4 hover:underline" to={documentHref}>
              Открыть полный документ →
            </Link>
          </p>
        ) : null}
      </div>
    </details>
  );
}

function Panel({
  title,
  empty,
  count,
  icon,
  children,
}: {
  title: string;
  empty: string;
  count: number;
  icon: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-sm border border-border bg-card p-5 shadow-elev-1">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-primary">{icon}</span>
          <h2 className="font-display text-sm font-bold tracking-tight text-foreground">{title}</h2>
        </div>
        {count > 0 ? <span className="font-mono text-xs text-muted-foreground">{count}</span> : null}
      </div>
      {children || <p className="text-sm text-muted-foreground">{empty}</p>}
    </section>
  );
}
