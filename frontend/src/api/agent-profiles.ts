import { api } from "./client";
import type { Details } from "./intelligence";
export interface AgentProfile {
  shared_user_ids?: number[];
  id: number;
  name: string;
  description: string;
  system_prompt: string;
  instructions: string;
  model: string;
  max_iterations: number;
  allowed_tools: string[];
  sudo_policy: string;
  skill_slugs: string[];
  skill_errors: string[];
  mcp_servers: { id: number; name: string; transport: string }[];
  server_scope: { id: number; name: string }[];
  can_edit: boolean;
  can_share: boolean;
  is_shared: boolean;
  owner_username: string;
  updated_at: string;
  provider_binding: Details;
}
export const agentProfilesApi = {
  list: () => api.get<AgentProfile[]>("/api/studio/agents/"),
  save: (id: number | undefined, body: Details) =>
    id
      ? api.put<AgentProfile>(`/api/studio/agents/${id}/`, body)
      : api.post<AgentProfile>("/api/studio/agents/", body),
  remove: (id: number) => api.delete(`/api/studio/agents/${id}/`),
};
