import { apiFetch } from "@/lib/api";

export interface TelegramLinkCodeResponse {
  id: number;
  code: string;
  bot_id: number;
  bot_username: string;
  deep_link: string;
  expires_at: string;
}

export interface TelegramAccountLink {
  id: number;
  bot_id: number;
  bot_username: string;
  bot_kind: string;
  telegram_user_id: number;
  chat_id: string;
  username: string;
  status: string;
  linked_at?: string | null;
  last_seen_at?: string | null;
}

export interface TelegramBotRecord {
  id: number;
  kind: string;
  name: string;
  bot_username: string;
  bot_user_id?: number | null;
  is_active: boolean;
  mode: "assistant" | "pipeline" | string;
  pipeline_id?: number | null;
  system_prompt: string;
  provider_binding: Record<string, unknown>;
  allow_group_chats: boolean;
  allowed_chat_ids: string[];
  last_poll_at?: string | null;
  last_error: string;
  owner_id?: number | null;
  has_token: boolean;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface TelegramStatus {
  notifications_allowed: boolean;
  notifications_enabled: boolean;
  chat_id: string;
  prefs_chat_id: string;
  linked: boolean;
  bot_username: string;
  bot_configured: boolean;
  assistant_allowed: boolean;
  personal_bots_allowed: boolean;
  hub_hint: "ok" | "worker_offline" | string;
  link: TelegramAccountLink | null;
}

export const meTelegram = {
  status: () => apiFetch<TelegramStatus>("/api/me/telegram/status/"),
  createLinkCode: (botId?: number) =>
    apiFetch<TelegramLinkCodeResponse>("/api/me/telegram/link-codes/", {
      method: "POST",
      body: JSON.stringify(botId ? { bot_id: botId } : {}),
    }),
  listLinks: () => apiFetch<{ links: TelegramAccountLink[] }>("/api/me/telegram/links/"),
  deleteLink: (linkId: number) =>
    apiFetch<{ ok: boolean }>(`/api/me/telegram/links/${linkId}/`, { method: "DELETE" }),
  listBots: () => apiFetch<{ bots: TelegramBotRecord[] }>("/api/me/telegram/bots/"),
  createBot: (data: {
    token: string;
    name?: string;
    mode?: string;
    system_prompt?: string;
  }) =>
    apiFetch<TelegramBotRecord>("/api/me/telegram/bots/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  updateBot: (botId: number, data: Record<string, unknown>) =>
    apiFetch<TelegramBotRecord>(`/api/me/telegram/bots/${botId}/`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  deleteBot: (botId: number) =>
    apiFetch<{ ok: boolean }>(`/api/me/telegram/bots/${botId}/`, { method: "DELETE" }),
  testBot: (botId: number) =>
    apiFetch<{ ok: boolean; message: string }>(`/api/me/telegram/bots/${botId}/test/`, {
      method: "POST",
    }),
};

export const studioTelegram = {
  listBots: () => apiFetch<{ bots: TelegramBotRecord[] }>("/api/studio/telegram/bots/"),
  updateBot: (botId: number, data: { is_active?: boolean; mode?: string }) =>
    apiFetch<TelegramBotRecord>(`/api/studio/telegram/bots/${botId}/`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
};
