import { test, expect } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { login } from "./helpers";

test("warm navigation and search stay within the interaction budget", async ({
  page,
}) => {
  await login(page);
  await page.goto("/infrastructure/servers");
  await expect(
    page.getByRole("link", { name: "qa-ssh-local", exact: true }),
  ).toBeVisible();
  const start = Date.now();
  await page
    .getByRole("textbox", { name: "Поиск по имени или адресу…", exact: true })
    .fill("qa-ssh-local");
  await expect(
    page.getByRole("link", { name: "qa-ssh-local", exact: true }),
  ).toBeVisible();
  const searchMs = Date.now() - start;
  await page.getByRole("link", { name: "qa-ssh-local", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "qa-ssh-local", exact: true }),
  ).toBeVisible();
  const navigationMs = Date.now() - start - searchMs;
  await mkdir("artifacts", { recursive: true });
  await writeFile(
    "artifacts/interaction-budget.json",
    JSON.stringify(
      {
        searchMs,
        navigationMs,
        limits: { searchMs: 1500, navigationMs: 5000 },
        environment: "local real backend, Chromium, development bundle",
      },
      null,
      2,
    ),
  );
  expect(searchMs).toBeLessThan(1500);
  expect(navigationMs).toBeLessThan(5000);
});
