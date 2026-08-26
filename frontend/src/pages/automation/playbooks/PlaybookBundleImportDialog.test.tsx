import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { commitRawPlaybook, previewRawPlaybook } from "@/api/playbooks";
import { PlaybookBundleImportDialog } from "./PlaybookBundleImportDialog";

vi.mock("@/api/playbooks", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/api/playbooks")>();
  return { ...original, previewRawPlaybook: vi.fn(), commitRawPlaybook: vi.fn() };
});

describe("PlaybookBundleImportDialog", () => {
  it("previews YAML server-side and commits the exact reviewed hash as a private project", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const onOpenChange = vi.fn();
    vi.mocked(previewRawPlaybook).mockResolvedValue({
      success: true,
      preview: true,
      parsed: { name: "Site" },
      content_hash: "sha-reviewed",
      tree: { entrypoint: "site.yml", files: [{ path: "site.yml", size_bytes: 13, sha256: "sha-file", is_text: true, editable: true, is_entrypoint: true }] },
      entrypoint: "site.yml",
      dependencies: { roles: [], collections: [], assets: [] },
      compatibility: { ready: true },
      secret_findings: [],
      safe_to_commit: true,
    });
    vi.mocked(commitRawPlaybook).mockResolvedValue({ success: true, playbook: { id: 7, name: "Site" } as never, parsed: {}, content_hash: "sha-reviewed", entrypoint: "site.yml" });
    render(
      <QueryClientProvider client={client}>
        <PlaybookBundleImportDialog open lang="en" onOpenChange={onOpenChange} />
      </QueryClientProvider>,
    );

    expect(screen.getByRole("tab", { name: "YAML", selected: true })).toBeInTheDocument();
    const file = new File(["- hosts: all\n"], "site.yml", { type: "text/yaml" });
    Object.defineProperty(file, "text", { value: vi.fn().mockResolvedValue("- hosts: all\n") });
    fireEvent.change(screen.getByLabelText("Choose Ansible YAML"), { target: { files: [file] } });
    await waitFor(() => expect(previewRawPlaybook).toHaveBeenCalledWith("- hosts: all\n", "site.yml"));
    expect(await screen.findByRole("region", { name: "YAML import preview" })).toHaveTextContent("Private project");
    expect(screen.getByRole("progressbar", { name: "Import progress" })).toBeInTheDocument();
    expect(screen.queryByText(/shared/i)).not.toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);

    fireEvent.click(screen.getByRole("button", { name: "Add private project" }));
    await waitFor(() => expect(commitRawPlaybook).toHaveBeenCalledWith("- hosts: all\n", "site.yml", "sha-reviewed"));
    expect(await screen.findByText("Project added")).toBeInTheDocument();
  });

  it("renders the requested source mode without reading derived state before initialization", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(
      <QueryClientProvider client={client}>
        <PlaybookBundleImportDialog
          open
          lang="en"
          initialMode="archive"
          onOpenChange={vi.fn()}
        />
      </QueryClientProvider>,
    );

    expect(screen.getByRole("dialog", { name: "Connect Ansible project" })).toBeInTheDocument();
    expect(await screen.findByRole("tab", { name: "Archive", selected: true })).toBeInTheDocument();
    expect(screen.getByText("Drop a ZIP/TAR here")).toBeInTheDocument();
  });
});
