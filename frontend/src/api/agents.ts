import { apiFetch, backendPath } from "@/lib/api";
import type { BackgroundWorkerStateRecord } from "@/api/server-memory";
import type { ProviderBinding } from "@/api/aiProviders";
import type {
  AgentExecutionReadiness,
  AgentInputArtifact,
  AgentItem,
  AgentListResponse,
  AgentReportDelivery,
  AgentRunDetail,
  AgentRunEventItem,
  AgentRunReportResponse,
  AgentRunResult,
  AgentRuntimeOverview,
  AgentScheduleConfig,
  AgentScheduleDispatchSummary,
  AgentScheduleOverviewSummary,
  AgentTemplate,
  DashboardRunItem,
  AgentRunActivityFilters,
  AgentRunActivityV2Response,
  AgentRunArtifactsV2Response,
  AgentRunCleanupStaleResponse,
  AgentRunReportDeliveryAttemptResponse,
  AgentRunReportEventFilters,
  AgentRunReportEventsV2Response,
  AgentRunReportV2Response,
} from "@/api/agent-types";

export type * from "@/api/agent-types";

// ---------------------------------------------------------------------------
// Agents API (mini + full)
// ---------------------------------------------------------------------------

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
  provider_binding?: ProviderBinding | Record<string, never>;
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

export async function runAgent(agentId: number, serverId?: number, providerBinding?: ProviderBinding) {
  // Launch only queues the run (execution plane). Keep a modest timeout so a
  // stuck HTTP thread cannot pin the UI for minutes.
  return apiFetch<{ success: boolean; runs: AgentRunResult[]; run_id?: number; status?: string }>(
    `/servers/api/agents/${agentId}/run/`,
    {
      method: "POST",
      body: JSON.stringify({
        ...(serverId ? { server_id: serverId } : {}),
        ...(providerBinding ? { provider_binding: providerBinding } : {}),
      }),
      timeoutMs: 60_000,
    },
  );
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

export async function fetchAgentRunReportV2(runId: number) {
  const response = await fetch(backendPath(`/servers/api/agents/runs/${runId}/report/v2/`), { credentials: "include" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json() as Promise<AgentRunReportV2Response>;
}

function appendListParam(params: URLSearchParams, name: string, values?: string[]) {
  const normalized = values?.map((value) => value.trim()).filter(Boolean);
  if (normalized?.length) params.set(name, normalized.join(","));
}

export async function fetchAgentRunReportEventsV2(runId: number, filters: AgentRunReportEventFilters = {}) {
  const params = new URLSearchParams();
  params.set("limit", String(filters.limit ?? 50));
  params.set("direction", filters.direction ?? "older");
  if (filters.cursor !== undefined && filters.cursor !== null) params.set("cursor", String(filters.cursor));
  appendListParam(params, "severity", filters.severity);
  appendListParam(params, "phase", filters.phase);
  appendListParam(params, "category", filters.category);
  if (filters.important !== undefined) params.set("important", String(filters.important));
  if (filters.q?.trim()) params.set("q", filters.q.trim());
  return apiFetch<AgentRunReportEventsV2Response>(
    `/servers/api/agents/runs/${runId}/events/?${params.toString()}`,
  );
}

export async function fetchAgentRunActivityV2(runId: number, filters: AgentRunActivityFilters = {}) {
  const params = new URLSearchParams();
  params.set("limit", String(filters.limit ?? 50));
  params.set("direction", filters.direction ?? "older");
  if (filters.cursor !== undefined && filters.cursor !== null) params.set("cursor", String(filters.cursor));
  appendListParam(params, "kind", filters.kind);
  appendListParam(params, "status", filters.status);
  return apiFetch<AgentRunActivityV2Response>(
    `/servers/api/agents/runs/${runId}/activity/?${params.toString()}`,
  );
}

export async function fetchAgentRunArtifactsV2(runId: number) {
  return apiFetch<AgentRunArtifactsV2Response>(`/servers/api/agents/runs/${runId}/artifacts/`);
}

export async function retryAgentRunReportDelivery(runId: number) {
  return apiFetch<AgentRunReportDeliveryAttemptResponse>(`/servers/api/agents/runs/${runId}/report/deliver/`, {
    method: "POST",
  });
}

export async function cleanupStaleAgentRun(runId: number) {
  return apiFetch<AgentRunCleanupStaleResponse>(`/servers/api/agents/runs/${runId}/cleanup-stale/`, {
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


export async function fetchAgentDashboardRuns() {
  return apiFetch<{ success: boolean; active: DashboardRunItem[]; recent: DashboardRunItem[] }>("/servers/api/agents/dashboard/");
}
