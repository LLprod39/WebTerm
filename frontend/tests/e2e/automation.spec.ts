import { expect, test, type Page } from "@playwright/test";
import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { delimiter, join } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { login, assertNoOverflow } from "./helpers";

type GraphNode = {
  id: string;
  type: string;
  data: Record<string, unknown>;
  position: { x: number; y: number };
};
type GraphEdge = {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string;
};
type Pipeline = {
  id: number;
  name: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
};
const playbookBase = "/servers/api/playbooks/";
const pipelineBase = "/api/studio/pipelines/";
async function executePureFixture(runId: number) {
  const repo = fileURLToPath(new URL("../../../", import.meta.url));
  const backend = fileURLToPath(new URL("../backend/", import.meta.url));
  const localPython = join(repo, ".venv", "Scripts", "python.exe");
  const python =
    process.env.WEBTERM_QA_PYTHON ||
    (existsSync(localPython) ? localPython : "python");
  await promisify(execFile)(
    python,
    [join(backend, "run_safe_pipeline.py"), String(runId)],
    {
      cwd: repo,
      timeout: 45_000,
      env: {
        ...process.env,
        DJANGO_SETTINGS_MODULE: "qa_settings",
        PYTHONPATH: [repo, backend, process.env.PYTHONPATH]
          .filter(Boolean)
          .join(delimiter),
        POSTGRES_HOST: process.env.POSTGRES_HOST || "127.0.0.1",
        POSTGRES_PORT: process.env.POSTGRES_PORT || "5433",
      },
    },
  );
}
async function headers(page: Page) {
  const csrf = await page.request.get("/api/auth/csrf/");
  expect(csrf.ok()).toBeTruthy();
  return {
    "X-CSRFToken": (await csrf.json()).csrfToken as string,
    Origin: "http://127.0.0.1:8091",
  };
}
async function pipeline(page: Page, id: number): Promise<Pipeline> {
  const response = await page.request.get(`${pipelineBase}${id}/`);
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json();
}
async function deletePipeline(page: Page, id: number, name: string) {
  expect(name.startsWith("qa_auto_")).toBeTruthy();
  const item = await pipeline(page, id);
  expect(item.name).toBe(name);
  const response = await page.request.delete(`${pipelineBase}${id}/`, {
    headers: await headers(page),
  });
  expect(response.ok(), await response.text()).toBeTruthy();
}
async function archivePlaybook(page: Page, id: number, name: string) {
  expect(name.startsWith("qa_auto_")).toBeTruthy();
  const response = await page.request.post(`${playbookBase}${id}/delete/`, {
    headers: await headers(page),
  });
  expect([200, 404]).toContain(response.status());
}
async function connect(
  page: Page,
  sourceId: string,
  targetId: string,
  handle = "out",
) {
  await page.getByRole("button", { name: "Вписать в экран", exact: true }).click();
  const source = page.locator(
    `.react-flow__node[data-id="${sourceId}"] .react-flow__handle.source[data-handleid="${handle}"]`,
  );
  const target = page.locator(
    `.react-flow__node[data-id="${targetId}"] .react-flow__handle.target`,
  );
  await expect(source).toBeVisible();
  await expect(target).toBeVisible();
  const from = await source.boundingBox();
  const to = await target.boundingBox();
  expect(from).not.toBeNull();
  expect(to).not.toBeNull();
  await page.mouse.move(from!.x + from!.width / 2, from!.y + from!.height / 2);
  await page.mouse.down();
  await page.mouse.move(to!.x + to!.width / 2, to!.y + to!.height / 2, {
    steps: 15,
  });
  await page.mouse.up();
}
test.beforeEach(async ({ baseURL }) => {
  expect(
    baseURL,
    "Automation writes must stay on the isolated QA service",
  ).toBe("http://127.0.0.1:8091");
});

test("playbook YAML draft persists through reload, metadata edit, archive and restore", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await login(page);
  let id: number | undefined;
  let name = `qa_auto_playbook_${Date.now()}`;
  const source =
    "- name: QA safe document\n  hosts: all\n  gather_facts: false\n  tasks:\n    - name: Describe test\n      ansible.builtin.debug:\n        msg: draft-one\n";
  try {
    await page.goto("/automation/playbooks");
    await page
      .getByRole("button", { name: "Новый плейбук", exact: true })
      .click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Название", { exact: true }).fill(name);
    await dialog.getByLabel("Ansible YAML", { exact: true }).fill(source);
    const created = page.waitForResponse(
      (response) =>
        response.url().endsWith(`${playbookBase}create/`) &&
        response.request().method() === "POST",
    );
    await dialog
      .getByRole("button", { name: "Создать плейбук", exact: true })
      .click();
    const createdResponse = await created;
    expect(createdResponse.ok(), await createdResponse.text()).toBeTruthy();
    id = (await createdResponse.json()).playbook.id;
    await expect(page).toHaveURL(new RegExp(`/automation/playbooks/${id}$`));
    const editor = page.getByLabel("Редактор Ansible YAML", { exact: true });
    await expect(editor).toHaveValue(source);
    const updated = source.replace("draft-one", "draft-two");
    await editor.fill(updated);
    const saved = page.waitForResponse(
      (response) =>
        response.url().endsWith(`${playbookBase}${id}/draft/`) &&
        response.request().method() === "PUT",
    );
    await page
      .getByRole("button", { name: "Сохранить черновик", exact: true })
      .click();
    const savedResponse = await saved;
    expect(savedResponse.ok(), await savedResponse.text()).toBeTruthy();
    expect((await savedResponse.json()).draft.source_yaml).toBe(updated);
    await expect(
      page.getByRole("button", { name: "Сохранить черновик", exact: true }),
    ).toBeDisabled();
    await page.reload();
    await expect(editor).toHaveValue(updated);
    await page.getByText("Название и описание", { exact: true }).click();
    name += "_edited";
    await page.getByLabel("Название", { exact: true }).fill(name);
    await page
      .getByLabel("Описание", { exact: true })
      .fill("Verified YAML draft and metadata");
    await page
      .getByRole("button", { name: "Сохранить сведения", exact: true })
      .click();
    await expect(
      page.getByRole("heading", { level: 1, name, exact: true }),
    ).toBeVisible();
    await assertNoOverflow(page);
    await page.screenshot({
      path: "test-results/automation-playbook-workspace.png",
      fullPage: true,
    });
    await page
      .getByRole("button", { name: "Архивировать плейбук", exact: true })
      .click();
    await page.getByRole("dialog").getByRole("textbox").fill(name);
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Архивировать", exact: true })
      .click();
    await expect(page).toHaveURL(/\/automation\/playbooks$/);
    await expect(page.getByRole("link", { name, exact: true })).toHaveCount(0);
    await page
      .getByRole("button", { name: "Восстановить", exact: true })
      .click();
    await expect(page).toHaveURL(new RegExp(`/automation/playbooks/${id}$`));
    await expect(editor).toHaveValue(updated);
  } finally {
    if (id) await archivePlaybook(page, id, name);
  }
});

test("pipeline canvas keeps invalid edits, exposes node errors, persists connections and performs validation only", async ({
  page,
}) => {
  test.setTimeout(120_000);
  await login(page);
  let id: number | undefined;
  const name = `qa_auto_canvas_${Date.now()}`;
  try {
    await page.goto("/automation/pipelines");
    await page
      .getByRole("button", { name: "Новый процесс", exact: true })
      .click();
    await page
      .getByRole("dialog")
      .getByLabel("Название", { exact: true })
      .fill(name);
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Создать процесс", exact: true })
      .click();
    await expect(page).toHaveURL(/\/automation\/pipelines\/\d+$/);
    id = Number(page.url().split("/").at(-1));
    const initial = await pipeline(page, id);
    const trigger = initial.nodes.find(
      (node) => node.type === "trigger/manual",
    )!;
    expect(trigger.data.is_active).toBe(false);
    await page
      .getByRole("button", { name: "Добавить шаг", exact: true })
      .click();
    await page
      .getByLabel("Поиск шагов", { exact: true })
      .fill("logic/condition");
    await page
      .locator(".auto-node-picker")
      .getByRole("button", { name: /Условие/i })
      .click();
    await page.getByLabel("Название шага", { exact: true }).fill("QA branch");
    const conditionNode = page
      .locator(".react-flow__node")
      .filter({ hasText: "QA branch" });
    const conditionId = (await conditionNode.getAttribute("data-id"))!;
    let responsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith(`${pipelineBase}${id}/`) &&
        response.request().method() === "PUT",
    );
    await page.getByRole("button", { name: "Сохранить", exact: true }).click();
    expect((await responsePromise).status()).toBe(400);
    await expect(page.locator(".auto-validation")).toContainText(
      /unreachable|check_value/,
    );
    expect((await pipeline(page, id)).nodes).toHaveLength(1);
    await expect(conditionNode).toBeVisible();
    await connect(page, trigger.id, conditionId);
    await expect(page.locator(".react-flow__edge")).toHaveCount(1);
    responsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith(`${pipelineBase}${id}/`) &&
        response.request().method() === "PUT",
    );
    await page.getByRole("button", { name: "Сохранить", exact: true }).click();
    expect((await responsePromise).status()).toBe(400);
    await page
      .locator(".auto-validation")
      .getByRole("button", { name: "К узлу", exact: true })
      .first()
      .click();
    await expect(page.getByLabel("Название шага", { exact: true })).toHaveValue(
      "QA branch",
    );
    await page.getByLabel("Значение", { exact: true }).fill("QA_VALUE");
    await page.locator(`.react-flow__node[data-id="${trigger.id}"]`).click();
    await page
      .getByRole("checkbox", { name: "Триггер включён", exact: true })
      .check();
    responsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith(`${pipelineBase}${id}/`) &&
        response.request().method() === "PUT",
    );
    await page.getByRole("button", { name: "Сохранить", exact: true }).click();
    const saved = await responsePromise;
    expect(saved.ok(), await saved.text()).toBeTruthy();
    await expect(
      page.getByRole("button", { name: "Сохранить", exact: true }),
    ).toBeDisabled();
    const persisted = await pipeline(page, id);
    expect(
      persisted.nodes.find((node) => node.id === conditionId)?.data.check_value,
    ).toBe("QA_VALUE");
    expect(
      persisted.nodes.find((node) => node.id === trigger.id)?.data.is_active,
    ).toBe(true);
    expect(persisted.edges).toEqual([
      expect.objectContaining({
        source: trigger.id,
        target: conditionId,
        sourceHandle: "out",
      }),
    ]);
    await page.reload();
    await expect(page.locator(".react-flow__edge")).toHaveCount(1);
    await page
      .getByRole("button", { name: "Проверить и запустить", exact: true })
      .click();
    const readyResponse = page.waitForResponse(
      (response) =>
        response.url().endsWith(`${pipelineBase}${id}/run/`) &&
        response.request().method() === "POST",
    );
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Проверить готовность", exact: true })
      .click();
    const ready = await readyResponse;
    expect(ready.ok(), await ready.text()).toBeTruthy();
    expect(ready.request().postDataJSON().validate_only).toBe(true);
    expect((await ready.json()).dry_run.executed).toBe(false);
    await expect(
      page.getByRole("dialog").getByText("Проверки пройдены", { exact: true }),
    ).toBeVisible();
    await page.keyboard.press("Escape");
    await assertNoOverflow(page);
    await page.screenshot({
      path: "test-results/automation-pipeline-canvas.png",
      fullPage: true,
    });
    await page
      .getByRole("button", { name: "Включить тёмную тему", exact: true })
      .click();
    await expect(page.locator(".auto-flow-canvas .react-flow")).toHaveClass(
      /dark/,
    );
    const surface = await page
      .locator(".auto-node-settings, .auto-editor-topbar")
      .first()
      .evaluate((element) => getComputedStyle(element).backgroundColor);
    await expect(page.locator(".auto-canvas-controls").first()).toHaveCSS(
      "background-color",
      surface,
    );
    await expect(page.locator(".react-flow__minimap")).toHaveCSS(
      "background-color",
      surface,
    );
    await page.screenshot({
      path: "test-results/automation-pipeline-canvas-dark.png",
      fullPage: true,
    });
    const edge = page.locator(".react-flow__edge");
    await edge.focus();
    await page.keyboard.press("Enter");
    await page.keyboard.press("Delete");
    await expect(page.locator(".react-flow__edge")).toHaveCount(0);
    responsePromise = page.waitForResponse(
      (response) =>
        response.url().endsWith(`${pipelineBase}${id}/`) &&
        response.request().method() === "PUT",
    );
    await page.getByRole("button", { name: "Сохранить", exact: true }).click();
    expect((await responsePromise).status()).toBe(400);
    await expect(page.locator(".auto-validation")).toContainText("unreachable");
    expect((await pipeline(page, id)).edges).toHaveLength(1);
  } finally {
    if (id) await deletePipeline(page, id, name);
  }
});

test("stale playbook draft conflicts preserve unsaved operator text", async ({
  page,
}) => {
  await login(page);
  const name = `qa_auto_conflict_${Date.now()}`;
  const auth = await headers(page);
  const created = await page.request.post(`${playbookBase}create/`, {
    headers: auth,
    data: {
      name,
      kind: "runbook",
      tasks: [
        {
          id: "qa-task",
          command: "echo document-only",
          description: "QA fixture",
          continue_on_error: false,
        },
      ],
    },
  });
  expect(created.ok(), await created.text()).toBeTruthy();
  const id = (await created.json()).playbook.id as number;
  try {
    await page.goto(`/automation/playbooks/${id}`);
    const editor = page.getByLabel("Команда", { exact: true });
    await expect(editor).toHaveValue("echo document-only");
    await editor.fill("echo my-unsaved-change");
    const draft = (
      await (await page.request.get(`${playbookBase}${id}/draft/`)).json()
    ).draft;
    const external = await page.request.put(`${playbookBase}${id}/draft/`, {
      headers: auth,
      data: {
        expected_draft_version: draft.version,
        source_yaml: draft.source_yaml,
        tasks: [{ ...draft.tasks[0], command: "echo other-editor" }],
      },
    });
    expect(external.ok(), await external.text()).toBeTruthy();
    const rejected = page.waitForResponse(
      (response) =>
        response.url().endsWith(`${playbookBase}${id}/draft/`) &&
        response.request().method() === "PUT",
    );
    await page
      .getByRole("button", { name: "Сохранить черновик", exact: true })
      .click();
    expect((await rejected).status()).toBe(409);
    await expect(
      page.getByText("Черновик изменён другим редактором.", { exact: false }),
    ).toBeVisible();
    await expect(editor).toHaveValue("echo my-unsaved-change");
    const persisted = (
      await (await page.request.get(`${playbookBase}${id}/draft/`)).json()
    ).draft;
    expect(persisted.tasks[0].command).toBe("echo other-editor");
  } finally {
    await archivePlaybook(page, id, name);
  }
});

test("a pure local condition run opens persisted node results without remote execution", async ({
  page,
}) => {
  test.setTimeout(90_000);
  await login(page);
  const name = `qa_auto_pure_run_${Date.now()}`;
  const created = await page.request.post(pipelineBase, {
    headers: await headers(page),
    data: {
      name,
      nodes: [
        {
          id: "qa_manual",
          type: "trigger/manual",
          data: { label: "QA start", is_active: true },
          position: { x: 200, y: 80 },
        },
        {
          id: "qa_condition",
          type: "logic/condition",
          data: { label: "QA local condition", check_type: "always_true" },
          position: { x: 200, y: 260 },
        },
      ],
      edges: [
        {
          id: "qa_edge",
          source: "qa_manual",
          target: "qa_condition",
          sourceHandle: "out",
        },
      ],
    },
  });
  expect(created.ok(), await created.text()).toBeTruthy();
  const id = (await created.json()).id as number;
  try {
    await page.goto(`/automation/pipelines/${id}`);
    await page
      .getByRole("button", { name: "Проверить и запустить", exact: true })
      .click();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Проверить готовность", exact: true })
      .click();
    await expect(
      page
        .getByRole("dialog")
        .getByRole("button", { name: "Запустить процесс", exact: true }),
    ).toBeEnabled();
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Запустить процесс", exact: true })
      .click();
    await page
      .getByRole("dialog", { name: "Выполнить рабочий процесс?", exact: true })
      .getByRole("button", { name: "Запустить", exact: true })
      .click();
    await expect(page).toHaveURL(/\/automation\/runs\/pipeline\/\d+$/);
    await expect(
      page.getByRole("heading", { level: 1, name, exact: true }),
    ).toBeVisible();
    const runId = Number(page.url().split("/").at(-1));
    const canvas = page.getByRole("region", {
      name: "Схема выполнения процесса",
    });
    const conditionNode = canvas.locator(
      '.react-flow__node[data-id="qa_condition"]',
    );
    await expect(conditionNode.locator(".auto-node")).toHaveAttribute(
      "data-run-status",
      "unreported",
    );
    await expect(canvas.locator(".react-flow__edge")).toHaveCount(1);
    await executePureFixture(runId);
    await expect
      .poll(
        async () =>
          (await (await page.request.get(`/api/studio/runs/${runId}/`)).json())
            .status,
        { timeout: 30_000 },
      )
      .toBe("completed");
    await page.reload();
    await expect(conditionNode.locator(".auto-node")).toHaveAttribute(
      "data-run-status",
      "completed",
    );
    await expect(
      conditionNode.getByText("Завершено", { exact: true }),
    ).toBeVisible();
    await expect(canvas.locator(".react-flow__edge")).toHaveCount(1);
    await conditionNode.click();
    await expect(
      page.getByRole("heading", {
        name: "Результат: qa_condition",
        exact: true,
      }),
    ).toBeVisible();
    await expect(conditionNode).toHaveClass(/selected/);
    await expect(page.locator(".auto-log")).not.toContainText(
      "Шаг ещё не вернул результат",
    );
    await assertNoOverflow(page);
    await page.screenshot({
      path: "test-results/automation-pure-run-report.png",
      fullPage: true,
    });
  } finally {
    await deletePipeline(page, id, name);
  }
});
