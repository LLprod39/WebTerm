import { describe, expect, it } from "vitest";

import { extractPinnedServersFromMentions, parseOperatorCompose } from "./operatorCompose";

describe("parseOperatorCompose", () => {
  it("expands /fleet slash", () => {
    const parsed = parseOperatorCompose("/fleet");
    expect(parsed.slash).toBe("fleet");
    expect(parsed.message.toLowerCase()).toContain("флот");
  });

  it("expands /run with command", () => {
    const parsed = parseOperatorCompose("/run df -h");
    expect(parsed.slash).toBe("run");
    expect(parsed.message).toContain("df -h");
  });

  it("collects @mentions", () => {
    const parsed = parseOperatorCompose("check @db-01 and @web-02 please");
    expect(parsed.mentions).toEqual(["db-01", "web-02"]);
  });

  it("attaches mentions to slash templates", () => {
    const parsed = parseOperatorCompose("/forecasts @db-01");
    expect(parsed.mentions).toContain("db-01");
    expect(parsed.message).toContain("@db-01");
  });
});

describe("extractPinnedServersFromMentions", () => {
  it("matches inventory by name case-insensitively", () => {
    const pinned = extractPinnedServersFromMentions(
      ["Db-01", "missing"],
      [
        { id: 1, name: "db-01" },
        { id: 2, name: "web" },
      ],
    );
    expect(pinned).toEqual([{ id: 1, name: "db-01" }]);
  });
});
