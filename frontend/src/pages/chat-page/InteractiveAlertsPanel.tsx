import { Link } from "react-router-dom";

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
};

function sevDot(sev?: string) {
  const s = (sev || "").toLowerCase();
  if (s === "critical") return "bg-destructive/80";
  if (s === "warning") return "bg-warning/70";
  return "bg-muted-foreground/40";
}

/** Extreme-minimal alerts list for Operator chat. */
export function InteractiveAlertsPanel({ title, items, onAsk }: Props) {
  const { lang } = useI18n();
  const rows = items.slice(0, 30);
  if (!rows.length) return null;

  return (
    <div className="max-w-[min(520px,100%)] animate-in fade-in-0 duration-300 overflow-hidden rounded-sm border border-border/40 bg-card/30">
      <div className="flex items-baseline justify-between gap-3 px-3.5 pt-2.5 pb-1">
        <span className="text-[11px] font-medium tracking-wide text-muted-foreground">
          {title?.replace(/\s*·\s*\d+\s*$/, "") || localize(lang, "Алерты", "Alerts")}
        </span>
        <span className="text-[11px] tabular-nums text-muted-foreground/70">{rows.length}</span>
      </div>

      <ul className="pb-1">
        {rows.map((a, idx) => {
          const sid = a.server_id ? Number(a.server_id) : null;
          const meta = [a.server_name, a.severity].filter(Boolean).join(" · ");
          return (
            <li key={String(a.id ?? idx)} className="group">
              <div className="flex items-center gap-2.5 px-3.5 py-1.5 transition-colors hover:bg-foreground/[0.03]">
                <span className={cn("h-1 w-1 shrink-0 rounded-full", sevDot(a.severity))} />
                <div className="min-w-0 flex-1">
                  <div className="flex min-w-0 items-baseline gap-2">
                    <span className="truncate text-[13px] font-medium tracking-tight text-foreground">
                      {a.title || "—"}
                    </span>
                    {meta ? (
                      <span className="truncate text-[11px] text-muted-foreground/75">{meta}</span>
                    ) : null}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2 opacity-0 transition-opacity group-hover:opacity-100">
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
                        `Разобери алерт #${a.id || "?"} на ${a.server_name || "server"}: ${a.title || ""}.`,
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
    </div>
  );
}
