import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  fetchAgentDashboardRuns,
  fetchAuthSession,
  fetchFrontendBootstrap,
  fetchMonitoringDashboard,
  fetchPluginSurfaces,
  refreshMonitoringFleet,
} from "@/lib/api";
import {
  readMonitoringDashboardCache,
  writeMonitoringDashboardCache,
} from "@/lib/monitoring-cache";
import { useI18n } from "@/lib/i18n";
import {
  useMonitoringLive,
  withLiveMonitoringDashboard,
} from "@/pages/servers/useMonitoringLive";

/** Data controller for the user workspace dashboard (queries, live metrics, width toggle). */
export function useUserDashboardData() {
  const { lang } = useI18n();
  const queryClient = useQueryClient();
  const [isFullWidth, setIsFullWidth] = useState(() => {
    return localStorage.getItem("user_dashboard_full_width") === "true";
  });
  const [cachedMonitoring] = useState(() => readMonitoringDashboardCache());

  const toggleWidth = () => {
    setIsFullWidth((prev) => {
      const next = !prev;
      localStorage.setItem("user_dashboard_full_width", String(next));
      return next;
    });
  };

  const { data: bootstrapResponse, isLoading: bootLoading } = useQuery({
    queryKey: ["bootstrap"],
    queryFn: fetchFrontendBootstrap,
    staleTime: 30_000,
  });
  const { data: authData } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });

  const { data: runsResponse, isLoading: runsLoading } = useQuery({
    queryKey: ["agent-dashboard-runs"],
    queryFn: fetchAgentDashboardRuns,
    refetchInterval: 10000,
    staleTime: 10_000,
  });

  const { data: monitoringResponse, isLoading: monLoading, isFetching: monFetching } = useQuery({
    queryKey: ["monitoring-dashboard"],
    queryFn: fetchMonitoringDashboard,
    // Keep fleet health fresh; backend also overlays live SSH samples now.
    staleTime: 30_000,
    gcTime: 15 * 60_000,
    refetchInterval: 30_000,
    refetchIntervalInBackground: true,
    placeholderData: (previous) => previous ?? cachedMonitoring,
    initialData: cachedMonitoring,
    initialDataUpdatedAt: cachedMonitoring ? Date.now() - 60_000 : undefined,
  });
  const { data: pluginSurfaces } = useQuery({
    queryKey: ["plugins", "surfaces", "dashboard", "user"],
    queryFn: fetchPluginSurfaces,
    enabled: Boolean(authData?.user?.features.plugins),
  });

  // Persist last good snapshot so the next visit paints immediately.
  useEffect(() => {
    if (monitoringResponse?.success) {
      writeMonitoringDashboardCache(monitoringResponse);
    }
  }, [monitoringResponse]);

  // Background SSH metrics refresh (debounced server-side) so numbers stay warm
  // even when live WS is still connecting or the monitor worker is slow.
  useEffect(() => {
    let cancelled = false;
    const pull = () => {
      void refreshMonitoringFleet({ metrics: true }).then(() => {
        if (!cancelled) {
          void queryClient.invalidateQueries({ queryKey: ["monitoring-dashboard"] });
          void queryClient.invalidateQueries({ queryKey: ["monitoring", "status"] });
        }
      });
    };
    pull();
    const timer = window.setInterval(pull, 90_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [queryClient]);

  const boot = bootstrapResponse;
  const runs = runsResponse;

  // Same live WS as Servers page — CPU/RAM/HDD stream while dashboard is open.
  const liveServerIds = useMemo(() => {
    const fromMon = (monitoringResponse?.servers ?? []).map((s) => s.server_id);
    if (fromMon.length) return fromMon;
    return (bootstrapResponse?.servers ?? []).map((s) => s.id);
  }, [monitoringResponse?.servers, bootstrapResponse?.servers]);

  const { metricsByServerId: liveMetrics, connected: liveConnected } = useMonitoringLive(
    liveServerIds,
    liveServerIds.length > 0,
  );

  const mon = useMemo(
    () => withLiveMonitoringDashboard(monitoringResponse, liveMetrics),
    [monitoringResponse, liveMetrics],
  );

  // With session cache / placeholder, don't block the whole page on monLoading.
  const isLoading = (bootLoading && !boot) || (runsLoading && !runs);

  return {
    lang,
    isFullWidth,
    toggleWidth,
    boot,
    runs,
    mon,
    monLoading,
    monFetching,
    liveConnected,
    liveMetrics,
    isLoading,
    pluginSurfaces,
  };
}

export type UserDashboardData = ReturnType<typeof useUserDashboardData>;
