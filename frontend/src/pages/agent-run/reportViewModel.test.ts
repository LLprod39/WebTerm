import { describe, expect, it } from "vitest";

import type {
  AgentRunReportV2Indicator,
  AgentRunReportV2Response,
} from "@/api/agent-report-v2-types";

import { createReportViewModel } from "./reportViewModel";

const FIXED_AT = "2026-08-25T13:33:00.000Z";

function indicator(
  overrides: Partial<AgentRunReportV2Indicator> & Pick<AgentRunReportV2Indicator, "id" | "label" | "value">,
): AgentRunReportV2Indicator {
  return {
    id: overrides.id,
    role: "supporting",
    label: overrides.label,
    value: overrides.value,
    value_kind: "count",
    unit: "",
    numerator: null,
    denominator: null,
    tone: "info",
    priority: 10,
    evidence_refs: [],
    ...overrides,
  };
}

function report2156(overrides: Partial<AgentRunReportV2Response> = {}): AgentRunReportV2Response {
  const report: AgentRunReportV2Response = {
    success: true,
    schema_version: 2,
    run: {
      id: 2156,
      agent_id: 301,
      agent_name: "Проверка логов",
      agent_type: "log_audit",
      agent_mode: "full",
      server_id: 17,
      server_name: "nikitavm",
    },
    lifecycle: {
      status: "failed",
      label: "Техническое выполнение завершилось ошибкой",
      is_active: false,
      is_terminal: true,
      started_at: "2026-08-25T13:29:26.000Z",
      completed_at: FIXED_AT,
      duration_ms: 214_000,
      can_cleanup: false,
    },
    outcome: {
      status: "partial",
      label: "Проверка завершена частично",
      reason: "Проверены логи только 2 из 21 контейнера.",
      exit_reason: "LLM call failed after evidence collection",
      source: "structured_fallback",
      severity: "warning",
      details: "Нельзя делать вывод об остальных 19 контейнерах.",
    },
    evidence_state: {
      status: "partial",
      label: "Неполный охват",
      summary: "Собраны доказательства по двум контейнерам.",
      coverage: {
        checked: 2,
        total: 21,
        unit: "контейнер",
        ratio: 2 / 21,
      },
    },
    report_generation: {
      status: "ready_with_fallback",
      label: "Резервный отчёт готов",
      ready: true,
      error: "LLM call failed",
      generated_at: FIXED_AT,
    },
    delivery: {
      enabled: true,
      configured: false,
      channel: "telegram",
      status: "blocked",
      label: "Telegram не настроен",
      description: "Не указаны bot token или chat id.",
      target: "",
      severity: "warning",
      can_retry: false,
      blocked_reason: "telegram_not_configured",
      setup_url: "/settings/notifications",
      next_action: "Настроить Telegram",
      updated_at: FIXED_AT,
      attempt_count: 0,
      last_attempt_at: null,
    },
    indicators: [
      indicator({
        id: "outcome",
        role: "outcome",
        label: "Результат",
        value: "Частично выполнено",
        value_kind: "status",
        tone: "warning",
        priority: 0,
      }),
      indicator({
        id: "report_delivery",
        role: "report_delivery",
        label: "Отчёт и доставка",
        value: "Готов через fallback",
        value_kind: "status",
        tone: "warning",
        priority: 0,
      }),
      indicator({
        id: "coverage",
        label: "Охват проверки",
        value: "2/21",
        value_kind: "ratio",
        unit: "контейнер",
        numerator: 2,
        denominator: 21,
        tone: "warning",
        priority: 1,
        evidence_refs: [{ kind: "event", ref: "event-137", label: "Граница охвата", href: "" }],
      }),
      indicator({
        id: "tool-activity",
        label: "Операции инструментов",
        value: "6",
        unit: "операций",
        tone: "success",
        priority: 2,
      }),
    ],
    findings: [
      {
        id: "finding-coverage",
        kind: "finding",
        title: "19 контейнеров не проверены",
        description: "Критические ошибки могли остаться необнаруженными.",
        severity: "high",
        confidence: "reported",
        scope: "Docker logs, last 24h",
        evidence_refs: [{ kind: "event", ref: "event-137", label: "Событие охвата", href: "" }],
      },
    ],
    actions: [
      {
        id: "action-open-evidence",
        title: "Открыть доказательство",
        description: "Проверить событие, которое зафиксировало неполный охват.",
        priority: "high",
        status: "pending",
        owner: "operator",
        safety: "read_only",
        evidence_refs: [{ kind: "event", ref: "event-137", label: "Событие охвата", href: "" }],
        cta: {
          type: "open_evidence",
          label: "Открыть событие",
          ref: "event-137",
          href: "/agents/run/2156?tab=evidence&view=events&evidence=event-137",
          enabled: true,
        },
      },
    ],
    phases: [
      { id: "goal", label: "Цель", status: "completed", count: 1, important: 1, problems: 0, started_at: FIXED_AT, completed_at: FIXED_AT },
      { id: "action", label: "Действия", status: "completed", count: 6, important: 2, problems: 0, started_at: FIXED_AT, completed_at: FIXED_AT },
      { id: "observation", label: "Наблюдения", status: "problem", count: 2, important: 2, problems: 1, started_at: FIXED_AT, completed_at: FIXED_AT },
      { id: "conclusion", label: "Вывод", status: "problem", count: 1, important: 1, problems: 1, started_at: FIXED_AT, completed_at: FIXED_AT },
    ],
    counts: {
      events_total: 46,
      important_events: 9,
      execution_problem_events: 1,
      delivery_problem_events: 1,
      findings: 1,
      risks: 0,
      actions: 1,
      activities_total: 6,
      activities_succeeded: 6,
      activities_failed: 0,
      activities_unknown: 0,
      artifacts: 5,
    },
    report_revision: "2156-v2-r1",
    event_high_watermark: {
      sequence_no: 46,
      total: 46,
      updated_at: FIXED_AT,
    },
    document: {
      available: true,
      title: "Полный отчёт проверки логов",
      content_type: "text/markdown",
      size_bytes: 4_096,
      size_label: "4 KB",
      checksum_sha256: "a".repeat(64),
      preview: "# Частичная проверка логов\n\nПроверено 2 из 21 контейнера.",
      preview_truncated: false,
      detail_url: "/servers/api/agents/runs/2156/report/document/",
      download_url: "/servers/api/agents/runs/2156/report/document/?download=1",
    },
    evidence_links: {
      events: "/servers/api/agents/runs/2156/events/v2/",
      activity: "/servers/api/agents/runs/2156/activity/",
      artifacts: "/servers/api/agents/runs/2156/artifacts/",
      audit_export: "/servers/api/agents/runs/2156/report/audit/",
    },
    updated_at: FIXED_AT,
  };

  return { ...report, ...overrides };
}

describe("schema-driven agent report view model", () => {
  it("keeps partial outcome, LLM fallback, coverage, tools, and blocked Telegram as separate facts", () => {
    const viewModel = createReportViewModel(report2156());

    expect(viewModel.sourceVersion).toBe("v2");
    expect(viewModel.header).toMatchObject({
      statusLabel: "Проверка завершена частично",
      statusTone: "warning",
      summary: "Проверены логи только 2 из 21 контейнера.",
    });
    expect(Object.fromEntries(viewModel.axes.map((axis) => [axis.id, axis.value]))).toEqual({
      lifecycle: "Техническое выполнение завершилось ошибкой",
      outcome: "Проверка завершена частично",
      evidence: "Неполный охват",
      generation: "Резервный отчёт готов",
      delivery: "Telegram не настроен",
    });
    expect(viewModel.indicators.map((item) => item.id)).toEqual([
      "outcome",
      "report-delivery",
      "coverage",
      "tool-activity",
    ]);
    expect(viewModel.indicators.find((item) => item.id === "coverage")).toMatchObject({
      value: "2/21",
      numerator: 2,
      denominator: 21,
    });
    expect(viewModel.counts.activities).toBe(6);
    expect(viewModel.delivery).toMatchObject({
      status: "blocked",
      canRetry: false,
      setupUrl: "/settings/notifications",
    });
    expect(JSON.stringify(viewModel)).not.toContain("7/7");
  });

  it("creates evidence deep links and keeps read-only CTAs out of confirmation dialogs", () => {
    const viewModel = createReportViewModel(report2156());

    expect(viewModel.findings[0].evidence[0]).toMatchObject({
      view: "events",
      targetId: "event-137",
      href: "/agents/run/2156?tab=evidence&view=events&evidence=event-137",
    });
    expect(viewModel.actions[0].cta).toMatchObject({
      kind: "open_evidence",
      label: "Открыть событие",
      target: "/agents/run/2156?tab=evidence&view=events&evidence=event-137",
      isMutation: false,
      requiresConfirmation: false,
    });
  });

  it.each([
    ["custom-domain-01", "Ошибки в логах", "3", "записей"],
    ["custom-domain-02", "Этап развёртывания", "canary", ""],
    ["custom-domain-03", "Критические уязвимости", "1", "CVE"],
    ["custom-domain-04", "Возраст точки восстановления", "17 мин", ""],
  ])("renders %s from the schema without metric-name-specific mapping", (id, label, value, unit) => {
    const domainIndicator = indicator({ id, label, value, unit, priority: 1 });
    const viewModel = createReportViewModel(report2156({ indicators: [domainIndicator] }));

    expect(viewModel.indicators.find((item) => item.id === id)).toMatchObject({
      id,
      label,
      value,
      unit,
    });
  });
});
