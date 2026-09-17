import { describe, expect, it } from "vitest";

import { getWsUrl } from "@/lib/api";

describe("terminal WebSocket URL security", () => {
  it("never embeds a bearer token argument in the URL", () => {
    const urlBuilder = getWsUrl as unknown as (serverId: number, bearerToken: string) => string;
    const url = urlBuilder(42, "bearer-secret-from-url");

    expect(url).not.toContain("bearer-secret-from-url");
    expect(url).not.toContain("ws_token");
    expect(new URL(url).search).toBe("");
  });
});
