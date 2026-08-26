import { expect, test, type Page } from "@playwright/test";

import type {
  AgentRunActivityV2Response,
  AgentRunReportEventsV2Response,
  AgentRunReportV2Response,
} from "../src/api/agent-report-v2-types";
import { installApiHarness, json } from "./support/apiHarness";
import { collectSeriousAndCriticalViolations, expectViolationsWithinBudget } from "./support/a11y";
import { makeAgentsHandler } from "./support/agentsHandlers";

const FIXED_AT = "2026-08-25T13:33:00.000Z";
const REPORT_PATH = "/servers/api/agents/runs/2156/report/v2/";
const EVENTS_PATH = "/servers/api/agents/runs/2156/events/";
const ACTIVITY_PATH = "/servers/api/agents/runs/2156/activity/";

const report2156: AgentRunReportV2Response = {
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
    coverage: { checked: 2, total: 21, unit: "контейнер", ratio: 2 / 21 },
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
    {
      id: "coverage",
      role: "primary",
      label: "Охват проверки",
      value: "2/21",
      value_kind: "ratio",
      unit: "контейнер",
      numerator: 2,
      denominator: 21,
      tone: "warning",
      priority: 1,
      evidence_refs: [{ kind: "event", ref: "event-137", label: "Граница охвата", href: "" }],
    },
    {
      id: "tool-activity",
      role: "supporting",
      label: "Операции инструментов",
      value: "6",
      value_kind: "count",
      unit: "операций",
      numerator: 6,
      denominator: null,
      tone: "success",
      priority: 2,
      evidence_refs: [],
    },
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
      title: "Проверить границу охвата",
      description: "Открыть событие и продолжить диагностику остальных контейнеров.",
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
  event_high_watermark: { sequence_no: 46, total: 46, updated_at: FIXED_AT },
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
    events: EVENTS_PATH,
    activity: ACTIVITY_PATH,
    artifacts: "/servers/api/agents/runs/2156/artifacts/",
    audit_export: "/servers/api/agents/runs/2156/report/audit/",
  },
  updated_at: FIXED_AT,
};

const eventResponse: AgentRunReportEventsV2Response = {
  success: true,
  items: [
    {
      id: "event-137",
      sequence_no: 41,
      event_type: "agent_scope_partial",
      title: "Контейнеры проверены частично",
      summary: "Проверено 2 из 21; mini-prod-kubernetes-ops-sync завершился с кодом 137.",
      message: "coverage partial",
      severity: "high",
      phase: "executing",
      category: "docker",
      source: "agent",
      important: true,
      task_id: 7,
      payload: { checked: 2, total: 21, exit_code: 137 },
      created_at: "2026-08-25T13:32:40.000Z",
    },
    {
      id: "event-report",
      sequence_no: 46,
      event_type: "agent_report_fallback_ready",
      title: "Резервный отчёт сформирован",
      summary: "LLM call failed; structured fallback is ready.",
      message: "fallback ready",
      severity: "warning",
      phase: "conclusion",
      category: "report",
      source: "report",
      important: true,
      task_id: null,
      payload: { generation: "ready_with_fallback" },
      created_at: FIXED_AT,
    },
  ],
  page: { limit: 50, direction: "older", next_cursor: null, prev_cursor: null, has_more: false },
  total: 46,
  filters: {},
  event_watermark: 46,
  integrity: { complete: true },
};

const activityResponse: AgentRunActivityV2Response = {
  success: true,
  items: Array.from({ length: 6 }, (_, index) => ({
    id: `tool-${index + 1}`,
    ordinal: index + 1,
    kind: "tool" as const,
    status: "succeeded",
    success: true,
    title: index === 0 ? "Подключиться к серверу" : `Проверить контейнер ${index + 1}`,
    summary: index === 0 ? "SSH-соединение установлено." : "Команда завершена; данные сохранены как доказательство.",
    tool: index === 0 ? "open_connection" : "ssh_execute",
    server: "nikitavm",
    command: index === 0 ? "ssh nikitavm" : `sudo docker logs container-${index + 1} --tail 200`,
    exit_code: 0,
    duration_ms: 1_000 + index * 100,
    started_at: FIXED_AT,
    completed_at: FIXED_AT,
    error: "",
    evidence_refs: index === 5 ? [{ kind: "event" as const, ref: "event-137", label: "Граница охвата", href: "" }] : [],
  })),
  page: { limit: 50, direction: "older", next_cursor: null, prev_cursor: null, has_more: false },
  total: 6,
  counts: { total: 6, succeeded: 6, failed: 0, unknown: 0 },
};

async function installReport2156(page: Page) {
  const fallback = makeAgentsHandler(
    [{
      id: 301,
      name: "Проверка логов",
      mode: "full",
      agent_type: "log_audit",
      agent_type_display: "Log audit",
      server_count: 1,
      last_run_at: FIXED_AT,
      schedule_minutes: 0,
      max_iterations: 20,
      goal: "Проверить Docker-логи за 24 часа",
      active_run_id: null,
      last_run_id: 2156,
    }],
    { completedRunIds: [2156] },
  );

  return installApiHarness(page, async (request) => {
    if (request.path === REPORT_PATH && request.method === "GET") return json(report2156);
    if (request.path === EVENTS_PATH && request.method === "GET") return json(eventResponse);
    if (request.path === ACTIVITY_PATH && request.method === "GET") return json(activityResponse);
    return fallback(request);
  }, "ru");
}

async function expectNoDocumentOverflow(page: Page, width: number) {
  const geometry = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(geometry.scrollWidth, `${width}px: ${JSON.stringify(geometry)}`).toBeLessThanOrEqual(geometry.clientWidth + 1);
}

test("renders #2156 as partial with fallback, 2/21 coverage, six tools, and blocked Telegram", async ({ page }) => {
  await installReport2156(page);
  await page.goto("/agents/run/2156?tab=result");

  const root = page.getByTestId("agent-report-v2");
  await expect(root).toBeVisible();
  await expect(page.getByRole("tablist", { name: "Разделы отчёта" })).toBeVisible();
  await expect(page.getByRole("tab", { name: /Результат/ })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("heading", { name: "Проверка логов" })).toBeVisible();
  await expect(root.getByText("Проверка завершена частично").first()).toBeVisible();

  const indicators = page.getByTestId("report-indicators");
  await expect(indicators.locator(":scope > *")).toHaveCount(4);
  await expect(indicators.locator("dd").filter({ hasText: /^2\/21/ })).toBeVisible();
  await expect(indicators).toContainText("6");
  await expect(root).not.toContainText("7/7");

  await expect(page.getByRole("link", { name: "Настроить Telegram" })).toHaveAttribute("href", "/settings/notifications");
  await expect(page.getByRole("button", { name: /Повторить/ })).toHaveCount(0);
  await expect(page.getByRole("dialog")).toHaveCount(0);

  await page.getByTestId("report-action").getByRole("link", { name: "Открыть событие" }).click();
  await expect(page).toHaveURL(/\/agents\/run\/2156\?tab=evidence&view=events&evidence=event-137$/);
  await expect(page.getByTestId("evidence-detail")).toContainText("Контейнеры проверены частично");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("keeps tabs, evidence selection, and filters in the URL and API requests", async ({ page }) => {
  const harness = await installReport2156(page);
  await page.goto("/agents/run/2156?tab=evidence&view=events&evidence=event-137&q=%D0%BA%D0%BE%D0%B4+137&severity=high&phase=executing&category=docker&important=true");

  await expect(page.getByRole("tab", { name: /Доказательства/ })).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("tablist", { name: "Виды доказательств" })).toBeVisible();
  await expect(page.getByLabel("Поиск по событиям")).toHaveValue("код 137");
  await expect(page.getByLabel("Важность")).toHaveValue("high");
  await expect(page.getByLabel("Фаза")).toHaveValue("executing");
  await expect(page.getByLabel("Только важные")).toBeChecked();
  await expect(page.getByTestId("evidence-detail")).toContainText("кодом 137");

  await expect.poll(() => harness.getCalls(EVENTS_PATH, "GET").at(-1)?.query).toMatchObject({
    q: "код 137",
    severity: "high",
    phase: "executing",
    category: "docker",
    important: "true",
  });

  await page.getByRole("tab", { name: /Выполнение/ }).click();
  await expect(page).toHaveURL(/tab=execution/);
  await page.getByLabel("Тип").selectOption("tool");
  await page.getByLabel("Статус").selectOption("succeeded");
  await expect(page).toHaveURL(/kind=tool/);
  await expect(page).toHaveURL(/status=succeeded/);
  await expect.poll(() => harness.getCalls(ACTIVITY_PATH, "GET").at(-1)?.query).toMatchObject({
    kind: "tool",
    status: "succeeded",
  });

  const progress = page.getByRole("progressbar", { name: "Обработанные операции" });
  await expect(progress).toHaveAttribute("aria-valuemin", "0");
  await expect(progress).toHaveAttribute("aria-valuemax", "6");
  await expect(progress).toHaveAttribute("aria-valuenow", "6");
  await expect(page.getByText("6 операций", { exact: true })).toBeVisible();
  for (const phase of ["goal", "action", "observation", "conclusion"]) {
    await expect(page.getByTestId(`execution-phase-${phase}`)).toBeVisible();
  }
});

test("reflows at 390px and 320px without document-level horizontal overflow", async ({ page }) => {
  await installReport2156(page);

  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/agents/run/2156?tab=result");
    await expect(page.getByTestId("agent-report-v2")).toBeVisible();
    await expectNoDocumentOverflow(page, width);

    await page.getByRole("tab", { name: /Выполнение/ }).click();
    await expect(page.getByRole("progressbar", { name: "Обработанные операции" })).toBeVisible();
    await expectNoDocumentOverflow(page, width);

    await page.getByRole("tab", { name: /Доказательства/ }).click();
    await expect(page.getByRole("tablist", { name: "Виды доказательств" })).toBeVisible();
    await expectNoDocumentOverflow(page, width);
  }
});

test("has semantic report navigation/search/progress and no serious or critical axe violations", async ({ page }) => {
  await installReport2156(page);
  await page.goto("/agents/run/2156?tab=result");
  await expect(page.getByTestId("agent-report-v2")).toBeVisible();

  await expect(page.getByRole("tablist", { name: "Разделы отчёта" })).toBeVisible();
  expectViolationsWithinBudget(await collectSeriousAndCriticalViolations(page), {});

  await page.getByRole("tab", { name: /Выполнение/ }).click();
  await expect(page.getByRole("progressbar", { name: "Обработанные операции" })).toBeVisible();
  expectViolationsWithinBudget(await collectSeriousAndCriticalViolations(page), {});

  await page.getByRole("tab", { name: /Доказательства/ }).click();
  await expect(page.getByLabel("Поиск по событиям")).toBeVisible();
  await expect(page.getByRole("tablist", { name: "Виды доказательств" })).toBeVisible();
  expectViolationsWithinBudget(await collectSeriousAndCriticalViolations(page), {});
});
