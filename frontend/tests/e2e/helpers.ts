import { readFileSync } from "node:fs";
import { expect, type Page } from "@playwright/test";

export const credentials = JSON.parse(
  readFileSync(new URL("../.auth/credentials.json", import.meta.url), "utf8"),
) as {
  password: string;
  serverId: number;
  groupId: number;
  fingerprint: string;
  admin: { username: string };
  viewer: { username: string };
};
export async function login(page: Page, role: "admin" | "viewer" = "admin") {
  const csrfResponse = await page.request.get("/api/auth/csrf/");
  expect(csrfResponse.ok()).toBeTruthy();
  const { csrfToken } = await csrfResponse.json();
  const response = await page.request.post("/api/auth/login/", {
    headers: { "X-CSRFToken": csrfToken, Origin: "http://127.0.0.1:8091" },
    data: {
      username: credentials[role].username,
      password: credentials.password,
      auth_mode: "local",
    },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
}
export async function assertNoOverflow(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > innerWidth + 1,
  );
  expect(
    overflow,
    "Page must not have horizontal document overflow",
  ).toBeFalsy();
}
