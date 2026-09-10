import { api, clearCsrf } from "./client";
export interface SessionUser {
  id: number;
  username: string;
  email: string;
  is_staff: boolean;
  can_manage_ai_routing: boolean;
  ai_cli_runtime_enabled: boolean;
  access_profile: string;
  permission_sources: Record<string, string>;
  features: Record<string, boolean>;
  active_project: { id: string; name: string; slug: string } | null;
  project_count: number;
}
export interface Session {
  authenticated: boolean;
  user: SessionUser | null;
}
export const authApi = {
  session: (signal?: AbortSignal) =>
    api.get<Session>("/api/auth/session/", signal),
  login: async (username: string, password: string, auth_mode = "auto") => {
    const result = await api.post<Session>("/api/auth/login/", {
      username,
      password,
      auth_mode,
    });
    clearCsrf();
    return result;
  },
  logout: async () => {
    const result = await api.post<Session>("/api/auth/logout/");
    clearCsrf();
    return result;
  },
};
