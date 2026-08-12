import { expect, test } from "@playwright/test";
import {
  collectSeriousAndCriticalViolations,
  expectViolationsWithinBudget,
} from "./support/a11y";
import { installPlatformMocks } from "./support/platformFixtures";

async function expectPilotReflow(page: import("@playwright/test").Page) {
  const geometry = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(geometry.scrollWidth, JSON.stringify(geometry)).toBeLessThanOrEqual(geometry.clientWidth + 1);
}

async function expectFlowDarkTextFloor(page: import("@playwright/test").Page) {
  await expect(page.locator("html")).toHaveAttribute("data-ui-style", "flow-dark");
  const undersized = await page.evaluate(() => Array.from(document.body.querySelectorAll<HTMLElement>("*"))
    .filter((element) => {
      const style = getComputedStyle(element);
      if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) === 0) return false;
      if (!Array.from(element.childNodes).some((node) => node.nodeType === Node.TEXT_NODE && node.textContent?.trim())) return false;
      return parseFloat(style.fontSize) < 12;
    })
    .slice(0, 10)
    .map((element) => ({
      tag: element.tagName.toLowerCase(),
      className: element.getAttribute("class") ?? "",
      fontSize: getComputedStyle(element).fontSize,
      text: element.textContent?.trim().slice(0, 60),
    })));
  expect(undersized).toEqual([]);
}

test.describe("Accessibility", () => {
  test("login page accessibility budget", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: false });

    await page.goto("/login");
    await expect(page.getByRole("heading", { name: /WebTerm/ })).toBeVisible();

    const violations = await collectSeriousAndCriticalViolations(page);
    expectViolationsWithinBudget(violations, {});
  });

  test("servers page accessibility budget", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true, isStaff: false });

    await page.goto("/servers");
    await expect(page.getByRole("heading", { name: "Infrastructure" })).toBeVisible();

    const violations = await collectSeriousAndCriticalViolations(page);
    expectViolationsWithinBudget(violations, {});
  });

  test("studio notifications page accessibility budget", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true });

    await page.goto("/studio/notifications");
    await expect(page.getByRole("heading", { name: "Notification Settings" })).toBeVisible();

    const violations = await collectSeriousAndCriticalViolations(page);
    expectViolationsWithinBudget(violations, {});
  });

  test("server create sheet accessibility budget", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true });

    await page.goto("/servers");
    await expect(page.getByRole("heading", { name: "Infrastructure" })).toBeVisible();
    await page.getByRole("button", { name: /Add Server/i }).click();
    await expect(page.getByRole("dialog").filter({ hasText: "Create Server" })).toBeVisible();

    const violations = await collectSeriousAndCriticalViolations(page);
    expectViolationsWithinBudget(violations, {});
  });

  test("agent wizard accessibility budget", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true });

    await page.goto("/agents");
    await expect(page.getByRole("heading", { name: "Agents", level: 1 })).toBeVisible();
    await page.getByRole("button", { name: "New agent" }).click();
    await expect(page.getByRole("dialog").getByRole("heading", { name: "Agent type" })).toBeVisible();

    const violations = await collectSeriousAndCriticalViolations(page);
    expectViolationsWithinBudget(violations, {});
  });

  test("settings users create drawer accessibility budget", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true });

    await page.goto("/settings/users");
    await expect(page.getByRole("heading", { name: "Users" })).toBeVisible();
    await page.getByRole("button", { name: "Create User" }).click();
    await expect(page.getByRole("dialog", { name: "Create User" })).toBeVisible();

    const violations = await collectSeriousAndCriticalViolations(page);
    expectViolationsWithinBudget(violations, {});
  });

  test("mars beta page accessibility budget", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true, features: { mars: true } });

    await page.goto("/mars");
    await expect(page.getByRole("heading", { name: /MARS beta/ })).toBeVisible();

    const violations = await collectSeriousAndCriticalViolations(page);
    expectViolationsWithinBudget(violations, {});
  });

  test("flow-dark pilot screens reflow at 390px and 200% zoom", async ({ page }, testInfo) => {
    await installPlatformMocks(page, { authenticated: true, features: { chat: true } });
    await page.setViewportSize({ width: 390, height: 844 });

    const mobileScreens = [
      { path: "/servers", ready: () => page.getByRole("heading", { name: "Infrastructure" }) },
      { path: "/agents", ready: () => page.getByRole("heading", { name: "Agents", level: 1 }) },
      { path: "/chat", ready: () => page.getByPlaceholder("Ask anything…") },
    ];
    for (const screen of mobileScreens) {
      await page.goto(screen.path);
      await expect(screen.ready()).toBeVisible();
      await expectPilotReflow(page);
      await expectFlowDarkTextFloor(page);
    }
    await testInfo.attach("flow-dark-mobile-390", {
      body: await page.screenshot({ fullPage: true }),
      contentType: "image/png",
    });

    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto("/agents");
    await expect(page.getByRole("heading", { name: "Agents", level: 1 })).toBeVisible();
    await page.evaluate(() => {
      document.documentElement.style.zoom = "2";
    });
    await expectPilotReflow(page);
    await expectFlowDarkTextFloor(page);
    await testInfo.attach("flow-dark-agents-200-percent", {
      body: await page.screenshot({ fullPage: true }),
      contentType: "image/png",
    });
  });
});
