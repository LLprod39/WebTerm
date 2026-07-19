import { useMemo, useState } from "react";
import { ListFilter, Search } from "lucide-react";

import type { AgentRunReportEvent, AgentRunReportResponse, AgentRunReportSeverity } from "@/lib/api";
import { StatusBadge } from "@/components/system/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

import { formatCompactDateTime } from "./formatters";
import {
  _severityRank,
  EVENT_PAGE_SIZE,
  eventCategoryLabel,
  eventModeLabel,
  eventPhaseLabel,
  eventDot,
  severityLabel,
  severityTone,
} from "./reportShared";


export function EventsTab({ report }: { report: AgentRunReportResponse }) {
  const [filter, setFilter] = useState<AgentRunReportSeverity | "all">("all");
  const [mode, setMode] = useState<"brief" | "all" | "debug">("brief");
  const [query, setQuery] = useState("");
  const [visibleCount, setVisibleCount] = useState(EVENT_PAGE_SIZE);

  const summary = useMemo(() => normalizeEventSummary(report), [report]);
  const phaseMeta = useMemo(() => {
    const map = new Map<string, { label: string; count: number; important: number; problems: number }>();
    for (const group of report.event_groups || []) {
      map.set(String(group.phase || "activity"), {
        label: group.label || eventPhaseLabel[String(group.phase)] || String(group.phase || "activity"),
        count: Number(group.count || group.events?.length || 0),
        important: Number(group.important || 0),
        problems: Number(group.problems || 0),
      });
    }
    return map;
  }, [report.event_groups]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return report.events.filter((event) => {
      if (filter !== "all" && event.severity !== filter) return false;
      if (mode === "brief" && !event.important) return false;
      if (!q) return true;
      return eventSearchText(event).includes(q);
    });
  }, [filter, mode, query, report.events]);

  const visible = filtered.slice(0, visibleCount);
  const hasMore = visible.length < filtered.length;
  const grouped = groupEventsByPhase(visible, phaseMeta);
  const categoryEntries = Object.entries(summary.categories || {});
  const phaseEntries = report.event_groups?.length
    ? report.event_groups
    : grouped.map((group) => ({
        phase: group.phase,
        label: group.label,
        count: group.events.length,
        important: group.events.filter((event) => event.important).length,
        problems: group.events.filter((event) => _severityRank(event.severity) >= _severityRank("warning")).length,
      }));
  const latestImportant = summary.latest_important;

  return (
    <div className="enterprise-panel overflow-hidden">
      <div className="border-b border-border/70 p-4">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <div>
            <h3 className="text-base font-semibold text-foreground">Хронология событий</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              {report.events.length} событий в журнале, показано {visible.length} из {filtered.length}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex flex-wrap items-center gap-1 rounded-lg border border-border/70 bg-background/45 p-1">
              {(["brief", "all", "debug"] as const).map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => {
                    setMode(item);
                    setVisibleCount(EVENT_PAGE_SIZE);
                  }}
                  className={cn(
                    "rounded-md px-2.5 py-1 text-xs font-medium transition-colors",
                    mode === item ? "bg-card text-foreground" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {eventModeLabel[item]}
                </button>
              ))}
            </div>
            <div className="flex flex-wrap items-center gap-1 rounded-lg border border-border/70 bg-background/45 p-1">
              <ListFilter className="ml-1 h-3.5 w-3.5 text-muted-foreground" />
              {(["all", "critical", "high", "warning", "info", "success"] as const).map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => {
                    setFilter(item);
                    setVisibleCount(EVENT_PAGE_SIZE);
                  }}
                  className={cn(
                    "rounded-md px-2 py-1 text-xs font-medium transition-colors",
                    filter === item ? "bg-card text-foreground" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {item === "all" ? "Severity" : severityLabel[item]}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-4 grid gap-3 xl:grid-cols-[minmax(0,1fr)_auto]">
          <div className="relative min-w-0">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setVisibleCount(EVENT_PAGE_SIZE);
              }}
              placeholder="Поиск по событиям, задачам, фазам и payload"
              className="pl-9"
            />
          </div>
          <div className="grid min-w-[360px] grid-cols-3 gap-2 max-sm:min-w-0">
            <EventMiniStat label="Важные" value={summary.important} />
            <EventMiniStat label="Проблемы" value={summary.problems} />
            <EventMiniStat label="Debug" value={summary.debug} />
          </div>
        </div>

        {latestImportant ? (
          <div className="mt-4 rounded-lg border border-border/70 bg-background/45 p-3">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0">
                <p className="text-2xs font-semibold uppercase tracking-wide text-muted-foreground">Последний важный сигнал</p>
                <p className="mt-1 break-words text-sm font-medium leading-6 text-foreground">
                  {latestImportant.title || latestImportant.message}
                </p>
                {latestImportant.summary ? <p className="mt-1 max-w-5xl text-xs leading-5 text-muted-foreground">{latestImportant.summary}</p> : null}
              </div>
              <div className="flex shrink-0 flex-wrap items-center gap-2">
                <StatusBadge label={severityLabel[latestImportant.severity]} tone={severityTone[latestImportant.severity]} />
                <span className="whitespace-nowrap text-xs text-muted-foreground">{formatCompactDateTime(latestImportant.created_at)}</span>
              </div>
            </div>
          </div>
        ) : null}

        {phaseEntries.length ? (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {phaseEntries.map((phase) => (
              <span
                key={String(phase.phase)}
                className={cn(
                  "rounded-md border px-2 py-1 text-xs",
                  Number(phase.problems || 0) > 0
                    ? "border-warning/35 bg-warning/10 text-warning"
                    : "border-border/70 bg-background/45 text-muted-foreground",
                )}
              >
                {phase.label || eventPhaseLabel[String(phase.phase)] || String(phase.phase)}: {phase.count}
                {Number(phase.problems || 0) > 0 ? ` · ${phase.problems} проблем` : ""}
              </span>
            ))}
          </div>
        ) : null}

        {categoryEntries.length ? (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {categoryEntries.map(([category, count]) => (
              <span key={category} className="rounded-md border border-border/70 bg-background/45 px-2 py-1 text-xs text-muted-foreground">
                {eventCategoryLabel[category] || category}: {count}
              </span>
            ))}
          </div>
        ) : null}
      </div>

      <div className="p-4">
        {visible.length ? (
          <div className="space-y-5">
            {grouped.map((group) => (
              <section key={group.phase} className="min-w-0">
                <div className="mb-3 flex items-center gap-3">
                  <span className="rounded-md border border-border/70 bg-secondary/45 px-2.5 py-1 text-xs font-semibold text-foreground">
                    {group.label}
                  </span>
                  <span className="font-mono text-xs text-muted-foreground">{group.events.length}</span>
                  <span className="h-px min-w-8 flex-1 bg-border/70" />
                </div>
                <ol className="space-y-0">
                  {group.events.map((event, index) => (
                    <EventTimelineItem
                      key={event.id}
                      event={event}
                      debugOpen={mode === "debug"}
                      showTechnical={mode !== "brief"}
                      last={index === group.events.length - 1}
                    />
                  ))}
                </ol>
              </section>
            ))}
          </div>
        ) : (
          <div className="workspace-empty text-sm text-muted-foreground">
            {mode === "brief" ? "Важных событий пока нет. Переключите на «Все», чтобы увидеть технический журнал." : "События не найдены."}
          </div>
        )}
        {hasMore ? (
          <div className="mt-4 flex justify-center">
            <Button variant="outline" size="sm" onClick={() => setVisibleCount((value) => value + EVENT_PAGE_SIZE)}>
              Показать ещё {Math.min(EVENT_PAGE_SIZE, filtered.length - visible.length)}
            </Button>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function EventMiniStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border/70 bg-background/45 px-3 py-2">
      <p className="text-2xs font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-0.5 font-mono text-sm font-semibold text-foreground">{value}</p>
    </div>
  );
}

function EventTimelineItem({
  event,
  debugOpen,
  showTechnical,
  last,
}: {
  event: AgentRunReportEvent;
  debugOpen: boolean;
  showTechnical: boolean;
  last: boolean;
}) {
  const hasPayload = Object.keys(event.payload || {}).length > 0;
  const showDetails = showTechnical || debugOpen;
  return (
    <li className="grid grid-cols-[20px_minmax(0,1fr)] gap-3">
      <div className="relative flex justify-center">
        <span className={cn("mt-3 h-2.5 w-2.5 rounded-full ring-4 ring-background", eventDot(event.severity))} />
        {!last ? <span className="absolute top-6 bottom-0 w-px bg-border/70" /> : null}
      </div>
      <article className="mb-3 min-w-0 rounded-lg border border-border/70 bg-background/45 px-4 py-3">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="mb-1.5 flex flex-wrap items-center gap-2">
              <StatusBadge label={severityLabel[event.severity]} tone={severityTone[event.severity]} />
              <span className="rounded-md border border-border/70 bg-card/60 px-2 py-0.5 font-mono text-xs text-muted-foreground">
                {eventCategoryLabel[event.category] || event.category || "event"}
              </span>
              {event.task_id !== null ? <span className="font-mono text-xs text-muted-foreground">task #{event.task_id}</span> : null}
              {event.important ? <span className="text-xs font-medium text-foreground">важное</span> : null}
            </div>
            <p className="break-words text-sm font-medium leading-6 text-foreground">{event.title || event.message}</p>
            {event.summary ? <p className="mt-1 max-w-4xl break-words text-xs leading-5 text-muted-foreground">{event.summary}</p> : null}
          </div>
          <span className="shrink-0 whitespace-nowrap text-xs text-muted-foreground">{formatCompactDateTime(event.created_at)}</span>
        </div>

        {showDetails ? (
          <details className="group mt-2" open={debugOpen}>
            <summary className="inline-flex cursor-pointer list-none items-center gap-2 font-mono text-xs text-muted-foreground hover:text-foreground">
              <span>{event.event_type}</span>
              {hasPayload ? <span className="text-muted-foreground/70">payload</span> : null}
            </summary>
            {hasPayload ? (
              <pre className="mt-2 max-h-56 max-w-full overflow-auto rounded-lg border border-border/70 bg-card/60 p-3 font-mono text-xs leading-5 text-muted-foreground">
                {JSON.stringify(event.payload, null, 2)}
              </pre>
            ) : (
              <p className="mt-2 text-xs text-muted-foreground">Технический payload пуст.</p>
            )}
          </details>
        ) : null}
      </article>
    </li>
  );
}

function eventSearchText(event: AgentRunReportEvent) {
  return [
    event.title,
    event.summary,
    event.message,
    event.event_type,
    event.category,
    event.phase,
    event.source,
    event.task_id,
    JSON.stringify(event.payload || {}),
  ]
    .filter((value) => value !== null && value !== undefined)
    .join("\n")
    .toLowerCase();
}

function normalizeEventSummary(report: AgentRunReportResponse) {
  if (report.event_summary) {
    return {
      total: Number(report.event_summary.total || report.events.length),
      important: Number(report.event_summary.important || 0),
      problems: Number(report.event_summary.problems || 0),
      debug: Number(report.event_summary.debug || 0),
      categories: report.event_summary.categories || {},
      severities: report.event_summary.severities || {},
      latest: report.event_summary.latest || null,
      latest_important: report.event_summary.latest_important || report.event_summary.latest || null,
    };
  }
  const categories: Record<string, number> = {};
  const severities: Record<string, number> = {};
  let important = 0;
  let problems = 0;
  let debug = 0;
  let latestImportant: AgentRunReportEvent | null = null;
  for (const event of report.events) {
    const category = event.category || "agent";
    categories[category] = (categories[category] || 0) + 1;
    severities[event.severity] = (severities[event.severity] || 0) + 1;
    if (event.important) {
      important += 1;
      latestImportant = event;
    }
    if (_severityRank(event.severity) >= _severityRank("warning")) problems += 1;
    if (Object.keys(event.payload || {}).length > 0) debug += 1;
  }
  return {
    total: report.events.length,
    important,
    problems,
    debug,
    categories,
    severities,
    latest: report.events[report.events.length - 1] || null,
    latest_important: latestImportant || report.events[report.events.length - 1] || null,
  };
}

function groupEventsByPhase(
  events: AgentRunReportEvent[],
  phaseMeta: Map<string, { label: string; count: number; important: number; problems: number }>,
) {
  const groups: Array<{ phase: string; label: string; events: AgentRunReportEvent[] }> = [];
  for (const event of events) {
    const phase = event.phase || "activity";
    const current = groups[groups.length - 1];
    if (!current || current.phase !== phase) {
      groups.push({ phase, label: phaseMeta.get(phase)?.label || eventPhaseLabel[phase] || phase, events: [event] });
    } else {
      current.events.push(event);
    }
  }
  return groups;
}

