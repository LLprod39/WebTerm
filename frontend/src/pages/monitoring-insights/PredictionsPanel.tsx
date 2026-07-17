import { Link } from "react-router-dom";
import { AlertOctagon, AlertTriangle, Info, MessageSquare, TrendingUp } from "lucide-react";

import type { InsightPrediction, PredictionSeverity } from "@/api/monitoring-insights";
import { useI18n, localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";

import { formatEta, predictionDetail, predictionTitle } from "./insights-format";

const severityStyles: Record<
  PredictionSeverity,
  { row: string; icon: string; Icon: typeof AlertTriangle }
> = {
  critical: {
    row: "border-destructive/40 bg-destructive/5",
    icon: "text-destructive",
    Icon: AlertOctagon,
  },
  warning: {
    row: "border-warning/40 bg-warning/5",
    icon: "text-warning",
    Icon: AlertTriangle,
  },
  info: {
    row: "border-border bg-surface-1/60",
    icon: "text-muted-foreground",
    Icon: Info,
  },
};

/** Bare forecast list for the insights rail (scroll lives outside). */
export function PredictionsList({ predictions }: { predictions: InsightPrediction[] }) {
  const { lang } = useI18n();

  if (predictions.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
        <TrendingUp className="h-5 w-5 text-muted-foreground/50" />
        <p className="text-xs text-muted-foreground">
          {localize(
            lang,
            "Пока прогнозов нет — тренды появляются после нескольких часов истории.",
            "No forecasts yet — trends appear after a few hours of history.",
          )}
        </p>
      </div>
    );
  }

  return (
    <ul className="space-y-1.5">
      {predictions.map((prediction) => {
        const styles = severityStyles[prediction.severity] ?? severityStyles.info;
        const eta = formatEta(lang, prediction.eta_days);
        const detail = predictionDetail(lang, prediction);
        return (
          <li
            key={`${prediction.server_id}-${prediction.kind}-${prediction.target}`}
            className={cn("flex items-start gap-2.5 rounded-sm border px-2.5 py-2", styles.row)}
          >
            <styles.Icon className={cn("mt-0.5 h-3.5 w-3.5 shrink-0", styles.icon)} aria-hidden />
            <div className="min-w-0 flex-1">
              <div className="text-xs font-medium leading-snug text-foreground">
                {predictionTitle(lang, prediction)}
              </div>
              <div className="mt-0.5 truncate text-2xs text-muted-foreground">
                <span className="font-mono">{prediction.server_name}</span>
                {detail ? ` · ${detail}` : ""}
                {prediction.confidence < 0.9 && prediction.eta_days !== null
                  ? ` · ${Math.round(prediction.confidence * 100)}%`
                  : ""}
              </div>
            </div>
            <div className="flex shrink-0 flex-col items-end gap-1">
              {eta ? (
                <span className="font-display text-xs font-bold tabular-nums text-foreground">{eta}</span>
              ) : null}
              <Link
                to={`/chat?q=${encodeURIComponent(
                  `Разобрать прогноз на ${prediction.server_name}: ${prediction.kind} ${prediction.target || ""} ETA ${prediction.eta_days ?? "?"}д. Severity ${prediction.severity}.`,
                )}`}
                className="inline-flex items-center gap-1 rounded-md border border-border/60 bg-background/50 px-1.5 py-0.5 text-2xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
                title={localize(lang, "Разобрать в чате", "Open in chat")}
              >
                <MessageSquare className="h-3 w-3" />
                {localize(lang, "Чат", "Chat")}
              </Link>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
