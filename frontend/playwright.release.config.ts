import { defineConfig, devices } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  testMatch: "release-published.spec.ts",
  workers: 1,
  timeout: 60_000,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    ...devices["Desktop Chrome"],
    baseURL: process.env.WEBTERM_RELEASE_BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
