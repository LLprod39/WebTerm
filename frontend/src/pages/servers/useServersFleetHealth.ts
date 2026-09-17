import { useEffect, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchMonitoringStatus,
  refreshMonitoringFleet,
  type FrontendServer,
  type MonitoringStatusItem,
} from "@/lib/api";
import type { MainTab } from "./types";
import { isFreshLiveSample, statusFromLiveMetrics, useMonitoringLive } from "./useMonitoringLive";

/**
 * Fleet health for the servers list: monitoring status snapshot + live WS metrics,
 * with a periodic SSH metrics refresh when the list tab is active.
 */
export function useServersFleetHealth(servers: FrontendServer[], mainTab: MainTab) {
  const queryClient = useQueryClient();
  const { data: monitoringStatus } = useQuery({
    queryKey: ["monitoring", "status"],
    queryFn: fetchMonitoringStatus,
    // Cheap DB-only read (no SSH): keep the list fresh while the page is visible.
    staleTime: 25_000,
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
  });

  // Live monitoring is always on for the servers list: backend shares one SSH
  // collector per host:port across all viewers/users.
  const liveServerIds = useMemo(() => servers.map((server) => server.id), [servers]);
  const { metricsByServerId: liveMetrics } = useMonitoringLive(
    liveServerIds,
    mainTab === "servers" && liveServerIds.length > 0,
  );

  // Backup path: when live WS is down, SSH quick metrics refresh so numbers don't
  // stay frozen for hours (lite TCP refresh does NOT update CPU/RAM/disk).
  useEffect(() => {
    if (mainTab !== "servers" || liveServerIds.length === 0) return;
    let cancelled = false;
    const pullMetrics = () => {
      void refreshMonitoringFleet({ metrics: true }).then(() => {
        if (!cancelled) {
          void queryClient.invalidateQueries({ queryKey: ["monitoring", "status"] });
          void queryClient.invalidateQueries({ queryKey: ["monitoring-dashboard"] });
        }
      });
    };
    pullMetrics();
    const timer = window.setInterval(pullMetrics, 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [mainTab, liveServerIds.length, queryClient]);

  const fleetHealthByServerId = useMemo(() => {
    const map = new Map<number, MonitoringStatusItem>();
    for (const item of monitoringStatus?.servers ?? []) {
      map.set(item.server_id, item);
    }
    // Live WebSocket samples override the snapshot when fresh.
    // Partial ticks (first sample often has cpu=null until two /proc reads) must NOT
    // blank RAM/disk/CPU that we already have from a recent DB snapshot — that caused
    // chips to pop in one-by-one ~1s after open.
    const nowMs = Date.now();
    for (const [serverId, live] of liveMetrics) {
      if (!isFreshLiveSample(live, nowMs)) continue;
      const base = map.get(serverId);
      const liveStatus = statusFromLiveMetrics(live);
      const serverMeta = servers.find((s) => s.id === serverId);
      // Only fill null live fields from a non-stale DB snapshot (avoid days-old 100% CPU).
      const baseMetricsFresh =
        Boolean(base) &&
        !base!.is_stale &&
        (base!.metrics_age_seconds == null || base!.metrics_age_seconds <= 300);
      const pickMetric = (liveVal: number | null | undefined, baseVal: number | null | undefined) =>
        liveVal ?? (baseMetricsFresh ? (baseVal ?? null) : null);
      map.set(serverId, {
        server_id: serverId,
        server_name: base?.server_name || serverMeta?.name || "",
        host: base?.host || serverMeta?.host || "",
        server_type: base?.server_type || serverMeta?.server_type || "",
        status: liveStatus,
        checked_at: base?.checked_at ?? null,
        age_seconds: 0,
        is_stale: false,
        response_time_ms: base?.response_time_ms ?? null,
        cpu_percent: pickMetric(live.cpu_percent, base?.cpu_percent),
        memory_percent: pickMetric(live.memory_percent, base?.memory_percent),
        disk_percent: pickMetric(live.disk_percent, base?.disk_percent),
        load_1m: pickMetric(live.load_1m, base?.load_1m),
        metrics_checked_at: new Date(nowMs).toISOString(),
        metrics_age_seconds: 0,
        is_lite: false,
      });
    }
    return map;
  }, [monitoringStatus, liveMetrics, servers]);

  return { fleetHealthByServerId };
}
