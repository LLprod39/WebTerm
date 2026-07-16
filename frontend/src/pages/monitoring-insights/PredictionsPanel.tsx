import { AlertOctagon, AlertTriangle, Info, TrendingUp } from "lucide-react";

import type { InsightPrediction, PredictionSeverity } from "@/api/monitoring-insights";
import { EmptyState, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { useI18n, localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";

import { formatEta, predictionDetail, predictionTitle, severityTone } from "./insights-format";

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

const MAX_VISIBLE = 12;

export function PredictionsPanel({ predictions }: { predictions: InsightPrediction[] }) {
  const { lang } = useI18n();
  const visible = predictions.slice(0, MAX_VISIBLE);
  const hidden = predictions.length - visible.length;

  return (
    <SectionCard
      title={localize(lang, "Прогнозы", "Forecasts")}
      description={localize(
        lang,
        "Детерминированные тренды: диск, память, сертификаты, логи",
        "Deterministic trends: disk, memory, certificates, logs",
      )}
      icon={<TrendingUp className="h-4 w-4" />}
      bodyClassName="px-4 py-4"
    >
      {visible.length === 0 ? (
        <EmptyState
          icon={<TrendingUp className="h-5 w-5" />}
          title={localize(lang, "Пока прогнозов нет", "No forecasts yet")}
          description={localize(
            lang,
            "Копим историю метрик: первые тренды появляются после нескольких часов мониторинга.",
            "Metric history is accumulating: first trends appear after a few hours of monitoring.",
          )}
        />
      ) : (
        <ul className="space-y-2">
          {visible.map((prediction) => {
            const styles = severityStyles[prediction.severity] ?? severityStyles.info;
            const eta = formatEta(lang, prediction.eta_days);
            const detail = predictionDetail(lang, prediction);
            return (
              <li
                key={`${prediction.server_id}-${prediction.kind}-${prediction.target}`}
                className={cn("flex items-start gap-3 rounded-sm border px-3 py-2.5", styles.row)}
              >
                <styles.Icon className={cn("mt-0.5 h-4 w-4 shrink-0", styles.icon)} aria-hidden />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="text-sm font-medium text-foreground">
                      {predictionTitle(lang, prediction)}
                    </span>
                    <span className="rounded-sm border border-border bg-surface-2 px-1.5 py-0.5 font-mono text-2xs text-muted-foreground">
                      {prediction.server_name}
                    </span>
                  </div>
                  {detail ? (
                    <div className="mt-0.5 text-xs text-muted-foreground">{detail}</div>
                  ) : null}
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1">
                  {eta ? (
                    <span className="font-display text-sm font-bold tabular-nums text-foreground">{eta}</span>
                  ) : (
                    <StatusBadge
                      label={
                        prediction.severity === "info"
                          ? localize(lang, "инфо", "info")
                          : localize(lang, "внимание", "attention")
                      }
                      tone={severityTone(prediction.severity)}
                      dot={false}
                    />
                  )}
                  {prediction.confidence < 0.9 && prediction.eta_days !== null ? (
                    <span className="text-2xs text-muted-foreground/70">
                      {localize(lang, "уверенность", "confidence")} {Math.round(prediction.confidence * 100)}%
                    </span>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {hidden > 0 ? (
        <div className="mt-3 text-center text-xs text-muted-foreground">
          {localize(lang, `и ещё ${hidden} прогнозов в таблице флота`, `and ${hidden} more in the fleet table`)}
        </div>
      ) : null}
    </SectionCard>
  );
}
