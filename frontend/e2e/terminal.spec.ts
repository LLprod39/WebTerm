import { expect, test, type Page } from "@playwright/test";
import { installApiHarness, json } from "./support/apiHarness";

const fullFeatures = {
  servers: true,
  dashboard: true,
  agents: true,
  studio: true,
  settings: true,
  orchestrator: true,
};

async function installTerminalSocketMock(page: Page) {
  await page.addInitScript(() => {
    const sockets: any[] = [];
    const terminalSockets = () => sockets.filter((socket) => String(socket.url || "").includes("/ws/servers/"));

    class MockWebSocket {
      static CONNECTING = 0;
      static OPEN = 1;
      static CLOSING = 2;
      static CLOSED = 3;

      url: string;
      readyState = MockWebSocket.CONNECTING;
      sent: string[] = [];
      onopen: ((event?: any) => void) | null = null;
      onmessage: ((event: { data: string }) => void) | null = null;
      onerror: ((event?: any) => void) | null = null;
      onclose: ((event: { code: number; reason: string }) => void) | null = null;

      constructor(url: string) {
        this.url = url;
        sockets.push(this);
        window.setTimeout(() => {
          if (this.readyState !== MockWebSocket.CONNECTING) return;
          this.readyState = MockWebSocket.OPEN;
          this.onopen?.({ type: "open" });
          window.setTimeout(() => {
            if (this.readyState !== MockWebSocket.OPEN) return;
            this.onmessage?.({ data: JSON.stringify({ type: "status", status: "connected" }) });
          }, 0);
        }, 0);
      }

      send(data: string) {
        this.sent.push(String(data));
      }

      close(code = 1000, reason = "") {
        if (this.readyState === MockWebSocket.CLOSED) return;
        this.readyState = MockWebSocket.CLOSED;
        this.onclose?.({ code, reason });
      }

      __serverMessage(payload: Record<string, unknown>) {
        if (this.readyState !== MockWebSocket.OPEN) return;
        this.onmessage?.({ data: JSON.stringify(payload) });
      }

      __serverClose(code = 1006, reason = "") {
        if (this.readyState === MockWebSocket.CLOSED) return;
        this.readyState = MockWebSocket.CLOSED;
        this.onclose?.({ code, reason });
      }
    }

    Object.defineProperty(window, "__terminalWsMock", {
      configurable: true,
      value: {
        getState: () =>
          terminalSockets().map((socket, index) => ({
            index,
            url: socket.url,
            readyState: socket.readyState,
            sent: [...socket.sent],
          })),
        closeFromServer: (index: number, code = 1006, reason = "") => {
          terminalSockets()[index]?.__serverClose(code, reason);
        },
        sendFromServer: (index: number, payload: Record<string, unknown>) => {
          terminalSockets()[index]?.__serverMessage(payload);
        },
      },
    });

    Object.defineProperty(window, "WebSocket", {
      configurable: true,
      writable: true,
      value: MockWebSocket,
    });
  });
}

function makeTerminalHandler() {
  return async (req: any) => {
    if (req.path === "/api/auth/session/" && req.method === "GET") {
      return json({
        authenticated: true,
        user: {
          id: 1,
          username: "admin",
          email: "admin@example.com",
          is_staff: true,
          features: fullFeatures,
        },
      });
    }

    if (req.path === "/api/auth/ws-token/" && req.method === "GET") {
      return json({ token: "mock-terminal-token" });
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
            status: "online",
            group_id: 11,
            group_name: "Core",
            is_shared: false,
            can_edit: true,
            share_context_enabled: true,
            shared_by_username: "",
            terminal_path: "/servers/1/terminal",
            minimal_terminal_path: "/servers/1/terminal/minimal",
            last_connected: null,
          },
          {
            id: 2,
            name: "DB-01",
            host: "10.0.0.21",
            port: 22,
            username: "postgres",
            server_type: "ssh",
            status: "online",
            group_id: 11,
            group_name: "Core",
            is_shared: false,
            can_edit: true,
            share_context_enabled: true,
            shared_by_username: "",
            terminal_path: "/servers/2/terminal",
            minimal_terminal_path: "/servers/2/terminal/minimal",
            last_connected: null,
          },
        ],
        groups: [{ id: 11, name: "Core", server_count: 2 }],
        stats: { owned: 2, shared: 0, total: 2 },
        recent_activity: [],
      });
    }

    if (req.path === "/servers/api/1/files/" && req.method === "GET") {
      return json({
        success: true,
        path: "/home/root",
        home_path: "/home/root",
        parent_path: "/home",
        entries: [
          {
            path: "/home/root/app.conf",
            name: "app.conf",
            kind: "file",
            is_dir: false,
            is_symlink: false,
            size: 128,
            permissions: "0644",
            modified_at: 1772326800,
          },
          {
            path: "/home/root/logs",
            name: "logs",
            kind: "dir",
            is_dir: true,
            is_symlink: false,
            size: 0,
            permissions: "0755",
            modified_at: 1772326800,
          },
        ],
      });
    }

    if (req.path === "/servers/api/1/files/write/" && req.method === "POST") {
      const body = (req.body || {}) as { path?: string; content?: string };
      const path = body.path || "/home/root/new-file.conf";
      return json({
        success: true,
        path: "/home/root",
        file: {
          path,
          filename: path.split("/").pop() || "new-file.conf",
          encoding: "utf-8",
          content: body.content || "",
          size: (body.content || "").length,
        },
      });
    }
  };
}

async function getSocketState(page: Page) {
  return page.evaluate(() => (window as any).__terminalWsMock.getState());
}

test("keeps multiple terminal tabs connected while switching between servers", async ({ page }) => {
  await installTerminalSocketMock(page);
  await installApiHarness(page, makeTerminalHandler(), "ru");

  await page.goto("/servers/1/terminal");

  await expect.poll(async () => {
    const state = await getSocketState(page);
    return state.length;
  }).toBe(1);

  await expect.poll(async () => {
    const state = await getSocketState(page);
    const messageTypes = state[0]?.sent.map((raw: string) => JSON.parse(raw).type) || [];
    return messageTypes.includes("connect");
  }).toBeTruthy();

  await page.getByRole("button", { name: "Подключить сервер" }).click();
  await page.getByRole("button", { name: "DB-01" }).click();

  await expect.poll(async () => {
    const state = await getSocketState(page);
    return state.length;
  }).toBe(2);

  await page.locator("button").filter({ hasText: "Web-01" }).first().click();
  await page.locator("button").filter({ hasText: "DB-01" }).first().click();
  await page.waitForTimeout(200);

  const state = await getSocketState(page);
  expect(state).toHaveLength(2);
  expect(state[0].readyState).toBe(1);
  expect(state[1].readyState).toBe(1);
  expect(state[0].sent.map((raw: string) => JSON.parse(raw).type)).not.toContain("disconnect");
  expect(state[1].sent.map((raw: string) => JSON.parse(raw).type)).not.toContain("disconnect");
});

test("reconnects terminal websocket after server-side connection loss", async ({ page }) => {
  await installTerminalSocketMock(page);
  await installApiHarness(page, makeTerminalHandler(), "ru");

  await page.goto("/servers/1/terminal");

  await expect.poll(async () => {
    const state = await getSocketState(page);
    return state.length;
  }).toBe(1);

  await page.evaluate(() => {
    (window as any).__terminalWsMock.closeFromServer(0, 1006, "Connection lost");
  });

  await expect.poll(async () => {
    const state = await getSocketState(page);
    return state.length;
  }, { timeout: 5_000 }).toBe(2);

  const state = await getSocketState(page);
  expect(state[0].readyState).toBe(3);
  expect(state[1].readyState).toBe(1);
  expect(state[1].sent.map((raw: string) => JSON.parse(raw).type)).toContain("connect");
});

test("uses custom terminal and SFTP dialogs instead of browser prompts", async ({ page }) => {
  await installTerminalSocketMock(page);
  const harness = await installApiHarness(page, makeTerminalHandler(), "ru");

  await page.goto("/servers/1/terminal");

  await page.getByRole("button", { name: "Подключить сервер" }).click();
  await page.getByRole("button", { name: "DB-01" }).click();

  await page.getByLabel("Закрыть вкладку DB-01").click();
  await expect(page.getByRole("alertdialog", { name: "Закрыть терминальную сессию?" })).toBeVisible();
  await page.getByRole("button", { name: "Отмена" }).click();
  await expect(page.getByRole("button", { name: "DB-01", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Web-01", exact: true }).click();
  await page.getByRole("button", { name: "Файлы" }).click();
  await expect(page.getByText("Файлы SFTP").first()).toBeVisible();

  await page.getByRole("button", { name: "Новый файл" }).click();
  await expect(page.getByRole("dialog", { name: "Новый файл" })).toBeVisible();
  await page.getByLabel("Имя файла").fill("deploy.env");
  await page.getByRole("button", { name: "Создать файл" }).click();

  await expect.poll(() => harness.getCalls("/servers/api/1/files/write/", "POST").length).toBe(1);
});
