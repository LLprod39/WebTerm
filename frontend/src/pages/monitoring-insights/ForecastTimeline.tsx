import { useMemo } from "react";
import { CalendarClock } from "lucide-react";

import type { InsightPrediction } from "@/api/monitoring-insights";
import { useI18n, localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";

import { predictionTitle } from "./insights-format";

const WIDTH = 960;
const HEIGHT = 136;
const PAD_X = 22;
const AXIS_Y = 68;
const MAX_EVENTS = 10;

const severityClass: Record<string, string> = {
  critical: "text-destructive",
  warning: "text-warning",
  info: "text-primary",
};

/** Piecewise x-scale: [0..1d | 1..7d | 7..30d] each takes a third of the axis. */
function etaToX(etaDays: number): number {
  const zone = (WIDTH - PAD_X * 2) / 3;
  const clamped = Math.max(0, Math.min(30, etaDays));
  if (clamped <= 1) return PAD_X + clamped * zone;
  if (clamped <= 7) return PAD_X + zone + ((clamped - 1) / 6) * zone;
  return PAD_X + zone * 2 + ((clamped - 7) / 23) * zone;
}

interface TimelineEvent {
  x: number;
  above: boolean;
  prediction: InsightPrediction;
  label: string;
  sub: string;
}

export function ForecastTimeline({ predictions, className }: { predictions: InsightPrediction[]; className?: string }) {
  const { lang } = useI18n();

  const { events, hidden } = useMemo(() => {
    const upcoming = predictions
      .filter((item) => item.eta_days !== null && item.eta_days <= 30)
      .sort((a, b) => (a.eta_days ?? 0) - (b.eta_days ?? 0));
    const visible = upcoming.slice(0, MAX_EVENTS);
    const rows: TimelineEvent[] = visible.map((prediction, index) => ({
      x: etaToX(prediction.eta_days ?? 0),
      above: index % 2 === 0,
      prediction,
      label: (prediction.server_name ?? "").slice(0, 18),
      sub: predictionTitle(lang, prediction).slice(0, 32),
    }));
    return { events: rows, hidden: upcoming.length - visible.length };
  }, [predictions, lang]);

  const zone = (WIDTH - PAD_X * 2) / 3;
  const zoneLabels = [
    { x: PAD_X, text: localize(lang, "сейчас", "now") },
    { x: PAD_X + zone, text: localize(lang, "24 часа", "24 hours") },
    { x: PAD_X + zone * 2, text: localize(lang, "неделя", "week") },
    { x: WIDTH - PAD_X, text: localize(lang, "месяц", "month") },
  ];

  return (
    <section className={cn("shrink-0 overflow-hidden rounded-sm border border-border bg-card shadow-elev-1", className)}>
      <div className="flex items-center justify-between gap-3 border-b border-border bg-surface-2/40 px-4 py-2">
        <div className="flex items-center gap-2">
          <CalendarClock className="h-3.5 w-3.5 text-primary" aria-hidden />
          <h2 className="text-xs font-semibold uppercase tracking-[0.14em] text-foreground">
            {localize(lang, "Лента будущего", "What breaks next")}
          </h2>
        </div>
        <span className="hidden truncate text-2xs text-muted-foreground sm:block">
          {hidden > 0
            ? localize(lang, `+${hidden} событий в прогнозах`, `+${hidden} more in forecasts`)
            : localize(lang, "если тренды сохранятся", "if current trends hold")}
        </span>
      </div>

      {events.length === 0 ? (
        <div className="flex items-center justify-center gap-2 px-4 py-7 text-xs text-muted-foreground">
          <span className="relative flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping bg-success opacity-50" />
            <span className="relative inline-flex h-2 w-2 bg-success" />
          </span>
          {localize(
            lang,
            "Горизонт чист — предсказанных инцидентов на 30 дней вперёд нет.",
            "The horizon is clear — no predicted incidents within 30 days.",
          )}
        </div>
      ) : (
        <div className="overflow-x-auto px-1">
          <svg
            viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
            className="w-full min-w-[620px]"
            role="img"
            aria-label={localize(lang, "Хронология предсказанных событий", "Timeline of predicted events")}
          >
            <g className="text-muted-foreground/40">
              {[PAD_X + zone, PAD_X + zone * 2].map((x) => (
                <line key={x} x1={x} y1={14} x2={x} y2={HEIGHT - 24} stroke="currentColor" strokeDasharray="3 5" strokeWidth="1" />
              ))}
            </g>
            <g className="text-muted-foreground">
              {zoneLabels.map((item, index) => (
                <text
                  key={item.text}
                  x={item.x}
                  y={HEIGHT - 8}
                  fill="currentColor"
                  fontSize="10.5"
                  fontFamily="var(--font-mono, monospace)"
                  textAnchor={index === 0 ? "start" : index === zoneLabels.length - 1 ? "end" : "middle"}
                >
                  {item.text}
                </text>
              ))}
            </g>

            <line x1={PAD_X} y1={AXIS_Y} x2={WIDTH - PAD_X} y2={AXIS_Y} stroke="currentColor" strokeWidth="1.5" className="text-border" />
            <g className="text-primary">
              <circle cx={PAD_X} cy={AXIS_Y} r="4.5" fill="currentColor" />
              <circle cx={PAD_X} cy={AXIS_Y} r="4.5" fill="none" stroke="currentColor" opacity="0.5">
                <animate attributeName="r" values="4.5;11" dur="2s" repeatCount="indefinite" />
                <animate attributeName="opacity" values="0.5;0" dur="2s" repeatCount="indefinite" />
              </circle>
            </g>

            {events.map((event) => {
              const labelY = event.above ? AXIS_Y - 36 : AXIS_Y + 26;
              const stemY = event.above ? labelY + 14 : labelY - 10;
              const cls = severityClass[event.prediction.severity] ?? "text-primary";
              return (
                <g key={`${event.prediction.server_id}-${event.prediction.kind}-${event.prediction.target}`} className={cls}>
                  <title>
                    {`${event.prediction.server_name}: ${predictionTitle(lang, event.prediction)} · ~${event.prediction.eta_days} ${localize(lang, "дн", "d")}`}
                  </title>
                  <line x1={event.x} y1={AXIS_Y} x2={event.x} y2={stemY} stroke="currentColor" strokeWidth="1" opacity="0.55" />
                  <circle cx={event.x} cy={AXIS_Y} r="5" fill="currentColor" />
                  <circle cx={event.x} cy={AXIS_Y} r="5" fill="none" stroke="hsl(var(--card))" strokeWidth="2" />
                  <text
                    x={event.x}
                    y={labelY}
                    fill="currentColor"
                    fontSize="11"
                    fontWeight="600"
                    textAnchor="middle"
                    fontFamily="var(--font-sans, sans-serif)"
                  >
                    {event.label}
                  </text>
                  <text
                    x={event.x}
                    y={labelY + 12}
                    fontSize="10"
                    textAnchor="middle"
                    fontFamily="var(--font-sans, sans-serif)"
                    fill="currentColor"
                    opacity="0.7"
                  >
                    {event.sub}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
      )}
    </section>
  );
}
