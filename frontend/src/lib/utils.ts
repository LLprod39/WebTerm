import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
export function cn(...values: ClassValue[]) {
  return twMerge(clsx(values));
}
export function formatDate(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "—"
    : new Intl.DateTimeFormat("ru", {
        dateStyle: "short",
        timeStyle: "short",
      }).format(date);
}
export function formatNumber(value?: number | null) {
  return value == null ? "—" : new Intl.NumberFormat("ru").format(value);
}
export function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : "Не удалось выполнить запрос";
}
export function downloadText(
  name: string,
  content: string,
  type = "text/plain",
) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}
