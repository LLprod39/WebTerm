import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  commitGitLabPlaybookProject,
  previewGitLabPlaybookProject,
  type CommitPlaybookBundleResponse,
  type PlaybookBundlePreview,
} from "@/api/playbook-bundles";
import { usePlaybookGitLabImport } from "./usePlaybookGitLabImport";

vi.mock("@/api/playbook-bundles", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/playbook-bundles")>();
  return { ...actual, previewGitLabPlaybookProject: vi.fn(), commitGitLabPlaybookProject: vi.fn() };
});

const preview: PlaybookBundlePreview = {
  archive_format: "tar",
  content_hash: "gitlab-snapshot-hash",
  file_count: 2,
  total_size_bytes: 1024,
  files: [],
  manifest: {},
  entrypoints: [{ path: "site.yml", play_count: 1, task_count: 2, plays: [] }],
  selected_entrypoint: "site.yml",
  secret_warnings: [],
  safe_to_commit: true,
};
const committed = {
  success: true,
  playbook: { id: 11, name: "ops", category: "custom", visibility: "private" },
  revision: { id: 21, number: 1, content_hash: "content", bundle_hash: "gitlab-snapshot-hash" },
  bundle: { id: 5, content_hash: "gitlab-snapshot-hash", file_count: 2, size_bytes: 1024, scan_status: "clean" },
  preview,
} satisfies CommitPlaybookBundleResponse;

describe("usePlaybookGitLabImport", () => {
  beforeEach(() => {
    vi.mocked(previewGitLabPlaybookProject).mockReset();
    vi.mocked(commitGitLabPlaybookProject).mockReset();
  });

  it("previews and commits the exact GitLab snapshot", async () => {
    vi.mocked(previewGitLabPlaybookProject).mockResolvedValue({
      success: true,
      preview,
      source: { type: "gitlab", host: "gitlab.example.com", project: "platform/ops", ref: "main" },
    });
    vi.mocked(commitGitLabPlaybookProject).mockResolvedValue(committed);
    const { result } = renderHook(() => usePlaybookGitLabImport());

    act(() => result.current.updateSource({
      project_url: "https://gitlab.example.com/platform/ops",
      ref: "main",
      token: "request-only-token",
    }));
    await act(async () => { await result.current.previewProject(); });

    expect(result.current.metadata).toMatchObject({ name: "ops", entrypoint: "site.yml", visibility: "private" });
    expect(result.current.canCommit).toBe(true);
    await act(async () => { await result.current.commit(); });

    expect(commitGitLabPlaybookProject).toHaveBeenCalledWith(
      expect.objectContaining({ token: "request-only-token", ref: "main" }),
      expect.objectContaining({ name: "ops", entrypoint: "site.yml" }),
      "gitlab-snapshot-hash",
    );
    expect(result.current.status).toBe("success");
  });

  it("invalidates the preview when the repository source changes", async () => {
    vi.mocked(previewGitLabPlaybookProject).mockResolvedValue({
      success: true,
      preview,
      source: { type: "gitlab", host: "gitlab.com", project: "team/ops" },
    });
    const { result } = renderHook(() => usePlaybookGitLabImport());
    act(() => result.current.updateSource({ project_url: "https://gitlab.com/team/ops" }));
    await act(async () => { await result.current.previewProject(); });

    act(() => result.current.updateSource({ ref: "release" }));

    expect(result.current.preview).toBeNull();
    expect(result.current.canCommit).toBe(false);
    expect(result.current.status).toBe("idle");
  });

  it("re-previews the same GitLab snapshot when the entrypoint changes", async () => {
    const multiEntrypointPreview = {
      ...preview,
      entrypoints: [
        ...preview.entrypoints,
        { path: "deploy.yml", play_count: 1, task_count: 3, plays: [] },
      ],
    };
    const refreshedPreview = {
      ...multiEntrypointPreview,
      content_hash: "deploy-preview-hash",
      selected_entrypoint: "deploy.yml",
    };
    const source = { type: "gitlab" as const, host: "gitlab.com", project: "team/ops", ref: "main" };
    vi.mocked(previewGitLabPlaybookProject)
      .mockResolvedValueOnce({ success: true, preview: multiEntrypointPreview, source })
      .mockResolvedValueOnce({ success: true, preview: refreshedPreview, source });
    vi.mocked(commitGitLabPlaybookProject).mockResolvedValue({ ...committed, preview: refreshedPreview });
    const { result } = renderHook(() => usePlaybookGitLabImport());
    act(() => result.current.updateSource({ project_url: "https://gitlab.com/team/ops", ref: "main" }));
    await act(async () => { await result.current.previewProject(); });

    await act(async () => { await result.current.selectEntrypoint("deploy.yml"); });

    expect(previewGitLabPlaybookProject).toHaveBeenLastCalledWith(expect.objectContaining({
      project_url: "https://gitlab.com/team/ops",
      ref: "main",
      entrypoint: "deploy.yml",
    }));
    expect(result.current.preview?.content_hash).toBe("deploy-preview-hash");
    expect(result.current.metadata.entrypoint).toBe("deploy.yml");

    await act(async () => { await result.current.commit(); });
    expect(commitGitLabPlaybookProject).toHaveBeenCalledWith(
      expect.any(Object),
      expect.objectContaining({ entrypoint: "deploy.yml", visibility: "private" }),
      "deploy-preview-hash",
    );
  });
});
