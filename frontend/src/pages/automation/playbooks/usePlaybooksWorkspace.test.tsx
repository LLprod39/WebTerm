import type { ReactNode } from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import { getPlaybookRun, type PlaybookDetail } from "@/api/playbooks";
import { I18nProvider } from "@/lib/i18n";
import type { PlaybooksView } from "./types";
import { usePlaybooksWorkspace } from "./usePlaybooksWorkspace";

vi.mock("@/api/playbooks", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/api/playbooks")>();
  return { ...original, getPlaybookRun: vi.fn() };
});

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <I18nProvider>{children}</I18nProvider>
    </QueryClientProvider>
  );
}

afterEach(() => vi.restoreAllMocks());

describe("usePlaybooksWorkspace editor guard", () => {
  it("marks edits dirty and requires confirmation before leaving", () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const { result } = renderHook(
      () => usePlaybooksWorkspace({ servers: [], groups: [], enabled: false }),
      { wrapper },
    );

    act(() => result.current.openNew());
    act(() => result.current.updateEditor({ name: "Unsaved playbook" }));

    expect(result.current.editorDirty).toBe(true);
    const unload = new Event("beforeunload", { cancelable: true });
    expect(window.dispatchEvent(unload)).toBe(false);

    act(() => result.current.leaveEditor());
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(result.current.view.mode).toBe("edit");

    confirm.mockReturnValue(true);
    act(() => result.current.leaveEditor());
    expect(result.current.view.mode).toBe("catalog");
  });

  it("guards route-driven SPA navigation and restores the editor URL when cancelled", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const onViewChange = vi.fn();
    const { result, rerender } = renderHook(
      ({ initialView }: { initialView: PlaybooksView }) =>
        usePlaybooksWorkspace({ servers: [], groups: [], enabled: false, initialView, onViewChange }),
      {
        wrapper,
        initialProps: { initialView: { mode: "edit", playbookId: null } as PlaybooksView },
      },
    );

    act(() => result.current.updateEditor({ name: "Unsaved route edit" }));
    rerender({ initialView: { mode: "catalog" } });

    await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1));
    expect(result.current.view).toEqual({ mode: "edit", playbookId: null });
    expect(onViewChange).toHaveBeenCalledWith(
      { mode: "edit", playbookId: null },
      { replace: true },
    );
  });

  it("stops failed run polling, clears a stale run, and retries only on request", async () => {
    vi.mocked(getPlaybookRun).mockRejectedValue(new Error("Run not found"));
    const { result } = renderHook(
      () => usePlaybooksWorkspace({ servers: [], groups: [], enabled: false }),
      { wrapper },
    );

    act(() => result.current.setActiveRun({ id: 41, status: "completed" } as never));
    act(() => result.current.setView({ mode: "run-results", runId: 99 }));

    await waitFor(() => expect(result.current.runLoadError).toBe("Run not found"));
    expect(result.current.activeRun).toBeNull();
    expect(getPlaybookRun).toHaveBeenCalledTimes(1);

    act(() => result.current.retryRunLoad());
    await waitFor(() => expect(getPlaybookRun).toHaveBeenCalledTimes(2));
  });

  it("refreshes draft and revision caches after adaptation without replacing editor YAML", () => {
    const { result } = renderHook(
      () => usePlaybooksWorkspace({ servers: [], groups: [], enabled: false }),
      { wrapper },
    );
    const invalidate = vi.spyOn(result.current.queryClient, "invalidateQueries").mockResolvedValue(undefined);
    const adapted = {
      id: 7,
      source_yaml: "- hosts: published-copy\n  tasks: []\n",
      compatibility: { analyzer_version: 3, status: "ready" },
      active_compatibility_revision: null,
    } as unknown as PlaybookDetail;

    act(() => result.current.openNew());
    act(() => result.current.updateEditor({ sourceYaml: "- hosts: local-draft\n  tasks: []\n" }));
    act(() => result.current.onCompatibilityApplied(adapted));

    expect(result.current.editor.sourceYaml).toBe("- hosts: local-draft\n  tasks: []\n");
    expect(result.current.editor.compatibility).toEqual(adapted.compatibility);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["playbook-workspace", "draft", 7] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["playbook-workspace", "revisions", 7] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["playbooks"] });
  });
});
