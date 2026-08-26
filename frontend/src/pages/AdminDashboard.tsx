import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Activity, Maximize2, Minimize2, Radio } from "lucide-react";

import { fetchAdminDashboard, fetchAuthSession, fetchMonitoringDashboard } from "@/api";
import { fetchPluginSurfaces } from "@/api";
import { Button } from "@/components/ui/button";
import { CustomizableDashboard } from "@/components/dashboard/CustomizableDashboard";
import { PageHero, PageShell, QueryStateBlock, StatusBadge } from "@/components/ui/page-shell";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { buildAdminDashboardWidgets } from "./admin-dashboard/adminDashboardWidgets";
import { buildPluginDashboardWidgets } from "@/plugins/dashboardWidgets";
import {
  useMonitoringLive,
  withLiveMonitoringDashboard,
} from "@/pages/servers/useMonitoringLive";

export default function AdminDashboard() {
  const { lang } = useI18n();
  const [isFullWidth, setIsFullWidth] = useState(() => localStorage.getItem("admin_dashboard_full_width") === "true");

  const toggleWidth = () => {
    setIsFullWidth((prev) => {
      const next = !prev;
      localStorage.setItem("admin_dashboard_full_width", String(next));
      return next;
    });
  };

  const { data: dashResponse, isLoading, error, refetch } = useQuery({
    queryKey: ["admin", "dashboard"],
    queryFn: fetchAdminDashboard,
    refetchInterval: 30000,
  });
  const { data: authData } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const { data: monitoringResponse } = useQuery({
    queryKey: ["monitoring-dashboard"],
    queryFn: fetchMonitoringDashboard,
    staleTime: 20_000,
    refetchInterval: 30000,
    refetchIntervalInBackground: false,
    placeholderData: (previous) => previous,
  });
  const { data: pluginSurfaces } = useQuery({
    queryKey: ["plugins", "surfaces", "dashboard", "admin"],
    queryFn: fetchPluginSurfaces,
    enabled: Boolean(authData?.user?.features.plugins),
  });

  const liveServerIds = useMemo(
    () => (monitoringResponse?.servers ?? []).map((s) => s.server_id),
    [monitoringResponse?.servers],
  );
  const { metricsByServerId: liveMetrics, connected: liveConnected } = useMonitoringLive(
    liveServerIds,
    liveServerIds.length > 0,
  );
  const monitoring = useMemo(
    () => withLiveMonitoringDashboard(monitoringResponse, liveMetrics),
    [monitoringResponse, liveMetrics],
  );

  const d = dashResponse;
  const availableWidgets = useMemo(() => {
    const builtins = d ? buildAdminDashboardWidgets(d, lang, monitoring) : [];
    const pluginWidgets = buildPluginDashboardWidgets(pluginSurfaces?.surfaces?.dashboard_widgets ?? []);
    return [...builtins, ...pluginWidgets];
  }, [d, lang, monitoring, pluginSurfaces?.surfaces?.dashboard_widgets]);

  const verdict = useMemo(() => {
    if (!monitoring?.summary) return null;
    const { critical, unreachable, warning, active_alerts } = monitoring.summary;
    const failedAgents = d?.agents?.failed_24h ?? 0;
    const problems = critical + unreachable + active_alerts;
    if (problems > 0) {
      return { tone: "danger" as const, label: localize(lang, `Проблем: ${problems}`, `Problems: ${problems}`) };
    }
    if (warning > 0 || failedAgents > 0) {
      return { tone: "warning" as const, label: localize(lang, "Есть предупреждения", "Warnings present") };
    }
    return { tone: "success" as const, label: localize(lang, "Стабильно", "Stable") };
  }, [monitoring?.summary, d?.agents?.failed_24h, lang]);

  return (
    <PageShell width={isFullWidth ? "full" : "7xl"}>
      <PageHero
        kicker={localize(lang, "Администрирование", "Administration")}
        title={localize(lang, "Состояние системы", "System status")}
        description={localize(
          lang,
          "Инфраструктура, активность пользователей и запуски агентов.",
          "Infrastructure, user activity, and agent runs.",
        )}
        actions={
          <div className="flex items-center gap-2">
            {verdict ? <StatusBadge label={verdict.label} tone={verdict.tone} /> : null}
            <Button
              variant="outline"
              size="sm"
              onClick={toggleWidth}
              className="h-8 gap-1.5 text-xs font-semibold hover:border-primary/50 shadow-sm transition-all"
            >
              {isFullWidth ? (
                <>
                  <Minimize2 className="h-3.5 w-3.5" />
                  <span>{localize(lang, "Сузить", "Narrow")}</span>
                </>
              ) : (
                <>
                  <Maximize2 className="h-3.5 w-3.5" />
                  <span>{localize(lang, "Расширить", "Expand")}</span>
                </>
              )}
            </Button>
            <div className="flex items-center gap-3 px-3 py-1.5 rounded-xl bg-card border border-border/80 shadow-sm h-8 shrink-0">
              <Activity className="h-4 w-4 text-info" />
              <span className="text-xs font-semibold text-foreground/90">{localize(lang, "Версия", "Version")} v{d?.app_version || "2.0.0"}</span>
              <div className="h-3.5 w-px bg-border mx-1" />
              <span
                className={cn(
                  "inline-flex items-center gap-1 text-xs font-medium",
                  liveConnected ? "text-success" : "text-muted-foreground",
                )}
              >
                <Radio className={cn("h-3.5 w-3.5", liveConnected && "animate-pulse")} />
                {liveConnected
                  ? localize(lang, "Метрики онлайн", "Live metrics")
                  : localize(lang, "Подключение…", "Connecting…")}
              </span>
            </div>
          </div>
        }
      />

      <QueryStateBlock loading={isLoading} error={error} onRetry={() => refetch()}>
        <CustomizableDashboard type="admin" availableWidgets={availableWidgets} />
      </QueryStateBlock>
    </PageShell>
  );
}
