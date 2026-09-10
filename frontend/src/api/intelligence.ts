import { api } from "./client";

export type Details = Record<string, unknown>;
export interface Agent {
  id: number;
  name: string;
  mode: string;
  agent_type: string;
  server_ids: number[];
  server_names: string[];
  commands: unknown[];
  goal: string;
  ai_prompt: string;
  system_prompt: string;
  is_enabled: boolean;
  max_iterations: number;
  session_timeout_seconds: number;
  max_connections: number;
  allow_multi_server: boolean;
  tools_config: Details;
  sudo_policy: string;
  stop_conditions: string[];
  skill_slugs: string[];
  schedule_minutes: number;
  schedule_config: Details;
  input_artifacts: unknown[];
  report_delivery: Details;
  execution_readiness: Details;
  last_run_id: number | null;
  last_run_status: string | null;
  active_run_id: number | null;
  active_run_status: string | null;
  next_due_at: string | null;
}
export interface ScheduledAgent extends Agent {
  due_now: boolean;
  schedule_state: string;
}
export interface AgentRun {
  id: number;
  agent_id: number | null;
  agent_name: string;
  agent_mode: string;
  server_name: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  pending_question: string;
  plan_tasks: PlanTask[];
  final_report: string;
  ai_analysis: string;
  total_iterations: number;
  dispatch?: Details;
  commands_output: unknown[];
}
export interface PlanTask {
  id: number;
  name: string;
  description: string;
  status: string;
}
export interface RunReport {
  run: {
    id: number;
    agent_id: number;
    agent_name: string;
    goal: string;
    server_name: string;
  };
  lifecycle: Details;
  outcome: Details;
  evidence_state: Details;
  report_generation: Details;
  delivery: Details;
  indicators: Details[];
  findings: Details[];
  actions: Details[];
  phases: Details[];
  counts: Details;
  document: Details;
  evidence_links: Record<string, string>;
}
export interface PageResult {
  items: Details[];
  total: number;
  page: { next_cursor: string | null; has_more: boolean };
}
export interface ServerChoice {
  id: number;
  name: string;
  host: string;
  can_edit: boolean;
}
export interface ChatAction {
  id: number;
  title: string;
  description: string;
  status: string;
  risk: string;
  action_type: string;
  input: Details;
  result: Details;
  error: string;
  requires_confirmation: boolean;
  blast_radius: Details;
  dry_run_preview: Details;
  target_url: string;
}
export interface ChatMessage {
  id: number;
  role: string;
  content: string;
  created_at: string;
  metadata: Details & { actions?: ChatAction[] };
}
export interface Chat {
  id: number;
  title: string;
  kind: string;
  updated_at: string;
  messages?: ChatMessage[];
  active_turn?: {
    busy: boolean;
    status: string;
    assistant_text: string;
    assistant_message_id: number | null;
    pending_action_id: number | null;
  } | null;
  pinned_context: Details;
  total_usage: Details;
}
export interface ChatArtifact {
  id: number;
  title: string;
  kind: string;
  content: string;
  version: number;
}
export interface MCP {
  shared_user_ids?: number[];
  secret_env_keys?: string[];
  id: number;
  name: string;
  description: string;
  transport: "stdio" | "sse";
  command: string;
  args: string[];
  env: Details;
  headers: Details;
  url: string;
  can_edit: boolean;
  can_share: boolean;
  is_shared: boolean;
  owner_username: string;
  last_test_ok: boolean | null;
  last_test_at: string | null;
  last_test_error: string;
}
export interface MemorySnapshot {
  id: number;
  title: string;
  content: string;
  kind: string;
  memory_key: string;
  version: number;
  confidence: number;
  freshness: number;
  updated_at: string;
}
export interface MarsQuestion {
  id: string;
  question: string;
  kind: string;
  options: string[];
  required: boolean;
  placeholder: string;
}
export interface MarsSession {
  id: number;
  task_brief: string;
  status: string;
  answers: Record<string, string>;
  interview_questions: MarsQuestion[];
  generated_plan: string;
  workspace: { name: string; root_path: string; enabled: boolean };
  updated_at: string;
}
export interface MarsRun {
  id: number;
  session_id: number;
  status: string;
  runtime_control: Details;
  final_report: string;
  codex_summary: string;
  gemini_review: string;
  test_output: string;
  created_at: string;
  completed_at: string | null;
}
const agents = "/servers/api/agents/";
const chats = "/api/assistant/chats/";
export const intelligenceApi = {
  agents: () =>
    api.get<{
      agents: Agent[];
      runtime_overview: Details;
      worker_states: Details;
    }>(agents),
  schedules: () =>
    api.get<{
      scheduled_agents: ScheduledAgent[];
      worker_states: Details;
      execution_readiness: Details;
    }>(`${agents}schedules/?limit=200`),
  dispatchSchedules: (agent_ids: number[]) =>
    api.post<Details>(`${agents}schedules/dispatch/`, {
      agent_ids,
      limit: agent_ids.length,
    }),
  cleanupRuns: () =>
    api.post<Details>(`${agents}runtime/cleanup-stale/`, { limit: 100 }),
  refineTask: (run: number, id: number, instruction: string) =>
    api.post<{ task: PlanTask; plan_tasks: PlanTask[] }>(
      `${agents}runs/${run}/tasks/${id}/ai-refine/`,
      { instruction },
    ),
  templates: () => api.get<{ templates: Details[] }>(`${agents}templates/`),
  createAgent: (body: Details) =>
    api.post<{ id: number }>(`${agents}create/`, body),
  updateAgent: (id: number, body: Details) =>
    api.post(`${agents}${id}/update/`, body),
  deleteAgent: (id: number) => api.post(`${agents}${id}/delete/`),
  launchAgent: (id: number) =>
    api.post<{ run_id: number }>(`${agents}${id}/run/`),
  stopAgent: (id: number) => api.post(`${agents}${id}/stop/`),
  runs: (id: number) =>
    api.get<{ runs: AgentRun[] }>(`${agents}${id}/runs/?limit=100`),
  run: (id: number) => api.get<{ run: AgentRun }>(`${agents}runs/${id}/`),
  report: (id: number) => api.get<RunReport>(`${agents}runs/${id}/report/v2/`),
  events: (id: number, cursor = "") =>
    api.get<PageResult>(
      `${agents}runs/${id}/events/v2/?limit=50&cursor=${encodeURIComponent(cursor)}`,
    ),
  activity: (id: number, cursor = "") =>
    api.get<PageResult>(
      `${agents}runs/${id}/activity/?limit=50&cursor=${encodeURIComponent(cursor)}`,
    ),
  artifacts: (id: number) =>
    api.get<{ items?: Details[]; artifacts?: Details[] }>(
      `${agents}runs/${id}/artifacts/`,
    ),
  runAction: (id: number, action: string, body: Details = {}) =>
    api.post(`${agents}runs/${id}/${action}/`, body),
  task: (run: number, id: number, body: Details) =>
    api.post(`${agents}runs/${run}/tasks/${id}/update/`, body),
  servers: () =>
    api.get<{ servers: ServerChoice[] }>("/servers/api/frontend/bootstrap/"),
  chats: () => api.get<{ chats: Chat[] }>(chats),
  chat: (id: number) => api.get<Chat>(`${chats}${id}/`),
  createChat: (title = "") => api.post<Chat>(chats, { title }),
  patchChat: (id: number, body: Details) =>
    api.patch<Chat>(`${chats}${id}/`, body),
  deleteChat: (id: number) => api.delete(`${chats}${id}/`),
  message: (id: number, message: string) =>
    api.post<{ chat: Chat; assistant_message: ChatMessage }>(
      `${chats}${id}/message/`,
      { message },
    ),
  chatAction: (id: number, action: "confirm" | "cancel", typed_confirm = "") =>
    api.post<ChatAction>(`/api/assistant/actions/${id}/${action}/`, {
      typed_confirm,
    }),
  chatArtifacts: (id: number) =>
    api.get<{ artifacts: ChatArtifact[] }>(`${chats}${id}/artifacts/`),
  updateArtifact: (id: number, body: Details) =>
    api.patch<ChatArtifact>(`${chats}${id}/artifacts/`, body),
  duty: (body?: Details) =>
    body
      ? api.post<Chat & { chat?: Chat; duty_enabled?: boolean }>(
          "/api/assistant/duty/",
          body,
        )
      : api.get<Chat & { duty_enabled: boolean }>("/api/assistant/duty/"),
  mcps: () => api.get<MCP[]>("/api/studio/mcp/"),
  mcpTemplates: () => api.get<Details[]>("/api/studio/mcp/templates/"),
  saveMcp: (id: number | undefined, body: Details) =>
    id
      ? api.put<MCP>(`/api/studio/mcp/${id}/`, body)
      : api.post<MCP>("/api/studio/mcp/", body),
  deleteMcp: (id: number) => api.delete(`/api/studio/mcp/${id}/`),
  testMcp: (id: number) =>
    api.post<{ ok: boolean; error: string | null }>(
      `/api/studio/mcp/${id}/test/`,
    ),
  mcpTools: (id: number) => api.get<Details>(`/api/studio/mcp/${id}/tools/`),
  memory: (id: number) =>
    api.get<{ items: MemorySnapshot[] }>(
      `/servers/api/${id}/memory/snapshots/`,
    ),
  memoryOverview: (id: number) =>
    api.get<Details>(`/servers/api/${id}/memory/overview/`),
  memoryAction: (id: number, action: string, body: Details = {}) =>
    api.post<Details>(`/servers/api/${id}/memory/${action}/`, body),
  marsProjects: () =>
    api.get<{
      projects: {
        session: MarsSession;
        latest_run: MarsRun | null;
        run_count: number;
      }[];
    }>("/api/mars/projects/"),
  createMars: (task_brief: string) =>
    api.post<{ session: MarsSession }>("/api/mars/sessions/", { task_brief }),
  marsSession: (id: number) =>
    api.get<{ session: MarsSession }>(`/api/mars/sessions/${id}/`),
  marsAnswer: (id: number, answers: Record<string, string>) =>
    api.post<{ session: MarsSession }>(`/api/mars/sessions/${id}/answer/`, {
      answers,
    }),
  marsApprove: (id: number, generated_plan: string) =>
    api.post<{ session: MarsSession }>(
      `/api/mars/sessions/${id}/approve-plan/`,
      { generated_plan },
    ),
  marsLaunch: (id: number, body: Details) =>
    api.post<{ run: MarsRun }>(`/api/mars/sessions/${id}/run/`, body),
  marsRun: (id: number) => api.get<{ run: MarsRun }>(`/api/mars/runs/${id}/`),
  marsEvents: (id: number, after = 0) =>
    api.get<{ events: Details[] }>(
      `/api/mars/runs/${id}/events/?after_id=${after}`,
    ),
  marsStop: (id: number) => api.post(`/api/mars/runs/${id}/stop/`),
};
