import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";

import { fetchAdminDashboard, fetchAuthSession, fetchMonitoringDashboard } from "@/api";
import { fetchPluginSurfaces } from "@/api";
import { CustomizableDashboard } from "@/components/dashboard/CustomizableDashboard";
import { PageHero, PageShell, QueryStateBlock } from "@/components/ui/page-shell";
import { localize, useI18n } from "@/lib/i18n";
import { buildAdminDashboardWidgets } from "./admin-dashboard/adminDashboardWidgets";
import { buildPluginDashboardWidgets } from "@/plugins/dashboardWidgets";
import {
  useMonitoringLive,
  withLiveMonitoringDashboard,
} from "@/pages/servers/useMonitoringLive";

export default function AdminDashboard() {
  const { lang } = useI18n();

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
  const { metricsByServerId: liveMetrics } = useMonitoringLive(
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

  return (
    <PageShell width="7xl">
      <PageHero
        kicker={localize(lang, "Администрирование", "Administration")}
        title={localize(lang, "Состояние системы", "System status")}
        description={localize(
          lang,
          "Инфраструктура, активность пользователей и запуски агентов.",
          "Infrastructure, user activity, and agent runs.",
        )}
      />

      <QueryStateBlock loading={isLoading} error={error} onRetry={() => refetch()}>
        <CustomizableDashboard type="admin" availableWidgets={availableWidgets} />
      </QueryStateBlock>
    </PageShell>
  );
}
