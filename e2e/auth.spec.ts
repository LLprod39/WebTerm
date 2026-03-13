import { expect, test } from "@playwright/test";
import { installApiHarness, json } from "./support/apiHarness";

test.describe("Auth flows", () => {
  test("redirects unauthenticated user to login", async ({ page }) => {
    let authenticated = false;

    await installApiHarness(page, (req) => {
      if (req.path === "/api/auth/session/" && req.method === "GET") {
        return json({
          authenticated,
          user: authenticated
            ? {
                id: 1,
                username: "admin",
                email: "admin@example.com",
                is_staff: true,
                features: { servers: true, settings: true, orchestrator: true },
              }
            : null,
        });
      }

      if (req.path === "/api/auth/login/" && req.method === "POST") {
        authenticated = true;
        return json({
          success: true,
          authenticated: true,
          next_url: "/servers",
          user: {
            id: 1,
            username: String(req.body?.username || "admin"),
            email: "admin@example.com",
            is_staff: true,
            features: { servers: true, settings: true, orchestrator: true },
          },
        });
      }

      if (req.path === "/servers/api/frontend/bootstrap/" && req.method === "GET") {
        return json({
          success: true,
          servers: [],
          groups: [],
          stats: { owned: 0, shared: 0, total: 0 },
          recent_activity: [],
        });
      }
    });

    await page.goto("/servers");

    await expect(page).toHaveURL(/\/login\?next=%2Fservers/);
    await expect(page.getByRole("heading", { name: "WebTermAI" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  });

  test("allows login and keeps language toggle understandable", async ({ page }) => {
    let authenticated = false;

    await installApiHarness(page, (req) => {
      if (req.path === "/api/auth/session/" && req.method === "GET") {
        return json({
          authenticated,
          user: authenticated
            ? {
                id: 1,
                username: "admin",
                email: "admin@example.com",
                is_staff: true,
                features: { servers: true, settings: true, orchestrator: true },
              }
            : null,
        });
      }

      if (req.path === "/api/auth/login/" && req.method === "POST") {
        authenticated = true;
        return json({
          success: true,
          authenticated: true,
          next_url: "/servers",
          user: {
            id: 1,
            username: String(req.body?.username || "admin"),
            email: "admin@example.com",
            is_staff: true,
            features: { servers: true, settings: true, orchestrator: true },
          },
        });
      }

      if (req.path === "/servers/api/frontend/bootstrap/" && req.method === "GET") {
        return json({
          success: true,
          servers: [
            {
              id: 1,
              name: "Web-01",
              host: "10.0.0.11",
              port: 22,
              username: "root",
              server_type: "ssh",
              rdp: false,
              status: "online",
              group_id: null,
              group_name: "Ungrouped",
              is_shared: false,
              can_edit: true,
              share_context_enabled: false,
              shared_by_username: "",
              terminal_path: "/servers/1/terminal",
              minimal_terminal_path: "/servers/1/terminal/minimal",
              last_connected: null,
            },
          ],
          groups: [],
          stats: { owned: 1, shared: 0, total: 1 },
          recent_activity: [],
        });
      }
    });

    await page.goto("/login");

    await page.getByRole("button", { name: "RU" }).click();
    await expect(page.getByRole("button", { name: "Войти" })).toBeVisible();

    await page.getByRole("button", { name: "EN" }).click();
    await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();

    await page.getByLabel("Username").fill("operator");
    await page.getByLabel("Password").fill("pass123");
    await page.getByRole("button", { name: "Sign in" }).click();

    await expect(page).toHaveURL(/\/servers$/);
    await expect(page.getByRole("heading", { name: "Infrastructure" })).toBeVisible();
  });
});
