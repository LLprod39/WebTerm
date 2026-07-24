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

async function installTerminalSocketMock(page: Page): Promise<void> {
  await page.addInitScript(() => {
    class MockWebSocket {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSING = 2;
      static CLOSED = 3;

      url: string;
      readyState = MockWebSocket.CONNECTING;
      onopen: ((event?: Event) => void) | null = null;
      onmessage: ((event: { data: string }) => void) | null = null;
      onerror: ((event?: Event) => void) | null = null;
      onclose: ((event: { code: number; reason: string }) => void) | null = null;

      constructor(url: string) {
        this.url = url;
        window.setTimeout(() => {
          this.readyState = MockWebSocket.OPEN;
          this.onopen?.(new Event("open"));
          this.onmessage?.({ data: JSON.stringify({ type: "status", status: "connected" }) });
          this.onmessage?.({ data: JSON.stringify({ type: "output", data: "deploy@web-01:~$ systemctl status webterm\nactive (running)\n" }) });
        }, 0);
      }

      send() {}

      close(code = 1000, reason = "") {
        this.readyState = MockWebSocket.CLOSED;
        this.onclose?.({ code, reason });
      }
    }

    Object.defineProperty(window, "WebSocket", {
      configurable: true,
      writable: true,
      value: MockWebSocket,
    });
  });
}

test.describe("Visual regression", () => {
  test("login page snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: false });
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: /WebTerm/ })).toBeVisible();
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

  test("user dashboard snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true, lang: "ru" });
    await page.goto("/dashboard");
    await expect(page.getByRole("heading", { name: "Мой воркспейс" })).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("user-dashboard.png", { animations: "disabled", fullPage: true });
  });

  test("agents page snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true });
    await page.goto("/agents");
    await expect(page.getByRole("heading", { level: 1, name: "Agents" })).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("agents-page.png", { animations: "disabled", fullPage: true });
  });

  test("agent wizard review snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true });
    await page.goto("/agents");
    await page.getByRole("button", { name: "New agent" }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("heading", { name: "Agent type" })).toBeVisible();
    await dialog.getByRole("button", { name: /Custom/i }).click();
    await dialog.getByPlaceholder("Log analysis").fill("Disk Audit");
    await dialog.locator("textarea").nth(0).fill("hostname\nuptime");
    await dialog.getByRole("button", { name: "Next" }).click();
    await dialog.getByRole("button", { name: /Web-01/i }).click();
    await dialog.getByRole("button", { name: "Next" }).click();
    await dialog.getByRole("button", { name: "Next" }).click();
    await expect(dialog.getByText("Preflight passed")).toBeVisible();

    await stabilizeVisuals(page);
    await expect(dialog).toHaveScreenshot("agent-wizard-review.png", { animations: "disabled" });
  });

  test("agent run page snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true });
    await page.goto("/agents/run/901");
    await expect(page.getByRole("heading", { name: "Patch Rollout" })).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("agent-run-page.png", { animations: "disabled", fullPage: true });
  });

  test("terminal files panel snapshot", async ({ page }) => {
    await installTerminalSocketMock(page);
    await installPlatformMocks(page, { authenticated: true, lang: "ru" });
    await page.goto("/servers/1/terminal");
    await expect(page.getByRole("heading", { name: "Web-01" })).toBeVisible();
    await page.getByRole("button", { name: "Файлы" }).click();
    await expect(page.getByText("Файлы SFTP").first()).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("terminal-files-panel.png", { animations: "disabled", fullPage: true });
  });

  test("studio page snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true });
    await page.goto("/studio");
    await expect(page.getByRole("heading", { name: "Pipelines", exact: true })).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("studio-page.png", { animations: "disabled", fullPage: true });
  });

  test("studio drafts page snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true, lang: "en" });
    await page.goto("/studio/drafts?draft=501");
    await expect(page.getByRole("heading", { name: /Pipeline drafts|Черновики пайплайнов/ })).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText("Daily health report").first()).toBeVisible({ timeout: 20_000 });
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("studio-drafts-page.png", { animations: "disabled", fullPage: true });
  });

  test("studio pipeline editor snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true });
    await page.goto("/studio/pipeline/101");
    await expect(page.getByPlaceholder("Pipeline name…")).toHaveValue("Nightly Patch", { timeout: 20_000 });
    await expect(page.getByRole("button", { name: "Validate" })).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("studio-pipeline-editor.png", { animations: "disabled", fullPage: true });
  });

  test("studio runs page snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true });
    await page.goto("/studio/runs");
    await expect(page.getByRole("heading", { name: "Execution History" })).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("studio-runs-page.png", { animations: "disabled", fullPage: true });
  });

  test("studio execution profiles page snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true });
    await page.goto("/studio/agents");
    await expect(page.getByRole("heading", { name: "Execution Profiles" })).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("studio-execution-profiles-page.png", { animations: "disabled", fullPage: true });
  });

  test("mcp registry page snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true });
    await page.goto("/studio/mcp");
    await expect(page.getByRole("heading", { name: "MCP Registry" })).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("mcp-registry-page.png", { animations: "disabled", fullPage: true });
  });

  test("notifications settings dirty state snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true });
    await page.goto("/studio/notifications");
    await expect(page.getByRole("heading", { name: "Notification Settings" })).toBeVisible();
    await page.locator('input[type="password"]').first().fill("visual-token");
    await expect(page.getByText("You have unsaved changes")).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("notifications-settings-dirty.png", { animations: "disabled", fullPage: true });
  });

  test("settings page snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true });
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("settings-page.png", { animations: "disabled", fullPage: true });
  });

  test("settings access page snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true });
    await page.goto("/settings/access");
    await expect(page.getByRole("heading", { name: "Access Control" })).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("settings-access-page.png", { animations: "disabled", fullPage: true });
  });

  test("settings users page snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true });
    await page.goto("/settings/users");
    await expect(page.getByRole("heading", { name: "Users" })).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("settings-users-page.png", { animations: "disabled", fullPage: true });
  });

  test("settings groups page snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true });
    await page.goto("/settings/groups");
    await expect(page.getByRole("heading", { name: "Groups" })).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("settings-groups-page.png", { animations: "disabled", fullPage: true });
  });

  test("settings permissions page snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true });
    await page.goto("/settings/permissions");
    await expect(page.getByRole("heading", { name: "Permissions", exact: true })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Effective Access Matrix" })).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("settings-permissions-page.png", { animations: "disabled", fullPage: true });
  });

  test("settings sso page snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true });
    await page.goto("/settings/sso");
    await expect(page.getByRole("heading", { name: "Domain Authentication" })).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("settings-sso-page.png", { animations: "disabled", fullPage: true });
  });

  test("settings audit page snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true, isStaff: true });
    await page.goto("/settings/audit");
    await expect(page.getByRole("heading", { name: "Аудит и журнал" })).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("settings-audit-page.png", { animations: "disabled", fullPage: true });
  });

  test("settings kubernetes page snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true, isStaff: true, lang: "ru", features: { kubernetes: true }, kubernetesState: "healthy" });
    await page.goto("/settings/kubernetes");
    await expect(page.getByRole("heading", { name: "Kubernetes Ops" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Настройка провайдеров" })).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("settings-kubernetes-page.png", { animations: "disabled", fullPage: true });
  });

  test("kubernetes empty state snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true, lang: "ru", features: { kubernetes: true }, kubernetesState: "empty" });
    await page.goto("/kubernetes");
    await expect(page.getByRole("heading", { name: "Kubernetes Ops" })).toBeVisible();
    await expect(page.getByRole("heading", { level: 2, name: "Кластеры" })).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("kubernetes-empty-state.png", { animations: "disabled", fullPage: true });
  });

  test("kubernetes healthy inventory snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true, lang: "ru", features: { kubernetes: true }, kubernetesState: "healthy" });
    await page.goto("/kubernetes");
    await expect(page.getByRole("heading", { name: "Kubernetes Ops" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "prod-kz-1" })).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("kubernetes-healthy-inventory.png", { animations: "disabled", fullPage: true });
  });

  test("kubernetes degraded inventory snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true, lang: "ru", features: { kubernetes: true }, kubernetesState: "degraded" });
    await page.goto("/kubernetes");
    await expect(page.getByRole("heading", { name: "Kubernetes Ops" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "prod-eu-1" })).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("kubernetes-degraded-inventory.png", { animations: "disabled", fullPage: true });
  });

  test("mars beta page snapshot", async ({ page }) => {
    await installPlatformMocks(page, { authenticated: true, features: { mars: true } });
    await page.goto("/mars");
    await expect(page.getByRole("heading", { name: "MARS beta - AI development" })).toBeVisible();
    await expect(page.getByText("Project history")).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("mars-beta-page.png", { animations: "disabled", fullPage: true });
  });

  test("servers page mobile snapshot", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await installPlatformMocks(page, { authenticated: true });
    await page.goto("/servers");
    await expect(page.getByRole("heading", { name: "Infrastructure" })).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("servers-page-mobile.png", { animations: "disabled", fullPage: true });
  });

  test("agent wizard mobile snapshot", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await installPlatformMocks(page, { authenticated: true, agentList: "empty" });
    await page.goto("/agents");
    await page.getByRole("button", { name: "New agent" }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("heading", { name: "Agent type" })).toBeVisible();
    await dialog.getByRole("button", { name: /Custom/i }).click();
    await dialog.getByPlaceholder("Log analysis").fill("Disk Audit");
    await dialog.locator("textarea").nth(0).fill("hostname\nuptime");
    await dialog.getByRole("button", { name: "Next" }).click();
    await expect(dialog.getByPlaceholder("Search by name, host, or group")).toBeVisible();
    await expect(dialog.getByRole("heading", { name: "Schedule" })).toBeVisible();

    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("agent-wizard-mobile.png", { animations: "disabled", fullPage: true });
  });

  test("terminal files panel mobile snapshot", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await installTerminalSocketMock(page);
    await installPlatformMocks(page, { authenticated: true, lang: "ru" });
    await page.goto("/servers/1/terminal");
    await expect(page.getByRole("heading", { name: "Web-01" })).toBeVisible();
    await page.getByRole("button", { name: "Файлы" }).click();
    await expect(page.getByText("Файлы SFTP").first()).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("terminal-files-panel-mobile.png", { animations: "disabled", fullPage: true });
  });

  test("settings page tablet snapshot", async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 768 });
    await installPlatformMocks(page, { authenticated: true });
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();
    await stabilizeVisuals(page);
    await expect(page).toHaveScreenshot("settings-page-tablet.png", { animations: "disabled", fullPage: true });
  });
});
