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

const FIXED_DATE = "2026-03-01T08:00:00.000Z";

async function installPipelineRunSocketMock(page: Page) {
  await page.addInitScript(() => {
    const sockets: any[] = [];
    const pipelineSockets = () =>
      sockets.filter((socket) => String(socket.url || "").includes("/ws/studio/pipeline-runs/"));

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
    }

    Object.defineProperty(window, "__pipelineRunWsMock", {
      configurable: true,
      value: {
        getState: () =>
          pipelineSockets().map((socket, index) => ({
            index,
            url: socket.url,
            readyState: socket.readyState,
            sent: [...socket.sent],
          })),
        sendNodeEvent: (index: number, payload: Record<string, unknown>) => {
          pipelineSockets()[index]?.__serverMessage({ type: "node_event", ...payload });
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

function makePipelineLiveHandler() {
  const run = {
    id: 9001,
    pipeline_id: 101,
    pipeline_name: "Nightly Patch",
    status: "running",
    node_states: {
      "agent-1": {
        status: "running",
        output: "",
        error: "",
        started_at: FIXED_DATE,
        finished_at: null,
      },
    },
    nodes_snapshot: [
      {
        id: "agent-1",
        type: "agent/task",
        position: { x: 100, y: 120 },
        data: { label: "Audit Node" },
      },
    ],
    context: {},
    summary: "",
    error: "",
    duration_seconds: null,
    started_at: FIXED_DATE,
    finished_at: null,
    created_at: FIXED_DATE,
    triggered_by: "admin",
  };

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

    if (req.path === "/api/studio/runs/" && req.method === "GET") {
      return json([run]);
    }

    if (req.path === "/api/studio/pipelines/" && req.method === "GET") {
      return json([
        {
          id: 101,
          name: "Nightly Patch",
          description: "Patch workflow",
          icon: "⚡",
          tags: ["ops"],
          is_shared: false,
          is_template: false,
          node_count: 1,
          created_at: FIXED_DATE,
          updated_at: FIXED_DATE,
          last_run: null,
        },
      ]);
    }

    if (req.path === "/api/studio/runs/9001/" && req.method === "GET") {
      return json(run);
    }

    if (req.path === "/api/studio/runs/9001/stop/" && req.method === "POST") {
      run.status = "stopped";
      run.finished_at = FIXED_DATE;
      return json({ ok: true });
    }
  };
}

async function getPipelineSocketState(page: Page) {
  return page.evaluate(() => (window as any).__pipelineRunWsMock.getState());
}

test("renders live pipeline node events from websocket updates", async ({ page }) => {
  await installPipelineRunSocketMock(page);
  await installApiHarness(page, makePipelineLiveHandler());

  await page.goto("/studio/runs");
  await expect(page.getByRole("heading", { name: "История запусков" })).toBeVisible();
  await expect(page.getByText("Run #9001").last()).toBeVisible();

  await expect.poll(async () => {
    const state = await getPipelineSocketState(page);
    return state.length;
  }).toBe(1);

  await page.evaluate(() => {
    (window as any).__pipelineRunWsMock.sendNodeEvent(0, {
      node_id: "agent-1",
      event_type: "agent_thought",
      data: { thought: "Collecting diagnostics before rollout" },
    });
  });

  await expect(page.getByText("Collecting diagnostics before rollout")).toBeVisible();
});
