import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { login, assertNoOverflow } from "./helpers";

test("major workspaces pass accessibility and laptop layout checks", async ({
  page,
}) => {
  test.setTimeout(150_000);
  await login(page);
  await page.setViewportSize({ width: 1280, height: 800 });
  const violations: unknown[] = [];
  for (const path of [
    "/infrastructure/servers",
    "/automation/playbooks",
    "/automation/pipelines",
    "/automation/runs",
    "/intelligence/agents",
    "/intelligence/chat",
    "/intelligence/memory",
    "/governance/users",
    "/governance/audit",
    "/settings/general",
    "/settings/ai",
  ]) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    const result = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    violations.push(
      ...result.violations.map((v) => ({
        path,
        id: v.id,
        nodes: v.nodes.map((n) => n.target),
      })),
    );
    await assertNoOverflow(page);
  }
  expect(violations).toEqual([]);
});
