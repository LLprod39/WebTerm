import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { credentials, login } from "./helpers";

test("server create, secret preservation, update and typed deletion use live contracts", async ({
  page,
}) => {
  await login(page);
  const name = `qa-ui-${Date.now()}`;
  let id: number | undefined;
  try {
    await page.goto("/infrastructure/servers");
    await page
      .getByRole("button", { name: "Добавить сервер", exact: true })
      .click();
    const dialog = page.getByRole("dialog");
    await dialog.getByLabel("Название", { exact: true }).fill(name);
    await dialog.getByLabel("Адрес сервера").fill("127.0.0.1");
    await dialog.getByLabel("SSH-порт").fill("22391");
    await dialog.getByLabel("Пользователь SSH").fill("qa");
    await dialog
      .getByLabel("Пароль SSH")
      .fill("test-secret-not-for-host-execution");
    const created = page.waitForResponse(
      (r) =>
        r.url().endsWith("/servers/api/create/") &&
        r.request().method() === "POST",
    );
    await dialog
      .getByRole("button", { name: "Добавить сервер", exact: true })
      .click();
    const response = await created;
    expect(response.ok()).toBeTruthy();
    id = (await response.json()).server_id;
    expect(id).toBeTruthy();
    await page.getByRole("link", { name, exact: true }).click();
    await page.getByRole("button", { name: "Настроить", exact: true }).click();
    await expect(dialog.getByLabel("Пароль SSH")).toHaveValue("");
    await dialog
      .getByText("Контекст и дополнительные параметры", { exact: true })
      .click();
    await dialog
      .getByLabel("Заметки", { exact: true })
      .fill("Проверено из интерфейса");
    await dialog.getByLabel("Повышение привилегий").selectOption("nopasswd");
    await dialog.getByRole("button", { name: "Сохранить изменения" }).click();
    await expect(dialog).toBeHidden();
    await expect(
      page.getByText("Проверено из интерфейса", { exact: true }),
    ).toBeVisible();
    const detail = await (
      await page.request.get(`/servers/api/${id}/get/`)
    ).json();
    expect(detail.sudo_auth_mode).toBe("nopasswd");
    expect(detail.has_saved_password).toBe(true);
    expect(JSON.stringify(detail)).not.toContain(
      "test-secret-not-for-host-execution",
    );
    await page.getByRole("button", { name: "Ещё для сервера", exact: true }).click();
    await page.getByRole("menuitem", { name: "Удалить сервер", exact: true }).click();
    await expect(
      dialog.getByRole("button", { name: "Удалить сервер" }),
    ).toBeDisabled();
    await dialog.getByRole("textbox").fill(name);
    await dialog.getByRole("button", { name: "Удалить сервер" }).click();
    await expect(page).toHaveURL(/\/infrastructure\/servers$/);
    await expect(page.getByRole("link", { name, exact: true })).toHaveCount(0);
    id = undefined;
  } finally {
    if (id) {
      const { csrfToken } = await (
        await page.request.get("/api/auth/csrf/")
      ).json();
      await page.request.post(`/servers/api/${id}/delete/`, {
        headers: { "X-CSRFToken": csrfToken },
        data: {},
      });
    }
  }
});

test("remote file edit preserves unsaved draft, writes and re-reads through SFTP", async ({
  page,
}) => {
  await login(page);
  await page.goto(`/infrastructure/servers/${credentials.serverId}`);
  await page.getByRole("tab", { name: "Файлы", exact: true }).click();
  await page.getByRole("button", { name: "readme.txt", exact: true }).click();
  const editor = page.getByLabel("Содержимое файла", { exact: true });
  await expect(editor).toBeVisible();
  const original = await editor.inputValue();
  const changed = `${original.trim()}\nQA persisted via SFTP\n`;
  try {
    await editor.fill(changed);
    await page.keyboard.press("Escape");
    await expect(
      page.getByRole("heading", { name: "Закрыть без сохранения?" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "Отмена", exact: true }).click();
    await expect(editor).toHaveValue(changed);
    await page.getByRole("button", { name: "Сохранить", exact: true }).click();
    await expect(
      page.getByText("Все изменения сохранены", { exact: true }),
    ).toBeVisible();
    await page.keyboard.press("Escape");
    await page.getByRole("button", { name: "readme.txt", exact: true }).click();
    await expect(editor).toHaveValue(changed);
  } finally {
    const { csrfToken } = await (
      await page.request.get("/api/auth/csrf/")
    ).json();
    await page.request.post(
      `/servers/api/${credentials.serverId}/files/write/`,
      {
        headers: { "X-CSRFToken": csrfToken },
        data: { path: "/readme.txt", content: original },
      },
    );
  }
});

test("dark form accessibility and error draft retention", async ({ page }) => {
  await login(page);
  await page.goto("/infrastructure/servers");
  await page.getByRole("button", { name: "Включить тёмную тему" }).click();
  await page
    .getByRole("button", { name: "Добавить сервер", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Название", { exact: true }).fill("qa-unsaved");
  await dialog.getByLabel("Адрес сервера").fill("127.0.0.1");
  await dialog.getByLabel("Пользователь SSH").fill("qa");
  await page.route("**/servers/api/create/", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: "QA controlled backend outage" }),
    }),
  );
  await dialog
    .getByRole("button", { name: "Добавить сервер", exact: true })
    .click();
  await expect(
    dialog.getByText("QA controlled backend outage", { exact: true }),
  ).toBeVisible();
  await expect(dialog.getByLabel("Название", { exact: true })).toHaveValue(
    "qa-unsaved",
  );
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(
    result.violations.map((v) => ({
      id: v.id,
      nodes: v.nodes.map((n) => n.target),
    })),
  ).toEqual([]);
  await page.screenshot({
    path: "test-results/server-form-dark.png",
    fullPage: true,
  });
});
