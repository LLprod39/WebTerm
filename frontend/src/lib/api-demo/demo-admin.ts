/** Admin dashboard demo fallbacks. */
export function demoAdminFallback<T>(path: string, _options: RequestInit = {}): T | undefined {
  // Admin dashboard — must match AdminDashboardData shape
  if (path.includes("/api/admin/dashboard")) {
    const now = Date.now();
    const minutesAgo = (m: number) => new Date(now - m * 60_000).toISOString();
    const dayIso = (offset: number) => new Date(now - offset * 86_400_000).toISOString().slice(0, 10);
    const hourlyPattern = [4, 3, 2, 2, 3, 5, 9, 14, 18, 22, 26, 24, 21, 25, 28, 31, 27, 22, 17, 14, 12, 9, 7, 5];
    return {
      success: true,
      data: {
        online_users: {
          count: 3,
          total_registered: 12,
          users: [
            { username: "demo", action: "terminal_command", time: minutesAgo(1) },
            { username: "a.petrov", action: "chat_request", time: minutesAgo(2) },
            { username: "i.sidorova", action: "http_request", time: minutesAgo(4) },
          ],
        },
        ai: { requests_today: 128 },
        terminals: {
          active: 2,
          connections: [
            { server: "web-prod-01", user: "demo", connected_at: minutesAgo(25) },
            { server: "db-prod-01", user: "a.petrov", connected_at: minutesAgo(6) },
          ],
        },
        agents: {
          running: 1,
          today: 14,
          succeeded_24h: 18,
          failed_24h: 2,
          success_rate: 90,
          daily: [
            { date: dayIso(6), succeeded: 9, failed: 1 },
            { date: dayIso(5), succeeded: 12, failed: 0 },
            { date: dayIso(4), succeeded: 8, failed: 2 },
            { date: dayIso(3), succeeded: 15, failed: 1 },
            { date: dayIso(2), succeeded: 11, failed: 0 },
            { date: dayIso(1), succeeded: 17, failed: 2 },
            { date: dayIso(0), succeeded: 12, failed: 1 },
          ],
        },
        api_usage: {
          gemini: { calls: 64, input_tokens: 182_400, output_tokens: 45_100, errors: 0, cost_usd: 0.1138 },
          claude: { calls: 38, input_tokens: 240_800, output_tokens: 88_400, errors: 1, cost_usd: 0.9876 },
          openai: { calls: 26, input_tokens: 96_300, output_tokens: 31_200, errors: 0, cost_usd: 0.255 },
        },
        api_calls_today: 128,
        providers: {
          gemini: { enabled: true, model: "gemini-2.0-flash" },
          claude: { enabled: true, model: "claude-sonnet-4-6" },
          openai: { enabled: true, model: "gpt-5-mini" },
          ollama: { enabled: false, model: "" },
        },
        servers: { total: 3, active: 2 },
        tasks: { total: 6, in_progress: 2 },
        hourly_activity: hourlyPattern.map((count, index) => ({
          hour: new Date(now - (23 - index) * 3_600_000).toISOString(),
          count,
        })),
        top_users: [
          { username: "demo", total: 214, ai_requests: 64, terminal_sessions: 38 },
          { username: "a.petrov", total: 122, ai_requests: 31, terminal_sessions: 27 },
          { username: "i.sidorova", total: 78, ai_requests: 12, terminal_sessions: 19 },
        ],
        recent_activity: [
          { user: "demo", category: "terminal", action: "terminal_command", time: minutesAgo(1) },
          { user: "a.petrov", category: "agent", action: "agent_run", time: minutesAgo(3) },
          { user: "i.sidorova", category: "auth", action: "login", time: minutesAgo(9) },
          { user: "demo", category: "server", action: "http_request", time: minutesAgo(14) },
          { user: "a.petrov", category: "agent", action: "agent_run", time: minutesAgo(21) },
        ],
        fleet_health: { avg_cpu: 38, avg_memory: 65, avg_disk: 60, healthy: 1, warning: 1, critical: 0, unreachable: 1 },
        active_alerts_count: 2,
        alerts: [
          { server: "staging-01", type: "unreachable", severity: "critical", title: "Server unreachable", time: minutesAgo(31) },
          { server: "db-prod-01", type: "resource", severity: "warning", title: "resource", time: minutesAgo(22) },
        ],
        app_version: "demo",
      },
    } as T;
  }
  if (path.includes("/api/admin/users/sessions")) return { success: true, online_count: 1, total_registered: 1, active_today: 1, sessions: [] } as T;
  if (path.includes("/api/admin/users/activity")) return { success: true, total: 0, events: [] } as T;
  return undefined;
}
