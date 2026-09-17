import { describe, expect, it } from "vitest";

import { detectComposeTrigger, filterSlashCommands, replaceComposeRange } from "./composeCommands";

describe("composeCommands", () => {
  it("filters slash commands by query", () => {
    const hits = filterSlashCommands("serv");
    expect(hits.some((c) => c.trigger === "servers")).toBe(true);
  });

  it("detects slash trigger at caret", () => {
    const t = detectComposeTrigger("/serv", 5);
    expect(t?.type).toBe("slash");
    expect(t?.query).toBe("serv");
  });

  it("detects @ mention trigger", () => {
    const t = detectComposeTrigger("hello @db", 9);
    expect(t?.type).toBe("mention");
    expect(t?.query).toBe("db");
  });

  it("replaces compose range", () => {
    expect(replaceComposeRange("/fleet rest", 0, 6, "MSG")).toBe("MSG rest");
  });
});
