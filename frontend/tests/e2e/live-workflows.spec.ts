import { test, expect, type WebSocket } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { credentials, login, assertNoOverflow } from "./helpers";

test("real login establishes session; theme and project navigation remain usable", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("Имя пользователя").fill(credentials.admin.username);
  await page.getByLabel("Пароль", { exact: true }).fill(credentials.password);
  await page
    .getByText("Дополнительные параметры входа", { exact: true })
    .click();
  await page.getByText("Локальная учётная запись", { exact: true }).check();
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(
    page.getByRole("navigation", { name: "Основная навигация" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Включить тёмную тему" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", { name: "Выбрать рабочий проект" }).click();
  await expect(page.getByRole("dialog")).toContainText("Frontend QA");
  await page.keyboard.press("Escape");
  await assertNoOverflow(page);
  await page.screenshot({
    path: "test-results/live-overview-dark.png",
    fullPage: true,
  });
});

test("inventory, server detail, SFTP and connected SSH use the real backend", async ({
  page,
}) => {
  await login(page);
  const errors: string[] = [];
  let terminalOutput = "";
  page.on("websocket", (socket) =>
    socket.on("framereceived", ({ payload }) => {
      try {
        const event = JSON.parse(String(payload));
        if (event.type === "output") terminalOutput += event.data;
      } catch {
        /* Other frames are not terminal output. */
      }
    }),
  );
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/infrastructure/servers");
  await expect(
    page.getByRole("link", { name: "qa-ssh-local", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "qa-ssh-local", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "qa-ssh-local", exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Файлы", exact: true }).click();
  await expect(page.getByText("readme.txt", { exact: true })).toBeVisible();
  await page.screenshot({
    path: "test-results/live-server-files-light.png",
    fullPage: true,
  });
  await page
    .getByRole("link", { name: "Открыть терминал", exact: true })
    .click();
  await expect(
    page.getByText("Подключено", { exact: true }).first(),
  ).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".xterm-screen")).toBeVisible();
  await page
    .locator(".xterm-helper-textarea")
    .pressSequentially("echo WEBTERM_E2E_OK");
  await page.locator(".xterm-helper-textarea").press("Enter");
  await expect
    .poll(() => terminalOutput.replace(/\r/g, ""))
    .toContain("\nWEBTERM_E2E_OK\nqa@fixture");
  await assertNoOverflow(page);
  await page.getByRole("button", { name: "Настройки терминала" }).click();
  await page.getByLabel("Размер шрифта", { exact: true }).fill("16");
  await page.getByRole("button", { name: "Сохранить настройки" }).click();
  await expect(page.getByLabel("Размер шрифта терминала")).toHaveValue("16");
  await page
    .locator(".xterm-helper-textarea")
    .pressSequentially("nano /readme.txt");
  await page.locator(".xterm-helper-textarea").press("Enter");
  await expect(page.getByLabel("Содержимое удалённого файла")).toBeVisible();
  await page.keyboard.press("Escape");
  await page.screenshot({
    path: "test-results/live-terminal.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("terminal route changes preserve cancellation and replace the confirmed SSH session", async ({
  page,
}) => {
  expect(
    test.info().project.use.baseURL,
    "This mutation test must use the isolated QA frontend.",
  ).toBe("http://127.0.0.1:8091");
  await login(page);
  const { csrfToken } = await (
    await page.request.get("/api/auth/csrf/")
  ).json();
  const headers = {
    "X-CSRFToken": csrfToken,
    Origin: "http://127.0.0.1:8091",
  };
  const name = `qa-terminal-route-${Date.now()}`;
  // This metadata row points only to the local fixture. Without a stored
  // password its terminal waits for input and never starts a remote command.
  const response = await page.request.post("/servers/api/create/", {
    headers,
    data: {
      name,
      host: "127.0.0.1",
      port: 22391,
      username: "qa",
      auth_method: "password",
    },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  const secondId = (await response.json()).server_id as number;
  const firstPath = `/infrastructure/terminal/${credentials.serverId}`;
  const secondPath = `/infrastructure/terminal/${secondId}`;
  let connectedFirstSocket: WebSocket | undefined;
  let firstClosed = false;
  let secondOpened = false;
  page.on("websocket", (socket) => {
    if (
      socket.url().includes(`/ws/servers/${credentials.serverId}/terminal/`)
    ) {
      socket.on("framereceived", ({ payload }) => {
        const event = JSON.parse(String(payload));
        // StrictMode closes an initial transport before SSH connects. Track
        // the actual connected stream, and never replace it on reconnect.
        if (
          event.type === "status" &&
          event.status === "connected" &&
          !connectedFirstSocket
        )
          connectedFirstSocket = socket;
      });
      socket.on("close", () => {
        if (socket === connectedFirstSocket) firstClosed = true;
      });
    }
    if (socket.url().includes(`/ws/servers/${secondId}/terminal/`))
      secondOpened = true;
  });
  try {
    // Seed two same-document history entries before React Router starts so
    // Back exercises a real SPA parameter change, without a document reload.
    await page.addInitScript(
      ({ firstPath, secondPath }) => {
        if (location.pathname !== firstPath) return;
        history.replaceState({ idx: 0, key: "terminal-b" }, "", secondPath);
        history.pushState({ idx: 1, key: "terminal-a" }, "", firstPath);
      },
      { firstPath, secondPath },
    );
    await page.goto(firstPath);
    await expect(
      page.getByText("Подключено", { exact: true }).first(),
    ).toBeVisible({ timeout: 20_000 });
    await expect.poll(() => !!connectedFirstSocket).toBe(true);
    await page.evaluate(() => history.back());
    const confirm = page.getByRole("dialog", { name: "Покинуть терминал?" });
    await expect(confirm).toBeVisible();
    await confirm.getByRole("button", { name: "Отмена", exact: true }).click();
    await expect(confirm).not.toBeVisible();
    await expect(page).toHaveURL(new RegExp(`${firstPath}$`));
    expect(firstClosed).toBe(false);

    await page.evaluate(() => history.back());
    await expect(confirm).toBeVisible();
    await confirm
      .getByRole("button", { name: "Закрыть сеансы и перейти", exact: true })
      .click();
    await expect(page).toHaveURL(new RegExp(`${secondPath}$`));
    await expect(page.getByRole("tab", { name, exact: true })).toBeVisible();
    await expect(
      page.getByRole("tab", { name: "qa-ssh-local", exact: true }),
    ).toHaveCount(0);
    await expect(page.getByLabel("Пароль SSH", { exact: true })).toBeVisible();
    await expect.poll(() => firstClosed).toBe(true);
    await expect.poll(() => secondOpened).toBe(true);
  } finally {
    await page.goto("/infrastructure/servers");
    const deleted = await page.request.post(
      `/servers/api/${secondId}/delete/`,
      {
        headers,
      },
    );
    expect(deleted.ok(), await deleted.text()).toBeTruthy();
  }
});

test("viewer is denied protected routes and does not see administrative navigation", async ({
  page,
}) => {
  await login(page, "viewer");
  await page.goto("/governance/users");
  await expect(
    page.getByText(/Недостаточно прав|Доступ ограничен|Нет доступа/).first(),
  ).toBeVisible();
  await expect(
    page
      .getByRole("navigation", { name: "Основная навигация", exact: true })
      .getByRole("link", { name: "Пользователи", exact: true }),
  ).toHaveCount(0);
  const response = await page.request.get("/api/access/users/");
  expect(response.status()).toBe(403);
});

test("core modules render against live contracts without uncaught errors", async ({
  page,
}) => {
  await login(page);
  const errors: string[] = [];
  const serverFailures: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("response", (response) => {
    if (
      response.status() >= 500 &&
      /\/(api|servers\/api)\//.test(response.url())
    )
      serverFailures.push(
        `${response.status()} ${new URL(response.url()).pathname}`,
      );
  });
  for (const path of [
    "/automation/playbooks",
    "/automation/pipelines",
    "/automation/runs",
    "/automation/drafts",
    "/automation/schedules",
    "/intelligence/agents",
    "/intelligence/chat",
    "/intelligence/skills",
    "/intelligence/mcp",
    "/intelligence/memory",
    "/intelligence/mars",
    "/governance/users",
    "/governance/groups",
    "/governance/permissions",
    "/governance/audit",
    "/settings/general",
    "/settings/ai",
    "/settings/identity",
  ]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.locator("#main-content")).not.toContainText(
      "Страница не найдена",
    );
    await assertNoOverflow(page);
  }
  expect(errors).toEqual([]);
  expect(serverFailures).toEqual([]);
});

test("keyboard, form labels and contrast pass accessibility checks at laptop size", async ({
  page,
}) => {
  await login(page);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/infrastructure/servers");
  await expect(
    page.getByRole("link", { name: "qa-ssh-local", exact: true }),
  ).toBeVisible();
  const report = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(
    report.violations.map((v) => ({
      id: v.id,
      impact: v.impact,
      nodes: v.nodes.map((n) => n.target),
    })),
  ).toEqual([]);
  await page
    .getByRole("link", { name: "qa-ssh-local", exact: true })
    .press("Enter");
  await expect(
    page.getByRole("heading", { name: "qa-ssh-local", exact: true }),
  ).toBeVisible();
  await assertNoOverflow(page);
  await page.screenshot({
    path: "test-results/live-desktop-navigation.png",
    fullPage: true,
  });
});
