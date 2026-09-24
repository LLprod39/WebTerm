import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { I18nProvider } from "@/lib/i18n";

import { AgentTodoMsg } from "./AgentTimelineMessages";
import type { AiMessage } from "../ai-types";

const todoMsg: AiMessage = {
  id: "todo-1",
  role: "assistant",
  type: "agent_todo",
  content: "",
  agentTodos: [
    { id: "1", content: "List containers", status: "completed" },
    { id: "2", content: "Inspect logs", status: "in_progress" },
    { id: "3", content: "Summarize errors", status: "pending" },
  ],
};

describe("AgentTodoMsg", () => {
  it("is expanded by default and can collapse", () => {
    render(
      <I18nProvider>
        <AgentTodoMsg msg={todoMsg} />
      </I18nProvider>,
    );

    expect(screen.getByText("List containers")).toBeInTheDocument();
    expect(screen.getByText("Inspect logs")).toBeInTheDocument();

    const toggle = screen.getByRole("button", { name: /Задачи/i });
    expect(toggle).toHaveAttribute("aria-expanded", "true");

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("List containers")).not.toBeInTheDocument();
    // Collapsed strip keeps current step preview.
    expect(screen.getByText("Inspect logs")).toBeInTheDocument();
  });
});
