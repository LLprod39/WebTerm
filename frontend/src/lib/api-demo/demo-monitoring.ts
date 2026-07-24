/** Monitoring dashboard/status/config/refresh demo fallbacks. */
export function demoMonitoringFallback<T>(path: string, _options: RequestInit = {}): T | undefined {
  // Monitoring dashboard — must match MonitoringDashboard shape
  if (path.includes("/servers/api/monitoring/config")) return {
    success: true,
    thresholds: { cpu_warn: 80, cpu_crit: 95, mem_warn: 85, mem_crit: 95, disk_warn: 80, disk_crit: 90 },
    stats: { total_checks: 0, active_alerts: 0, last_check_at: null, monitored_servers: 0 },
  } as T;
  if (path.includes("/servers/api/monitoring/dashboard")) {
    const now = Date.now();
    const minutesAgo = (m: number) => new Date(now - m * 60_000).toISOString();
    return {
      success: true,
      servers: [
        {
          server_id: 1, server_name: "web-prod-01", host: "192.168.1.10", status: "healthy",
          cpu_percent: 34, memory_percent: 52, disk_percent: 61, load_1m: 0.8,
          uptime_seconds: 3_456_000, response_time_ms: 42, checked_at: minutesAgo(2),
        },
        {
          server_id: 2, server_name: "db-prod-01", host: "192.168.1.11", status: "warning",
          cpu_percent: 41, memory_percent: 78, disk_percent: 72, load_1m: 1.9,
          uptime_seconds: 8_640_000, response_time_ms: 55, checked_at: minutesAgo(2),
        },
        {
          server_id: 3, server_name: "staging-01", host: "192.168.1.20", status: "unreachable",
          cpu_percent: null, memory_percent: null, disk_percent: null, load_1m: null,
          uptime_seconds: null, response_time_ms: null, checked_at: minutesAgo(31),
        },
      ],
      alerts: [
        {
          id: 1, server_id: 3, server_name: "staging-01", alert_type: "unreachable", severity: "critical",
          title: "Сервер недоступен", message: "TCP-проба не отвечает более 30 минут",
          is_resolved: false, created_at: minutesAgo(31),
        },
        {
          id: 2, server_id: 2, server_name: "db-prod-01", alert_type: "resource", severity: "warning",
          title: "Высокая загрузка памяти", message: "RAM 78% превышает порог 75%",
          is_resolved: false, created_at: minutesAgo(22),
        },
      ],
      summary: { total_servers: 3, healthy: 1, warning: 1, critical: 0, unreachable: 1, unknown: 0, active_alerts: 2, avg_cpu: 38, avg_memory: 65, avg_disk: 66 },
      recent_activity: [],
    } as T;
  }
  if (path.includes("/servers/api/monitoring/status")) return {
    success: true,
    servers: [],
    summary: { total_servers: 0, healthy: 0, warning: 0, critical: 0, unreachable: 0, unknown: 0, stale: 0 },
    meta: { stale_after_seconds: 300, latest_checked_at: null, has_stale: false },
  } as T;
  if (path.includes("/servers/api/monitoring/refresh")) return {
    success: true,
    servers: [],
    summary: { total_servers: 0, healthy: 0, warning: 0, critical: 0, unreachable: 0, unknown: 0, stale: 0 },
    meta: { stale_after_seconds: 300, latest_checked_at: null, has_stale: false },
    refreshed: true,
  } as T;
  return undefined;
}
