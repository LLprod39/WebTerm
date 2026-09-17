import type { ApiHandler, ApiRequest } from "./apiHarness";
import { json } from "./apiHarness";

export type AutomationRole = "viewer" | "editor" | "operator" | "manager" | "owner";

export interface AutomationMockOptions {
  role?: AutomationRole;
  gitlab?: boolean;
  dirtyDraft?: boolean;
  compatibilityReady?: boolean;
  failFirstReport?: boolean;
  failFirstLog?: boolean;
}

export interface AutomationMockState {
  role: AutomationRole;
  draftVersion: number;
  draftContentHash: string;
  draftBundleHash: string;
  publishedRevisionId: number;
  revisions: Array<Record<string, unknown>>;
  roleFileContent: string;
  reportCalls: Record<number, number>;
  logCalls: Record<number, number>;
}

const ENTRYPOINT = [
  "---",
  "- name: Deploy web tier",
  "  hosts: web",
  "  gather_facts: true",
  "  roles:",
  "    - web",
  "",
].join("\n");

const ROLE_TASK = [
  "---",
  "- name: Install nginx",
  "  ansible.builtin.package:",
  "    name: nginx",
  "    state: present",
  "",
].join("\n");

const ADAPTED_ROLE_TASK = ROLE_TASK.replace("state: present", "state: latest");

function capabilities(role: AutomationRole) {
  const base = {
    can_view: true,
    can_edit: false,
    can_validate: false,
    can_publish: false,
    can_run: false,
    can_export: false,
    can_share: false,
    can_delete: false,
    is_owner: false,
  };
  if (role === "editor") return { ...base, can_edit: true, can_validate: true, can_export: true };
  if (role === "operator") return { ...base, can_validate: true, can_run: true, can_export: true };
  if (role === "manager") {
    return {
      ...base,
      can_edit: true,
      can_validate: true,
      can_publish: true,
      can_run: true,
      can_export: true,
      can_share: true,
    };
  }
  if (role === "owner") {
    return {
      can_view: true,
      can_edit: true,
      can_validate: true,
      can_publish: true,
      can_run: true,
      can_export: true,
      can_share: true,
      can_delete: true,
      is_owner: true,
    };
  }
  return base;
}

function compatibility(ready: boolean) {
  return {
    analyzer_version: 3,
    status: ready ? "ready" : "needs_adaptation",
    ready,
    host_selectors: ["web"],
    host_patterns: ["web"],
    missing_bindings: [],
    required_variables: ["release"],
    dependencies: { roles: ["web"], collections: ["community.general"], assets: [] },
    issues: ready ? [] : [{ code: "platform_path", severity: "warning", message: "Use the managed WebTerm target mapping." }],
    semantic_hash: ready ? "semantic-ready" : "semantic-review",
    syntax_check: { status: "passed", passed: true, method: "ansible-playbook --syntax-check" },
  };
}

function revision(id: number, number: number, contentHash: string, message: string, source = ENTRYPOINT) {
  return {
    id,
    revision_number: number,
    parent_id: id === 11 ? null : 11,
    content_format: "ansible_yaml",
    content_hash: contentHash,
    bundle_hash: `bundle-${contentHash}`,
    origin_type: id === 11 ? "import" : "manual",
    message,
    author_id: 7,
    author_username: "pilot-owner",
    created_at: `2026-08-26T10:0${number}:00Z`,
    source_yaml: source,
    compatibility: compatibility(true),
  };
}

function bundlePreview(contentHash = "bundle-reviewed-hash", selectedEntrypoint = "site.yml") {
  return {
    archive_format: "zip",
    content_hash: contentHash,
    file_count: 5,
    total_size_bytes: 1480,
    files: [
      { path: "site.yml", size_bytes: 140, sha256: "sha-site", is_text: true },
      { path: "roles/web/tasks/main.yml", size_bytes: 130, sha256: "sha-role", is_text: true },
      { path: "roles/web/templates/nginx.conf.j2", size_bytes: 90, sha256: "sha-template", is_text: true },
      { path: ".gitlab-ci.yml", size_bytes: 900, sha256: "sha-ci", is_text: true },
      { path: "README.md", size_bytes: 220, sha256: "sha-readme", is_text: true },
    ],
    manifest: {
      schema_version: 1,
      kind: "ansible-project",
      name: "Web tier",
      description: "Imported infrastructure project",
      entrypoint: selectedEntrypoint,
      tags: ["web"],
      required_collections: ["community.general"],
      required_roles: ["web"],
    },
    entrypoints: [
      { path: "site.yml", play_count: 1, task_count: 2, plays: [{ name: "Deploy web tier", hosts: "web", task_count: 2 }] },
      { path: "maintenance.yml", play_count: 1, task_count: 1, plays: [{ name: "Maintenance", hosts: "web", task_count: 1 }] },
    ],
    selected_entrypoint: selectedEntrypoint,
    secret_warnings: [],
    ignored_files: [".gitlab-ci.yml", "README.md"],
    safe_to_commit: true,
  };
}

function archiveBundlePreview(projectPath = "") {
  const scoped = projectPath === "ansible";
  const prefix = scoped ? "" : "ansible/";
  const selectedEntrypoint = `${prefix}playbook.yml`;
  return {
    ...bundlePreview("archive-reviewed-hash", selectedEntrypoint),
    project_path: scoped ? "ansible" : "",
    file_count: 3,
    files: [
      { path: `${prefix}playbook.yml`, size_bytes: 140, sha256: "sha-site", is_text: true },
      { path: `${prefix}roles/web/tasks/main.yml`, size_bytes: 130, sha256: "sha-role", is_text: true },
      { path: `${prefix}roles/web/templates/nginx.conf.j2`, size_bytes: 90, sha256: "sha-template", is_text: true },
    ],
    manifest: {
      schema_version: 1,
      kind: "ansible-project",
      name: "Web tier",
      description: "Imported infrastructure project",
      entrypoint: selectedEntrypoint,
      tags: ["web"],
      required_collections: ["community.general"],
      required_roles: ["web"],
    },
    entrypoints: [
      { path: `${prefix}playbook.yml`, play_count: 1, task_count: 2, plays: [{ name: "Deploy web tier", hosts: "web", task_count: 2 }] },
      { path: `${prefix}maintenance.yml`, play_count: 1, task_count: 1, plays: [{ name: "Maintenance", hosts: "web", task_count: 1 }] },
    ],
    selected_entrypoint: selectedEntrypoint,
    ignored_files: [".gitlab-ci.yml", "README.md", "service/app.py"],
  };
}

function bindingProfile() {
  return {
    id: 51,
    name: "Production web",
    is_default: true,
    selector_mappings: { web: { server_ids: [2], group_ids: [] } },
    variable_values: {},
    secret_variables: ["api_token"],
    options: { concurrency: 2, become: true, dry_run: true, tags: "deploy", skip_tags: "dangerous" },
    version: 1,
    content_hash: "binding-hash",
    updated_at: "2026-08-26T10:00:00Z",
  };
}

function makePlaybook(options: Required<AutomationMockOptions>, state: AutomationMockState) {
  const ready = options.compatibilityReady;
  return {
    id: 7,
    name: "Web tier rollout",
    description: "Managed Ansible project",
    kind: "ansible",
    category: "deploy",
    visibility: "private",
    tags: ["web", "production"],
    fidelity: { runnable: 2, total: 2, score: 1 },
    compatibility: compatibility(ready),
    active_compatibility_revision: ready ? {
      id: 71,
      status: "validated",
      report: compatibility(true),
      semantic_guard: { passed: true, violations: [] },
      change_summary: [],
      inventory_bindings: { web: { server_ids: [2], group_ids: [] } },
      created_at: "2026-08-26T10:00:00Z",
      active: true,
    } : null,
    task_count: 2,
    is_template_clone: false,
    template_slug: "",
    last_run_at: "2026-08-26T10:05:00Z",
    last_run_status: "completed",
    created_at: "2026-08-26T09:00:00Z",
    updated_at: "2026-08-26T10:05:00Z",
    owner_id: options.role === "owner" ? 7 : 99,
    origin_revision_id: 11,
    published_revision_id: state.publishedRevisionId,
    published_revision_number: Number(state.revisions.find((item) => item.id === state.publishedRevisionId)?.revision_number || 1),
    published_content_hash: String(state.revisions.find((item) => item.id === state.publishedRevisionId)?.content_hash || "published-hash"),
    draft_version: state.draftVersion,
    has_unpublished_draft: state.draftContentHash !== "published-hash",
    source: options.gitlab ? {
      type: "gitlab",
      host: "gitlab.example.test",
      project: "platform/ansible",
      ref: "main",
      path: "ansible",
    } : { type: "archive" },
    capabilities: capabilities(options.role),
    tasks: [],
    source_yaml: ENTRYPOINT,
    adapted_source_yaml: "",
  };
}

function runStatus(runId: number) {
  if (runId === 901) return "running";
  if (runId === 902 || runId === 906) return "completed";
  if (runId === 903) return "partial";
  if (runId === 904) return "failed";
  if (runId === 905) return "cancelled";
  return "completed";
}

function makeRun(runId: number) {
  const status = runStatus(runId);
  const live = status === "running";
  const failed = status === "failed" || status === "partial";
  const cancelled = status === "cancelled";
  return {
    id: runId,
    playbook_id: 7,
    status,
    playbook_name: "Web tier rollout",
    target_server_ids: [1, 2],
    target_group_ids: [],
    options: { dry_run: true, concurrency: 2, become: true, engine: "ansible" },
    summary: {
      hosts_total: 2,
      hosts_ok: failed ? 1 : cancelled ? 0 : live ? 0 : 2,
      hosts_failed: failed ? 1 : 0,
      tasks_ok: live ? 1 : failed ? 3 : cancelled ? 1 : 4,
      tasks_changed: status === "partial" ? 1 : 0,
      tasks_failed: failed ? 1 : 0,
      tasks_unreachable: status === "failed" ? 1 : 0,
      tasks_skipped: cancelled ? 1 : 0,
      tasks_cancelled: cancelled ? 1 : 0,
      engine: "ansible",
    },
    progress: {
      engine: "ansible",
      phase: live ? "execution" : "completed",
      play: "Deploy web tier",
      task: live ? "Install nginx" : "",
      task_number: live ? 1 : 4,
      tasks_total: live ? null : 4,
      hosts_seen: live ? 1 : 2,
      hosts_total: 2,
      counts: { ok: live ? 1 : failed ? 3 : 4, changed: status === "partial" ? 1 : 0, failed: failed ? 1 : 0, unreachable: status === "failed" ? 1 : 0, skipped: cancelled ? 1 : 0 },
      finished: !live,
    },
    live_log: "PLAY [Deploy web tier]\nTASK [Install nginx]\n",
    inventory_preview: "[web]\nweb-01\nweb-02\n",
    error_message: failed ? (status === "failed" ? "web-02 is unreachable" : "nginx validation failed") : "",
    cancel_requested: cancelled,
    started_at: "2026-08-26T10:00:00Z",
    finished_at: live ? null : "2026-08-26T10:00:12Z",
    created_at: "2026-08-26T09:59:58Z",
    host_results: [],
  };
}

function taskCounts(status: string) {
  const failed = status === "failed";
  const unreachable = status === "unreachable";
  const cancelled = status === "cancelled";
  const running = status === "running";
  return {
    total: 2,
    ok: failed || unreachable || cancelled || running ? 1 : 2,
    changed: 0,
    failed: failed ? 1 : 0,
    unreachable: unreachable ? 1 : 0,
    skipped: 0,
    cancelled: cancelled ? 1 : 0,
    running: running ? 1 : 0,
    pending: 0,
  };
}

function makeReport(runId: number) {
  const run = makeRun(runId);
  const live = run.status === "running";
  const firstHostStatus = run.status === "cancelled" ? "cancelled" : live ? "running" : "ok";
  const secondHostStatus = run.status === "failed" ? "unreachable" : run.status === "partial" ? "failed" : firstHostStatus;
  const hosts = [
    {
      server_id: 1,
      server_name: "web-01",
      host: "10.0.0.11",
      status: firstHostStatus,
      task_counts: taskCounts(firstHostStatus),
      first_failure: null,
      detail_url: `/servers/api/playbooks/runs/${runId}/hosts/1/`,
    },
    {
      server_id: 2,
      server_name: "web-02",
      host: "10.0.0.12",
      status: secondHostStatus,
      task_counts: taskCounts(secondHostStatus),
      first_failure: ["failed", "unreachable"].includes(secondHostStatus)
        ? { task_id: "install", task_name: "Install nginx", message: run.error_message }
        : null,
      detail_url: `/servers/api/playbooks/runs/${runId}/hosts/2/`,
    },
  ];
  return {
    schema_version: 2,
    run: {
      id: runId,
      playbook_id: 7,
      playbook_name: run.playbook_name,
      revision_id: 11,
      validation_id: 77,
      binding_profile_id: 51,
      status: run.status,
      cancel_requested: run.cancel_requested,
      target_count: 2,
      options: run.options,
      created_at: run.created_at,
      started_at: run.started_at,
      finished_at: run.finished_at,
      duration_ms: live ? null : 12_000,
    },
    progress: {
      state_version: live ? 3 : 7,
      phase: live ? "execution" : "completed",
      total_kind: live ? "unknown" : "exact",
      completed: live ? null : 4,
      total: live ? null : 4,
      percent: live ? null : 100,
      indeterminate: live,
      engine: "ansible",
      play: "Deploy web tier",
      task: live ? "Install nginx" : "",
      task_number: live ? 1 : 4,
      hosts_seen: live ? 1 : 2,
      hosts_total: 2,
      counts: run.summary,
      is_terminal: !live,
      log_start_cursor: 0,
      log_end_cursor: 52,
      log_truncated: false,
    },
    summary: run.summary,
    failure: run.error_message ? {
      code: run.status === "failed" ? "unreachable" : "task_failed",
      message: run.error_message,
      host_id: 2,
      host_name: "web-02",
      task_id: "install",
      task_name: "Install nginx",
      retryable: true,
      suggested_action: "Review the failed host, then validate a safe retry.",
    } : null,
    hosts,
    dispatch: live ? { status: "running", queued_at: run.created_at, claimed_at: run.started_at, completed_at: null, attempt_count: 1, heartbeat_stale: false, mutation_safe_to_retry: false } : null,
    log: { start_cursor: 0, end_cursor: 52, truncated: false, url: `/servers/api/playbooks/runs/${runId}/log/` },
    actions: {
      can_cancel: live,
      can_retry_failed: Boolean(run.error_message),
      can_export: !live,
      retry_context_url: `/servers/api/playbooks/runs/${runId}/retry-context/`,
      export_url: `/servers/api/playbooks/runs/${runId}/export/`,
    },
  };
}

function bodyObject(req: ApiRequest): Record<string, unknown> {
  return req.body && typeof req.body === "object" && !Array.isArray(req.body)
    ? req.body as Record<string, unknown>
    : {};
}

export function createAutomationWorkspaceMocks(input: AutomationMockOptions = {}): {
  handler: ApiHandler;
  state: AutomationMockState;
} {
  const options: Required<AutomationMockOptions> = {
    role: input.role || "owner",
    gitlab: input.gitlab ?? false,
    dirtyDraft: input.dirtyDraft ?? false,
    compatibilityReady: input.compatibilityReady ?? true,
    failFirstReport: input.failFirstReport ?? false,
    failFirstLog: input.failFirstLog ?? false,
  };
  const state: AutomationMockState = {
    role: options.role,
    draftVersion: 3,
    draftContentHash: options.dirtyDraft ? "draft-modified-hash" : "published-hash",
    draftBundleHash: options.dirtyDraft ? "bundle-draft-modified" : "bundle-published-hash",
    publishedRevisionId: 11,
    revisions: [revision(11, 1, "published-hash", "Imported snapshot")],
    roleFileContent: ROLE_TASK,
    reportCalls: {},
    logCalls: {},
  };

  const handler: ApiHandler = async (req) => {
    if (req.path === "/api/auth/session/" && req.method === "GET") {
      return json({
        authenticated: true,
        user: {
          id: 7,
          username: "pilot-owner",
          email: "pilot@example.test",
          is_staff: true,
          features: { automation: true, servers: true, settings: true, dashboard: true },
        },
      });
    }

    if (req.path === "/api/settings/readiness/" && req.method === "GET") {
      return json({
        success: true,
        status: "ready",
        summary: { ready: 1, warning: 0, error: 0, total: 1 },
        checks: [{ key: "ansible_runtime", title: "Ansible runtime", status: "ready", severity: "ready", message: "Ready" }],
      });
    }

    if (req.path === "/servers/api/frontend/bootstrap/" && req.method === "GET") {
      return json({
        success: true,
        servers: [
          { id: 1, name: "web-01", host: "10.0.0.11", port: 22, username: "ubuntu", server_type: "ssh", status: "online", group_id: 21, group_name: "Web", is_shared: false, can_edit: true, share_context_enabled: false, shared_by_username: "", terminal_path: "/servers/1/terminal", minimal_terminal_path: "/servers/1/terminal/minimal", last_connected: null },
          { id: 2, name: "web-02", host: "10.0.0.12", port: 22, username: "ubuntu", server_type: "ssh", status: "online", group_id: 21, group_name: "Web", is_shared: false, can_edit: true, share_context_enabled: false, shared_by_username: "", terminal_path: "/servers/2/terminal", minimal_terminal_path: "/servers/2/terminal/minimal", last_connected: null },
        ],
        groups: [{ id: 21, name: "Web", description: "Web tier", color: "#3b82f6", server_count: 2 }],
        stats: { owned: 2, shared: 0, total: 2 },
        recent_activity: [],
      });
    }

    if (req.path === "/servers/api/playbooks/" && req.method === "GET") {
      return json({ success: true, playbooks: [makePlaybook(options, state)], count: 1 });
    }
    if (req.path === "/servers/api/playbooks/templates/" && req.method === "GET") return json({ success: true, templates: [] });
    if (req.path === "/servers/api/playbooks/ansible/status/" && req.method === "GET") {
      return json({ success: true, ansible: { available: true, method: "native", binary: "ansible-playbook", version: "2.18", message: "ready", validation_available: true, worker_ready: true } });
    }

    if (req.path === "/servers/api/playbooks/import/" && req.method === "POST") {
      const body = bodyObject(req);
      if (body.save === true) {
        return json({ success: true, playbook: makePlaybook(options, state), parsed: { name: "Web tier rollout" }, content_hash: "yaml-reviewed-hash", entrypoint: "site.yml" });
      }
      return json({
        success: true,
        preview: true,
        parsed: { name: "Web tier rollout", tags: ["web"] },
        content_hash: "yaml-reviewed-hash",
        tree: { entrypoint: "site.yml", files: [{ path: "site.yml", size_bytes: ENTRYPOINT.length, sha256: "sha-site", is_text: true, editable: true, is_entrypoint: true }] },
        entrypoint: "site.yml",
        dependencies: { roles: ["web"], collections: ["community.general"], assets: [] },
        compatibility: compatibility(true),
        secret_findings: [],
        safe_to_commit: true,
      });
    }

    if (req.path === "/servers/api/playbooks/import/preview/" && req.method === "POST") {
      const projectPath = typeof req.body === "string" && req.body.includes("ansible") ? "ansible" : "";
      return json({ success: true, preview: archiveBundlePreview(projectPath) });
    }
    if (req.path === "/servers/api/playbooks/import/commit/" && req.method === "POST") {
      return json({
        success: true,
        playbook: { id: 7, name: "Web tier", category: "deploy", visibility: "private" },
        revision: { id: 11, number: 1, content_hash: "published-hash", bundle_hash: "bundle-published-hash" },
        bundle: { id: 31, content_hash: "archive-reviewed-hash", file_count: 5, size_bytes: 1480, scan_status: "clean" },
        preview: archiveBundlePreview("ansible"),
      });
    }

    if (req.path === "/servers/api/playbooks/import/gitlab/preview/" && req.method === "POST") {
      const body = bodyObject(req);
      const entrypoint = typeof body.entrypoint === "string" && body.entrypoint ? body.entrypoint : "site.yml";
      return json({
        success: true,
        preview: bundlePreview("gitlab-reviewed-hash", entrypoint),
        source: { type: "gitlab", host: "gitlab.example.test", project: "platform/ansible", ref: "main", path: "ansible" },
      });
    }
    if (req.path === "/servers/api/playbooks/import/gitlab/commit/" && req.method === "POST") {
      return json({
        success: true,
        playbook: { id: 7, name: "Web tier", category: "deploy", visibility: "private" },
        revision: { id: 11, number: 1, content_hash: "published-hash", bundle_hash: "bundle-published-hash" },
        bundle: { id: 31, content_hash: "gitlab-reviewed-hash", file_count: 5, size_bytes: 1480, scan_status: "clean" },
        preview: bundlePreview("gitlab-reviewed-hash"),
      });
    }

    if (req.path === "/servers/api/playbooks/7/" && req.method === "GET") {
      return json({ success: true, playbook: makePlaybook(options, state) });
    }
    if (req.path === "/servers/api/playbooks/7/draft/" && req.method === "GET") {
      return json({
        success: true,
        draft: { id: 41, base_revision_id: 11, content_format: "ansible_yaml", source_yaml: ENTRYPOINT, tasks: [], content_hash: state.draftContentHash, bundle_hash: state.draftBundleHash, version: state.draftVersion, last_editor_id: 7, updated_at: "2026-08-26T10:06:00Z" },
      });
    }
    if (req.path === "/servers/api/playbooks/7/draft/" && req.method === "PUT") {
      const body = bodyObject(req);
      state.draftVersion += 1;
      state.draftContentHash = `draft-${state.draftVersion}`;
      return json({ success: true, draft: { id: 41, base_revision_id: 11, content_format: "ansible_yaml", source_yaml: String(body.source_yaml || ENTRYPOINT), tasks: [], content_hash: state.draftContentHash, bundle_hash: state.draftBundleHash, version: state.draftVersion, last_editor_id: 7, updated_at: "2026-08-26T10:07:00Z" } });
    }
    if (req.path === "/servers/api/playbooks/7/draft/files/" && req.method === "GET") {
      return json({
        success: true,
        tree: {
          entrypoint: "site.yml",
          bundle_hash: state.draftBundleHash,
          draft_version: state.draftVersion,
          files: [
            { path: "site.yml", size_bytes: ENTRYPOINT.length, sha256: "sha-site", is_text: true, editable: true },
            { path: "roles/web/tasks/main.yml", size_bytes: state.roleFileContent.length, sha256: `sha-role-${state.draftVersion}`, is_text: true, editable: true },
            { path: "roles/web/templates/nginx.conf.j2", size_bytes: 90, sha256: "sha-template", is_text: true, editable: false },
            { path: "README.md", size_bytes: 220, sha256: "sha-readme", is_text: true, editable: false },
          ],
        },
      });
    }
    if (req.path === "/servers/api/playbooks/7/draft/file/" && req.method === "GET") {
      const path = req.query.path || "";
      const content = path === "roles/web/tasks/main.yml"
        ? req.query.view === "base" ? ROLE_TASK : state.roleFileContent
        : path.endsWith("nginx.conf.j2") ? "server { listen 80; }\n" : "# Web tier\n";
      return json({ success: true, file: { path, content, sha256: `sha-${state.draftVersion}`, size_bytes: content.length, is_text: true }, draft_version: state.draftVersion, bundle_hash: state.draftBundleHash });
    }
    if (req.path === "/servers/api/playbooks/7/draft/file/" && req.method === "PATCH") {
      const body = bodyObject(req);
      const path = String(body.path || req.query.path || "");
      state.roleFileContent = String(body.content || state.roleFileContent);
      state.draftVersion += 1;
      state.draftContentHash = `draft-file-${state.draftVersion}`;
      state.draftBundleHash = `bundle-cow-${state.draftVersion}`;
      const file = { path, content: state.roleFileContent, sha256: `sha-role-${state.draftVersion}`, size_bytes: state.roleFileContent.length, is_text: true };
      return json({
        success: true,
        file,
        draft: { id: 41, base_revision_id: 11, content_format: "ansible_yaml", source_yaml: ENTRYPOINT, tasks: [], content_hash: state.draftContentHash, bundle_hash: state.draftBundleHash, version: state.draftVersion, last_editor_id: 7, updated_at: "2026-08-26T10:08:00Z" },
        tree: { entrypoint: "site.yml", bundle_hash: state.draftBundleHash, draft_version: state.draftVersion, files: [{ path: "site.yml", size_bytes: ENTRYPOINT.length, sha256: "sha-site", is_text: true, editable: true }, { path, size_bytes: state.roleFileContent.length, sha256: file.sha256, is_text: true, editable: true }] },
      });
    }

    if (req.path === "/servers/api/playbooks/7/revisions/" && req.method === "GET") {
      return json({ success: true, published_revision_id: state.publishedRevisionId, revisions: state.revisions });
    }
    if (req.path === "/servers/api/playbooks/7/revisions/" && req.method === "POST") {
      const created = revision(12, 2, state.draftContentHash, String(bodyObject(req).message || "Workspace revision"), ENTRYPOINT);
      state.revisions = [created, ...state.revisions];
      return json({ success: true, revision: created });
    }
    const revisionDetailMatch = req.path.match(/^\/servers\/api\/playbooks\/7\/revisions\/(\d+)\/$/);
    if (revisionDetailMatch && req.method === "GET") {
      return json({ success: true, revision: state.revisions.find((item) => item.id === Number(revisionDetailMatch[1])) || state.revisions[0] });
    }
    const publishMatch = req.path.match(/^\/servers\/api\/playbooks\/7\/revisions\/(\d+)\/publish\/$/);
    if (publishMatch && req.method === "POST") {
      state.publishedRevisionId = Number(publishMatch[1]);
      return json({ success: true, published_revision_id: state.publishedRevisionId, revision: state.revisions.find((item) => item.id === state.publishedRevisionId) });
    }
    if (/^\/servers\/api\/playbooks\/7\/revisions\/\d+\/export\/$/.test(req.path) && req.method === "GET") {
      return { body: "sanitized bundle with manifest and checksums" };
    }

    if (req.path === "/servers/api/playbooks/7/bindings/" && req.method === "GET") return json({ success: true, bindings: [bindingProfile()] });
    if (req.path === "/servers/api/playbooks/7/shares/" && req.method === "GET") return json({ success: true, shares: [] });
    if (req.path === "/servers/api/playbooks/7/shares/candidates/" && req.method === "GET") {
      return json({ success: true, candidates: { users: [{ id: 8, username: "alice", email: "alice@example.test" }], groups: [{ id: 31, name: "Platform operators" }] } });
    }
    if (req.path === "/servers/api/playbooks/7/shares/" && req.method === "POST") {
      const body = bodyObject(req);
      return json({ success: true, share: { id: 81, role: body.role, principal: { type: body.principal_type, id: body.principal_id, label: "alice" }, capabilities: body.capabilities, expires_at: body.expires_at || null, revoked_at: null, created_at: "2026-08-26T10:10:00Z" } });
    }

    if (req.path === "/servers/api/playbooks/7/compatibility/analyze/" && req.method === "POST") {
      return json({ success: true, report: compatibility(options.compatibilityReady), base: { path: "site.yml", content_hash: state.draftContentHash, draft_version: state.draftVersion, bundle_hash: state.draftBundleHash, base_revision_id: 11 } });
    }
    if (req.path === "/servers/api/playbooks/7/compatibility/adapt/" && req.method === "POST") {
      const path = String(bodyObject(req).path || "site.yml");
      return json({
        success: true,
        proposal: { method: "deterministic", adapted_yaml: path === "roles/web/tasks/main.yml" ? ADAPTED_ROLE_TASK : ENTRYPOINT, changes: ["Update the package state while preserving task order."], assumptions: [], semantic_guard: { passed: true, violations: [], original_hash: "semantic-before", adapted_hash: "semantic-after" }, report: compatibility(true) },
        base: { path, content_hash: `sha-${state.draftVersion}`, draft_version: state.draftVersion, bundle_hash: state.draftBundleHash, base_revision_id: 11 },
      });
    }
    if (req.path === "/servers/api/playbooks/7/compatibility/apply/" && req.method === "POST") {
      const body = bodyObject(req);
      state.roleFileContent = String(body.adapted_yaml || state.roleFileContent);
      state.draftVersion += 1;
      state.draftContentHash = `adapted-${state.draftVersion}`;
      state.draftBundleHash = `bundle-adapted-${state.draftVersion}`;
      const playbook = makePlaybook({ ...options, compatibilityReady: true }, state);
      return json({ success: true, playbook, report: compatibility(true), draft: { id: 41, base_revision_id: 11, content_format: "ansible_yaml", source_yaml: ENTRYPOINT, tasks: [], content_hash: state.draftContentHash, bundle_hash: state.draftBundleHash, version: state.draftVersion, last_editor_id: 7, updated_at: "2026-08-26T10:11:00Z" } });
    }

    if (req.path === "/servers/api/playbooks/7/gitlab/refresh/preview/" && req.method === "POST") {
      return json({
        success: true,
        preview: bundlePreview("gitlab-refresh-hash"),
        source: { type: "gitlab", host: "gitlab.example.test", project: "platform/ansible", ref: "main", path: "ansible" },
        refresh: { base_revision_id: 11, base_content_hash: "published-hash", base_bundle_hash: "bundle-published-hash", diff: { from_bundle_hash: "bundle-published-hash", to_bundle_hash: "bundle-gitlab-refresh", added: ["roles/web/handlers/main.yml"], removed: [], changed: ["roles/web/tasks/main.yml"], unchanged_count: 3 } },
      });
    }
    if (req.path === "/servers/api/playbooks/7/gitlab/refresh/commit/" && req.method === "POST") {
      const imported = { ...revision(13, 3, "gitlab-refresh-hash", "GitLab refresh"), origin_type: "gitlab" };
      state.revisions = [imported, ...state.revisions];
      return json({ success: true, revision: { id: 13, number: 3, content_hash: "gitlab-refresh-hash", bundle_hash: "bundle-gitlab-refresh", origin_type: "gitlab" }, bundle: { id: 33, content_hash: "gitlab-refresh-hash", file_count: 5, size_bytes: 1480, scan_status: "clean" }, refresh: { base_revision_id: 11, diff: { from_bundle_hash: "bundle-published-hash", to_bundle_hash: "bundle-gitlab-refresh", added: ["roles/web/handlers/main.yml"], removed: [], changed: ["roles/web/tasks/main.yml"], unchanged_count: 3 } }, preview: bundlePreview("gitlab-refresh-hash") });
    }

    if (req.path === "/servers/api/playbooks/runs/" && req.method === "GET") {
      return json({ success: true, runs: [makeRun(901), makeRun(902), makeRun(903), makeRun(904), makeRun(905)] });
    }
    if (req.path === "/servers/api/playbooks/runs/history/" && req.method === "GET") {
      return json({ success: true, items: [902, 903, 904, 905].map((id) => { const run = makeRun(id); return { id, playbook_id: 7, playbook_name: run.playbook_name, status: run.status, phase: "completed", state_version: 7, total_kind: "exact", progress_percent: 100, summary: run.summary, failure: makeReport(id).failure, created_at: run.created_at, started_at: run.started_at, finished_at: run.finished_at }; }), page: { limit: 25, next_cursor: null, has_more: false }, filters: { status: [], playbook_id: null, q: "" } });
    }
    const runMatch = req.path.match(/^\/servers\/api\/playbooks\/runs\/(\d+)\/$/);
    if (runMatch && req.method === "GET") return json({ success: true, run: makeRun(Number(runMatch[1])) });
    const reportMatch = req.path.match(/^\/servers\/api\/playbooks\/runs\/(\d+)\/report\/$/);
    if (reportMatch && req.method === "GET") {
      const runId = Number(reportMatch[1]);
      state.reportCalls[runId] = (state.reportCalls[runId] || 0) + 1;
      if (options.failFirstReport && runId === 906 && state.reportCalls[runId] === 1) return json({ error: "temporary report outage" }, 503);
      return json({ success: true, report: makeReport(runId) });
    }
    const hostMatch = req.path.match(/^\/servers\/api\/playbooks\/runs\/(\d+)\/hosts\/(\d+)\/$/);
    if (hostMatch && req.method === "GET") {
      const runId = Number(hostMatch[1]);
      const serverId = Number(hostMatch[2]);
      const host = makeReport(runId).hosts.find((item) => item.server_id === serverId) || makeReport(runId).hosts[0];
      return json({ success: true, host: { ...host, tasks: [{ task_id: "facts", name: "Gather facts", command: "ansible.builtin.setup", description: "", status: "ok", exit_code: 0, output: "ok: redacted" }, { task_id: "install", name: "Install nginx", command: "ansible.builtin.package", description: "", status: host.status === "unreachable" || host.status === "failed" ? host.status : "ok", exit_code: host.status === "failed" ? 1 : 0, output: host.status === "failed" || host.status === "unreachable" ? "connection failed" : "ok: redacted" }] } });
    }
    const logMatch = req.path.match(/^\/servers\/api\/playbooks\/runs\/(\d+)\/log\/$/);
    if (logMatch && req.method === "GET") {
      const runId = Number(logMatch[1]);
      state.logCalls[runId] = (state.logCalls[runId] || 0) + 1;
      if (options.failFirstLog && runId === 904 && state.logCalls[runId] === 1) return json({ error: "temporary log outage" }, 503);
      return json({ success: true, text: "PLAY [Deploy web tier]\nTASK [Install nginx]\nok: [web-01]\n", cursor: Number(req.query.after || 0), next_cursor: 62, start_cursor: 0, end_cursor: 62, has_more: false, truncated: false, reset_required: false });
    }
    const retryMatch = req.path.match(/^\/servers\/api\/playbooks\/runs\/(\d+)\/retry-context\/$/);
    if (retryMatch && req.method === "GET") {
      const runId = Number(retryMatch[1]);
      return json({ success: true, retry_context: { run_id: runId, can_retry: true, blockers: [], playbook_id: 7, revision_id: 11, validation_id: 77, binding_profile_id: 51, failed_server_ids: [2], options: { dry_run: true, concurrency: 2, become: true }, required_variable_names: ["release"], managed_variable_names: ["api_token"], values_redacted: true, rerun_endpoint: `/servers/api/playbooks/runs/${runId}/rerun-failed/` } });
    }
    const validateMatch = req.path.match(/^\/servers\/api\/playbooks\/7\/revisions\/(\d+)\/validate\/$/);
    if (validateMatch && req.method === "POST") {
      return json({ success: true, validation: { id: 78, revision_id: Number(validateMatch[1]), status: "ready", stages: { input_guard: { status: "passed", passed: true }, parse: { status: "passed", passed: true }, compatibility: { status: "passed", passed: true }, runtime: { status: "ready", passed: true }, targets: { status: "passed", passed: true } }, issues: [], compatibility: compatibility(true), started_at: "2026-08-26T10:20:00Z", finished_at: "2026-08-26T10:20:01Z" } });
    }
    if (req.path === "/servers/api/playbooks/7/run/" && req.method === "POST") return json({ success: true, run: makeRun(907) });
    if (/^\/servers\/api\/playbooks\/runs\/\d+\/cancel\/$/.test(req.path) && req.method === "POST") return json({ success: true, run: makeRun(905) });
    if (/^\/servers\/api\/playbooks\/runs\/\d+\/export\/$/.test(req.path) && req.method === "GET") return { body: "redacted report bundle" };

    return undefined;
  };

  return { handler, state };
}

export const automationYaml = ENTRYPOINT;
