import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  downloadPlaybookBundleExport,
  exportPlaybookRevisionBundle,
} from "@/api/playbook-bundles";
import { PlaybookBundleExportButton } from "./PlaybookBundleExportButton";

vi.mock("@/api/playbook-bundles", () => ({
  exportPlaybookRevisionBundle: vi.fn(),
  downloadPlaybookBundleExport: vi.fn(),
}));
vi.mock("@/lib/notify", () => ({
  notify: { success: vi.fn(), error: vi.fn() },
}));

describe("PlaybookBundleExportButton", () => {
  beforeEach(() => {
    vi.mocked(exportPlaybookRevisionBundle).mockReset();
    vi.mocked(downloadPlaybookBundleExport).mockReset();
  });

  it("renders nothing when export capability is absent", () => {
    render(
      <PlaybookBundleExportButton
        playbookId={7}
        revisionId={14}
        revisionNumber={4}
        canExport={false}
        lang="en"
      />,
    );

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("downloads the selected published revision and shows progress", async () => {
    let resolveExport: (value: { blob: Blob; filename: string; redactionCount: number }) => void = () => {};
    vi.mocked(exportPlaybookRevisionBundle).mockImplementation(
      () => new Promise((resolve) => { resolveExport = resolve; }),
    );
    render(
      <PlaybookBundleExportButton
        playbookId={7}
        revisionId={14}
        revisionNumber={4}
        canExport
        lang="en"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Export published revision 4" }));
    expect(screen.getByRole("button", { name: "Export published revision 4" })).toBeDisabled();
    expect(screen.getByText("Exporting…")).toBeInTheDocument();

    resolveExport({ blob: new Blob(["zip"]), filename: "project-r4.zip", redactionCount: 1 });
    await waitFor(() => expect(downloadPlaybookBundleExport).toHaveBeenCalledTimes(1));
    expect(exportPlaybookRevisionBundle).toHaveBeenCalledWith(7, 14);
  });

  it("keeps a retryable inline error when export fails", async () => {
    vi.mocked(exportPlaybookRevisionBundle).mockRejectedValue(new Error("Artifact unavailable"));
    render(
      <PlaybookBundleExportButton
        playbookId={7}
        revisionId={14}
        revisionNumber={4}
        canExport
        lang="en"
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Export published revision 4" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Artifact unavailable");
    expect(screen.getByRole("button", { name: "Export published revision 4" })).toBeEnabled();
    expect(downloadPlaybookBundleExport).not.toHaveBeenCalled();
  });
});
