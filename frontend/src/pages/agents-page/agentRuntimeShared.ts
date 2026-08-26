import type { AgentExecutionReadiness, AgentItem, AgentRuntimeRunItem, BackgroundWorkerStateRecord } from "@/lib/api";
import { agentRunStatusPresentation } from "@/design/status";
import { localize } from "@/lib/i18n";
import { formatDuration } from "./agentPageUtils";


export function readinessTone(readiness?: AgentExecutionReadiness): "neutral" | "success" | "warning" | "danger" | "info" {
  if (!readiness?.required) return "neutral";
  if (readiness.ready) return "success";
  if (readiness.severity === "critical" || readiness.severity === "fatal") return "danger";
  if (readiness.severity === "warning" || readiness.severity === "high") return "warning";
  return "info";
}

export function workerStateTone(worker?: BackgroundWorkerStateRecord): "neutral" | "success" | "warning" | "danger" | "info" {
  if (!worker || worker.status === "missing") return "warning";
  if (worker.status === "error") return "danger";
  if (worker.is_stale) return "warning";
  if (worker.status === "running") return "success";
  if (worker.status === "stopped") return "warning";
  return "neutral";
}

export function runBlockedReason(agent: AgentItem, lang: "ru" | "en", options?: { isAdmin?: boolean }) {
  const readiness = agent.execution_readiness;
  if (readiness?.required && !readiness.ready) {
    if (options?.isAdmin) {
      return readiness.next_action || readiness.description || localize(lang, "Сервис запуска недоступен.", "Execution service is unavailable.");
    }
    // Operators should not see manage.py / ops commands — only a clear user-facing reason.
    return localize(
      lang,
      "Запуск временно недоступен. Попробуйте позже или обратитесь к администратору.",
      "Launch is temporarily unavailable. Try again later or contact an administrator.",
    );
  }
  if (agent.is_enabled === false) {
    return localize(lang, "Агент выключен.", "Agent is disabled.");
  }
  if (agent.server_count <= 0) {
    return localize(lang, "Выберите хотя бы один сервер.", "Select at least one server.");
  }
  return "";
}

export function formatWorkerTime(value: string | null | undefined, lang: "ru" | "en") {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(lang === "ru" ? "ru-RU" : "en-US");
}

export function workerSummaryEntries(summary: Record<string, unknown> | undefined) {
  return Object.entries(summary || {})
    .filter(([, value]) => value !== null && value !== undefined && ["string", "number", "boolean"].includes(typeof value))
    .slice(0, 6);
}

export function formatRuntimeAge(seconds: number | null | undefined) {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds <= 0) return "0s";
  return formatDuration(seconds * 1000);
}

export function severityTone(severity?: string): "neutral" | "success" | "warning" | "danger" | "info" {
  if (severity === "success") return "success";
  if (severity === "warning" || severity === "high") return "warning";
  if (severity === "critical" || severity === "fatal") return "danger";
  if (severity === "info") return "info";
  return "neutral";
}

export function runStatusLabel(status: string | null | undefined, lang: "ru" | "en") {
  switch (status) {
    case "running":
      return localize(lang, "Выполняется", "Running");
    case "pending":
      return localize(lang, "В очереди", "Queued");
    case "waiting":
      return localize(lang, "Ждёт ответа", "Needs answer");
    case "plan_review":
      return localize(lang, "План на проверке", "Plan review");
    case "paused":
      return localize(lang, "Пауза", "Paused");
    case "failed":
      return localize(lang, "Ошибка", "Failed");
    case "stopped":
      return localize(lang, "Остановлен", "Stopped");
    case "completed":
      return localize(lang, "Завершён", "Completed");
    default:
      return status || localize(lang, "Активен", "Active");
  }
}

export function activeRunStatus(run: AgentRuntimeRunItem | undefined, fallbackActiveRunId: number | null, lang: "ru" | "en") {
  const status = run?.status || (fallbackActiveRunId ? "running" : "");
  const presentation = agentRunStatusPresentation(status);
  return {
    status,
    label: runStatusLabel(status, lang),
    tone: presentation.tone === "ai" ? "info" : presentation.tone,
    pulse: Boolean(presentation.pulse || status === "waiting"),
  } as const;
}

