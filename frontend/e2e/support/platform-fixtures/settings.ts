import { json } from "../apiHarness";
import { FIXED_DATE } from "../platformFixtureTypes";
import type { PlatformFixtureContext } from "../platformFixtureState";

/** Settings, models, and monitoring config fixtures. */
export function handleSettingsFixture(req: any, ctx: PlatformFixtureContext) {
  const { options, settingsConfig, servers } = ctx;
  if (req.path === "/api/settings/readiness/" && req.method === "GET") {
    const status = options.settingsReadiness ?? "ready";
    const severity = status;
    return json({
      success: true,
      status,
      summary: {
        ready: status === "ready" ? 1 : 0,
        warning: status === "warning" ? 1 : 0,
        error: status === "error" ? 1 : 0,
        total: 1,
      },
      checks: [
        {
          key: "fixture_readiness",
          title: "Fixture readiness",
          status,
          severity,
          message: status === "ready" ? "Ready" : "Configuration requires attention",
          action_path: "/settings/ai",
          action_label: "Configure",
        },
      ],
    });
  }

      if (req.path === "/api/settings/" && req.method === "GET") {
        return json({ success: true, config: settingsConfig });
      }

      if (req.path === "/api/settings/" && req.method === "POST") {
        Object.assign(settingsConfig, req.body || {});
        return json({ success: true, message: "saved" });
      }

      if (req.path === "/api/settings/activity/" && req.method === "GET") {
        return json({
          success: true,
          events: [],
          summary: { total_events: 0, total_users: 0 },
        });
      }

      if (req.path === "/api/models/" && req.method === "GET") {
        return json({
          gemini: ["gemini-2.5-pro"],
          grok: ["grok-3-mini", "grok-3"],
          openai: ["gpt-5.2"],
          claude: ["claude-4.5-sonnet"],
          current: {
            default_provider: "grok",
            chat_gemini: "gemini-2.5-pro",
            chat_grok: "grok-3-mini",
            chat_openai: "gpt-5.2",
            chat_claude: "claude-4.5-sonnet",
          },
        });
      }

      if (req.path === "/servers/api/monitoring/config/" && req.method === "GET") {
        return json({
          thresholds: {
            cpu_warn: 70,
            cpu_crit: 90,
            mem_warn: 75,
            mem_crit: 92,
            disk_warn: 80,
            disk_crit: 95,
          },
          stats: {
            monitored_servers: servers.length,
            total_checks: 12,
            active_alerts: 0,
            last_check_at: FIXED_DATE,
          },
        });
      }

      if (req.path === "/servers/api/monitoring/config/" && req.method === "POST") {
        return json({ success: true });
      }
  return undefined;
}
