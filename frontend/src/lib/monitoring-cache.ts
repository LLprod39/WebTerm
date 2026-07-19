/**
 * Session-scoped last-known monitoring dashboard snapshot.
 * Makes dashboard first paint show real numbers instead of "нет связи"
 * while the network request and live WS reconnect.
 */

import type { MonitoringDashboard } from "@/api/monitoring";

const KEY = "webterm.monitoring.dashboard.v1";
const MAX_AGE_MS = 15 * 60 * 1000; // 15 minutes

type Cached = {
  savedAt: number;
  data: MonitoringDashboard;
};

export function readMonitoringDashboardCache(): MonitoringDashboard | undefined {
  try {
    const raw = sessionStorage.getItem(KEY);
    if (!raw) return undefined;
    const parsed = JSON.parse(raw) as Cached;
    if (!parsed?.data || typeof parsed.savedAt !== "number") return undefined;
    if (Date.now() - parsed.savedAt > MAX_AGE_MS) return undefined;
    return parsed.data;
  } catch {
    return undefined;
  }
}

export function writeMonitoringDashboardCache(data: MonitoringDashboard | undefined | null) {
  if (!data?.success) return;
  try {
    const payload: Cached = { savedAt: Date.now(), data };
    sessionStorage.setItem(KEY, JSON.stringify(payload));
  } catch {
    // ignore quota / private mode
  }
}
