import { expect, test, type Page } from "@playwright/test";
import { credentials, login } from "./helpers";

async function headers(page: Page) {
  const response = await page.request.get("/api/auth/csrf/");
  expect(response.ok()).toBeTruthy();
  return {
    "X-CSRFToken": (await response.json()).csrfToken as string,
    Origin: "http://127.0.0.1:8091",
  };
}
async function groupByName(
  page: Page,
  name: string,
): Promise<{ id: number; name: string } | undefined> {
  const response = await page.request.get("/servers/api/frontend/bootstrap/");
  expect(response.ok()).toBeTruthy();
  return (
    (await response.json()).groups as { id: number; name: string }[]
  ).find((group) => group.name === name);
}
test.beforeEach(async ({ baseURL }) => {
  expect(baseURL, "Group writes must stay on the isolated QA service").toBe(
    "http://127.0.0.1:8091",
  );
});

test("group membership lists real assignments, adds an exact user and revokes that membership", async ({
  page,
}) => {
  test.setTimeout(90_000);
  await login(page);
  const name = `qa_groups_access_${Date.now()}`;
  let groupId: number | undefined;
  try {
    await page.goto("/infrastructure/servers?tab=groups");
    await page
      .getByRole("button", { name: "Создать группу", exact: true })
      .click();
    await page
      .getByRole("dialog")
      .getByLabel("Название", { exact: true })
      .fill(name);
    await page
      .getByRole("dialog")
      .getByRole("button", { name: "Создать группу", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    const group = await groupByName(page, name);
    expect(group).toBeDefined();
    groupId = group!.id;
    await page
      .getByRole("row")
      .filter({ hasText: name })
      .getByRole("button", { name, exact: true })
      .click();
    const drawer = page.getByRole("dialog", { name, exact: true });
    await drawer.getByRole("tab", { name: "Доступ", exact: true }).click();
    await expect(
      drawer.getByText(`Владелец группы: ${credentials.admin.username}`, {
        exact: true,
      }),
    ).toBeVisible();
    await drawer
      .getByRole("button", { name: "Добавить участника", exact: true })
      .click();
    await drawer
      .getByLabel("Точный логин или email", { exact: true })
      .fill(credentials.viewer.username);
    await drawer.getByLabel("Роль", { exact: true }).selectOption("viewer");
    await drawer.getByRole("button", { name: "Добавить", exact: true }).click();
    const row = drawer
      .getByRole("row")
      .filter({ hasText: credentials.viewer.username });
    await expect(row).toContainText("Наблюдатель");
    const memberResponse = await page.request.get(
      `/servers/api/groups/${groupId}/members/`,
    );
    expect(memberResponse.ok(), await memberResponse.text()).toBeTruthy();
    const members = (await memberResponse.json()).members as {
      user_id: number;
      username: string;
      role: string;
    }[];
    const member = members.find(
      (item) => item.username === credentials.viewer.username,
    );
    expect(member?.role).toBe("viewer");
    await row
      .getByRole("button", {
        name: `Отозвать доступ ${credentials.viewer.username}`,
        exact: true,
      })
      .click();
    await page
      .getByRole("dialog", { name: "Отозвать доступ к группе?", exact: true })
      .getByRole("button", { name: "Отозвать доступ", exact: true })
      .click();
    await expect(row).toHaveCount(0);
    const after = await page.request.get(
      `/servers/api/groups/${groupId}/members/`,
    );
    expect(
      ((await after.json()).members as { user_id: number }[]).some(
        (item) => item.user_id === member!.user_id,
      ),
    ).toBe(false);
    await page.reload();
    await expect(page.getByRole("dialog", { name, exact: true })).toBeVisible();
    await expect(
      page.getByText("Пока только владелец", { exact: true }),
    ).toBeVisible();
  } finally {
    if (groupId) {
      expect(name.startsWith("qa_groups_")).toBeTruthy();
      const result = await page.request.post(
        `/servers/api/groups/${groupId}/delete/`,
        { headers: await headers(page) },
      );
      expect(result.ok()).toBeTruthy();
    }
  }
});

test("group bulk metadata operation records its scope and restores its progress URL", async ({
  page,
}) => {
  test.setTimeout(90_000);
  await login(page);
  const suffix = Date.now();
  const name = `qa_groups_bulk_${suffix}`;
  const auth = await headers(page);
  const groupResponse = await page.request.post("/servers/api/groups/create/", {
    headers: auth,
    data: { name },
  });
  expect(groupResponse.ok(), await groupResponse.text()).toBeTruthy();
  const groupId = (await groupResponse.json()).group_id as number;
  let serverId: number | undefined;
  try {
    // Dedicated metadata row points only at the local SSH fixture; this test never opens a terminal or executes a command.
    const serverResponse = await page.request.post("/servers/api/create/", {
      headers: auth,
      data: {
        name: `qa_groups_server_${suffix}`,
        host: "127.0.0.1",
        port: 22391,
        username: "qa",
        auth_method: "password",
        password: credentials.password,
        group_id: groupId,
      },
    });
    expect(serverResponse.ok(), await serverResponse.text()).toBeTruthy();
    serverId = (await serverResponse.json()).server_id as number;
    await page.goto(
      `/infrastructure/servers?tab=groups&group=${groupId}&group_view=bulk`,
    );
    const drawer = page.getByRole("dialog", { name, exact: true });
    await drawer
      .getByLabel("Массовое изменение", { exact: true })
      .selectOption("set_tags");
    await drawer
      .getByLabel("Новые теги", { exact: true })
      .fill(`qa-bulk-${suffix}`);
    await drawer
      .getByRole("button", { name: "Проверить и запустить", exact: true })
      .click();
    const confirmation = page.getByRole("dialog", {
      name: "Применить ко всей группе?",
      exact: true,
    });
    await confirmation.getByRole("textbox").fill(name);
    const queued = page.waitForResponse(
      (response) =>
        response
          .url()
          .endsWith(`/servers/api/groups/${groupId}/bulk-actions/`) &&
        response.request().method() === "POST",
    );
    await confirmation
      .getByRole("button", { name: "Запустить изменение", exact: true })
      .click();
    const result = await queued;
    expect(result.status(), await result.text()).toBe(202);
    const operation = (await result.json()).operation;
    expect(operation).toMatchObject({
      group_id: groupId,
      action: "set_tags",
      parameters: { value: `qa-bulk-${suffix}` },
      total_count: 1,
    });
    await expect(page).toHaveURL(new RegExp(`bulk_operation=${operation.id}`));
    await expect(
      drawer.getByRole("heading", {
        name: `Операция #${operation.id}`,
        exact: true,
      }),
    ).toBeVisible();
    await page.reload();
    await expect(page.getByRole("dialog", { name, exact: true })).toBeVisible();
    await expect(
      page.getByRole("heading", {
        name: `Операция #${operation.id}`,
        exact: true,
      }),
    ).toBeVisible();
    const detailResponse = await page.request.get(
      `/servers/api/bulk-actions/${operation.id}/`,
    );
    expect(detailResponse.ok()).toBeTruthy();
    const detail = (await detailResponse.json()).operation;
    expect(detail.group_id).toBe(groupId);
    expect(["queued", "running", "completed"]).toContain(detail.status);
    if (detail.status === "completed") {
      expect(detail.succeeded_count).toBe(1);
      const server = await page.request.get(`/servers/api/${serverId}/get/`);
      expect((await server.json()).tags).toBe(`qa-bulk-${suffix}`);
    }
  } finally {
    expect(name.startsWith("qa_groups_")).toBeTruthy();
    const deleted = await page.request.post(
      `/servers/api/groups/${groupId}/delete/`,
      { headers: await headers(page) },
    );
    expect(deleted.ok()).toBeTruthy();
    if (serverId) {
      const serverDeleted = await page.request.post(
        `/servers/api/${serverId}/delete/`,
        { headers: await headers(page) },
      );
      expect(serverDeleted.ok()).toBeTruthy();
    }
  }
});
