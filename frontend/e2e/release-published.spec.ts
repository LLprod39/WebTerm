import { expect, test } from "@playwright/test";

test("published digest serves the authenticated release flow", async ({ page }) => {
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

  const readiness = await page.request.get("/api/settings/readiness/");
  expect(readiness.ok()).toBeTruthy();
  expect((await readiness.json()).success).toBe(true);

  await page.goto("/automation");
  await expect(page.locator("body")).toContainText(/Playbooks|Плейбуки/i);
  await expect(page.locator("body")).not.toContainText(/Internal Server Error/i);
});
