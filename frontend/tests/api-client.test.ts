import { beforeEach, afterEach, describe, it, expect, vi } from "vitest";
import { api, ApiError, clearCsrf, downloadFile } from "@/api/client";
function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
describe("authenticated API boundary", () => {
  beforeEach(() => clearCsrf());
  afterEach(() => vi.unstubAllGlobals());
  it("reports a rejected login without expiring a session that has not started", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (path: string) =>
        path.includes("/csrf/")
          ? json({ csrfToken: "qa" })
          : json({ error: "Invalid credentials" }, 401),
      ),
    );
    const listener = vi.fn();
    window.addEventListener("webterm:session-expired", listener);
    try {
      await expect(api.post("/api/auth/login/", {})).rejects.toMatchObject({
        status: 401,
        message:
          "Неверный логин или пароль. Проверьте данные и повторите вход.",
      });
      expect(listener).not.toHaveBeenCalled();
    } finally {
      window.removeEventListener("webterm:session-expired", listener);
    }
  });
  it("obtains CSRF once and sends it with credentials on parallel mutations", async () => {
    const calls: { path: string; options: RequestInit }[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (path: string, options: RequestInit) => {
        calls.push({ path, options });
        return path.includes("/csrf/")
          ? json({ csrfToken: "test-csrf" })
          : json({ success: true });
      }),
    );
    await Promise.all([
      api.post("/first/", { name: "one" }),
      api.patch("/second/", { name: "two" }),
    ]);
    expect(calls.filter((c) => c.path.includes("/csrf/"))).toHaveLength(1);
    for (const call of calls.filter((c) => !c.path.includes("/csrf/"))) {
      expect(new Headers(call.options.headers).get("X-CSRFToken")).toBe(
        "test-csrf",
      );
      expect(call.options.credentials).toBe("include");
    }
  });
  it("retains host key verification challenge even for HTTP 200 failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (path: string) =>
        path.includes("/csrf/")
          ? json({ csrfToken: "x" })
          : json({
              success: false,
              code: "host_key_confirmation_required",
              error: "Verify fingerprint",
              host_key: { fingerprint_sha256: "SHA256:verified" },
            }),
      ),
    );
    try {
      await api.post("/servers/api/1/test/");
      throw new Error("Expected rejection");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect((error as ApiError).details).toMatchObject({
        code: "host_key_confirmation_required",
        host_key: { fingerprint_sha256: "SHA256:verified" },
      });
    }
  });
  it("does not lose bare Studio arrays or envelope payload fields", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(json([{ id: "pipeline-1" }]))
        .mockResolvedValueOnce(json({ success: true, servers: [{ id: 1 }] })),
    );
    expect(await api.get("/api/studio/pipelines/")).toEqual([
      { id: "pipeline-1" },
    ]);
    expect(await api.get("/servers/api/frontend/bootstrap/")).toMatchObject({
      servers: [{ id: 1 }],
    });
  });
  it("unwraps normalized list responses while preserving object fields", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(
          json({ success: true, code: "ok", data: [{ id: 5 }] }),
        )
        .mockResolvedValueOnce(
          json({
            success: true,
            code: "ok",
            data: { value: 5 },
            message: "saved",
          }),
        ),
    );
    expect(await api.get("/list/")).toEqual([{ id: 5 }]);
    expect(await api.get("/object/")).toEqual({
      success: true,
      code: "ok",
      data: { value: 5 },
      message: "saved",
    });
  });
  it("treats an HTML login redirect as session expiry rather than JSON parsing failure", async () => {
    const response = new Response("<html>Login</html>", {
      headers: { "content-type": "text/html" },
    });
    Object.defineProperty(response, "redirected", { value: true });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
    const listener = vi.fn();
    window.addEventListener("webterm:session-expired", listener);
    await expect(api.get("/private/")).rejects.toMatchObject({ status: 401 });
    expect(listener).toHaveBeenCalledTimes(1);
    window.removeEventListener("webterm:session-expired", listener);
  });
  it("surfaces a denied operation and does not retry it", async () => {
    const fetcher = vi.fn(async () =>
      json({ error: "Missing server capability: write_files" }, 403),
    );
    vi.stubGlobal("fetch", fetcher);
    await expect(api.get("/private/")).rejects.toMatchObject({
      status: 403,
      message: "Missing server capability: write_files",
    });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it("downloads JSON attachments instead of interpreting the remote file as an API error", async () => {
    vi.useFakeTimers();
    const click = vi
      .spyOn(HTMLAnchorElement.prototype, "click")
      .mockImplementation(() => {});
    const createObjectURL = vi.fn(() => "blob:json-download");
    vi.stubGlobal(
      "URL",
      Object.assign(class extends URL {}, {
        createObjectURL,
        revokeObjectURL: vi.fn(),
      }),
    );
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response('{"configuration":true}', {
          headers: {
            "Content-Type": "application/json",
            "Content-Disposition": 'attachment; filename="config.json"',
          },
        }),
      ),
    );
    await downloadFile("/files/download/", "config.json");
    expect(createObjectURL).toHaveBeenCalledOnce();
    expect(click).toHaveBeenCalledOnce();
    await vi.runAllTimersAsync();
    vi.useRealTimers();
  });
  it("expires authentication on a denied download without starting a file", async () => {
    const listener = vi.fn();
    window.addEventListener("webterm:session-expired", listener);
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(json({ error: "Authentication required" }, 401)),
    );
    await expect(
      downloadFile("/files/download/", "config.json"),
    ).rejects.toMatchObject({ status: 401 });
    expect(listener).toHaveBeenCalledOnce();
    window.removeEventListener("webterm:session-expired", listener);
  });
});
