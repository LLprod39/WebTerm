import { expect, test } from "@playwright/test";
import { installPlatformMocks } from "./support/platformFixtures";

test.describe("Smoke scenarios", () => {
  test("@smoke signs in and opens infrastructure", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: false });

    await page.goto("/servers");
    await expect(page).toHaveURL(/\/login\?next=%2Fservers/);

    await page.getByLabel("Username").fill("operator");
    await page.getByLabel("Password").fill("pass123");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page).toHaveURL(/\/servers$/);
    await expect(page.getByRole("heading", { name: "Infrastructure" })).toBeVisible();
  });

  test("@smoke opens key sections from sidebar", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true });

    await page.goto("/servers");
    await expect(page.getByRole("heading", { name: "Infrastructure" })).toBeVisible();

    await page.getByRole("link", { name: "Dashboard" }).first().click();
    await expect(page.getByRole("heading", { name: "Server Dashboard" })).toBeVisible();

    await page.getByRole("link", { name: "Studio" }).first().click();
    await expect(page.getByRole("heading", { name: "Pipeline Workspace" })).toBeVisible();

    await page.getByRole("link", { name: "Settings" }).first().click();
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
  });

  test("@smoke starts pipeline run from studio", async ({ page }) => {
    const { harness } = await installPlatformMocks(page, { authenticated: true });

    await page.goto("/studio");
    await expect(page.getByRole("heading", { name: "Pipeline Workspace" })).toBeVisible();

    await page.getByRole("button", { name: /^Run$/ }).first().click();
    expect(harness.getCalls("/api/studio/pipelines/101/run/", "POST").length).toBeGreaterThan(0);
  });
});
