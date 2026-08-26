import type { BackgroundWorkerStateRecord } from "@/api/server-memory";
import type { AgentRunReportSeverity } from "@/api/agent-report-types";
import type { ProviderBinding } from "@/api/aiProviders";

export type * from "@/api/agent-report-types";
export type * from "@/api/agent-report-v2-types";

// ---------------------------------------------------------------------------
// Agents API (mini + full)
// ---------------------------------------------------------------------------

export type AgentScheduleMode = "manual" | "interval" | "daily" | "weekly" | "monthly" | "once";

export interface AgentScheduleConfig {
  mode: AgentScheduleMode;
  timezone?: string;
  interval_minutes?: number;
  time?: string;
  weekdays?: number[];
  day_of_month?: number;
  run_at?: string;
}

export interface AgentInputArtifact {
  kind: "document" | "task_list" | "script";
  name: string;
  content: string;
  run_hint?: string;
  tasks?: Array<{ title: string; details?: string; done?: boolean }>;
  source_name?: string;
  size_bytes?: number;
}

export interface AgentReportDelivery {
  telegram?: {
    enabled: boolean;
    chat_id?: string;
    format?: string;
    include_link?: boolean;
  };
}

export interface AgentExecutionReadiness {
  required: boolean;
  ready: boolean;
  status: string;
  severity: AgentRunReportSeverity;
  title: string;
  description: string;
  next_action: string;
  supervisor_action?: string;
  commands?: {
    execution_worker?: string;
    scheduled_agents_worker?: string;
    ops_supervisor?: string;
  };
  worker: BackgroundWorkerStateRecord | null;
}

export interface AgentItem {
  id: number;
  name: string;
  mode: "mini" | "full" | "multi";
  mode_display: string;
  agent_type: string;
  agent_type_display: string;
  server_count: number;
  server_ids: number[];
  server_names: string[];
  schedule_minutes: number;
  schedule_config: AgentScheduleConfig;
  is_enabled: boolean;
  commands: string[];
  ai_prompt: string;
  goal: string;
  system_prompt: string;
  max_iterations: number;
  allow_multi_server: boolean;
  tools_config: Record<string, boolean>;
  sudo_policy: "disabled" | "ask" | "approved";
  stop_conditions: string[];
  skill_slugs: string[];
  input_artifacts: AgentInputArtifact[];
  report_delivery: AgentReportDelivery;
  session_timeout_seconds: number;
  max_connections: number;
  provider_binding?: ProviderBinding;
  last_run_at: string | null;
  last_run_status: string | null;
  last_run_id: number | null;
  active_run_id: number | null;
  active_run_status?: string | null;
  active_run_started_at?: string | null;
  active_run_iterations?: number;
  active_run_server_name?: string | null;
  active_run_pending_question?: string;
  execution_readiness?: AgentExecutionReadiness;
  schedule_state?: "manual" | "paused" | "due" | "scheduled";
  due_now?: boolean;
  next_due_at?: string | null;
  next_due_in_seconds?: number | null;
}

export interface AgentScheduleOverviewSummary {
  total_scheduled: number;
  enabled: number;
  paused: number;
  due_now: number;
  active_runs: number;
}

export interface AgentScheduleDispatchSummary {
  scanned: number;
  due: number;
  launched_agents: number;
  runs_created: number;
  background_runs: number;
  mini_runs: number;
  skipped: number;
  skip_reasons: Record<string, number>;
  errors: Array<{ agent_id: number; agent_name: string; error: string }>;
}

export interface AgentRunDispatchRecord {
  id: number;
  run_id: number;
  dispatch_kind: string;
  status: string;
  server_ids: number[];
  plan_only: boolean;
  queued_at: string | null;
  claimed_at: string | null;
  heartbeat_at: string | null;
  lease_expires_at: string | null;
  completed_at: string | null;
  claimed_by: string;
  attempt_count: number;
  error: string;
  metadata: Record<string, unknown>;
}

export interface AgentTemplate {
  type: string;
  name: string;
  mode: "mini" | "full" | "multi";
  commands: string[];
  ai_prompt: string;
  command_count: number;
  goal?: string;
  system_prompt?: string;
  allow_multi_server?: boolean;
  stop_conditions?: string[];
}

export interface AgentRunResult {
  run_id: number;
  server_name: string;
  status: string;
  ai_analysis: string;
  duration_ms: number;
  commands_output: Array<{ cmd: string; stdout: string; stderr: string; exit_code: number; duration_ms: number }>;
  total_iterations?: number;
  final_report?: string;
  dispatch?: AgentRunDispatchRecord | null;
}

export interface AgentRunDetail {
  id: number;
  agent_id: number;
  agent_name: string;
  agent_type: string;
  agent_mode: string;
  server_name: string;
  status: string;
  ai_analysis: string;
  commands_output: Array<{ cmd: string; stdout: string; stderr: string; exit_code: number; duration_ms: number }>;
  duration_ms: number;
  started_at: string;
  completed_at: string | null;
  iterations_log: Array<{
    iteration: number;
    thought: string;
    action: string | null;
    args: Record<string, unknown>;
    observation: string;
    timestamp: string;
  }>;
  tool_calls: Array<{
    tool: string;
    args: Record<string, unknown>;
    result: string;
    duration_ms: number;
    timestamp: string;
  }>;
  total_iterations: number;
  connected_servers: Array<{ server_id: number; server_name: string }>;
  final_report: string;
  pending_question: string;
  plan_tasks: Array<{
    id: number;
    name: string;
    description: string;
    status: "pending" | "running" | "done" | "failed" | "skipped";
    thought: string;
    iterations: Array<{
      iteration: number;
      thought: string;
      action: string | null;
      args: Record<string, unknown>;
      observation: string;
      timestamp: string;
    }>;
    result: string;
    error: string;
    orchestrator_decision: { action: string; reason?: string; message?: string } | null;
    started_at: string | null;
    completed_at: string | null;
  }>;
  orchestrator_log: Array<{ role: string; content: string; timestamp: string }>;
  dispatch?: AgentRunDispatchRecord | null;
}

export interface AgentRunEventItem {
  id: number;
  run_id: number;
  event_type: string;
  task_id: number | null;
  message: string;
  payload: Record<string, unknown>;
  created_at: string | null;
}


export interface AgentRuntimeOverviewIssue {
  id: string;
  severity: AgentRunReportSeverity;
  title: string;
  description: string;
  next_action: string;
}

export interface AgentRuntimeRunItem {
  run_id: number;
  agent_id: number | null;
  agent_name: string;
  agent_mode: string;
  server_id: number | null;
  server_name: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  age_seconds: number | null;
  duration_ms: number;
  pending_question: string;
  is_stale_candidate: boolean;
  dispatch: AgentRunDispatchRecord | null;
}

export interface AgentRuntimeDispatchItem {
  dispatch_id: number;
  run_id: number;
  agent_id: number;
  agent_name: string;
  agent_mode: string;
  server_id: number | null;
  server_name: string;
  dispatch_kind: string;
  status: string;
  server_ids: number[];
  queued_at: string | null;
  claimed_at: string | null;
  heartbeat_at: string | null;
  lease_expires_at: string | null;
  queued_age_seconds: number | null;
  lease_seconds_left: number | null;
  claimed_by: string;
  attempt_count: number;
  error: string;
}

export interface AgentRuntimeScheduledItem {
  agent_id: number;
  agent_name: string;
  agent_mode: string;
  server_count: number;
  server_names: string[];
  schedule_minutes: number;
  schedule_config: AgentScheduleConfig;
  last_run_at: string | null;
  next_due_at: string | null;
  due_age_seconds: number;
  active_run_id: number | null;
  active_run_status: string;
}

export interface AgentRuntimeOverview {
  status: "idle" | "active" | "needs_attention" | string;
  severity: AgentRunReportSeverity;
  summary: {
    configured_agents: number;
    active_runs: number;
    pending_runs: number;
    running_runs: number;
    waiting_runs: number;
    queued_dispatches: number;
    claimed_dispatches: number;
    scheduled_agents: number;
    scheduled_due_now: number;
    issues: number;
  };
  queue: {
    runs: Record<string, number>;
    dispatches: Record<string, number>;
  };
  schedule: {
    total_scheduled: number;
    enabled: number;
    paused: number;
    due_now: number;
    worker_ready: boolean;
  };
  workers: Record<string, BackgroundWorkerStateRecord>;
  execution_readiness: AgentExecutionReadiness;
  items?: {
    active_runs: AgentRuntimeRunItem[];
    queued_dispatches: AgentRuntimeDispatchItem[];
    scheduled_due: AgentRuntimeScheduledItem[];
    stale_candidates: AgentRuntimeRunItem[];
  };
  issues: AgentRuntimeOverviewIssue[];
  commands: {
    execution_worker: string;
    scheduled_agents_worker: string;
    ops_supervisor?: string;
  };
  generated_at: string;
}

export interface AgentListResponse {
  success: boolean;
  agents: AgentItem[];
  worker_states?: Record<string, BackgroundWorkerStateRecord>;
  runtime_overview?: AgentRuntimeOverview;
}

export interface DashboardRunItem {
  id: number;
  agent_id: number;
  agent_name: string;
  agent_mode: "mini" | "full" | "multi";
  agent_type: string;
  server_name: string;
  server_id: number;
  status: string;
  total_iterations: number;
  duration_ms: number;
  started_at: string;
  completed_at: string | null;
  pending_question: string;
  connected_servers: Array<{ server_id: number; server_name: string }>;
  ai_analysis: string;
  final_report: string;
  commands_output: Array<{ cmd: string; stdout: string; stderr: string; exit_code: number; duration_ms: number }>;
}
