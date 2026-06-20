import { Activity } from "lucide-react";

import type { AgentRunDetail, AgentRunEventItem } from "@/lib/api";

import { eventTypeClasses, formatCompactDateTime } from "./formatters";
import { StatusBadge } from "./StatusBadge";

export function TimelineView({ run, events }: { run: AgentRunDetail; events: AgentRunEventItem[] }) {
  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-5 px-4 py-5 sm:px-6">
      <div className="rounded-[28px] border border-border/70 bg-card/55 px-5 py-5 shadow-[0_22px_64px_rgba(0,0,0,0.18)]">
        <div className="flex flex-col gap-3 border-b border-border/70 pb-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-border/70 bg-background/60 px-3 py-1 text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
              <Activity className="h-3 w-3" />
              Run timeline
            </div>
            <h2 className="mt-4 text-2xl font-semibold tracking-[-0.03em] text-foreground">{run.agent_name}</h2>
            <p className="mt-1 text-sm leading-6 text-muted-foreground">
              Persistent event stream for planning, subagents, tool work, approvals, and failures.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge status={run.status} />
            <span className="rounded-full border border-border/70 bg-background/60 px-3 py-1 text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
              {events.length} events
            </span>
          </div>
        </div>

        {events.length === 0 ? (
          <div className="flex flex-col items-center justify-center px-4 py-16 text-center">
            <Activity className="mb-4 h-10 w-10 text-muted-foreground/35" />
            <p className="text-sm text-foreground">Timeline is still empty.</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Events will appear as soon as the background runtime starts emitting activity.
            </p>
          </div>
        ) : (
          <div className="space-y-3 pt-5">
            {events.map((event) => (
              <div key={event.id} className="rounded-[22px] border border-border/70 bg-background/45 px-4 py-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] ${eventTypeClasses(event.event_type)}`}>
                        {event.event_type.replaceAll("_", " ")}
                      </span>
                      {event.task_id !== null ? (
                        <span className="rounded-full border border-border/70 bg-card/60 px-2.5 py-1 text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                          task #{event.task_id}
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-3 text-sm font-medium leading-6 text-foreground">{event.message || event.event_type}</p>
                    {Object.keys(event.payload || {}).length > 0 ? (
                      <pre className="mt-3 overflow-x-auto rounded-2xl border border-border/70 bg-card/65 px-3 py-3 font-mono text-[11px] whitespace-pre-wrap text-muted-foreground">
                        {JSON.stringify(event.payload, null, 2)}
                      </pre>
                    ) : null}
                  </div>
                  <div className="shrink-0 text-[11px] text-muted-foreground">
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
