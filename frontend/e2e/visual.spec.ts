import { expect, Page, test } from "@playwright/test";
import { installPlatformMocks } from "./support/platformFixtures";

async function stabilizeVisuals(page: Page): Promise<void> {
  await page.addStyleTag({
    content: `
      *,
      *::before,
      *::after {
        animation: none !important;
        transition: none !important;
        caret-color: transparent !important;
      }
    `,
  });
}

test.describe("Visual regression", () => {
  test("login page snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: false });
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "WebTermAI" })).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("login-page.png", { animations: "disabled", fullPage: true });
  });

  test("servers page snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true });
    await page.goto("/servers");
    await expect(page.getByRole("heading", { name: "Infrastructure" })).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("servers-page.png", { animations: "disabled", fullPage: true });
  });

  test("studio page snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true });
    await page.goto("/studio");
    await expect(page.getByRole("heading", { name: "Pipeline Workspace" })).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("studio-page.png", { animations: "disabled", fullPage: true });
  });

  test("settings page snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true });
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("settings-page.png", { animations: "disabled", fullPage: true });
  });
});
