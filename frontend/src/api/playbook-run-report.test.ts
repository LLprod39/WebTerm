import { afterEach, describe, expect, it, vi } from "vitest";

import {
  downloadPlaybookRunReport,
  getPlaybookRunReport,
  type PlaybookRunReport,
} from "./playbook-run-report";

describe("playbook run report API", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("reuses the cached redacted report on ETag 304 polling responses", async () => {
    const report = {
      schema_version: 2,
      run: { id: 9123, status: "running", playbook_name: "Deploy" },
      progress: { is_terminal: false, state_version: 4 },
      summary: {},
      failure: null,
      hosts: [],
      dispatch: null,
      log: {},
      actions: {},
    } as unknown as PlaybookRunReport;
    const fetchMock = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response(JSON.stringify({ success: true, report }), {
        status: 200,
        headers: { "Content-Type": "application/json", ETag: '"state-4"' },
      }))
      .mockResolvedValueOnce(new Response(null, { status: 304 }));

    const first = await getPlaybookRunReport(9123);
    const second = await getPlaybookRunReport(9123);

    expect(first.report).toEqual(report);
    expect(second.report).toEqual(report);
    expect(fetchMock).toHaveBeenNthCalledWith(2, "/servers/api/playbooks/runs/9123/report/", {
      credentials: "include",
      headers: { "If-None-Match": '"state-4"' },
    });
  });

  it("attaches the export anchor before clicking and removes it afterwards", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(new Blob(["zip-bytes"], { type: "application/zip" }), { status: 200 }),
    );
    const createObjectURL = vi.fn(() => "blob:run-report");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);

    await downloadPlaybookRunReport(9123);

    expect(click).toHaveBeenCalledTimes(1);
    const link = click.mock.instances[0];
    expect(link.download).toBe("ansible-run-9123-report.zip");
    expect(link.isConnected).toBe(false);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:run-report");
  });
});
