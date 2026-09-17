import { useEffect, useRef, useState } from "react";
import { getMonitoringLiveWsUrl } from "@/lib/api";
import type { FleetHealthStatus, MonitoringDashboard, ServerHealth } from "@/lib/api";

export interface LiveServerMetrics {
  server_id: number;
  cpu_percent: number | null;
  memory_percent: number | null;
  disk_percent: number | null;
  load_1m: number | null;
  ts: number;
}

/** Keep in sync with servers.monitor CPU/MEM/DISK thresholds. */
const CPU_WARN = 80;
const CPU_CRIT = 95;
const MEM_WARN = 85;
const MEM_CRIT = 95;
const DISK_WARN = 80;
const DISK_CRIT = 90;

const RECONNECT_DELAY_MS = 3_000;
const PING_INTERVAL_MS = 20_000;
/** Drop live samples that stopped updating (stream died without clean close). */
const LIVE_SAMPLE_MAX_AGE_MS = 20_000;

/**
 * Derive fleet status from a live /proc sample. Any successful live sample means
 * the host is reachable — never show "unreachable" while metrics are streaming.
 */
export function statusFromLiveMetrics(live: LiveServerMetrics): FleetHealthStatus {
  const cpu = live.cpu_percent;
  const mem = live.memory_percent;
  const disk = live.disk_percent;

  if (
    (cpu != null && cpu >= CPU_CRIT) ||
    (mem != null && mem >= MEM_CRIT) ||
    (disk != null && disk >= DISK_CRIT)
  ) {
    return "critical";
  }
  if (
    (cpu != null && cpu >= CPU_WARN) ||
    (mem != null && mem >= MEM_WARN) ||
    (disk != null && disk >= DISK_WARN)
  ) {
    return "warning";
  }
  // Live frames may still lack a field mid-stream; host is online while streaming.
  return "healthy";
}

export function isFreshLiveSample(live: LiveServerMetrics, nowMs = Date.now()): boolean {
  if (!live.ts) return false;
  const tsMs = live.ts < 1e12 ? live.ts * 1000 : live.ts;
  return nowMs - tsMs <= LIVE_SAMPLE_MAX_AGE_MS;
}

function isLiveMetricsFrame(data: { type?: string }): boolean {
  return data?.type === "live.metrics" || data?.type === "live_metrics";
}

/**
 * Subscribes to the live fleet metrics WebSocket while `enabled` is true.
 * The backend keeps a single shared SSH session per host:port (across users
 * and inventory rows) and streams /proc samples every ~2s; nothing is persisted.
 */
export function useMonitoringLive(serverIds: number[], enabled: boolean) {
  const [metricsByServerId, setMetricsByServerId] = useState<Map<number, LiveServerMetrics>>(new Map());
  const [connected, setConnected] = useState(false);
  const idsKey = [...serverIds].sort((a, b) => a - b).join(",");
  const idsRef = useRef(idsKey);
  idsRef.current = idsKey;

  useEffect(() => {
    if (!enabled || !idsKey) {
      setMetricsByServerId(new Map());
      setConnected(false);
      return;
    }

    let disposed = false;
    let ws: WebSocket | null = null;
    let retryTimer: number | undefined;
    let pingTimer: number | undefined;
    let attempt = 0;

    const clearTimers = () => {
      if (retryTimer) window.clearTimeout(retryTimer);
      if (pingTimer) window.clearInterval(pingTimer);
      retryTimer = undefined;
      pingTimer = undefined;
    };

    const applySample = (data: LiveServerMetrics & { type?: string }) => {
      if (typeof data.server_id !== "number") return;
      setMetricsByServerId((prev) => {
        const next = new Map(prev);
        const prevSample = prev.get(data.server_id);
        // Never blank a metric that already streamed this session (partial frames).
        next.set(data.server_id, {
          server_id: data.server_id,
          cpu_percent: data.cpu_percent ?? prevSample?.cpu_percent ?? null,
          memory_percent: data.memory_percent ?? prevSample?.memory_percent ?? null,
          disk_percent: data.disk_percent ?? prevSample?.disk_percent ?? null,
          load_1m: data.load_1m ?? prevSample?.load_1m ?? null,
          ts: typeof data.ts === "number" ? data.ts : Date.now() / 1000,
        });
        return next;
      });
    };

    const open = () => {
      if (disposed) return;
      clearTimers();
      try {
        ws = new WebSocket(getMonitoringLiveWsUrl());
      } catch {
        retryTimer = window.setTimeout(open, RECONNECT_DELAY_MS);
        return;
      }

      ws.onopen = () => {
        if (disposed) return;
        attempt = 0;
        setConnected(true);
        const ids = idsRef.current.split(",").map(Number).filter((n) => Number.isFinite(n) && n > 0);
        ws?.send(JSON.stringify({ type: "subscribe", server_ids: ids }));
        pingTimer = window.setInterval(() => {
          if (ws?.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "ping" }));
          }
        }, PING_INTERVAL_MS);
      };

      ws.onmessage = (event) => {
        if (disposed) return;
        try {
          const data = JSON.parse(String(event.data)) as LiveServerMetrics & {
            type?: string;
            state?: string;
          };
          if (isLiveMetricsFrame(data)) {
            applySample(data);
          }
        } catch {
          // ignore malformed frames
        }
      };

      ws.onerror = () => {
        // onclose will schedule reconnect
      };

      ws.onclose = () => {
        setConnected(false);
        if (pingTimer) window.clearInterval(pingTimer);
        pingTimer = undefined;
        if (!disposed) {
          attempt += 1;
          const delay = Math.min(RECONNECT_DELAY_MS * Math.min(attempt, 5), 15_000);
          retryTimer = window.setTimeout(open, delay);
        }
      };
    };

    open();

    return () => {
      disposed = true;
      clearTimers();
      if (ws && ws.readyState !== WebSocket.CLOSED) ws.close();
      setConnected(false);
    };
  }, [enabled, idsKey]);

  return { metricsByServerId, connected };
}

/**
 * Overlay fresh live WS samples onto dashboard ServerHealth rows.
 * Same data path as the Servers list — one stream per host:port on the backend.
 */
export function mergeLiveIntoServerHealth(
  servers: ServerHealth[],
  liveMetrics: Map<number, LiveServerMetrics>,
  nowMs = Date.now(),
): ServerHealth[] {
  if (!servers.length || liveMetrics.size === 0) return servers;

  return servers.map((server) => {
    const live = liveMetrics.get(server.server_id);
    if (!live || !isFreshLiveSample(live, nowMs)) return server;

    const liveStatus = statusFromLiveMetrics(live);
    // Always keep last-known snapshot under partial live frames so the UI
    // never blanks CPU/RAM while the stream warms up or the base row is stale.
    const pick = (liveVal: number | null | undefined, baseVal: number | null | undefined) =>
      liveVal ?? baseVal ?? null;

    return {
      ...server,
      status: liveStatus,
      is_stale: false,
      is_lite: false,
      cpu_percent: pick(live.cpu_percent, server.cpu_percent),
      memory_percent: pick(live.memory_percent, server.memory_percent),
      disk_percent: pick(live.disk_percent, server.disk_percent),
      load_1m: pick(live.load_1m, server.load_1m),
      checked_at: new Date(nowMs).toISOString(),
    };
  });
}

/** Rebuild dashboard summary counters from (possibly live-merged) server rows. */
export function summarizeLiveServerHealth(
  servers: ServerHealth[],
  previous?: MonitoringDashboard["summary"],
): MonitoringDashboard["summary"] {
  const statusCounts: Record<string, number> = {
    healthy: 0,
    warning: 0,
    critical: 0,
    unreachable: 0,
    unknown: 0,
  };
  let cpuSum = 0;
  let memSum = 0;
  let diskSum = 0;
  let cpuN = 0;
  let memN = 0;
  let diskN = 0;

  for (const server of servers) {
    const key = server.status in statusCounts ? server.status : "unknown";
    statusCounts[key] += 1;
    if (typeof server.cpu_percent === "number") {
      cpuSum += server.cpu_percent;
      cpuN += 1;
    }
    if (typeof server.memory_percent === "number") {
      memSum += server.memory_percent;
      memN += 1;
    }
    if (typeof server.disk_percent === "number") {
      diskSum += server.disk_percent;
      diskN += 1;
    }
  }

  return {
    total_servers: servers.length,
    healthy: statusCounts.healthy,
    warning: statusCounts.warning,
    critical: statusCounts.critical,
    unreachable: statusCounts.unreachable,
    unknown: statusCounts.unknown,
    active_alerts: previous?.active_alerts ?? 0,
    avg_cpu: cpuN ? Math.round(cpuSum / cpuN) : previous?.avg_cpu ?? 0,
    avg_memory: memN ? Math.round(memSum / memN) : previous?.avg_memory ?? 0,
    avg_disk: diskN ? Math.round(diskSum / diskN) : previous?.avg_disk ?? 0,
  };
}

/** Apply live overlay to a full MonitoringDashboard payload. */
export function withLiveMonitoringDashboard(
  mon: MonitoringDashboard | undefined,
  liveMetrics: Map<number, LiveServerMetrics>,
): MonitoringDashboard | undefined {
  if (!mon) return mon;
  const servers = mergeLiveIntoServerHealth(mon.servers ?? [], liveMetrics);
  return {
    ...mon,
    servers,
    summary: {
      ...mon.summary,
      ...summarizeLiveServerHealth(servers, mon.summary),
      active_alerts: mon.summary?.active_alerts ?? 0,
    },
  };
}
