import { expect, test, type Page } from "@playwright/test";

import { collectSeriousAndCriticalViolations, expectViolationsWithinBudget } from "./support/a11y";
import { installApiHarness, type ApiHarness } from "./support/apiHarness";
import {
  automationYaml,
  createAutomationWorkspaceMocks,
  type AutomationMockOptions,
  type AutomationMockState,
  type AutomationRole,
} from "./support/automationWorkspaceMocks";

type FlowStyle = "flow" | "flow-dark";

interface BrowserProbe {
  errors: string[];
  harness: ApiHarness;
  state: AutomationMockState;
}

async function prepareAutomation(
  page: Page,
  options: AutomationMockOptions = {},
  style: FlowStyle = "flow-dark",
): Promise<BrowserProbe> {
  const errors: string[] = [];
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(`console: ${message.text()}`);
  });
  page.on("pageerror", (error) => errors.push(`page: ${error.message}`));
  await page.addInitScript(({ selectedStyle }) => {
    window.localStorage.setItem("webterm.ui-style.active", selectedStyle);
    window.localStorage.setItem("webterm.ui-style.by-user", JSON.stringify({ "id:7": selectedStyle, guest: selectedStyle }));
    window.confirm = () => true;
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: async () => undefined },
    });
  }, { selectedStyle: style });
  const mocks = createAutomationWorkspaceMocks(options);
  const harness = await installApiHarness(page, mocks.handler, "en");
  return { errors, harness, state: mocks.state };
}

async function expectNoBrowserErrors(probe: BrowserProbe) {
  await expect.poll(() => probe.errors, { message: probe.errors.join("\n") }).toEqual([]);
}

async function expectNoHorizontalOverflow(page: Page) {
  const geometry = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  expect(geometry.scrollWidth, JSON.stringify(geometry)).toBeLessThanOrEqual(geometry.clientWidth + 1);
}

test.describe("Ansible workspace", () => {
  test.describe.configure({ timeout: 90_000 });

  test("imports YAML through reviewed hash locking and opens a private workspace", async ({ page }) => {
    const probe = await prepareAutomation(page, { role: "owner", compatibilityReady: true });

    await page.goto("/automation");
    await expect(page.getByRole("heading", { name: "Ansible" })).toBeVisible({ timeout: 45_000 });
    await page.getByRole("button", { name: "Import", exact: true }).first().click();

    const dialog = page.getByRole("dialog", { name: "Connect Ansible project" });
    await expect(dialog.getByRole("tab", { name: "YAML", selected: true })).toBeVisible();
    await dialog.getByLabel("Choose Ansible YAML").setInputFiles({
      name: "site.yml",
      mimeType: "text/yaml",
      buffer: Buffer.from(automationYaml),
    });

    await expect(dialog.getByRole("region", { name: "YAML import preview" })).toContainText("Private project");
    await expect(dialog.getByText("Confirmation is locked to the reviewed SHA-256 snapshot.")).toBeVisible();
    const previewCall = probe.harness.getCalls("/servers/api/playbooks/import/", "POST")[0];
    expect(previewCall.body).toMatchObject({ content: automationYaml, filename: "site.yml", save: false });
    const importViolations = await collectSeriousAndCriticalViolations(page, "[role=\"dialog\"]");
    expectViolationsWithinBudget(importViolations, {});

    await dialog.getByRole("button", { name: "Add private project" }).click();
    await expect(dialog.getByText("Project added")).toBeVisible();
    const commitCall = probe.harness.getCalls("/servers/api/playbooks/import/", "POST")[1];
    expect(commitCall.body).toMatchObject({
      content: automationYaml,
      filename: "site.yml",
      save: true,
      expected_content_hash: "yaml-reviewed-hash",
    });

    await dialog.getByRole("button", { name: "Open project" }).click();
    await expect(page).toHaveURL(/\/automation\/playbooks\/7$/);
    await expect(page.getByRole("heading", { name: "Web tier rollout" })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Content", selected: true })).toBeVisible();
    await expect(page.getByText("Original", { exact: true }).first()).toBeVisible();
    await expect(page.getByText(/Published #1/)).toBeVisible();

    const stickyHeader = page.getByRole("heading", { name: "Web tier rollout" }).locator("xpath=ancestor::div[contains(@class,'sticky')]");
    const projectTabs = page.getByRole("tablist", { name: "Project sections" });
    await expect(stickyHeader.getByRole("tablist", { name: "Project sections" })).toBeVisible();
    const [headerBox, tabsBox] = await Promise.all([stickyHeader.boundingBox(), projectTabs.boundingBox()]);
    expect(headerBox).not.toBeNull();
    expect(tabsBox).not.toBeNull();
    expect(tabsBox!.y).toBeGreaterThanOrEqual(headerBox!.y);
    expect(tabsBox!.y + tabsBox!.height).toBeLessThanOrEqual(headerBox!.y + headerBox!.height + 1);

    const adaptation = page.getByRole("region", { name: "AI check and adaptation" });
    await page.mouse.wheel(0, 900);
    await expect(stickyHeader).toBeInViewport();
    await stickyHeader.getByRole("button", { name: "AI adaptation" }).click();
    await expect(adaptation).toBeInViewport();
    await expect(adaptation.getByRole("button", { name: "Analyze" })).toBeFocused();

    await expectNoBrowserErrors(probe);
  });

  test("imports an archive, edits a role with clone-on-write, reviews adaptation, publishes, and exports", async ({ page }) => {
    const probe = await prepareAutomation(page, {
      role: "owner",
      dirtyDraft: false,
      compatibilityReady: false,
    });

    await page.goto("/automation");
    await page.getByRole("button", { name: "Import", exact: true }).first().click();
    const importDialog = page.getByRole("dialog", { name: "Connect Ansible project" });
    await importDialog.getByRole("tab", { name: "Archive" }).click();
    await importDialog.getByLabel("Choose project archive").setInputFiles({
      name: "web-tier.zip",
      mimeType: "application/zip",
      buffer: Buffer.from("PK mock safe archive"),
    });
    await expect(importDialog.getByText("ansible/roles/web/tasks/main.yml", { exact: true })).toBeVisible();
    await importDialog.getByLabel("Ansible project root").click();
    await page.getByRole("option", { name: "ansible", exact: true }).click();
    await expect.poll(() => probe.harness.getCalls("/servers/api/playbooks/import/preview/", "POST").length).toBe(2);
    await expect(importDialog.getByText("roles/web/tasks/main.yml", { exact: true })).toBeVisible();
    await importDialog.getByText(/Ignored service files/).click();
    await expect(importDialog.getByText(".gitlab-ci.yml", { exact: true })).toBeVisible();
    await expect(importDialog.getByText("community.general", { exact: true })).toBeVisible();
    await expect(importDialog.getByText("Private project", { exact: true })).toBeVisible();
    expect(String(probe.harness.getCalls("/servers/api/playbooks/import/preview/", "POST")[1]?.body)).toContain("project_path");
    expect(String(probe.harness.getCalls("/servers/api/playbooks/import/preview/", "POST")[1]?.body)).toContain("ansible");
    await importDialog.getByRole("button", { name: "Add private project" }).click();
    await expect(importDialog.getByText("Project added")).toBeVisible();
    const archiveCommitBody = String(probe.harness.getCalls("/servers/api/playbooks/import/commit/", "POST")[0]?.body);
    expect(archiveCommitBody).toContain("archive-reviewed-hash");
    expect(archiveCommitBody).toContain("private");
    expect(archiveCommitBody).toContain("project_path");
    expect(archiveCommitBody).toContain("expected_project_path");
    expect(archiveCommitBody).toContain("ansible");
    await importDialog.getByRole("button", { name: "Open project" }).click();

    await page.getByRole("button", { name: "roles/web/tasks/main.yml" }).click();
    const roleEditor = page.getByRole("textbox", { name: "roles/web/tasks/main.yml editor" });
    await expect(roleEditor).toBeVisible();
    await roleEditor.fill(automationYaml.replace("Deploy web tier", "Configure nginx role"));
    await page.getByRole("button", { name: "Save file" }).click();
    await expect.poll(() => probe.harness.getCalls("/servers/api/playbooks/7/draft/file/", "PATCH").length).toBe(1);
    expect(probe.harness.getCalls("/servers/api/playbooks/7/draft/file/", "PATCH")[0].body).toMatchObject({
      path: "roles/web/tasks/main.yml",
      expected_draft_version: 3,
      expected_bundle_hash: "bundle-published-hash",
    });
    expect(probe.state.draftBundleHash).toBe("bundle-cow-4");

    await page.getByRole("tab", { name: "Original", exact: true }).click();
    await expect(page.getByRole("textbox", { name: "roles/web/tasks/main.yml original" })).toContainText("Install nginx");
    expect(probe.harness.getCalls("/servers/api/playbooks/7/draft/file/", "GET").some((call) => call.query.view === "base")).toBe(true);
    await page.getByRole("tab", { name: "Changes", exact: true }).click();
    const fileChanges = page.getByRole("region", { name: "Current file changes" });
    await expect(fileChanges).toContainText("Install nginx");
    await expect(fileChanges).toContainText("Configure nginx role");

    await page.getByRole("button", { name: "Prepare adaptation" }).click();
    const proposal = page.getByRole("region", { name: "Proposal review" });
    await expect(proposal).toContainText("No changes have been applied yet.");
    await expect(proposal.getByRole("region", { name: "YAML diff" })).toBeVisible();
    await proposal.getByRole("button", { name: "Apply reviewed proposal" }).click();
    await expect.poll(() => probe.harness.getCalls("/servers/api/playbooks/7/compatibility/apply/", "POST").length).toBe(1);
    expect(probe.harness.getCalls("/servers/api/playbooks/7/compatibility/apply/", "POST")[0].body).toMatchObject({
      path: "roles/web/tasks/main.yml",
      expected_draft_version: 4,
      expected_bundle_hash: "bundle-cow-4",
      base_revision_id: 11,
    });

    await page.getByRole("tab", { name: "Versions" }).click();
    await page.getByRole("button", { name: "Export immutable revision 1" }).click();
    await expect.poll(() => probe.harness.getCalls("/servers/api/playbooks/7/revisions/11/export/", "GET").length).toBe(1);

    const header = page.getByRole("heading", { name: "Web tier rollout" }).locator("xpath=ancestor::div[contains(@class,'sticky')]");
    await header.getByRole("button", { name: "Publish", exact: true }).click();
    const publishDialog = page.getByRole("alertdialog", { name: "Publish the current working copy?" });
    await expect(publishDialog).toContainText("history is not rewritten");
    await publishDialog.getByRole("button", { name: "Publish", exact: true }).click();
    await expect.poll(() => probe.harness.getCalls("/servers/api/playbooks/7/revisions/", "POST").length).toBe(1);
    await expect.poll(() => probe.harness.getCalls("/servers/api/playbooks/7/revisions/12/publish/", "POST").length).toBe(1);

    await expectNoBrowserErrors(probe);
  });

  test("imports and manually refreshes a GitLab snapshot without persisting the token", async ({ page }) => {
    const probe = await prepareAutomation(page, { role: "owner", gitlab: true, compatibilityReady: true });
    const token = "glpat-e2e-request-only-token";

    await page.goto("/automation");
    await page.getByRole("button", { name: "Import", exact: true }).first().click();
    const importDialog = page.getByRole("dialog", { name: "Connect Ansible project" });
    await importDialog.getByRole("tab", { name: "GitLab" }).click();
    await importDialog.getByLabel("GitLab project URL").fill("https://gitlab.example.test/platform/ansible");
    await importDialog.getByLabel("Branch or tag").fill("main");
    await importDialog.getByLabel("Ansible directory").fill("ansible");
    await importDialog.getByLabel("Access token — private projects only").fill(token);
    await expect(importDialog.getByText("The token is used once and never stored.")).toBeVisible();
    await importDialog.getByRole("button", { name: "Check project" }).click();
    await expect(importDialog.getByText("gitlab.example.test/platform/ansible")).toBeVisible();
    await expect(importDialog.getByText("roles/web/tasks/main.yml", { exact: true })).toBeVisible();
    await importDialog.getByRole("button", { name: "Add private project" }).click();
    await expect.poll(() => probe.harness.getCalls("/servers/api/playbooks/import/gitlab/commit/", "POST").length).toBe(1);
    const importCommit = probe.harness.getCalls("/servers/api/playbooks/import/gitlab/commit/", "POST")[0];
    expect(importCommit.body).toMatchObject({
      token,
      expected_content_hash: "gitlab-reviewed-hash",
      visibility: "private",
      entrypoint: "site.yml",
    });
    await importDialog.getByRole("button", { name: "Open project" }).click();

    await page.getByRole("button", { name: "Refresh from GitLab" }).first().click();
    const refreshDialog = page.getByRole("dialog", { name: "Refresh project from GitLab" });
    await refreshDialog.getByLabel("Token — private projects only").fill(token);
    await refreshDialog.getByRole("button", { name: "Review changes" }).click();
    const refreshPreview = refreshDialog.getByLabel("GitLab refresh preview");
    await expect(refreshPreview).toContainText("roles/web/handlers/main.yml");
    await expect(refreshPreview).toContainText("roles/web/tasks/main.yml");
    await refreshDialog.getByRole("button", { name: "Create new revision" }).click();
    await expect.poll(() => probe.harness.getCalls("/servers/api/playbooks/7/gitlab/refresh/commit/", "POST").length).toBe(1);
    const refreshCommit = probe.harness.getCalls("/servers/api/playbooks/7/gitlab/refresh/commit/", "POST")[0];
    expect(refreshCommit.body).toMatchObject({
      token,
      entrypoint: "site.yml",
      expected_content_hash: "gitlab-refresh-hash",
      expected_base_revision_id: 11,
    });
    expect(probe.state.publishedRevisionId).toBe(11);
    expect(probe.state.revisions[0]).toMatchObject({ id: 13, origin_type: "gitlab" });

    const persistedBrowserState = await page.evaluate(() => JSON.stringify(window.localStorage));
    expect(persistedBrowserState).not.toContain(token);
    const nonGitLabCalls = probe.harness.calls.filter((call) => !call.path.includes("gitlab"));
    expect(JSON.stringify(nonGitLabCalls)).not.toContain(token);
    await expectNoBrowserErrors(probe);
  });

  for (const role of ["viewer", "editor", "operator", "manager"] as AutomationRole[]) {
    test(`${role} sees only the fixed role actions`, async ({ page }) => {
      const options: AutomationMockOptions = {
        role,
        compatibilityReady: role === "operator" || role === "manager" || role === "viewer",
        dirtyDraft: role === "manager",
      };
      const probe = await prepareAutomation(page, options);
      await page.goto("/automation/playbooks/7");
      const heading = page.getByRole("heading", { name: "Web tier rollout" });
      await expect(heading).toBeVisible({ timeout: 20_000 });
      const header = heading.locator("xpath=ancestor::div[contains(@class,'sticky')]");
      const nameInput = page.getByLabel("Name", { exact: true });

      if (role === "viewer") {
        await expect(nameInput).toBeDisabled();
        await expect(header.getByRole("button", { name: /^(Validate|Publish|Run)$/ })).toHaveCount(0);
        await page.getByRole("tab", { name: "Access" }).click();
        await expect(page.getByText("Project access")).toHaveCount(0);
      } else if (role === "editor") {
        await expect(nameInput).toBeEnabled();
        await expect(header.getByRole("button", { name: "Validate", exact: true })).toBeVisible();
        await expect(header.getByRole("button", { name: "Run", exact: true })).toHaveCount(0);
      } else if (role === "operator") {
        await expect(nameInput).toBeDisabled();
        await expect(header.getByRole("button", { name: "Run", exact: true })).toBeVisible();
        await expect(header.getByRole("button", { name: "Publish", exact: true })).toHaveCount(0);
      } else {
        await expect(nameInput).toBeEnabled();
        await expect(header.getByRole("button", { name: "Publish", exact: true })).toBeVisible();
        await page.getByRole("tab", { name: "Access" }).click();
        await expect(page.getByRole("heading", { name: "Project access" })).toBeVisible();
        await page.getByRole("button", { name: "Add access" }).click();
        const accessDialog = page.getByRole("dialog", { name: "Add or update access" });
        await expect(accessDialog.getByRole("combobox", { name: "Access principal" })).toHaveCount(0);
        await accessDialog.getByLabel("Search user").fill("ali");
        await accessDialog.getByRole("option", { name: /alice/ }).click();
        await expect(accessDialog.getByText("View, validate, run, and export")).toBeVisible();
        await accessDialog.getByRole("combobox", { name: "Access level" }).click();
        await expect(page.getByRole("option", { name: "Use", exact: true })).toBeVisible();
        await expect(page.getByRole("option", { name: "Use + edit", exact: true })).toBeVisible();
        await expect(page.getByRole("option", { name: "Group", exact: true })).toHaveCount(0);
      }

      await expectNoBrowserErrors(probe);
    });
  }

  test("shows running and terminal report states, recovers APIs, and retries through the normal wizard", async ({ page }) => {
    test.setTimeout(150_000);
    const probe = await prepareAutomation(page, {
      role: "owner",
      compatibilityReady: true,
      failFirstReport: true,
      failFirstLog: true,
    });

    await page.goto("/automation/runs/901");
    await expect(page.getByRole("tab", { name: /Execution/, selected: true })).toBeVisible({ timeout: 20_000 });
    const progressbar = page.getByRole("progressbar", { name: "Run progress" });
    await expect(progressbar).toBeVisible();
    await expect(progressbar).not.toHaveAttribute("aria-valuenow");
    await expect(page.getByRole("button", { name: "Cancel" })).toBeVisible();
    await expect(page.getByText("Executing")).toBeVisible();

    const terminalCases = [
      { id: 902, status: "Completed", text: "The run finished without recorded failures." },
      { id: 903, status: "Partial", text: "nginx validation failed" },
      { id: 904, status: "Failed", text: "web-02 is unreachable" },
      { id: 905, status: "Cancelled", text: "Cancelled" },
    ];
    for (const item of terminalCases) {
      await page.goto(`/automation/runs/${item.id}`);
      await expect(page.getByRole("tab", { name: "Result", selected: true })).toBeVisible();
      await expect(page.getByText(item.status, { exact: true }).first()).toBeVisible();
      await expect(page.getByText(item.text, { exact: false }).first()).toBeVisible();
    }

    await page.goto("/automation/runs/906");
    await expect.poll(() => probe.state.reportCalls[906] || 0, { timeout: 8_000 }).toBeGreaterThanOrEqual(2);
    await expect(page.getByText("2/2", { exact: true })).toBeVisible();

    await page.goto("/automation/runs/904?tab=log");
    await expect(page.getByText("The streamed log is unavailable; saved output is shown.")).toBeVisible();
    await page.getByRole("button", { name: "Retry", exact: true }).click();
    await expect(page.getByText(/PLAY \[Deploy web tier\]/)).toBeVisible();
    await expect.poll(() => probe.state.logCalls[904] || 0).toBeGreaterThanOrEqual(2);

    await page.getByRole("tab", { name: "Result" }).click();
    await page.getByRole("button", { name: "Retry failed hosts" }).click();
    await expect(page).toHaveURL(/\/automation\/playbooks\/7\/run$/);
    await expect(page.getByRole("heading", { name: "Safe retry: Web tier rollout" })).toBeVisible();
    await expect(page.getByText("Retry targets are locked")).toBeVisible();
    await expect(page.getByText("api_token", { exact: true })).toBeVisible();
    await expect.poll(
      () => probe.harness.getCalls("/servers/api/playbooks/7/revisions/", "GET").length,
    ).toBeGreaterThan(0);
    await expect.poll(
      () => probe.harness.getCalls("/servers/api/playbooks/7/bindings/", "GET").length,
    ).toBeGreaterThan(0);
    const releaseInput = page.getByLabel("release", { exact: true });
    const validateButton = page.getByRole("button", { name: "Validate and continue" });
    await expect(async () => {
      await releaseInput.fill("2026.08.26");
      await expect(releaseInput).toHaveValue("2026.08.26");
      await expect(validateButton).toBeEnabled();
      await validateButton.click({ timeout: 3_000 });
      await expect(page.getByRole("heading", { name: "Ready to run" })).toBeVisible({ timeout: 3_000 });
    }).toPass({ timeout: 20_000 });
    await expect(page.getByRole("heading", { name: "Ready to run" })).toBeVisible();
    const validationCall = probe.harness.getCalls("/servers/api/playbooks/7/revisions/11/validate/", "POST")[0];
    expect(validationCall.body).toMatchObject({
      server_ids: [2],
      group_ids: [],
      variable_names: ["api_token", "release"],
    });
    expect(probe.harness.calls.filter((call) => call.path.endsWith("/rerun-failed/"))).toHaveLength(0);

    expect(probe.errors).toEqual([
      "console: Failed to load resource: the server responded with a status of 503 (Service Unavailable)",
      "console: Failed to load resource: the server responded with a status of 503 (Service Unavailable)",
    ]);
    probe.errors.length = 0;
    await expectNoBrowserErrors(probe);
  });

  for (const style of ["flow", "flow-dark"] as FlowStyle[]) {
    for (const viewport of [
      { label: "desktop", width: 1440, height: 900 },
      { label: "mobile-390", width: 390, height: 844 },
    ]) {
      test(`${style} ${viewport.label} reflows and keeps the workspace accessibility budget`, async ({ page }) => {
        await page.setViewportSize({ width: viewport.width, height: viewport.height });
        const probe = await prepareAutomation(page, { role: "owner", compatibilityReady: true }, style);
        await page.goto("/automation/playbooks/7");
        await expect(page.locator("html")).toHaveAttribute("data-ui-style", style);
        await expect(page.getByRole("heading", { name: "Web tier rollout" })).toBeVisible({ timeout: 20_000 });
        await expect(page.getByRole("tab", { name: "Content", selected: true })).toBeVisible();
        await expectNoHorizontalOverflow(page);
        const violations = await collectSeriousAndCriticalViolations(page, "main");
        expectViolationsWithinBudget(violations, {});
        await expectNoBrowserErrors(probe);
      });
    }
  }
});
