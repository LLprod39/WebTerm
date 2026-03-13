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

function makeStudioHandler() {
  let nextPipelineId = 102;
  let nextSkillSlug = 1;
  let nextMcpId = 502;

  const pipelines: any[] = [
    {
      id: 101,
      name: "Nightly Patch",
      description: "Patch workflow",
      icon: "⚡",
      tags: ["ops"],
      is_shared: false,
      is_template: false,
      node_count: 3,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
      last_run: null,
      nodes: [],
      edges: [],
    },
  ];

  const templates = [
    {
      slug: "starter-ops",
      name: "Ops Starter",
      description: "Starter template",
      icon: "🧩",
      category: "operations",
    },
  ];

  const skills: any[] = [
    {
      slug: "incident-triage",
      name: "Incident Triage",
      description: "Diagnostics playbook",
      tags: ["incident"],
      service: "platform",
      category: "operations",
      safety_level: "standard",
      ui_hint: "Use during incidents",
      guardrail_summary: ["Run preflight"],
      recommended_tools: ["report"],
      runtime_enforced: true,
      path: "studio/skills/incident-triage/SKILL.md",
    },
  ];

  const skillDetails: Record<string, any> = {
    "incident-triage": {
      ...skills[0],
      runtime_policy: { allow: [".*"], block: [], pinned_arguments: {} },
      metadata: {},
      content: "# Incident Triage\n\n- Verify scope\n- Gather logs",
    },
  };

  const mcpServers: any[] = [
    {
      id: 501,
      name: "GitHub MCP",
      description: "Repository tools",
      transport: "stdio",
      command: "npx",
      args: ["-y", "@modelcontextprotocol/server-github"],
      env: {},
      url: "",
      is_shared: false,
      last_test_ok: true,
      last_test_at: new Date().toISOString(),
      last_test_error: "",
    },
  ];

  const mcpTemplates = [
    {
      slug: "github",
      name: "GitHub",
      description: "GitHub template",
      transport: "stdio",
      command: "npx",
      args: ["-y", "@modelcontextprotocol/server-github"],
      env: {},
      icon: "🐙",
    },
  ];

  const notifications = {
    telegram_bot_token: "",
    telegram_chat_id: "",
    notify_email: "ops@example.com",
    smtp_host: "",
    smtp_port: "587",
    smtp_user: "",
    smtp_password: "",
    from_email: "",
    site_url: "http://127.0.0.1:9000",
  };

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

    if (req.path === "/api/studio/pipelines/" && req.method === "GET") {
      const q = (req.query.q || "").trim().toLowerCase();
      const filtered = pipelines.filter((pipeline) => {
        if (!q) return true;
        return [pipeline.name, pipeline.description, ...(pipeline.tags || [])].join(" ").toLowerCase().includes(q);
      });
      return json(filtered);
    }

    if (req.path === "/api/studio/runs/" && req.method === "GET") {
      return json([]);
    }

    if (req.path.match(/^\/api\/studio\/pipelines\/\d+\/run\/$/) && req.method === "POST") {
      return json({
        id: Date.now(),
        pipeline_id: Number(req.path.split("/")[4]),
        pipeline_name: "Run",
        status: "running",
        node_states: {},
        nodes_snapshot: [],
        context: {},
        summary: "started",
        error: "",
        duration_seconds: null,
        started_at: new Date().toISOString(),
        finished_at: null,
        created_at: new Date().toISOString(),
        triggered_by: "admin",
      });
    }

    if (req.path.match(/^\/api\/studio\/pipelines\/\d+\/clone\/$/) && req.method === "POST") {
      const sourceId = Number(req.path.split("/")[4]);
      const source = pipelines.find((pipeline) => pipeline.id === sourceId);
      const clone = {
        ...(source || pipelines[0]),
        id: nextPipelineId++,
        name: `${source?.name || "Pipeline"} Copy`,
        last_run: null,
        updated_at: new Date().toISOString(),
      };
      pipelines.push(clone);
      return json(clone);
    }

    if (req.path.match(/^\/api\/studio\/pipelines\/\d+\/$/) && req.method === "DELETE") {
      const id = Number(req.path.split("/")[4]);
      const idx = pipelines.findIndex((pipeline) => pipeline.id === id);
      if (idx >= 0) pipelines.splice(idx, 1);
      return json({ ok: true });
    }

    if (req.path === "/api/studio/templates/" && req.method === "GET") return json(templates);
    if (req.path.match(/^\/api\/studio\/templates\/[^/]+\/use\/$/) && req.method === "POST") {
      const created = {
        id: nextPipelineId++,
        name: "Template Instance",
        description: "Generated from template",
        icon: "⚡",
        tags: ["template"],
        is_shared: false,
        is_template: false,
        node_count: 1,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        last_run: null,
        nodes: [],
        edges: [],
      };
      pipelines.push(created);
      return json(created);
    }

    if (req.path === "/api/studio/notifications/" && req.method === "GET") return json(notifications);
    if (req.path === "/api/studio/notifications/" && req.method === "POST") {
      Object.assign(notifications, req.body || {});
      return json({ ok: true, saved: Object.keys(req.body || {}) });
    }
    if (req.path === "/api/studio/notifications/test-telegram/" && req.method === "POST") return json({ ok: true, message: "Telegram test sent" });
    if (req.path === "/api/studio/notifications/test-email/" && req.method === "POST") return json({ ok: true, message: "Email test sent" });

    if (req.path === "/api/studio/skills/" && req.method === "GET") return json(skills);
    if (req.path.match(/^\/api\/studio\/skills\/[^/]+\/$/) && req.method === "GET") {
      const slug = decodeURIComponent(req.path.split("/")[4]);
      return json(skillDetails[slug] || skillDetails["incident-triage"]);
    }
    if (req.path === "/api/studio/skills/templates/" && req.method === "GET") {
      return json([
        {
          slug: "service-ops",
          name: "Service Ops",
          description: "Template for service operations",
          summary: "Use for internal automation",
          defaults: {
            service: "platform",
            category: "operations",
            safety_level: "standard",
            runtime_policy: { allow: [".*"], block: [], pinned_arguments: {} },
          },
        },
      ]);
    }
    if (req.path === "/api/studio/skills/validate/" && req.method === "POST") {
      return json({
        results: skills.map((skill) => ({ slug: skill.slug, path: skill.path, errors: [], warnings: [], is_valid: true })),
        summary: {
          skills: skills.length,
          errors: 0,
          warnings: 0,
          is_valid: true,
          strict: Boolean(req.body?.strict),
        },
      });
    }
    if (req.path === "/api/studio/skills/scaffold/" && req.method === "POST") {
      const slug = String(req.body?.slug || `new-skill-${nextSkillSlug++}`);
      const created = {
        slug,
        name: String(req.body?.name || "New Skill"),
        description: String(req.body?.description || ""),
        tags: Array.isArray(req.body?.tags) ? req.body.tags : [],
        service: String(req.body?.service || "platform"),
        category: String(req.body?.category || "operations"),
        safety_level: String(req.body?.safety_level || "standard"),
        ui_hint: String(req.body?.ui_hint || ""),
        guardrail_summary: Array.isArray(req.body?.guardrail_summary) ? req.body.guardrail_summary : [],
        recommended_tools: Array.isArray(req.body?.recommended_tools) ? req.body.recommended_tools : [],
        runtime_enforced: true,
        path: `studio/skills/${slug}/SKILL.md`,
      };
      skills.push(created);
      skillDetails[slug] = {
        ...created,
        runtime_policy: req.body?.runtime_policy || {},
        metadata: {},
        content: `# ${created.name}`,
      };
      return json({
        ok: true,
        skill: skillDetails[slug],
        validation: { slug, path: skillDetails[slug].path, errors: [], warnings: [], is_valid: true },
      });
    }

    if (req.path === "/api/studio/mcp/" && req.method === "GET") return json(mcpServers);
    if (req.path === "/api/studio/mcp/" && req.method === "POST") {
      const created = {
        id: nextMcpId++,
        name: String(req.body?.name || "MCP"),
        description: String(req.body?.description || ""),
        transport: String(req.body?.transport || "stdio"),
        command: String(req.body?.command || ""),
        args: Array.isArray(req.body?.args) ? req.body.args : [],
        env: req.body?.env || {},
        url: String(req.body?.url || ""),
        is_shared: false,
        last_test_ok: null,
        last_test_at: null,
        last_test_error: "",
      };
      mcpServers.push(created);
      return json(created);
    }
    if (req.path.match(/^\/api\/studio\/mcp\/\d+\/test\/$/) && req.method === "POST") {
      const id = Number(req.path.split("/")[4]);
      const target = mcpServers.find((mcp) => mcp.id === id);
      if (target) {
        target.last_test_ok = true;
        target.last_test_at = new Date().toISOString();
      }
      return json({ ok: true, error: null });
    }
    if (req.path.match(/^\/api\/studio\/mcp\/\d+\/$/) && req.method === "DELETE") {
      const id = Number(req.path.split("/")[4]);
      const idx = mcpServers.findIndex((mcp) => mcp.id === id);
      if (idx >= 0) mcpServers.splice(idx, 1);
      return json({ ok: true });
    }
    if (req.path === "/api/studio/mcp/templates/" && req.method === "GET") return json(mcpTemplates);

    if (req.path === "/api/studio/servers/" && req.method === "GET") return json([{ id: 1, name: "Web-01", host: "10.0.0.11" }]);
    if (req.path === "/api/studio/agents/" && req.method === "GET") return json([]);
  };
}

test("works with pipeline actions from Studio", async ({ page }) => {
  const handler = makeStudioHandler();
  const harness = await installApiHarness(page, handler);

  await page.goto("/studio");
  await expect(page.getByRole("heading", { name: "Pipeline Workspace" })).toBeVisible();

  await page.getByRole("button", { name: /^Run$/ }).first().click();
  expect(harness.getCalls("/api/studio/pipelines/101/run/", "POST").length).toBeGreaterThan(0);

  const pipelineCard = page.locator("article").filter({ hasText: "Nightly Patch" }).first();
  await pipelineCard.locator("button").first().click();
  await page.getByRole("menuitem", { name: /Clone/ }).click();
  await expect(page.getByRole("heading", { name: "Nightly Patch Copy" })).toBeVisible();

  const cloneCard = page.locator("article").filter({ hasText: "Nightly Patch Copy" }).first();
  await cloneCard.locator("button").first().click();
  await page.getByRole("menuitem", { name: /Delete/ }).click();
  await page.getByRole("button", { name: /^Delete$/ }).click();
  await expect(page.getByText("Nightly Patch Copy")).toHaveCount(0);
});

test("manages MCP registry and notification test actions", async ({ page }) => {
  const harness = await installApiHarness(page, makeStudioHandler());

  await page.goto("/studio/mcp");
  await expect(page.getByText("MCP Hub")).toBeVisible();

  await page.getByRole("button", { name: "Add server" }).first().click();
  await page.getByPlaceholder("GitHub MCP").fill("PagerDuty MCP");
  await page.getByPlaceholder("What this MCP provides").fill("Incident escalation tools");
  await page.getByPlaceholder("npx").fill("npx");
  await page.getByRole("button", { name: /^Save$/ }).click();
  await expect(page.getByText("PagerDuty MCP")).toBeVisible();
  expect(harness.getCalls("/api/studio/mcp/", "POST").length).toBeGreaterThan(0);

  await page.goto("/studio/notifications");
  await expect(page.getByText("Notification settings")).toBeVisible();

  await page.locator('input[type="password"]').first().fill("tg-token");
  await page.locator('input[placeholder="123456789"]').fill("123456789");
  await page.getByRole("button", { name: "Send test Telegram message" }).click();
  await expect(page.getByText("Telegram test sent")).toBeVisible();

  await page.getByPlaceholder("smtp.gmail.com").fill("smtp.gmail.com");
  await page.getByPlaceholder("email@example.com", { exact: true }).fill("smtp-user");
  await page.getByRole("button", { name: "Send test email" }).click();
  await expect(page.getByText("Email test sent")).toBeVisible();

  await page.getByRole("button", { name: /^Save$/ }).click();
});
