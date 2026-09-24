import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { ChevronDown } from "lucide-react";

import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export type InteractiveAlertItem = {
  id?: number | string;
  server_id?: number | string;
  server_name?: string;
  severity?: string;
  title?: string;
  alert_type?: string;
};

type Props = {
  title?: string;
  items: InteractiveAlertItem[];
  onAsk?: (prompt: string) => void;
  /** Visible unique groups before expand (default 4). */
  previewLimit?: number;
};

type AlertGroup = {
  key: string;
  sample: InteractiveAlertItem;
  count: number;
  ids: Array<number | string>;
};

function sevDot(sev?: string) {
  const s = (sev || "").toLowerCase();
  if (s === "critical") return "bg-destructive/80";
  if (s === "warning") return "bg-warning/70";
  return "bg-muted-foreground/40";
}

function groupKey(a: InteractiveAlertItem): string {
  return [
    (a.title || "").trim().toLowerCase(),
    (a.severity || "").trim().toLowerCase(),
    (a.server_name || String(a.server_id || "")).trim().toLowerCase(),
    (a.alert_type || "").trim().toLowerCase(),
  ].join("|");
}

function groupAlerts(items: InteractiveAlertItem[]): AlertGroup[] {
  const map = new Map<string, AlertGroup>();
  for (const item of items) {
    const key = groupKey(item);
    const existing = map.get(key);
    if (existing) {
      existing.count += 1;
      if (item.id != null) existing.ids.push(item.id);
    } else {
      map.set(key, {
        key,
        sample: item,
        count: 1,
        ids: item.id != null ? [item.id] : [],
      });
    }
  }
  // Critical / higher count first
  return [...map.values()].sort((a, b) => {
    const sevRank = (s?: string) => {
      const v = (s || "").toLowerCase();
      if (v === "critical") return 0;
      if (v === "warning") return 1;
      return 2;
    };
    const d = sevRank(a.sample.severity) - sevRank(b.sample.severity);
    if (d !== 0) return d;
    return b.count - a.count;
  });
}

/** Compact alerts: dedupe identical rows, preview a few groups, expand the rest. */
export function InteractiveAlertsPanel({ title, items, onAsk, previewLimit = 4 }: Props) {
  const { lang } = useI18n();
  const [expanded, setExpanded] = useState(false);
  const groups = useMemo(() => groupAlerts(items), [items]);
  if (!groups.length) return null;

  const total = items.length;
  const unique = groups.length;
  const visible = expanded ? groups : groups.slice(0, previewLimit);
  const hidden = Math.max(0, unique - previewLimit);

  return (
    <div className="w-full max-w-[420px] overflow-hidden rounded-sm border border-border/40 bg-card/30">
      <div className="flex items-baseline justify-between gap-3 px-3 pt-2 pb-1">
        <span className="text-[11px] font-medium tracking-wide text-muted-foreground">
          {title?.replace(/\s*·\s*\d+\s*$/, "") || localize(lang, "Алерты", "Alerts")}
        </span>
        <span className="font-mono text-[10px] tabular-nums text-muted-foreground/70">
          {unique < total
            ? localize(lang, `${unique} типа · ${total}`, `${unique} kinds · ${total}`)
            : String(total)}
        </span>
      </div>

      <ul className="pb-1">
        {visible.map((g) => {
          const a = g.sample;
          const sid = a.server_id ? Number(a.server_id) : null;
          const meta = [a.server_name, a.severity].filter(Boolean).join(" · ");
          const askId = a.id ?? g.ids[0] ?? "?";
          return (
            <li key={g.key} className="group">
              <div className="flex items-center gap-2.5 px-3 py-1.5 transition-colors hover:bg-foreground/[0.03]">
                <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", sevDot(a.severity))} />
                <div className="min-w-0 flex-1">
                  <div className="flex min-w-0 items-baseline gap-2">
                    <span className="truncate text-[13px] font-medium tracking-tight text-foreground">
                      {a.title || "—"}
                    </span>
                    {g.count > 1 ? (
                      <span className="shrink-0 rounded-sm bg-destructive/10 px-1.5 py-px font-mono text-[10px] tabular-nums text-destructive">
                        ×{g.count}
                      </span>
                    ) : null}
                    {meta ? (
                      <span className="truncate text-[11px] text-muted-foreground/75">{meta}</span>
                    ) : null}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
                  {sid ? (
                    <Link
                      to={`/servers/${sid}/terminal`}
                      className="text-[11px] text-muted-foreground/80 underline-offset-2 hover:text-foreground hover:underline"
                    >
                      ssh
                    </Link>
                  ) : null}
                  <button
                    type="button"
                    className="text-[11px] text-muted-foreground/80 underline-offset-2 hover:text-foreground hover:underline"
                    onClick={() =>
                      onAsk?.(
                        `Разобери алерт #${askId} на ${a.server_name || "server"}: ${a.title || ""}.`,
                      )
                    }
                  >
                    {localize(lang, "Разбор", "Inspect")}
                  </button>
                </div>
              </div>
            </li>
          );
        })}
      </ul>

      {hidden > 0 ? (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex w-full items-center justify-center gap-1 border-t border-border/30 px-3 py-1.5 text-[11px] text-muted-foreground transition-colors hover:bg-foreground/[0.03] hover:text-foreground"
        >
          <ChevronDown className={cn("h-3 w-3 transition-transform", expanded && "rotate-180")} />
          {expanded
            ? localize(lang, "Свернуть", "Collapse")
            : localize(lang, `Ещё ${hidden}`, `${hidden} more`)}
        </button>
      ) : null}
    </div>
  );
}
