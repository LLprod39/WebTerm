import { Page } from "@playwright/test";
import { ApiHarness, installApiHarness, json } from "./apiHarness";

type SessionUser = {
  id: number;
  username: string;
  email: string;
  is_staff: boolean;
  features: {
    servers: boolean;
    dashboard: boolean;
    agents: boolean;
    studio: boolean;
    settings: boolean;
    orchestrator: boolean;
  };
};

type ServerItem = {
  id: number;
  name: string;
  host: string;
  port: number;
  username: string;
  server_type: "ssh" | "rdp";
  rdp: boolean;
  status: "online" | "offline" | "unknown";
  group_id: number | null;
  group_name: string;
  is_shared: boolean;
  can_edit: boolean;
  share_context_enabled: boolean;
  shared_by_username: string;
  terminal_path: string;
  minimal_terminal_path: string;
  last_connected: string | null;
};

type PlatformMockOptions = {
  authenticated?: boolean;
  isStaff?: boolean;
  lang?: "en" | "ru";
};

type PlatformMockResult = {
  harness: ApiHarness;
  state: {
    authenticated: boolean;
  };
};

const FIXED_DATE = "2026-03-01T08:00:00.000Z";

function makeSessionUser(isStaff: boolean, username = "admin"): SessionUser {
  return {
    id: 1,
    username,
    email: `${username}@example.com`,
    is_staff: isStaff,
    features: {
      servers: true,
      dashboard: true,
      agents: true,
      studio: true,
      settings: true,
      orchestrator: true,
    },
  };
}

export async function installPlatformMocks(page: Page, options: PlatformMockOptions = {}): Promise<PlatformMockResult> {
  const defaultUser = makeSessionUser(options.isStaff ?? false);
  const state = {
    authenticated: options.authenticated ?? true,
  };

  const groups = [{ id: 11, name: "Core" }];
  const servers: ServerItem[] = [
    {
      id: 1,
      name: "Web-01",
      host: "10.0.0.11",
      port: 22,
      username: "root",
      server_type: "ssh",
      rdp: false,
      status: "online",
      group_id: 11,
      group_name: "Core",
      is_shared: false,
      can_edit: true,
      share_context_enabled: true,
      shared_by_username: "",
      terminal_path: "/servers/1/terminal",
      minimal_terminal_path: "/servers/1/terminal/minimal",
      last_connected: null,
    },
  ];

  let nextServerId = 2;

  const pipelines = [
    {
      id: 101,
      name: "Nightly Patch",
      description: "Patch workflow",
      icon: "⚡",
      tags: ["ops"],
      is_shared: false,
      is_template: false,
      node_count: 3,
      created_at: FIXED_DATE,
      updated_at: FIXED_DATE,
      last_run: null,
    },
  ];

  const notifications = {
    telegram_bot_token: "",
    telegram_chat_id: "",
    notify_email: "ops@example.com",
    smtp_host: "",
    smtp_port: "587",
    smtp_user: "",
    smtp_password: "",
    from_email: "",
    site_url: "http://127.0.0.1:9000",
  };

  const settingsConfig = {
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
  };

  const accessUsers = [
    {
      id: 1,
      username: "admin",
      email: "admin@example.com",
      is_staff: true,
      is_active: true,
      is_superuser: true,
      access_profile: "admin_full",
      groups: [{ id: 11, name: "Core" }],
    },
    {
      id: 2,
      username: "operator",
      email: "operator@example.com",
      is_staff: false,
      is_active: true,
      is_superuser: false,
      access_profile: "server_only",
      groups: [{ id: 11, name: "Core" }],
    },
  ];

  const accessGroups = [{ id: 11, name: "Core", members: [{ id: 1 }, { id: 2 }], member_count: 2 }];

  const accessPermissions = [
    {
      id: 1,
      user_id: 2,
      username: "operator",
      feature: "settings",
      feature_display: "Settings",
      allowed: false,
    },
  ];

  const harness = await installApiHarness(
    page,
    (req) => {
      if (req.path === "/api/auth/session/" && req.method === "GET") {
        return json({
          authenticated: state.authenticated,
          user: state.authenticated ? defaultUser : null,
        });
      }

      if (req.path === "/api/auth/login/" && req.method === "POST") {
        state.authenticated = true;
        return json({
          success: true,
          authenticated: true,
          next_url: "/servers",
          user: makeSessionUser(options.isStaff ?? false, String(req.body?.username || defaultUser.username)),
        });
      }

      if (req.path === "/api/auth/logout/" && req.method === "POST") {
        state.authenticated = false;
        return json({ success: true });
      }

      if (req.path === "/api/auth/ws-token/" && req.method === "GET") {
        return json({ token: "mock-ws-token" });
      }

      if (req.path === "/servers/api/frontend/bootstrap/" && req.method === "GET") {
        return json({
          success: true,
          servers,
          groups: groups.map((group) => ({
            id: group.id,
            name: group.name,
            server_count: servers.filter((server) => server.group_id === group.id).length,
          })),
          stats: { owned: servers.length, shared: 0, total: servers.length },
          recent_activity: [],
        });
      }

      if (req.path === "/servers/api/create/" && req.method === "POST") {
        const id = nextServerId++;
        const created: ServerItem = {
          id,
          name: String(req.body?.name || `Server-${id}`),
          host: String(req.body?.host || `10.0.0.${id}`),
          port: Number(req.body?.port || 22),
          username: String(req.body?.username || "root"),
          server_type: "ssh",
          rdp: false,
          status: "unknown",
          group_id: 11,
          group_name: "Core",
          is_shared: false,
          can_edit: true,
          share_context_enabled: false,
          shared_by_username: "",
          terminal_path: `/servers/${id}/terminal`,
          minimal_terminal_path: `/servers/${id}/terminal/minimal`,
          last_connected: null,
        };
        servers.push(created);
        return json({ success: true, server_id: id });
      }

      if (req.path === "/servers/api/monitoring/dashboard/" && req.method === "GET") {
        return json({
          summary: {
            total_servers: servers.length,
            healthy: servers.length,
            warning: 0,
            critical: 0,
            unreachable: 0,
          },
          servers: servers.map((server) => ({
            server_id: server.id,
            server_name: server.name,
            host: server.host,
            status: "healthy",
            cpu_percent: 35,
            memory_percent: 42,
            disk_percent: 51,
            load_1m: 0.2,
            uptime_seconds: 10_000,
            response_time_ms: 100,
            checked_at: FIXED_DATE,
          })),
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
        return json(pipelines);
      }

      if (req.path === "/api/studio/runs/" && req.method === "GET") {
        return json([]);
      }

      if (req.path === "/api/studio/skills/" && req.method === "GET") {
        return json([]);
      }

      if (req.path.match(/^\/api\/studio\/pipelines\/\d+\/run\/$/) && req.method === "POST") {
        return json({
          id: 7001,
          pipeline_id: Number(req.path.split("/")[4]),
          pipeline_name: "Nightly Patch",
          status: "running",
          node_states: {},
          nodes_snapshot: [],
          context: {},
          summary: "started",
          error: "",
          duration_seconds: null,
          started_at: FIXED_DATE,
          finished_at: null,
          created_at: FIXED_DATE,
          triggered_by: "admin",
        });
      }

      if (req.path === "/api/studio/templates/" && req.method === "GET") {
        return json([]);
      }

      if (req.path === "/api/studio/notifications/" && req.method === "GET") {
        return json(notifications);
      }

      if (req.path === "/api/studio/notifications/" && req.method === "POST") {
        Object.assign(notifications, req.body || {});
        return json({ ok: true });
      }

      if (req.path === "/api/studio/notifications/test-telegram/" && req.method === "POST") {
        return json({ ok: true, message: "Telegram test sent" });
      }

      if (req.path === "/api/studio/notifications/test-email/" && req.method === "POST") {
        return json({ ok: true, message: "Email test sent" });
      }

      if (req.path === "/api/studio/mcp/" && req.method === "GET") {
        return json([
          {
            id: 501,
            name: "GitHub MCP",
            description: "Repository tools",
            transport: "stdio",
            command: "npx",
            args: ["-y", "@modelcontextprotocol/server-github"],
            env: {},
            url: "",
            is_shared: false,
            last_test_ok: true,
            last_test_at: FIXED_DATE,
            last_test_error: "",
          },
        ]);
      }

      if (req.path === "/api/studio/mcp/templates/" && req.method === "GET") {
        return json([]);
      }

      if (req.path === "/api/studio/agents/" && req.method === "GET") {
        return json([]);
      }

      if (req.path === "/api/studio/servers/" && req.method === "GET") {
        return json([{ id: 1, name: "Web-01", host: "10.0.0.11" }]);
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

      if (req.path === "/api/access/users/" && req.method === "GET") {
        return json({ users: accessUsers });
      }

      if (req.path === "/api/access/groups/" && req.method === "GET") {
        return json({ groups: accessGroups });
      }

      if (req.path === "/api/access/permissions/" && req.method === "GET") {
        return json({
          permissions: accessPermissions,
          features: [
            { value: "servers", label: "Servers" },
            { value: "settings", label: "Settings" },
            { value: "orchestrator", label: "Orchestrator" },
          ],
        });
      }
    },
    options.lang ?? "en",
  );

  return { harness, state };
}
