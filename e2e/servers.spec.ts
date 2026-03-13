import { expect, test } from "@playwright/test";
import { installApiHarness, json } from "./support/apiHarness";

const fullFeatures = {
  servers: true,
  dashboard: true,
  agents: true,
  studio: true,
  settings: true,
  orchestrator: true,
};

type ServerItem = {
  id: number;
  name: string;
  host: string;
  port: number;
  username: string;
  server_type: "ssh" | "rdp";
  rdp: boolean;
  status: "online" | "offline" | "unknown";
  group_id: number | null;
  group_name: string;
  is_shared: boolean;
  can_edit: boolean;
  share_context_enabled: boolean;
  shared_by_username: string;
  terminal_path: string;
  minimal_terminal_path: string;
  last_connected: string | null;
};

function makeServersHandler() {
  let nextServerId = 2;
  let nextGroupId = 12;
  let nextShareId = 101;
  let nextKnowledgeId = 201;
  let masterSet = false;

  const groups = [{ id: 11, name: "Core" }];
  const servers: ServerItem[] = [
    {
      id: 1,
      name: "Web-01",
      host: "10.0.0.11",
      port: 22,
      username: "root",
      server_type: "ssh",
      rdp: false,
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
  ];

  const serverDetails: Record<number, any> = {
    1: {
      id: 1,
      name: "Web-01",
      host: "10.0.0.11",
      port: 22,
      username: "root",
      server_type: "ssh",
      auth_method: "password",
      key_path: "",
      tags: "web",
      notes: "",
      group_id: 11,
      is_active: true,
    },
  };

  const shares: Record<number, any[]> = { 1: [] };
  const knowledge: Record<number, any[]> = {
    1: [
      {
        id: 200,
        title: "Baseline",
        content: "Current baseline notes",
        category: "other",
        category_label: "other",
        source: "manual",
        source_label: "Manual",
        confidence: 0.8,
        is_active: true,
        updated_at: new Date().toISOString(),
      },
    ],
  };

  const globalContext = {
    rules: "Always verify before restart",
    forbidden_commands: ["rm -rf /"],
    required_checks: ["uptime"],
    environment_vars: { ENV: "staging" },
  };

  const groupContexts: Record<number, any> = {
    11: {
      id: 11,
      name: "Core",
      rules: "Core services rules",
      forbidden_commands: ["shutdown now"],
      environment_vars: { TEAM: "core" },
    },
  };

  const getBootstrap = () => ({
    success: true,
    servers,
    groups: groups.map((group) => ({
      id: group.id,
      name: group.name,
      server_count: servers.filter((server) => server.group_id === group.id).length,
    })),
    stats: { owned: servers.length, shared: 0, total: servers.length },
    recent_activity: [],
  });

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

    if (req.path === "/servers/api/frontend/bootstrap/" && req.method === "GET") return json(getBootstrap());

    if (req.path === "/servers/api/create/" && req.method === "POST") {
      const id = nextServerId++;
      const groupId = req.body?.group_id ?? null;
      const group = groups.find((item) => item.id === Number(groupId));
      const created: ServerItem = {
        id,
        name: String(req.body?.name || `Server ${id}`),
        host: String(req.body?.host || `10.0.0.${id}`),
        port: Number(req.body?.port || 22),
        username: String(req.body?.username || "root"),
        server_type: "ssh",
        rdp: false,
        status: "unknown",
        group_id: group ? group.id : null,
        group_name: group?.name || "Ungrouped",
        is_shared: false,
        can_edit: true,
        share_context_enabled: false,
        shared_by_username: "",
        terminal_path: `/servers/${id}/terminal`,
        minimal_terminal_path: `/servers/${id}/terminal/minimal`,
        last_connected: null,
      };
      servers.push(created);
      serverDetails[id] = {
        ...created,
        auth_method: req.body?.auth_method || "password",
        key_path: req.body?.key_path || "",
        tags: req.body?.tags || "",
        notes: req.body?.notes || "",
        is_active: req.body?.is_active !== false,
      };
      shares[id] = [];
      knowledge[id] = [];
      return json({ success: true, server_id: id, message: "Created" });
    }

    if (req.path.match(/^\/servers\/api\/\d+\/get\/$/) && req.method === "GET") {
      const id = Number(req.path.split("/")[3]);
      return json(serverDetails[id]);
    }

    if (req.path.match(/^\/servers\/api\/\d+\/delete\/$/) && req.method === "POST") {
      const id = Number(req.path.split("/")[3]);
      const idx = servers.findIndex((item) => item.id === id);
      if (idx >= 0) servers.splice(idx, 1);
      delete serverDetails[id];
      return json({ success: true });
    }

    if (req.path === "/servers/api/groups/create/" && req.method === "POST") {
      const id = nextGroupId++;
      groups.push({ id, name: String(req.body?.name || `Group ${id}`) });
      groupContexts[id] = { id, name: String(req.body?.name || `Group ${id}`), rules: "", forbidden_commands: [], environment_vars: {} };
      return json({ success: true, group_id: id });
    }

    if (req.path.match(/^\/servers\/api\/groups\/\d+\/update\/$/) && req.method === "POST") {
      const id = Number(req.path.split("/")[4]);
      const target = groups.find((group) => group.id === id);
      if (target) target.name = String(req.body?.name || target.name);
      for (const server of servers) {
        if (server.group_id === id) server.group_name = target?.name || server.group_name;
      }
      if (groupContexts[id]) groupContexts[id].name = target?.name || groupContexts[id].name;
      return json({ success: true });
    }

    if (req.path.match(/^\/servers\/api\/groups\/\d+\/delete\/$/) && req.method === "POST") {
      const id = Number(req.path.split("/")[4]);
      const idx = groups.findIndex((group) => group.id === id);
      if (idx >= 0) groups.splice(idx, 1);
      for (const server of servers) {
        if (server.group_id === id) {
          server.group_id = null;
          server.group_name = "Ungrouped";
        }
      }
      return json({ success: true });
    }

    if (req.path === "/servers/api/bulk-update/" && req.method === "POST") {
      const ids: number[] = req.body?.server_ids || [];
      for (const id of ids) {
        const target = servers.find((server) => server.id === id);
        if (!target) continue;
        if (Object.prototype.hasOwnProperty.call(req.body || {}, "group_id")) {
          const groupId = req.body.group_id;
          const group = groups.find((item) => item.id === Number(groupId));
          target.group_id = group ? group.id : null;
          target.group_name = group?.name || "Ungrouped";
          if (serverDetails[id]) serverDetails[id].group_id = target.group_id;
        }
      }
      return json({ success: true, updated_count: ids.length });
    }

    if (req.path.match(/^\/servers\/api\/\d+\/shares\/$/) && req.method === "GET") {
      const id = Number(req.path.split("/")[3]);
      return json({ success: true, shares: shares[id] || [] });
    }

    if (req.path.match(/^\/servers\/api\/\d+\/share\/$/) && req.method === "POST") {
      const id = Number(req.path.split("/")[3]);
      const item = {
        id: nextShareId++,
        user_id: nextShareId,
        username: String(req.body?.user || "user"),
        email: `${String(req.body?.user || "user")}@example.com`,
        share_context: req.body?.share_context !== false,
        expires_at: req.body?.expires_at || null,
        created_at: new Date().toISOString(),
        is_active: true,
      };
      shares[id] = shares[id] || [];
      shares[id].push(item);
      return json({ success: true });
    }

    if (req.path.match(/^\/servers\/api\/\d+\/knowledge\/$/) && req.method === "GET") {
      const id = Number(req.path.split("/")[3]);
      return json({ success: true, items: knowledge[id] || [], categories: [{ value: "other", label: "Other" }] });
    }

    if (req.path.match(/^\/servers\/api\/\d+\/knowledge\/create\/$/) && req.method === "POST") {
      const id = Number(req.path.split("/")[3]);
      const item = {
        id: nextKnowledgeId++,
        title: String(req.body?.title || "Untitled"),
        content: String(req.body?.content || ""),
        category: String(req.body?.category || "other"),
        category_label: String(req.body?.category || "other"),
        source: "manual",
        source_label: "Manual",
        confidence: 0.7,
        is_active: req.body?.is_active !== false,
        updated_at: new Date().toISOString(),
      };
      knowledge[id] = knowledge[id] || [];
      knowledge[id].push(item);
      return json({ success: true, id: item.id });
    }

    if (req.path.match(/^\/servers\/api\/\d+\/knowledge\/\d+\/update\/$/) && req.method === "POST") {
      const [, , , serverIdRaw, , knowledgeIdRaw] = req.path.split("/");
      const serverId = Number(serverIdRaw);
      const knowledgeId = Number(knowledgeIdRaw);
      const item = (knowledge[serverId] || []).find((entry) => entry.id === knowledgeId);
      if (item) Object.assign(item, req.body || {});
      return json({ success: true });
    }

    if (req.path === "/servers/api/global-context/" && req.method === "GET") return json(globalContext);
    if (req.path === "/servers/api/global-context/save/" && req.method === "POST") {
      Object.assign(globalContext, req.body || {});
      return json({ success: true });
    }

    if (req.path.match(/^\/servers\/api\/groups\/\d+\/context\/$/) && req.method === "GET") {
      const id = Number(req.path.split("/")[4]);
      return json(groupContexts[id] || { id, name: `Group ${id}`, rules: "", forbidden_commands: [], environment_vars: {} });
    }

    if (req.path.match(/^\/servers\/api\/groups\/\d+\/context\/save\/$/) && req.method === "POST") {
      const id = Number(req.path.split("/")[4]);
      groupContexts[id] = { ...(groupContexts[id] || { id, name: `Group ${id}` }), ...(req.body || {}) };
      return json({ success: true });
    }

    if (req.path === "/servers/api/master-password/check/" && req.method === "GET") return json({ has_master_password: masterSet });
    if (req.path === "/servers/api/master-password/set/" && req.method === "POST") {
      masterSet = true;
      return json({ success: true });
    }
    if (req.path === "/servers/api/master-password/clear/" && req.method === "POST") {
      masterSet = false;
      return json({ success: true });
    }

    if (req.path.match(/^\/servers\/api\/\d+\/reveal-password\/$/) && req.method === "POST") {
      return json({ success: true, password: "revealed-password" });
    }

    if (req.path.match(/^\/servers\/api\/\d+\/execute\/$/) && req.method === "POST") {
      return json({ success: true, output: { stdout: `Executed: ${String(req.body?.command || "")}`, stderr: "", exit_code: 0 } });
    }

    if (req.path.match(/^\/servers\/api\/groups\/\d+\/(add-member|remove-member|subscribe)\/$/) && req.method === "POST") {
      return json({ success: true });
    }
  };
}

test("manages server catalog and groups", async ({ page }) => {
  const handler = makeServersHandler();
  const harness = await installApiHarness(page, handler);

  await page.goto("/servers");

  await page.getByRole("button", { name: /Add Server/i }).click();
  const createDialog = page.getByRole("dialog").filter({ hasText: "Create Server" });
  await createDialog.getByPlaceholder("e.g. prod-web-01").fill("Cache-01");
  await createDialog.getByPlaceholder("192.168.1.10").fill("10.0.0.33");
  await createDialog.getByPlaceholder("ubuntu").fill("cache");
  await page.getByRole("button", { name: /^Create$/ }).click();
  await expect(page.getByText("Cache-01")).toBeVisible();

  await page.getByRole("tab", { name: "Groups" }).click();
  await page.getByPlaceholder("Group name").fill("Edge Group");
  await page.getByPlaceholder("Description").fill("Edge nodes");
  await page.getByRole("button", { name: "Create Group" }).click();
  await expect(page.getByText("Edge Group")).toBeVisible();

  page.once("dialog", async (dialog) => {
    await dialog.accept("Edge Team");
  });
  await page.getByRole("button", { name: "Rename" }).last().click();
  await expect(page.getByText("Edge Team")).toBeVisible();

  await page.getByRole("button", { name: "Follow" }).last().click();
  expect(harness.getCalls("/servers/api/groups/12/subscribe/", "POST").length).toBeGreaterThan(0);
});

test("uses advanced server actions for sharing, knowledge, context, security and command run", async ({ page }) => {
  await installApiHarness(page, makeServersHandler());

  await page.goto("/servers");

  await page.locator("button:has(svg.lucide-sparkles)").first().click();
  const advancedDialog = page.getByRole("dialog");
  await expect(advancedDialog).toBeVisible();
  await expect(advancedDialog.getByText("Web-01")).toBeVisible();
  await expect(advancedDialog.getByText("10.0.0.11:22")).toBeVisible();
  await expect(advancedDialog.getByRole("button", { name: "Share" })).toBeVisible();

  await advancedDialog.locator("input").first().fill("alice");
  await advancedDialog.getByRole("button", { name: "Share" }).click();
  await expect(advancedDialog.getByText(/^alice$/)).toBeVisible();

  await advancedDialog.getByRole("button", { name: "Knowledge" }).click();
  await page.getByPlaceholder("Title").fill("Rotation note");
  await page.getByPlaceholder("Content").fill("Rotate secrets every 30 days");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("Rotation note")).toBeVisible();

  await advancedDialog.getByRole("button", { name: "Context" }).click();
  await page.getByRole("button", { name: "Save Global Context" }).click();

  await advancedDialog.getByRole("button", { name: "Security" }).click();
  await page.locator('input[type="password"]').first().fill("master-pass");
  await page.getByRole("button", { name: "Set Session MP" }).click();
  await page.getByRole("button", { name: "Reveal Server Password" }).click();
  await expect(page.locator('input[value="revealed-password"]')).toBeVisible();

  await advancedDialog.getByRole("button", { name: "Execute" }).click();
  await page.getByPlaceholder("hostname").fill("uname -a");
  await page.getByRole("button", { name: "Run" }).click();
  await expect(page.locator("textarea").filter({ hasText: "Executed: uname -a" })).toBeVisible();
});
