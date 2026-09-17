import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  commitPlaybookBundle,
  previewPlaybookBundle,
  type CommitPlaybookBundleResponse,
  type PlaybookBundlePreview,
} from "@/api/playbook-bundles";
import { usePlaybookBundleImport } from "./usePlaybookBundleImport";

vi.mock("@/api/playbook-bundles", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/api/playbook-bundles")>();
  return {
    ...actual,
    previewPlaybookBundle: vi.fn(),
    commitPlaybookBundle: vi.fn(),
  };
});

const preview: PlaybookBundlePreview = {
  archive_format: "zip",
  content_hash: "bundle-hash",
  file_count: 3,
  total_size_bytes: 2048,
  files: [
    { path: "site.yml", size_bytes: 512, sha256: "yaml-hash", is_text: true },
    { path: "roles/web/tasks/main.yml", size_bytes: 256, sha256: "role-hash", is_text: true },
    { path: "files/logo.bin", size_bytes: 1280, sha256: "binary-hash", is_text: false },
  ],
  manifest: {
    name: "Web project",
    description: "Deploy web tier",
    tags: ["nginx", "deploy"],
  },
  entrypoints: [
    {
      path: "site.yml",
      play_count: 1,
      task_count: 4,
      plays: [{ name: "Web", hosts: "web", task_count: 4 }],
    },
  ],
  selected_entrypoint: "site.yml",
  secret_warnings: [],
  safe_to_commit: true,
};

const committed = {
  success: true,
  playbook: { id: 7, name: "Web project", category: "custom", visibility: "private" },
  revision: { id: 14, number: 1, content_hash: "content-hash", bundle_hash: "bundle-hash" },
  bundle: { id: 3, content_hash: "bundle-hash", file_count: 3, size_bytes: 2048, scan_status: "clean" },
  preview,
} satisfies CommitPlaybookBundleResponse;

describe("usePlaybookBundleImport", () => {
  beforeEach(() => {
    vi.mocked(previewPlaybookBundle).mockReset();
    vi.mocked(commitPlaybookBundle).mockReset();
  });

  it("previews an archive and prefills entrypoint and non-secret metadata", async () => {
    vi.mocked(previewPlaybookBundle).mockResolvedValue({ success: true, preview });
    const { result } = renderHook(() => usePlaybookBundleImport());
    const file = new File(["archive"], "fallback.zip", { type: "application/zip" });

    await act(async () => {
      await result.current.selectFile(file);
    });

    expect(result.current.status).toBe("ready");
    expect(result.current.preview?.files.map((item) => item.path)).toEqual([
      "site.yml",
      "roles/web/tasks/main.yml",
      "files/logo.bin",
    ]);
    expect(result.current.metadata).toMatchObject({
      entrypoint: "site.yml",
      name: "Web project",
      description: "Deploy web tier",
      tags: ["nginx", "deploy"],
      visibility: "private",
    });
    expect(result.current.canCommit).toBe(true);
  });

  it("refuses unsupported files before making a network request", async () => {
    const { result } = renderHook(() => usePlaybookBundleImport());

    await act(async () => {
      await result.current.selectFile(new File(["yaml"], "site.yml"));
    });

    expect(previewPlaybookBundle).not.toHaveBeenCalled();
    expect(result.current.status).toBe("error");
    expect(result.current.errorStage).toBe("file");
    expect(result.current.canCommit).toBe(false);
  });

  it("blocks commit when preview reports security findings", async () => {
    vi.mocked(previewPlaybookBundle).mockResolvedValue({
      success: true,
      preview: {
        ...preview,
        safe_to_commit: false,
        secret_warnings: [{ path: "group_vars/prod.yml", kind: "sensitive_value", key: "api_token" }],
      },
    });
    const { result } = renderHook(() => usePlaybookBundleImport());

    await act(async () => {
      await result.current.selectFile(new File(["archive"], "unsafe.zip"));
      await result.current.commit();
    });

    expect(result.current.canCommit).toBe(false);
    expect(commitPlaybookBundle).not.toHaveBeenCalled();
  });

  it("commits the same file only after preview and exposes the completed result", async () => {
    vi.mocked(previewPlaybookBundle).mockResolvedValue({ success: true, preview });
    vi.mocked(commitPlaybookBundle).mockResolvedValue(committed);
    const onCommitted = vi.fn();
    const { result } = renderHook(() => usePlaybookBundleImport({ onCommitted }));
    const file = new File(["archive"], "project.tar.gz", { type: "application/gzip" });

    await act(async () => {
      await result.current.selectFile(file);
    });
    act(() => result.current.updateMetadata({ category: "deploy", visibility: "shared" }));
    await act(async () => {
      await result.current.commit();
    });

    expect(commitPlaybookBundle).toHaveBeenCalledWith(
      file,
      expect.objectContaining({
        entrypoint: "site.yml",
        name: "Web project",
        category: "deploy",
        visibility: "private",
      }),
      preview.content_hash,
    );
    expect(result.current.status).toBe("success");
    expect(result.current.result).toEqual(committed);
    expect(onCommitted).toHaveBeenCalledWith(committed);
  });

  it("re-previews a selected entrypoint and commits only its refreshed hash", async () => {
    const multiEntrypointPreview: PlaybookBundlePreview = {
      ...preview,
      entrypoints: [
        ...preview.entrypoints,
        { path: "ops.yml", play_count: 1, task_count: 2, plays: [{ name: "Ops", hosts: "ops", task_count: 2 }] },
      ],
    };
    const refreshedPreview: PlaybookBundlePreview = {
      ...multiEntrypointPreview,
      content_hash: "ops-preview-hash",
      selected_entrypoint: "ops.yml",
    };
    vi.mocked(previewPlaybookBundle)
      .mockResolvedValueOnce({ success: true, preview: multiEntrypointPreview })
      .mockResolvedValueOnce({ success: true, preview: refreshedPreview });
    vi.mocked(commitPlaybookBundle).mockResolvedValue({ ...committed, preview: refreshedPreview });
    const { result } = renderHook(() => usePlaybookBundleImport());
    const file = new File(["archive"], "project.zip", { type: "application/zip" });

    await act(async () => {
      await result.current.selectFile(file);
    });
    await act(async () => {
      await result.current.selectEntrypoint("ops.yml");
    });

    expect(previewPlaybookBundle).toHaveBeenLastCalledWith(file, "ops.yml", "");
    expect(result.current.metadata.entrypoint).toBe("ops.yml");
    expect(result.current.preview?.content_hash).toBe("ops-preview-hash");

    await act(async () => {
      await result.current.commit();
    });
    expect(commitPlaybookBundle).toHaveBeenCalledWith(
      file,
      expect.objectContaining({ entrypoint: "ops.yml", visibility: "private" }),
      "ops-preview-hash",
    );
  });

  it("re-previews a safe archive subdirectory and binds commit to its rebased hash", async () => {
    const repositoryPreview: PlaybookBundlePreview = {
      ...preview,
      files: [
        { path: "README.md", size_bytes: 10, sha256: "readme", is_text: true },
        { path: "ansible/site.yml", size_bytes: 512, sha256: "yaml", is_text: true },
      ],
      entrypoints: [{ ...preview.entrypoints[0], path: "ansible/site.yml" }],
      selected_entrypoint: "ansible/site.yml",
      project_path: "",
    };
    const ansiblePreview: PlaybookBundlePreview = {
      ...preview,
      content_hash: "ansible-subdir-hash",
      files: [{ path: "site.yml", size_bytes: 512, sha256: "yaml", is_text: true }],
      entrypoints: [{ ...preview.entrypoints[0], path: "site.yml" }],
      selected_entrypoint: "site.yml",
      project_path: "ansible",
    };
    vi.mocked(previewPlaybookBundle)
      .mockResolvedValueOnce({ success: true, preview: repositoryPreview })
      .mockResolvedValueOnce({ success: true, preview: ansiblePreview });
    vi.mocked(commitPlaybookBundle).mockResolvedValue({ ...committed, preview: ansiblePreview });
    const { result } = renderHook(() => usePlaybookBundleImport());
    const file = new File(["archive"], "repository.zip", { type: "application/zip" });

    await act(async () => { await result.current.selectFile(file); });
    await act(async () => { await result.current.selectProjectPath("ansible/"); });

    expect(previewPlaybookBundle).toHaveBeenLastCalledWith(file, "", "ansible");
    expect(result.current.metadata).toMatchObject({ project_path: "ansible", entrypoint: "site.yml" });
    await act(async () => { await result.current.commit(); });
    expect(commitPlaybookBundle).toHaveBeenCalledWith(
      file,
      expect.objectContaining({ project_path: "ansible", entrypoint: "site.yml", visibility: "private" }),
      "ansible-subdir-hash",
    );
  });
});
