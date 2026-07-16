import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, RefreshCw, ShieldAlert } from "lucide-react";

import { fetchAdminInsights, type AdminInsightsResponse, type InsightAlert } from "@/api/monitoring-insights";
import { Button } from "@/components/ui/button";
import {
  EmptyState,
  PageHero,
  PageShell,
  QueryStateBlock,
  SectionCard,
  StatStrip,
  StatStripItem,
  StatusBadge,
} from "@/components/ui/page-shell";
import { fetchAuthSession } from "@/lib/api";
import { useI18n, localize } from "@/lib/i18n";
import { relativeTime } from "@/lib/utils";

import { CertificatesPanel } from "./CertificatesPanel";
import { FleetMetricsTable } from "./FleetMetricsTable";
import { PredictionsPanel } from "./PredictionsPanel";

const INSIGHTS_QUERY_KEY = ["admin", "insights"];

function AlertsPanel({ alerts }: { alerts: InsightAlert[] }) {
  const { lang } = useI18n();
  return (
    <SectionCard
      title={localize(lang, "Активные проблемы", "Active problems")}
      description={localize(lang, "Нерешённые алерты мониторинга", "Unresolved monitoring alerts")}
      icon={<AlertTriangle className="h-4 w-4" />}
      bodyClassName="px-4 py-4"
    >
      {alerts.length === 0 ? (
        <EmptyState
          icon={<AlertTriangle className="h-5 w-5" />}
          title={localize(lang, "Проблем нет", "No active problems")}
          description={localize(lang, "Все алерты решены — флот в порядке.", "All alerts resolved — the fleet is fine.")}
        />
      ) : (
        <ul className="space-y-1.5">
          {alerts.slice(0, 10).map((alert) => (
            <li key={alert.id} className="flex items-center gap-2.5 rounded-sm border border-border bg-surface-1/60 px-3 py-2">
              <StatusBadge
                label={alert.severity}
                tone={alert.severity === "critical" ? "danger" : alert.severity === "warning" ? "warning" : "info"}
                dot={false}
              />
              <div className="min-w-0 flex-1">
                <span className="text-sm text-foreground">{alert.title}</span>
                <span className="ml-2 font-mono text-2xs text-muted-foreground">{alert.server_name}</span>
              </div>
              <span className="shrink-0 text-2xs text-muted-foreground/70">{relativeTime(alert.created_at)}</span>
            </li>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}

export default function MonitoringInsightsPage() {
  const { lang } = useI18n();
  const queryClient = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);

  const sessionQuery = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const isStaff = Boolean(sessionQuery.data?.user?.is_staff);

  const insightsQuery = useQuery({
    queryKey: INSIGHTS_QUERY_KEY,
    queryFn: () => fetchAdminInsights(),
    enabled: isStaff,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      const fresh = await fetchAdminInsights(true);
      queryClient.setQueryData<AdminInsightsResponse>(INSIGHTS_QUERY_KEY, fresh);
    } finally {
      setRefreshing(false);
    }
  };

  if (sessionQuery.isSuccess && !isStaff) {
    return (
      <PageShell width="7xl">
        <EmptyState
          icon={<ShieldAlert className="h-5 w-5" />}
          title={localize(lang, "Только для администраторов", "Admins only")}
          description={localize(
            lang,
            "Раздел «Метрики и прогнозы» доступен пользователям со статусом администратора.",
            "The Metrics & Forecasts section is available to admin users only.",
          )}
        />
      </PageShell>
    );
  }

  const data = insightsQuery.data;
  const summary = data?.summary;

  return (
    <PageShell width="7xl">
      <div className="space-y-4">
        <PageHero
          kicker={localize(lang, "Мониторинг", "Monitoring")}
          title={localize(lang, "Метрики и прогнозы", "Metrics & Forecasts")}
          description={localize(
            lang,
            "Расширенная телеметрия флота, детерминированные прогнозы и инвентарь сертификатов.",
            "Extended fleet telemetry, deterministic forecasts, and the certificate inventory.",
          )}
          actions={
            <Button variant="outline" size="sm" onClick={handleRefresh} disabled={refreshing || !isStaff}>
              <RefreshCw className={refreshing ? "mr-1.5 h-3.5 w-3.5 animate-spin" : "mr-1.5 h-3.5 w-3.5"} />
              {localize(lang, "Обновить", "Refresh")}
            </Button>
          }
        />

        <QueryStateBlock
          loading={insightsQuery.isLoading || sessionQuery.isLoading}
          error={insightsQuery.error}
          onRetry={() => insightsQuery.refetch()}
        >
          {data && summary ? (
            <div className="space-y-4">
              <StatStrip>
                <StatStripItem
                  label={localize(lang, "Серверы", "Servers")}
                  value={`${summary.healthy}/${summary.servers_total}`}
                  hint={localize(
                    lang,
                    `${summary.warning} warn · ${summary.critical + summary.unreachable} crit`,
                    `${summary.warning} warn · ${summary.critical + summary.unreachable} crit`,
                  )}
                  tone={summary.critical + summary.unreachable > 0 ? "danger" : summary.warning > 0 ? "warning" : "success"}
                />
                <StatStripItem
                  label={localize(lang, "Проблемы сейчас", "Problems now")}
                  value={summary.active_alerts}
                  hint={localize(lang, "активные алерты", "active alerts")}
                  tone={summary.active_alerts > 0 ? "danger" : "success"}
                />
                <StatStripItem
                  label={localize(lang, "Прогнозы", "Forecasts")}
                  value={summary.predictions_critical + summary.predictions_warning}
                  hint={localize(
                    lang,
                    `${summary.predictions_critical} крит · ${summary.predictions_warning} warn · всего ${summary.predictions_total}`,
                    `${summary.predictions_critical} crit · ${summary.predictions_warning} warn · total ${summary.predictions_total}`,
                  )}
                  tone={summary.predictions_critical > 0 ? "danger" : summary.predictions_warning > 0 ? "warning" : "success"}
                />
                <StatStripItem
                  label={localize(lang, "Сертификаты ≤30д", "Certs ≤30d")}
                  value={summary.certificates_expiring_30d}
                  hint={localize(
                    lang,
                    `всего ${summary.certificates_total} · смен за 7д: ${summary.certificates_changed_7d}`,
                    `total ${summary.certificates_total} · changed 7d: ${summary.certificates_changed_7d}`,
                  )}
                  tone={summary.certificates_expiring_30d > 0 ? "warning" : "success"}
                />
              </StatStrip>

              <div className="grid gap-4 xl:grid-cols-3">
                <div className="space-y-4 xl:col-span-2">
                  <PredictionsPanel predictions={data.predictions} />
                  <AlertsPanel alerts={data.alerts} />
                </div>
                <CertificatesPanel certificates={data.certificates} />
              </div>

              <FleetMetricsTable servers={data.servers} />

              <div className="text-right text-2xs text-muted-foreground/60">
                {localize(lang, "Обновлено", "Updated")}: {relativeTime(data.generated_at)}
                {data.cached ? localize(lang, " · из кэша", " · cached") : ""}
              </div>
            </div>
          ) : (
            <EmptyState
              title={localize(lang, "Нет данных", "No data")}
              description={localize(
                lang,
                "Запустите run_monitor, чтобы начать сбор расширенных метрик.",
                "Start run_monitor to begin collecting extended metrics.",
              )}
            />
          )}
        </QueryStateBlock>
      </div>
    </PageShell>
  );
}
