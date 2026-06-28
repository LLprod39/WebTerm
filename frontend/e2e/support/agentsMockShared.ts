export const fullFeatures = {
  servers: true,
  dashboard: true,
  agents: true,
  studio: true,
  settings: true,
  orchestrator: true,
};

export const FIXED_DATE = "2026-03-01T08:00:00.000Z";

export type AgentMode = "mini" | "full" | "multi";

export type AgentItem = {
  id: number;
  name: string;
  mode: AgentMode;
  agent_type: string;
  agent_type_display: string;
  server_count: number;
  last_run_at: string | null;
  schedule_minutes: number;
  schedule_config?: Record<string, unknown>;
  max_iterations: number;
  goal: string;
  is_enabled?: boolean;
  sudo_policy?: "disabled" | "ask" | "approved";
  active_run_id: number | null;
  last_run_id: number | null;
  execution_readiness?: {
    required: boolean;
    ready: boolean;
    status: string;
    severity: "success" | "info" | "warning" | "high" | "critical" | "fatal";
    title: string;
    description: string;
    next_action: string;
    worker: Record<string, unknown> | null;
  };
};

export function workerState(overrides: Record<string, unknown> = {}) {
  return {
    worker_kind: "scheduled_agents",
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
    ...overrides,
  };
}

export function runtimeOverview(overrides: Record<string, unknown> = {}) {
  return {
    status: "idle",
    severity: "info",
    summary: {
      configured_agents: 0,
      active_runs: 0,
      pending_runs: 0,
      running_runs: 0,
      waiting_runs: 0,
      queued_dispatches: 0,
      claimed_dispatches: 0,
      scheduled_agents: 0,
      scheduled_due_now: 0,
      issues: 0,
    },
    queue: {
      runs: {},
      dispatches: {},
    },
    schedule: {
      total_scheduled: 0,
      enabled: 0,
      paused: 0,
      due_now: 0,
      worker_ready: false,
    },
    workers: {},
    execution_readiness: {
      required: true,
      ready: false,
      status: "missing",
      severity: "warning",
      title: "Execution worker не запущен",
      description: "Full/multi-агенты будут поставлены в очередь, но не начнут выполняться до запуска worker.",
      next_action: "python manage.py run_agent_execution_plane --worker-key default",
      worker: null,
    },
    issues: [],
    commands: {
      execution_worker: "python manage.py run_agent_execution_plane --worker-key default",
      scheduled_agents_worker: "python manage.py run_scheduled_agents --daemon --worker-key default",
      ops_supervisor: "python manage.py run_ops_supervisor --with-scheduled-agents --with-watchers",
    },
    items: {
      active_runs: [],
      queued_dispatches: [],
      scheduled_due: [],
      stale_candidates: [],
    },
    generated_at: FIXED_DATE,
    ...overrides,
  };
}

export function normalizeAgent(agent: AgentItem): AgentItem {
  return {
    schedule_config: { mode: "manual" },
    is_enabled: true,
    sudo_policy: "ask",
    ...agent,
  };
}
