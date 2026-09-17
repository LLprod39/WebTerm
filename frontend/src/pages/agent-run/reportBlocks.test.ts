import { describe, expect, it } from "vitest";

import {
  normalizeReportBlocks,
  parseReportBlocksFromMarkdown,
  stripReportBlocksFence,
} from "./reportBlocks";

describe("reportBlocks", () => {
  it("normalizes known blocks and drops empty/unknown", () => {
    const blocks = normalizeReportBlocks([
      { type: "verdict", text: "Ок" },
      { type: "unknown_widget", text: "x" },
      { type: "bars", items: [] },
      { type: "chart", series: [1, 2, 3], title: "Load" },
    ]);
    expect(blocks.map((b) => b.type)).toEqual(["verdict", "chart"]);
  });

  it("parses report-blocks fence from markdown", () => {
    const md = `# Title\n\n\`\`\`report-blocks\n[{"type":"before_after","before":{"value":"4%"},"after":{"value":"19%"}}]\n\`\`\`\n\nBody`;
    expect(parseReportBlocksFromMarkdown(md)).toHaveLength(1);
    expect(stripReportBlocksFence(md)).toContain("Body");
    expect(stripReportBlocksFence(md)).not.toContain("report-blocks");
  });
});
