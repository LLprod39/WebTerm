import { api } from "./client";

export interface GroupIdentity {
  user_id: number;
  username: string;
  email: string;
}
export interface GroupMember extends GroupIdentity {
  role: string;
  joined_at: string;
}
export interface GroupMembers {
  group_id: number;
  owner: GroupIdentity;
  members: GroupMember[];
}
export interface GroupContext {
  id: number;
  name: string;
  rules: string;
  forbidden_commands: string[];
  environment_vars: Record<string, string>;
}
export type BulkAction = "set_active" | "set_ai_read_only" | "set_tags";
export type BulkRequest =
  | {
      action: "set_active" | "set_ai_read_only";
      parameters: { value: boolean };
    }
  | { action: "set_tags"; parameters: { value: string } };
export interface BulkOperation {
  id: number;
  group_id: number;
  action: BulkAction;
  parameters: { value: boolean | string };
  status: "queued" | "running" | "completed" | "failed";
  total_count: number;
  processed_count: number;
  succeeded_count: number;
  failed_count: number;
  progress_percent: number;
  failures: { server_id?: number; error: string; code?: string }[];
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}
export const serverGroupsApi = {
  members: (id: number, signal?: AbortSignal) =>
    api.get<GroupMembers>(`/servers/api/groups/${id}/members/`, signal),
  addMember: (id: number, user: string, role: "admin" | "member" | "viewer") =>
    api.post(`/servers/api/groups/${id}/add-member/`, { user, role }),
  removeMember: (id: number, user_id: number) =>
    api.post(`/servers/api/groups/${id}/remove-member/`, { user_id }),
  context: (id: number, signal?: AbortSignal) =>
    api.get<GroupContext>(`/servers/api/groups/${id}/context/`, signal),
  saveContext: (
    id: number,
    body: Pick<
      GroupContext,
      "rules" | "forbidden_commands" | "environment_vars"
    >,
  ) => api.post(`/servers/api/groups/${id}/context/save/`, body),
  bulkCreate: (id: number, body: BulkRequest) =>
    api.post<{ operation: BulkOperation }>(
      `/servers/api/groups/${id}/bulk-actions/`,
      body,
    ),
  bulkOperation: (id: number, signal?: AbortSignal) =>
    api.get<{ operation: BulkOperation }>(
      `/servers/api/bulk-actions/${id}/`,
      signal,
    ),
  updateServers: (body: {
    server_ids: number[];
    group_id?: number | null;
    tags?: string;
    is_active?: boolean;
  }) => api.post("/servers/api/bulk-update/", body),
};
