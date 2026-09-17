import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { validatePlaybookRevision } from "@/api/playbook-preflight";
import type { PlaybookCapabilities, PlaybookRevision } from "@/api/playbooks";
import type { FrontendServer } from "@/lib/api";
import { RunWizard } from "./RunWizard";

vi.mock("@/api/playbook-preflight", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/api/playbook-preflight")>();
  return { ...original, validatePlaybookRevision: vi.fn() };
});

const capabilities: PlaybookCapabilities = {
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

const revision: PlaybookRevision = {
  id: 12,
  revision_number: 2,
  parent_id: 11,
  content_format: "ansible_yaml",
  content_hash: "content-hash",
  bundle_hash: "bundle-hash",
  origin_type: "manual",
  message: "Release",
  author_id: 1,
  author_username: "owner",
  created_at: "2026-07-24T10:00:00Z",
  compatibility: { host_selectors: ["web"], required_variables: [] },
};

const servers = [{ id: 1, name: "web-01", host: "10.0.0.1", status: "online" }] as FrontendServer[];
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
    workerReady: true,
    compatibility: revision.compatibility,
    revisions: [revision],
    publishedRevisionId: revision.id,
    revisionsLoading: false,
    capabilities,
    onBack: vi.fn(),
    onConfirm: vi.fn(),
    ...overrides,
  };
  return { ...render(<RunWizard {...props} />), props };
}

async function chooseTarget() {
  const server = await screen.findByRole("button", { name: /web-01/i });
  fireEvent.click(server);
}

describe("RunWizard minimal preflight", () => {
  beforeEach(() => vi.mocked(validatePlaybookRevision).mockReset());

  it("shows revision, targets, safe run mode, and optional advanced settings", async () => {
    renderWizard();

    const steps = within(screen.getByLabelText("Run steps"));
    expect(steps.getByText("Setup")).toBeInTheDocument();
    expect(steps.getByText("Review")).toBeInTheDocument();
    expect(await screen.findByText("Run mode")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Dry run/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Apply changes/i })).toBeInTheDocument();
    expect(screen.getByText("Advanced settings")).toBeInTheDocument();
    expect(screen.getByLabelText("Revision")).toBeInTheDocument();
    expect(screen.queryByLabelText("Saved profile")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("extra_vars JSON")).not.toBeInTheDocument();
  });

  it("asks only for required parameters before validation", async () => {
    const requiredRevision = {
      ...revision,
      compatibility: { host_selectors: ["web"], required_variables: ["db_password"] },
    };
    renderWizard({ revisions: [requiredRevision], compatibility: requiredRevision.compatibility });
    await chooseTarget();

    const required = screen.getByLabelText("db_password");
    expect(screen.getByText("Fill in only what the playbook needs to start.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Validate and continue" })).toBeDisabled();
    fireEvent.change(required, { target: { value: "from-user" } });
    expect(screen.getByRole("button", { name: "Validate and continue" })).toBeEnabled();
  });

  it("validates selected servers and starts a dry run with a simple payload", async () => {
    vi.mocked(validatePlaybookRevision).mockResolvedValue({ success: true, validation: readyValidation });
    const onConfirm = vi.fn();
    renderWizard({ onConfirm });
    await chooseTarget();
    fireEvent.click(screen.getByRole("button", { name: /Dry run/i }));
    fireEvent.click(screen.getByRole("button", { name: "Validate and continue" }));

    await waitFor(() => expect(validatePlaybookRevision).toHaveBeenCalledWith(7, 12, {
      server_ids: [1],
      group_ids: [],
      inventory_bindings: { web: { server_ids: [1], group_ids: [] } },
      variable_names: [],
    }));
    expect(await screen.findByText("Ready to run")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Start dry run" }));
    expect(onConfirm).toHaveBeenCalledWith(expect.objectContaining({
      revision_id: 12,
      validation_id: 77,
      server_ids: [1],
      dry_run: true,
      engine: "ansible",
    }));
  });

  it("shows a failed preflight and never enables execution", async () => {
    vi.mocked(validatePlaybookRevision).mockResolvedValue({
      success: true,
      validation: {
        ...readyValidation,
        status: "blocked",
        stages: { runtime: { status: "failed", passed: false, message: "Collection unavailable" } },
        issues: [{
          code: "missing_collection",
          severity: "error",
          stage: "runtime",
          message: "community.general is unavailable",
          remediation: "Install the collection and validate again.",
        }],
      },
    });
    renderWizard();
    await chooseTarget();
    fireEvent.click(screen.getByRole("button", { name: "Validate and continue" }));

    expect(await screen.findByText("Settings need attention")).toBeInTheDocument();
    expect(screen.getByText("community.general is unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start dry run" })).toBeDisabled();
  });

  it("does not validate when the Ansible runtime is unavailable", async () => {
    renderWizard({ ansibleAvailable: false, workerReady: true });
    await chooseTarget();

    expect(screen.getByText("Execution is currently unavailable")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Validate and continue" })).toBeDisabled();
    expect(validatePlaybookRevision).not.toHaveBeenCalled();
  });
});
