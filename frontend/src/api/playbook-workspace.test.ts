import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "@/lib/api";
import {
  createPlaybookBinding,
  createPlaybookRevision,
  createPlaybookShare,
  deletePlaybookBinding,
  deletePlaybookShare,
  getPlaybookDraft,
  listPlaybookBindings,
  listPlaybookRevisions,
  listPlaybookShares,
  publishPlaybookRevision,
  rollbackPlaybookRevision,
  updatePlaybookBinding,
  updatePlaybookDraft,
} from "./playbook-workspace";

vi.mock("@/lib/api", () => ({ apiFetch: vi.fn(async () => ({ success: true })) }));

describe("playbook workspace API", () => {
  beforeEach(() => vi.mocked(apiFetch).mockClear());

  it("uses expected_version for draft autosave", async () => {
    await getPlaybookDraft(7);
    await updatePlaybookDraft(7, {
      expected_version: 3,
      content_format: "ansible_yaml",
      source_yaml: "- hosts: all\n",
    });

    expect(apiFetch).toHaveBeenNthCalledWith(1, "/servers/api/playbooks/7/draft/");
    expect(apiFetch).toHaveBeenNthCalledWith(2, "/servers/api/playbooks/7/draft/", {
      method: "PUT",
      body: JSON.stringify({
        expected_version: 3,
        content_format: "ansible_yaml",
        source_yaml: "- hosts: all\n",
      }),
    });
  });

  it("maps revision create, publish, and rollback endpoints", async () => {
    await listPlaybookRevisions(7);
    await createPlaybookRevision(7, { expected_version: 4, message: "Reviewed" });
    await publishPlaybookRevision(7, 12);
    await rollbackPlaybookRevision(7, 8, { message: "Restore stable" });

    expect(apiFetch).toHaveBeenNthCalledWith(1, "/servers/api/playbooks/7/revisions/");
    expect(apiFetch).toHaveBeenNthCalledWith(2, "/servers/api/playbooks/7/revisions/", {
      method: "POST",
      body: JSON.stringify({ expected_version: 4, message: "Reviewed" }),
    });
    expect(apiFetch).toHaveBeenNthCalledWith(3, "/servers/api/playbooks/7/revisions/12/publish/", {
      method: "POST",
      body: "{}",
    });
    expect(apiFetch).toHaveBeenNthCalledWith(4, "/servers/api/playbooks/7/revisions/8/rollback/", {
      method: "POST",
      body: JSON.stringify({ message: "Restore stable" }),
    });
  });

  it("maps viewer-owned binding CRUD without a secret read endpoint", async () => {
    const payload = {
      name: "Production",
      selector_mappings: { web: { server_ids: [1], group_ids: [] } },
      variable_values: { release: "2026.07" },
      secret_values: { deploy_token: "write-only" },
    };
    await listPlaybookBindings(7);
    await createPlaybookBinding(7, payload);
    await updatePlaybookBinding(7, 3, { ...payload, expected_version: 2 });
    await deletePlaybookBinding(7, 3);

    expect(apiFetch).toHaveBeenNthCalledWith(1, "/servers/api/playbooks/7/bindings/");
    expect(apiFetch).toHaveBeenNthCalledWith(2, "/servers/api/playbooks/7/bindings/", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    expect(apiFetch).toHaveBeenNthCalledWith(3, "/servers/api/playbooks/7/bindings/3/", {
      method: "PATCH",
      body: JSON.stringify({ ...payload, expected_version: 2 }),
    });
    expect(apiFetch).toHaveBeenNthCalledWith(4, "/servers/api/playbooks/7/bindings/3/", {
      method: "DELETE",
      body: "{}",
    });
  });

  it("maps user/group/workspace sharing and revocation", async () => {
    await listPlaybookShares(7);
    await createPlaybookShare(7, { principal_type: "group", principal_id: 9, role: "operator" });
    await deletePlaybookShare(7, 4);

    expect(apiFetch).toHaveBeenNthCalledWith(1, "/servers/api/playbooks/7/shares/");
    expect(apiFetch).toHaveBeenNthCalledWith(2, "/servers/api/playbooks/7/shares/", {
      method: "POST",
      body: JSON.stringify({ principal_type: "group", principal_id: 9, role: "operator" }),
    });
    expect(apiFetch).toHaveBeenNthCalledWith(3, "/servers/api/playbooks/7/shares/4/", {
      method: "DELETE",
      body: "{}",
    });
  });
});
