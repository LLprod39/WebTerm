import { useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  Circle,
  Loader2,
  Wrench,
  XCircle,
} from "lucide-react";

import type { AgentRunDetail, AgentRunEventItem } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

import { formatCompactDateTime } from "./formatters";
import { StatusBadge } from "./StatusBadge";

function eventIcon(eventType: string, message: string) {
  const t = `${eventType} ${message}`.toLowerCase();
  if (t.includes("fail") || t.includes("error")) return XCircle;
  if (t.includes("success") || t.includes("complete") || t.includes("done")) return CheckCircle2;
  if (t.includes("tool") || t.includes("command") || t.includes("ssh")) return Wrench;
  if (t.includes("warn")) return AlertTriangle;
  if (t.includes("start") || t.includes("run") || t.includes("progress")) return Loader2;
  return Circle;
}

function eventTone(eventType: string, message: string): "success" | "danger" | "warning" | "info" | "neutral" {
  const t = `${eventType} ${message}`.toLowerCase();
  if (t.includes("fail") || t.includes("error")) return "danger";
  if (t.includes("success") || t.includes("complete") || t.includes("done")) return "success";
  if (t.includes("warn")) return "warning";
  if (t.includes("tool") || t.includes("command")) return "info";
  return "neutral";
}

const TONE_RING: Record<string, string> = {
  success: "border-success/40 bg-success/10 text-success",
  danger: "border-destructive/40 bg-destructive/10 text-destructive",
  warning: "border-warning/40 bg-warning/10 text-warning",
  info: "border-info/40 bg-info/10 text-info",
  neutral: "border-border bg-card text-muted-foreground",
};

const TONE_PILL: Record<string, string> = {
  success: "border-success/30 bg-success/10 text-success",
  danger: "border-destructive/30 bg-destructive/10 text-destructive",
  warning: "border-warning/30 bg-warning/10 text-warning",
  info: "border-info/30 bg-info/10 text-info",
  neutral: "border-border bg-surface-1 text-muted-foreground",
};

export function TimelineView({ run, events }: { run: AgentRunDetail; events: AgentRunEventItem[] }) {
  const { t } = useI18n();
  const tr = (key: string, vars?: Record<string, string | number>) => {
    let text = t(key);
    if (!vars) return text;
    for (const [name, value] of Object.entries(vars)) {
      text = text.split(`{${name}}`).join(String(value));
    }
    return text;
  };

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-5 px-4 py-5 sm:px-6">
      <div className="rounded-lg border border-border/80 bg-card/95 px-5 py-5">
        <div className="flex flex-col gap-3 border-b border-border/70 pb-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-md border border-border/70 bg-background/60 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              <Activity className="h-3 w-3" />
              {t("run.timeline_kicker")}
            </div>
            <h2 className="mt-4 text-2xl font-semibold tracking-normal text-foreground">{run.agent_name}</h2>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">{t("run.timeline_desc")}</p>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge status={run.status} />
            <span className="rounded-md border border-border/70 bg-background/60 px-3 py-1 text-xs font-medium text-muted-foreground">
              {tr("run.events_count", { count: events.length })}
            </span>
          </div>
        </div>

        {events.length === 0 ? (
          <div className="flex flex-col items-center justify-center px-4 py-16 text-center">
            <Activity className="mb-4 h-10 w-10 text-muted-foreground/35" />
            <p className="text-sm text-foreground">{t("run.timeline_empty_title")}</p>
            <p className="mt-1 text-sm text-muted-foreground">{t("run.timeline_empty_desc")}</p>
          </div>
        ) : (
          <ol className="relative space-y-0 pt-6">
            {events.map((event, index) => (
              <TimelineStep
                key={event.id}
                event={event}
                last={index === events.length - 1}
                taskLabel={
                  event.task_id !== null ? tr("run.task_id", { id: event.task_id }) : null
                }
              />
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

function TimelineStep({
  event,
  last,
  taskLabel,
}: {
  event: AgentRunEventItem;
  last: boolean;
  taskLabel: string | null;
}) {
  const tone = eventTone(event.event_type, event.message || "");
  const Icon = eventIcon(event.event_type, event.message || "");
  const hasPayload = Object.keys(event.payload || {}).length > 0;
  const [open, setOpen] = useState(tone === "danger" || tone === "warning");

  return (
    <li className="relative grid grid-cols-[2rem_minmax(0,1fr)] gap-3 pb-5">
      {!last ? (
        <span
          aria-hidden
          className="absolute left-[0.9375rem] top-9 bottom-0 w-px bg-border"
        />
      ) : null}
      <div className="relative z-[1] flex justify-center pt-1">
        <span
          className={cn(
            "flex h-8 w-8 items-center justify-center rounded-full border",
            TONE_RING[tone],
          )}
        >
          <Icon className={cn("h-3.5 w-3.5", Icon === Loader2 && "animate-spin")} />
        </span>
      </div>
      <article className="min-w-0 rounded-lg border border-border/70 bg-background/45">
        <button
          type="button"
          className="flex w-full flex-col gap-2 p-3.5 text-left sm:flex-row sm:items-start sm:justify-between"
          onClick={() => hasPayload && setOpen((v) => !v)}
          disabled={!hasPayload}
        >
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className={cn("rounded-full border px-2.5 py-0.5 text-[11px] font-semibold", TONE_PILL[tone])}>
                {event.event_type.replaceAll("_", " ")}
              </span>
              {taskLabel ? (
                <span className="rounded-md border border-border/70 bg-card/60 px-2 py-0.5 text-[11px] text-muted-foreground">
                  {taskLabel}
                </span>
              ) : null}
            </div>
            <p className="mt-2 text-sm font-medium leading-6 text-foreground">
              {event.message || event.event_type}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
            <span>{formatCompactDateTime(event.created_at)}</span>
            {hasPayload ? (
              <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", open && "rotate-180")} />
            ) : null}
          </div>
        </button>
        {hasPayload && open ? (
          <pre className="mx-3.5 mb-3.5 max-h-56 overflow-auto rounded-lg border border-border/70 bg-card/65 px-3 py-3 font-mono text-xs whitespace-pre-wrap text-muted-foreground">
            {JSON.stringify(event.payload, null, 2)}
          </pre>
        ) : null}
      </article>
    </li>
  );
}
