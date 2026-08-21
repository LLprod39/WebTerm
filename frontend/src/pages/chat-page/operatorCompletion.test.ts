import { describe, expect, it } from "vitest";

import { shouldReconcileOperatorCompletion } from "./useChatPageOperatorRuntime";

const assistant = {
  id: 2,
  role: "assistant" as const,
  content: "Grounded playbook summary",
  metadata: {},
  created_at: "2026-08-20T18:25:06Z",
};

describe("operator completion reconciliation", () => {
  it("ends local writing when a previously open REST turn is durably closed", () => {
    expect(shouldReconcileOperatorCompletion({
      restTurnWasOpen: true,
      operatorBusy: true,
      activeTurn: null,
      lastMessage: assistant,
    })).toBe(true);
  });

  it("does not end a genuinely running turn or a turn without final text", () => {
    expect(shouldReconcileOperatorCompletion({
      restTurnWasOpen: true,
      operatorBusy: true,
      activeTurn: { turn_id: 8, status: "running", busy: true },
      lastMessage: assistant,
    })).toBe(false);
    expect(shouldReconcileOperatorCompletion({
      restTurnWasOpen: false,
      operatorBusy: true,
      activeTurn: null,
      lastMessage: undefined,
    })).toBe(false);
  });
});
