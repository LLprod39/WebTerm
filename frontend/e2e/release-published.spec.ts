import { expect, test } from "@playwright/test";

import { firstRunReadinessStorageKey } from "../src/lib/first-run-readiness";

type ServerBootstrapResponse = {
  success: boolean;
  servers: Array<{ id: number; name: string }>;
};

type ActivityResponse = {
  success: boolean;
  events: Array<{
    action: string;
    description: string;
    entity_id: string;
    entity_name: string;
    status: string;
  }>;
};

test("published digest serves the authenticated operator golden path", async ({ page }) => {
  const username = process.env.WEBTERM_RELEASE_ADMIN_USERNAME;
  const password = process.env.WEBTERM_RELEASE_ADMIN_PASSWORD;
  const baseURL = process.env.WEBTERM_RELEASE_BASE_URL;
  expect(username).toBeTruthy();
  expect(password).toBeTruthy();
  expect(baseURL).toBeTruthy();

  const health = await page.request.get("/api/health/");
  expect(health.ok()).toBeTruthy();
  expect((await health.json()).services.django).toBe("ok");

  const csrfResponse = await page.request.get("/api/auth/csrf/");
  expect(csrfResponse.ok()).toBeTruthy();
  const { csrfToken } = await csrfResponse.json();
  const login = await page.request.post("/api/auth/login/", {
    data: { username, password, auth_mode: "local" },
    headers: {
      "X-CSRFToken": csrfToken,
      Origin: baseURL!,
      Referer: `${baseURL}/`,
    },
  });
  expect(login.ok()).toBeTruthy();
  const loginPayload = (await login.json()) as { user: { id: number } };

  const readiness = await page.request.get("/api/settings/readiness/");
  expect(readiness.ok()).toBeTruthy();
  expect((await readiness.json()).success).toBe(true);
  await page.addInitScript(
    ({ readinessKey }) => {
      window.localStorage.setItem(readinessKey, "seen");
      window.localStorage.setItem("weu_lang", "en");
    },
    { readinessKey: firstRunReadinessStorageKey(loginPayload.user.id) },
  );

  const serverName = `Release SSH ${Date.now()}`;
  await page.goto("/servers");
  await page.getByRole("button", { name: "Add Server" }).click();

  const createDialog = page.getByRole("dialog", { name: "Create Server" });
  await createDialog.getByLabel(/^Name/).fill(serverName);
  await createDialog.getByLabel(/^Host/).fill("ssh-target");
  await createDialog.getByLabel(/^Port/).fill("2222");
  await createDialog.getByLabel(/^Username/).fill("smoke");
  await createDialog.getByLabel(/^Password/).fill("smoke-password");
  await createDialog.getByRole("button", { name: "Save & test" }).click();

  const hostKeyDialog = page.getByRole("dialog", { name: "Verify this SSH host key" });
  await expect(hostKeyDialog).toBeVisible();
  const fingerprint = (await hostKeyDialog.locator("code").first().textContent())?.trim();
  expect(fingerprint).toMatch(/^SHA256:/);
  await hostKeyDialog.getByLabel("Paste the verified fingerprint").fill(fingerprint!);
  await hostKeyDialog.getByRole("button", { name: "Trust key and test" }).click();
  await expect(hostKeyDialog).toBeHidden();
  await expect(page.getByText(serverName, { exact: true })).toBeVisible();

  const bootstrapResponse = await page.request.get("/servers/api/frontend/bootstrap/");
  expect(bootstrapResponse.ok()).toBeTruthy();
  const bootstrap = (await bootstrapResponse.json()) as ServerBootstrapResponse;
  const server = bootstrap.servers.find((item) => item.name === serverName);
  expect(server?.id).toBeTruthy();

  await page.goto(`/servers/${server!.id}/terminal`);
  await expect(page.locator('header[title*="Connected"]')).toBeVisible({ timeout: 30_000 });

  const commandMarker = `webterm-release-e2e-${Date.now()}`;
  const terminalInput = page.locator(".xterm-helper-textarea").last();
  await terminalInput.focus();
  await terminalInput.pressSequentially(`printf '${commandMarker}\\n'`);
  await terminalInput.press("Enter");
  await expect(page.locator(".xterm-rows")).toContainText(commandMarker, { timeout: 30_000 });

  await expect.poll(async () => {
    const activityResponse = await page.request.get(
      `/api/settings/activity/?limit=50&days=1&action=terminal_command&search=${encodeURIComponent(commandMarker)}`,
    );
    if (!activityResponse.ok()) return false;
    const activity = (await activityResponse.json()) as ActivityResponse;
    return activity.events.some((event) => (
      event.action === "terminal_command"
      && event.status === "success"
      && event.entity_id === String(server!.id)
      && event.entity_name === serverName
      && event.description.includes(commandMarker)
    ));
  }, { timeout: 30_000 }).toBe(true);

  await page.goto("/automation");
  await expect(page.locator("body")).toContainText(/Playbooks|Плейбуки/i);
  await expect(page.locator("body")).not.toContainText(/Internal Server Error/i);
});
