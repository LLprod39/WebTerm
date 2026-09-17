import { apiFetch } from "@/lib/api";

export type AiSubscriptionTarget = "codex_subscription" | "grok_subscription" | "cursor_subscription";
export type AiPurpose = "assistant" | "agents" | "terminal" | "internal";
export type AiReasoningEffort = "low" | "medium" | "high" | "xhigh" | "max" | "ultra";

export interface AiProviderModel {
  id: string;
  label: string;
  default_reasoning_effort: AiReasoningEffort | null;
  reasoning_efforts: AiReasoningEffort[];
  deprecated?: boolean;
}

export const aiProviderQueryKeys = {
  all: ["ai-providers"] as const,
  catalog: ["ai-providers", "catalog"] as const,
  connections: ["ai-providers", "connections"] as const,
  pools: ["ai-providers", "pools"] as const,
  preferences: ["ai-providers", "preferences"] as const,
  authFlow: (flowId: string) => ["ai-providers", "auth-flow", flowId] as const,
};

export interface ProviderBinding {
  target_id: string;
  connection_id?: number | null;
  pool_id?: number | null;
  model_id?: string | null;
  reasoning_effort?: AiReasoningEffort | null;
}

export interface AiProviderGrant {
  id: number;
  connection_id: number;
  user: { id: number; username: string } | null;
  group: { id: number; name: string } | null;
  project: { id: number; name: string } | null;
  project_role: string;
  allow_interactive: boolean;
  allow_unattended: boolean;
  max_slots: number | null;
}

export interface AiProviderConnection {
  id: number;
  public_id: string;
  target_id: AiSubscriptionTarget;
  scope: "personal" | "workspace";
  owner_id: number | null;
  name: string;
  status: string;
  enabled: boolean;
  concurrency_limit: number;
  last_error_code: string;
  last_verified_at: string | null;
  access: { interactive: boolean; unattended: boolean };
  manageable: boolean;
  grants?: AiProviderGrant[];
}

export interface AiProviderPool {
  id: number;
  name: string;
  target_id: AiSubscriptionTarget;
  enabled: boolean;
  manageable: boolean;
  members: Array<{
    connection_id: number;
    connection_name: string;
    status: string;
    enabled: boolean;
    access?: { interactive: boolean; unattended: boolean };
  }>;
}

export interface AiProviderPreference {
  id: number;
  user_id: number | null;
  project_id: number | null;
  purpose: AiPurpose;
  binding: ProviderBinding;
}

export interface AiProviderAuthFlow {
  id: string;
  connection_id: number;
  status: string;
  verification_uri: string;
  user_code: string;
  error_code: string;
  expires_at: string | null;
}

export const fetchAiProviderCatalog = () => apiFetch<{
  success: boolean;
  targets: Array<{ id: string; label: string; kind: string }>;
  purposes: AiPurpose[];
  models_by_target: Record<string, AiProviderModel[]>;
}>("/api/ai/providers/catalog/");

export const fetchAiProviderConnections = () => apiFetch<{ success: boolean; connections: AiProviderConnection[] }>(
  "/api/ai/providers/connections/",
);

export const createAiProviderConnection = (payload: {
  target_id: AiSubscriptionTarget;
  scope: "personal" | "workspace";
  name: string;
  concurrency_limit?: number;
}) => apiFetch<{ success: boolean; connection: AiProviderConnection }>("/api/ai/providers/connections/", {
  method: "POST",
  body: JSON.stringify(payload),
});

export const updateAiProviderConnection = (
  connectionId: number,
  payload: { name?: string; enabled?: boolean; concurrency_limit?: number; scope?: "personal" | "workspace" },
) => apiFetch<{ success: boolean; connection: AiProviderConnection }>(
  `/api/ai/providers/connections/${connectionId}/`,
  { method: "PATCH", body: JSON.stringify(payload) },
);

export const revokeAiProviderConnection = (connectionId: number) => apiFetch<{
  success: boolean;
  revoked: boolean;
  deleted?: boolean;
  cleanup_pending?: boolean;
  code?: string;
}>(
  `/api/ai/providers/connections/${connectionId}/`,
  { method: "DELETE" },
);

export const startAiProviderAuth = (connectionId: number) => apiFetch<{ success: boolean; auth_flow: AiProviderAuthFlow }>(
  `/api/ai/providers/connections/${connectionId}/auth/`,
  { method: "POST", body: "{}" },
);

export const fetchAiProviderAuthFlow = (flowId: string) => apiFetch<{ success: boolean; auth_flow: AiProviderAuthFlow }>(
  `/api/ai/providers/auth-flows/${flowId}/`,
);

export const verifyAiProviderConnection = (connectionId: number) => apiFetch<{
  success: boolean;
  auth_flow: AiProviderAuthFlow;
}>(`/api/ai/providers/connections/${connectionId}/verify/`, { method: "POST", body: "{}" });

export const fetchAiProviderPrincipals = () => apiFetch<{
  success: boolean;
  users: Array<{ id: number; username: string }>;
  groups: Array<{ id: number; name: string }>;
}>("/api/ai/providers/principals/");

export const fetchAiProviderPools = () => apiFetch<{ success: boolean; pools: AiProviderPool[] }>(
  "/api/ai/providers/pools/",
);

export const createAiProviderPool = (payload: {
  name: string;
  target_id: AiSubscriptionTarget;
  connection_ids: number[];
}) => apiFetch<{ success: boolean; pool: AiProviderPool }>("/api/ai/providers/pools/", {
  method: "POST",
  body: JSON.stringify(payload),
});

export const fetchAiProviderPreferences = (params?: { forUserId?: number }) => {
  const query = params?.forUserId ? `?for_user_id=${params.forUserId}` : "";
  return apiFetch<{
    success: boolean;
    preferences: AiProviderPreference[];
    workspace_defaults: AiProviderPreference[];
    for_user_id?: number;
  }>(`/api/ai/providers/preferences/${query}`);
};

export const saveAiProviderPreference = (payload: {
  purpose?: AiPurpose;
  purposes?: AiPurpose[];
  binding: ProviderBinding;
  project_scoped: boolean;
  workspace_default?: boolean;
  require_unattended?: boolean;
  target_user_id?: number;
}) => apiFetch<{
  success: boolean;
  preference?: AiProviderPreference;
  preferences?: AiProviderPreference[];
}>("/api/ai/providers/preferences/", {
  method: "PUT",
  body: JSON.stringify(payload),
});

export const clearAiProviderPreference = (payload: {
  purpose?: AiPurpose;
  purposes?: AiPurpose[];
  project_scoped?: boolean;
  workspace_default?: boolean;
  target_user_id?: number;
}) => apiFetch<{ success: boolean; deleted?: number }>("/api/ai/providers/preferences/", {
  method: "DELETE",
  body: JSON.stringify(payload),
});

export const createAiProviderGrant = (payload: {
  connection_id: number;
  user_id?: number;
  group_id?: number;
  allow_interactive: boolean;
  allow_unattended: boolean;
  max_slots?: number | null;
  assign_preferences?: {
    purposes: AiPurpose[];
    project_scoped?: boolean;
    model_id?: string | null;
  };
}) => apiFetch<{
  success: boolean;
  grant: AiProviderGrant;
  assigned_preferences?: AiProviderPreference[];
}>("/api/ai/providers/grants/", {
  method: "POST",
  body: JSON.stringify(payload),
});

export const updateAiProviderGrant = (
  grantId: number,
  payload: {
    allow_interactive?: boolean;
    allow_unattended?: boolean;
    max_slots?: number | null;
  },
) => apiFetch<{ success: boolean; grant: AiProviderGrant }>(
  `/api/ai/providers/grants/${grantId}/`,
  { method: "PATCH", body: JSON.stringify(payload) },
);

export const deleteAiProviderGrant = (grantId: number) => apiFetch<{ success: boolean }>(
  `/api/ai/providers/grants/${grantId}/`,
  { method: "DELETE" },
);
