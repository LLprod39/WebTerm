import { expect, test } from "@playwright/test";
import { installApiHarness } from "./support/apiHarness";
import { FIXED_DATE, runtimeOverview } from "./support/agentsMockShared";
import { makeAgentsHandler } from "./support/agentsHandlers";

test("cleans stale run from the live run page", async ({ page }) => {
  const harness = await installApiHarness(
    page,
    makeAgentsHandler(
      [
        {
          id: 216,
          name: "Stale Rollout",
          mode: "full",
          agent_type: "custom",
          agent_type_display: "Custom",
          server_count: 1,
          last_run_at: FIXED_DATE,
          schedule_minutes: 0,
          max_iterations: 20,
          goal: "Recover stale worker queue",
          active_run_id: 906,
          last_run_id: 906,
        },
      ],
      {
        runtimeOverview: runtimeOverview({
          status: "needs_attention",
          severity: "warning",
          summary: {
            configured_agents: 1,
            active_runs: 1,
            pending_runs: 1,
            running_runs: 0,
            waiting_runs: 0,
            queued_dispatches: 1,
            claimed_dispatches: 0,
            scheduled_agents: 0,
            scheduled_due_now: 0,
            issues: 1,
          },
          items: {
            active_runs: [
              {
                run_id: 906,
                agent_id: 216,
                agent_name: "Stale Rollout",
                agent_mode: "full",
                server_id: 1,
                server_name: "Web-01",
                status: "pending",
                started_at: FIXED_DATE,
                completed_at: null,
                age_seconds: 300,
                duration_ms: 0,
                pending_question: "",
                is_stale_candidate: true,
                dispatch: null,
              },
            ],
            queued_dispatches: [
              {
                dispatch_id: 32,
                run_id: 906,
                agent_id: 216,
                agent_name: "Stale Rollout",
                agent_mode: "full",
                server_id: 1,
                server_name: "Web-01",
                dispatch_kind: "launch",
                status: "queued",
                server_ids: [1],
                queued_at: FIXED_DATE,
                claimed_at: null,
                heartbeat_at: null,
                lease_expires_at: null,
                queued_age_seconds: 300,
                lease_seconds_left: null,
                claimed_by: "",
                attempt_count: 0,
                error: "",
              },
            ],
            scheduled_due: [],
            stale_candidates: [
              {
                run_id: 906,
                agent_id: 216,
                agent_name: "Stale Rollout",
                agent_mode: "full",
                server_id: 1,
                server_name: "Web-01",
                status: "pending",
                started_at: FIXED_DATE,
                completed_at: null,
                age_seconds: 300,
                duration_ms: 0,
                pending_question: "",
                is_stale_candidate: true,
                dispatch: null,
              },
            ],
          },
        }),
      },
    ),
  );

  await page.goto("/agents/run/906");
  await expect(page.locator("h1", { hasText: "Stale Rollout" })).toBeVisible();
  await expect(page.getByText("Запуск завис в очереди").first()).toBeVisible();
  await expect(page.getByText("Runtime").first()).toBeVisible();
  await expect(page.getByText("Stale after").first()).toBeVisible();
  await expect(page.getByRole("button", { name: /Скопировать действие/ })).toBeVisible();

  await page.getByRole("button", { name: /Очистить stale/ }).first().click();
  await expect.poll(() => harness.getCalls("/servers/api/agents/runtime/cleanup-stale/", "POST").length).toBe(1);
  await expect(page.getByText("Очищено stale-запусков: 1; отменено dispatch: 1.")).toBeVisible();
  await expect(page.getByRole("button", { name: /Очистить stale/ })).toHaveCount(0);
});

test("downloads completed run artifacts as a server bundle", async ({ page }) => {
  const harness = await installApiHarness(
    page,
    makeAgentsHandler(
      [
        {
          id: 217,
          name: "Completed Report",
          mode: "full",
          agent_type: "custom",
          agent_type_display: "Custom",
          server_count: 1,
          last_run_at: FIXED_DATE,
          schedule_minutes: 0,
          max_iterations: 20,
          goal: "Inspect artifact bundle",
          active_run_id: null,
          last_run_id: 908,
        },
      ],
      { completedRunIds: [908] },
    ),
  );

  await page.goto("/agents/run/908");
  await expect(page.locator("h1", { hasText: "Completed Report" })).toBeVisible();
  await expect(page.getByText("Доставка:").first()).toBeVisible();
  await expect(page.getByText("Доставлено").first()).toBeVisible();
  await page.getByRole("tab", { name: /Материалы/ }).click();
  await page.getByRole("button", { name: /Файлы/ }).first().click();
  await expect(page.getByText("Артефакты отчёта готовы")).toBeVisible();
  await expect(page.getByText("3 файлов · 3.0 KB")).toBeVisible();
  await expect(page.getByText("manifest проверен")).toBeVisible();
  await expect(page.getByText("artifact-manifest.json")).toBeVisible();
  await expect(page.getByText("sha256:aaaaaaaaaaaa")).toBeVisible();
  await page.getByRole("button", { name: "Скачать всё" }).click();
  await expect.poll(() => harness.getCalls("/servers/api/agents/runs/908/artifacts/download-all/", "GET").length).toBe(1);
  expect(harness.getCalls("/servers/api/agents/runs/908/artifacts/51/download/", "GET")).toHaveLength(0);
});

test("retries failed report delivery from the run page", async ({ page }) => {
  const harness = await installApiHarness(
    page,
    makeAgentsHandler(
      [
        {
          id: 218,
          name: "Failed Delivery Report",
          mode: "full",
          agent_type: "custom",
          agent_type_display: "Custom",
          server_count: 1,
          last_run_at: FIXED_DATE,
          schedule_minutes: 0,
          max_iterations: 20,
          goal: "Retry report delivery",
          active_run_id: null,
          last_run_id: 910,
        },
      ],
      { completedRunIds: [910], deliveryStatusByRunId: { 910: "failed" } },
    ),
  );

  await page.goto("/agents/run/910");
  await expect(page.locator("h1", { hasText: "Failed Delivery Report" })).toBeVisible();
  await expect(page.getByText("Доставка в Telegram завершилась ошибкой HTTP 503.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Повторить" })).toBeVisible();
  await page.getByRole("button", { name: "Повторить" }).click();
  await expect.poll(() => harness.getCalls("/servers/api/agents/runs/910/report/deliver/", "POST").length).toBe(1);
  await expect(page.getByText("Доставка отчёта запущена повторно.")).toBeVisible();
  await expect(page.getByText("Доставлено").first()).toBeVisible();
});
