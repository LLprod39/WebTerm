import { test, expect } from "@playwright/test";
test("published release serves authenticated operational workspace", async ({
  page,
}) => {
  const username = process.env.WEBTERM_RELEASE_ADMIN_USERNAME;
  const password = process.env.WEBTERM_RELEASE_ADMIN_PASSWORD;
  if (!username || !password)
    throw new Error(
      "Release operator credentials must be supplied by the release smoke environment",
    );
  const ready = await page.request.get("/api/ready/");
  expect(ready.ok()).toBeTruthy();
  await page.goto("/login");
  await page.getByLabel("Имя пользователя").fill(username);
  await page.getByLabel("Пароль", { exact: true }).fill(password);
  await page.getByLabel("Локальная учётная запись").check();
  await page.getByRole("button", { name: "Войти", exact: true }).click();
  await expect(
    page.getByRole("navigation", { name: "Основная навигация" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Серверы", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Серверы", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Добавить сервер", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Включить тёмную тему" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("link", { name: "Пользователи", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Пользователи", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
});
