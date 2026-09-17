import { expect, test } from "@playwright/test";

import { installPlatformMocks } from "./support/platformFixtures";

test("@smoke unready admin enters the first-run readiness wizard before the workspace", async ({ page }) => {
  await installPlatformMocks(page, {
    authenticated: true,
    isStaff: true,
    settingsReadiness: "warning",
  });

  await page.goto("/dashboard");

  await expect(page).toHaveURL(/\/settings\/readiness\?firstRun=1/);
  await expect(page.getByRole("heading", { name: "Prepare WebTerm for operations" })).toBeVisible();
  await expect(page.getByText("Configuration requires attention")).toBeVisible();

  await page.getByRole("button", { name: "Continue to workspace" }).click();

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: "Admin Dashboard" })).toBeVisible();
  await expect.poll(() => page.evaluate(() => localStorage.getItem("webterm.first-run-readiness.v1.1"))).toBe("seen");
});
