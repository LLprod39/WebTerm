import type { AdminDashboardData, MonitoringDashboard } from "@/api";
import type { AttentionItem } from "@/components/dashboard/AttentionPanel";
import { localize } from "@/lib/i18n";
import { shortProviderName } from "./adminDashboardFormatters";

export function buildAdminAttentionItems(
  d: AdminDashboardData,
  mon: MonitoringDashboard | undefined,
  lang: string,
): AttentionItem[] {
  const items: AttentionItem[] = [];
  const unreachableIds = new Set<number>();

  for (const server of mon?.servers ?? []) {
    if (server.status === "unreachable") {
      unreachableIds.add(server.server_id);
      items.push({
        id: `srv-unreachable-${server.server_id}`,
        severity: "critical",
        title: `${localize(lang, "Сервер недоступен", "Server unreachable")}: ${server.server_name}`,
        detail: server.host,
        time: server.checked_at,
        action: { label: localize(lang, "К серверам", "Servers"), to: "/servers" },
      });
    } else if (server.status === "critical") {
      items.push({
        id: `srv-critical-${server.server_id}`,
        severity: "critical",
        title: `${localize(lang, "Критическая нагрузка", "Critical load")}: ${server.server_name}`,
        detail: `CPU ${server.cpu_percent ?? "—"}% · RAM ${server.memory_percent ?? "—"}% · ${localize(lang, "Диск", "Disk")} ${server.disk_percent ?? "—"}%`,
        time: server.checked_at,
        action: { label: localize(lang, "Терминал", "Terminal"), to: `/servers/${server.server_id}/terminal` },
      });
    }
  }

  for (const alert of (mon?.alerts ?? []).filter((a) => !a.is_resolved)) {
    // A separate "unreachable" row already covers these servers.
    if (unreachableIds.has(alert.server_id) && alert.alert_type.toLowerCase().includes("unreachable")) continue;
    items.push({
      id: `alert-${alert.id}`,
      severity: alert.severity === "critical" ? "critical" : alert.severity === "warning" ? "warning" : "info",
      title: alert.title,
      detail: `${alert.server_name} · ${alert.message}`,
      time: alert.created_at,
      action: { label: localize(lang, "Терминал", "Terminal"), to: `/servers/${alert.server_id}/terminal` },
    });
  }

  if (d.agents?.failed_24h) {
    items.push({
      id: "agents-failed-24h",
      severity: "warning",
      title: localize(lang, `Сбои агентов за 24 ч: ${d.agents.failed_24h}`, `Agent failures in 24h: ${d.agents.failed_24h}`),
      detail: localize(lang, `Успешность запусков ${d.agents.success_rate}%`, `Run success rate ${d.agents.success_rate}%`),
      action: { label: localize(lang, "К агентам", "Agents"), to: "/agents" },
    });
  }

  for (const [provider, usage] of Object.entries(d.api_usage ?? {})) {
    if (usage.errors > 0) {
      items.push({
        id: `llm-errors-${provider}`,
        severity: "warning",
        title: `${localize(lang, "Ошибки LLM-провайдера", "LLM provider errors")}: ${shortProviderName(provider)} — ${usage.errors}`,
        detail: localize(lang, "Проверьте ключи, лимиты и доступность модели", "Check keys, limits and model availability"),
        action: { label: localize(lang, "Настройки AI", "AI settings"), to: "/settings/ai" },
      });
    }
  }

  return items;
}
