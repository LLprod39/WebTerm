import { expect, test } from "@playwright/test";
import { installApiHarness } from "./support/apiHarness";
import { FIXED_DATE, runtimeOverview } from "./support/agentsMockShared";
import { makeAgentsHandler } from "./support/agentsHandlers";

test("creates and runs a mini agent from the agents page", async ({ page }) => {
  const harness = await installApiHarness(page, makeAgentsHandler());

  await page.goto("/agents");
  await expect(page.getByRole("heading", { name: "Agents", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "New agent" }).click();

  const createDialog = page.getByRole("dialog");
  await expect(createDialog.getByText("Agent type")).toBeVisible();
  await createDialog.getByRole("button", { name: /Mini Agent/i }).click();
  await createDialog.getByRole("button", { name: /Custom/i }).click();

  await expect(createDialog.getByRole("heading", { name: "Basics" })).toBeVisible();
  await createDialog.getByPlaceholder("Log analysis").fill("Disk Audit");
  await createDialog.locator("textarea").nth(0).fill("hostname\nuptime");
  await createDialog.locator("textarea").nth(1).fill("Summarize the result");
  await createDialog.getByRole("button", { name: "Next" }).click();

  await expect(createDialog.getByRole("heading", { name: "Server selection" })).toBeVisible();
  await createDialog.getByRole("button", { name: /Web-01/i }).click();
  await createDialog.getByRole("button", { name: "Next" }).click();

  await expect(createDialog.getByRole("heading", { name: "Capabilities" })).toBeVisible();
  await createDialog.getByRole("button", { name: "Next" }).click();

  await expect(createDialog.getByText("Ready to save")).toBeVisible();
  await createDialog.getByRole("button", { name: "Create Agent" }).click();

  await expect.poll(() => harness.getCalls("/servers/api/agents/create/", "POST").length).toBe(1);
  await expect(createDialog).toBeHidden();
  await expect(page.getByRole("main").getByText("Disk Audit")).toBeVisible();

  await page.getByRole("button", { name: "Run Disk Audit" }).click();
  await expect.poll(() => harness.getCalls("/servers/api/agents/300/run/", "POST").length).toBe(1);
  await expect(page).toHaveURL(/\/agents\/run\/700$/);
  await expect(page.getByRole("heading", { name: "Disk Audit" })).toBeVisible();
});

test("opens the durable mini run report after launch", async ({ page }) => {
  await installApiHarness(
    page,
    makeAgentsHandler([
      {
        id: 221,
        name: "Mini Preview",
        mode: "mini",
        agent_type: "custom",
        agent_type_display: "Custom",
        server_count: 1,
        last_run_at: null,
        schedule_minutes: 0,
        max_iterations: 20,
        goal: "Render quick report preview",
        active_run_id: null,
        last_run_id: null,
      },
    ]),
  );

  await page.goto("/agents");
  await expect(page.getByText("Mini Preview")).toBeVisible();
  await page.getByRole("button", { name: "Run Mini Preview" }).click();

  await expect(page).toHaveURL(/\/agents\/run\/700$/);
  await expect(page.getByRole("heading", { name: "Mini Preview" })).toBeVisible();
  await expect(page.getByText("1s").first()).toBeVisible();
});

test("blocks full agent launch when execution worker is not ready", async ({ page }) => {
  const harness = await installApiHarness(
    page,
    makeAgentsHandler([
      {
        id: 211,
        name: "Worker Blocked",
        mode: "full",
        agent_type: "custom",
        agent_type_display: "Custom",
        server_count: 1,
        last_run_at: null,
        schedule_minutes: 0,
        max_iterations: 20,
        goal: "Run only when the execution worker is available",
        active_run_id: null,
        last_run_id: null,
        execution_readiness: {
          required: true,
          ready: false,
          status: "idle",
          severity: "warning",
          title: "Execution worker не активен",
          description: "Full/multi-агенты могут остаться в очереди.",
          next_action: "Запустите worker: python manage.py run_agent_execution_plane --worker-key <unique-worker-key>",
          worker: null,
        },
      },
    ]),
  );

  await page.goto("/agents");
  await expect(page.getByText("Worker Blocked")).toBeVisible();
  await expect(page.getByText("Execution worker").first()).toBeVisible();
  await expect(page.getByText("Full/multi agent queue runtime")).toBeVisible();
  await expect(page.getByText("python manage.py run_agent_execution_plane").first()).toBeVisible();
  await expect(page.getByRole("button", { name: /^Copy$/ })).toBeVisible();
  await expect(page.getByRole("button", { name: "Run Worker Blocked" })).toBeDisabled();
  expect(harness.getCalls("/servers/api/agents/211/run/", "POST")).toHaveLength(0);
});

test("shows agent runtime queue blockers", async ({ page }) => {
  const harness = await installApiHarness(
    page,
    makeAgentsHandler(
      [
        {
          id: 214,
          name: "Queued Pipeline",
          mode: "multi",
          agent_type: "custom",
          agent_type_display: "Custom",
          server_count: 1,
          last_run_at: FIXED_DATE,
          schedule_minutes: 10,
          schedule_config: { mode: "interval", interval_minutes: 10 },
          max_iterations: 20,
          goal: "Waits for worker diagnostics",
          active_run_id: 904,
          last_run_id: 904,
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
            scheduled_agents: 1,
            scheduled_due_now: 1,
            issues: 2,
          },
          issues: [
            {
              id: "execution_worker_not_ready",
              severity: "warning",
              title: "Execution worker не активен",
              description: "Full/multi-запуски есть в очереди, но worker не подтверждён.",
              next_action: "python manage.py run_agent_execution_plane --worker-key <unique-worker-key>",
            },
            {
              id: "scheduled_agents_worker_not_ready",
              severity: "warning",
              title: "Schedule worker не активен",
              description: "Есть due-агенты, но автозапуск по расписанию не подтверждён.",
              next_action: "python manage.py run_scheduled_agents --daemon --worker-key default",
            },
          ],
          items: {
            active_runs: [
              {
                run_id: 904,
                agent_id: 214,
                agent_name: "Queued Pipeline",
                agent_mode: "multi",
                server_id: 1,
                server_name: "Web-01",
                status: "pending",
                started_at: FIXED_DATE,
                completed_at: null,
                age_seconds: 420,
                duration_ms: 0,
                pending_question: "",
                is_stale_candidate: true,
                dispatch: null,
              },
            ],
            queued_dispatches: [
              {
                dispatch_id: 19,
                run_id: 904,
                agent_id: 214,
                agent_name: "Queued Pipeline",
                agent_mode: "multi",
                server_id: 1,
                server_name: "Web-01",
                dispatch_kind: "launch",
                status: "queued",
                server_ids: [1],
                queued_at: FIXED_DATE,
                claimed_at: null,
                heartbeat_at: null,
                lease_expires_at: null,
                queued_age_seconds: 420,
                lease_seconds_left: null,
                claimed_by: "",
                attempt_count: 0,
                error: "",
              },
            ],
            scheduled_due: [
              {
                agent_id: 214,
                agent_name: "Queued Pipeline",
                agent_mode: "multi",
                server_count: 1,
                server_names: ["Web-01"],
                schedule_minutes: 10,
                schedule_config: { mode: "interval", interval_minutes: 10 },
                last_run_at: FIXED_DATE,
                next_due_at: FIXED_DATE,
                due_age_seconds: 60,
                active_run_id: 904,
                active_run_status: "pending",
              },
            ],
            stale_candidates: [
              {
                run_id: 904,
                agent_id: 214,
                agent_name: "Queued Pipeline",
                agent_mode: "multi",
                server_id: 1,
                server_name: "Web-01",
                status: "pending",
                started_at: FIXED_DATE,
                completed_at: null,
                age_seconds: 420,
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

  await page.goto("/agents");
  const runtimeSection = page.locator("section").filter({ hasText: "Agent runtime" }).first();
  await expect(runtimeSection).toBeVisible();
  await expect(runtimeSection.getByText("Runtime blockers detected")).toBeVisible();
  await expect(runtimeSection.getByText("Full/multi-запуски есть в очереди")).toBeVisible();
  await expect(runtimeSection.getByText("queued", { exact: true }).first()).toBeVisible();
  await expect(runtimeSection.getByText("due", { exact: true }).first()).toBeVisible();
  await expect(runtimeSection.getByText("Active runs", { exact: true })).toBeVisible();
  await expect(runtimeSection.getByText("Dispatch queue", { exact: true })).toBeVisible();
  await expect(runtimeSection.getByText("Due schedule", { exact: true })).toBeVisible();
  await expect(runtimeSection.getByText("Stale candidates", { exact: true })).toBeVisible();
  await expect(runtimeSection.getByText("Queued Pipeline").first()).toBeVisible();
  await expect(runtimeSection.getByText("run #904")).toBeVisible();
  await expect(runtimeSection.getByRole("button", { name: /Clean stale/i })).toBeVisible();
  await expect(runtimeSection.getByText("Recommended production worker")).toBeVisible();
  await expect(runtimeSection.getByText("docker compose up -d --scale agent-execution")).toBeVisible();
  await expect(runtimeSection.getByText("python manage.py run_scheduled_agents")).toBeVisible();

  await runtimeSection.getByRole("button", { name: /Clean stale/i }).click();
  await expect.poll(() => harness.getCalls("/servers/api/agents/runtime/cleanup-stale/", "POST").length).toBe(1);
  await expect(page.getByText("Cleaned stale runs: 1; canceled dispatches: 1.")).toBeVisible();
  await expect(runtimeSection.getByRole("button", { name: /Clean stale/i })).toBeHidden();
});
