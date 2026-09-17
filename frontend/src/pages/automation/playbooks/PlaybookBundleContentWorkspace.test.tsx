import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getPlaybookDraftFile, getPlaybookDraftFiles } from "@/api/playbooks";
import { PlaybookBundleContentWorkspace } from "./PlaybookBundleContentWorkspace";

vi.mock("@/api/playbooks", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/api/playbooks")>();
  return {
    ...original,
    getPlaybookDraftFile: vi.fn(),
    getPlaybookDraftFiles: vi.fn(),
    updatePlaybookDraftFile: vi.fn(),
  };
});

vi.mock("@/components/editor/CodeEditor", () => ({
  CodeEditor: ({ content, readOnly, ariaLabel }: { content: string; readOnly?: boolean; ariaLabel?: string }) => (
    <textarea aria-label={ariaLabel} readOnly={readOnly} value={content} onChange={() => undefined} />
  ),
}));

function renderWorkspace() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <PlaybookBundleContentWorkspace
        lang="en"
        playbookId={7}
        entrypointEditor={<div>Entrypoint editor</div>}
      />
    </QueryClientProvider>,
  );
}

describe("PlaybookBundleContentWorkspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getPlaybookDraftFiles).mockResolvedValue({
      success: true,
      tree: {
        entrypoint: "playbook.yml",
        bundle_hash: "bundle-v4",
        draft_version: 4,
        files: [
          { path: "playbook.yml", size_bytes: 20, sha256: "entry", is_text: true, editable: true },
          { path: "roles/web/tasks/main.yml", size_bytes: 24, sha256: "role", is_text: true, editable: true },
        ],
      },
    });
    vi.mocked(getPlaybookDraftFile).mockImplementation(async (_id, path, view) => ({
      success: true,
      file: {
        path,
        content: view === "base" ? "- name: Original role\n" : "- name: Working role\n",
        sha256: view === "base" ? "base" : "current",
        size_bytes: 22,
        is_text: true,
      },
      draft_version: 4,
      bundle_hash: "bundle-v4",
    }));
  });

  it("loads immutable base content for Original and Changes modes", async () => {
    renderWorkspace();

    fireEvent.click(await screen.findByRole("button", { name: /roles\/web\/tasks\/main\.yml/ }));
    expect(await screen.findByLabelText("roles/web/tasks/main.yml editor")).toHaveValue("- name: Working role\n");

    await waitFor(() => expect(getPlaybookDraftFile).toHaveBeenCalledWith(7, "roles/web/tasks/main.yml", "base"));
    fireEvent.click(screen.getByRole("tab", { name: "Original" }));
    expect(await screen.findByLabelText("roles/web/tasks/main.yml original")).toHaveValue("- name: Original role\n");

    fireEvent.click(screen.getByRole("tab", { name: "Changes" }));
    expect(screen.getByText("Working copy compared with the immutable base revision.")).toBeInTheDocument();
    expect(screen.getByText(/- - name: Original role/)).toBeInTheDocument();
    expect(screen.getByText(/\+ - name: Working role/)).toBeInTheDocument();
  });
});
