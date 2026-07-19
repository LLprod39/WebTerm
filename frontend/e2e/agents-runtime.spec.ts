import { expect, test } from "@playwright/test";
import { installApiHarness } from "./support/apiHarness";
import { FIXED_DATE, runtimeOverview, workerState } from "./support/agentsMockShared";
import { makeAgentsHandler } from "./support/agentsHandlers";

test("shows scheduled agents worker runtime state", async ({ page }) => {
  await installApiHarness(
    page,
    makeAgentsHandler(
      [
        {
          id: 213,
          name: "Nightly Health",
          mode: "mini",
          agent_type: "custom",
          agent_type_display: "Custom",
          server_count: 1,
          last_run_at: FIXED_DATE,
          schedule_minutes: 15,
          schedule_config: { mode: "interval", interval_minutes: 15 },
          max_iterations: 20,
          goal: "Run health checks on a schedule",
          active_run_id: null,
          last_run_id: 900,
        },
      ],
      {
        workerStates: {
          scheduled_agents: workerState({
            status: "running",
            is_stale: false,
            hostname: "sched-worker-01",
            pid: 7331,
            heartbeat_at: FIXED_DATE,
            lease_expires_at: "2026-03-01T08:03:00.000Z",
            last_cycle_finished_at: FIXED_DATE,
            last_summary: { scanned: 4, due: 1, launched_agents: 1, skipped: 3 },
          }),
        },
      },
    ),
  );

  await page.goto("/agents");
  await expect(page.getByText("Nightly Health")).toBeVisible();
  await expect(page.getByText("Schedule worker").first()).toBeVisible();
  await expect(page.getByText("Scheduled agent dispatcher runtime")).toBeVisible();
  await expect(page.getByText("sched-worker-01")).toBeVisible();
  await expect(page.getByText("launched_agents: 1")).toBeVisible();
});

test("stops active agent run from list with explicit run id", async ({ page }) => {
  const harness = await installApiHarness(
    page,
    makeAgentsHandler([
      {
        id: 212,
        name: "Active Rollout",
        mode: "full",
        agent_type: "custom",
        agent_type_display: "Custom",
        server_count: 1,
        last_run_at: FIXED_DATE,
        schedule_minutes: 0,
        max_iterations: 20,
        goal: "Stop the active run from the list",
        active_run_id: 902,
        last_run_id: 902,
        execution_readiness: {
          required: true,
          ready: true,
          status: "running",
          severity: "success",
          title: "Execution worker готов",
          description: "Worker accepts full/multi runs.",
          next_action: "",
          worker: {
            worker_kind: "agent_execution",
            worker_key: "default",
            status: "running",
            is_stale: false,
            hostname: "worker-01",
            pid: 4242,
            command: "python manage.py run_agent_execution_plane",
            heartbeat_at: FIXED_DATE,
            lease_expires_at: "2026-03-01T08:03:00.000Z",
            last_started_at: FIXED_DATE,
            last_stopped_at: null,
            last_cycle_started_at: FIXED_DATE,
            last_cycle_finished_at: FIXED_DATE,
            last_summary: { processed: 3, completed: 3, failed: 0 },
            last_error: "",
          },
        },
      },
    ]),
  );

  await page.goto("/agents");
  await expect(page.getByText("Active Rollout")).toBeVisible();
  await expect(page.getByText("worker-01")).toBeVisible();
  await expect(page.getByText("processed: 3")).toBeVisible();
  await page.getByRole("button", { name: /^Stop$/ }).click();
  await expect.poll(() => harness.getCalls("/servers/api/agents/212/stop/", "POST").length).toBe(1);
  expect(harness.getCalls("/servers/api/agents/212/stop/", "POST")[0].body).toEqual({ run_id: 902 });
});

test("opens a live agent run and sends stop from the run page", async ({ page }) => {
  const harness = await installApiHarness(
    page,
    makeAgentsHandler([
      {
        id: 202,
        name: "Patch Rollout",
        mode: "full",
        agent_type: "custom",
        agent_type_display: "Custom",
        server_count: 1,
        last_run_at: FIXED_DATE,
        schedule_minutes: 0,
        max_iterations: 20,
        goal: "Roll out production patch safely",
        active_run_id: 901,
        last_run_id: 901,
      },
    ]),
  );

  await page.goto("/agents");
  await expect(page.getByText("Patch Rollout")).toBeVisible();
  await page.getByRole("link", { name: "Watch" }).click();

  await expect(page).toHaveURL(/\/agents\/run\/901$/);
  await expect(page.locator("h1", { hasText: "Patch Rollout" })).toBeVisible();
  // Simplified report shell: one status + live summary
  await expect(page.getByText("В работе").first()).toBeVisible();
  await expect(page.getByRole("tab", { name: /Итог/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: /Ход/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: /Материалы/ })).toBeVisible();

  const scrollRoot = page.locator("[data-agent-run-scroll]");
  await expect.poll(() => scrollRoot.evaluate((node) => node.scrollHeight > node.clientHeight)).toBe(true);
  await scrollRoot.evaluate((node) => {
    node.scrollTop = 0;
  });
  await scrollRoot.hover();
  await page.mouse.wheel(0, 700);
  await expect.poll(() => scrollRoot.evaluate((node) => node.scrollTop)).toBeGreaterThan(0);

  // Materials → Events
  await page.getByRole("tab", { name: /Материалы/ }).click();
  await page.getByRole("button", { name: /События/ }).first().click();
  await expect(page.getByText("Хронология событий")).toBeVisible();
  await expect(page.getByText("Package lock check failed").first()).toBeVisible();
  await expect(page.getByText("Запуск создан")).toBeVisible();
  await page.getByPlaceholder("Поиск по событиям, задачам, фазам и payload").fill("apt-get");
  await expect(page.getByText("Package lock check failed").first()).toBeVisible();
  await expect(page.getByText("Запуск создан")).toBeHidden();
  await page.getByRole("button", { name: "Debug" }).click();
  await expect(page.getByText("\"exit_code\": 100")).toBeVisible();

  // Progress (steps)
  await page.getByRole("tab", { name: /Ход/ }).click();
  const agentTab = page.getByRole("tabpanel").filter({ hasText: "Ход работы" });
  await expect(page.getByText("1 из 3 шагов завершено")).toBeVisible();
  await expect(page.getByText("Inspect service health").first()).toBeVisible();
  await expect(page.getByText("Apply patch window checks").first()).toBeVisible();
  await page.getByPlaceholder("Поиск по шагам, командам и результатам").fill("package locks");
  await expect(agentTab.locator("article").filter({ hasText: "Apply patch window checks" })).toBeVisible();
  await expect(agentTab.locator("article").filter({ hasText: "Inspect service health" })).toHaveCount(0);
  await page.getByPlaceholder("Поиск по шагам, командам и результатам").fill("");
  await page.getByRole("button", { name: "Активные" }).click();
  await expect(agentTab.locator("article").filter({ hasText: "Write completion report" })).toBeVisible();
  await expect(agentTab.locator("article").filter({ hasText: "Inspect service health" })).toHaveCount(0);

  // Materials → Artifacts
  await page.getByRole("tab", { name: /Материалы/ }).click();
  await page.getByRole("button", { name: /Файлы/ }).first().click();
  await expect(page.getByText("Артефакты появятся после финального отчёта").first()).toBeVisible();
  await expect(page.getByRole("button", { name: /Скачать/ })).toHaveCount(0);

  await page.getByRole("button", { name: /Stop/i }).click();
  await expect.poll(() => harness.getCalls("/servers/api/agents/202/stop/", "POST").length).toBe(1);
});

test("keeps artifacts hidden while live report is not ready", async ({ page }) => {
  await installApiHarness(
    page,
    makeAgentsHandler(
      [
        {
          id: 219,
          name: "Premature Artifact Run",
          mode: "full",
          agent_type: "custom",
          agent_type_display: "Custom",
          server_count: 1,
          last_run_at: FIXED_DATE,
          schedule_minutes: 0,
          max_iterations: 20,
          goal: "Do not expose artifacts until report finalization",
          active_run_id: 909,
          last_run_id: 909,
        },
      ],
      {
        reportMutators: {
          909: (report) => {
            report.report_state.report_ready = false;
            report.report_state.artifacts_ready = false;
            report.artifact_state.ready = false;
            report.artifact_state.artifact_count = 1;
            report.artifacts = [
              {
                id: "premature-final-report",
                name: "final-report.md",
                type: "Markdown",
                description: "Should stay hidden before final report readiness.",
                size_bytes: 42,
                size_label: "42 B",
                created_at: FIXED_DATE,
                artifact_id: 91,
                download_kind: "server",
                download_url: "/servers/api/agents/runs/909/artifacts/91/download/",
                content_type: "text/markdown",
                content: "# Draft",
                truncated: false,
                checksum_sha256: "d".repeat(64),
              },
            ];
          },
        },
      },
    ),
  );

  await page.goto("/agents/run/909");
  await expect(page.getByRole("heading", { name: "Premature Artifact Run" })).toBeVisible();
  await page.getByRole("tab", { name: /Материалы/ }).click();
  await page.getByRole("button", { name: /Файлы/ }).first().click();
  await expect(page.getByText("Артефакты появятся после финального отчёта").first()).toBeVisible();
  await expect(page.getByText("final-report.md")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Скачать/ })).toHaveCount(0);
});

test("answers a pending agent question from the run page", async ({ page }) => {
  const harness = await installApiHarness(
    page,
    makeAgentsHandler(
      [
        {
          id: 218,
          name: "Interactive Rollout",
          mode: "full",
          agent_type: "custom",
          agent_type_display: "Custom",
          server_count: 1,
          last_run_at: FIXED_DATE,
          schedule_minutes: 0,
          max_iterations: 20,
          goal: "Ask before restarting nginx",
          active_run_id: 907,
          last_run_id: 907,
        },
      ],
      {
        waitingRunQuestions: {
          907: "Можно перезапустить nginx сейчас?",
        },
        runtimeOverview: runtimeOverview({
          summary: {
            configured_agents: 1,
            active_runs: 1,
            pending_runs: 0,
            running_runs: 0,
            waiting_runs: 1,
            queued_dispatches: 0,
            claimed_dispatches: 0,
            scheduled_agents: 0,
            scheduled_due_now: 0,
            issues: 0,
          },
          items: {
            active_runs: [
              {
                run_id: 907,
                agent_id: 218,
                agent_name: "Interactive Rollout",
                agent_mode: "full",
                server_id: 1,
                server_name: "Web-01",
                status: "waiting",
                started_at: FIXED_DATE,
                completed_at: null,
                age_seconds: 45,
                duration_ms: 45_000,
                pending_question: "Можно перезапустить nginx сейчас?",
                is_stale_candidate: false,
                dispatch: null,
              },
            ],
            queued_dispatches: [],
            scheduled_due: [],
            stale_candidates: [],
          },
        }),
      },
    ),
  );

  await page.goto("/agents");
  await expect(page.getByText("Interactive Rollout").first()).toBeVisible();
  await expect(page.getByText("Needs answer").first()).toBeVisible();
  await expect(page.getByText("Agent question: Можно перезапустить nginx сейчас?")).toBeVisible();
  await page.getByRole("link", { name: /Answer/i }).click();
  await expect(page).toHaveURL(/\/agents\/run\/907$/);

  await expect(page.locator("h1", { hasText: "Interactive Rollout" })).toBeVisible();
  await expect(page.getByText("Нужен ваш ответ").first()).toBeVisible();
  await expect(page.getByText("Можно перезапустить nginx сейчас?").first()).toBeVisible();

  await page.getByLabel("Ответ агенту").fill("Да, перезапускай nginx в текущем окне.");
  await page.getByRole("button", { name: "Отправить" }).click();

  const replyPath = "/servers/api/agents/runs/907/reply/";
  await expect.poll(() => harness.getCalls(replyPath, "POST").length).toBe(1);
  expect(harness.getCalls(replyPath, "POST")[0].body).toEqual({
    answer: "Да, перезапускай nginx в текущем окне.",
  });
  await expect(page.getByText("Ответ отправлен агенту.")).toBeVisible();
  await expect(page.getByText("Вопрос агента")).toHaveCount(0);

  await page.getByRole("tab", { name: /Материалы/ }).click();
  await page.getByRole("button", { name: /События/ }).first().click();
  await expect(page.getByText("Ответ отправлен агенту").first()).toBeVisible();
});

