import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  commitGitLabPlaybookRefresh,
  previewGitLabPlaybookRefresh,
} from "@/api/playbooks";
import { PlaybookGitLabRefreshButton } from "./PlaybookGitLabRefreshButton";

vi.mock("@/api/playbooks", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/api/playbooks")>();
  return {
    ...original,
    previewGitLabPlaybookRefresh: vi.fn(),
    commitGitLabPlaybookRefresh: vi.fn(),
  };
});

vi.mock("@/lib/notify", () => ({
  notify: { success: vi.fn(), error: vi.fn() },
}));

const previewResponse = {
  success: true as const,
  source: { type: "gitlab" as const, host: "gitlab.example.com", project: "platform/ops", ref: "main" },
  preview: {
    archive_format: "tar",
    content_hash: "snapshot-v2",
    file_count: 2,
    total_size_bytes: 240,
    files: [
      { path: "site.yml", size_bytes: 120, sha256: "site-v2", is_text: true },
      { path: "roles/web/tasks/main.yml", size_bytes: 120, sha256: "role-v2", is_text: true },
    ],
    manifest: { required_collections: ["community.general"], required_roles: ["web"] },
    entrypoints: [{ path: "site.yml", play_count: 1, task_count: 2, plays: [] }],
    selected_entrypoint: "site.yml",
    secret_warnings: [],
    safe_to_commit: true,
  },
  refresh: {
    base_revision_id: 8,
    base_content_hash: "content-v1",
    base_bundle_hash: "bundle-v1",
    diff: {
      from_bundle_hash: "bundle-v1",
      to_bundle_hash: "snapshot-v2",
      added: ["roles/web/tasks/main.yml"],
      removed: [],
      changed: ["site.yml"],
      unchanged_count: 0,
    },
  },
};

function renderButton() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PlaybookGitLabRefreshButton
        lang="en"
        playbookId={17}
        source={{ type: "gitlab", host: "gitlab.example.com", project: "platform/ops", ref: "main" }}
      />
    </QueryClientProvider>,
  );
}

describe("PlaybookGitLabRefreshButton", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(previewGitLabPlaybookRefresh).mockResolvedValue(previewResponse);
    vi.mocked(commitGitLabPlaybookRefresh).mockResolvedValue({
      success: true,
      revision: { id: 18, number: 4, content_hash: "content-v2", bundle_hash: "snapshot-v2", origin_type: "imported" },
      bundle: { id: 22, content_hash: "snapshot-v2", file_count: 2, size_bytes: 240, scan_status: "clean" },
      refresh: { base_revision_id: 8, diff: previewResponse.refresh.diff },
      preview: previewResponse.preview,
    });
  });

  it("requires a reviewed snapshot before creating an immutable revision", async () => {
    renderButton();
    fireEvent.click(screen.getByRole("button", { name: "Refresh from GitLab" }));
    fireEvent.change(screen.getByLabelText("Token — private projects only"), {
      target: { value: "request-only" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Review changes" }));

    expect(await screen.findByLabelText("GitLab refresh preview")).toBeInTheDocument();
    expect(screen.getAllByText("roles/web/tasks/main.yml")).toHaveLength(2);
    expect(screen.getByText("collection: community.general")).toBeInTheDocument();
    expect(commitGitLabPlaybookRefresh).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Create new revision" }));
    await waitFor(() => expect(commitGitLabPlaybookRefresh).toHaveBeenCalledWith(17, {
      token: "request-only",
      entrypoint: "site.yml",
      expected_content_hash: "snapshot-v2",
      expected_base_revision_id: 8,
    }));
  });
});
