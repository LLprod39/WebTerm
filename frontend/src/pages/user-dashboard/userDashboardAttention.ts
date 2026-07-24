import type { AttentionItem } from "@/components/dashboard/AttentionPanel";
import { isRunFailure } from "@/lib/runStatus";
import { localize } from "@/lib/i18n";
import type { UserDashboardData } from "./useUserDashboardData";

export function buildUserAttentionItems(
  runs: UserDashboardData["runs"],
  mon: UserDashboardData["mon"],
  lang: string,
): AttentionItem[] {
  const attentionItems: AttentionItem[] = [];
  for (const run of runs?.active ?? []) {
    if (run.pending_question) {
      attentionItems.push({
        id: `run-question-${run.id}`,
        severity: "warning",
        title: `${localize(lang, "Агент ждёт вашего ответа", "Agent is waiting for your reply")}: ${run.agent_name}`,
        detail: run.pending_question,
        time: run.started_at,
        action: { label: localize(lang, "Ответить", "Reply"), to: `/agents/run/${run.id}` },
      });
    }
  }
  for (const server of mon?.servers ?? []) {
    // Ignore stale/unknown and rows that still carry last metrics — not confirmed outages.
    const hasMetrics =
      typeof server.cpu_percent === "number" ||
      typeof server.memory_percent === "number" ||
      typeof server.disk_percent === "number";
    if (server.status === "unreachable" && !server.is_stale && !hasMetrics) {
      attentionItems.push({
        id: `srv-unreachable-${server.server_id}`,
        severity: "critical",
        title: `${localize(lang, "Сервер недоступен", "Server unreachable")}: ${server.server_name}`,
        detail: server.host,
        time: server.checked_at,
        action: { label: localize(lang, "К серверам", "Servers"), to: "/servers" },
      });
    }
  }
  for (const alert of (mon?.alerts ?? []).filter((a) => !a.is_resolved).slice(0, 6)) {
    attentionItems.push({
      id: `alert-${alert.id}`,
      severity: alert.severity === "critical" ? "critical" : alert.severity === "warning" ? "warning" : "info",
      title: alert.title,
      detail: `${alert.server_name} · ${alert.message}`,
      time: alert.created_at,
      action: { label: localize(lang, "Терминал", "Terminal"), to: `/servers/${alert.server_id}/terminal` },
    });
  }
  for (const run of (runs?.recent ?? []).filter((r) => isRunFailure(r.status)).slice(0, 4)) {
    attentionItems.push({
      id: `run-failed-${run.id}`,
      severity: "warning",
      title: `${localize(lang, "Сбой агента", "Agent run failed")}: ${run.agent_name}`,
      detail: `${localize(lang, "сервер", "server")}: ${run.server_name}`,
      time: run.started_at,
      action: { label: localize(lang, "Разбор", "Inspect"), to: `/agents/run/${run.id}` },
    });
  }
  return attentionItems;
}
