import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown, Pin, PinOff, Terminal } from "lucide-react";

import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export type InteractiveServerItem = {
  id: number | string;
  name: string;
  host?: string;
  port?: number | string;
  tags?: string[];
  ai_read_only?: boolean;
  os_family?: string;
  status?: string;
  terminal_url?: string;
  detail_url?: string;
};

export type ServerPanelActions = {
  pinnedIds?: number[];
  onPin?: (server: { id: number; name: string; host?: string }) => void;
  onUnpin?: (id: number) => void;
  onAsk?: (prompt: string) => void;
  onOpenTerminal?: (serverId: number) => void;
  /** Open chat-side live session dock */
  onOpenSession?: (server: { id: number; name: string; host?: string }) => void;
};

type Props = {
  title?: string;
  items: InteractiveServerItem[];
  actions?: ServerPanelActions;
  /** How many rows to show while collapsed (default 8 ≈ half of a typical fleet). */
  previewLimit?: number;
  /** If true, start fully expanded (default false — preview only). */
  defaultExpanded?: boolean;
  note?: string;
};

type StatusBucket = "critical" | "warning" | "healthy" | "unknown";

function statusBucket(status?: string): StatusBucket {
  const s = (status || "").toLowerCase();
  if (s === "critical" || s === "offline" || s === "unreachable") return "critical";
  if (s === "warning" || s === "degraded") return "warning";
  if (s === "online" || s === "healthy" || s === "ok") return "healthy";
  return "unknown";
}

function statusDot(status?: string, aiRo?: boolean) {
  if (aiRo) return "bg-warning/80";
  const b = statusBucket(status);
  if (b === "healthy") return "bg-success/80";
  if (b === "warning") return "bg-warning/70";
  if (b === "critical") return "bg-destructive/80";
  return "bg-muted-foreground/35";
}

function rank(status?: string): number {
  const b = statusBucket(status);
  if (b === "critical") return 0;
  if (b === "warning") return 1;
  if (b === "unknown") return 2;
  return 3;
}

/**
 * Compact fleet card for Operator chat.
 *
 * Full inventory dumps are noise when the answer is "all down" or "16 hosts".
 * We lead with a status summary and only preview the worst hosts; the rest
 * stays behind «Показать все».
 */
export function InteractiveServersPanel({
  title,
  items,
  actions,
  previewLimit = 8,
  defaultExpanded = false,
  note,
}: Props) {
  const { lang } = useI18n();
  const [openId, setOpenId] = useState<number | null>(null);
  const pinned = new Set(actions?.pinnedIds || []);

  const sorted = useMemo(() => {
    return [...items]
      .sort((a, b) => {
        const byStatus = rank(a.status) - rank(b.status);
        if (byStatus !== 0) return byStatus;
        return String(a.name || "").localeCompare(String(b.name || ""));
      })
      .slice(0, 80);
  }, [items]);

  const counts = useMemo(() => {
    const c = { critical: 0, warning: 0, healthy: 0, unknown: 0, total: sorted.length };
    for (const s of sorted) c[statusBucket(s.status)] += 1;
    return c;
  }, [sorted]);

  // Half-collapsed by default: first ~8 rows, expand for the rest.
  const limit = Math.max(1, Math.min(previewLimit, 12));
  const shouldCollapse = sorted.length > limit;
  const [expanded, setExpanded] = useState(() => Boolean(defaultExpanded));

  const visible = expanded || !shouldCollapse ? sorted : sorted.slice(0, limit);
  const hiddenCount = Math.max(0, sorted.length - visible.length);

  if (!sorted.length) return null;

  const summaryParts: string[] = [];
  if (counts.critical) {
    summaryParts.push(
      localize(lang, `${counts.critical} недоступны`, `${counts.critical} unreachable`),
    );
  }
  if (counts.warning) {
    summaryParts.push(localize(lang, `${counts.warning} warning`, `${counts.warning} warning`));
  }
  if (counts.healthy) {
    summaryParts.push(localize(lang, `${counts.healthy} ok`, `${counts.healthy} ok`));
  }
  if (counts.unknown) {
    summaryParts.push(localize(lang, `${counts.unknown} без данных`, `${counts.unknown} unknown`));
  }

  return (
    <div className="w-full max-w-[520px] overflow-hidden rounded-sm border border-border/40 bg-card/30">
      <div className="flex items-start justify-between gap-3 px-3.5 pt-2.5 pb-1.5">
        <div className="min-w-0">
          <div className="flex items-baseline gap-2">
            <span className="text-[11px] font-medium tracking-wide text-muted-foreground">
              {title?.replace(/\s*·\s*\d+\s*$/, "") || localize(lang, "Серверы", "Servers")}
            </span>
            <span className="text-[11px] tabular-nums text-muted-foreground/70">{counts.total}</span>
          </div>
          {summaryParts.length ? (
            <p className="mt-0.5 text-[12px] leading-4 text-foreground/85">
              {summaryParts.join(" · ")}
            </p>
          ) : null}
        </div>
      </div>

      {/* Tiny status bar for at-a-glance mix */}
      {counts.total > 1 ? (
        <div className="mx-3.5 mb-1.5 flex h-1 overflow-hidden rounded-full bg-muted/40">
          {counts.critical ? (
            <span className="bg-destructive/80" style={{ width: `${(counts.critical / counts.total) * 100}%` }} />
          ) : null}
          {counts.warning ? (
            <span className="bg-warning/70" style={{ width: `${(counts.warning / counts.total) * 100}%` }} />
          ) : null}
          {counts.healthy ? (
            <span className="bg-success/70" style={{ width: `${(counts.healthy / counts.total) * 100}%` }} />
          ) : null}
          {counts.unknown ? (
            <span className="bg-muted-foreground/35" style={{ width: `${(counts.unknown / counts.total) * 100}%` }} />
          ) : null}
        </div>
      ) : null}

      {note ? (
        <p className="px-3.5 pb-2 text-[11px] leading-4 text-muted-foreground">{note}</p>
      ) : null}

      <ul className="pb-1">
        {visible.map((s) => {
          const id = Number(s.id);
          const isPinned = pinned.has(id);
          const open = openId === id;
          const terminalUrl = s.terminal_url || `/servers/${id}/terminal`;
          const host = s.host ? `${s.host}${s.port ? `:${s.port}` : ""}` : "";
          const tags = (s.tags || []).slice(0, 2).join(", ");
          const statusLabel = s.status ? String(s.status) : "";
          // Skip empty "· []" meta noise from seed inventory.
          const meta = [host, tags || null, s.ai_read_only ? "RO" : null, statusLabel || null]
            .filter(Boolean)
            .join(" · ");

          return (
            <li key={id} className="group">
              <div
                className={cn(
                  "flex items-center gap-2.5 px-3.5 py-1.5 transition-colors hover:bg-foreground/[0.03]",
                  open && "bg-foreground/[0.03]",
                )}
              >
                <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", statusDot(s.status, s.ai_read_only))} />

                <button
                  type="button"
                  className="min-w-0 flex-1 text-left"
                  onClick={() => setOpenId(open ? null : id)}
                >
                  <div className="flex min-w-0 items-baseline gap-2">
                    <span className="truncate text-[13px] font-medium tracking-tight text-foreground">
                      {s.name}
                    </span>
                    {meta ? (
                      <span className="truncate text-[11px] text-muted-foreground/75">{meta}</span>
                    ) : null}
                  </div>
                </button>

                <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
                  {actions?.onOpenSession ? (
                    <button
                      type="button"
                      title={localize(lang, "Сессия в чате", "Session in chat")}
                      className="flex h-7 w-7 items-center justify-center rounded-full text-muted-foreground hover:bg-foreground/[0.06] hover:text-foreground"
                      onClick={(e) => {
                        e.stopPropagation();
                        actions.onOpenSession?.({ id, name: s.name, host: s.host });
                      }}
                    >
                      <Terminal className="h-3.5 w-3.5" />
                    </button>
                  ) : (
                    <Link
                      to={terminalUrl}
                      title={localize(lang, "Терминал", "Terminal")}
                      className="flex h-7 w-7 items-center justify-center rounded-full text-muted-foreground hover:bg-foreground/[0.06] hover:text-foreground"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <Terminal className="h-3.5 w-3.5" />
                    </Link>
                  )}
                  <button
                    type="button"
                    title={isPinned ? localize(lang, "Открепить", "Unpin") : localize(lang, "Пин", "Pin")}
                    className="flex h-7 w-7 items-center justify-center rounded-full text-muted-foreground hover:bg-foreground/[0.06] hover:text-foreground"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (isPinned) actions?.onUnpin?.(id);
                      else actions?.onPin?.({ id, name: s.name, host: s.host });
                    }}
                  >
                    {isPinned ? <PinOff className="h-3.5 w-3.5 text-foreground/80" /> : <Pin className="h-3.5 w-3.5" />}
                  </button>
                </div>
              </div>

              {open ? (
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3.5 pb-2 pl-[1.625rem] text-[11px]">
                  <Link to={terminalUrl} className="text-muted-foreground/80 underline-offset-2 hover:text-foreground hover:underline">
                    {localize(lang, "Подключиться", "Connect")}
                  </Link>
                  <button
                    type="button"
                    className="text-muted-foreground/80 underline-offset-2 hover:text-foreground hover:underline"
                    onClick={() =>
                      actions?.onAsk?.(
                        `Сделай диагностику @${s.name}: uptime, df -h, free -h, load, свежие алерты.`,
                      )
                    }
                  >
                    {localize(lang, "Диагностика", "Diagnose")}
                  </button>
                  <button
                    type="button"
                    className="text-muted-foreground/80 underline-offset-2 hover:text-foreground hover:underline"
                    onClick={() => actions?.onAsk?.(`Покажи метрики CPU/memory/disk для @${s.name}`)}
                  >
                    {localize(lang, "Метрики", "Metrics")}
                  </button>
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>

      {shouldCollapse ? (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex w-full items-center justify-center gap-1 border-t border-border/30 px-3 py-2 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-foreground/[0.03] hover:text-foreground"
        >
          <ChevronDown className={cn("h-3.5 w-3.5 transition-transform", expanded && "rotate-180")} />
          {expanded
            ? localize(lang, "Свернуть список", "Collapse list")
            : localize(
                lang,
                `Показать все ${sorted.length} (+${hiddenCount})`,
                `Show all ${sorted.length} (+${hiddenCount})`,
              )}
        </button>
      ) : null}
    </div>
  );
}
