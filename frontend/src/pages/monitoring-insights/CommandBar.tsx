import { Loader2, RefreshCw, Sparkles } from "lucide-react";

import type { AdminInsightsResponse, AiInsight, InsightPrediction } from "@/api/monitoring-insights";
import { Button } from "@/components/ui/button";
import { useI18n, localize } from "@/lib/i18n";
import { cn, relativeTime } from "@/lib/utils";

import { formatEta, predictionTitle } from "./insights-format";
import { useCountUp } from "./use-count-up";

function scoreToneClass(score: number): string {
  if (score >= 80) return "text-success";
  if (score >= 60) return "text-warning";
  return "text-destructive";
}

function MiniRing({ score }: { score: number }) {
  const animated = useCountUp(score);
  const radius = 20;
  const circumference = 2 * Math.PI * radius;
  const filled = circumference * (Math.max(0, Math.min(100, animated)) / 100);
  return (
    <div className={cn("relative h-12 w-12 shrink-0", scoreToneClass(score))} role="img" aria-label={`Health ${score}/100`}>
      <svg viewBox="0 0 48 48" className="h-full w-full -rotate-90">
        <circle cx="24" cy="24" r={radius} fill="none" strokeWidth="4.5" className="stroke-border" />
        <circle
          cx="24"
          cy="24"
          r={radius}
          fill="none"
          strokeWidth="4.5"
          stroke="currentColor"
          strokeDasharray={`${filled} ${circumference - filled}`}
          style={{ transition: "stroke-dasharray 0.3s linear" }}
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center font-display text-sm font-bold tabular-nums text-foreground">
        {animated}
      </span>
    </div>
  );
}

function StatChip({ label, value, tone }: { label: string; value: string; tone?: "danger" | "warning" | "success" }) {
  return (
    <div className="flex items-baseline gap-1.5 border-l border-border pl-3 first:border-l-0 first:pl-0">
      <span
        className={cn(
          "font-display text-base font-bold leading-none tabular-nums",
          tone === "danger" ? "text-destructive" : tone === "warning" ? "text-warning" : tone === "success" ? "text-success" : "text-foreground",
        )}
      >
        {value}
      </span>
      <span className="text-2xs uppercase tracking-[0.1em] text-muted-foreground/70">{label}</span>
    </div>
  );
}

export function CommandBar({
  summary,
  predictions,
  aiFleet,
  generatedAt,
  cached,
  onRefresh,
  refreshing,
  onRunAi,
  aiBusy,
  aiEnabled,
}: {
  summary: AdminInsightsResponse["summary"];
  predictions: InsightPrediction[];
  aiFleet: AiInsight | null;
  generatedAt: string;
  cached: boolean;
  onRefresh: () => void;
  refreshing: boolean;
  onRunAi: () => void;
  aiBusy: boolean;
  aiEnabled: boolean;
}) {
  const { lang } = useI18n();
  const attention = summary.warning + summary.critical + summary.unreachable;
  const nextEvent = predictions.find((item) => item.eta_days !== null);

  return (
    <section className="relative shrink-0 overflow-hidden rounded-sm border border-border bg-card px-4 py-3 shadow-elev-1">
      <div className="absolute left-0 top-0 h-full w-1 bg-primary" />
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 pl-1">
        <div className="flex items-center gap-3">
          <MiniRing score={summary.fleet_health_score} />
          <div className="min-w-0">
            <div className="enterprise-kicker">{localize(lang, "Командный центр", "Command center")}</div>
            <h1 className="font-display text-lg font-bold leading-tight text-foreground">
              {localize(lang, "Метрики и прогнозы", "Metrics & Forecasts")}
            </h1>
          </div>
        </div>

        <div className="hidden min-w-0 flex-1 lg:block">
          <p className="truncate text-xs text-muted-foreground">
            {summary.servers_total} {localize(lang, "серверов", "servers")}
            {attention > 0
              ? ` · ${attention} ${localize(lang, "требуют внимания", "need attention")}`
              : ` · ${localize(lang, "все в порядке", "all fine")}`}
            {nextEvent
              ? ` · ${localize(lang, "ближайшее", "next")}: ${predictionTitle(lang, nextEvent)} ${formatEta(lang, nextEvent.eta_days)}`
              : ""}
            {aiFleet
              ? ` · AI: ${aiFleet.verdict === "low" ? localize(lang, "спокойно", "calm") : aiFleet.verdict}`
              : ""}
          </p>
          <p className="mt-0.5 text-2xs text-muted-foreground/50">
            {localize(lang, "Обновлено", "Updated")} {relativeTime(generatedAt)}
            {cached ? localize(lang, " · кэш", " · cached") : ""}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
          <StatChip
            label={localize(lang, "проблем", "problems")}
            value={String(summary.active_alerts)}
            tone={summary.active_alerts > 0 ? "danger" : "success"}
          />
          <StatChip
            label={localize(lang, "прогнозов", "forecasts")}
            value={String(summary.predictions_critical + summary.predictions_warning)}
            tone={summary.predictions_critical > 0 ? "danger" : summary.predictions_warning > 0 ? "warning" : "success"}
          />
          <StatChip
            label={localize(lang, "серт ≤30д", "certs ≤30d")}
            value={String(summary.certificates_expiring_30d)}
            tone={summary.certificates_expiring_30d > 0 ? "warning" : "success"}
          />
          <StatChip
            label={localize(lang, "худший", "worst")}
            value={String(summary.fleet_health_worst)}
            tone={summary.fleet_health_worst < 60 ? "danger" : summary.fleet_health_worst < 80 ? "warning" : "success"}
          />
        </div>

        <div className="ml-auto flex shrink-0 items-center gap-2">
          <Button variant="outline" size="sm" onClick={onRefresh} disabled={refreshing} className="h-8">
            <RefreshCw className={cn("h-3.5 w-3.5", refreshing && "animate-spin")} />
            <span className="ml-1.5 hidden xl:inline">{localize(lang, "Обновить", "Refresh")}</span>
          </Button>
          {aiEnabled ? (
            <Button variant="default" size="sm" onClick={onRunAi} disabled={aiBusy} className="h-8">
              {aiBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
              <span className="ml-1.5 hidden xl:inline">
                {aiBusy ? localize(lang, "Анализ…", "Analyzing…") : localize(lang, "AI-анализ", "AI analysis")}
              </span>
            </Button>
          ) : null}
        </div>
      </div>
    </section>
  );
}
