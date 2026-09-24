import { describe, expect, it } from "vitest";

import type { AiMessage } from "@/components/terminal/ai-types";

import { finalizeAgentRunTodos } from "./finalizeAgentRunTodos";

function msg(partial: Partial<AiMessage> & Pick<AiMessage, "id" | "type">): AiMessage {
  return {
    role: "assistant",
    content: "",
    ...partial,
  };
}

describe("finalizeAgentRunTodos", () => {
  it("marks open todos completed on successful agent_done", () => {
    const messages: AiMessage[] = [
      msg({ id: "1", type: "agent_start" }),
      msg({
        id: "2",
        type: "agent_todo",
        agentTodos: [
          { id: "a", content: "list", status: "completed" },
          { id: "b", content: "logs", status: "in_progress" },
          { id: "c", content: "report", status: "pending" },
        ],
      }),
      msg({ id: "3", type: "text", content: "done" }),
    ];

    const next = finalizeAgentRunTodos(messages, "completed");
    expect(next[1].agentTodos?.map((t) => t.status)).toEqual([
      "completed",
      "completed",
      "completed",
    ]);
  });

  it("cancels open todos on stop/error", () => {
    const messages: AiMessage[] = [
      msg({ id: "1", type: "agent_start" }),
      msg({
        id: "2",
        type: "agent_todo",
        agentTodos: [
          { id: "a", content: "one", status: "in_progress" },
          { id: "b", content: "two", status: "pending" },
        ],
      }),
    ];

    const next = finalizeAgentRunTodos(messages, "cancelled");
    expect(next[1].agentTodos?.map((t) => t.status)).toEqual(["cancelled", "cancelled"]);
  });

  it("leaves an already-finished checklist unchanged", () => {
    const messages: AiMessage[] = [
      msg({ id: "1", type: "agent_start" }),
      msg({
        id: "2",
        type: "agent_todo",
        agentTodos: [{ id: "a", content: "one", status: "completed" }],
      }),
    ];
    expect(finalizeAgentRunTodos(messages, "completed")).toBe(messages);
  });
});
