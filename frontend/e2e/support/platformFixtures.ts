import { Page } from "@playwright/test";
import { ApiHarness, installApiHarness, json } from "./apiHarness";

type SessionUser = {
  id: number;
  username: string;
  email: string;
  is_staff: boolean;
  features: Record<string, boolean> & {
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
  server_type: "ssh";
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
  features?: Partial<SessionUser["features"]>;
  agentList?: "default" | "empty";
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
      kubernetes: false,
      mars: false,
      settings: true,
      orchestrator: true,
    },
  };
}

export async function installPlatformMocks(page: Page, options: PlatformMockOptions = {}): Promise<PlatformMockResult> {
  const defaultUser = makeSessionUser(options.isStaff ?? false);
  defaultUser.features = {
    ...defaultUser.features,
    ...(options.features || {}),
  };
  const state = {
    authenticated: options.authenticated ?? true,
  };

  const groups = [{ id: 11, name: "Core", description: "Core services", color: "#3b82f6", role: "owner", can_edit: true }];
  const servers: ServerItem[] = [
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
      share_context_enabled: true,
      shared_by_username: "",
      terminal_path: "/servers/1/terminal",
      minimal_terminal_path: "/servers/1/terminal/minimal",
      last_connected: null,
    },
  ];

  let nextServerId = 2;

  const executionReadinessMissing = {
    required: true,
    ready: false,
    status: "missing",
    severity: "warning",
    title: "Execution worker не запущен",
    description: "Full/multi-агенты будут поставлены в очередь, но не начнут выполняться до запуска worker.",
    next_action: "Запустите worker: python manage.py run_agent_execution_plane --worker-key default",
    worker: {
      worker_kind: "agent_execution",
      worker_key: "default",
      status: "missing",
      is_stale: true,
      hostname: "",
      pid: null,
      command: "",
      heartbeat_at: null,
      lease_expires_at: null,
      last_started_at: null,
      last_stopped_at: null,
      last_cycle_started_at: null,
      last_cycle_finished_at: null,
      last_summary: {},
      last_error: "",
    },
  };

  const miniExecutionReadiness = {
    required: false,
    ready: true,
    status: "not_required",
    severity: "info",
    title: "Execution worker не требуется",
    description: "Mini-агенты выполняются inline и не требуют execution-plane worker.",
    next_action: "",
    worker: null,
  };

  const agentWorkerStates = {
    scheduled_agents: {
      worker_kind: "scheduled_agents",
      worker_key: "default",
      status: "running",
      is_stale: false,
      hostname: "sched-worker-01",
      pid: 7331,
      command: "python manage.py run_scheduled_agents --daemon --worker-key default",
      heartbeat_at: FIXED_DATE,
      lease_expires_at: "2026-03-01T08:03:00.000Z",
      last_started_at: FIXED_DATE,
      last_stopped_at: null,
      last_cycle_started_at: FIXED_DATE,
      last_cycle_finished_at: FIXED_DATE,
      last_summary: { scanned: 2, due: 1, launched_agents: 0, skipped: 2 },
      last_error: "",
    },
  };

  const agentRuntimeOverview = {
    status: "needs_attention",
    severity: "warning",
    summary: {
      configured_agents: 2,
      active_runs: 1,
      pending_runs: 1,
      running_runs: 0,
      waiting_runs: 0,
      queued_dispatches: 1,
      claimed_dispatches: 0,
      scheduled_agents: 1,
      scheduled_due_now: 1,
      issues: 1,
    },
    queue: {
      runs: { pending: 1, running: 0, waiting: 0 },
      dispatches: { queued: 1, claimed: 0 },
    },
    schedule: {
      total_scheduled: 1,
      enabled: 1,
      paused: 0,
      due_now: 1,
      worker_ready: true,
    },
    workers: agentWorkerStates,
    execution_readiness: executionReadinessMissing,
    issues: [
      {
        id: "execution_worker_not_ready",
        severity: "warning",
        title: "Execution worker не активен",
        description: "Full/multi-запуски есть в очереди, но worker не подтверждён.",
        next_action: "python manage.py run_agent_execution_plane --worker-key default",
      },
    ],
    commands: {
      execution_worker: "python manage.py run_agent_execution_plane --worker-key default",
      scheduled_agents_worker: "python manage.py run_scheduled_agents --daemon --worker-key default",
      ops_supervisor: "python manage.py run_ops_supervisor --with-scheduled-agents --with-watchers",
    },
    items: {
      active_runs: [
        {
          run_id: 901,
          agent_id: 202,
          agent_name: "Patch Rollout",
          agent_mode: "multi",
          server_id: 1,
          server_name: "Web-01",
          status: "pending",
          started_at: FIXED_DATE,
          completed_at: null,
          age_seconds: 125,
          duration_ms: 0,
          pending_question: "",
          is_stale_candidate: false,
          dispatch: null,
        },
      ],
      queued_dispatches: [
        {
          dispatch_id: 41,
          run_id: 901,
          agent_id: 202,
          agent_name: "Patch Rollout",
          agent_mode: "multi",
          server_id: 1,
          server_name: "Web-01",
          dispatch_kind: "launch",
          status: "queued",
          server_ids: [1],
          queued_at: FIXED_DATE,
          claimed_at: null,
          heartbeat_at: null,
          lease_expires_at: null,
          queued_age_seconds: 125,
          lease_seconds_left: null,
          claimed_by: "",
          attempt_count: 0,
          error: "",
        },
      ],
      scheduled_due: [
        {
          agent_id: 202,
          agent_name: "Patch Rollout",
          agent_mode: "multi",
          server_count: 1,
          server_names: ["Web-01"],
          schedule_minutes: 60,
          schedule_config: { mode: "interval", interval_minutes: 60 },
          last_run_at: "2026-03-01T07:00:00.000Z",
          next_due_at: FIXED_DATE,
          due_age_seconds: 0,
          active_run_id: 901,
          active_run_status: "pending",
        },
      ],
      stale_candidates: [],
    },
    generated_at: FIXED_DATE,
  };

  const serverAgents = [
    {
      id: 201,
      name: "Disk Audit",
      mode: "mini",
      mode_display: "Mini Agent",
      agent_type: "disk_report",
      agent_type_display: "Disk Report",
      server_count: 1,
      server_ids: [1],
      server_names: ["Web-01"],
      schedule_minutes: 0,
      schedule_config: { mode: "manual" },
      is_enabled: true,
      commands: ["df -h", "du -sh /var/log"],
      ai_prompt: "Summarize disk pressure.",
      goal: "",
      system_prompt: "",
      max_iterations: 20,
      allow_multi_server: false,
      tools_config: {},
      sudo_policy: "disabled",
      stop_conditions: [],
      skill_slugs: [],
      input_artifacts: [],
      report_delivery: { telegram: { enabled: false, chat_id: "", format: "brief", include_link: true } },
      session_timeout_seconds: 600,
      max_connections: 5,
      last_run_at: FIXED_DATE,
      last_run_status: "completed",
      last_run_id: 901,
      active_run_id: null,
      execution_readiness: miniExecutionReadiness,
      schedule_state: "manual",
      due_now: false,
      next_due_at: null,
      next_due_in_seconds: null,
    },
    {
      id: 202,
      name: "Patch Rollout",
      mode: "multi",
      mode_display: "Multi-Agent Pipeline",
      agent_type: "custom",
      agent_type_display: "Custom",
      server_count: 1,
      server_ids: [1],
      server_names: ["Web-01"],
      schedule_minutes: 15,
      schedule_config: { mode: "interval", interval_minutes: 15 },
      is_enabled: true,
      commands: [],
      ai_prompt: "",
      goal: "Validate patch readiness and collect evidence before rollout.",
      system_prompt: "",
      max_iterations: 20,
      allow_multi_server: true,
      tools_config: {},
      sudo_policy: "ask",
      stop_conditions: ["report ready"],
      skill_slugs: [],
      input_artifacts: [],
      report_delivery: { telegram: { enabled: true, chat_id: "", format: "brief", include_link: true } },
      session_timeout_seconds: 900,
      max_connections: 5,
      last_run_at: FIXED_DATE,
      last_run_status: "running",
      last_run_id: 901,
      active_run_id: 901,
      execution_readiness: executionReadinessMissing,
      schedule_state: "due",
      due_now: true,
      next_due_at: FIXED_DATE,
      next_due_in_seconds: 0,
    },
  ];

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
      graph_version: 2,
      trigger_summary: { active_total: 1, active_manual: 1, active_webhook: 0, active_schedule: 0, active_monitoring: 0, last_triggered_at: null },
      nodes: [
        { id: "manual_start", type: "trigger/manual", position: { x: 0, y: 0 }, data: { label: "Manual start", is_active: true } },
      ],
      edges: [],
      triggers: [],
    },
  ];

  const draftSessions = [
    {
      id: 501,
      status: "ready",
      intent: "create",
      title: "Daily health report",
      user_goal: "Create a daily health check with Telegram delivery.",
      source_pipeline_id: null,
      applied_pipeline_id: null,
      selected_node_id: "",
      created_at: FIXED_DATE,
      updated_at: FIXED_DATE,
      applied_at: null,
      latest_revision: {
        id: 9001,
        session_id: 501,
        user_message: "Create a daily health check with Telegram delivery.",
        created_at: FIXED_DATE,
        preview_nodes: [
          { id: "manual_start", type: "trigger/manual", position: { x: 0, y: 0 }, data: { label: "Manual start" } },
          { id: "server_check", type: "ops/server_snapshot", position: { x: 260, y: 0 }, data: { label: "Server check" } },
          { id: "report", type: "output/report", position: { x: 520, y: 0 }, data: { label: "Telegram report" } },
        ],
        preview_edges: [
          { id: "e1", source: "manual_start", target: "server_check", sourceHandle: "out" },
          { id: "e2", source: "server_check", target: "report", sourceHandle: "out" },
        ],
        response: {
          reply: "Draft ready.",
          target_node_id: null,
          node_patch: {},
          graph_patch: {
            anchor_node_id: null,
            nodes: [
              { ref: "manual_start", type: "trigger/manual", label: "Manual start", data: {} },
              { ref: "server_check", type: "ops/server_snapshot", label: "Server check", data: {} },
              { ref: "report", type: "output/report", label: "Telegram report", data: {} },
            ],
            edges: [
              { source: "manual_start", target: "server_check" },
              { source: "server_check", target: "report" },
            ],
          },
          warnings: [],
          validation: { ok: true, errors: [], warnings: [] },
          risk: { level: "safe", items: [] },
          requirements: ["Run on demand", "Collect health metrics", "Send Telegram summary"],
          assumptions: ["Web-01 is the first pilot server"],
          questions: [],
          patch_summary: "Creates a manual health report pipeline.",
          resource_plan: {
            servers: [{ id: "1", name: "Web-01", reason: "Pilot server" }],
            mcp_servers: [],
            skills: [],
            missing: [],
            notes: [],
          },
          suggested_next_actions: ["Validate dry-run", "Create pipeline"],
          confidence: 0.84,
          selected_template: {
            slug: "pilot-health-report",
            name: "Pilot: Health Report",
            source: "visual_fixture",
          },
          template_recommendations: [
            {
              slug: "pilot-health-report",
              name: "Pilot: Health Report",
              description: "Health check and report",
              node_types: ["trigger/manual", "ops/server_snapshot", "output/report"],
            },
          ],
        },
      },
    },
  ];

  const marsWorkspace = {
    id: 31,
    name: "WebTerm workspace",
    root_path: "C:/WebTrerm",
    read_allow_roots: ["C:/WebTrerm"],
    write_allow_roots: ["C:/WebTrerm"],
    deny_globs: ["**/.env", "**/node_modules/**"],
    enabled: true,
    created_at: FIXED_DATE,
    updated_at: FIXED_DATE,
  };
  const marsSession = {
    id: 41,
    workspace_id: marsWorkspace.id,
    workspace: marsWorkspace,
    task_brief: "Create a compact deployment checklist",
    answers: {},
    interview_questions: [
      {
        id: "verification",
        question: "How should MARS verify the result?",
        kind: "multi_choice_text",
        options: ["npm run build", "Playwright smoke"],
        required: true,
      },
    ],
    selected_skill_slugs: [],
    generated_plan: "# Execution plan\n\n1. Build the checklist.\n2. Run verification.",
    status: "interview",
    created_at: FIXED_DATE,
    updated_at: FIXED_DATE,
  };
  const marsRun = {
    id: 51,
    session_id: marsSession.id,
    workspace_id: marsWorkspace.id,
    workspace: marsWorkspace,
    cli_roles: {},
    status: "completed",
    runtime_control: {},
    allow_dirty: false,
    final_report: "Checklist generated and verified.",
    codex_summary: "Updated project checklist.",
    gemini_review: "No blocking issues.",
    test_output: "npm run build passed",
    git_before: "abc123",
    git_after: "def456",
    started_at: FIXED_DATE,
    completed_at: FIXED_DATE,
    created_at: FIXED_DATE,
  };
  const marsProjects = [
    {
      session: marsSession,
      latest_run: marsRun,
      run_count: 1,
      recommended_skills: [],
    },
  ];

  const agentRunPlanTasks = [
    {
      id: 1,
      name: "Inspect service health",
      description: "Collect systemd and disk status before applying changes.",
      status: "done",
      thought: "Baseline captured.",
      iterations: [],
      result: "nginx is active, disk usage is below threshold.",
      error: "",
      orchestrator_decision: null,
      started_at: FIXED_DATE,
      completed_at: FIXED_DATE,
    },
    {
      id: 2,
      name: "Apply patch window checks",
      description: "Verify the maintenance window and prepare the package update.",
      status: "running",
      thought: "Checking package locks and pending services.",
      iterations: [
        {
          iteration: 1,
          thought: "Check package lock state.",
          action: "run_command",
          args: { command: "apt list --upgradable" },
          observation: "3 packages can be upgraded.",
          timestamp: FIXED_DATE,
        },
      ],
      result: "",
      error: "",
      orchestrator_decision: null,
      started_at: FIXED_DATE,
      completed_at: null,
    },
    {
      id: 3,
      name: "Write completion report",
      description: "Summarize commands, risks, and next verification steps.",
      status: "pending",
      thought: "",
      iterations: [],
      result: "",
      error: "",
      orchestrator_decision: null,
      started_at: null,
      completed_at: null,
    },
  ];

  const agentRunEvents = [
    {
      id: 1,
      run_id: 901,
      event_type: "agent_background_started",
      task_id: null,
      message: "Agent run started.",
      payload: { server: "Web-01" },
      created_at: FIXED_DATE,
      severity: "info",
      source: "agent",
      title: "Фоновый запуск начат",
      summary: "Worker начал выполнение агента.",
      phase: "starting",
      category: "system",
      important: true,
    },
    {
      id: 2,
      run_id: 901,
      event_type: "agent_task_start",
      task_id: 2,
      message: "Running package readiness checks.",
      payload: { command: "apt list --upgradable" },
      created_at: FIXED_DATE,
      severity: "info",
      source: "task",
      title: "Apply patch window checks",
      summary: "Running package readiness checks.",
      phase: "executing",
      category: "task",
      important: true,
    },
    {
      id: 3,
      run_id: 901,
      event_type: "agent_task_failed",
      task_id: 2,
      message: "Package lock check returned a warning exit code.",
      payload: { command: "apt-get check", exit_code: 100 },
      created_at: FIXED_DATE,
      severity: "critical",
      source: "command",
      title: "Package lock check failed",
      summary: "apt-get check вернул код 100, rollout требует ручной проверки.",
      phase: "executing",
      category: "task",
      important: true,
    },
  ];

  const agentRunLogs = [
    {
      id: "cmd-1",
      index: 1,
      kind: "command",
      title: "systemctl is-active nginx",
      command: "systemctl is-active nginx",
      stdout: "active\n",
      stderr: "",
      exit_code: 0,
      duration_ms: 320,
      status: "completed",
      severity: "success",
      timestamp: FIXED_DATE,
    },
    {
      id: "cmd-2",
      index: 2,
      kind: "command",
      title: "apt-get check",
      command: "apt-get check",
      stdout: "",
      stderr: "E: dpkg was interrupted, you must manually run 'dpkg --configure -a'\n",
      exit_code: 100,
      duration_ms: 840,
      status: "failed",
      severity: "critical",
      timestamp: FIXED_DATE,
    },
  ];

  const agentRunSteps = agentRunPlanTasks.map((task, index) => ({
    id: String(task.id),
    index: index + 1,
    title: task.name,
    description: task.description,
    command: task.iterations[0]?.action || "",
    status: task.status,
    severity: task.status === "done" ? "success" : task.status === "failed" ? "critical" : "info",
    status_label: task.status === "done" ? "Завершено" : task.status === "running" ? "Выполняется" : "Ожидает",
    duration_ms: task.status === "done" ? 1250 : 0,
    details: task.result || task.thought,
    error: task.error,
    started_at: task.started_at,
    completed_at: task.completed_at,
  }));

  const agentRunReport = {
    success: true,
    schema_version: 1,
    run: {
      id: 901,
      agent_id: 202,
      agent_name: "Patch Rollout",
      agent_type: "custom",
      agent_mode: "multi",
      server_name: "Web-01",
      server_id: 1,
      status: "running",
      duration_ms: 125000,
      started_at: FIXED_DATE,
      completed_at: null,
      total_iterations: 4,
      connected_servers: [{ server_id: 1, server_name: "Web-01" }],
      pending_question: "",
      dispatch: {
        id: 701,
        run_id: 901,
        dispatch_kind: "launch",
        status: "queued",
        server_ids: [1],
        plan_only: false,
        queued_at: FIXED_DATE,
        claimed_at: null,
        heartbeat_at: null,
        lease_expires_at: null,
        completed_at: null,
        claimed_by: "",
        attempt_count: 0,
        error: "",
        metadata: {},
      },
    },
    report_state: {
      phase: "executing",
      report_ready: false,
      artifacts_ready: false,
      is_terminal: false,
      headline: "Агент выполняет проверки",
      description:
        "Идёт сбор данных, выполнение команд и накопление доказательств для финального отчёта. Уже есть проблемные сигналы: 2. Dispatch ждёт в очереди 2m 5s. Статус worker: missing.",
      current_step: "Execution worker не принимает запуск",
      next_expected: "Запустите worker: python manage.py run_agent_execution_plane --worker-key default",
      progress: 62,
      execution_state: {
        status: "worker_missing",
        severity: "warning",
        title: "Execution worker не принимает запуск",
        description: "Dispatch ждёт в очереди 2m 5s. Статус worker: missing.",
        next_action: "Запустите worker: python manage.py run_agent_execution_plane --worker-key default",
        dispatch: {
          id: 701,
          run_id: 901,
          dispatch_kind: "launch",
          status: "queued",
          server_ids: [1],
          plan_only: false,
          queued_at: FIXED_DATE,
          claimed_at: null,
          heartbeat_at: null,
          lease_expires_at: null,
          completed_at: null,
          claimed_by: "",
          attempt_count: 0,
          error: "",
          metadata: {},
        },
        worker: {
          worker_kind: "agent_execution",
          worker_key: "",
          status: "missing",
          is_stale: true,
          hostname: "",
          pid: null,
          command: "",
          heartbeat_at: null,
          heartbeat_age_ms: null,
          lease_expires_at: null,
          last_started_at: null,
          last_stopped_at: null,
          last_cycle_started_at: null,
          last_cycle_finished_at: null,
          last_summary: {},
          last_error: "",
        },
        queued_age_ms: 125000,
        queued_for: "2m 5s",
        heartbeat_age_ms: null,
        heartbeat_age: "—",
        lease_expired: false,
        worker_ready: false,
      },
    },
    artifact_state: {
      ready: false,
      title: "Артефакты ещё не готовы",
      description: "Артефакты появятся только после того, как агент сохранит финальный markdown-отчёт.",
      empty_title: "Артефакты появятся после финального отчёта",
      empty_description: "После выполнения агент соберёт итоговый markdown-отчёт.",
    },
    report: {
      schema_version: 1,
      title: "Patch Rollout",
      subtitle:
        "Идёт сбор данных, выполнение команд и накопление доказательств для финального отчёта. Уже есть проблемные сигналы: 2. Dispatch ждёт в очереди 2m 5s. Статус worker: missing.",
      status: "running",
      status_label: "Выполняется",
      severity: "high",
      summary:
        "Идёт сбор данных, выполнение команд и накопление доказательств для финального отчёта. Уже есть проблемные сигналы: 2. Dispatch ждёт в очереди 2m 5s. Статус worker: missing.",
      root_cause: null,
      markdown: "",
      meta: {
        server: "Web-01",
        window: FIXED_DATE,
        analysis_duration: "2m 5s",
        finished_at: null,
        started_at: FIXED_DATE,
      },
      kpis: [
        { id: "status", label: "Статус", value: "Выполняется", hint: "running", severity: "info" },
        { id: "duration", label: "Длительность", value: "2m 5s", hint: "runtime", severity: "info" },
        { id: "scope", label: "Серверы", value: "1", hint: "Web-01", severity: "info" },
        { id: "signals", label: "Сигналы", value: "3", hint: "1 проблемный", severity: "high" },
      ],
      findings: [
        {
          id: "md-finding-1",
          title: "Web service живой, базовое состояние в норме.",
          description: "",
          severity: "info",
          source: "report",
        },
        {
          id: "log-cmd-2",
          title: "Команда завершилась с кодом 100",
          description: "apt-get check",
          severity: "critical",
          source: "command",
        },
      ],
      risks: [
        {
          id: "risk-log-cmd-2",
          title: "Команда завершилась с кодом 100",
          description: "apt-get check",
          severity: "critical",
          source: "command",
        },
      ],
      recommendations: [
        {
          id: "md-action-1",
          priority: "P1",
          title: "Проверить dpkg --configure -a на Web-01.",
          description: "",
          owner: "Оператор",
          done: false,
        },
        {
          id: "md-action-2",
          priority: "P2",
          title: "Повторить apt-get check перед продолжением rollout.",
          description: "",
          owner: "Оператор",
          done: false,
        },
      ],
    },
    events: agentRunEvents,
    logs: agentRunLogs,
    agent_steps: agentRunSteps,
    artifacts: [],
    generated_at: FIXED_DATE,
  };

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
      effective_permissions: { servers: true, settings: true, orchestrator: true },
      permission_sources: { servers: "profile", settings: "profile", orchestrator: "profile" },
      group_permission_sources: { servers: [{ group_id: 11, group_name: "Core", allowed: true }] },
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
      effective_permissions: { servers: true, settings: false, orchestrator: false },
      permission_sources: { servers: "group", settings: "direct", orchestrator: "profile" },
      group_permission_sources: { servers: [{ group_id: 11, group_name: "Core", allowed: true }] },
    },
  ];

  const accessGroups = [
    {
      id: 11,
      name: "Core",
      members: [
        { id: 1, username: "admin" },
        { id: 2, username: "operator" },
      ],
      member_count: 2,
      explicit_permissions: { servers: true },
    },
  ];

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

  const accessGroupPermissions = [
    {
      id: 21,
      group_id: 11,
      group_name: "Core",
      feature: "servers",
      feature_display: "Servers",
      allowed: true,
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
            ...group,
            server_count: servers.filter((server) => server.group_id === group.id).length,
          })),
          stats: { owned: servers.length, shared: 0, total: servers.length },
          recent_activity: [],
        });
      }

      if (req.path === "/servers/api/1/files/" && req.method === "GET") {
        return json({
          success: true,
          path: "/var/www/webterm",
          home_path: "/home/deploy",
          parent_path: "/var/www",
          entries: [
            {
              path: "/var/www/webterm/.env",
              name: ".env",
              kind: "file",
              is_dir: false,
              is_symlink: false,
              size: 512,
              permissions: "0600",
              modified_at: 1772326800,
            },
            {
              path: "/var/www/webterm/releases",
              name: "releases",
              kind: "dir",
              is_dir: true,
              is_symlink: false,
              size: 0,
              permissions: "0755",
              modified_at: 1772326800,
            },
            {
              path: "/var/www/webterm/nginx.conf",
              name: "nginx.conf",
              kind: "file",
              is_dir: false,
              is_symlink: false,
              size: 2048,
              permissions: "0644",
              modified_at: 1772326800,
            },
          ],
        });
      }

      if (req.path === "/api/mars/workspaces/" && req.method === "GET") {
        return json({ workspaces: [marsWorkspace] });
      }

      if (req.path === "/api/mars/projects/" && req.method === "GET") {
        return json({ projects: marsProjects });
      }

      if (req.path.match(/^\/api\/mars\/sessions\/\d+\/$/) && req.method === "GET") {
        return json({ session: marsSession, recommended_skills: [] });
      }

      if (req.path.match(/^\/api\/mars\/runs\/\d+\/$/) && req.method === "GET") {
        return json({ run: marsRun });
      }

      if (req.path.match(/^\/api\/mars\/runs\/\d+\/events\/$/) && req.method === "GET") {
        return json({
          events: [
            {
              id: 1,
              run_id: marsRun.id,
              event_type: "tests_completed",
              message: "Verification passed.",
              payload: {},
              created_at: FIXED_DATE,
            },
          ],
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
        return json({
          success: true,
          agents: options.agentList === "empty" ? [] : serverAgents,
          worker_states: options.agentList === "empty" ? {} : agentWorkerStates,
          runtime_overview: options.agentList === "empty" ? undefined : agentRuntimeOverview,
        });
      }

      if (req.path === "/servers/api/agents/dashboard/" && req.method === "GET") {
        return json({ success: true, active: [], recent: [] });
      }

      if (req.path === "/servers/api/agents/runs/901/report/" && req.method === "GET") {
        return json(agentRunReport);
      }

      if (req.path === "/servers/api/agents/runs/901/" && req.method === "GET") {
        return json({
          success: true,
          run: {
            id: 901,
            agent_id: 202,
            agent_name: "Patch Rollout",
            agent_type: "custom",
            agent_mode: "multi",
            server_name: "Web-01",
            status: "running",
            ai_analysis: "",
            commands_output: [],
            duration_ms: 125000,
            started_at: FIXED_DATE,
            completed_at: null,
            iterations_log: [],
            tool_calls: [],
            total_iterations: 4,
            connected_servers: [{ server_id: 1, server_name: "Web-01" }],
            final_report: "",
            pending_question: "",
            plan_tasks: agentRunPlanTasks,
            orchestrator_log: [],
          },
        });
      }

      if (req.path === "/servers/api/agents/runs/901/log/" && req.method === "GET") {
        return json({
          success: true,
          iterations_log: [],
          tool_calls: [],
          total_iterations: 4,
          status: "running",
          pending_question: "",
          plan_tasks: agentRunPlanTasks,
        });
      }

      if (req.path === "/servers/api/agents/runs/901/events/" && req.method === "GET") {
        return json({
          success: true,
          events: agentRunEvents,
        });
      }

      if (req.path === "/api/studio/pipelines/" && req.method === "GET") {
        return json(pipelines);
      }

      if (req.path.match(/^\/api\/studio\/pipelines\/\d+\/$/) && req.method === "GET") {
        const id = Number(req.path.split("/")[4]);
        return json(pipelines.find((pipeline) => pipeline.id === id) || pipelines[0]);
      }

      if ((req.path === "/api/studio/assistant/drafts/" || req.path === "/api/studio/pipeline-drafts/") && req.method === "GET") {
        return json(draftSessions);
      }

      if (
        (req.path.match(/^\/api\/studio\/assistant\/drafts\/\d+\/$/) ||
          req.path.match(/^\/api\/studio\/pipeline-drafts\/\d+\/$/)) &&
        req.method === "GET"
      ) {
        const id = Number(req.path.match(/\/(\d+)\/$/)?.[1] || 0);
        return json(draftSessions.find((draft) => draft.id === id) || draftSessions[0]);
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
          trigger_id: null,
          entry_node_id: String(req.body?.entry_node_id || ""),
          trigger_type: "manual",
          trigger_name: "Manual start",
          trigger_node_id: String(req.body?.entry_node_id || ""),
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
        return json([
          {
            id: 301,
            name: "Patch review",
            description: "Reviews package updates before a rollout.",
            icon: "P",
            system_prompt: "Review patch plans before execution.",
            instructions: "Check risk and report blockers.",
            model: "gpt-5.2",
            max_iterations: 8,
            allowed_tools: ["read_console", "analyze_output", "report"],
            sudo_policy: "disabled",
            skill_slugs: ["patch-review"],
            skills: [],
            mcp_servers: [{ id: 501, name: "GitHub MCP", transport: "stdio" }],
            server_scope: [{ id: 1, name: "Web-01" }],
            owner_username: "admin",
            is_owner: true,
            can_edit: true,
            is_shared: true,
            shared_user_ids: [2],
            created_at: FIXED_DATE,
            updated_at: FIXED_DATE,
          },
          {
            id: 302,
            name: "Incident responder",
            description: "Runs first-pass diagnostics during incidents.",
            icon: "I",
            system_prompt: "Diagnose incidents without destructive changes.",
            instructions: "Collect context, explain findings, and wait for approval.",
            model: "claude-4.5-sonnet",
            max_iterations: 12,
            allowed_tools: ["ssh_execute", "read_console", "report", "ask_user"],
            sudo_policy: "ask",
            skill_slugs: [],
            skills: [],
            mcp_servers: [],
            server_scope: [],
            owner_username: "ops-lead",
            is_owner: false,
            can_edit: false,
            is_shared: false,
            shared_user_ids: [],
            created_at: FIXED_DATE,
            updated_at: FIXED_DATE,
          },
        ]);
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

      if (req.path === "/api/access/group-permissions/" && req.method === "GET") {
        return json({
          permissions: accessGroupPermissions,
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
