import { writeFile } from "node:fs/promises";
import { performance } from "node:perf_hooks";

import { expect, test } from "@playwright/test";

import { installPlatformMocks } from "./support/platformFixtures";

const MAX_P95_INTERACTION_MS = 1_000;

test("warm primary navigation stays within the interaction latency budget", async ({ page }, testInfo) => {
  await installPlatformMocks(page, { authenticated: true });
  await page.goto("/servers");
  await expect(page.getByRole("heading", { name: "Infrastructure" })).toBeVisible();

  // Load both route chunks before measuring UI interaction latency.
  await page.getByRole("link", { name: "Dashboard" }).first().click();
  await expect(page.getByRole("heading", { name: "My workspace" })).toBeVisible();
  await page.getByRole("link", { name: "Servers" }).first().click();
  await expect(page.getByRole("heading", { name: "Infrastructure" })).toBeVisible();

  const samples = [];
  for (let index = 0; index < 3; index += 1) {
    let startedAt = performance.now();
    await page.getByRole("link", { name: "Dashboard" }).first().click();
    await expect(page.getByRole("heading", { name: "My workspace" })).toBeVisible();
    samples.push({ interaction: "servers-to-dashboard", durationMs: performance.now() - startedAt });

    startedAt = performance.now();
    await page.getByRole("link", { name: "Servers" }).first().click();
    await expect(page.getByRole("heading", { name: "Infrastructure" })).toBeVisible();
    samples.push({ interaction: "dashboard-to-servers", durationMs: performance.now() - startedAt });
  }

  const durations = samples.map((sample) => sample.durationMs).sort((left, right) => left - right);
  const p95Ms = durations[Math.ceil(durations.length * 0.95) - 1];
  const report = {
    state: p95Ms <= MAX_P95_INTERACTION_MS ? "passed" : "failed",
    budget: { maxP95Ms: MAX_P95_INTERACTION_MS, sampleCount: samples.length, mode: "warm-client-navigation" },
    p95Ms,
    samples,
  };
  const reportPath = testInfo.outputPath("interaction-latency.json");
  await writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`);
  await testInfo.attach("interaction-latency", { path: reportPath, contentType: "application/json" });

  expect(p95Ms, `Warm navigation p95 ${p95Ms.toFixed(1)} ms exceeds ${MAX_P95_INTERACTION_MS} ms`).toBeLessThanOrEqual(MAX_P95_INTERACTION_MS);
});
