import { defineConfig } from "@playwright/test";

/**
 * Records a real-browser tour of the actual WebTerm UI (mocked API fixtures).
 * Output: frontend/demo-recordings/
 *
 *   npm run demo:record
 */
export default defineConfig({
  testDir: "./e2e",
  testMatch: "**/product-demo-tour.spec.ts",
  timeout: 180_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  outputDir: "demo-recordings",
  use: {
    baseURL: "http://127.0.0.1:4173",
    trace: "off",
    screenshot: "off",
    video: {
      mode: "on",
      size: { width: 1440, height: 900 },
    },
    viewport: { width: 1440, height: 900 },
    locale: "ru-RU",
    actionTimeout: 12_000,
    navigationTimeout: 30_000,
  },
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4173",
    url: "http://127.0.0.1:4173",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
  projects: [
    {
      name: "chromium-demo",
      use: { browserName: "chromium" },
    },
  ],
});
