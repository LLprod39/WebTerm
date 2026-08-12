import { apiFetch } from "@/lib/api";

export type AiSubscriptionTarget = "codex_subscription" | "grok_subscription";
export type AiPurpose = "assistant" | "agents" | "terminal" | "internal";

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

export const revokeAiProviderConnection = (connectionId: number) => apiFetch<{ success: boolean; revoked: boolean }>(
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

export const fetchAiProviderPreferences = () => apiFetch<{
  success: boolean;
  preferences: AiProviderPreference[];
  workspace_defaults: AiProviderPreference[];
}>("/api/ai/providers/preferences/");

export const saveAiProviderPreference = (payload: {
  purpose: AiPurpose;
  binding: ProviderBinding;
  project_scoped: boolean;
  workspace_default?: boolean;
  require_unattended?: boolean;
}) => apiFetch<{ success: boolean; preference: AiProviderPreference }>("/api/ai/providers/preferences/", {
  method: "PUT",
  body: JSON.stringify(payload),
});

export const createAiProviderGrant = (payload: {
  connection_id: number;
  user_id: number;
  allow_interactive: boolean;
  allow_unattended: boolean;
}) => apiFetch<{ success: boolean; grant: AiProviderGrant }>("/api/ai/providers/grants/", {
  method: "POST",
  body: JSON.stringify(payload),
});

export const deleteAiProviderGrant = (grantId: number) => apiFetch<{ success: boolean }>(
  `/api/ai/providers/grants/${grantId}/`,
  { method: "DELETE" },
);
