import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";

import { PlaybookBundleImportDialog } from "./PlaybookBundleImportDialog";

describe("PlaybookBundleImportDialog", () => {
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
