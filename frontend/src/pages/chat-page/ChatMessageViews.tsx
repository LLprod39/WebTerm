import { useState } from "react";
import { Link } from "react-router-dom";
import { Bot, Check, CheckCircle2, Circle, Copy, Loader2, MapPin, RotateCcw, ShieldCheck, User, XCircle } from "lucide-react";

import type { AssistantAction, AssistantChatMessage } from "@/api";
import { Button } from "@/components/ui/button";
import { Sparkline } from "@/components/dashboard/Sparkline";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
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
import { cleanStepTitle } from "./PlanTasksPanel";
import { WebSourcesCard, type WebSource } from "./WebSourcesCard";

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
  const quietThreshold = Math.max(0.5, (max - min) * 0.08);
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
      className="w-full max-w-[640px] min-h-[190px] overflow-hidden rounded-xl border border-border/60 bg-card/65 shadow-sm sm:min-h-[220px]"
    >
      <figcaption className="flex flex-wrap items-start justify-between gap-3 border-b border-border/45 px-4 py-3.5 sm:px-5">
        <div className="min-w-0">
          <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted-foreground/60">
            {localize(lang, "Отчёт по метрике", "Metric report")}
          </div>
          <h3 className="mt-1 truncate text-sm font-semibold tracking-tight text-foreground">{title}</h3>
          <p className="mt-1 text-[11px] text-muted-foreground">
            {chart.summary || trend} · {localize(lang, "диапазон", "range")} {range}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground/60">
            {localize(lang, "Сейчас", "Current")}
          </div>
          <div className="mt-0.5 text-2xl font-semibold tabular-nums tracking-tight text-foreground">
            {formatMetricValue(last, chart.unit)}
          </div>
        </div>
      </figcaption>
      <div className="px-4 pb-4 pt-3 sm:px-5 sm:pb-5">
        <div className="h-24 min-h-24 w-full overflow-hidden text-primary/80 sm:h-28 sm:min-h-28">
          <Sparkline
            data={series}
            height={112}
            width={600}
            strokeWidth={1.75}
            className="h-24 w-full sm:h-28"
          />
        </div>
      </div>
    </figure>
  );
}

function actionServerLabel(action: AssistantAction): string {
  const blast = action.blast_radius || {};
  if (Array.isArray(blast.server_names) && blast.server_names.length) {
    return String(blast.server_names[0]);
  }
  const input = (action.input || {}) as Record<string, unknown>;
  if (input.server_name) return String(input.server_name);
  if (input.server_id != null) return `#${input.server_id}`;
  return "";
}

function actionCommandLine(action: AssistantAction): string {
  const dry = action.dry_run_preview || {};
  if (typeof dry.command === "string" && dry.command.trim()) return dry.command.trim();
  const input = (action.input || {}) as Record<string, unknown>;
  const cmd = input.command ?? input.cmd;
  if (typeof cmd === "string" && cmd.trim()) return cmd.trim();
  return "";
}

function actionResultOutput(action: AssistantAction): string {
  const result = (action.result || {}) as Record<string, unknown>;
  const nested = (result.result && typeof result.result === "object" ? result.result : result) as Record<
    string,
    unknown
  >;
  const out =
    (typeof nested.output === "string" && nested.output) ||
    (typeof nested.stdout === "string" && nested.stdout) ||
    (typeof result.output === "string" && result.output) ||
    (typeof result.stdout === "string" && result.stdout) ||
    "";
  return String(out).trim();
}

function actionTargetLabel(action: AssistantAction): string {
  const blast = (action.blast_radius || {}) as Record<string, unknown>;
  const serverNames = Array.isArray(blast.server_names)
    ? blast.server_names.map(String).filter(Boolean)
    : [];
  if (serverNames.length) return serverNames.join(", ");
  const input = (action.input || {}) as Record<string, unknown>;
  const explicit = input.server_name ?? input.target_name ?? input.target ?? input.project_name;
  if (explicit != null && String(explicit).trim()) return String(explicit);
  if (action.target_url) return action.target_url;
  return "";
}

/** Confirmation card with immutable target preview and typed-confirm support. */
export function ActionCard({
  action,
  isWorking,
  onConfirm,
  onCancel,
  onUndo,
}: {
  action: AssistantAction;
  isWorking: boolean;
  onConfirm: (actionId: number, typedConfirm?: string) => void;
  onCancel: (actionId: number) => void;
  onUndo?: (actionId: number) => void;
}) {
  const { lang } = useI18n();
  const [typedConfirm, setTypedConfirm] = useState("");
  const canConfirm = action.status === "requires_confirmation";
  const canCancel = action.status === "requires_confirmation" || action.status === "proposed";

  const server = actionServerLabel(action);
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
  const cmd = actionCommandLine(action);
  const output = action.status === "completed" ? actionResultOutput(action) : "";
  const target = actionTargetLabel(action);
  const statusDot =
    action.status === "completed"
      ? "bg-success/80"
      : action.status === "failed" || action.status === "cancelled"
        ? "bg-destructive/80"
        : canConfirm
          ? "bg-warning/70"
          : action.status === "running"
            ? "bg-info animate-pulse"
            : "bg-muted-foreground/40";

  return (
    <div className="max-w-[min(640px,100%)] overflow-hidden rounded-xl border border-border/55 bg-card/55 shadow-sm">
      <div className="flex min-w-0 items-start justify-between gap-3 border-b border-border/45 px-3.5 py-3">
        <div className="flex min-w-0 items-start gap-2.5">
          <span className={cn("mt-2 h-1.5 w-1.5 shrink-0 rounded-full", statusDot)} />
          <div className="min-w-0">
            <div className="truncate text-[13px] font-semibold tracking-tight text-foreground">
              {action.title || action.action_type}
            </div>
            <div className="mt-0.5 font-mono text-[10px] text-muted-foreground/65">{action.action_type}</div>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap justify-end gap-1.5">
          <span className={cn("rounded-full border px-2 py-0.5 text-[10px] font-medium", statusTone(action.status))}>
            {actionStatusLabel(action.status, lang)}
          </span>
          <span className={cn(
            "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium",
            action.risk === "dangerous"
              ? "border-destructive/35 bg-destructive/10 text-destructive"
              : action.risk === "read"
                ? "border-success/30 bg-success/10 text-success"
                : "border-warning/30 bg-warning/10 text-warning",
          )}>
            <ShieldCheck className="h-3 w-3" />
            {actionRiskLabel(action.risk, lang)}
          </span>
        </div>
      </div>

      <div className="space-y-3 px-3.5 py-3">
        {action.description ? (
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
              {localize(lang, "Что произойдёт", "What will happen")}
            </div>
            <p className="mt-1 text-[12px] leading-5 text-foreground/90">{action.description}</p>
          </div>
        ) : null}

        {(target || server || targetCount > 0) ? (
          <div className="rounded-lg border border-border/50 bg-background/45 px-3 py-2">
            <div className="flex items-start gap-2">
              <MapPin className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              <div className="min-w-0">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
                  {localize(lang, "Где", "Where")}
                </div>
                <div className="mt-0.5 break-words text-[12px] font-medium text-foreground">
                  {target || server || localize(lang, `${targetCount} целей`, `${targetCount} targets`)}
                </div>
                {targetCount > 1 ? (
                  <div className="mt-0.5 text-[10.5px] text-warning">
                    {localize(lang, `Охват: ${targetCount} целей`, `Blast radius: ${targetCount} targets`)}
                  </div>
                ) : null}
              </div>
            </div>
          </div>
        ) : null}

        {cmd ? (
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
              {localize(lang, "Команда / операция", "Command / operation")}
            </div>
            <pre className="mt-1 overflow-x-auto rounded-lg border border-border/50 bg-background/60 px-3 py-2 font-mono text-[11px] leading-4 text-foreground">$ {cmd}</pre>
          </div>
        ) : null}

          {output ? (
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
                {localize(lang, "Результат", "Result")}
              </div>
              <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-success/20 bg-success/[0.04] px-3 py-2 font-mono text-[10.5px] leading-4 text-muted-foreground/90">
                {output.length > 4000 ? `${output.slice(0, 4000)}\n…` : output}
              </pre>
            </div>
          ) : null}

          {canConfirm && targetCount > 0 ? (
            <div className="rounded-lg border border-warning/25 bg-warning/[0.06] px-3 py-2 text-[10.5px] leading-4 text-muted-foreground">
              <span className="font-medium text-foreground">
                {localize(lang, "Затронет", "Targets")}: {targetCount}
              </span>
              {serverNames.length ? ` · ${serverNames.slice(0, 8).join(", ")}` : null}
              {serverNames.length > 8 ? ` +${serverNames.length - 8}` : null}
            </div>
          ) : null}

          {canConfirm && typedRequired ? (
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

          {(canConfirm || canCancel || (action.status === "completed" && onUndo && action.undo_payload)) && (
            <div className="flex flex-wrap items-center gap-2 border-t border-border/45 pt-3 text-[11px]">
              {canConfirm ? (
                <button
                  type="button"
                  className="rounded-lg bg-primary px-3 py-1.5 font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-40"
                  disabled={isWorking || !typedMatches}
                  onClick={() => onConfirm(action.id, typedRequired ? typedConfirm.trim() : undefined)}
                >
                  {isWorking ? (
                    <Loader2 className="inline h-3 w-3 animate-spin" />
                  ) : (
                    localize(lang, "подтвердить", "confirm")
                  )}
                </button>
              ) : null}
              {canCancel ? (
                <button
                  type="button"
                  className="rounded-lg border border-border/70 px-3 py-1.5 font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-40"
                  disabled={isWorking}
                  onClick={() => onCancel(action.id)}
                >
                  {localize(lang, "отмена", "cancel")}
                </button>
              ) : null}
              {action.status === "completed" &&
              action.undo_payload &&
              Object.keys(action.undo_payload).length > 0 &&
              onUndo ? (
                <button
                  type="button"
                  className="rounded-lg border border-border/70 px-3 py-1.5 font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  disabled={isWorking}
                  onClick={() => onUndo(action.id)}
                >
                  {localize(lang, "откат", "undo")}
                </button>
              ) : null}
              {action.target_url && action.status === "completed" ? (
                <Link
                  to={action.target_url}
                  className="rounded-lg border border-border/70 px-3 py-1.5 font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                >
                  {localize(lang, "открыть", "open")}
                </Link>
              ) : null}
            </div>
          )}
      </div>
    </div>
  );
}

export function PlanChecklist({ plan }: { plan: { title?: string; steps?: Array<{ id?: number; text?: string; status?: string }> } }) {
  const { lang } = useI18n();
  const steps = plan.steps || [];
  if (!steps.length) return null;
  return (
    <div className="rounded-sm border border-primary/20 bg-primary/[0.04] px-2 py-1.5">
      <div className="mb-1 text-[11px] font-semibold text-foreground">
        {plan.title || localize(lang, "План", "Plan")}
      </div>
      <ul className="space-y-0.5">
        {steps.map((step, idx) => {
          const done = step.status === "done" || step.status === "completed";
          const failed = step.status === "failed" || step.status === "error";
          return (
            <li key={step.id ?? idx} className="flex items-start gap-1.5 text-[12px] leading-4">
              {done ? (
                <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0 text-success" />
              ) : failed ? (
                <XCircle className="mt-0.5 h-3 w-3 shrink-0 text-destructive" />
              ) : step.status === "running" ? (
                <Loader2 className="mt-0.5 h-3 w-3 shrink-0 animate-spin text-primary" />
              ) : (
                <Circle className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground" />
              )}
              <span
                title={step.text}
                className={cn("line-clamp-2", done && "text-muted-foreground line-through")}
              >
                {cleanStepTitle(step.text)}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
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

export function MessageBubble({
  message,
  actionWorkingId,
  onConfirmAction,
  onCancelAction,
  onUndoAction,
  onSaveRunbook,
  onRetry,
  serverPanelActions,
  agentPanelActions,
  forecastPanelActions,
}: {
  message: AssistantChatMessage;
  actionWorkingId: number | null;
  onConfirmAction: (actionId: number, typedConfirm?: string) => void;
  onCancelAction: (actionId: number) => void;
  onUndoAction?: (actionId: number) => void;
  onSaveRunbook?: (message: AssistantChatMessage) => void;
  /** Re-send the previous user message; provided only for the latest assistant message. */
  onRetry?: () => void;
  serverPanelActions?: ServerPanelActions;
  agentPanelActions?: AgentPanelActions;
  forecastPanelActions?: ForecastPanelActions;
}) {
  const { lang } = useI18n();
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
    const displayContent = String(message.content || "")
      .replace(/\n\n\[Human terminal on[^\]]*\][\s\S]*$/i, "")
      .replace(/\n\nКонтекст серверов:[\s\S]*$/i, "")
      .replace(/\n\nКонтекст playbook:[\s\S]*$/i, "")
      .replace(/\nКонтекст пользователей:[\s\S]*$/i, "")
      .trim();
    return (
      <div className="group flex justify-end gap-3">
        <div className="min-w-0 max-w-[min(560px,85%)]">
          <div className="rounded-sm rounded-br-md bg-primary px-3.5 py-2.5 text-[13px] font-medium leading-5 tracking-tight text-primary-foreground shadow-sm">
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

  return (
    <div className="group grid grid-cols-[2rem_minmax(0,1fr)] gap-2.5">
      <div className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-sm border border-primary/20 bg-primary/10 text-primary shadow-[0_0_0_1px_hsl(var(--primary)/0.06)]">
        <Icon className="h-3.5 w-3.5" strokeWidth={1.75} />
      </div>
      <div className="min-w-0 space-y-2 pt-0.5">
        <div className="flex flex-wrap items-center gap-2 text-[11px]">
          <span className="font-semibold tracking-tight text-foreground">
            {localize(lang, "Оператор", "Operator")}
          </span>
          <span className="tabular-nums text-muted-foreground/65 opacity-0 transition-opacity group-hover:opacity-100">
            {formatDateTime(message.created_at, lang)}
          </span>
          {actions.length ? (
            <span className="rounded-sm border border-border/50 bg-muted/20 px-1.5 py-px font-mono text-[10px] text-muted-foreground">
              {actions.length} {localize(lang, "действ.", "actions")}
            </span>
          ) : null}
          <span className="flex items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
            {message.content ? <CopyMessageButton content={message.content} lang={lang} /> : null}
            {onRetry ? (
              <button
                type="button"
                onClick={onRetry}
                className="rounded p-1 text-muted-foreground/60 transition-colors hover:text-foreground"
                aria-label={localize(lang, "Повторить", "Retry")}
                title={localize(lang, "Повторить последний запрос", "Retry last request")}
              >
                <RotateCcw className="h-3 w-3" />
              </button>
            ) : null}
          </span>
        </div>
        {message.content ? (
          <div className="max-w-[min(640px,100%)]">
            <OperatorMarkdown content={message.content} stripTables={hasStructuredTable || Boolean(metrics)} />
          </div>
        ) : null}
        <WebSourcesCard sources={webSources} />
        {metrics ? <MetricsSnapshotCard data={metrics} /> : null}
        {plan ? (
          <div className="max-w-[min(920px,100%)]">
            <PlanChecklist plan={plan} />
          </div>
        ) : null}
        {chart?.series && chart.series.length >= 2 ? <MetricSeriesReportCard chart={chart} /> : null}
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
            // Show even when empty — clean «no risks» card with recheck/analyze
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
      </div>
    </div>
  );
}
