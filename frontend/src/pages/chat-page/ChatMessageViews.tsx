import { useState } from "react";
import { Link } from "react-router-dom";
import { Bot, Check, CheckCircle2, Circle, Copy, Loader2, RotateCcw, User, XCircle } from "lucide-react";

import type { AssistantAction, AssistantChatMessage } from "@/api";
import { Button } from "@/components/ui/button";
import { Sparkline } from "@/components/dashboard/Sparkline";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { formatDateTime } from "./chatHelpers";
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

/** Minimal action row — click confirm only (no typing). */
function ActionCard({
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
  const canConfirm = action.status === "requires_confirmation";
  const canCancel = action.status === "requires_confirmation" || action.status === "proposed";

  const server = actionServerLabel(action);
  const cmd = actionCommandLine(action);
  const output = action.status === "completed" ? actionResultOutput(action) : "";
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
    <div className="max-w-[min(520px,100%)] space-y-1 rounded-sm border border-border/40 bg-card/30 px-3 py-2">
      <div className="flex min-w-0 items-start gap-2">
        <span className={cn("mt-1.5 h-1 w-1 shrink-0 rounded-full", statusDot)} />
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5">
            {server ? (
              <span className="text-[12px] font-medium tracking-tight text-foreground">{server}</span>
            ) : null}
            {cmd ? (
              <span className="min-w-0 truncate font-mono text-[11px] text-muted-foreground">$ {cmd}</span>
            ) : (
              <span className="truncate text-[12px] text-foreground/90">
                {action.title || action.action_type}
              </span>
            )}
            {action.status === "completed" ? (
              <span className="text-[10px] text-muted-foreground/70">ok</span>
            ) : null}
            {action.status === "failed" ? (
              <span className="text-[10px] text-destructive/90">fail</span>
            ) : null}
          </div>

          {output ? (
            <pre className="max-h-48 overflow-auto whitespace-pre-wrap break-words font-mono text-[10.5px] leading-4 text-muted-foreground/90">
              {output.length > 4000 ? `${output.slice(0, 4000)}\n…` : output}
            </pre>
          ) : null}

          {action.error ? <p className="text-[11px] text-destructive/90">{action.error}</p> : null}

          {(canConfirm || canCancel || (action.status === "completed" && onUndo && action.undo_payload)) && (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 pt-0.5 text-[11px]">
              {canConfirm ? (
                <button
                  type="button"
                  className="text-foreground/90 underline-offset-2 hover:underline disabled:opacity-40"
                  disabled={isWorking}
                  onClick={() => onConfirm(action.id)}
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
                  className="text-muted-foreground underline-offset-2 hover:text-foreground hover:underline disabled:opacity-40"
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
                  className="text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                  disabled={isWorking}
                  onClick={() => onUndo(action.id)}
                >
                  {localize(lang, "откат", "undo")}
                </button>
              ) : null}
              {action.target_url && action.status === "completed" ? (
                <Link
                  to={action.target_url}
                  className="text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
                >
                  {localize(lang, "открыть", "open")}
                </Link>
              ) : null}
            </div>
          )}
        </div>
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
  const chart = message.metadata.chart as { title?: string; series?: number[]; unit?: string } | undefined;
  const metrics = message.metadata.metrics as MetricsSnapshot | undefined;
  const table = message.metadata.table as DataTable | undefined;
  const tables = (message.metadata.tables as DataTable[] | undefined) || (table ? [table] : []);
  const completedMutations = actions.filter((a) => a.status === "completed" && a.risk !== "read");

  if (isUser) {
    // Strip hidden operator context (pins / human terminal trail) from display
    const displayContent = String(message.content || "")
      .replace(/\n\n\[Human terminal on[^\]]*\][\s\S]*$/i, "")
      .replace(/\n\nКонтекст серверов:[\s\S]*$/i, "")
      .replace(/\nКонтекст пользователей:[\s\S]*$/i, "")
      .trim();
    return (
      <div className="group flex justify-end gap-3 animate-in fade-in-0 slide-in-from-bottom-1 duration-200">
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
    <div className="group grid grid-cols-[2rem_minmax(0,1fr)] gap-2.5 animate-in fade-in-0 duration-300">
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
        {metrics ? <MetricsSnapshotCard data={metrics} /> : null}
        {plan ? (
          <div className="max-w-[min(920px,100%)]">
            <PlanChecklist plan={plan} />
          </div>
        ) : null}
        {chart?.series && chart.series.length >= 2 ? (
          <div className="max-w-[min(280px,100%)] animate-in fade-in-0 duration-300 overflow-hidden rounded-sm border border-border/40 bg-card/30 px-3 py-2">
            <div className="mb-1 flex items-baseline justify-between gap-2">
              <div className="truncate text-[11px] font-medium tracking-wide text-muted-foreground">
                {chart.title || "Metric"}
              </div>
              {chart.unit ? (
                <span className="shrink-0 text-[11px] tabular-nums text-muted-foreground/70">{chart.unit}</span>
              ) : null}
            </div>
            <div className="h-9 text-foreground/70">
              <Sparkline data={chart.series} height={36} width={260} strokeWidth={1.35} className="h-full w-full" />
            </div>
            {(() => {
              const last = chart.series[chart.series.length - 1];
              if (last == null || Number.isNaN(Number(last))) return null;
              const n = Number(last);
              return (
                <div className="mt-0.5 text-right text-[12px] font-medium tabular-nums tracking-tight text-foreground">
                  {n < 10 ? n.toFixed(1) : Math.round(n)}
                  {chart.unit === "%" ? "%" : chart.unit ? ` ${chart.unit}` : ""}
                </div>
              );
            })()}
          </div>
        ) : null}
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

