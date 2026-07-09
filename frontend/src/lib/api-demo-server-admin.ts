import { ACCESS_FEATURE_OPTIONS } from "./access-features";
import {
  DEMO_ACTIVITY_LOGS,
  DEMO_BOOTSTRAP,
  DEMO_MODELS,
  DEMO_SETTINGS,
} from "./demo";
export function demoServerAdminFallback<T>(path: string, _options: RequestInit = {}): T | undefined {
  if (path.includes("/servers/api/") && path.includes("/files/read/")) {
    const filePath = path.includes("path=") ? decodeURIComponent(path.split("path=")[1].split("&")[0] || "/home/demo/nginx.conf") : "/home/demo/nginx.conf";
    return {
      success: true,
      file: {
        path: filePath,
        filename: filePath.split("/").filter(Boolean).pop() || "demo.conf",
        size: 246,
        encoding: "utf-8",
        content: "server {\n    listen 80;\n    server_name demo.local;\n    root /var/www/html;\n}\n",
      },
    } as T;
  }
  if (path.includes("/servers/api/") && path.includes("/files/write/")) {
    let filePath = "/home/demo/nginx.conf";
    let content = "";
    try {
      const body =
        typeof _options.body === "string" && _options.body
          ? (JSON.parse(_options.body) as { path?: string; content?: string })
          : null;
      filePath = body?.path || filePath;
      content = body?.content || content;
    } catch {
      // noop
    }
    return {
      success: true,
      file: {
        path: filePath,
        filename: filePath.split("/").filter(Boolean).pop() || "demo.conf",
        size: content.length,
        encoding: "utf-8",
        content,
      },
    } as T;
  }
  if (path.includes("/servers/api/") && path.includes("/files/chmod/")) {
    let filePath = "/home/demo/deploy.log";
    try {
      const body =
        typeof _options.body === "string" && _options.body
          ? (JSON.parse(_options.body) as { path?: string })
          : null;
      filePath = body?.path || filePath;
    } catch {
      // noop
    }
    return {
      success: true,
      path: filePath.split("/").slice(0, -1).join("/") || "/",
      entry: {
        name: filePath.split("/").filter(Boolean).pop() || "deploy.log",
        path: filePath,
        kind: "file",
        is_dir: false,
        is_symlink: false,
        size: 18432,
        permissions: "-rw-r-----",
        permissions_octal: "0640",
        modified_at: Math.floor(Date.now() / 1000),
      },
    } as T;
  }
  if (path.includes("/servers/api/") && path.includes("/files/chown/")) {
    let filePath = "/home/demo/deploy.log";
    try {
      const body =
        typeof _options.body === "string" && _options.body
          ? (JSON.parse(_options.body) as { path?: string })
          : null;
      filePath = body?.path || filePath;
    } catch {
      // noop
    }
    return {
      success: true,
      path: filePath.split("/").slice(0, -1).join("/") || "/",
      entry: {
        name: filePath.split("/").filter(Boolean).pop() || "deploy.log",
        path: filePath,
        kind: "file",
        is_dir: false,
        is_symlink: false,
        size: 18432,
        permissions: "-rw-r--r--",
        permissions_octal: "0644",
        modified_at: Math.floor(Date.now() / 1000),
      },
    } as T;
  }

  // Settings page
  if (path.includes("/api/settings/activity")) return DEMO_ACTIVITY_LOGS as T;
  if (path.includes("/api/settings/readiness")) return {
    success: true,
    status: "warning",
    summary: { ready: 3, warning: 2, error: 0, total: 5 },
    checks: [
      {
        key: "deployment_mode",
        title: "Режим Django",
        status: "warning",
        severity: "warning",
        message: "Demo mode использует dev-настройки. Для PROD запуска включите DJANGO_DEBUG=false.",
        details: { debug: true },
      },
      {
        key: "ai_providers",
        title: "AI providers",
        status: "ready",
        severity: "ready",
        message: "Demo provider готов для интерфейсной проверки.",
        action_path: "/settings/ai",
        action_label: "Открыть модели",
      },
      {
        key: "notifications",
        title: "Уведомления",
        status: "warning",
        severity: "warning",
        message: "В demo mode внешняя отправка уведомлений не выполняется.",
        action_path: "/settings/notifications",
        action_label: "Открыть уведомления",
      },
      {
        key: "ldap_login",
        title: "LDAP Login",
        status: "ready",
        severity: "ready",
        message: "LDAP login выключен в demo mode и показывается как env/startup настройка.",
        action_path: "/settings/sso",
        action_label: "Открыть SSO",
      },
      {
        key: "runtime_limits",
        title: "Runtime limits",
        status: "ready",
        severity: "ready",
        message: "Demo soft limits и LLM budget заданы.",
        action_path: "/settings/limits",
        action_label: "Открыть лимиты",
      },
    ],
  } as T;
  if (path.includes("/api/settings")) return DEMO_SETTINGS as T;
  if (path.includes("/api/models/refresh")) {
    const requestedProvider = (() => {
      try {
        const raw = typeof _options.body === "string" ? JSON.parse(_options.body) : null;
        return typeof raw?.provider === "string" ? raw.provider : "gemini";
      } catch {
        return "gemini";
      }
    })();
    const demoModels =
      requestedProvider === "ollama"
        ? ["llama3.2:latest", "qwen2.5-coder:7b"]
        : requestedProvider === "openai"
          ? ["gpt-5-mini"]
          : requestedProvider === "claude"
            ? ["claude-sonnet-4-6"]
            : requestedProvider === "grok"
              ? ["grok-3"]
              : ["gemini-2.0-flash"];
    return { success: true, provider: requestedProvider, models: demoModels, count: demoModels.length } as T;
  }
  if (path.includes("/api/models")) return DEMO_MODELS as T;

  // Admin dashboard — must match AdminDashboardData shape
  if (path.includes("/api/admin/dashboard")) return {
    success: true,
    data: {
      online_users: { count: 1, total_registered: 1, users: [{ username: "demo", action: "login", time: new Date().toISOString() }] },
      ai: { requests_today: 0 },
      terminals: { active: 0, connections: [] },
      agents: { running: 0, today: 0, succeeded_24h: 0, failed_24h: 0, success_rate: 0 },
      api_usage: {},
      api_calls_today: 0,
      providers: { gemini: { enabled: true, model: "gemini-2.0-flash" } },
      servers: { total: 3, active: 2 },
      tasks: { total: 0, in_progress: 0 },
      hourly_activity: [],
      top_users: [{ username: "demo", total: 5, ai_requests: 2, terminal_sessions: 3 }],
      recent_activity: [{ user: "demo", category: "auth", action: "login", time: new Date().toISOString() }],
      fleet_health: { avg_cpu: 25, avg_memory: 40, avg_disk: 35, healthy: 2, warning: 0, critical: 0, unreachable: 1 },
      active_alerts_count: 0,
      alerts: [],
      app_version: "demo",
    },
  } as T;
  if (path.includes("/api/admin/users/sessions")) return { success: true, online_count: 1, total_registered: 1, active_today: 1, sessions: [] } as T;
  if (path.includes("/api/admin/users/activity")) return { success: true, total: 0, events: [] } as T;

  // Monitoring dashboard — must match MonitoringDashboard shape
  if (path.includes("/servers/api/monitoring/config")) return {
    success: true,
    thresholds: { cpu_warn: 80, cpu_crit: 95, mem_warn: 85, mem_crit: 95, disk_warn: 80, disk_crit: 90 },
    stats: { total_checks: 0, active_alerts: 0, last_check_at: null, monitored_servers: 0 },
  } as T;
  if (path.includes("/servers/api/monitoring/dashboard")) return {
    success: true,
    servers: [],
    alerts: [],
    summary: { total_servers: 3, healthy: 2, warning: 0, critical: 0, unreachable: 1, unknown: 0, active_alerts: 0, avg_cpu: 25, avg_memory: 40, avg_disk: 35 },
    recent_activity: [],
  } as T;
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

  // Agents
  if (path.includes("/servers/api/agents/dashboard")) return { success: true, active: [], recent: [] } as T;
  if (path.includes("/servers/api/agents/schedules/dispatch/")) {
    return {
      success: true,
      summary: {
        scanned: 1,
        due: 1,
        launched_agents: 1,
        runs_created: 1,
        background_runs: 1,
        mini_runs: 0,
        skipped: 0,
        skip_reasons: {
          not_due: 0,
          no_servers: 0,
          active_run: 0,
          limit: 0,
          launch_rejected: 0,
          error: 0,
        },
        errors: [],
      },
      generated_at: new Date().toISOString(),
    } as T;
  }
  if (path.includes("/servers/api/agents/schedules/")) {
    return {
      success: true,
      summary: {
        total_scheduled: 1,
        enabled: 1,
        paused: 0,
        due_now: 1,
        active_runs: 0,
      },
      generated_at: new Date().toISOString(),
      scheduled_agents: [
        {
          id: 1,
          name: "Demo Deploy Watcher",
          mode: "full",
          mode_display: "Full Agent (ReAct)",
          agent_type: "deploy_watcher",
          agent_type_display: "Deploy Watcher",
          server_count: 1,
          server_names: ["demo-linux"],
          schedule_minutes: 15,
          is_enabled: true,
          commands: [],
          ai_prompt: "Track deploy drift",
          goal: "Check services after deploy and verify health.",
          system_prompt: "",
          max_iterations: 8,
          allow_multi_server: false,
          last_run_at: new Date(Date.now() - 60 * 60_000).toISOString(),
          last_run_status: "completed",
          last_run_id: 1,
          active_run_id: null,
          schedule_state: "due",
          due_now: true,
          next_due_at: new Date(Date.now() - 30 * 60_000).toISOString(),
          next_due_in_seconds: 0,
        },
      ],
    } as T;
  }
  if (path.includes("/servers/api/agents/templates")) return { success: true, templates: [] } as T;
  if (path.includes("/servers/api/agents/runs/") && path.includes("/events/")) {
    return { success: true, events: [], total: 0 } as T;
  }
  if (path.includes("/servers/api/agents/runs")) return { success: true, runs: [] } as T;
  if (path.includes("/servers/api/watchers/drafts/") && path.includes("/launch/")) {
    return {
      success: true,
      draft: {
        id: 1,
        server_id: 1,
        server_name: "demo-linux",
        severity: "warning",
        recommended_role: "infra_scout",
        objective: "Investigate service drift on demo-linux",
        reasons: ["Demo mode watcher draft"],
        memory_excerpt: ["Nginx was restarted during the last deploy"],
        status: "acknowledged",
        acknowledged_at: new Date().toISOString(),
        acknowledged_by: "demo",
        resolved_at: null,
        first_seen_at: new Date().toISOString(),
        last_seen_at: new Date().toISOString(),
        metadata: { launch_count: 1 },
      },
      agent_id: 1,
      run_id: 1,
      status: "pending",
    } as T;
  }
  if (path.includes("/servers/api/agents")) return { success: true, agents: [] } as T;
  if (path.includes("/servers/api/alerts")) return { success: true, alerts: [] } as T;
  if (path.includes("/servers/api/") && path.includes("/files/")) return {
    success: true,
    path: "/home/demo",
    home_path: "/home/demo",
    parent_path: "/home",
    entries: [
      {
        name: "deploy.log",
        path: "/home/demo/deploy.log",
        kind: "file",
        is_dir: false,
        is_symlink: false,
        size: 18432,
        permissions: "-rw-r--r--",
        permissions_octal: "0644",
        modified_at: Math.floor(Date.now() / 1000) - 3600,
      },
      {
        name: "releases",
        path: "/home/demo/releases",
        kind: "dir",
        is_dir: true,
        is_symlink: false,
        size: 0,
        permissions: "drwxr-xr-x",
        permissions_octal: "0755",
        modified_at: Math.floor(Date.now() / 1000) - 86400,
      },
    ],
  } as T;
  if (path.includes("/servers/api/global-context")) {
    return { rules: "", forbidden_commands: [], required_checks: [], environment_vars: {} } as T;
  }
  if (path.includes("/group-context") || path.includes("/groups/") && path.includes("/context")) {
    return { rules: "", forbidden_commands: [], environment_vars: {} } as T;
  }
  if (path.includes("/servers/api/master-password")) return { has_master_password: false, success: true } as T;

  // Server detail / CRUD used by create-edit dialogs
  if (path.includes("/servers/api/") && path.includes("/get/")) {
    const match = path.match(/\/servers\/api\/(\d+)\/get\//);
    const id = match ? Number(match[1]) : 1;
    const seed = DEMO_BOOTSTRAP.servers.find((server) => server.id === id) || DEMO_BOOTSTRAP.servers[0];
    return {
      id: seed?.id ?? id,
      name: seed?.name ?? `server-${id}`,
      host: seed?.host ?? "127.0.0.1",
      port: seed?.port ?? 22,
      username: seed?.username ?? "demo",
      server_type: "ssh",
      auth_method: "key",
      key_path: "",
      tags: "demo,ssh",
      notes: "Demo server (static UI demo — no live SSH).",
      group_id: seed?.group_id ?? 1,
      is_active: true,
      ai_read_only: false,
      sudo_auth_mode: "none",
      has_saved_sudo_password: false,
      corporate_context: "",
      network_config: {},
      has_saved_password: false,
      can_view_password: false,
      can_edit: true,
      is_shared_server: false,
      share_context_enabled: false,
      shared_by_username: "",
    } as T;
  }
  if (path.includes("/servers/api/create") || path.includes("/servers/api/") && path.endsWith("/create/")) {
    return { success: true, server_id: 99, message: "created (demo)" } as T;
  }
  if (path.includes("/update/")) return { success: true, message: "updated (demo)" } as T;
  if (path.includes("/delete/") || path.includes("/test/")) return { success: true, message: "ok (demo)" } as T;
  if (path.includes("/execute/")) {
    return {
      success: true,
      output: { stdout: "demo-execute: backend offline\n", stderr: "", exit_code: 0 },
    } as T;
  }
  if (path.includes("/reveal-password/")) {
    return { success: true, password: "••••••••" } as T;
  }

  // Knowledge + memory (must always include items arrays)
  if (path.includes("/knowledge")) return { success: true, items: [], categories: [] } as T;
  if (path.includes("/memory/snapshots") || path.includes("/memory/overview") || path.includes("/memory/")) {
    return { success: true, items: [], snapshots: [], episodes: [], revalidations: [], summary: {} } as T;
  }
  if (path.includes("/shares")) return { success: true, shares: [] } as T;

  if (path.includes("/api/health")) return { status: "ok" } as T;
  if (path.includes("/api/access/users")) return {
    success: true,
    features: ACCESS_FEATURE_OPTIONS,
    users: [
      {
        id: 1,
        username: "demo",
        email: "demo@example.com",
        is_staff: true,
        is_active: true,
        is_superuser: false,
        access_profile: "admin_full",
        groups: [{ id: 1, name: "Operators" }],
        effective_permissions: {
          servers: true,
          dashboard: true,
          agents: true,
          studio: true,
          studio_pipelines: true,
          studio_runs: true,
          studio_agents: true,
          studio_skills: true,
          studio_mcp: true,
          studio_notifications: true,
          kubernetes: false,
          mars: false,
          settings: true,
          orchestrator: true,
          knowledge_base: true,
        },
        explicit_permissions: {},
        group_permissions: { servers: true, studio: true, studio_pipelines: true, studio_runs: true, studio_agents: true, studio_skills: true, studio_mcp: true, studio_notifications: true },
        group_permission_sources: {
          servers: [{ group_id: 1, group_name: "Operators", allowed: true }],
          studio: [{ group_id: 1, group_name: "Operators", allowed: true }],
          studio_pipelines: [{ group_id: 1, group_name: "Operators", allowed: true }],
          studio_runs: [{ group_id: 1, group_name: "Operators", allowed: true }],
          studio_agents: [{ group_id: 1, group_name: "Operators", allowed: true }],
          studio_skills: [{ group_id: 1, group_name: "Operators", allowed: true }],
          studio_mcp: [{ group_id: 1, group_name: "Operators", allowed: true }],
          studio_notifications: [{ group_id: 1, group_name: "Operators", allowed: true }],
        },
        permission_sources: {
          servers: "group_explicit",
          dashboard: "staff_default",
          agents: "staff_default",
          studio: "group_explicit",
          studio_pipelines: "group_explicit",
          studio_runs: "group_explicit",
          studio_agents: "group_explicit",
          studio_skills: "group_explicit",
          studio_mcp: "group_explicit",
          studio_notifications: "group_explicit",
          kubernetes: "explicit_opt_in",
          mars: "explicit_opt_in",
          settings: "staff_default",
          orchestrator: "staff_default",
          knowledge_base: "staff_default",
        },
      },
    ],
  } as T;
  if (path.includes("/api/access/groups")) return {
    success: true,
    features: ACCESS_FEATURE_OPTIONS,
    groups: [
      {
        id: 1,
        name: "Operators",
        member_count: 1,
        members: [{ id: 1, username: "demo" }],
        explicit_permissions: { servers: true, studio: true, studio_pipelines: true, studio_runs: true, studio_agents: true, studio_skills: true, studio_mcp: true, studio_notifications: true },
      },
    ],
  } as T;
  if (path.includes("/api/access/group-permissions")) return {
    success: true,
    features: ACCESS_FEATURE_OPTIONS,
    permissions: [
      { id: 1, group_id: 1, group_name: "Operators", feature: "servers", feature_display: "Servers", allowed: true },
      { id: 2, group_id: 1, group_name: "Operators", feature: "studio", feature_display: "Studio", allowed: true },
      { id: 3, group_id: 1, group_name: "Operators", feature: "studio_pipelines", feature_display: "Studio Pipelines", allowed: true },
      { id: 4, group_id: 1, group_name: "Operators", feature: "studio_runs", feature_display: "Studio Runs", allowed: true },
      { id: 5, group_id: 1, group_name: "Operators", feature: "studio_agents", feature_display: "Studio Agents", allowed: true },
      { id: 6, group_id: 1, group_name: "Operators", feature: "studio_skills", feature_display: "Studio Skills", allowed: true },
      { id: 7, group_id: 1, group_name: "Operators", feature: "studio_mcp", feature_display: "Studio MCP", allowed: true },
      { id: 8, group_id: 1, group_name: "Operators", feature: "studio_notifications", feature_display: "Studio Notifications", allowed: true },
    ],
  } as T;
  if (path.includes("/api/access/permissions")) return {
    success: true,
    features: ACCESS_FEATURE_OPTIONS,
    permissions: [],
    group_permissions: [],
  } as T;
  return undefined;
}
