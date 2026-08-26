import { expect, test } from "@playwright/test";
import { installApiHarness, json } from "./support/apiHarness";

const fullFeatures = {
  servers: true,
  dashboard: true,
  agents: true,
  studio: true,
  settings: true,
  chat: true,
  orchestrator: true,
};

test("sidebar navigation opens key sections", async ({ page }) => {
  await installApiHarness(page, (req) => {
    if (req.path === "/api/auth/session/" && req.method === "GET") {
      return json({
        authenticated: true,
        user: {
          id: 7,
          username: "operator",
          email: "operator@example.com",
          is_staff: false,
          features: fullFeatures,
        },
      });
    }

    if (req.path === "/servers/api/frontend/bootstrap/" && req.method === "GET") {
      return json({
        success: true,
        servers: [
          {
            id: 1,
            name: "Web-01",
            host: "10.0.0.11",
            port: 22,
            username: "root",
            server_type: "ssh",
            status: "online",
            group_id: 11,
            group_name: "Core",
            is_shared: false,
            can_edit: true,
            share_context_enabled: false,
            shared_by_username: "",
            terminal_path: "/servers/1/terminal",
            minimal_terminal_path: "/servers/1/terminal/minimal",
            last_connected: null,
          },
        ],
        groups: [{ id: 11, name: "Core", server_count: 1 }],
        stats: { owned: 1, shared: 0, total: 1 },
        recent_activity: [],
      });
    }

    if (req.path === "/servers/api/monitoring/dashboard/" && req.method === "GET") {
      return json({
        summary: {
          total_servers: 1,
          healthy: 1,
          warning: 0,
          critical: 0,
          unreachable: 0,
        },
        servers: [
          {
            server_id: 1,
            server_name: "Web-01",
            host: "10.0.0.11",
            status: "healthy",
            cpu_percent: 35,
            memory_percent: 42,
            disk_percent: 51,
            load_1m: 0.22,
            uptime_seconds: 10000,
            response_time_ms: 100,
            checked_at: new Date().toISOString(),
          },
        ],
        alerts: [],
      });
    }

    if (req.path === "/servers/api/agents/" && req.method === "GET") {
      return json({ success: true, agents: [] });
    }

    if (req.path === "/servers/api/agents/dashboard/" && req.method === "GET") {
      return json({ success: true, active: [], recent: [] });
    }

    if (req.path === "/api/studio/pipelines/" && req.method === "GET") {
      return json([
        {
          id: 101,
          name: "Nightly Patch",
          description: "Patch flow",
          icon: "⚡",
          tags: ["ops"],
          is_shared: false,
          is_template: false,
          node_count: 2,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          last_run: null,
        },
      ]);
    }

    if (req.path === "/api/studio/runs/" && req.method === "GET") {
      return json([]);
    }

    if (req.path === "/api/studio/templates/" && req.method === "GET") {
      return json([]);
    }

    if (req.path === "/api/studio/notifications/" && req.method === "GET") {
      return json({
        telegram_bot_token: "",
        telegram_chat_id: "",
        notify_email: "ops@example.com",
        smtp_host: "",
        smtp_port: "587",
        smtp_user: "",
        smtp_password: "",
        from_email: "",
        site_url: "http://127.0.0.1:9000",
      });
    }

    if (req.path === "/api/settings/" && req.method === "GET") {
      return json({
        success: true,
        config: {
          default_provider: "grok",
          internal_llm_provider: "grok",
          gemini_enabled: true,
          grok_enabled: true,
          openai_enabled: true,
          claude_enabled: true,
          gemini_set: true,
          grok_set: true,
          openai_set: true,
          claude_set: true,
          chat_llm_provider: "grok",
          chat_llm_model: "grok-3-mini",
          agent_llm_provider: "grok",
          agent_llm_model: "grok-3",
          orchestrator_llm_provider: "openai",
          orchestrator_llm_model: "gpt-5.2",
          chat_model_gemini: "gemini-2.5-pro",
          chat_model_grok: "grok-3-mini",
          chat_model_openai: "gpt-5.2",
          chat_model_claude: "claude-4.5-sonnet",
          openai_reasoning_effort: "medium",
          domain_auth_enabled: true,
          domain_auth_header: "REMOTE_USER",
          domain_auth_auto_create: true,
        },
      });
    }

    if (req.path === "/api/models/" && req.method === "GET") {
      return json({
        gemini: ["gemini-2.5-pro"],
        grok: ["grok-3-mini"],
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

    if (req.path === "/api/settings/activity/" && req.method === "GET") {
      return json({
        success: true,
        events: [],
        summary: { total_events: 0, total_users: 0 },
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
          monitored_servers: 1,
          total_checks: 10,
          active_alerts: 0,
          last_check_at: new Date().toISOString(),
        },
      });
    }
  });

  await page.goto("/servers");
  await expect(page.getByRole("heading", { name: "Servers" })).toBeVisible();

  await page.getByRole("link", { name: "Dashboard" }).first().click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: "My workspace" })).toBeVisible();

  await page.getByRole("link", { name: "Agents" }).first().click();
  await expect(page).toHaveURL(/\/agents$/);
  await expect(page.getByRole("heading", { name: "Agents", exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Studio" }).first().click();
  await expect(page).toHaveURL(/\/studio$/);
  await expect(page.getByRole("heading", { name: "Pipelines", exact: true })).toBeVisible();

  await page.getByRole("link", { name: "Settings" }).first().click();
  await expect(page).toHaveURL(/\/settings$/);
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();

  await page.getByRole("link", { name: "Servers" }).first().click();
  await expect(page).toHaveURL(/\/servers$/);
  await expect(page.getByRole("heading", { name: "Servers" })).toBeVisible();
});

test("pilot personal AI capability cannot direct-load administrative settings", async ({ page }) => {
  const harness = await installApiHarness(page, (req) => {
    if (req.path === "/api/auth/session/" && req.method === "GET") {
      return json({
        authenticated: true,
        user: {
          id: 20,
          username: "pilot-user",
          email: "pilot@example.test",
          is_staff: false,
          access_profile: "pilot_user",
          features: { ai_connections_personal: true },
        },
      });
    }
    if (req.path === "/api/ai/providers/connections/") {
      return json({ success: true, connections: [] });
    }
    if (req.path === "/api/ai/providers/preferences/") {
      return json({ success: true, preferences: [], workspace_defaults: [] });
    }
    if (req.path === "/api/ai/providers/catalog/") {
      return json({ success: true, targets: [], purposes: [] });
    }
  });

  await page.goto("/settings/users");

  await expect(page).toHaveURL(/\/settings\/ai-connections$/);
  await expect(page.getByRole("heading", { name: "CLI subscriptions" })).toBeVisible();
  expect(harness.getCalls("/api/access/users/")).toHaveLength(0);
  expect(harness.getCalls("/api/ai/providers/pools/")).toHaveLength(0);
});

test("pilot opens Chat with the narrow chat capability only", async ({ page }) => {
  const harness = await installApiHarness(page, (req) => {
    if (req.path === "/api/auth/session/" && req.method === "GET") {
      return json({
        authenticated: true,
        user: {
          id: 21,
          username: "pilot-chat",
          email: "pilot-chat@example.test",
          is_staff: false,
          access_profile: "pilot_user",
          features: {
            chat: true,
            orchestrator: false,
            ai_connections_personal: true,
            ai_connections_admin: false,
          },
        },
      });
    }
    if (req.path === "/api/assistant/chats/") return json({ chats: [] });
    if (req.path === "/api/ai/providers/connections/") return json({ success: true, connections: [] });
  });

  await page.goto("/chat");

  await expect(page).toHaveURL(/\/chat$/);
  await expect(page.getByRole("heading", { name: "Chats", exact: true })).toBeVisible();
  expect(harness.getCalls("/api/ai/providers/pools/")).toHaveLength(0);
});
