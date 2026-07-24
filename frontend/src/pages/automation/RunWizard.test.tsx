import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { validatePlaybookRevision } from "@/api/playbook-preflight";
import type {
  PlaybookBindingProfile,
  PlaybookCapabilities,
  PlaybookRevision,
} from "@/api/playbooks";
import type { FrontendServer } from "@/lib/api";
import { RunWizard } from "./RunWizard";

vi.mock("@/api/playbook-preflight", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/api/playbook-preflight")>();
  return { ...original, validatePlaybookRevision: vi.fn() };
});

const ownerCapabilities: PlaybookCapabilities = {
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

const publishedRevision: PlaybookRevision = {
  id: 12,
  revision_number: 2,
  parent_id: 11,
  content_format: "ansible_yaml",
  content_hash: "published-content-hash",
  bundle_hash: "published-bundle-hash",
  origin_type: "manual",
  message: "Release",
  author_id: 1,
  author_username: "owner",
  created_at: "2026-07-24T10:00:00Z",
  compatibility: { host_selectors: ["web"], required_variables: [] },
};

const draftRevision: PlaybookRevision = {
  ...publishedRevision,
  id: 13,
  revision_number: 3,
  content_hash: "unpublished-content-hash",
  message: "Draft candidate",
  compatibility: { host_selectors: ["db"], required_variables: ["db_password"] },
};

const servers = [
  { id: 1, name: "web-01", host: "10.0.0.1", status: "online" },
] as FrontendServer[];

const readyValidation = {
  id: 77,
  revision_id: 12,
  binding_profile_id: null,
  status: "ready",
  stages: {
    parse: { status: "passed" },
    bindings: { status: "complete" },
    runtime: { status: "passed", passed: true },
    targets: { status: "ready", count: 1 },
  },
  issues: [],
};

function renderWizard(overrides: Partial<React.ComponentProps<typeof RunWizard>> = {}) {
  const props: React.ComponentProps<typeof RunWizard> = {
    lang: "en",
    playbookId: 7,
    playbookName: "Deploy",
    servers,
    groups: [],
    running: false,
    ansibleAvailable: true,
    compatibility: { host_selectors: ["web"], required_variables: [], issues: [] },
    revisions: [draftRevision, publishedRevision],
    publishedRevisionId: publishedRevision.id,
    revisionsLoading: false,
    bindingProfiles: [],
    capabilities: ownerCapabilities,
    onBack: vi.fn(),
    onConfirm: vi.fn(),
    ...overrides,
  };
  return { ...render(<RunWizard {...props} />), props };
}

async function moveToTargets() {
  const next = screen.getByRole("button", { name: "Next" });
  await waitFor(() => expect(next).toBeEnabled());
  fireEvent.click(next);
}

async function selectAdhocTargetAndMoveToVariables() {
  await moveToTargets();
  fireEvent.click(screen.getByRole("button", { name: /web-01/i }));
  const next = screen.getByRole("button", { name: "Next" });
  await waitFor(() => expect(next).toBeEnabled());
  fireEvent.click(next);
}

describe("RunWizard preflight", () => {
  beforeEach(() => vi.mocked(validatePlaybookRevision).mockReset());

  it("presents four explicit preflight steps", async () => {
    renderWizard();

    const steps = within(screen.getByLabelText("Preflight steps"));
    expect(steps.getByText("1. Revision")).toBeInTheDocument();
    expect(steps.getByText("2. Targets")).toBeInTheDocument();
    expect(steps.getByText("3. Variables")).toBeInTheDocument();
    expect(steps.getByText("4. Review")).toBeInTheDocument();
    expect(await screen.findByText("published-content-hash")).toBeInTheDocument();
  });

  it("restricts a non-owner to the published immutable revision", async () => {
    renderWizard({
      capabilities: { ...ownerCapabilities, is_owner: false, can_edit: false, can_publish: false },
    });

    expect(await screen.findByText("Shared playbooks can run only their published revision.")).toBeInTheDocument();
    expect(screen.queryByLabelText("Revision")).not.toBeInTheDocument();
    expect(screen.getByText("published-content-hash")).toBeInTheDocument();
    expect(screen.queryByText("unpublished-content-hash")).not.toBeInTheDocument();
  });

  it("lets a non-owner editor choose unpublished revisions and uses that revision's selector schema", async () => {
    renderWizard({
      capabilities: { ...ownerCapabilities, is_owner: false },
    });

    const revisionSelect = await screen.findByLabelText("Revision");
    fireEvent.click(revisionSelect);
    fireEvent.click(await screen.findByRole("option", { name: /#3.*unpublished/i }));

    expect(await screen.findByText("unpublished-content-hash")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByLabelText("hosts: db")).toBeInTheDocument();
    expect(screen.queryByLabelText("hosts: web")).not.toBeInTheDocument();
  });

  it("exposes pressed state for selectable targets", async () => {
    renderWizard();
    await moveToTargets();

    const server = screen.getByRole("button", { name: /web-01/i });
    expect(server).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(server);
    expect(server).toHaveAttribute("aria-pressed", "true");
  });

  it("shows blocked validation stages and issues and never enables run", async () => {
    const onConfirm = vi.fn();
    vi.mocked(validatePlaybookRevision).mockResolvedValue({
      success: true,
      validation: {
        ...readyValidation,
        status: "blocked",
        stages: {
          bindings: { status: "complete" },
          runtime: { status: "failed", passed: false, message: "Collection unavailable" },
        },
        issues: [{
          code: "missing_collection",
          severity: "error",
          stage: "runtime",
          message: "community.general is unavailable",
          remediation: "Install the collection and validate again.",
        }],
      },
    });
    renderWizard({ onConfirm });
    await selectAdhocTargetAndMoveToVariables();
    fireEvent.click(screen.getByRole("button", { name: "Review & validate" }));

    expect(await screen.findByText("Run blocked")).toBeInTheDocument();
    expect(screen.getByText("community.general is unavailable")).toBeInTheDocument();
    expect(screen.getByText("Install the collection and validate again.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run validated revision" })).toBeDisabled();
    expect(onConfirm).not.toHaveBeenCalled();
    expect(validatePlaybookRevision).toHaveBeenCalledWith(7, 12, {
      server_ids: [1],
      group_ids: [],
      inventory_bindings: { web: { server_ids: [1], group_ids: [] } },
      variable_names: [],
    });
  });

  it("uses a personal profile, keeps typed vars, and emits exact validation and run payloads", async () => {
    const profile = {
      id: 9,
      name: "Production",
      is_default: true,
      selector_mappings: { web: { server_ids: [1], group_ids: [] } },
      variable_values: { release_channel: "stable" },
      secret_variables: ["deploy_token"],
      options: {
        concurrency: 6,
        become: false,
        dry_run: true,
        tags: "deploy",
        skip_tags: "risky",
        limit: "web",
      },
      version: 4,
      content_hash: "profile-hash",
      updated_at: "2026-07-24T10:00:00Z",
      secret_values: { deploy_token: "must-never-render" },
    } as PlaybookBindingProfile & { secret_values: Record<string, string> };
    vi.mocked(validatePlaybookRevision).mockResolvedValue({
      success: true,
      validation: { ...readyValidation, binding_profile_id: profile.id },
    });
    const onConfirm = vi.fn();
    renderWizard({ bindingProfiles: [profile], onConfirm });

    await moveToTargets();
    expect(await screen.findByText("Production")).toBeInTheDocument();
    expect(screen.getByText("deploy_token · secret")).toBeInTheDocument();
    expect(screen.queryByText("must-never-render")).not.toBeInTheDocument();
    const next = screen.getByRole("button", { name: "Next" });
    await waitFor(() => expect(next).toBeEnabled());
    fireEvent.click(next);

    fireEvent.change(screen.getByLabelText("extra_vars JSON"), {
      target: { value: '{"release":42,"enabled":true,"matrix":[1,2]}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Review & validate" }));

    await waitFor(() => expect(validatePlaybookRevision).toHaveBeenCalledWith(7, 12, {
      binding_profile_id: 9,
      server_ids: [1],
      group_ids: [],
      inventory_bindings: { web: { server_ids: [1], group_ids: [] } },
      variable_names: ["deploy_token", "enabled", "matrix", "release", "release_channel"],
    }));
    expect(await screen.findByText("Ready to run")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Start dry-run" }));

    expect(onConfirm).toHaveBeenCalledWith({
      revision_id: 12,
      validation_id: 77,
      binding_profile_id: 9,
      server_ids: [1],
      group_ids: [],
      inventory_bindings: { web: { server_ids: [1], group_ids: [] } },
      extra_vars: { release: 42, enabled: true, matrix: [1, 2] },
      concurrency: 6,
      dry_run: true,
      become: false,
      tags: "deploy",
      skip_tags: "risky",
      limit: "web",
      engine: "ansible",
    });
  });

  it("blocks Review with a clear typed JSON error", async () => {
    renderWizard();
    await selectAdhocTargetAndMoveToVariables();

    fireEvent.change(screen.getByLabelText("extra_vars JSON"), { target: { value: '{"release":' } });

    expect(screen.getByRole("alert")).toHaveTextContent("Invalid JSON");
    expect(screen.getByRole("button", { name: "Review & validate" })).toBeDisabled();
    expect(validatePlaybookRevision).not.toHaveBeenCalled();
  });

  it("allows validation but never execution without can_run", async () => {
    vi.mocked(validatePlaybookRevision).mockResolvedValue({
      success: true,
      validation: readyValidation,
    });
    const onConfirm = vi.fn();
    renderWizard({
      capabilities: {
        ...ownerCapabilities,
        is_owner: false,
        can_edit: false,
        can_publish: false,
        can_run: false,
        can_validate: true,
      },
      onConfirm,
    });

    await selectAdhocTargetAndMoveToVariables();
    fireEvent.click(screen.getByRole("button", { name: "Review & validate" }));

    expect(await screen.findByText("Ready to run")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run validated revision" })).toBeDisabled();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("uses worker readiness, not Ansible availability, for JSON runbooks", async () => {
    const runbookRevision: PlaybookRevision = {
      ...publishedRevision,
      id: 21,
      content_format: "runbook_json",
      content_hash: "runbook-hash",
      compatibility: { host_selectors: ["web"], required_variables: [] },
    };
    vi.mocked(validatePlaybookRevision).mockResolvedValue({
      success: true,
      validation: { ...readyValidation, revision_id: runbookRevision.id },
    });
    renderWizard({
      revisions: [runbookRevision],
      publishedRevisionId: runbookRevision.id,
      ansibleAvailable: false,
      workerReady: true,
    });

    expect(await screen.findByText("The worker is ready to execute this JSON runbook.")).toBeInTheDocument();
    await selectAdhocTargetAndMoveToVariables();
    fireEvent.click(screen.getByRole("button", { name: "Review & validate" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "Run validated revision" })).toBeEnabled());
  });

  it("does not use worker readiness to bypass a missing Ansible runtime", async () => {
    vi.mocked(validatePlaybookRevision).mockResolvedValue({
      success: true,
      validation: readyValidation,
    });
    renderWizard({ ansibleAvailable: false, workerReady: true });

    await selectAdhocTargetAndMoveToVariables();
    fireEvent.click(screen.getByRole("button", { name: "Review & validate" }));

    expect(await screen.findByText("Ready to run")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run validated revision" })).toBeDisabled();
  });
});
