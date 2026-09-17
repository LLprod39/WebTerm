import { describe, expect, it } from "vitest";

import {
  normalizeAdminDashboardResponse,
  type AdminDashboardData,
} from "@/api/monitoring";
import { buildAdminDashboardWidgets } from "./adminDashboardWidgets";

const dashboardData = {
  online_users: { count: 0, total_registered: 0, users: [] },
  ai: { requests_today: 0 },
  terminals: { active: 0, connections: [] },
  agents: { running: 0, today: 0, succeeded_24h: 0, failed_24h: 0, success_rate: 0 },
  execution_queues: {
    observed_at: null,
    depth: 0,
    in_flight: 0,
    lease_expired: 0,
    retrying: 0,
    retried_24h: 0,
    attempts_exhausted_24h: 0,
    stale_workers: 0,
    oldest_queued_seconds: 0,
    queues: [],
  },
  api_usage: {},
  api_calls_today: 0,
  providers: {},
  servers: { total: 0, active: 0 },
  tasks: { total: 0, in_progress: 0 },
  hourly_activity: [],
  top_users: [],
  recent_activity: [],
  fleet_health: { avg_cpu: 0, avg_memory: 0, avg_disk: 0, healthy: 0, warning: 0, critical: 0, unreachable: 0 },
  active_alerts_count: 0,
  alerts: [],
  app_version: "test",
} satisfies AdminDashboardData;

describe("admin dashboard widget data", () => {
  it("normalizes an API envelope and keeps built-in widgets available", () => {
    const normalized = normalizeAdminDashboardResponse({ success: true, data: dashboardData });
    const widgets = buildAdminDashboardWidgets(normalized, "ru");

    expect(normalized).toBe(dashboardData);
    expect(widgets.length).toBeGreaterThan(0);
    expect(widgets.map((widget) => widget.id)).toContain("fleet_metrics");
  });

  it("preserves already-unwrapped dashboard data", () => {
    expect(normalizeAdminDashboardResponse(dashboardData)).toBe(dashboardData);
  });
});
