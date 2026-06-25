import { apiFetch } from "@/lib/api";
import type { BackgroundWorkerStateRecord } from "@/api/server-memory";

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
  last_run_at: string | null;
  last_run_status: string | null;
  last_run_id: number | null;
  active_run_id: number | null;
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

export type AgentRunReportSeverity = "success" | "info" | "warning" | "high" | "critical" | "fatal";
export type AgentRunReportPhase =
  | "queued"
  | "starting"
  | "planning"
  | "plan_review"
  | "executing"
  | "synthesizing"
  | "delivery"
  | "waiting"
  | "ready"
  | "failed"
  | "stopped"
  | "activity"
  | (string & {});

export interface AgentRunReportState {
  phase: AgentRunReportPhase;
  report_ready: boolean;
  artifacts_ready: boolean;
  is_terminal: boolean;
  headline: string;
  description: string;
  current_step: string;
  next_expected: string;
  progress: number;
  execution_state?: AgentRunExecutionState;
}

export interface AgentRunArtifactState {
  ready: boolean;
  title: string;
  description: string;
  empty_title: string;
  empty_description: string;
  bundle_ready?: boolean;
  bundle_download_url?: string;
  artifact_count?: number;
  total_size_bytes?: number;
  total_size_label?: string;
  manifest_ready?: boolean;
  manifest_name?: string;
}

export interface AgentRunExecutionWorkerState {
  worker_kind: string;
  worker_key: string;
  status: string;
  is_stale: boolean;
  hostname: string;
  pid: number | null;
  command?: string;
  heartbeat_at: string | null;
  heartbeat_age_ms?: number | null;
  lease_expires_at: string | null;
  last_started_at: string | null;
  last_stopped_at: string | null;
  last_cycle_started_at: string | null;
  last_cycle_finished_at: string | null;
  last_summary: Record<string, unknown>;
  last_error: string;
}

export interface AgentRunExecutionState {
  status: string;
  severity: AgentRunReportSeverity;
  title: string;
  description: string;
  next_action: string;
  dispatch: AgentRunDispatchRecord | null;
  worker: AgentRunExecutionWorkerState;
  queued_age_ms: number | null;
  queued_for: string;
  heartbeat_age_ms: number | null;
  heartbeat_age: string;
  runtime_age_ms: number | null;
  runtime_age: string;
  stale_after_ms: number;
  stale_after: string;
  is_stale_candidate: boolean;
  can_cleanup: boolean;
  lease_expired: boolean;
  worker_ready: boolean;
  commands?: {
    execution_worker?: string;
    ops_supervisor?: string;
  };
}

export interface AgentRunReportKpi {
  id: string;
  label: string;
  value: string;
  hint: string;
  severity: AgentRunReportSeverity;
}

export interface AgentRunReportFinding {
  id: string;
  title: string;
  description: string;
  severity: AgentRunReportSeverity;
  source?: string;
}

export interface AgentRunReportRecommendation {
  id: string;
  priority: "P0" | "P1" | "P2" | string;
  title: string;
  description: string;
  owner: string;
  done: boolean;
}

export interface AgentRunReportBody {
  schema_version: number;
  title: string;
  subtitle: string;
  status: string;
  status_label: string;
  severity: AgentRunReportSeverity;
  summary: string;
  root_cause: string | null;
  markdown: string;
  meta: {
    server: string;
    window: string;
    analysis_duration: string;
    finished_at: string | null;
    started_at: string | null;
  };
  kpis: AgentRunReportKpi[];
  findings: AgentRunReportFinding[];
  risks: AgentRunReportFinding[];
  recommendations: AgentRunReportRecommendation[];
}

export interface AgentRunReportEvent extends AgentRunEventItem {
  severity: AgentRunReportSeverity;
  source: string;
  title: string;
  summary: string;
  phase: AgentRunReportPhase;
  category: string;
  important: boolean;
}

export interface AgentRunReportEventSummary {
  total: number;
  important: number;
  problems: number;
  debug: number;
  categories: Record<string, number>;
  severities: Record<string, number>;
  latest: AgentRunReportEvent | null;
  latest_important: AgentRunReportEvent | null;
}

export interface AgentRunReportEventGroup {
  phase: AgentRunReportPhase;
  label: string;
  count: number;
  important: number;
  problems: number;
  first_at: string | null;
  last_at: string | null;
  events: AgentRunReportEvent[];
}

export interface AgentRunReportDeliveryState {
  enabled: boolean;
  channels: string[];
  channel: string;
  target: string;
  status: string;
  severity: AgentRunReportSeverity;
  label: string;
  title: string;
  description: string;
  next_action: string;
  updated_at: string | null;
  event: AgentRunReportEvent | null;
}

export interface AgentRunReportRun {
  id: number;
  agent_id: number;
  agent_name: string;
  agent_type: string;
  agent_mode: string;
  server_name: string;
  server_id: number | null;
  status: string;
  duration_ms: number;
  started_at: string | null;
  completed_at: string | null;
  total_iterations: number;
  connected_servers: Array<{ server_id: number; server_name: string }>;
  pending_question: string;
  dispatch?: AgentRunDispatchRecord | null;
}

export interface AgentRunReportLog {
  id: string;
  index: number;
  kind: string;
  title: string;
  command: string;
  stdout: string;
  stderr: string;
  exit_code: number;
  duration_ms: number;
  status: string;
  severity: AgentRunReportSeverity;
  timestamp: string | null;
}

export interface AgentRunReportStep {
  id: string;
  index: number;
  title: string;
  description: string;
  command: string;
  status: string;
  severity: AgentRunReportSeverity;
  status_label: string;
  duration_ms: number;
  details: string;
  error: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface AgentRunReportArtifact {
  id: string;
  artifact_id: number | null;
  name: string;
  type: string;
  description: string;
  size_bytes: number;
  original_size_bytes?: number;
  size_label: string;
  created_at: string | null;
  download_kind: "inline" | string;
  download_url: string;
  content_type: string;
  content: string;
  truncated: boolean;
  checksum_sha256?: string;
  metadata?: Record<string, unknown>;
}

export interface AgentRunReportResponse {
  success: boolean;
  schema_version: number;
  run: AgentRunReportRun;
  report: AgentRunReportBody;
  report_state: AgentRunReportState;
  artifact_state: AgentRunArtifactState;
  delivery_state?: AgentRunReportDeliveryState;
  event_summary?: AgentRunReportEventSummary;
  event_groups?: AgentRunReportEventGroup[];
  events: AgentRunReportEvent[];
  logs: AgentRunReportLog[];
  agent_steps: AgentRunReportStep[];
  artifacts: AgentRunReportArtifact[];
  generated_at: string;
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

export async function fetchAgents(mode?: string) {
  const url = mode ? `/servers/api/agents/?mode=${mode}` : "/servers/api/agents/";
  return apiFetch<AgentListResponse>(url);
}

export async function fetchAgentScheduleOverview(limit = 40) {
  return apiFetch<{
    success: boolean;
    summary: AgentScheduleOverviewSummary;
    scheduled_agents: AgentItem[];
    execution_plane: BackgroundWorkerStateRecord;
    scheduled_agents_worker?: BackgroundWorkerStateRecord;
    worker_states?: Record<string, BackgroundWorkerStateRecord>;
    runtime_overview?: AgentRuntimeOverview;
    execution_readiness: AgentExecutionReadiness;
    generated_at: string;
  }>(`/servers/api/agents/schedules/?limit=${limit}`);
}

export async function dispatchAgentSchedules(payload?: { limit?: number; agent_ids?: number[] }) {
  return apiFetch<{
    success: boolean;
    summary: AgentScheduleDispatchSummary;
    generated_at: string;
  }>("/servers/api/agents/schedules/dispatch/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
}

export async function cleanupStaleAgentRuns(payload?: { limit?: number }) {
  return apiFetch<{
    success: boolean;
    cleanup: {
      stale_seconds: number;
      scanned: number;
      cleaned: number;
      canceled_dispatches: number;
      runs: Array<{
        run_id: number;
        agent_id: number | null;
        agent_name: string;
        status: string;
        age_seconds: number | null;
        canceled_dispatches: number;
      }>;
      generated_at: string;
    };
    runtime_overview: AgentRuntimeOverview;
  }>("/servers/api/agents/runtime/cleanup-stale/", {
    method: "POST",
    body: JSON.stringify(payload || {}),
  });
}

export async function fetchAgentTemplates() {
  return apiFetch<{ success: boolean; templates: AgentTemplate[] }>("/servers/api/agents/templates/");
}

export async function createAgent(payload: {
  name?: string;
  mode?: string;
  agent_type: string;
  server_ids: number[];
  commands?: string[];
  ai_prompt?: string;
  schedule_minutes?: number;
  schedule_config?: AgentScheduleConfig;
  goal?: string;
  system_prompt?: string;
  max_iterations?: number;
  allow_multi_server?: boolean;
  tools_config?: Record<string, boolean>;
  sudo_policy?: "disabled" | "ask" | "approved";
  stop_conditions?: string[];
  skill_slugs?: string[];
  input_artifacts?: AgentInputArtifact[];
  report_delivery?: AgentReportDelivery;
  session_timeout_seconds?: number;
  max_connections?: number;
}) {
  return apiFetch<{ success: boolean; id: number }>("/servers/api/agents/create/", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function updateAgent(agentId: number, payload: Record<string, unknown>) {
  return apiFetch<{ success: boolean }>(`/servers/api/agents/${agentId}/update/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export async function deleteAgent(agentId: number) {
  return apiFetch<{ success: boolean }>(`/servers/api/agents/${agentId}/delete/`, { method: "POST" });
}

export async function runAgent(agentId: number, serverId?: number) {
  return apiFetch<{ success: boolean; runs: AgentRunResult[]; run_id?: number }>(`/servers/api/agents/${agentId}/run/`, {
    method: "POST",
    body: JSON.stringify(serverId ? { server_id: serverId } : {}),
  });
}

export async function stopAgent(agentId: number, runId?: number) {
  return apiFetch<{ success: boolean }>(`/servers/api/agents/${agentId}/stop/`, {
    method: "POST",
    body: JSON.stringify(runId ? { run_id: runId } : {}),
  });
}

export async function fetchAgentRuns(agentId: number, limit = 20) {
  return apiFetch<{ success: boolean; runs: AgentRunDetail[] }>(`/servers/api/agents/${agentId}/runs/?limit=${limit}`);
}

export async function fetchAgentRunDetail(runId: number) {
  return apiFetch<{ success: boolean; run: AgentRunDetail }>(`/servers/api/agents/runs/${runId}/`);
}

export async function fetchAgentRunReport(runId: number) {
  return apiFetch<AgentRunReportResponse>(`/servers/api/agents/runs/${runId}/report/`);
}

export async function retryAgentRunReportDelivery(runId: number) {
  return apiFetch<AgentRunReportResponse>(`/servers/api/agents/runs/${runId}/report/deliver/`, {
    method: "POST",
  });
}

export async function fetchAgentRunLog(runId: number) {
  return apiFetch<{
    success: boolean;
    iterations_log: AgentRunDetail["iterations_log"];
    tool_calls: AgentRunDetail["tool_calls"];
    total_iterations: number;
    status: string;
    pending_question: string;
    plan_tasks: AgentRunDetail["plan_tasks"];
  }>(`/servers/api/agents/runs/${runId}/log/`);
}

export async function fetchAgentRunEvents(runId: number, limit = 200, eventTypes?: string[]) {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  for (const eventType of eventTypes || []) {
    params.append("event_type", eventType);
  }
  return apiFetch<{
    success: boolean;
    events: AgentRunEventItem[];
    total: number;
  }>(`/servers/api/agents/runs/${runId}/events/?${params.toString()}`);
}

export async function replyToAgent(runId: number, answer: string) {
  return apiFetch<{ success: boolean }>(`/servers/api/agents/runs/${runId}/reply/`, {
    method: "POST",
    body: JSON.stringify({ answer }),
  });
}

export async function updatePipelineTask(
  runId: number,
  taskId: number,
  payload: { action: "update" | "delete"; name?: string; description?: string },
) {
  return apiFetch<{ success: boolean; plan_tasks: AgentRunDetail["plan_tasks"] }>(
    `/servers/api/agents/runs/${runId}/tasks/${taskId}/update/`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export async function aiRefinePipelineTask(
  runId: number,
  taskId: number,
  instruction: string,
) {
  return apiFetch<{
    success: boolean;
    task: AgentRunDetail["plan_tasks"][number];
    plan_tasks: AgentRunDetail["plan_tasks"];
    error?: string;
    raw?: string;
  }>(`/servers/api/agents/runs/${runId}/tasks/${taskId}/ai-refine/`, {
    method: "POST",
    body: JSON.stringify({ instruction }),
  });
}

export async function approvePipelinePlan(runId: number) {
  return apiFetch<{
    success: boolean;
    run_id: number;
    status: string;
    runs: Array<{
      run_id: number;
      server_name: string;
      status: string;
      ai_analysis: string;
      duration_ms: number;
      total_iterations: number;
      final_report: string;
    }>;
    error?: string;
  }>(`/servers/api/agents/runs/${runId}/approve-plan/`, { method: "POST" });
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

export async function fetchAgentDashboardRuns() {
  return apiFetch<{ success: boolean; active: DashboardRunItem[]; recent: DashboardRunItem[] }>("/servers/api/agents/dashboard/");
}
