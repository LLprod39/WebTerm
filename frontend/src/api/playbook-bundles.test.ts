import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "@/lib/api";
import {
  commitPlaybookBundle,
  exportPlaybookRevisionBundle,
  isSupportedPlaybookBundleFile,
  previewPlaybookBundle,
} from "./playbook-bundles";

vi.mock("@/lib/api", () => ({ apiFetch: vi.fn(async () => ({ success: true })) }));

describe("playbook bundle API", () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockClear();
    vi.restoreAllMocks();
  });

  it("accepts only supported project archive names", () => {
    expect(isSupportedPlaybookBundleFile("project.zip")).toBe(true);
    expect(isSupportedPlaybookBundleFile("project.TAR")).toBe(true);
    expect(isSupportedPlaybookBundleFile("project.tar.gz")).toBe(true);
    expect(isSupportedPlaybookBundleFile("playbook.yml")).toBe(false);
    expect(isSupportedPlaybookBundleFile("archive.gz")).toBe(false);
  });

  it("uploads the raw archive for preview without reading file contents in the client", async () => {
    const file = new File(["archive"], "project.zip", { type: "application/zip" });

    await previewPlaybookBundle(file);

    expect(apiFetch).toHaveBeenCalledTimes(1);
    const [path, options] = vi.mocked(apiFetch).mock.calls[0];
    expect(path).toBe("/servers/api/playbooks/import/preview/");
    expect(options?.method).toBe("POST");
    expect(options?.body).toBeInstanceOf(FormData);
    expect((options?.body as FormData).get("bundle")).toBe(file);
    expect((options?.body as FormData).has("entrypoint")).toBe(false);
  });

  it("sends the selected entrypoint and explicit commit metadata", async () => {
    const file = new File(["archive"], "project.tar.gz", { type: "application/gzip" });

    await commitPlaybookBundle(file, {
      entrypoint: "site.yml",
      name: " Web deploy ",
      description: " Production project ",
      category: "deploy",
      visibility: "shared",
      tags: ["nginx", "production"],
    });

    const [path, options] = vi.mocked(apiFetch).mock.calls[0];
    const form = options?.body as FormData;
    expect(path).toBe("/servers/api/playbooks/import/commit/");
    expect(options?.method).toBe("POST");
    expect(form.get("bundle")).toBe(file);
    expect(form.get("entrypoint")).toBe("site.yml");
    expect(form.get("name")).toBe("Web deploy");
    expect(form.get("description")).toBe("Production project");
    expect(form.get("category")).toBe("deploy");
    expect(form.get("visibility")).toBe("shared");
    expect(form.get("tags")).toBe('["nginx","production"]');
  });

  it("downloads the exact published revision and preserves export metadata", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(new Blob(["zip-bytes"], { type: "application/zip" }), {
        status: 200,
        headers: {
          "Content-Type": "application/zip",
          "Content-Disposition": 'attachment; filename="web-deploy-r4.zip"',
          "X-Playbook-Redactions": "2",
        },
      }),
    );

    const result = await exportPlaybookRevisionBundle(7, 14);

    expect(fetchMock).toHaveBeenCalledWith(
      "/servers/api/playbooks/7/revisions/14/export/",
      { credentials: "include" },
    );
    expect(result.filename).toBe("web-deploy-r4.zip");
    expect(result.redactionCount).toBe(2);
    expect(result.blob.type).toBe("application/zip");
  });

  it("surfaces the backend export error instead of downloading an error body", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ error: "Export is not allowed" }), {
        status: 403,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(exportPlaybookRevisionBundle(7, 14)).rejects.toThrow("Export is not allowed");
  });
});
