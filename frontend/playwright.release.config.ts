import { defineConfig } from "@playwright/test";

const baseURL = process.env.WEBTERM_RELEASE_BASE_URL;
if (!baseURL) {
  throw new Error("WEBTERM_RELEASE_BASE_URL is required");
}

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 10_000 },
  retries: 0,
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  use: {
    baseURL,
    ignoreHTTPSErrors: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
    viewport: { width: 1440, height: 900 },
  },
  projects: [{ name: "chromium-release", use: { browserName: "chromium" } }],
});
