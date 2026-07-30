import { apiFetch } from "@/lib/api";

export type ProjectRole = "owner" | "admin" | "operator" | "viewer";

export interface ProjectSummary {
  id: string;
  name: string;
  slug: string;
  role: ProjectRole;
  is_active: boolean;
  is_default: boolean;
  member_count: number;
  can_manage: boolean;
  created_at: string;
}

export interface ProjectsResponse {
  projects: ProjectSummary[];
  active_project_id: string | null;
}

export async function fetchProjects(): Promise<ProjectsResponse> {
  return apiFetch<ProjectsResponse>("/api/projects/");
}

export async function activateProject(projectId: string): Promise<{ success: boolean; project: ProjectSummary }> {
  return apiFetch<{ success: boolean; project: ProjectSummary }>(
    `/api/projects/${encodeURIComponent(projectId)}/activate/`,
    { method: "POST" },
  );
}
