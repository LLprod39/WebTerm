import { Activity } from "lucide-react";

import type { AgentRunDetail, AgentRunEventItem } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

import { eventTypeClasses, formatCompactDateTime } from "./formatters";
import { StatusBadge } from "./StatusBadge";

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
            <p className="mt-1 text-sm leading-6 text-muted-foreground">
              {t("run.timeline_desc")}
            </p>
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
            <p className="mt-1 text-sm text-muted-foreground">
              {t("run.timeline_empty_desc")}
            </p>
          </div>
        ) : (
          <div className="space-y-3 pt-5">
            {events.map((event) => (
              <div key={event.id} className="rounded-lg border border-border/70 bg-background/45 px-4 py-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`rounded-md border px-2.5 py-1 text-xs font-semibold ${eventTypeClasses(event.event_type)}`}>
                        {event.event_type.replaceAll("_", " ")}
                      </span>
                      {event.task_id !== null ? (
                        <span className="rounded-md border border-border/70 bg-card/60 px-2.5 py-1 text-xs text-muted-foreground">
                          {tr("run.task_id", { id: event.task_id })}
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-3 text-sm font-medium leading-6 text-foreground">{event.message || event.event_type}</p>
                    {Object.keys(event.payload || {}).length > 0 ? (
                      <pre className="mt-3 overflow-x-auto rounded-lg border border-border/70 bg-card/65 px-3 py-3 font-mono text-xs whitespace-pre-wrap text-muted-foreground">
                        {JSON.stringify(event.payload, null, 2)}
                      </pre>
                    ) : null}
                  </div>
                  <div className="shrink-0 text-xs text-muted-foreground">
                    {formatCompactDateTime(event.created_at)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
