import { apiFetch } from "@/lib/api";

export interface MarsWorkspace {
  id: number;
  name: string;
  root_path: string;
  read_allow_roots: string[];
  write_allow_roots: string[];
  deny_globs: string[];
  enabled: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface MarsInterviewQuestion {
  id: string;
  question: string;
  kind: string;
  options?: string[];
  placeholder?: string;
  required?: boolean;
}

export type MarsSessionStatus = "interview" | "plan_ready" | "approved" | "running" | "completed" | "cancelled";

export interface MarsSession {
  id: number;
  workspace_id: number;
  workspace: MarsWorkspace;
  task_brief: string;
  answers: Record<string, string>;
  interview_questions: MarsInterviewQuestion[];
  selected_skill_slugs: string[];
  generated_plan: string;
  status: MarsSessionStatus | string;
  created_at: string | null;
  updated_at: string | null;
}

export type MarsRunStatus = "queued" | "running" | "completed" | "failed" | "stopped";

export interface MarsOrchestrationRole {
  role: string;
  agent: string;
  workspace_mode: string;
  skills: string[];
  responsibility: string;
}

export interface MarsOrchestrationMetadata {
  strategy: string;
  roles: MarsOrchestrationRole[];
  skill_routing: Record<string, string[]>;
  max_repair_rounds: number;
  review_repair_rounds: number;
}

export interface MarsRun {
  id: number;
  session_id: number;
  workspace_id: number;
  workspace: MarsWorkspace;
  cli_roles: Record<string, string>;
  status: MarsRunStatus | string;
  runtime_control: Record<string, unknown>;
  allow_dirty: boolean;
  final_report: string;
  codex_summary: string;
  gemini_review: string;
  test_output: string;
  git_before: string;
  git_after: string;
  started_at: string | null;
  completed_at: string | null;
  created_at: string | null;
}

export interface MarsProject {
  session: MarsSession;
  latest_run: MarsRun | null;
  run_count: number;
  recommended_skills: string[];
}

export interface MarsRunEvent {
  id: number;
  run_id: number;
  event_type: string;
  message: string;
  payload: Record<string, unknown>;
  created_at: string | null;
}

export interface MarsWorkspacePayload {
  name?: string;
  root_path?: string;
  read_allow_roots?: string[];
  write_allow_roots?: string[];
  deny_globs?: string[];
  enabled?: boolean;
}

export interface MarsSessionPayload {
  workspace_id: number;
  task_brief: string;
  selected_skill_slugs?: string[];
}

export interface MarsRunPayload {
  allow_dirty?: boolean;
  verification_profile?: string;
  /** @deprecated Use verification_profile. */
  test_command?: string;
}

export const marsApi = {
  listWorkspaces: () => apiFetch<{ workspaces: MarsWorkspace[] }>("/api/mars/workspaces/"),
  listProjects: (limit = 30) => apiFetch<{ projects: MarsProject[] }>(`/api/mars/projects/?limit=${limit}`),
  createWorkspace: (data: MarsWorkspacePayload) =>
    apiFetch<{ workspace: MarsWorkspace }>("/api/mars/workspaces/", { method: "POST", body: JSON.stringify(data) }),
  updateWorkspace: (id: number, data: Partial<MarsWorkspacePayload>) =>
    apiFetch<{ workspace: MarsWorkspace }>(`/api/mars/workspaces/${id}/`, { method: "PATCH", body: JSON.stringify(data) }),
  deleteWorkspace: (id: number) => apiFetch<{ ok: boolean }>(`/api/mars/workspaces/${id}/`, { method: "DELETE" }),
  createSession: (data: MarsSessionPayload) =>
    apiFetch<{ session: MarsSession; recommended_skills: string[] }>("/api/mars/sessions/", {
      method: "POST",
      body: JSON.stringify(data),
      timeoutMs: 240_000,
    }),
  getSession: (id: number) => apiFetch<{ session: MarsSession; recommended_skills: string[] }>(`/api/mars/sessions/${id}/`),
  answerSession: (id: number, data: { answers: Record<string, string>; selected_skill_slugs?: string[] }) =>
    apiFetch<{ session: MarsSession }>(`/api/mars/sessions/${id}/answer/`, { method: "POST", body: JSON.stringify(data) }),
  approveSessionPlan: (id: number, data: { generated_plan?: string; selected_skill_slugs?: string[] }) =>
    apiFetch<{ session: MarsSession }>(`/api/mars/sessions/${id}/approve-plan/`, { method: "POST", body: JSON.stringify(data) }),
  runSession: (id: number, data: MarsRunPayload) =>
    apiFetch<{ run: MarsRun }>(`/api/mars/sessions/${id}/run/`, { method: "POST", body: JSON.stringify(data) }),
  getRun: (id: number) => apiFetch<{ run: MarsRun }>(`/api/mars/runs/${id}/`),
  listRunEvents: (id: number, afterId?: number) =>
    apiFetch<{ events: MarsRunEvent[] }>(`/api/mars/runs/${id}/events/${afterId ? `?after_id=${afterId}` : ""}`),
  stopRun: (id: number) => apiFetch<{ run: MarsRun }>(`/api/mars/runs/${id}/stop/`, { method: "POST" }),
};
