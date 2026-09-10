import { api } from "./client";

export interface ActiveUser {
  user_id: number;
  username: string;
  email: string;
  is_staff: boolean;
  last_action: string;
  last_category: string;
  last_activity: string;
  active_terminals: number;
  today_actions: number;
}
export interface ActiveUsers {
  online_count: number;
  total_registered: number;
  active_today: number;
  sessions: ActiveUser[];
}
export interface ActivityEvent {
  id: number;
  user_id: number | null;
  username: string;
  category: string;
  action: string;
  status: string;
  description: string;
  entity_type: string;
  entity_name: string;
  ip_address: string;
  created_at: string;
}
export interface ProviderUsage {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  errors: number;
  estimated_cost_usd: number;
  actual_spend_usd: number | null;
  balance_usd: number | null;
  billing_source: string;
  billing_note: string;
  cost_usd: number;
}
export interface AdminUsage {
  api_usage: Record<string, ProviderUsage>;
  api_calls_today: number;
  providers: Record<string, { enabled: boolean; model: string }>;
  hourly_activity: { hour: string; count: number }[];
  top_users: {
    username: string;
    total: number;
    ai_requests: number;
    terminal_sessions: number;
  }[];
  terminals: {
    active: number;
    connections: { server: string; user: string; connected_at: string }[];
  };
}
export const adminActivityApi = {
  sessions: (signal?: AbortSignal) =>
    api.get<ActiveUsers>("/api/admin/users/sessions/", signal),
  events: (params: URLSearchParams, signal?: AbortSignal) =>
    api.get<{ total: number; events: ActivityEvent[] }>(
      `/api/admin/users/activity/?${params}`,
      signal,
    ),
  usage: (signal?: AbortSignal) =>
    api.get<AdminUsage>("/api/admin/dashboard/", signal),
};
