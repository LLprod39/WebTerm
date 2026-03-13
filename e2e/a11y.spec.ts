import { expect, test } from "@playwright/test";
import {
  collectSeriousAndCriticalViolations,
  expectViolationsWithinBudget,
} from "./support/a11y";
import { installPlatformMocks } from "./support/platformFixtures";

test.describe("Accessibility", () => {
  test("login page accessibility budget", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: false });

    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "WebTermAI" })).toBeVisible();

    const violations = await collectSeriousAndCriticalViolations(page);
    expectViolationsWithinBudget(violations, {
      "color-contrast": { impact: "serious", maxNodes: 2 },
    });
  });

  test("servers page accessibility budget", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true, isStaff: false });

    await page.goto("/servers");
    await expect(page.getByRole("heading", { name: "Infrastructure" })).toBeVisible();

    const violations = await collectSeriousAndCriticalViolations(page);
    expectViolationsWithinBudget(violations, {
      "button-name": { impact: "critical", maxNodes: 4 },
      "color-contrast": { impact: "serious", maxNodes: 3 },
      "link-name": { impact: "serious", maxNodes: 1 },
    });
  });

  test("studio notifications page accessibility budget", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true });

    await page.goto("/studio/notifications");
    await expect(page.getByRole("heading", { name: "Notification Settings" })).toBeVisible();

    const violations = await collectSeriousAndCriticalViolations(page);
    expectViolationsWithinBudget(violations, {
      "button-name": { impact: "critical", maxNodes: 2 },
      "color-contrast": { impact: "serious", maxNodes: 4 },
      "link-in-text-block": { impact: "serious", maxNodes: 1 },
      "link-name": { impact: "serious", maxNodes: 1 },
    });
  });
});
