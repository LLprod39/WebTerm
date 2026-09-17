import { useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, MessageSquare } from "lucide-react";

import type { AdminInsightsResponse } from "@/api/monitoring-insights";
import { StatusBadge } from "@/components/ui/page-shell";
import { useI18n, localize } from "@/lib/i18n";
import { cn, relativeTime } from "@/lib/utils";

import { AiAnalysisContent } from "./AiInsightsPanel";
import { CertificatesList } from "./CertificatesPanel";
import { PredictionsList } from "./PredictionsPanel";

type RailTab = "forecasts" | "problems" | "certs" | "ai";

function AlertsList({ alerts }: { alerts: AdminInsightsResponse["alerts"] }) {
  const { lang } = useI18n();
  if (alerts.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
        <AlertTriangle className="h-5 w-5 text-muted-foreground/50" />
        <p className="text-xs text-muted-foreground">
          {localize(lang, "Активных предупреждений нет. Серверы в порядке.", "No active alerts. Servers are healthy.")}
        </p>
      </div>
    );
  }
  return (
    <ul className="space-y-1.5">
      {alerts.map((alert) => (
        <li key={alert.id} className="flex items-center gap-2 rounded-sm border border-border bg-surface-1/60 px-2.5 py-2">
          <StatusBadge
            label={alert.severity}
            tone={alert.severity === "critical" ? "danger" : alert.severity === "warning" ? "warning" : "info"}
            dot={false}
          />
          <div className="min-w-0 flex-1">
            <div className="truncate text-xs text-foreground">{alert.title}</div>
            <div className="truncate font-mono text-2xs text-muted-foreground">{alert.server_name}</div>
          </div>
          <div className="flex shrink-0 flex-col items-end gap-1">
            <span className="text-2xs text-muted-foreground/60">{relativeTime(alert.created_at)}</span>
            <Link
              to={`/chat?q=${encodeURIComponent(
                `Разобрать алерт #${alert.id} на ${alert.server_name}: ${alert.title}. Severity ${alert.severity}.`,
              )}`}
              className="inline-flex items-center gap-1 rounded-md border border-border/60 bg-background/50 px-1.5 py-0.5 text-2xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
              title={localize(lang, "Разобрать в чате", "Open in chat")}
            >
              <MessageSquare className="h-3 w-3" />
              {localize(lang, "Чат", "Chat")}
            </Link>
          </div>
        </li>
      ))}
    </ul>
  );
}

function SegmentButton({
  active,
  label,
  count,
  tone,
  onClick,
}: {
  active: boolean;
  label: string;
  count?: number;
  tone?: "danger" | "warning";
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "flex items-center gap-1.5 rounded-sm border px-2.5 py-1.5 text-2xs font-semibold uppercase tracking-[0.1em] transition-colors",
        active
          ? "border-primary bg-primary text-primary-foreground"
          : "border-border bg-surface-1 text-muted-foreground hover:border-border-strong hover:text-foreground",
      )}
    >
      {label}
      {count !== undefined && count > 0 ? (
        <span
          className={cn(
            "rounded-sm px-1 font-mono tabular-nums",
            active
              ? "bg-primary-foreground/20"
              : tone === "danger"
                ? "bg-destructive/15 text-destructive"
                : tone === "warning"
                  ? "bg-warning/15 text-warning"
                  : "bg-surface-2 text-muted-foreground",
          )}
        >
          {count}
        </span>
      ) : null}
    </button>
  );
}

/** Right rail: one panel, four segments, scroll inside. */
export function InsightsRail({
  data,
  aiRunning,
  className,
}: {
  data: AdminInsightsResponse;
  aiRunning: boolean;
  className?: string;
}) {
  const { lang } = useI18n();
  const [tab, setTab] = useState<RailTab>("forecasts");

  const attentionForecasts = data.summary.predictions_critical + data.summary.predictions_warning;

  return (
    <section
      className={cn(
        "flex flex-col overflow-hidden rounded-sm border border-border bg-card shadow-elev-1",
        className,
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5 border-b border-border bg-surface-2/40 px-3 py-2.5">
        <SegmentButton
          active={tab === "forecasts"}
          label={localize(lang, "Прогнозы", "Forecasts")}
          count={attentionForecasts}
          tone={data.summary.predictions_critical > 0 ? "danger" : "warning"}
          onClick={() => setTab("forecasts")}
        />
        <SegmentButton
          active={tab === "problems"}
          label={localize(lang, "Проблемы", "Problems")}
          count={data.summary.active_alerts}
          tone="danger"
          onClick={() => setTab("problems")}
        />
        <SegmentButton
          active={tab === "certs"}
          label={localize(lang, "Сертификаты", "Certificates")}
          count={data.summary.certificates_expiring_30d}
          tone="warning"
          onClick={() => setTab("certs")}
        />
        <SegmentButton active={tab === "ai"} label={localize(lang, "ИИ", "AI")} onClick={() => setTab("ai")} />
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-2.5">
        {tab === "forecasts" ? <PredictionsList predictions={data.predictions} /> : null}
        {tab === "problems" ? <AlertsList alerts={data.alerts} /> : null}
        {tab === "certs" ? <CertificatesList certificates={data.certificates} /> : null}
        {tab === "ai" ? <AiAnalysisContent ai={data.ai} servers={data.servers} running={aiRunning} /> : null}
      </div>
    </section>
  );
}
