import { apiFetch } from "@/lib/api";

export interface NotificationConfig {
  telegram_bot_token: string;
  telegram_chat_id: string;
  notify_email: string;
  smtp_host: string;
  smtp_port: string;
  smtp_user: string;
  smtp_password: string;
  from_email: string;
  site_url: string;
}

export const studioNotifications = {
  get: () => apiFetch<NotificationConfig>("/api/studio/notifications/"),
  save: (data: Partial<NotificationConfig>) =>
    apiFetch<{ ok: boolean; saved: string[] }>("/api/studio/notifications/", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  testTelegram: () =>
    apiFetch<{ ok: boolean; message: string }>("/api/studio/notifications/test-telegram/", { method: "POST" }),
  testEmail: () =>
    apiFetch<{ ok: boolean; message: string }>("/api/studio/notifications/test-email/", { method: "POST" }),
};
