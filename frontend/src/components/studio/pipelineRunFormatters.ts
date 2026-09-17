import { localize } from "@/lib/i18n";

export function formatRunDuration(seconds: number | null, lang = "en"): string {
  if (seconds == null) return "—";
  const roundedSeconds = Math.max(0, Math.round(seconds));
  if (roundedSeconds < 60) return localize(lang, `${roundedSeconds} с`, `${roundedSeconds}s`);
  const minutes = Math.floor(roundedSeconds / 60);
  const restSeconds = roundedSeconds % 60;
  return localize(lang, `${minutes} мин ${restSeconds} с`, `${minutes}m ${restSeconds}s`);
}

export function formatRunDate(iso: string | null, lang = "ru"): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(lang === "ru" ? "ru-RU" : "en-US", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}
