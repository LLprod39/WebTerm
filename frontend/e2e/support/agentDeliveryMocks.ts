import { FIXED_DATE } from "./agentsMockShared";
import { buildRunReport } from "./agentRunReportMocks";

export function applyDeliveryStatus(report: ReturnType<typeof buildRunReport>, status?: "sent" | "failed" | "skipped" | "pending") {
  if (!status || !report.delivery_state) return report;
  const variants = {
    sent: {
      status: "sent",
      severity: "success",
      label: "Доставлено",
      title: "Отчёт доставлен",
      description: "Отчёт отправлен в Telegram.",
      next_action: "",
      updated_at: FIXED_DATE,
    },
    failed: {
      status: "failed",
      severity: "critical",
      label: "Ошибка",
      title: "Доставка отчёта не удалась",
      description: "Доставка в Telegram завершилась ошибкой HTTP 503.",
      next_action: "Проверьте настройки канала и повторите отправку отчёта после исправления причины.",
      updated_at: FIXED_DATE,
    },
    skipped: {
      status: "skipped",
      severity: "warning",
      label: "Пропущено",
      title: "Доставка отчёта пропущена",
      description: "Доставка в Telegram пропущена: не настроены bot token или chat id.",
      next_action: "Настройте Telegram bot token и chat id или выключите доставку для агента.",
      updated_at: FIXED_DATE,
    },
    pending: {
      status: "pending",
      severity: "warning",
      label: "Ожидает",
      title: "Доставка ещё не подтверждена",
      description: "Финальный отчёт готов, но событие успешной доставки ещё не записано.",
      next_action: "Проверьте worker и настройки доставки отчёта.",
      updated_at: null,
    },
  } as const;
  report.delivery_state = {
    ...report.delivery_state,
    ...variants[status],
    event: status === "sent"
      ? {
          id: 9,
          run_id: report.run.id,
          event_type: "agent_report_delivery_sent",
          task_id: null,
          message: "Report delivered",
          payload: { channel: "telegram", chat_id: "***6789" },
          created_at: FIXED_DATE,
          severity: "success",
          source: "report",
          title: "Отчёт доставлен",
          summary: "Отчёт отправлен в Telegram.",
          phase: "delivery",
          category: "report",
          important: true,
        }
      : null,
  } as typeof report.delivery_state;
  return report;
}
