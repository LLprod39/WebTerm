import { memo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { motion, useReducedMotion } from "framer-motion";
import { Bot, Check, CheckCircle2, ChevronDown, Copy, Loader2, RotateCcw, ShieldCheck, User, XCircle } from "lucide-react";

import type { AssistantAction, AssistantChatMessage } from "@/api";
import { AgentProgress } from "@/boardui/components/application/agent-progress/agent-progress";
import { Button } from "@/components/ui/button";
import { Sparkline } from "@/components/dashboard/Sparkline";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import {
  actionCommandLine,
  actionPreviewLine,
  actionResultOutput,
  actionServerLabel,
} from "./actionPreview";
import { actionRiskLabel, actionStatusLabel, formatDateTime, statusTone } from "./chatHelpers";
import { DataTableCard, type DataTable } from "./DataTableCard";
import { InteractiveAlertsPanel, type InteractiveAlertItem } from "./InteractiveAlertsPanel";
import {
  InteractiveAgentsPanel,
  type InteractiveAgentItem,
  type AgentPanelActions,
} from "./InteractiveAgentsPanel";
import {
  InteractiveForecastsPanel,
  type InteractiveForecastItem,
  type ForecastPanelActions,
} from "./InteractiveForecastsPanel";
import {
  InteractiveServersPanel,
  type InteractiveServerItem,
  type ServerPanelActions,
} from "./InteractiveServersPanel";
import { MetricsSnapshotCard, type MetricsSnapshot } from "./MetricsSnapshotCard";
import { OperatorMarkdown } from "./OperatorMarkdown";
import { planToAgentProgressSteps } from "./PlanTasksPanel";
import { WebSourcesCard, type WebSource } from "./WebSourcesCard";
import { CHAT_MOTION } from "./chatMotion";
import { visibleOperatorUserText } from "./operatorUserText";

type MetricSeriesChart = {
  title?: string;
  series?: number[];
  unit?: string;
  summary?: string;
};

function formatMetricValue(value: number, unit?: string) {
  const formatted = Math.abs(value) < 10 ? value.toFixed(1) : Math.round(value).toString();
  if (unit === "%") return `${formatted}%`;
  return unit ? `${formatted} ${unit}` : formatted;
}

export function MetricSeriesReportCard({ chart }: { chart: MetricSeriesChart }) {
  const { lang } = useI18n();
  const series = (chart.series || []).filter((value) => Number.isFinite(value));
  if (series.length < 2) return null;

  const first = series[0];
  const last = series[series.length - 1];
  const min = Math.min(...series);
  const max = Math.max(...series);
  const delta = last - first;
  const span = max - min;
  const quietThreshold = Math.max(0.5, span * 0.08);
  const flat = span <= quietThreshold;
  const trend = Math.abs(delta) <= quietThreshold
    ? localize(lang, "Без резких изменений", "No material change")
    : delta > 0
      ? localize(lang, `Рост на ${formatMetricValue(Math.abs(delta), chart.unit)}`, `Up ${formatMetricValue(Math.abs(delta), chart.unit)}`)
      : localize(lang, `Снижение на ${formatMetricValue(Math.abs(delta), chart.unit)}`, `Down ${formatMetricValue(Math.abs(delta), chart.unit)}`);
  const title = chart.title || localize(lang, "Метрика", "Metric");
  const range = `${formatMetricValue(min, chart.unit)} — ${formatMetricValue(max, chart.unit)}`;

  return (
    <figure
      role="img"
      aria-label={localize(lang, `График метрики ${title}`, `${title} metric chart`)}
      data-testid="metric-series-report"
      className="w-full max-w-[420px] overflow-hidden rounded-sm border border-border/50 bg-card/40"
    >
      <figcaption className="flex items-center justify-between gap-3 px-3 py-2">
        <div className="min-w-0">
          <div className="truncate text-[12px] font-medium tracking-tight text-foreground">{title}</div>
          <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
            {chart.summary || trend}
            {!flat ? ` · ${range}` : null}
          </p>
        </div>
        <div className="shrink-0 text-right font-mono text-[15px] font-semibold tabular-nums tracking-tight text-foreground">
          {formatMetricValue(last, chart.unit)}
        </div>
      </figcaption>
      {!flat ? (
        <div className="px-3 pb-2">
          <div className="h-8 w-full overflow-hidden text-primary/80">
            <Sparkline
              data={series}
              height={32}
              width={400}
              strokeWidth={1.5}
              className="h-8 w-full"
            />
          </div>
        </div>
      ) : null}
    </figure>
  );
}

/** Compact action chip in the stream; full details live in Context Rail. */
export function ActionCard({
  action,
  isWorking,
  onConfirm,
  onCancel,
  onUndo,
  onOpenDetails,
}: {
  action: AssistantAction;
  isWorking: boolean;
  onConfirm: (actionId: number, typedConfirm?: string) => void;
  onCancel: (actionId: number) => void;
  onUndo?: (actionId: number) => void;
  onOpenDetails?: (action: AssistantAction) => void;
}) {
  const { lang } = useI18n();
  const [typedConfirm, setTypedConfirm] = useState("");
  const canConfirm = action.status === "requires_confirmation";
  const canCancel = action.status === "requires_confirmation" || action.status === "proposed";

  const blast = (action.blast_radius || {}) as Record<string, unknown>;
  const serverNames = Array.isArray(blast.server_names)
    ? blast.server_names.map(String).filter(Boolean)
    : [];
  const serverIds = Array.isArray(blast.server_ids) ? blast.server_ids : [];
  const targetCount = Number(blast.count || serverIds.length || serverNames.length || 0);
  const typedRequired = blast.typed_confirm_required === true;
  const typedToken = String(blast.typed_confirm_token || "").trim();
  const typedHint = String(blast.typed_confirm_hint || "").trim();
  const typedMatches = !typedRequired || (
    typedToken === "FANOUT"
      ? typedConfirm.trim().toUpperCase() === "FANOUT"
      : typedConfirm.trim().toLocaleLowerCase() === typedToken.toLocaleLowerCase()
  );
  const preview = actionPreviewLine(action);
  const hasUndo =
    action.status === "completed" &&
    Boolean(onUndo) &&
    Boolean(action.undo_payload) &&
    Object.keys(action.undo_payload || {}).length > 0;
  const statusDot =
    action.status === "completed"
      ? "bg-success/80"
      : action.status === "failed" || action.status === "cancelled"
        ? "bg-destructive/80"
        : canConfirm
          ? "bg-warning/70"
          : action.status === "running"
            ? "bg-info animate-pulse motion-reduce:animate-none"
            : "bg-muted-foreground/40";

  return (
    <div className="max-w-[min(640px,100%)] overflow-hidden rounded-sm border border-border/55 bg-card/55">
      <div className="flex min-w-0 items-center gap-2 px-3 py-2">
        <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", statusDot)} />
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 flex-wrap items-center gap-1.5">
            <span className="truncate text-[12px] font-semibold tracking-tight text-foreground">
              {action.title || action.action_type}
            </span>
            <span className={cn("rounded-sm border px-1.5 py-px text-[10px] font-medium", statusTone(action.status))}>
              {actionStatusLabel(action.status, lang)}
            </span>
            <span
              className={cn(
                "inline-flex items-center gap-0.5 rounded-sm border px-1.5 py-px text-[10px] font-medium",
                action.risk === "dangerous"
                  ? "border-destructive/35 bg-destructive/10 text-destructive"
                  : action.risk === "read"
                    ? "border-success/30 bg-success/10 text-success"
                    : "border-warning/30 bg-warning/10 text-warning",
              )}
            >
              <ShieldCheck className="h-3 w-3" />
              {actionRiskLabel(action.risk, lang)}
            </span>
          </div>
          {preview ? (
            <div className="mt-0.5 truncate font-mono text-[10.5px] text-muted-foreground/80">
              {preview}
            </div>
          ) : null}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {onOpenDetails ? (
            <button
              type="button"
              className="rounded-sm border border-border/70 px-2 py-1 text-[10.5px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              onClick={() => onOpenDetails(action)}
            >
              {localize(lang, "детали", "details")}
            </button>
          ) : null}
        </div>
      </div>

      {canConfirm ? (
        <div className="space-y-2 border-t border-border/45 px-3 py-2">
          {action.description ? (
            <p className="line-clamp-2 text-[11.5px] leading-4 text-foreground/85">{action.description}</p>
          ) : null}
          {targetCount > 0 ? (
            <div className="text-[10.5px] leading-4 text-muted-foreground">
              <span className="font-medium text-foreground">
                {localize(lang, "Затронет", "Targets")}: {targetCount}
              </span>
              {serverNames.length ? ` · ${serverNames.slice(0, 8).join(", ")}` : null}
              {serverNames.length > 8 ? ` +${serverNames.length - 8}` : null}
            </div>
          ) : null}
          {typedRequired ? (
            <label className="block space-y-1 text-[10.5px] text-warning">
              <span>{typedHint || localize(lang, `Введите ${typedToken}`, `Type ${typedToken}`)}</span>
              <input
                value={typedConfirm}
                onChange={(event) => setTypedConfirm(event.target.value)}
                placeholder={typedToken}
                autoComplete="off"
                spellCheck={false}
                className="h-8 w-full rounded-sm border border-warning/40 bg-background px-2 font-mono text-[12px] text-foreground outline-none focus:border-warning"
                aria-label={localize(lang, "Текстовое подтверждение", "Typed confirmation")}
              />
            </label>
          ) : null}
          {action.error ? <p className="text-[11px] text-destructive/90">{action.error}</p> : null}
          <div className="flex flex-wrap items-center gap-2 text-[11px]">
            <button
              type="button"
              className="rounded-sm bg-primary px-3 py-1.5 font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40"
              disabled={isWorking || !typedMatches}
              onClick={() => onConfirm(action.id, typedRequired ? typedConfirm.trim() : undefined)}
            >
              {isWorking ? (
                <Loader2 className="inline h-3 w-3 animate-spin motion-reduce:animate-none" />
              ) : (
                localize(lang, "подтвердить", "confirm")
              )}
            </button>
            {canCancel ? (
              <button
                type="button"
                className="rounded-sm border border-border/70 px-3 py-1.5 font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-40"
                disabled={isWorking}
                onClick={() => onCancel(action.id)}
              >
                {localize(lang, "отмена", "cancel")}
              </button>
            ) : null}
          </div>
        </div>
      ) : null}

      {!canConfirm && (hasUndo || (action.target_url && action.status === "completed") || canCancel || action.error) ? (
        <div className="flex flex-wrap items-center gap-2 border-t border-border/45 px-3 py-1.5 text-[11px]">
          {action.error ? <p className="w-full text-[11px] text-destructive/90">{action.error}</p> : null}
          {canCancel ? (
            <button
              type="button"
              className="rounded-sm border border-border/70 px-2.5 py-1 font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-40"
              disabled={isWorking}
              onClick={() => onCancel(action.id)}
            >
              {localize(lang, "отмена", "cancel")}
            </button>
          ) : null}
          {hasUndo && onUndo ? (
            <button
              type="button"
              className="rounded-sm border border-border/70 px-2.5 py-1 font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              disabled={isWorking}
              onClick={() => onUndo(action.id)}
            >
              {localize(lang, "откат", "undo")}
            </button>
          ) : null}
          {action.target_url && action.status === "completed" ? (
            <Link
              to={action.target_url}
              className="rounded-sm border border-border/70 px-2.5 py-1 font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              {localize(lang, "открыть", "open")}
            </Link>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

// Re-export helpers for tests / panels that previously imported from this module.
export { actionCommandLine, actionResultOutput, actionServerLabel };

export function PlanChecklist({ plan }: { plan: { title?: string; steps?: Array<{ id?: number; text?: string; status?: string }> } }) {
  const steps = planToAgentProgressSteps(plan);
  if (!steps.length) return null;
  return <AgentProgress steps={steps} defaultExpanded className="max-w-[min(28rem,100%)]" />;
}

/** Copy message markdown to clipboard with a brief confirmation state. */
function CopyMessageButton({ content, lang }: { content: string; lang: "ru" | "en" }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={() => {
        void navigator.clipboard
          ?.writeText(content)
          .then(() => {
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1500);
          })
          .catch(() => undefined);
      }}
      className="rounded p-1 text-muted-foreground/60 transition-colors hover:text-foreground"
      aria-label={localize(lang, "Скопировать", "Copy")}
      title={localize(lang, "Скопировать текст", "Copy text")}
    >
      {copied ? <Check className="h-3 w-3 text-success" /> : <Copy className="h-3 w-3" />}
    </button>
  );
}

type MessageBubbleProps = {
  message: AssistantChatMessage;
  actionWorkingId: number | null;
  onConfirmAction: (actionId: number, typedConfirm?: string) => void;
  onCancelAction: (actionId: number) => void;
  onUndoAction?: (actionId: number) => void;
  onOpenActionDetails?: (action: AssistantAction) => void;
  onSaveRunbook?: (message: AssistantChatMessage) => void;
  /** Re-send the previous user message; provided only for the latest assistant message. */
  onRetry?: () => void;
  serverPanelActions?: ServerPanelActions;
  agentPanelActions?: AgentPanelActions;
  forecastPanelActions?: ForecastPanelActions;
  /**
   * Live-turn adornments share this shell with the eventual REST message.
   * Keeping them as slots (instead of swapping the whole bubble) preserves
   * Markdown/code/card DOM while the durable message is attached.
   */
  turnActivity?: ReactNode;
  turnTrailing?: ReactNode;
  streaming?: boolean;
  streamStripTables?: boolean;
  animateSupportingContent?: boolean;
};

/** Collapses stacked metrics/tables/charts so one reply does not eat the viewport. */
function MessageEvidenceFold({
  count,
  defaultOpen,
  forceFold = false,
  children,
}: {
  count: number;
  defaultOpen: boolean;
  forceFold?: boolean;
  children: ReactNode;
}) {
  const { lang } = useI18n();
  const [open, setOpen] = useState(defaultOpen);
  if (count <= 1 && !forceFold) return <>{children}</>;

  return (
    <div className="max-w-[min(420px,100%)] overflow-hidden rounded-sm border border-border/40 bg-card/20">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-[12px] transition-colors hover:bg-foreground/[0.03]"
        aria-expanded={open}
      >
        <ChevronDown
          className={cn("h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")}
        />
        <span className="font-medium text-foreground">
          {localize(lang, "Данные ответа", "Reply data")}
        </span>
        <span className="font-mono text-[10px] tabular-nums text-muted-foreground">
          {count}
        </span>
      </button>
      {open ? <div className="space-y-2 border-t border-border/30 px-2 py-2">{children}</div> : null}
    </div>
  );
}

function MessageBubbleComponent({
  message,
  actionWorkingId,
  onConfirmAction,
  onCancelAction,
  onUndoAction,
  onOpenActionDetails,
  onSaveRunbook,
  onRetry,
  serverPanelActions,
  agentPanelActions,
  forecastPanelActions,
  turnActivity,
  turnTrailing,
  streaming = false,
  streamStripTables = false,
  animateSupportingContent = false,
}: MessageBubbleProps) {
  const { lang } = useI18n();
  const reduceMotion = useReducedMotion();
  const isUser = message.role === "user";
  const actions = message.metadata.actions || [];
  const Icon = isUser ? User : Bot;
  const plan = message.metadata.plan as { title?: string; steps?: Array<{ id?: number; text?: string; status?: string }> } | undefined;
  const chart = message.metadata.chart as MetricSeriesChart | undefined;
  const metrics = message.metadata.metrics as MetricsSnapshot | undefined;
  const table = message.metadata.table as DataTable | undefined;
  const tables = (message.metadata.tables as DataTable[] | undefined) || (table ? [table] : []);
  const webSources = (message.metadata.web_sources as WebSource[] | undefined) || [];
  const completedMutations = actions.filter((a) => a.status === "completed" && a.risk !== "read");

  if (isUser) {
    // Strip hidden operator context (pins / human terminal trail) from display
    const displayContent = visibleOperatorUserText(message.content);
    return (
      <div className="group flex justify-end gap-3">
        <div className="min-w-0 max-w-[min(560px,85%)]">
          <div className="rounded-2xl rounded-br-md bg-primary px-3.5 py-2.5 text-[13px] font-medium leading-5 tracking-tight text-primary-foreground shadow-sm">
            <div className="whitespace-pre-wrap break-words">{displayContent || message.content}</div>
          </div>
          <div className="mt-1 pr-0.5 text-right text-[10px] tabular-nums text-muted-foreground/70 opacity-0 transition-opacity group-hover:opacity-100">
            {formatDateTime(message.created_at, lang)}
          </div>
        </div>
      </div>
    );
  }

  const hasStructuredTable = tables.some(
    (t) => (t.rows?.length || 0) > 0 || t.kind === "forecasts" || Boolean(t.interactive),
  );
  const hasChart = Boolean(chart?.series && chart.series.length >= 2);
  const evidenceBlocks =
    (webSources.length ? 1 : 0) +
    (metrics ? 1 : 0) +
    (hasChart ? 1 : 0) +
    tables.length;
  const hasSupportingContent = Boolean(
    evidenceBlocks || plan || actions.length,
  );

  const evidenceBody = evidenceBlocks ? (
    <>
      <WebSourcesCard sources={webSources} />
      {metrics ? <MetricsSnapshotCard data={metrics} /> : null}
      {hasChart ? <MetricSeriesReportCard chart={chart!} /> : null}
      {tables.map((t, i) => {
        if (t.kind === "servers" && Array.isArray(t.items) && t.items.length) {
          return (
            <InteractiveServersPanel
              key={`${t.title || "servers"}-${i}`}
              title={t.title}
              items={t.items as InteractiveServerItem[]}
              actions={serverPanelActions}
              defaultExpanded={Boolean((t as { default_expanded?: boolean }).default_expanded)}
              note={typeof (t as { note?: string }).note === "string" ? (t as { note?: string }).note : undefined}
            />
          );
        }
        if (t.kind === "alerts" && Array.isArray(t.items) && t.items.length) {
          return (
            <InteractiveAlertsPanel
              key={`${t.title || "alerts"}-${i}`}
              title={t.title}
              items={t.items as InteractiveAlertItem[]}
              onAsk={serverPanelActions?.onAsk}
            />
          );
        }
        if (t.kind === "agents" && Array.isArray(t.items) && t.items.length) {
          return (
            <InteractiveAgentsPanel
              key={`${t.title || "agents"}-${i}`}
              title={t.title}
              items={t.items as InteractiveAgentItem[]}
              actions={agentPanelActions || { onAsk: serverPanelActions?.onAsk }}
            />
          );
        }
        if (t.kind === "forecasts") {
          const forecastItems = (Array.isArray(t.items) ? t.items : []) as InteractiveForecastItem[];
          return (
            <InteractiveForecastsPanel
              key={`${t.title || "forecasts"}-${i}`}
              title={t.title}
              items={forecastItems}
              empty={Boolean(t.empty) || forecastItems.length === 0}
              summary={typeof t.summary === "string" ? t.summary : undefined}
              actions={forecastPanelActions || { onAsk: serverPanelActions?.onAsk }}
            />
          );
        }
        return <DataTableCard key={`${t.title || "table"}-${i}`} table={t} />;
      })}
    </>
  ) : null;

  return (
    <motion.div
      layout={!reduceMotion}
      transition={reduceMotion ? { duration: 0 } : CHAT_MOTION.layout}
      className="group grid grid-cols-[2rem_minmax(0,1fr)] gap-2.5"
    >
      <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-full border border-border/60 bg-muted/50 text-muted-foreground">
        <Icon className="h-3.5 w-3.5" strokeWidth={1.75} />
      </div>
      <div className="min-w-0 space-y-2 pt-0.5">
        <div className="flex flex-wrap items-center gap-2 text-[11px]">
          <span className="font-semibold tracking-tight text-foreground">
            {localize(lang, "Оператор", "Operator")}
          </span>
          {message.created_at ? (
            <span className="tabular-nums text-muted-foreground/65 opacity-0 transition-opacity group-hover:opacity-100">
              {formatDateTime(message.created_at, lang)}
            </span>
          ) : null}
          {actions.length ? (
            <span className="rounded-full border border-border/50 bg-muted/20 px-1.5 py-px font-mono text-[10px] text-muted-foreground">
              {actions.length} {localize(lang, "действ.", "actions")}
            </span>
          ) : null}
          <span className="ml-auto flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
            {message.content ? <CopyMessageButton content={message.content} lang={lang} /> : null}
            {onRetry ? (
              <button
                type="button"
                onClick={onRetry}
                className="rounded-full p-1 text-muted-foreground/60 transition-colors hover:bg-muted hover:text-foreground"
                aria-label={localize(lang, "Повторить", "Retry")}
                title={localize(lang, "Повторить последний запрос", "Retry last request")}
              >
                <RotateCcw className="h-3 w-3" />
              </button>
            ) : null}
          </span>
        </div>
        {turnActivity}
        {message.content ? (
          <div
            className={cn(
              "max-w-[min(640px,100%)]",
              streaming && "text-foreground/80 [&_.operator-md_p]:text-foreground/80",
            )}
            data-message-markdown
            data-streaming={streaming ? "true" : undefined}
          >
            <OperatorMarkdown
              content={message.content}
              streaming={streaming}
              stripTables={streamStripTables || hasStructuredTable || Boolean(metrics)}
            />
          </div>
        ) : null}
        {turnTrailing}
        {hasSupportingContent ? (
          <motion.div
            layout={!reduceMotion}
            initial={
              animateSupportingContent && !reduceMotion ? { opacity: 0, y: 4 } : false
            }
            animate={{ opacity: 1, y: 0 }}
            transition={reduceMotion ? { duration: 0 } : CHAT_MOTION.status}
            className="space-y-2"
          >
        {evidenceBody ? (
          <MessageEvidenceFold
            count={evidenceBlocks}
            defaultOpen={evidenceBlocks <= 1 && actions.length === 0}
            forceFold={actions.length > 0}
          >
            {evidenceBody}
          </MessageEvidenceFold>
        ) : null}
        {plan ? (
          <div className="max-w-[min(920px,100%)]">
            <PlanChecklist plan={plan} />
          </div>
        ) : null}
        {actions.length ? (
          <div className="max-w-[min(920px,100%)] space-y-1.5">
            {actions.map((action) => (
              <ActionCard
                key={action.id}
                action={action}
                isWorking={actionWorkingId === action.id}
                onConfirm={onConfirmAction}
                onCancel={onCancelAction}
                onUndo={onUndoAction}
                onOpenDetails={onOpenActionDetails}
              />
            ))}
          </div>
        ) : null}
        {completedMutations.length >= 1 && onSaveRunbook ? (
          <Button
            size="sm"
            variant="ghost"
            className="h-7 px-2 text-[11px] text-muted-foreground hover:text-foreground"
            onClick={() => onSaveRunbook(message)}
          >
            {localize(lang, "Сохранить runbook", "Save runbook")}
          </Button>
        ) : null}
          </motion.div>
        ) : null}
      </div>
    </motion.div>
  );
}

export const MessageBubble = memo(MessageBubbleComponent);
MessageBubble.displayName = "MessageBubble";
