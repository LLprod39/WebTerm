import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Bell, Bot, Siren } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { enUS, ru } from "date-fns/locale";

import { fetchAgentDashboardRuns, fetchMonitoringDashboard } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { isRunFailure, isRunFinished } from "@/lib/runStatus";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

const SEEN_IDS_KEY = "webterm.notifications.seenIds";
const SEEN_AT_LEGACY_KEY = "webterm.notifications.seenAt";
/** Cap stored ids so localStorage stays small. */
const MAX_SEEN_IDS = 400;

type FeedItem = {
  id: string;
  kind: "alert" | "run";
  title: string;
  detail: string;
  at: string;
  href: string;
  severity: "info" | "warning" | "critical" | "success";
  dayKey: string;
};

function dayKey(iso: string): string {
  try {
    return new Date(iso).toISOString().slice(0, 10);
  } catch {
    return "unknown";
  }
}

function dayLabel(key: string, lang: "ru" | "en"): string {
  if (key === "unknown") return localize(lang, "Без даты", "No date");
  const today = new Date().toISOString().slice(0, 10);
  const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
  if (key === today) return localize(lang, "Сегодня", "Today");
  if (key === yesterday) return localize(lang, "Вчера", "Yesterday");
  try {
    return new Date(key).toLocaleDateString(lang === "ru" ? "ru-RU" : "en-US", {
      day: "numeric",
      month: "long",
    });
  } catch {
    return key;
  }
}

function loadSeenIds(): Set<string> {
  try {
    const raw = localStorage.getItem(SEEN_IDS_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.filter((id): id is string => typeof id === "string"));
  } catch {
    return new Set();
  }
}

function persistSeenIds(ids: Set<string>) {
  try {
    // Keep the most recently added ids (Set iteration is insertion order).
    const arr = Array.from(ids);
    const trimmed = arr.length > MAX_SEEN_IDS ? arr.slice(arr.length - MAX_SEEN_IDS) : arr;
    localStorage.setItem(SEEN_IDS_KEY, JSON.stringify(trimmed));
    // Drop legacy watermark so old buggy logic never comes back.
    localStorage.removeItem(SEEN_AT_LEGACY_KEY);
  } catch {
    // ignore quota / private mode
  }
}

/**
 * Aggregates monitoring alerts + finished agent runs into a slide-over feed.
 * Unread badge is driven by persisted item ids (not timestamps) so viewing
 * clears the badge across reloads even when server clocks skew.
 */
export function NotificationCenter() {
  const { lang } = useI18n();
  const [open, setOpen] = useState(false);
  const [seenIds, setSeenIds] = useState<Set<string>>(() => loadSeenIds());

  const monQuery = useQuery({
    queryKey: ["monitoring-dashboard"],
    queryFn: fetchMonitoringDashboard,
    staleTime: 30_000,
    refetchInterval: open ? 20_000 : 60_000,
  });

  const runsQuery = useQuery({
    queryKey: ["agent-dashboard-runs"],
    queryFn: fetchAgentDashboardRuns,
    staleTime: 20_000,
    refetchInterval: open ? 15_000 : 45_000,
  });

  const items = useMemo(() => {
    const feed: FeedItem[] = [];

    for (const alert of monQuery.data?.alerts ?? []) {
      if (alert.is_resolved) continue;
      feed.push({
        id: `alert-${alert.id}`,
        kind: "alert",
        title: alert.title,
        detail: `${alert.server_name} · ${alert.message}`,
        at: alert.created_at,
        href: `/servers/${alert.server_id}/terminal`,
        severity: alert.severity === "critical" ? "critical" : alert.severity === "warning" ? "warning" : "info",
        dayKey: dayKey(alert.created_at),
      });
    }

    for (const run of runsQuery.data?.recent ?? []) {
      if (!isRunFinished(run.status)) continue;
      const failed = isRunFailure(run.status);
      feed.push({
        id: `run-${run.id}`,
        kind: "run",
        title: failed
          ? localize(lang, `Сбой: ${run.agent_name}`, `Failed: ${run.agent_name}`)
          : localize(lang, `Готово: ${run.agent_name}`, `Done: ${run.agent_name}`),
        detail: run.server_name,
        at: run.completed_at || run.started_at,
        href: `/agents/run/${run.id}`,
        severity: failed ? "warning" : "success",
        dayKey: dayKey(run.completed_at || run.started_at),
      });
    }

    feed.sort((a, b) => new Date(b.at).getTime() - new Date(a.at).getTime());
    return feed.slice(0, 40);
  }, [lang, monQuery.data?.alerts, runsQuery.data?.recent]);

  const markItemsSeen = useCallback((feed: FeedItem[]) => {
    if (!feed.length) return;
    setSeenIds((prev) => {
      let changed = false;
      const next = new Set(prev);
      for (const item of feed) {
        if (!next.has(item.id)) {
          next.add(item.id);
          changed = true;
        }
      }
      if (!changed) return prev;
      persistSeenIds(next);
      return next;
    });
  }, []);

  // While the panel is open, anything currently listed is considered read
  // (including items that appear mid-session after a refetch).
  useEffect(() => {
    if (!open || items.length === 0) return;
    markItemsSeen(items);
  }, [open, items, markItemsSeen]);

  const unread = useMemo(
    () => items.reduce((count, item) => count + (seenIds.has(item.id) ? 0 : 1), 0),
    [items, seenIds],
  );

  const grouped = useMemo(() => {
    const map = new Map<string, FeedItem[]>();
    for (const item of items) {
      const list = map.get(item.dayKey) ?? [];
      list.push(item);
      map.set(item.dayKey, list);
    }
    return Array.from(map.entries());
  }, [items]);

  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          // Mark whatever is already loaded; effect above covers late loads.
          markItemsSeen(items);
        }
      }}
    >
      <SheetTrigger asChild>
        <button
          type="button"
          className={cn(
            "relative flex h-9 w-9 items-center justify-center rounded-lg border border-border bg-card",
            "text-muted-foreground transition-colors hover:border-border-strong hover:text-foreground",
          )}
          aria-label={localize(lang, "Уведомления", "Notifications")}
          title={localize(lang, "Уведомления", "Notifications")}
        >
          <Bell className="h-4 w-4" aria-hidden />
          {unread > 0 ? (
            <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-bold text-destructive-foreground">
              {unread > 9 ? "9+" : unread}
            </span>
          ) : null}
        </button>
      </SheetTrigger>
      <SheetContent side="right" className="flex w-full flex-col gap-0 p-0 sm:max-w-md">
        <SheetHeader className="border-b border-border px-4 py-3 text-left">
          <div className="flex items-start justify-between gap-2 pr-8">
            <div>
              <SheetTitle className="text-base">
                {localize(lang, "Уведомления", "Notifications")}
              </SheetTitle>
              <p className="text-xs text-muted-foreground">
                {localize(
                  lang,
                  "Алерты мониторинга и завершённые прогоны",
                  "Monitoring alerts and finished runs",
                )}
              </p>
            </div>
            {items.length > 0 ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-8 shrink-0 text-xs text-muted-foreground"
                onClick={() => markItemsSeen(items)}
              >
                {localize(lang, "Прочитать все", "Mark all read")}
              </Button>
            ) : null}
          </div>
        </SheetHeader>

        <ScrollArea className="flex-1">
          <div className="px-3 py-3">
            {grouped.length === 0 ? (
              <div className="workspace-empty rounded-lg border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">
                {localize(lang, "Пока тихо — новых событий нет", "All quiet — no new events")}
              </div>
            ) : (
              grouped.map(([key, dayItems]) => (
                <section key={key} className="mb-4">
                  <h3 className="mb-2 px-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                    {dayLabel(key, lang)}
                  </h3>
                  <ul className="space-y-1.5">
                    {dayItems.map((item) => {
                      const isUnread = !seenIds.has(item.id);
                      return (
                        <li key={item.id}>
                          <Link
                            to={item.href}
                            onClick={() => {
                              markItemsSeen([item]);
                              setOpen(false);
                            }}
                            className={cn(
                              "flex gap-3 rounded-lg border px-3 py-2.5 transition-colors",
                              "hover:border-border-strong hover:bg-surface-1",
                              isUnread
                                ? "border-primary/30 bg-primary/5"
                                : "border-border bg-card",
                            )}
                          >
                            <span
                              className={cn(
                                "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md border",
                                item.severity === "critical" && "border-destructive/40 bg-destructive/10 text-destructive",
                                item.severity === "warning" && "border-warning/40 bg-warning/10 text-warning",
                                item.severity === "success" && "border-success/40 bg-success/10 text-success",
                                item.severity === "info" && "border-info/40 bg-info/10 text-info",
                              )}
                            >
                              {item.kind === "alert" ? (
                                <Siren className="h-3.5 w-3.5" />
                              ) : (
                                <Bot className="h-3.5 w-3.5" />
                              )}
                            </span>
                            <span className="min-w-0 flex-1">
                              <span className="flex items-center gap-2">
                                <span className="block truncate text-sm font-medium text-foreground">
                                  {item.title}
                                </span>
                                {isUnread ? (
                                  <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary" aria-hidden />
                                ) : null}
                              </span>
                              <span className="mt-0.5 block truncate text-xs text-muted-foreground">{item.detail}</span>
                              <span className="mt-1 block text-[11px] text-muted-foreground/80">
                                {formatDistanceToNow(new Date(item.at), {
                                  addSuffix: true,
                                  locale: lang === "ru" ? ru : enUS,
                                })}
                              </span>
                            </span>
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                </section>
              ))
            )}
          </div>
        </ScrollArea>

        <div className="border-t border-border p-3">
          <Button variant="outline" size="sm" className="w-full" asChild>
            <Link to="/monitoring" onClick={() => setOpen(false)}>
              {localize(lang, "Открыть Insights", "Open Insights")}
            </Link>
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
}
