import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  createPlaybookRevision,
  getPlaybookDraft,
  listPlaybookRevisions,
  publishPlaybookRevision,
} from "@/api/playbook-workspace";
import { ensurePlaybookPublishedForRun } from "./ensurePlaybookPublishedForRun";

vi.mock("@/api/playbook-workspace", () => ({
  getPlaybookDraft: vi.fn(),
  listPlaybookRevisions: vi.fn(),
  createPlaybookRevision: vi.fn(),
  publishPlaybookRevision: vi.fn(),
}));

describe("ensurePlaybookPublishedForRun", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("returns existing published revision when draft matches", async () => {
    vi.mocked(listPlaybookRevisions).mockResolvedValue({
      success: true,
      published_revision_id: 10,
      revisions: [{ id: 10, revision_number: 1, content_hash: "abc", message: "", content_format: "ansible_yaml", created_at: null, compatibility: null } as never],
    });
    vi.mocked(getPlaybookDraft).mockResolvedValue({
      success: true,
      draft: { id: 1, version: 2, content_hash: "abc", base_revision_id: 10 } as never,
    });

    await expect(ensurePlaybookPublishedForRun(7)).resolves.toBe(10);
    expect(createPlaybookRevision).not.toHaveBeenCalled();
    expect(publishPlaybookRevision).not.toHaveBeenCalled();
  });

  it("creates and publishes when draft has unrevisioned changes", async () => {
    vi.mocked(listPlaybookRevisions).mockResolvedValue({
      success: true,
      published_revision_id: 10,
      revisions: [{ id: 10, revision_number: 1, content_hash: "old", message: "", content_format: "ansible_yaml", created_at: null, compatibility: null } as never],
    });
    vi.mocked(getPlaybookDraft).mockResolvedValue({
      success: true,
      draft: { id: 1, version: 3, content_hash: "new", base_revision_id: 10 } as never,
    });
    vi.mocked(createPlaybookRevision).mockResolvedValue({
      success: true,
      revision: { id: 11, revision_number: 2, content_hash: "new" } as never,
    });
    vi.mocked(publishPlaybookRevision).mockResolvedValue({
      success: true,
      published_revision_id: 11,
      revision: { id: 11 } as never,
    });

    await expect(ensurePlaybookPublishedForRun(7)).resolves.toBe(11);
    expect(createPlaybookRevision).toHaveBeenCalledWith(7, { expected_version: 3, message: "Prepared for run" });
    expect(publishPlaybookRevision).toHaveBeenCalledWith(7, 11);
  });
});
