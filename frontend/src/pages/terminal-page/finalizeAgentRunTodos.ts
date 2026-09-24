import type { AgentTodo, AiMessage } from "@/components/terminal/ai-types";

type TerminalTodoStatus = AgentTodo["status"];

/**
 * When the Nova run ends without a final todo_write, open items stay
 * forever on the sticky checklist. Close them so the UI matches reality.
 */
export function finalizeAgentRunTodos(
  messages: AiMessage[],
  fillStatus: Extract<TerminalTodoStatus, "completed" | "cancelled">,
): AiMessage[] {
  let startIdx = -1;
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    if (messages[i].type === "agent_start") {
      startIdx = i;
      break;
    }
  }
  if (startIdx < 0) return messages;

  const todoIdx = messages.findIndex(
    (message, idx) => message.type === "agent_todo" && idx > startIdx,
  );
  if (todoIdx < 0) return messages;

  const todos = messages[todoIdx].agentTodos;
  if (!todos?.length) return messages;

  const needsFinalize = todos.some(
    (todo) => todo.status === "pending" || todo.status === "in_progress",
  );
  if (!needsFinalize) return messages;

  const updated = [...messages];
  updated[todoIdx] = {
    ...messages[todoIdx],
    agentTodos: todos.map((todo) =>
      todo.status === "pending" || todo.status === "in_progress"
        ? { ...todo, status: fillStatus }
        : todo,
    ),
  };
  return updated;
}
