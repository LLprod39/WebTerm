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

export interface AssistantChatSession {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  messages?: AssistantChatMessage[];
}

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

export function sendAssistantChatMessage(chatId: number, message: string) {
  return apiFetch<AssistantChatTurnResponse>(`/api/assistant/chats/${chatId}/message/`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

export function startAssistantChat(message: string) {
  return apiFetch<AssistantChatTurnResponse>("/api/assistant/chats/message/", {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

export function confirmAssistantAction(actionId: number) {
  return apiFetch<AssistantAction>(`/api/assistant/actions/${actionId}/confirm/`, {
    method: "POST",
  });
}

export function cancelAssistantAction(actionId: number) {
  return apiFetch<AssistantAction>(`/api/assistant/actions/${actionId}/cancel/`, {
    method: "POST",
  });
}
