import { describe, expect, it } from "vitest";

import type { AssistantChatMessage } from "@/api";

import type { PlanData } from "./PlanTasksPanel";
import { resolveActivePlan, sanitizePlanForIdleTurn } from "./useChatPageOperatorRuntime";

function msg(
  role: "user" | "assistant",
  id: number,
  plan?: PlanData,
): AssistantChatMessage {
  return {
    id,
    role,
    content: role === "user" ? "hi" : "ok",
    metadata: plan ? { plan } : {},
    created_at: "2026-10-07T00:00:00Z",
  };
}

describe("resolveActivePlan", () => {
  it("hides completed plans after a newer user message without a plan", () => {
    const completed: PlanData = {
      title: "Old",
      status: "completed",
      steps: [
        { id: 1, text: "A", status: "done" },
        { id: 2, text: "B", status: "done" },
      ],
    };
    const plan = resolveActivePlan({
      livePlan: null,
      messages: [msg("user", 1), msg("assistant", 2, completed), msg("user", 3)],
      turnActive: false,
    });
    expect(plan).toBeNull();
  });

  it("keeps an in-progress plan across messages until a newer user turn", () => {
    const running: PlanData = {
      title: "Work",
      status: "running",
      steps: [
        { id: 1, text: "A", status: "done" },
        { id: 2, text: "B", status: "pending" },
      ],
    };
    const plan = resolveActivePlan({
      livePlan: null,
      messages: [msg("user", 1), msg("assistant", 2, running)],
      turnActive: true,
    });
    expect(plan?.title).toBe("Work");
  });

  it("sanitizes stuck running when turn is idle", () => {
    const stuck: PlanData = {
      title: "Stuck",
      status: "running",
      steps: [{ id: 1, text: "Confirm", status: "running" }],
    };
    const plan = resolveActivePlan({
      livePlan: stuck,
      messages: [],
      turnActive: false,
    });
    expect(plan?.steps?.[0]?.status).toBe("awaiting_confirm");
  });

  it("prefers livePlan over message history", () => {
    const live: PlanData = {
      title: "Live",
      steps: [{ id: 1, text: "Now", status: "pending" }],
    };
    const old: PlanData = {
      title: "Old",
      status: "completed",
      steps: [{ id: 1, text: "Done", status: "done" }],
    };
    const plan = resolveActivePlan({
      livePlan: live,
      messages: [msg("assistant", 1, old)],
      turnActive: true,
    });
    expect(plan?.title).toBe("Live");
  });
});

describe("sanitizePlanForIdleTurn", () => {
  it("leaves running intact while the turn is active", () => {
    const plan: PlanData = {
      steps: [{ id: 1, text: "Go", status: "running" }],
    };
    expect(sanitizePlanForIdleTurn(plan, true).steps?.[0]?.status).toBe("running");
  });
});
