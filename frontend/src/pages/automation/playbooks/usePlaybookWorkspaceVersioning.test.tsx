import { useState, type ReactNode } from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  getPlaybookDraft,
  listPlaybookBindings,
  listPlaybookRevisions,
  listPlaybookShares,
  updatePlaybookDraft,
  type PlaybookCapabilities,
  type PlaybookDetail,
  type PlaybookDraft,
} from "@/api/playbooks";
import { fetchAuthSession } from "@/lib/api";
import { detailToPlaybookEditor } from "../playbookEditorState";
import { usePlaybookWorkspaceVersioning } from "./usePlaybookWorkspaceVersioning";

vi.mock("@/api/playbooks", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/api/playbooks")>();
  return {
    ...original,
    getPlaybookDraft: vi.fn(),
    updatePlaybookDraft: vi.fn(),
    listPlaybookRevisions: vi.fn(),
    listPlaybookBindings: vi.fn(),
    listPlaybookShares: vi.fn(),
    createPlaybookRevision: vi.fn(),
    getPlaybookRevision: vi.fn(),
    publishPlaybookRevision: vi.fn(),
    rollbackPlaybookRevision: vi.fn(),
    createPlaybookBinding: vi.fn(),
    updatePlaybookBinding: vi.fn(),
    deletePlaybookBinding: vi.fn(),
    createPlaybookShare: vi.fn(),
    deletePlaybookShare: vi.fn(),
  };
});

vi.mock("@/lib/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/api")>();
  return { ...original, fetchAuthSession: vi.fn() };
});

vi.mock("@/lib/notify", () => ({ notify: { success: vi.fn(), error: vi.fn() } }));

const OWNER_CAPABILITIES: PlaybookCapabilities = {
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

function playbook(capabilities = OWNER_CAPABILITIES): PlaybookDetail {
  return {
    id: 7,
    name: "Deploy",
    description: "",
    kind: "ansible",
    category: "deploy",
    visibility: "private",
    tags: [],
    fidelity: {},
    compatibility: {},
    active_compatibility_revision: null,
    task_count: 0,
    is_template_clone: false,
    template_slug: "",
    last_run_at: null,
    last_run_status: "",
    created_at: null,
    updated_at: null,
    owner_id: 1,
    capabilities,
    tasks: [],
    source_yaml: "- hosts: all\n  tasks: []\n",
    adapted_source_yaml: "",
  };
}

function draft(overrides: Partial<PlaybookDraft> = {}): PlaybookDraft {
  return {
    id: 4,
    base_revision_id: 10,
    content_format: "ansible_yaml",
    source_yaml: "- hosts: all\n  tasks: []\n",
    tasks: [],
    content_hash: "base-hash",
    bundle_hash: "",
    version: 1,
    last_editor_id: 1,
    updated_at: "2026-07-24T10:00:00Z",
    ...overrides,
  };
}

function createWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

function setupQueries(initialDraft = draft()) {
  vi.mocked(fetchAuthSession).mockResolvedValue({ authenticated: true, user: { id: 1 } as never });
  vi.mocked(getPlaybookDraft).mockResolvedValue({ success: true, draft: initialDraft });
  vi.mocked(listPlaybookRevisions).mockResolvedValue({
    success: true,
    published_revision_id: 10,
    revisions: [
      {
        id: 10,
        revision_number: 1,
        parent_id: null,
        content_format: "ansible_yaml",
        content_hash: "base-hash",
        bundle_hash: "",
        origin_type: "manual",
        message: "Initial",
        author_id: 1,
        author_username: "owner",
        created_at: "2026-07-24T09:00:00Z",
      },
    ],
  });
  vi.mocked(listPlaybookBindings).mockResolvedValue({ success: true, bindings: [] });
  vi.mocked(listPlaybookShares).mockResolvedValue({ success: true, shares: [] });
}

describe("usePlaybookWorkspaceVersioning", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupQueries();
  });

  it("autosaves executable content with the current expected_version", async () => {
    const nextDraft = draft({ version: 2, content_hash: "next-hash", source_yaml: "- hosts: web\n  tasks: []\n" });
    vi.mocked(updatePlaybookDraft).mockResolvedValue({ success: true, draft: nextDraft });
    const detail = playbook();
    const { result } = renderHook(() => {
      const [editor, setEditor] = useState(() => detailToPlaybookEditor(detail));
      const workspace = usePlaybookWorkspaceVersioning({
        enabled: true,
        playbookId: detail.id,
        playbook: detail,
        editor,
        setEditor,
        tr: (_ru, en) => en,
      });
      return { editor, setEditor, workspace };
    }, { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.workspace.canEditContent).toBe(true));
    act(() => result.current.setEditor((current) => ({ ...current, sourceYaml: nextDraft.source_yaml })));
    await act(async () => { await result.current.workspace.saveDraftNow(); });

    expect(updatePlaybookDraft).toHaveBeenCalledWith(7, {
      expected_version: 1,
      content_format: "ansible_yaml",
      source_yaml: nextDraft.source_yaml,
    });
    expect(result.current.workspace.draft?.version).toBe(2);
  });

  it("debounces draft autosave after an editor change", async () => {
    const nextSource = "- hosts: workers\n  tasks: []\n";
    vi.mocked(updatePlaybookDraft).mockResolvedValue({
      success: true,
      draft: draft({ version: 2, content_hash: "workers-hash", source_yaml: nextSource }),
    });
    const detail = playbook();
    const { result } = renderHook(() => {
      const [editor, setEditor] = useState(() => detailToPlaybookEditor(detail));
      const workspace = usePlaybookWorkspaceVersioning({
        enabled: true,
        playbookId: detail.id,
        playbook: detail,
        editor,
        setEditor,
        tr: (_ru, en) => en,
      });
      return { setEditor, workspace };
    }, { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.workspace.canEditContent).toBe(true));
    act(() => result.current.setEditor((current) => ({ ...current, sourceYaml: nextSource })));
    expect(updatePlaybookDraft).not.toHaveBeenCalled();

    await waitFor(
      () => expect(updatePlaybookDraft).toHaveBeenCalledWith(7, {
        expected_version: 1,
        content_format: "ansible_yaml",
        source_yaml: nextSource,
      }),
      { timeout: 2_000 },
    );
  });

  it("surfaces a conflict and lets the user accept the server draft", async () => {
    const serverDraft = draft({ version: 3, content_hash: "server-hash", source_yaml: "- hosts: server\n  tasks: []\n" });
    vi.mocked(getPlaybookDraft)
      .mockResolvedValueOnce({ success: true, draft: draft() })
      .mockResolvedValueOnce({ success: true, draft: serverDraft });
    vi.mocked(updatePlaybookDraft).mockRejectedValue(new Error("Draft was changed by another editor"));
    const detail = playbook();
    const { result } = renderHook(() => {
      const [editor, setEditor] = useState(() => detailToPlaybookEditor(detail));
      const workspace = usePlaybookWorkspaceVersioning({ enabled: true, playbookId: 7, playbook: detail, editor, setEditor, tr: (_ru, en) => en });
      return { editor, setEditor, workspace };
    }, { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.workspace.canEditContent).toBe(true));
    act(() => result.current.setEditor((current) => ({ ...current, sourceYaml: "- hosts: local\n  tasks: []\n" })));
    await act(async () => { await result.current.workspace.saveDraftNow(); });
    await waitFor(() => expect(result.current.workspace.conflict?.serverDraft.version).toBe(3));

    act(() => result.current.workspace.acceptServerDraft());
    expect(result.current.editor.sourceYaml).toBe(serverDraft.source_yaml);
    expect(result.current.workspace.conflict).toBeNull();
  });

  it("stops retrying a failed autosave until the content changes or the user retries", async () => {
    vi.mocked(updatePlaybookDraft).mockRejectedValueOnce(new Error("Service unavailable"));
    const detail = playbook();
    const { result } = renderHook(() => {
      const [editor, setEditor] = useState(() => detailToPlaybookEditor(detail));
      const workspace = usePlaybookWorkspaceVersioning({
        enabled: true,
        playbookId: detail.id,
        playbook: detail,
        editor,
        setEditor,
        tr: (_ru, en) => en,
      });
      return { setEditor, workspace };
    }, { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.workspace.canEditContent).toBe(true));
    const changedSource = "- hosts: failed-once\n  tasks: []\n";
    act(() => result.current.setEditor((current) => ({ ...current, sourceYaml: changedSource })));
    await act(async () => { await result.current.workspace.saveDraftNow(); });

    expect(result.current.workspace.autosaveStatus).toBe("error");
    expect(updatePlaybookDraft).toHaveBeenCalledTimes(1);
    await act(async () => { await new Promise((resolve) => window.setTimeout(resolve, 1_050)); });
    expect(updatePlaybookDraft).toHaveBeenCalledTimes(1);

    vi.mocked(updatePlaybookDraft).mockResolvedValueOnce({
      success: true,
      draft: draft({ version: 2, content_hash: "retry-hash", source_yaml: changedSource }),
    });
    await act(async () => { await result.current.workspace.retryDraftSave(); });
    expect(updatePlaybookDraft).toHaveBeenCalledTimes(2);
    expect(result.current.workspace.autosaveStatus).toBe("saved");
  });
});
