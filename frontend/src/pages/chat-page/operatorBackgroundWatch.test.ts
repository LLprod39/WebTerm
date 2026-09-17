import { describe, expect, it } from "vitest";

import { previewOperatorReply } from "./operatorBackgroundWatch";

describe("previewOperatorReply", () => {
  it("keeps short replies intact", () => {
    expect(previewOperatorReply("Список серверов готов.")).toBe("Список серверов готов.");
  });

  it("truncates long replies with an ellipsis", () => {
    const long = "А".repeat(200);
    const preview = previewOperatorReply(long, 40);
    expect(preview.endsWith("…")).toBe(true);
    expect(preview.length).toBeLessThanOrEqual(40);
  });
});
