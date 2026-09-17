/**
 * Product demo tour — records real Chromium navigation through the actual SPA.
 * Uses platform API fixtures so screens match production UI chrome (not AI-generated).
 *
 * Flow: Dashboard → Servers (inventory + add) → server "Advanced":
 *       Access/Sharing → Notes + AI memory → Terminal (SSH) → Files → AI assistant
 *       → Agents → Studio → Settings → Servers finale.
 *
 * Run: npm run demo:record
 * Video: frontend/demo-recordings/**\/video.webm (copy to demo-assets after)
 */
import { expect, test, type Page } from "@playwright/test";
import { installPlatformMocks } from "./support/platformFixtures";

async function dwell(page: Page, ms = 1600) {
  await page.waitForTimeout(ms);
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
          this.onmessage?.({
            data: JSON.stringify({
              type: "output",
              data: "root@web-01:~$ uptime\n 18:24:01 up 2 days,  4:12,  1 user,  load average: 0.24, 0.31, 0.28\nroot@web-01:~$ ",
            }),
          });
        }, 40);
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

/** Best-effort click: does nothing if the target never shows (keeps the tour resilient). */
async function softClick(page: Page, locator: ReturnType<Page["locator"]>, ms = 1400): Promise<boolean> {
  const target = locator.first();
  if (await target.isVisible().catch(() => false)) {
    await target.click().catch(() => undefined);
    await dwell(page, ms);
    return true;
  }
  return false;
}

test.describe.configure({ mode: "serial" });

test("product demo tour — servers stack", async ({ page }) => {
  test.setTimeout(210_000);

  await installPlatformMocks(page, {
    authenticated: true,
    isStaff: true,
    lang: "ru",
    demoData: true,
    features: {
      servers: true,
      dashboard: true,
      agents: true,
      studio: true,
      settings: true,
      knowledge_base: true,
    },
  });
  await installTerminalSocketMock(page);

  // ── 1. Dashboard ──────────────────────────────────────────────
  await page.goto("/dashboard");
  await expect(page.locator("main").or(page.getByRole("main"))).toBeVisible({ timeout: 20_000 });
  await dwell(page, 2200);

  // ── 2. Servers inventory ──────────────────────────────────────
  await page.goto("/servers");
  await expect(page.getByRole("heading", { name: /Серверы|Servers/i })).toBeVisible({
    timeout: 15_000,
  });
  await dwell(page, 2400);

  // ── 3. Add server (open → preview → close) ────────────────────
  const addBtn = page.getByRole("button", { name: /^Добавить сервер$|Add server/i }).first();
  if (await addBtn.isVisible().catch(() => false)) {
    await addBtn.hover();
    await dwell(page, 700);
    await addBtn.click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible({ timeout: 8_000 });
    await dwell(page, 2200);
    await page.keyboard.press("Escape");
    await dwell(page, 700);
  }

  // ── 4. Server "Advanced" → Access / Sharing ───────────────────
  const advancedTrigger = page.getByRole("button", { name: /Открыть расширенные|Open advanced/i }).first();
  if (await advancedTrigger.isVisible().catch(() => false)) {
    await advancedTrigger.click();
    await softClick(page, page.getByRole("menuitem", { name: /^Расширенные$|Advanced/i }), 400);

    const advDialog = page.getByRole("dialog");
    await expect(advDialog).toBeVisible({ timeout: 8_000 });
    await dwell(page, 2200);

    // Sharing: grant a colleague access — the new share appears in the list.
    const shareInput = advDialog.getByPlaceholder(/логин|email|id/i).first();
    if (await shareInput.isVisible().catch(() => false)) {
      await shareInput.click();
      await shareInput.type("k.petrov", { delay: 55 });
      await dwell(page, 700);
      await softClick(page, advDialog.getByRole("button", { name: /^Поделиться$|^Share$/i }), 1600);
    }

    // ── 5. Notes (manual) + AI memory ───────────────────────────
    await softClick(page, advDialog.getByRole("button", { name: /^Знания$|Knowledge/i }), 1800);
    // Reveal the AI-memory section lower in the tab.
    const aiMemoryAnchor = advDialog.getByText(/Профиль сервера|Runbook/i).first();
    if (await aiMemoryAnchor.isVisible().catch(() => false)) {
      await aiMemoryAnchor.scrollIntoViewIfNeeded().catch(() => undefined);
      await dwell(page, 2400);
    } else {
      await dwell(page, 1600);
    }

    await page.keyboard.press("Escape");
    await dwell(page, 800);
  }

  // ── 6. Terminal (browser SSH) ─────────────────────────────────
  await page.goto("/servers/1/terminal");
  await dwell(page, 2600);

  // Files / SFTP panel
  await softClick(page, page.getByRole("button", { name: /^Файлы$|Files/i }), 2200);

  // AI assistant in server context
  const aiToggle = page
    .locator('button[title*="AI"]')
    .or(page.getByRole("button", { name: /^AI$|Ассистент/i }));
  await softClick(page, aiToggle, 2400);

  // ── 7. Agents ─────────────────────────────────────────────────
  await page.goto("/agents");
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible({ timeout: 12_000 });
  await dwell(page, 2200);

  const newAgent = page
    .getByRole("button", { name: /Новый агент|New agent|Создать.*агент|Create.*agent/i })
    .first();
  if (await newAgent.isVisible().catch(() => false)) {
    await newAgent.click();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible({ timeout: 10_000 });
    await dwell(page, 2000);
    const custom = dialog.getByRole("button", { name: /Вручную|Custom/i }).first();
    if (await custom.isVisible().catch(() => false)) {
      await custom.hover();
      await dwell(page, 900);
    }
    await page.keyboard.press("Escape");
    await dwell(page, 800);
  }

  // ── 8. Studio (brief) ─────────────────────────────────────────
  await page.goto("/studio");
  await dwell(page, 2200);

  // ── 9. Settings (brief) ───────────────────────────────────────
  await page.goto("/settings");
  await dwell(page, 2000);

  // ── 10. Servers finale ────────────────────────────────────────
  await page.goto("/servers");
  await dwell(page, 2400);
});
