import { backendPath, type AgentRunReportArtifact, type AgentRunReportResponse, type AgentRunReportSeverity } from "@/lib/api";
import type { StatusTone } from "@/design/status";


/** Simplified report IA: Итог · Ход · Материалы */
export type ReportTab = "summary" | "progress" | "materials";

export type MaterialsSection = "events" | "logs" | "artifacts";

export const severityTone: Record<AgentRunReportSeverity, StatusTone> = {
  success: "success",
  info: "info",
  warning: "warning",
  high: "warning",
  critical: "danger",
  fatal: "danger",
};

export const severityLabel: Record<AgentRunReportSeverity, string> = {
  success: "OK",
  info: "Info",
  warning: "Warning",
  high: "High",
  critical: "Critical",
  fatal: "Fatal",
};

export const EVENT_PAGE_SIZE = 60;
export const LOG_PAGE_SIZE = 30;

export const eventModeLabel = {
  brief: "Важные",
  all: "Все",
  debug: "Debug",
};

export const eventPhaseLabel: Record<string, string> = {
  queued: "Очередь",
  starting: "Старт",
  planning: "Планирование",
  plan_review: "Подтверждение",
  executing: "Выполнение",
  waiting: "Ожидание",
  synthesizing: "Отчёт",
  delivery: "Доставка",
  ready: "Готово",
  failed: "Ошибка",
  stopped: "Остановлен",
  activity: "Активность",
};

export const eventCategoryLabel: Record<string, string> = {
  agent: "Агент",
  command: "Команды",
  dispatch: "Dispatch",
  report: "Отчёт",
  system: "Система",
  task: "Задачи",
  worker: "Worker",
};
export function saveBlob(name: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name || "agent-run-artifact.txt";
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export function downloadTextFile(name: string, content: string, contentType: string) {
  saveBlob(name, new Blob([content || ""], { type: contentType || "text/plain;charset=utf-8" }));
}

export async function downloadArtifact(artifact: AgentRunReportArtifact) {
  if (artifact.download_url) {
    const response = await fetch(backendPath(artifact.download_url), { credentials: "include" });
    if (!response.ok) {
      throw new Error(`Не удалось скачать ${artifact.name}: HTTP ${response.status}`);
    }
    saveBlob(artifact.name, await response.blob());
    return;
  }
  downloadTextFile(artifact.name, artifact.content, artifact.content_type);
}

export async function downloadArtifactBundle(report: AgentRunReportResponse) {
  const url = report.artifact_state?.bundle_download_url;
  if (!url) return false;
  const response = await fetch(backendPath(url), { credentials: "include" });
  if (!response.ok) {
    throw new Error(`Не удалось скачать пакет артефактов: HTTP ${response.status}`);
  }
  saveBlob(`agent-run-${report.run.id}-artifacts.zip`, await response.blob());
  return true;
}

export async function copyText(value: string) {
  await navigator.clipboard?.writeText(value);
}

export function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function stripLeadingTitleHeading(markdown: string, title: string) {
  const normalizedTitle = title.trim();
  if (!markdown || !normalizedTitle) return markdown;
  return markdown.replace(new RegExp(`^#\\s+${escapeRegExp(normalizedTitle)}\\s*\\n+`, "i"), "");
}

export function cleanInlineMarkdown(value: string) {
  return String(value || "")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    // orphaned bold/heading markers left by unbalanced markdown ("*Статус:**")
    .replace(/\*{2,}/g, "")
    .replace(/^[\s*_#>-]+(?=\S)/, "")
    .replace(/[\s*_]+$/, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** True when the text carries real content — filters out "--", "***" and similar parsing leftovers. */
export function isMeaningfulReportText(value: string) {
  const cleaned = cleanInlineMarkdown(value);
  return cleaned.length > 1 && !/^[-—–_.:\s]+$/.test(cleaned);
}

export function primaryOutcomeSummary(report: AgentRunReportResponse) {
  return (
    cleanInlineMarkdown(report.report.root_cause || "") ||
    cleanInlineMarkdown(report.report.summary) ||
    cleanInlineMarkdown(report.report_state?.headline || "") ||
    cleanInlineMarkdown(report.report_state?.description || "") ||
    "Отчёт пока формируется."
  );
}

/**
 * Single human status for the page header — not dual run+severity badges.
 */
export function unifiedRunStatus(report: AgentRunReportResponse): { label: string; tone: StatusTone; pulse?: boolean } {
  const status = report.run.status;
  if (status === "waiting") return { label: "Ждёт вас", tone: "warning", pulse: true };
  if (status === "plan_review") return { label: "Нужно подтверждение", tone: "ai", pulse: true };
  if (status === "running") return { label: "Выполняется", tone: "info", pulse: true };
  if (status === "pending") return { label: "В очереди", tone: "neutral", pulse: true };
  if (status === "paused") return { label: "На паузе", tone: "warning" };
  if (status === "failed") return { label: "Ошибка", tone: "danger" };
  if (status === "stopped") return { label: "Остановлен", tone: "neutral" };

  // completed / terminal success path — severity tells if it was clean
  const sev = report.report.severity;
  if (sev === "critical" || sev === "fatal") return { label: "Проблема", tone: "danger" };
  if (sev === "high" || sev === "warning") return { label: "С замечаниями", tone: "warning" };
  if (sev === "success") return { label: "Успех", tone: "success" };
  return { label: "Завершён", tone: "success" };
}

export function problemCount(report: AgentRunReportResponse) {
  return report.report.findings.filter((item) => _severityRank(item.severity) >= _severityRank("warning")).length
    + report.report.risks.filter((item) => _severityRank(item.severity) >= _severityRank("warning")).length;
}

export function actionCount(report: AgentRunReportResponse) {
  return report.report.recommendations.filter((item) => isMeaningfulReportText(item.description || item.title)).length;
}

export function riskLabel(report: AgentRunReportResponse) {
  if (report.report.severity === "success" && !report.report.risks.length) return "OK";
  return severityLabel[report.report.severity] || report.report.severity || "Info";
}

export function reportSignalCount(report: AgentRunReportResponse) {
  const signalKpi = report.report.kpis.find((item) => {
    const id = String(item.id || "").toLowerCase();
    const label = String(item.label || "").toLowerCase();
    return id.includes("signal") || id.includes("сигнал") || label.includes("signal") || label.includes("сигнал");
  });
  const parsed = Number(String(signalKpi?.value || "").replace(/[^\d]/g, ""));
  if (Number.isFinite(parsed) && parsed > 0) return parsed;
  return report.events.length + report.logs.length;
}

export function diagnosticProblem(report: AgentRunReportResponse) {
  const severeFinding = [...report.report.findings]
    .sort((a, b) => _severityRank(b.severity) - _severityRank(a.severity))
    .find((item) => cleanInlineMarkdown(item.title));
  return (
    cleanInlineMarkdown(report.report.root_cause || "") ||
    cleanInlineMarkdown(severeFinding?.title || "") ||
    cleanInlineMarkdown(report.report.summary) ||
    cleanInlineMarkdown(report.report_state?.headline || "") ||
    "Причина пока не определена."
  );
}

export function diagnosticImpact(report: AgentRunReportResponse) {
  const risk = [...report.report.risks]
    .sort((a, b) => _severityRank(b.severity) - _severityRank(a.severity))
    .find((item) => cleanInlineMarkdown(item.title || item.description));
  return (
    cleanInlineMarkdown(risk?.description || "") ||
    cleanInlineMarkdown(risk?.title || "") ||
    cleanInlineMarkdown(report.report.subtitle) ||
    cleanInlineMarkdown(report.report_state?.next_expected || "") ||
    "Влияние пока не выделено."
  );
}

export function diagnosticActions(report: AgentRunReportResponse) {
  const actions = report.report.recommendations
    .map((item) => cleanInlineMarkdown(item.description || item.title))
    .filter((text) => isMeaningfulReportText(text));
  if (actions.length) return actions;
  const nextExpected = cleanInlineMarkdown(report.report_state?.next_expected || "");
  return isMeaningfulReportText(nextExpected) ? [nextExpected] : [];
}

export function diagnosticEvidenceItems(report: AgentRunReportResponse) {
  const fromFindings = report.report.findings.map((item, index) => ({
    text: cleanInlineMarkdown(item.description || item.title),
    time: evidenceTime(report.events[index]?.created_at || report.run.completed_at || report.run.started_at),
    severity: item.severity,
  }));
  const findings = fromFindings.filter((item) => item.text);
  if (findings.length) return findings;

  const fromEvents = report.events.filter((event) => event.important).map((event) => ({
    text: cleanInlineMarkdown(event.summary || event.title || event.message),
    time: evidenceTime(event.created_at),
    severity: event.severity,
  }));
  const events = fromEvents.filter((item) => item.text);
  if (events.length) return events;

  return report.logs.map((log) => ({
    text: cleanInlineMarkdown(log.stderr || log.stdout || log.command || log.title),
    time: evidenceTime(log.timestamp || report.run.completed_at || report.run.started_at),
    severity: log.severity,
  })).filter((item) => item.text);
}

export function evidenceTime(value?: string | null) {
  if (!value) return "—";
  return new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(value));
}
export function eventDot(severity: AgentRunReportSeverity) {
  switch (severityTone[severity]) {
    case "success":
      return "bg-success";
    case "warning":
      return "bg-warning";
    case "danger":
      return "bg-destructive";
    case "info":
      return "bg-info";
    default:
      return "bg-muted-foreground";
  }
}

export function _severityRank(severity: AgentRunReportSeverity) {
  switch (severity) {
    case "success":
      return 0;
    case "info":
      return 1;
    case "warning":
      return 2;
    case "high":
      return 3;
    case "critical":
      return 4;
    case "fatal":
      return 5;
    default:
      return 1;
  }
}

export function toneBox(severity: AgentRunReportSeverity) {
  switch (severityTone[severity]) {
    case "success":
      return "border-success/30 bg-success/10 text-success";
    case "warning":
      return "border-warning/35 bg-warning/10 text-warning";
    case "danger":
      return "border-destructive/35 bg-destructive/10 text-destructive";
    case "info":
      return "border-info/35 bg-info/10 text-info";
    default:
      return "border-border/70 bg-secondary/50 text-muted-foreground";
  }
}

export function toneBoxFromStatusTone(tone: StatusTone) {
  switch (tone) {
    case "success":
      return "border-success/30 bg-success/10 text-success";
    case "warning":
      return "border-warning/35 bg-warning/10 text-warning";
    case "danger":
      return "border-destructive/35 bg-destructive/10 text-destructive";
    case "info":
      return "border-info/35 bg-info/10 text-info";
    default:
      return "border-border/70 bg-secondary/50 text-muted-foreground";
  }
}
