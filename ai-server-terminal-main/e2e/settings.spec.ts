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

function makeSettingsHandler() {
  let nextUserId = 3;
  let nextGroupId = 3;
  let nextPermId = 2;

  const settingsConfig: any = {
    default_provider: "grok",
    internal_llm_provider: "grok",
    gemini_enabled: true,
    grok_enabled: true,
    openai_enabled: true,
    claude_enabled: true,
    gemini_set: true,
    grok_set: true,
    openai_set: true,
    claude_set: true,
    chat_llm_provider: "grok",
    chat_llm_model: "grok-3-mini",
    agent_llm_provider: "grok",
    agent_llm_model: "grok-3",
    orchestrator_llm_provider: "openai",
    orchestrator_llm_model: "gpt-5.2",
    chat_model_gemini: "gemini-2.5-pro",
    chat_model_grok: "grok-3-mini",
    chat_model_openai: "gpt-5.2",
    chat_model_claude: "claude-4.5-sonnet",
    openai_reasoning_effort: "medium",
    domain_auth_enabled: true,
    domain_auth_header: "REMOTE_USER",
    domain_auth_auto_create: true,
  };

  const monitoringConfig: any = {
    thresholds: {
      cpu_warn: 70,
      cpu_crit: 90,
      mem_warn: 75,
      mem_crit: 92,
      disk_warn: 80,
      disk_crit: 95,
    },
    stats: {
      monitored_servers: 2,
      total_checks: 100,
      active_alerts: 1,
      last_check_at: new Date().toISOString(),
    },
  };

  const groups: any[] = [
    { id: 1, name: "Operations", members: [], member_count: 0 },
    { id: 2, name: "Security", members: [], member_count: 0 },
  ];

  const users: any[] = [
    {
      id: 1,
      username: "admin",
      email: "admin@example.com",
      is_staff: true,
      is_active: true,
      is_superuser: true,
      access_profile: "admin_full",
      groups: [{ id: 1, name: "Operations" }],
    },
    {
      id: 2,
      username: "operator",
      email: "operator@example.com",
      is_staff: false,
      is_active: true,
      access_profile: "server_only",
      groups: [{ id: 1, name: "Operations" }],
    },
  ];

  const permissions: any[] = [
    {
      id: 1,
      user_id: 2,
      username: "operator",
      feature: "settings",
      feature_display: "Settings",
      allowed: false,
    },
  ];

  function syncGroups() {
    for (const group of groups) {
      group.members = [];
      group.member_count = 0;
    }
    for (const user of users) {
      user.groups = (user.groups || [])
        .map((group: any) => groups.find((item) => item.id === group.id))
        .filter(Boolean)
        .map((group: any) => ({ id: group.id, name: group.name }));
      for (const group of user.groups) {
        const target = groups.find((item) => item.id === group.id);
        if (target) {
          target.members.push({ id: user.id, username: user.username });
          target.member_count = target.members.length;
        }
      }
    }
  }

  syncGroups();

  return (req: any) => {
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

    if (req.path === "/api/settings/" && req.method === "GET") return json({ success: true, config: settingsConfig });
    if (req.path === "/api/settings/" && req.method === "POST") {
      Object.assign(settingsConfig, req.body || {});
      return json({ success: true, message: "saved" });
    }

    if (req.path === "/api/models/" && req.method === "GET") {
      return json({
        gemini: ["gemini-2.5-pro"],
        grok: ["grok-3-mini", "grok-3"],
        openai: ["gpt-5.2"],
        claude: ["claude-4.5-sonnet"],
        current: {
          default_provider: "grok",
          chat_gemini: "gemini-2.5-pro",
          chat_grok: "grok-3-mini",
          chat_openai: "gpt-5.2",
          chat_claude: "claude-4.5-sonnet",
        },
      });
    }

    if (req.path === "/api/models/refresh/" && req.method === "POST") {
      return json({ success: true, provider: String(req.body?.provider || "grok"), models: ["mock-model"], count: 1 });
    }

    if (req.path === "/api/settings/activity/" && req.method === "GET") {
      return json({ success: true, events: [], summary: { total_events: 0, total_users: 0 } });
    }

    if (req.path === "/servers/api/monitoring/config/" && req.method === "GET") return json(monitoringConfig);
    if (req.path === "/servers/api/monitoring/config/" && req.method === "POST") {
      monitoringConfig.thresholds = { ...monitoringConfig.thresholds, ...(req.body?.thresholds || {}) };
      return json({ success: true });
    }

    if (req.path === "/api/access/users/" && req.method === "GET") {
      syncGroups();
      return json({ users });
    }

    if (req.path === "/api/access/users/" && req.method === "POST") {
      const groupIds = Array.isArray(req.body?.groups) ? req.body.groups.map((id: unknown) => Number(id)).filter(Number.isFinite) : [];
      const created = {
        id: nextUserId++,
        username: String(req.body?.username || "new-user"),
        email: String(req.body?.email || ""),
        is_staff: Boolean(req.body?.is_staff),
        is_active: req.body?.is_active !== false,
        access_profile: String(req.body?.access_profile || "server_only"),
        groups: groups.filter((group) => groupIds.includes(group.id)).map((group) => ({ id: group.id, name: group.name })),
      };
      users.push(created);
      syncGroups();
      return json({ success: true, user: created });
    }

    if (req.path.match(/^\/api\/access\/users\/\d+\/$/) && req.method === "PUT") {
      const id = Number(req.path.split("/")[4]);
      const target = users.find((user) => user.id === id);
      if (target) {
        target.username = String(req.body?.username ?? target.username);
        target.email = String(req.body?.email ?? target.email);
        target.is_staff = req.body?.is_staff ?? target.is_staff;
        target.is_active = req.body?.is_active ?? target.is_active;
        target.access_profile = String(req.body?.access_profile ?? target.access_profile);
        if (Array.isArray(req.body?.groups)) {
          const ids = req.body.groups.map((groupId: unknown) => Number(groupId)).filter(Number.isFinite);
          target.groups = groups.filter((group) => ids.includes(group.id)).map((group) => ({ id: group.id, name: group.name }));
        }
      }
      syncGroups();
      return json({ success: true, user: target });
    }

    if (req.path.match(/^\/api\/access\/users\/\d+\/$/) && req.method === "DELETE") {
      const id = Number(req.path.split("/")[4]);
      const idx = users.findIndex((user) => user.id === id);
      if (idx >= 0) users.splice(idx, 1);
      syncGroups();
      return json({ success: true, message: "deleted" });
    }

    if (req.path.match(/^\/api\/access\/users\/\d+\/password\/$/) && req.method === "POST") {
      return json({ success: true, message: "password updated" });
    }

    if (req.path === "/api/access/groups/" && req.method === "GET") {
      syncGroups();
      return json({ groups });
    }

    if (req.path === "/api/access/groups/" && req.method === "POST") {
      const created = {
        id: nextGroupId++,
        name: String(req.body?.name || "New Group"),
        members: [],
        member_count: 0,
      };
      groups.push(created);
      if (Array.isArray(req.body?.members)) {
        for (const memberId of req.body.members) {
          const target = users.find((user) => user.id === Number(memberId));
          if (target && !target.groups.some((group: any) => group.id === created.id)) {
            target.groups.push({ id: created.id, name: created.name });
          }
        }
      }
      syncGroups();
      return json({ success: true, group: created });
    }

    if (req.path.match(/^\/api\/access\/groups\/\d+\/$/) && req.method === "PUT") {
      const id = Number(req.path.split("/")[4]);
      const target = groups.find((group) => group.id === id);
      if (target) target.name = String(req.body?.name || target.name);
      for (const user of users) {
        user.groups = (user.groups || []).map((group: any) => (group.id === id ? { ...group, name: target?.name || group.name } : group));
      }
      syncGroups();
      return json({ success: true, group: target });
    }

    if (req.path.match(/^\/api\/access\/groups\/\d+\/$/) && req.method === "DELETE") {
      const id = Number(req.path.split("/")[4]);
      const idx = groups.findIndex((group) => group.id === id);
      if (idx >= 0) groups.splice(idx, 1);
      for (const user of users) {
        user.groups = (user.groups || []).filter((group: any) => group.id !== id);
      }
      syncGroups();
      return json({ success: true, message: "deleted" });
    }

    if (req.path === "/api/access/permissions/" && req.method === "GET") {
      return json({
        permissions,
        features: [
          { value: "servers", label: "Servers" },
          { value: "settings", label: "Settings" },
          { value: "orchestrator", label: "Orchestrator" },
        ],
      });
    }

    if (req.path === "/api/access/permissions/" && req.method === "POST") {
      let target = permissions.find((perm) => perm.user_id === Number(req.body?.user_id) && perm.feature === String(req.body?.feature));
      if (!target) {
        target = {
          id: nextPermId++,
          user_id: Number(req.body?.user_id),
          username: users.find((user) => user.id === Number(req.body?.user_id))?.username || "user",
          feature: String(req.body?.feature || "servers"),
          feature_display: String(req.body?.feature || "servers"),
          allowed: Boolean(req.body?.allowed),
        };
        permissions.push(target);
      } else {
        target.allowed = Boolean(req.body?.allowed);
      }
      return json({ success: true, permission: target });
    }

    if (req.path.match(/^\/api\/access\/permissions\/\d+\/$/) && req.method === "PUT") {
      const id = Number(req.path.split("/")[4]);
      const target = permissions.find((perm) => perm.id === id);
      if (target) target.allowed = Boolean(req.body?.allowed);
      return json({ success: true, permission: target });
    }

    if (req.path.match(/^\/api\/access\/permissions\/\d+\/$/) && req.method === "DELETE") {
      const id = Number(req.path.split("/")[4]);
      const idx = permissions.findIndex((perm) => perm.id === id);
      if (idx >= 0) permissions.splice(idx, 1);
      return json({ success: true, message: "deleted" });
    }
  };
}

test("updates AI settings from the settings workspace", async ({ page }) => {
  const harness = await installApiHarness(page, makeSettingsHandler());

  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible();

  await page.getByRole("button", { name: "Сохранить" }).first().click();
  await expect
    .poll(() => harness.getCalls("/api/settings/", "POST").length)
    .toBeGreaterThan(0);

  await page.getByRole("button", { name: "Обновить список" }).first().click();
  await expect
    .poll(() => harness.getCalls("/api/models/refresh/", "POST").length)
    .toBeGreaterThan(0);
});

test("manages users from access catalog", async ({ page }) => {
  const harness = await installApiHarness(page, makeSettingsHandler());

  await page.goto("/settings/users");
  await expect(page.getByRole("heading", { name: "Users" })).toBeVisible();

  await page.getByPlaceholder("Username").fill("qa-user");
  await page.getByPlaceholder("Email").fill("qa@example.com");
  await page.getByPlaceholder("Password").fill("Temp1234");
  await page.getByRole("button", { name: "Create User" }).click();
  await expect(page.getByText("qa-user")).toBeVisible();

  await page.evaluate(() => {
    window.prompt = () => "NewPass123!";
    window.confirm = () => true;
    window.alert = () => undefined;
  });

  await page.getByRole("button", { name: "Password" }).last().click();
  await expect
    .poll(() => harness.getCalls("/api/access/users/3/password/", "POST").length)
    .toBeGreaterThan(0);

  await page.getByRole("button", { name: "Delete" }).last().click();
  await expect
    .poll(() => harness.getCalls("/api/access/users/3/", "DELETE").length)
    .toBeGreaterThan(0);
  await expect(page.getByText("qa-user")).toHaveCount(0);
});

test("manages groups and explicit permissions", async ({ page }) => {
  const harness = await installApiHarness(page, makeSettingsHandler());

  await page.goto("/settings/groups");
  await expect(page.getByRole("heading", { name: "Groups" })).toBeVisible();

  await page.getByPlaceholder("Group name").fill("SRE Team");
  await page.getByRole("button", { name: "Create Group" }).click();
  await expect(page.getByText("SRE Team")).toBeVisible();

  await page.getByRole("button", { name: "Edit Group" }).last().click();
  await page.locator("input").last().fill("SRE Core");
  await page.getByRole("button", { name: "Save" }).last().click();
  await expect
    .poll(() => harness.getCalls("/api/access/groups/3/", "PUT").length)
    .toBeGreaterThan(0);
  await expect(page.getByText("SRE Core")).toBeVisible();

  await page.goto("/settings/permissions");
  await expect(page.getByRole("heading", { name: "Permissions", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Save" }).first().click();
  await expect
    .poll(() => harness.getCalls("/api/access/permissions/", "POST").length)
    .toBeGreaterThan(0);

  await page.getByRole("button", { name: "Toggle" }).first().click();
  page.once("dialog", async (dialog) => {
    await dialog.accept();
  });
  await page.getByRole("button", { name: "Delete" }).first().click();
});
