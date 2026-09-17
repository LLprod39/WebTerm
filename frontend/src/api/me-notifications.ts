import { apiFetch } from "@/lib/api";

export interface MyNotificationPrefs {
  telegram_chat_id: string;
  telegram_enabled: boolean;
  updated_at?: string | null;
}

export const myNotifications = {
  get: () => apiFetch<MyNotificationPrefs>("/api/me/notifications/"),
  save: (data: Partial<MyNotificationPrefs>) =>
    apiFetch<MyNotificationPrefs>("/api/me/notifications/", {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  testTelegram: (telegram_chat_id?: string) =>
    apiFetch<{ ok: boolean; message: string }>("/api/me/notifications/test-telegram/", {
      method: "POST",
      body: JSON.stringify(telegram_chat_id ? { telegram_chat_id } : {}),
    }),
};
