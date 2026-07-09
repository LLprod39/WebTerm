import { useEffect, useState } from "react";
import { getMonitoringLiveWsUrl } from "@/lib/api";

export interface LiveServerMetrics {
  server_id: number;
  cpu_percent: number | null;
  memory_percent: number | null;
  disk_percent: number | null;
  load_1m: number | null;
  ts: number;
}

const RECONNECT_DELAY_MS = 5_000;

/**
 * Subscribes to the live fleet metrics WebSocket while `enabled` is true.
 * The backend keeps a single shared SSH session per watched server and
 * streams /proc samples every ~2s; nothing is persisted.
 */
export function useMonitoringLive(serverIds: number[], enabled: boolean) {
  const [metricsByServerId, setMetricsByServerId] = useState<Map<number, LiveServerMetrics>>(new Map());
  const [connected, setConnected] = useState(false);
  const idsKey = [...serverIds].sort((a, b) => a - b).join(",");

  useEffect(() => {
    if (!enabled || !idsKey) {
      setMetricsByServerId(new Map());
      setConnected(false);
      return;
    }

    let disposed = false;
    let ws: WebSocket | null = null;
    let retryTimer: number | undefined;

    const open = () => {
      ws = new WebSocket(getMonitoringLiveWsUrl());
      ws.onopen = () => {
        if (disposed) return;
        setConnected(true);
        ws?.send(JSON.stringify({ type: "subscribe", server_ids: idsKey.split(",").map(Number) }));
      };
      ws.onmessage = (event) => {
        if (disposed) return;
        try {
          const data = JSON.parse(String(event.data)) as LiveServerMetrics & { type?: string };
          if (data?.type === "live.metrics" && typeof data.server_id === "number") {
            setMetricsByServerId((prev) => {
              const next = new Map(prev);
              next.set(data.server_id, data);
              return next;
            });
          }
        } catch {
          // ignore malformed frames
        }
      };
      ws.onclose = () => {
        setConnected(false);
        if (!disposed) {
          retryTimer = window.setTimeout(open, RECONNECT_DELAY_MS);
        }
      };
    };

    open();

    return () => {
      disposed = true;
      if (retryTimer) window.clearTimeout(retryTimer);
      if (ws && ws.readyState !== WebSocket.CLOSED) ws.close();
      setConnected(false);
    };
  }, [enabled, idsKey]);

  return { metricsByServerId, connected };
}
