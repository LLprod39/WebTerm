import { expect, test, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { credentials, login } from "./helpers";

const serverHome = "/infrastructure/servers";
const bootstrapPath = "/servers/api/frontend/bootstrap/";

async function serversHome(page: Page) {
  await page.goto("/");
  await expect(page).toHaveURL(new RegExp(`${serverHome}$`));
  await expect(
    page.getByRole("heading", { name: "Серверы", exact: true }),
  ).toBeVisible();
}

async function axe(page: Page) {
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(
    result.violations.map(({ id, nodes }) => ({
      id,
      targets: nodes.map(({ target }) => target),
    })),
  ).toEqual([]);
}

async function realAccount(page: Page) {
  await login(page);
  await serversHome(page);
  await page
    .getByRole("button", { name: "Включить тёмную тему", exact: true })
    .click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page
    .getByRole("button", { name: "Включить светлую тему", exact: true })
    .click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page
    .getByRole("button", { name: "Меню аккаунта", exact: true })
    .click();
  const account = page.getByRole("menu");
  await expect(account).toContainText(credentials.admin.username);
  await expect(account.getByRole("menuitem")).toHaveText(["Выйти"]);
  await page.getByRole("menuitem", { name: "Выйти", exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  const session = await page.request.get("/api/auth/session/");
  expect((await session.json()).authenticated).toBe(false);
  await page.getByLabel("Имя пользователя").fill(credentials.admin.username);
  await page.getByLabel("Пароль", { exact: true }).fill(credentials.password);
  await page
    .getByText("Дополнительные параметры входа", { exact: true })
    .click();
  await page
    .getByRole("checkbox", { name: "Локальная учётная запись", exact: true })
    .check();
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(page).toHaveURL(new RegExp(`${serverHome}$`));
  await expect(
    page.getByRole("heading", { name: "Серверы", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Меню аккаунта", exact: true }),
  ).toBeVisible();
}

async function roleDenied(page: Page) {
  await login(page);
  let bootstrapRequests = 0;
  page.on("request", (request) => {
    if (request.url().endsWith(bootstrapPath)) bootstrapRequests += 1;
  });
  await page.route("**/api/auth/session/", async (route) => {
    const response = await route.fetch();
    const session = await response.json();
    session.user.features.servers = false;
    await route.fulfill({ response, json: session });
  });
  await page.goto("/");
  await expect(page).toHaveURL(new RegExp(`${serverHome}$`));
  await expect(
    page.getByRole("heading", { name: "Доступ ограничен", exact: true }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("navigation", { name: "Основная навигация", exact: true })
      .getByRole("link", { name: "Серверы", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Обновить", exact: true }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Добавить сервер", exact: true }),
  ).toHaveCount(0);
  expect(bootstrapRequests).toBe(0);
}

test("shell UX: real QA theme, account logout and login", async ({ page }) => {
  await realAccount(page);
  await axe(page);
});

test("shell UX permission fixture: denied server access hides navigation and avoids bootstrap", async ({
  page,
}) => {
  await roleDenied(page);
});
