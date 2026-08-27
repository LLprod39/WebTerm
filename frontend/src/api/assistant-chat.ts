import { apiFetch } from "@/lib/api";

export type AssistantActionStatus =
  | "proposed"
  | "requires_confirmation"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export type AssistantActionRisk =
  | "read"
  | "internal_write"
  | "external"
  | "mutating"
  | "dangerous";

export interface AssistantAction {
  id: number;
  chat_id: number;
  message_id: number | null;
  action_type: string;
  title: string;
  description: string;
  status: AssistantActionStatus;
  risk: AssistantActionRisk;
  required_feature: string;
  requires_confirmation: boolean;
  input: Record<string, unknown>;
  result: Record<string, unknown>;
  error: string;
  target_url: string;
  blast_radius?: Record<string, unknown>;
  dry_run_preview?: Record<string, unknown>;
  undo_payload?: Record<string, unknown>;
  async_run_ref?: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  confirmed_at: string | null;
  completed_at: string | null;
}

export interface AssistantChatMessage {
  id: number;
  role: "user" | "assistant" | "system";
  content: string;
  metadata: {
    actions?: AssistantAction[];
    action_ids?: number[];
    source?: string;
    [key: string]: unknown;
  };
  created_at: string;
}

export interface AssistantActiveTurn {
  turn_id: number;
  status: string;
  iteration?: number;
  busy?: boolean;
  assistant_message_id?: number | null;
  assistant_text?: string;
  pending_action_id?: number | null;
}

export interface AssistantChatSession {
  id: number;
  title: string;
  kind?: string;
  pinned_context?: Record<string, unknown>;
  total_usage?: Record<string, unknown>;
  provider_binding?: import("./aiProviders").ProviderBinding;
  created_at: string;
  updated_at: string;
  messages?: AssistantChatMessage[];
  /** Open / parked operator turn — survives leaving the page. */
  active_turn?: AssistantActiveTurn | null;
}

export type OperatorWsEvent =
  | {
      type: "ready";
      chat_id: number;
      busy?: boolean;
      health?: { ok: boolean; checks?: Record<string, string>; issues?: string[] };
    }
  | {
      type: "turn_snapshot";
      chat_id?: number;
      turn_id?: number;
      status?: string;
      iteration?: number;
      busy?: boolean;
      assistant_message_id?: number | null;
      assistant_text?: string;
      user_message_id?: number | null;
      user_text?: string;
      pending_action?: AssistantAction | null;
      in_process?: boolean;
    }
  | { type: "token"; text: string }
  | { type: "tool_started"; id?: string; name?: string; arguments?: Record<string, unknown> }
  | { type: "tool_result"; id?: string; name?: string; ok?: boolean; preview?: string; action?: AssistantAction }
  | { type: "confirm_required"; turn_id?: number; action_id?: number; action?: Partial<AssistantAction> & { id: number } }
  | { type: "action_update"; action: AssistantAction }
  | { type: "usage"; usage?: Record<string, number> }
  | {
      type: "thinking";
      iteration?: number;
      phase?: string;
      message?: string;
      /** True when model already streamed real reasoning tokens this turn. */
      reasoning_active?: boolean;
    }
  | { type: "thinking_delta"; text: string; iteration?: number }
  | { type: "turn_started" | "turn_done" | "turn_complete"; status?: string; actions?: AssistantAction[] }
  | { type: "error"; code?: string; message: string }
  | { type: "pong" }
  | { type: string; [key: string]: unknown };

export interface AssistantChatListResponse {
  chats: AssistantChatSession[];
}

export interface AssistantChatTurnResponse {
  chat: AssistantChatSession;
  user_message: AssistantChatMessage;
  assistant_message: AssistantChatMessage;
  actions: AssistantAction[];
}

export function fetchAssistantChats() {
  return apiFetch<AssistantChatListResponse>("/api/assistant/chats/");
}

export function createAssistantChat(title = "") {
  return apiFetch<AssistantChatSession>("/api/assistant/chats/", {
    method: "POST",
    body: JSON.stringify({ title }),
  });
}

export function fetchAssistantChat(chatId: number) {
  return apiFetch<AssistantChatSession>(`/api/assistant/chats/${chatId}/`);
}

export function updateAssistantChat(
  chatId: number,
  payload: {
    title?: string;
    kind?: string;
    pinned_context?: Record<string, unknown>;
    provider_binding?: import("./aiProviders").ProviderBinding | Record<string, never>;
  },
) {
  return apiFetch<AssistantChatSession>(`/api/assistant/chats/${chatId}/`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteAssistantChat(chatId: number) {
  return apiFetch<{ ok: boolean }>(`/api/assistant/chats/${chatId}/`, {
    method: "DELETE",
  });
}

export function sendAssistantChatMessage(
  chatId: number,
  message: string,
  providerBinding?: import("./aiProviders").ProviderBinding,
) {
  return apiFetch<AssistantChatTurnResponse>(`/api/assistant/chats/${chatId}/message/`, {
    method: "POST",
    body: JSON.stringify({ message, ...(providerBinding ? { provider_binding: providerBinding } : {}) }),
  });
}

export function startAssistantChat(message: string, providerBinding?: import("./aiProviders").ProviderBinding) {
  return apiFetch<AssistantChatTurnResponse>("/api/assistant/chats/message/", {
    method: "POST",
    body: JSON.stringify({ message, ...(providerBinding ? { provider_binding: providerBinding } : {}) }),
  });
}

export function confirmAssistantAction(actionId: number, typedConfirm?: string) {
  return apiFetch<AssistantAction>(`/api/assistant/actions/${actionId}/confirm/`, {
    method: "POST",
    body: JSON.stringify(typedConfirm ? { typed_confirm: typedConfirm } : {}),
  });
}

export function fetchDutyChat() {
  return apiFetch<AssistantChatSession & { duty_enabled?: boolean }>("/api/assistant/duty/");
}

export function setDutyEnabled(enabled: boolean) {
  return apiFetch<AssistantChatSession & { duty_enabled?: boolean }>("/api/assistant/duty/", {
    method: "POST",
    body: JSON.stringify({ enabled }),
  });
}

export function requestDutyBriefing() {
  return apiFetch<{ ok: boolean; result: unknown; chat: AssistantChatSession }>("/api/assistant/duty/", {
    method: "POST",
    body: JSON.stringify({ brief_now: true }),
  });
}

export interface ChatArtifact {
  id: number;
  session_id: number;
  message_id: number | null;
  kind: string;
  title: string;
  content: string;
  version: number;
  metadata: Record<string, unknown>;
  saved_playbook_id: number | null;
  created_at: string;
  updated_at: string;
}

export function fetchChatArtifacts(chatId: number) {
  return apiFetch<{ artifacts: ChatArtifact[] }>(`/api/assistant/chats/${chatId}/artifacts/`);
}

export function createChatArtifact(
  chatId: number,
  payload: { kind?: string; title?: string; content?: string; metadata?: Record<string, unknown> },
) {
  return apiFetch<ChatArtifact>(`/api/assistant/chats/${chatId}/artifacts/`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateChatArtifact(
  chatId: number,
  payload: { id: number; content?: string; title?: string; bump_version?: boolean },
) {
  return apiFetch<ChatArtifact>(`/api/assistant/chats/${chatId}/artifacts/`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function cancelAssistantAction(actionId: number) {
  return apiFetch<AssistantAction>(`/api/assistant/actions/${actionId}/cancel/`, {
    method: "POST",
  });
}
