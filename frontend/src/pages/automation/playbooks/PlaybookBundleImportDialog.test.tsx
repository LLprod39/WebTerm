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
  it("starts with a clear File vs GitLab choice", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <PlaybookBundleImportDialog open lang="en" onOpenChange={vi.fn()} />
      </QueryClientProvider>,
    );

    expect(screen.getByRole("dialog", { name: "Import Ansible" })).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Import source" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /File/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /GitLab/i })).toBeInTheDocument();
    expect(screen.queryByLabelText("Paste YAML")).not.toBeInTheDocument();
  });

  it("previews pasted YAML after choosing File", async () => {
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

    fireEvent.click(screen.getByRole("button", { name: /File/i }));
    fireEvent.click(screen.getByText("Or paste YAML text"));
    fireEvent.change(screen.getByLabelText("Paste YAML"), { target: { value: "- hosts: all\n" } });
    fireEvent.change(screen.getByLabelText("Filename"), { target: { value: "site.yml" } });
    fireEvent.click(screen.getByRole("button", { name: "Check and continue" }));
    await waitFor(() => expect(previewRawPlaybook).toHaveBeenCalledWith("- hosts: all\n", "site.yml"));
    expect(await screen.findByRole("region", { name: "YAML import preview" })).toHaveTextContent("Private project");
    expect(screen.getByRole("progressbar", { name: "Import progress" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Add and continue" }));
    await waitFor(() => expect(commitRawPlaybook).toHaveBeenCalledWith("- hosts: all\n", "site.yml", "sha-reviewed"));
    expect(await screen.findByText("Script added")).toBeInTheDocument();
  });

  it("opens GitLab form from the source choice", () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <PlaybookBundleImportDialog open lang="en" onOpenChange={vi.fn()} />
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: /GitLab/i }));
    expect(screen.getByLabelText("GitLab project URL")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Back to source/i }));
    expect(screen.getByRole("group", { name: "Import source" })).toBeInTheDocument();
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

    expect(screen.getByRole("dialog", { name: "Import Ansible" })).toBeInTheDocument();
    expect(await screen.findByText("Drop YAML or ZIP/TAR here")).toBeInTheDocument();
  });
});
