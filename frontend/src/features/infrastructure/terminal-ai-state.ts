import type {
  TerminalAiCommand,
  TerminalAiEvent,
  TerminalAiQuestion,
} from "@/api/terminal-ai";
export interface AiMessage {
  id: number;
  role: "user" | "assistant";
  text: string;
}
export interface AiTool {
  iteration: number;
  tool: string;
  args: Record<string, unknown>;
  status: string;
  output?: string;
  error?: string;
  data?: Record<string, unknown>;
}
export interface TerminalAiState {
  messages: AiMessage[];
  commands: TerminalAiCommand[];
  tools: AiTool[];
  todos: NonNullable<TerminalAiEvent["todos"]>;
  question: TerminalAiQuestion | null;
  awaitingCommandId: number | null;
  status: string;
  error: string;
  report: string;
  reportStatus: string;
  runId: string | null;
  priorRunId: string | null;
  awaitingRun: boolean;
  restoredCount: number;
  clearPending: boolean;
  progress: string;
}
export const initialTerminalAiState: TerminalAiState = {
  messages: [],
  commands: [],
  tools: [],
  todos: [],
  question: null,
  awaitingCommandId: null,
  status: "idle",
  error: "",
  report: "",
  reportStatus: "",
  runId: null,
  priorRunId: null,
  awaitingRun: false,
  restoredCount: 0,
  clearPending: false,
  progress: "",
};
export type AiAction =
  | { type: "event"; event: TerminalAiEvent }
  | { type: "request"; message: string }
  | { type: "error"; message: string }
  | { type: "reply" }
  | { type: "clear-memory" }
  | { type: "stopping" }
  | { type: "command-sent"; id: number; action: "confirm" | "cancel" };
function appendMessage(
  messages: AiMessage[],
  role: AiMessage["role"],
  text?: string,
) {
  if (
    !text?.trim() ||
    (role === "assistant" &&
      messages.at(-1)?.role === "assistant" &&
      messages.at(-1)?.text === text)
  )
    return messages;
  return [
    ...messages,
    { id: (messages.at(-1)?.id ?? 0) + 1, role, text: text.slice(0, 40000) },
  ].slice(-80);
}
function commandUpdate(
  commands: TerminalAiCommand[],
  id: number,
  patch: Partial<TerminalAiCommand>,
) {
  const previous = commands.find((command) => command.id === id);
  const updated = {
    id,
    cmd: previous?.cmd ?? `Команда #${id}`,
    status: previous?.status ?? "pending",
    ...previous,
    ...patch,
  };
  return previous
    ? commands.map((command) => (command.id === id ? updated : command))
    : [...commands, updated].slice(-100);
}
export function terminalAiReducer(
  state: TerminalAiState,
  action: AiAction,
): TerminalAiState {
  if (action.type === "request")
    return {
      ...state,
      messages: appendMessage(state.messages, "user", action.message),
      commands: [],
      tools: [],
      todos: [],
      question: null,
      awaitingCommandId: null,
      status: "sending",
      error: "",
      report: "",
      progress: "",
      priorRunId: state.runId,
      runId: null,
      awaitingRun: true,
    };
  if (action.type === "error") return { ...state, error: action.message };
  if (action.type === "reply")
    return { ...state, question: null, status: "running" };
  if (action.type === "clear-memory")
    return { ...state, clearPending: true, error: "" };
  if (action.type === "stopping")
    return {
      ...state,
      status: "stopping",
      question: null,
      awaitingCommandId: null,
    };
  if (action.type === "command-sent")
    return {
      ...state,
      awaitingCommandId: null,
      commands: commandUpdate(state.commands, action.id, {
        status: action.action === "confirm" ? "confirming" : "cancelling",
      }),
    };
  const event = action.event;
  if (event.type === "ready")
    return {
      ...state,
      status: "idle",
      awaitingRun: false,
      restoredCount: event.restored_history_count ?? 0,
      question: null,
      awaitingCommandId: null,
    };
  if (event.type === "status" && event.status === "disconnected")
    return {
      ...state,
      status: "disconnected",
      question: null,
      awaitingCommandId: null,
      awaitingRun: false,
      error:
        state.status === "idle"
          ? ""
          : "Соединение потеряно. Проверьте состояние сервера перед новым запросом.",
    };
  if (
    event.run_id &&
    ((state.awaitingRun && event.run_id === state.priorRunId) ||
      (!state.awaitingRun && state.runId && event.run_id !== state.runId))
  )
    return state;
  let next = event.run_id
    ? { ...state, runId: event.run_id, awaitingRun: false }
    : state;
  switch (event.type) {
    case "ai_status":
      return {
        ...next,
        status: event.status ?? next.status,
        awaitingCommandId:
          event.status === "waiting_confirm"
            ? Number(event.id)
            : event.status === "idle"
              ? null
              : next.awaitingCommandId,
        question: event.status === "idle" ? null : next.question,
      };
    case "ai_error":
    case "agent_error":
      return {
        ...next,
        status: "error",
        error: event.message ?? event.error ?? "Не удалось выполнить запрос",
        clearPending: false,
      };
    case "ai_response": {
      if (next.clearPending)
        next = { ...initialTerminalAiState, runId: next.runId };
      let commands = next.commands;
      for (const command of event.commands ?? [])
        commands = commandUpdate(commands, command.id, command);
      return {
        ...next,
        messages: appendMessage(
          next.messages,
          "assistant",
          event.assistant_text,
        ),
        commands,
        clearPending: false,
      };
    }
    case "ai_command_status":
      return {
        ...next,
        commands: commandUpdate(next.commands, Number(event.id), {
          status: event.status ?? "pending",
          exit_code: event.exit_code,
          reason: event.reason,
          streaming: event.streaming,
        }),
      };
    case "ai_direct_output":
      return {
        ...next,
        commands: commandUpdate(next.commands, Number(event.id), {
          cmd: event.cmd,
          output: event.output?.slice(-50000),
          exit_code: event.exit_code,
          dry_run: event.dry_run,
        }),
      };
    case "ai_recovery":
      return {
        ...next,
        commands: commandUpdate(next.commands, event.new_id ?? 0, {
          cmd: event.new_cmd,
          why: event.why,
          requires_confirm: event.requires_confirm,
          reason: event.reason,
          status: "pending",
        }),
      };
    case "ai_question":
      return {
        ...next,
        status: "waiting_reply",
        question: {
          q_id: event.q_id ?? "",
          question: event.question ?? "",
          cmd: event.cmd,
          options: event.options,
          allow_multiple: event.allow_multiple,
          free_text_allowed: event.free_text_allowed,
          placeholder: event.placeholder,
        },
      };
    case "ai_report":
      return {
        ...next,
        report: event.report ?? "",
        reportStatus: event.status ?? "unknown",
      };
    case "ai_explanation": {
      const id = typeof event.id === "number" ? event.id : Number(event.id);
      return next.commands.some((command) => command.id === id)
        ? {
            ...next,
            commands: commandUpdate(next.commands, id, {
              explanation: event.explanation,
            }),
          }
        : {
            ...next,
            messages: appendMessage(
              next.messages,
              "assistant",
              event.explanation,
            ),
          };
    }
    case "ai_install_progress":
      return {
        ...next,
        progress: `${event.cmd ?? "Операция"} · ${event.elapsed ?? 0} сек`,
      };
    case "ai_parallel_batch":
      return {
        ...next,
        progress:
          event.status === "running"
            ? `Параллельное выполнение: ${event.count ?? event.ids?.length ?? 0} команд`
            : "",
      };
    case "agent_start":
      return { ...next, status: "running" };
    case "agent_thinking":
      return {
        ...next,
        progress: `Планирует шаг ${event.iteration ?? ""}`.trim(),
      };
    case "agent_tool_call":
      return {
        ...next,
        status: "running",
        tools: [
          ...next.tools,
          {
            iteration: event.iteration ?? 0,
            tool: event.tool ?? "Инструмент",
            args: event.args ?? {},
            status: "running",
          },
        ].slice(-100),
      };
    case "agent_tool_result":
      return {
        ...next,
        tools: next.tools.map((tool) =>
          tool.iteration === event.iteration && tool.tool === event.tool
            ? {
                ...tool,
                status: event.ok ? "completed" : "failed",
                output: event.output,
                error: event.error,
                data: event.data,
              }
            : tool,
        ),
      };
    case "agent_todo_update":
      return { ...next, todos: event.todos ?? [] };
    case "agent_done":
    case "agent_stopped":
      return {
        ...next,
        status: "idle",
        question: null,
        awaitingCommandId: null,
        messages: appendMessage(next.messages, "assistant", event.final_text),
        progress: `${event.iterations ?? 0} шагов · ${event.tool_calls ?? 0} вызовов${event.type === "agent_stopped" ? ` · остановлено: ${event.reason ?? "прервано"}` : ""}`,
      };
    default:
      return next;
  }
}
