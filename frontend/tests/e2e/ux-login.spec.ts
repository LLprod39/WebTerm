import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { credentials, assertNoOverflow } from "./helpers";

test("login UX: invalid credentials, advanced auth, pending fields and recoverable outage", async ({
  page,
}) => {
  await page.goto("/login");
  await expect(
    page.getByRole("heading", { name: "Вход в WebTerm", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("checkbox", {
      name: "Локальная учётная запись",
      exact: true,
    }),
  ).not.toBeVisible();
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(page.getByLabel("Имя пользователя")).toBeFocused();
  await page.getByLabel("Имя пользователя").fill(credentials.admin.username);
  await page.getByLabel("Пароль", { exact: true }).fill("wrong-password");
  await page
    .getByRole("button", { name: "Показать пароль", exact: true })
    .click();
  await expect(page.getByLabel("Пароль", { exact: true })).toHaveAttribute(
    "type",
    "text",
  );
  await page
    .getByRole("button", { name: "Скрыть пароль", exact: true })
    .click();
  await page
    .getByText("Дополнительные параметры входа", { exact: true })
    .click();
  await page
    .getByRole("checkbox", { name: "Локальная учётная запись", exact: true })
    .check();
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText(
    "Неверный логин или пароль",
  );
  await expect(page.getByLabel("Имя пользователя")).toHaveValue(
    credentials.admin.username,
  );
  let release: () => void = () => {};
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/auth/login/", async (route) => {
    await pending;
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({
        error: "Сервис входа временно недоступен. Повторите попытку.",
      }),
    });
  });
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Входим…", exact: true }),
  ).toBeDisabled();
  await expect(page.getByLabel("Имя пользователя")).toBeDisabled();
  await expect(page.getByLabel("Пароль", { exact: true })).toBeDisabled();
  release();
  await expect(page.getByRole("alert")).toContainText("временно недоступен");
  await expect(page.getByLabel("Пароль", { exact: true })).toHaveValue(
    "wrong-password",
  );
  await page.unroute("**/api/auth/login/");
  const a11y = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(a11y.violations).toEqual([]);
  await page.setViewportSize({ width: 390, height: 844 });
  await assertNoOverflow(page);
  await page.screenshot({
    path: "artifacts/ux/01-login-mobile.png",
    fullPage: true,
  });
  await page.getByLabel("Пароль", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Серверы", exact: true }),
  ).toBeVisible();
});
