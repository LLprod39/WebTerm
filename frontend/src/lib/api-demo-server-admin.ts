import { ACCESS_FEATURE_OPTIONS } from "./access-features";
import {
  DEMO_ACTIVITY_LOGS,
  DEMO_BOOTSTRAP,
  DEMO_MODELS,
  DEMO_SETTINGS,
} from "./demo";

// Poll counter driving the simulated live playbook run in demo mode.
let demoPlaybookRunPolls = 0;

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

  // Agents
  if (path.includes("/servers/api/agents/dashboard")) {
    const now = Date.now();
    const minutesAgo = (m: number) => new Date(now - m * 60_000).toISOString();
    const baseRun = {
      agent_mode: "full", agent_type: "deploy_watcher", pending_question: "",
      connected_servers: [], ai_analysis: "", final_report: "", commands_output: [],
    };
    const finished = (
      id: number, agentName: string, serverId: number, serverName: string,
      status: string, startedMinAgo: number, durationSec: number, iterations: number,
    ) => ({
      ...baseRun,
      id, agent_id: 1, agent_name: agentName, server_id: serverId, server_name: serverName,
      status, total_iterations: iterations, duration_ms: durationSec * 1000,
      started_at: minutesAgo(startedMinAgo), completed_at: minutesAgo(startedMinAgo - Math.ceil(durationSec / 60)),
    });
    return {
      success: true,
      active: [
        {
          ...baseRun,
          id: 120, agent_id: 1, agent_name: "Deploy Watcher", server_id: 1, server_name: "web-prod-01",
          status: "running", total_iterations: 3, duration_ms: 0,
          started_at: minutesAgo(4), completed_at: null,
        },
      ],
      recent: [
        finished(119, "Health Check", 2, "db-prod-01", "completed", 42, 38, 5),
        finished(118, "Deploy Watcher", 1, "web-prod-01", "completed", 95, 61, 7),
        finished(117, "Log Auditor", 2, "db-prod-01", "failed", 150, 24, 3),
        finished(116, "Health Check", 1, "web-prod-01", "completed", 210, 33, 5),
        finished(115, "Deploy Watcher", 1, "web-prod-01", "completed", 300, 58, 6),
        finished(114, "Backup Verifier", 2, "db-prod-01", "completed", 420, 112, 9),
        finished(113, "Health Check", 3, "staging-01", "failed", 510, 19, 2),
        finished(112, "Deploy Watcher", 1, "web-prod-01", "completed", 640, 66, 7),
        finished(111, "Log Auditor", 2, "db-prod-01", "completed", 760, 29, 4),
        finished(110, "Health Check", 1, "web-prod-01", "completed", 900, 31, 5),
      ],
    } as T;
  }
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
  if (path.includes("/servers/api/playbooks/ansible/status")) {
    return {
      success: true,
      ansible: {
        available: true,
        method: "demo",
        binary: "ansible-playbook",
        version: "ansible-core 2.17 (demo)",
        message: "Demo mode",
      },
    } as T;
  }
  if (path.includes("/servers/api/playbooks/guided/generate")) {
    return {
      success: true,
      playbook: {
        id: 9,
        name: "Guided demo",
        description: "demo",
        kind: "ansible",
        category: "custom",
        visibility: "private",
        tags: ["guided"],
        fidelity: { engine: "ansible", score: 1 },
        task_count: 1,
        is_template_clone: true,
        template_slug: "guided:demo",
        last_run_at: null,
        last_run_status: "",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        owner_id: 1,
        tasks: [{ id: "t1", command: "uptime", description: "up", continue_on_error: false }],
        source_yaml: "- name: demo\n  hosts: all\n  tasks: []\n",
      },
    } as T;
  }
  if (path.includes("/servers/api/playbooks/guided")) {
    return {
      success: true,
      recipes: [
        {
          slug: "health-check",
          name: "Health check",
          description: "Demo recipe",
          category: "diagnose",
          icon: "heart",
          fields: [],
        },
      ],
    } as T;
  }
  if (path.includes("/servers/api/playbooks/templates/") && path.includes("/install/")) {
    return {
      success: true,
      playbook: {
        id: 1,
        name: "Health snapshot",
        description: "Demo template",
        kind: "runbook",
        category: "diagnose",
        visibility: "private",
        tags: ["health"],
        fidelity: {},
        task_count: 2,
        is_template_clone: true,
        template_slug: "health-snapshot",
        last_run_at: null,
        last_run_status: "",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        owner_id: 1,
        tasks: [
          { id: "t1", command: "uptime", description: "Uptime", continue_on_error: false },
          { id: "t2", command: "df -h", description: "Disk", continue_on_error: false },
        ],
        source_yaml: "",
      },
    } as T;
  }
  if (path.includes("/servers/api/playbooks/templates")) {
    return {
      success: true,
      templates: [
        {
          slug: "health-snapshot",
          name: "Health snapshot",
          description: "Uptime, load, disk, memory",
          kind: "runbook",
          category: "diagnose",
          tags: ["health"],
          task_count: 5,
          tasks_preview: [{ description: "Uptime", command: "uptime" }],
        },
      ],
    } as T;
  }
  if (path.includes("/servers/api/playbooks/runs/") && path.includes("/cancel/")) {
    demoPlaybookRunPolls = 99;
    return { success: true, run: { id: 1, status: "cancelled", playbook_name: "Demo", host_results: [], summary: {} } } as T;
  }
  if (path.includes("/servers/api/playbooks/runs/") && path.includes("/rerun-failed/")) {
    demoPlaybookRunPolls = 0;
    return { success: true, run: { id: 2, status: "pending", playbook_name: "Demo", host_results: [], summary: {} } } as T;
  }
  if (path.includes("/servers/api/playbooks/runs/")) {
    // Simulate a live run: first polls stream progress, then the run completes.
    demoPlaybookRunPolls += 1;
    const step = Math.min(demoPlaybookRunPolls, 5);
    const live = step < 5;
    const logAll = [
      "PLAY [Health snapshot] *********************************************************",
      "",
      "TASK [Gathering Facts] *********************************************************",
      "ok: [demo-linux]",
      "",
      "TASK [Uptime] ******************************************************************",
      "changed: [demo-linux]",
      "",
      "TASK [Disk] ********************************************************************",
      "changed: [demo-linux]",
      "",
      "PLAY RECAP *********************************************************************",
      "demo-linux                 : ok=3    changed=2    unreachable=0    failed=0    skipped=0",
    ];
    const logCut = [4, 7, 10, 13, logAll.length][step - 1] ?? logAll.length;
    const taskNames = ["Gathering Facts", "Uptime", "Disk", "Disk", ""];
    const statusFor = (n: number) => (step > n ? "success" : step === n ? "running" : "pending");
    return {
      success: true,
      run: {
        id: 1,
        playbook_id: 1,
        status: live ? "running" : "completed",
        playbook_name: "Health snapshot",
        target_server_ids: [1],
        target_group_ids: [],
        options: { concurrency: 2, dry_run: false },
        summary: live
          ? {}
          : { hosts_total: 1, hosts_ok: 1, hosts_failed: 0, tasks_ok: 3, tasks_failed: 0, tasks_skipped: 0, engine: "ansible", ansible_method: "demo" },
        progress: {
          engine: "ansible",
          play: "Health snapshot",
          task: taskNames[step - 1],
          task_number: Math.min(step, 3),
          tasks_total: 3,
          hosts_total: 1,
          counts: { ok: Math.min(step, 3), changed: Math.max(0, Math.min(step, 3) - 1), failed: 0, skipped: 0, unreachable: 0 },
          finished: !live,
        },
        live_log: logAll.slice(0, logCut).join("\n"),
        inventory_preview: "[all]\ndemo ansible_host=10.0.0.1",
        error_message: "",
        cancel_requested: false,
        started_at: new Date(Date.now() - step * 1200).toISOString(),
        finished_at: live ? null : new Date().toISOString(),
        created_at: new Date(Date.now() - step * 1200).toISOString(),
        host_results: [
          {
            server_id: 1,
            server_name: "demo-linux",
            host: "10.0.0.1",
            status: live ? "running" : "success",
            task_results: [
              { task_id: "t0", command: "Gathering Facts", description: "Gathering Facts", status: statusFor(1), output: "", exit_code: 0 },
              { task_id: "t1", command: "uptime", description: "Uptime", status: statusFor(2), output: step > 2 ? "up 3 days, load 0.42" : "", exit_code: 0 },
              { task_id: "t2", command: "df -h", description: "Disk", status: statusFor(3), output: step > 3 ? "/ 40% used" : "", exit_code: 0 },
            ],
          },
        ],
      },
    } as T;
  }
  if (path.includes("/servers/api/playbooks/runs")) {
    return { success: true, runs: [] } as T;
  }
  if (path.includes("/servers/api/playbooks/inventory/preview")) {
    return {
      success: true,
      inventory: "[all]\ndemo ansible_host=10.0.0.1\n",
      hosts: [{ id: 1, name: "demo-linux", host: "10.0.0.1", port: 22, username: "root", group_id: null, detected_os: "ubuntu" }],
      count: 1,
    } as T;
  }
  if (path.includes("/servers/api/playbooks/import")) {
    return {
      success: true,
      playbook: {
        id: 2,
        name: "Imported",
        description: "hosts: all",
        kind: "ansible",
        category: "custom",
        visibility: "private",
        tags: ["imported"],
        fidelity: { runnable: 1, total: 1, score: 1, unsupported_modules: [] },
        task_count: 1,
        is_template_clone: false,
        template_slug: "",
        last_run_at: null,
        last_run_status: "",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        owner_id: 1,
        tasks: [{ id: "t1", command: "echo ok", description: "demo", continue_on_error: false }],
        source_yaml: "",
      },
    } as T;
  }
  if (path.includes("/servers/api/playbooks/") && path.includes("/run/")) {
    demoPlaybookRunPolls = 0;
    return {
      success: true,
      run: {
        id: 1,
        playbook_id: 1,
        status: "running",
        playbook_name: "Demo",
        target_server_ids: [1],
        target_group_ids: [],
        options: {},
        summary: {},
        inventory_preview: "",
        error_message: "",
        cancel_requested: false,
        started_at: new Date().toISOString(),
        finished_at: null,
        created_at: new Date().toISOString(),
        host_results: [],
      },
    } as T;
  }
  if (path.includes("/servers/api/playbooks/") && (path.includes("/update/") || path.includes("/duplicate/") || path.includes("/create/"))) {
    return {
      success: true,
      playbook: {
        id: 1,
        name: "Demo playbook",
        description: "",
        kind: "runbook",
        category: "custom",
        visibility: "private",
        tags: [],
        fidelity: {},
        task_count: 1,
        is_template_clone: false,
        template_slug: "",
        last_run_at: null,
        last_run_status: "",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        owner_id: 1,
        tasks: [{ id: "t1", command: "uptime", description: "", continue_on_error: false }],
        source_yaml: "",
      },
    } as T;
  }
  if (path.includes("/servers/api/playbooks/") && path.includes("/delete/")) {
    return { success: true } as T;
  }
  if (path.match(/\/servers\/api\/playbooks\/\d+\/?$/)) {
    return {
      success: true,
      playbook: {
        id: 1,
        name: "Demo playbook",
        description: "Demo mode",
        kind: "runbook",
        category: "diagnose",
        visibility: "private",
        tags: ["demo"],
        fidelity: {},
        task_count: 1,
        is_template_clone: false,
        template_slug: "",
        last_run_at: null,
        last_run_status: "",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        owner_id: 1,
        tasks: [{ id: "t1", command: "uptime", description: "Uptime", continue_on_error: false }],
        source_yaml: "",
      },
    } as T;
  }
  if (path.includes("/servers/api/playbooks")) {
    return { success: true, playbooks: [], count: 0 } as T;
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

  // Knowledge + memory (must always include items arrays — UI calls .filter on them)
  if (path.includes("/knowledge")) {
    return { success: true, items: [], categories: [] } as T;
  }
  if (path.includes("/memory/snapshots") || path.includes("/memory/overview") || path.includes("/memory/")) {
    return { success: true, items: [], snapshots: [], episodes: [], revalidations: [], summary: {} } as T;
  }
  if (path.includes("/shares") || path.includes("/share/")) {
    return { success: true, shares: [] } as T;
  }

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
