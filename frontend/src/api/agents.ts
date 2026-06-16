import { apiFetch } from "@/lib/api";
import type { BackgroundWorkerStateRecord } from "@/api/server-memory";

// ---------------------------------------------------------------------------
// Agents API (mini + full)
// ---------------------------------------------------------------------------

export interface AgentItem {
  id: number;
  name: string;
  mode: "mini" | "full" | "multi";
  mode_display: string;
  agent_type: string;
  agent_type_display: string;
  server_count: number;
  server_names: string[];
  schedule_minutes: number;
  is_enabled: boolean;
  commands: string[];
  ai_prompt: string;
  goal: string;
  system_prompt: string;
  max_iterations: number;
  allow_multi_server: boolean;
  last_run_at: string | null;
  last_run_status: string | null;
  last_run_id: number | null;
  active_run_id: number | null;
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

export async function fetchAgents(mode?: string) {
  const url = mode ? `/servers/api/agents/?mode=${mode}` : "/servers/api/agents/";
  return apiFetch<{ success: boolean; agents: AgentItem[] }>(url);
}

export async function fetchAgentScheduleOverview(limit = 40) {
  return apiFetch<{
    success: boolean;
    summary: AgentScheduleOverviewSummary;
    scheduled_agents: AgentItem[];
    execution_plane: BackgroundWorkerStateRecord;
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
  goal?: string;
  system_prompt?: string;
  max_iterations?: number;
  allow_multi_server?: boolean;
  tools_config?: Record<string, boolean>;
  stop_conditions?: string[];
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
