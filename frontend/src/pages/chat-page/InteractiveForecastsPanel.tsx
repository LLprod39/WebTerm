import { useMemo, useState } from "react";

import { Sparkline } from "@/components/dashboard/Sparkline";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export type InteractiveForecastItem = {
  id?: number | string;
  server_id?: number | string;
  server_name?: string;
  kind?: string;
  target?: string;
  severity?: string;
  eta_days?: number | string | null;
  current_value?: number | string | null;
  threshold?: number | string | null;
  unit?: string;
  slope_per_day?: number | string | null;
  series?: number[];
  message?: string;
};

export type ForecastPanelActions = {
  onAsk?: (prompt: string) => void;
};

type Props = {
  title?: string;
  items: InteractiveForecastItem[];
  summary?: string;
  empty?: boolean;
  actions?: ForecastPanelActions;
};

function sevTone(sev?: string) {
  const s = (sev || "").toLowerCase();
  if (s === "critical") return "text-destructive/90";
  if (s === "warning" || s === "high") return "text-warning/90";
  return "text-muted-foreground/80";
}

function sevDot(sev?: string) {
  const s = (sev || "").toLowerCase();
  if (s === "critical") return "bg-destructive/80";
  if (s === "warning" || s === "high") return "bg-warning/70";
  if (s === "info") return "bg-foreground/30";
  return "bg-muted-foreground/30";
}

function kindShort(kind?: string) {
  switch ((kind || "").toLowerCase()) {
    case "disk_full":
      return "disk";
    case "inode_full":
      return "inode";
    case "memory_pressure":
      return "mem";
    case "swap_growth":
      return "swap";
    case "log_error_surge":
      return "logs";
    case "cert_expiry":
      return "cert";
    case "cert_changed":
      return "certΔ";
    default:
      return (kind || "—").slice(0, 8);
  }
}

function targetShort(target?: string) {
  if (!target) return "";
  // disk:/var → /var · cert:443 → :443
  if (target.startsWith("disk:")) return target.slice(5);
  if (target.startsWith("inode:")) return target.slice(6);
  if (target.startsWith("cert:")) return `:${target.slice(5)}`;
  return target;
}

function etaShort(eta: number | string | null | undefined, lang: "ru" | "en") {
  if (eta === null || eta === undefined || eta === "") return "";
  const n = typeof eta === "number" ? eta : Number(eta);
  if (Number.isNaN(n)) return "";
  if (n < 1) return localize(lang, "<1д", "<1d");
  if (n < 10) return `${n.toFixed(1)}${localize(lang, "д", "d")}`;
  return `${Math.round(n)}${localize(lang, "д", "d")}`;
}

function valueShort(item: InteractiveForecastItem) {
  const v = item.current_value;
  if (v === null || v === undefined || v === "") return "";
  const n = typeof v === "number" ? v : Number(v);
  if (Number.isNaN(n)) return String(v);
  const unit = (item.unit || "").trim();
  if (unit === "%" || unit === "percent") return `${Math.round(n)}%`;
  if (unit.toLowerCase() === "days" || unit === "д") return `${n < 10 ? n.toFixed(1) : Math.round(n)}д`;
  if (unit.toUpperCase() === "MB") return n >= 1024 ? `${(n / 1024).toFixed(1)}G` : `${Math.round(n)}M`;
  if (!unit) return n < 10 ? n.toFixed(1) : String(Math.round(n));
  return `${n < 10 ? n.toFixed(1) : Math.round(n)}${unit}`;
}

/**
 * Metrics-style forecasts: one quiet row + optional mini spark.
 * Operator does the looking via tools; this card only shows facts.
 */
export function InteractiveForecastsPanel({ title, items, empty, actions }: Props) {
  const { lang } = useI18n();
  const [openId, setOpenId] = useState<string | null>(null);
  const rows = useMemo(() => items.slice(0, 24), [items]);
  const isEmpty = empty || rows.length === 0;

  return (
    <div className="w-full max-w-[420px] overflow-hidden rounded-sm border border-border/40 bg-card/30">
      <div className="flex items-baseline justify-between gap-3 px-3 pt-2 pb-0.5">
        <span className="text-[11px] font-medium tracking-wide text-muted-foreground">
          {title?.replace(/\s*·\s*\d+\s*$/, "") || localize(lang, "Прогнозы", "Forecasts")}
        </span>
        <span className="text-[11px] tabular-nums text-muted-foreground/60">{isEmpty ? 0 : rows.length}</span>
      </div>

      {isEmpty ? (
        <div className="flex items-center justify-between gap-3 px-3 pb-2.5 pt-1">
          <span className="text-[13px] font-medium tracking-tight text-foreground/90">ok</span>
          <button
            type="button"
            className="text-[11px] text-muted-foreground/70 underline-offset-2 hover:text-foreground hover:underline"
            onClick={() =>
              actions?.onAsk?.(
                "Перепроверь прогнозы и fleet_status. Коротко: ok или риски.",
              )
            }
          >
            {localize(lang, "check", "check")}
          </button>
        </div>
      ) : (
        <ul className="pb-1">
          {rows.map((p, idx) => {
            const key = String(p.id ?? `${p.server_id}-${p.kind}-${p.target}-${idx}`);
            const open = openId === key;
            const series = Array.isArray(p.series) ? p.series.filter((n) => typeof n === "number" && !Number.isNaN(n)) : [];
            const eta = etaShort(p.eta_days, lang);
            const val = valueShort(p);
            const meta = [kindShort(p.kind), targetShort(p.target)].filter(Boolean).join(" ");
            const right = [val, eta].filter(Boolean).join(" · ");

            return (
              <li key={key}>
                <button
                  type="button"
                  className={cn(
                    "flex w-full items-center gap-2.5 px-3 py-1.5 text-left transition-colors hover:bg-foreground/[0.03]",
                    open && "bg-foreground/[0.03]",
                  )}
                  onClick={() => setOpenId(open ? null : key)}
                >
                  <span className={cn("h-1 w-1 shrink-0 rounded-full", sevDot(p.severity))} />
                  <div className="min-w-0 flex-1">
                    <div className="flex min-w-0 items-baseline gap-1.5">
                      <span className="truncate text-[13px] font-medium tracking-tight text-foreground">
                        {p.server_name || "—"}
                      </span>
                      <span className="truncate text-[11px] text-muted-foreground/70">{meta}</span>
                    </div>
                  </div>
                  {right ? (
                    <span className={cn("shrink-0 text-[11px] tabular-nums", sevTone(p.severity))}>
                      {right}
                    </span>
                  ) : null}
                  {series.length >= 2 ? (
                    <div className={cn("h-5 w-12 shrink-0 overflow-hidden", sevTone(p.severity))}>
                      <Sparkline data={series} width={48} height={20} strokeWidth={1.25} className="h-5 w-12" />
                    </div>
                  ) : null}
                </button>

                {open ? (
                  <div className="space-y-1.5 px-3 pb-2 pl-[1.375rem]">
                    {series.length >= 2 ? (
                      <div className={cn("h-8 w-full max-w-[240px] overflow-hidden", sevTone(p.severity))}>
                        <Sparkline data={series} width={240} height={32} strokeWidth={1.25} className="h-8 w-full" />
                      </div>
                    ) : null}
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-muted-foreground/80">
                      {p.threshold != null && p.threshold !== "" ? (
                        <span>
                          thr {String(p.threshold)}
                          {p.unit === "%" ? "%" : p.unit ? ` ${p.unit}` : ""}
                        </span>
                      ) : null}
                      {p.slope_per_day != null && Number(p.slope_per_day) !== 0 ? (
                        <span className="tabular-nums">
                          {Number(p.slope_per_day) > 0 ? "+" : ""}
                          {Number(p.slope_per_day).toFixed(2)}
                          /d
                        </span>
                      ) : null}
                      <button
                        type="button"
                        className="underline-offset-2 hover:text-foreground hover:underline"
                        onClick={(e) => {
                          e.stopPropagation();
                          actions?.onAsk?.(
                            `Метрики и короткий анализ: @${p.server_name || "server"} ${kindShort(p.kind)} ${targetShort(p.target)}. operator.metric_series + вывод в 2 строки.`,
                          );
                        }}
                      >
                        {localize(lang, "метрики", "metrics")}
                      </button>
                      <button
                        type="button"
                        className="underline-offset-2 hover:text-foreground hover:underline"
                        onClick={(e) => {
                          e.stopPropagation();
                          actions?.onAsk?.(
                            `Разбор @${p.server_name}: ${p.kind}/${p.target}, ETA ${p.eta_days ?? "—"}. 3 пункта: риск · факт · действие.`,
                          );
                        }}
                      >
                        {localize(lang, "разбор", "inspect")}
                      </button>
                    </div>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
