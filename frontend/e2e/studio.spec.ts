import { expect, test } from "@playwright/test";
import { installApiHarness, json } from "./support/apiHarness";

const fullFeatures = {
  servers: true,
  dashboard: true,
  agents: true,
  studio: true,
  studio_pipelines: true,
  studio_runs: true,
  studio_agents: true,
  studio_skills: true,
  studio_mcp: true,
  studio_notifications: true,
  settings: true,
  orchestrator: true,
};

function makeStudioHandler() {
  let nextPipelineId = 102;
  let nextSkillSlug = 1;
  let nextMcpId = 502;
  let nextAgentId = 301;

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
      graph_version: 2,
      trigger_summary: { active_total: 1, active_manual: 1, active_webhook: 0, active_schedule: 0, active_monitoring: 0, last_triggered_at: null },
      last_run: null,
      nodes: [
        { id: "manual_start", type: "trigger/manual", position: { x: 0, y: 0 }, data: { label: "Manual start", is_active: true } },
      ],
      edges: [],
      triggers: [],
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
      is_owner: true,
      can_edit: true,
      can_share: true,
      is_shared: false,
      shared_user_ids: [],
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

  const skillWorkspaceFiles: Record<string, Record<string, any>> = {
    "incident-triage": {
      "SKILL.md": {
        path: "SKILL.md",
        name: "SKILL.md",
        kind: "skill",
        language: "markdown",
        editable: true,
        content: "# Incident Triage\n\n- Verify scope\n- Gather logs",
      },
      "references/checklist.md": {
        path: "references/checklist.md",
        name: "checklist.md",
        kind: "reference",
        language: "markdown",
        editable: true,
        content: "# Checklist\n\n- Capture timeline",
      },
    },
  };

  const skillValidation = (slug: string) => ({
    slug,
    path: skillDetails[slug]?.path || `studio/skills/${slug}/SKILL.md`,
    errors: [],
    warnings: [],
    is_valid: true,
  });

  const workspaceFileSummary = (file: any) => ({
    path: file.path,
    name: file.name,
    kind: file.kind,
    language: file.language,
    editable: file.editable,
    size: file.content.length,
  });

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

  const agentConfigs: any[] = [];

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

    if (req.path.match(/^\/api\/studio\/pipelines\/\d+\/$/) && req.method === "GET") {
      const id = Number(req.path.split("/")[4]);
      return json(pipelines.find((pipeline) => pipeline.id === id) || pipelines[0]);
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
        trigger_id: null,
        entry_node_id: String(req.body?.entry_node_id || ""),
        trigger_type: "manual",
        trigger_name: "Manual start",
        trigger_node_id: String(req.body?.entry_node_id || ""),
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
    if (req.path.match(/^\/api\/studio\/skills\/[^/]+\/$/) && req.method === "GET") {
      const slug = decodeURIComponent(req.path.split("/")[4]);
      return json(skillDetails[slug] || skillDetails["incident-triage"]);
    }
    if (req.path.match(/^\/api\/studio\/skills\/[^/]+\/workspace\/$/) && req.method === "GET") {
      const slug = decodeURIComponent(req.path.split("/")[4]);
      const files = Object.values(skillWorkspaceFiles[slug] || {});
      return json({
        skill: skillDetails[slug] || skillDetails["incident-triage"],
        files: files.map(workspaceFileSummary),
        validation: skillValidation(slug),
      });
    }
    if (req.path.match(/^\/api\/studio\/skills\/[^/]+\/workspace\/file\/$/) && req.method === "GET") {
      const slug = decodeURIComponent(req.path.split("/")[4]);
      const path = req.query.path || "SKILL.md";
      const file = skillWorkspaceFiles[slug]?.[path] || skillWorkspaceFiles["incident-triage"]["SKILL.md"];
      return json({ ...workspaceFileSummary(file), content: file.content });
    }
    if (req.path.match(/^\/api\/studio\/skills\/[^/]+\/workspace\/file\/$/) && req.method === "PUT") {
      const slug = decodeURIComponent(req.path.split("/")[4]);
      const path = String((req.body as any)?.path || "SKILL.md");
      const content = String((req.body as any)?.content || "");
      const file = skillWorkspaceFiles[slug]?.[path];
      if (file) file.content = content;
      return json({
        ok: true,
        file: file ? { ...workspaceFileSummary(file), content: file.content } : undefined,
        validation: skillValidation(slug),
      });
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
      skillWorkspaceFiles[slug] = {
        "SKILL.md": {
          path: "SKILL.md",
          name: "SKILL.md",
          kind: "skill",
          language: "markdown",
          editable: true,
          content: `# ${created.name}`,
        },
      };
      return json({
        ok: true,
        skill: skillDetails[slug],
        validation: skillValidation(slug),
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
    if (req.path === "/api/studio/share-users/" && req.method === "GET") {
      return json([{ id: 2, username: "operator", email: "operator@example.com" }]);
    }
    if (req.path === "/api/studio/agents/" && req.method === "GET") return json(agentConfigs);
    if (req.path === "/api/studio/agents/" && req.method === "POST") {
      const created = {
        id: nextAgentId++,
        name: String(req.body?.name || "Execution profile"),
        description: String(req.body?.description || ""),
        icon: String(req.body?.icon || "B"),
        system_prompt: String(req.body?.system_prompt || ""),
        instructions: String(req.body?.instructions || ""),
        model: String(req.body?.model || "gpt-5.2"),
        max_iterations: Number(req.body?.max_iterations || 10),
        allowed_tools: Array.isArray(req.body?.allowed_tools) ? req.body.allowed_tools : ["ssh_execute", "report"],
        sudo_policy: String(req.body?.sudo_policy || "disabled"),
        skill_slugs: Array.isArray(req.body?.skill_slugs) ? req.body.skill_slugs : [],
        skills: [],
        mcp_servers: [],
        server_scope: [],
        owner_username: "admin",
        is_owner: true,
        can_edit: true,
        is_shared: Boolean(req.body?.is_shared),
        shared_user_ids: Array.isArray(req.body?.shared_user_ids) ? req.body.shared_user_ids : [],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      agentConfigs.push(created);
      return json(created);
    }
  };
}

test("works with pipeline actions from Studio", async ({ page }) => {
  const handler = makeStudioHandler();
  const harness = await installApiHarness(page, handler);

  await page.goto("/studio");
  await expect(page.getByRole("heading", { name: "Pipelines", exact: true })).toBeVisible();

  await page.getByRole("button", { name: /^Run$/ }).first().click();
  await expect.poll(() => harness.getCalls("/api/studio/pipelines/101/run/", "POST").length).toBe(1);

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

test("creates execution profile from Studio profiles", async ({ page }) => {
  const handler = makeStudioHandler();
  const harness = await installApiHarness(page, handler);

  await page.goto("/studio/agents");
  await expect(page.getByRole("heading", { name: "Execution Profiles" })).toBeVisible();

  await page.getByRole("button", { name: "New profile" }).first().click();
  const sheet = page.getByRole("dialog");
  await expect(sheet.getByRole("heading", { name: "New profile" })).toBeVisible();
  await expect(sheet.getByText("Risk summary")).toBeVisible();

  await sheet.getByPlaceholder("Ops triage profile").fill("Rollback guard");
  await expect(sheet.getByText("You have unsaved changes.")).toBeVisible();
  await sheet.getByRole("button", { name: "Tools" }).click();
  await expect(sheet.getByText("Allowed tools")).toBeVisible();
  await sheet.getByRole("button", { name: "Save profile" }).click();

  await expect.poll(() => harness.getCalls("/api/studio/agents/", "POST").length).toBe(1);
  await expect(page.getByText("Rollback guard")).toBeVisible();
});

test("guards unsaved skill workspace edits before switching files", async ({ page }) => {
  await installApiHarness(page, makeStudioHandler());

  await page.goto("/studio/skills");
  await expect(page.getByRole("heading", { name: "Skill Catalog" })).toBeVisible();

  await page.getByRole("button", { name: /Incident Triage/ }).click();
  await expect(page.getByRole("heading", { name: "Incident Triage" })).toBeVisible();
  await page.getByRole("tab", { name: "Workspace" }).click();

  const editor = page.locator("textarea").first();
  await expect(editor).toHaveValue(/Verify scope/);
  await editor.fill("# Incident Triage\n\n- Edited but not saved");
  await expect(page.getByText("unsaved")).toBeVisible();

  await page.getByRole("button", { name: /checklist\.md/ }).click();
  await expect(page.getByRole("alertdialog")).toContainText("Unsaved file changes");

  await page.getByRole("button", { name: "Stay" }).click();
  await expect(editor).toHaveValue(/Edited but not saved/);

  await page.getByRole("button", { name: /checklist\.md/ }).click();
  await page.getByRole("button", { name: "Discard and continue" }).click();
  await expect(editor).toHaveValue(/Capture timeline/);
});

test("manages MCP registry and notification test actions", async ({ page }) => {
  const harness = await installApiHarness(page, makeStudioHandler());

  await page.goto("/studio/mcp");
  await expect(page.getByRole("heading", { name: "MCP Registry" })).toBeVisible();

  await page.getByRole("button", { name: "Add server" }).first().click();
  await page.getByPlaceholder("For example, GitHub MCP").fill("PagerDuty MCP");
  await page.getByPlaceholder("What tools this server exposes").fill("Incident escalation tools");
  await page.getByPlaceholder("npx").fill("npx");
  await page.getByRole("button", { name: /^Save$/ }).click();
  await expect(page.getByText("PagerDuty MCP")).toBeVisible();
  await expect.poll(() => harness.getCalls("/api/studio/mcp/", "POST").length).toBe(1);

  await page.goto("/studio/notifications");
  await expect(page.getByRole("heading", { name: "Notification Settings" })).toBeVisible();

  await page.locator('input[type="password"]').first().fill("tg-token");
  await page.locator('input[placeholder="123456789"]').fill("123456789");
  await expect(page.getByText("You have unsaved changes")).toBeVisible();
  await page.getByRole("button", { name: "Send test Telegram message" }).click();
  await expect(page.getByText("Telegram test sent")).toBeVisible();
  await expect(page.getByText(/Tested/)).toBeVisible();

  await page.getByPlaceholder("smtp.gmail.com").fill("smtp.gmail.com");
  await page.getByPlaceholder("email@example.com", { exact: true }).fill("smtp-user");
  await page.getByRole("button", { name: "Send test email" }).click();
  await expect(page.getByText("Email test sent")).toBeVisible();

  await page.getByRole("button", { name: "Save settings" }).click();
  await expect(page.getByRole("button", { name: "Saved" })).toBeVisible();
});
