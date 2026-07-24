import { localize } from "@/lib/i18n";

export const sectionToneStyles: Record<string, string> = {
  default: "",
  info: "border-primary/30 bg-primary/5",
  success: "border-success/25 bg-success/5",
  warning: "border-warning/25 bg-warning/5",
  danger: "border-destructive/25 bg-destructive/5",
};

export function pctTone(value: number): "default" | "warning" | "danger" {
  return value > 85 ? "danger" : value > 65 ? "warning" : "default";
}

export type StatusTone = "neutral" | "success" | "warning" | "danger" | "info";

export function alertSeverityLabel(severity: string, lang: string) {
  const key = severity.toLowerCase();
  if (key === "critical") return localize(lang, "Критично", "Critical");
  if (key === "warning") return localize(lang, "Внимание", "Warning");
  if (key === "info") return localize(lang, "Инфо", "Info");
  return severity;
}

export function alertTypeLabel(type: string, lang: string) {
  const key = type.toLowerCase();
  if (key === "server unreachable") return localize(lang, "Сервер недоступен", "Server unreachable");
  if (key === "unreachable") return localize(lang, "Сервер недоступен", "Unreachable");
  if (key === "service") return localize(lang, "Сервис", "Service");
  if (key === "resource") return localize(lang, "Ресурсы", "Resource");
  return type;
}

export function activityCategoryLabel(category: string, lang: string) {
  const key = category.toLowerCase();
  if (key === "auth") return localize(lang, "Вход", "Auth");
  if (key === "agent") return localize(lang, "Агент", "Agent");
  if (key === "server") return localize(lang, "Сервер", "Server");
  if (key === "other") return localize(lang, "Другое", "Other");
  return category;
}

export function activityActionLabel(action: string, lang: string) {
  const key = action.toLowerCase();
  if (key === "http_request") return localize(lang, "HTTP-запрос", "HTTP request");
  if (key === "login") return localize(lang, "Вход в систему", "Login");
  if (key === "logout") return localize(lang, "Выход", "Logout");
  return action;
}

export function formatChartHour(value: unknown) {
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value ?? "");
  return date.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

export function formatChartDay(lang: string, value: unknown) {
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value ?? "");
  return date.toLocaleDateString(lang === "ru" ? "ru-RU" : "en-GB", { day: "2-digit", month: "2-digit" });
}

export function shortProviderName(provider: string) {
  const key = provider.toLowerCase();
  if (key === "openai") return "OpenAI";
  if (key === "xai") return "xAI";
  return provider.charAt(0).toUpperCase() + provider.slice(1);
}
