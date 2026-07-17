import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Pin, PinOff, Terminal } from "lucide-react";

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
};

type Props = {
  title?: string;
  items: InteractiveServerItem[];
  actions?: ServerPanelActions;
};

function statusDot(status?: string, aiRo?: boolean) {
  if (aiRo) return "bg-warning/80";
  const s = (status || "").toLowerCase();
  if (s === "online" || s === "healthy") return "bg-success/80";
  if (s === "warning") return "bg-warning/70";
  if (s === "critical" || s === "offline" || s === "unreachable") return "bg-destructive/80";
  return "bg-muted-foreground/35";
}

/** Extreme-minimal server list for Operator chat. */
export function InteractiveServersPanel({ title, items, actions }: Props) {
  const { lang } = useI18n();
  const [openId, setOpenId] = useState<number | null>(null);
  const pinned = new Set(actions?.pinnedIds || []);
  const rows = useMemo(() => items.slice(0, 40), [items]);

  if (!rows.length) return null;

  return (
    <div className="max-w-[min(520px,100%)] animate-in fade-in-0 duration-300 overflow-hidden rounded-sm border border-border/40 bg-card/30">
      <div className="flex items-baseline justify-between gap-3 px-3.5 pt-2.5 pb-1">
        <span className="text-[11px] font-medium tracking-wide text-muted-foreground">
          {title?.replace(/\s*·\s*\d+\s*$/, "") || localize(lang, "Серверы", "Servers")}
        </span>
        <span className="text-[11px] tabular-nums text-muted-foreground/70">{rows.length}</span>
      </div>

      <ul className="pb-1">
        {rows.map((s) => {
          const id = Number(s.id);
          const isPinned = pinned.has(id);
          const open = openId === id;
          const terminalUrl = s.terminal_url || `/servers/${id}/terminal`;
          const host = s.host ? `${s.host}${s.port ? `:${s.port}` : ""}` : "";
          const tags = (s.tags || []).slice(0, 2).join(", ");
          const meta = [host, tags, s.ai_read_only ? "RO" : ""].filter(Boolean).join(" · ");

          return (
            <li key={id} className="group">
              <div
                className={cn(
                  "flex items-center gap-2.5 px-3.5 py-1.5 transition-colors hover:bg-foreground/[0.03]",
                  open && "bg-foreground/[0.03]",
                )}
              >
                <span className={cn("h-1 w-1 shrink-0 rounded-full", statusDot(s.status, s.ai_read_only))} />

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
                  <Link
                    to={terminalUrl}
                    title={localize(lang, "Терминал", "Terminal")}
                    className="flex h-7 w-7 items-center justify-center rounded-full text-muted-foreground hover:bg-foreground/[0.06] hover:text-foreground"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <Terminal className="h-3.5 w-3.5" />
                  </Link>
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
    </div>
  );
}
