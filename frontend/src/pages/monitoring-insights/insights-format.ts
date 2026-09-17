import type { InsightPrediction, PredictionSeverity } from "@/api/monitoring-insights";

/** Badge tone used across the page for one severity vocabulary. */
export function severityTone(severity: PredictionSeverity): "danger" | "warning" | "info" {
  if (severity === "critical") return "danger";
  if (severity === "warning") return "warning";
  return "info";
}

export function formatEta(lang: string, etaDays: number | null): string {
  if (etaDays === null) return "";
  if (etaDays <= 0) return lang === "ru" ? "уже" : "now";
  if (etaDays < 1) {
    const hours = Math.max(1, Math.round(etaDays * 24));
    return lang === "ru" ? `~${hours} ч` : `~${hours} h`;
  }
  if (etaDays < 10) {
    const days = Math.round(etaDays * 10) / 10;
    return lang === "ru" ? `~${days} дн` : `~${days} d`;
  }
  return lang === "ru" ? `~${Math.round(etaDays)} дн` : `~${Math.round(etaDays)} d`;
}

export function formatBps(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  if (value >= 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB/s`;
  if (value >= 1024) return `${(value / 1024).toFixed(0)} KB/s`;
  return `${Math.round(value)} B/s`;
}

export function formatPercent(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `${value.toFixed(digits)}%`;
}

export function formatUptime(lang: string, seconds: number | null): string {
  if (!seconds || seconds <= 0) return "—";
  const days = Math.floor(seconds / 86400);
  if (days >= 1) return lang === "ru" ? `${days} дн` : `${days} d`;
  const hours = Math.floor(seconds / 3600);
  return lang === "ru" ? `${hours} ч` : `${hours} h`;
}

/** Human title for a prediction, e.g. «Диск /var заполнится до 90%». */
export function predictionTitle(lang: string, prediction: InsightPrediction): string {
  const ru = lang === "ru";
  const evidence = prediction.evidence || {};
  const mount = String(evidence.mount ?? prediction.target.split(":")[1] ?? "");
  const port = String(evidence.port ?? prediction.target.split(":")[1] ?? "");

  switch (prediction.kind) {
    case "disk_full":
      return ru
        ? `Диск ${mount} дойдёт до ${prediction.threshold ?? 100}%`
        : `Disk ${mount} will reach ${prediction.threshold ?? 100}%`;
    case "inode_full":
      return ru
        ? `Inode на ${mount} закончатся (${prediction.threshold ?? 100}%)`
        : `Inodes on ${mount} will hit ${prediction.threshold ?? 100}%`;
    case "memory_pressure":
      return ru ? "Память истощается (тренд к OOM)" : "Memory trending toward exhaustion";
    case "swap_growth":
      return ru ? "Swap растёт к пределу" : "Swap usage growing to its limit";
    case "log_error_surge":
      return ru ? "Всплеск ошибок в логах" : "Log error surge";
    case "cert_expiry": {
      const expired = Boolean(evidence.expired);
      if (expired) return ru ? `Сертификат :${port} истёк` : `Certificate :${port} expired`;
      return ru ? `Сертификат :${port} истекает` : `Certificate :${port} expires soon`;
    }
    case "cert_changed":
      return ru ? `Сертификат :${port} сменился` : `Certificate :${port} changed`;
    default:
      return prediction.kind;
  }
}

/** Secondary line: growth speed, ratios, subjects — the "why". */
export function predictionDetail(lang: string, prediction: InsightPrediction): string {
  const ru = lang === "ru";
  const evidence = prediction.evidence || {};
  const parts: string[] = [];

  if (prediction.kind === "disk_full" || prediction.kind === "inode_full" || prediction.kind === "swap_growth") {
    if (prediction.current_value !== null) {
      parts.push(ru ? `сейчас ${prediction.current_value.toFixed(1)}%` : `now ${prediction.current_value.toFixed(1)}%`);
    }
    if (typeof evidence.gb_per_day === "number") {
      parts.push(ru ? `+${evidence.gb_per_day} ГБ/день` : `+${evidence.gb_per_day} GB/day`);
    } else if (prediction.slope_per_day !== null) {
      parts.push(ru ? `+${prediction.slope_per_day.toFixed(1)}%/день` : `+${prediction.slope_per_day.toFixed(1)}%/day`);
    }
  } else if (prediction.kind === "memory_pressure") {
    if (prediction.current_value !== null) {
      parts.push(ru ? `доступно ${Math.round(prediction.current_value)} МБ` : `${Math.round(prediction.current_value)} MB available`);
    }
    if (prediction.slope_per_day !== null) {
      parts.push(ru ? `${Math.round(prediction.slope_per_day)} МБ/день` : `${Math.round(prediction.slope_per_day)} MB/day`);
    }
  } else if (prediction.kind === "log_error_surge") {
    if (typeof evidence.ratio === "number") {
      parts.push(ru ? `×${evidence.ratio} к базовому уровню` : `×${evidence.ratio} vs baseline`);
    }
    if (typeof evidence.recent_avg === "number") {
      parts.push(ru ? `${evidence.recent_avg}/10 мин` : `${evidence.recent_avg}/10 min`);
    }
  } else if (prediction.kind === "cert_expiry" || prediction.kind === "cert_changed") {
    const subject = String(evidence.subject ?? "").replace(/^CN\s*=\s*/i, "");
    if (subject) parts.push(subject);
    if (prediction.kind === "cert_expiry" && typeof evidence.not_after === "string") {
      parts.push(new Date(evidence.not_after).toLocaleDateString());
    }
  }

  return parts.join(" · ");
}
