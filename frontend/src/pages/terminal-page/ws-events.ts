import type { MutableRefObject } from "react";

import type { AiCommand, AiMessage } from "@/components/terminal/ai-types";
import { parseAiQuestionPayload } from "@/components/terminal/ai-question";
import { parseNovaContextPayload } from "@/components/terminal/nova-context";

import { nextId, type TabAiState } from "./model";

type UpdateTabAiState = (tabId: string, updater: (state: TabAiState) => TabAiState) => void;

export function handleTerminalPageWsEvent({
  tabId,
  serverId,
  payload,
  handleEditorWsEvent,
  getTabCwdRef,
  revealAiPanelForTab,
  updateTabAiState,
}: {
  tabId: string;
  serverId: number;
  payload: Record<string, unknown>;
  handleEditorWsEvent: (serverId: number, payload: Record<string, unknown>) => boolean;
  getTabCwdRef: (tabId: string) => MutableRefObject<string>;
  revealAiPanelForTab: (tabId: string) => void;
  updateTabAiState: UpdateTabAiState;
}) {
  if (handleEditorWsEvent(serverId, payload)) return;

  const type = String(payload.type || "");

  if (type === "terminal_session") {
    const cwd = String(payload.cwd || "").trim();
    if (cwd) {
      getTabCwdRef(tabId).current = cwd;
    }
    return;
  }

  if (type === "ai_status") {
    const status = String(payload.status || "");
    updateTabAiState(tabId, (state) => ({
      ...state,
      isGenerating: status === "thinking" || status === "running" || status === "generating_report",
    }));
    return;
  }

  if (type === "ai_response") {
    const text = String(payload.assistant_text || payload.message || "");
    const mode = String(payload.mode || "answer") as AiMessage["mode"];
    const rawCommands = (payload.commands as AiCommand[] | undefined) || [];

    revealAiPanelForTab(tabId);
    updateTabAiState(tabId, (state) => ({
      ...state,
      messages: [
        ...state.messages,
        {
          id: nextId(),
          role: "assistant",
          type: rawCommands.length > 0 ? "commands" : "text",
          content: text,
          commands: rawCommands.map((command) => ({
            ...command,
            status: (command.status || "pending") as AiCommand["status"],
          })),
          mode,
        },
      ],
    }));
    return;
  }

  if (type === "ai_command_status") {
    const cmdId = Number(payload.id);
    const status = String(payload.status || "done") as AiCommand["status"];
    const exitCode = payload.exit_code !== undefined ? Number(payload.exit_code) : undefined;

    updateTabAiState(tabId, (state) => ({
      ...state,
      messages: state.messages.map((message) => {
        if (message.type !== "commands" || !message.commands?.some((command) => command.id === cmdId)) return message;
        return {
          ...message,
          commands: message.commands.map((command) =>
            command.id === cmdId ? { ...command, status, exit_code: exitCode } : command,
          ),
        };
      }),
    }));
    return;
  }

  if (type === "ai_direct_output") {
    const cmdId = Number(payload.id);
    const directOutput = String(payload.output || "");
    const exitCode = payload.exit_code !== undefined ? Number(payload.exit_code) : undefined;

    updateTabAiState(tabId, (state) => ({
      ...state,
      messages: state.messages.map((message) => {
        if (message.type !== "commands" || !message.commands?.some((command) => command.id === cmdId)) return message;
        return {
          ...message,
          commands: message.commands.map((command) =>
            command.id === cmdId
              ? { ...command, direct_output: directOutput, exit_code: exitCode ?? command.exit_code }
              : command,
          ),
        };
      }),
    }));
    return;
  }

  if (type === "ai_explanation") {
    const cmdId = Number(payload.id);
    const explanation = String(payload.explanation || "");
    updateTabAiState(tabId, (state) => ({
      ...state,
      messages: state.messages.map((message) => {
        if (message.type !== "commands" || !message.commands?.some((c) => c.id === cmdId)) return message;
        return {
          ...message,
          commands: message.commands.map((c) =>
            c.id === cmdId ? { ...c, explanation, explaining: false } : c,
          ),
        };
      }),
    }));
    return;
  }

  if (type === "ai_report") {
    const report = String(payload.report || "");
    const reportStatus = String(payload.status || "ok") as AiMessage["reportStatus"];
    if (!report) return;

    revealAiPanelForTab(tabId);
    updateTabAiState(tabId, (state) => ({
      ...state,
      messages: [
        ...state.messages,
        { id: nextId(), role: "assistant", type: "report", content: report, reportStatus },
      ],
    }));
    return;
  }

  if (type === "ai_question") {
    const questionPayload = parseAiQuestionPayload(payload);

    revealAiPanelForTab(tabId);
    updateTabAiState(tabId, (state) => ({
      ...state,
      messages: [
        ...state.messages,
        {
          id: nextId(),
          role: "system",
          type: "question",
          content: questionPayload.question,
          qId: questionPayload.qId,
          question: questionPayload.question,
          questionCmd: questionPayload.cmd,
          questionExitCode: questionPayload.exitCode,
          questionOptions: questionPayload.options,
          questionAllowMultiple: questionPayload.allowMultiple,
          questionFreeTextAllowed: questionPayload.freeTextAllowed,
          questionPlaceholder: questionPayload.placeholder,
          questionSource: questionPayload.source,
          questionAnswered: false,
        },
      ],
    }));
    return;
  }

  if (type === "ai_install_progress") {
    const cmd = String(payload.cmd || "");
    const elapsed = Number(payload.elapsed || 0);
    const outputTail = String(payload.output_tail || "");

    revealAiPanelForTab(tabId);
    updateTabAiState(tabId, (state) => {
      let found = false;
      const updated = state.messages.map((message) => {
        if (message.type === "progress" && message.progressCmd === cmd) {
          found = true;
          return { ...message, progressElapsed: elapsed, progressTail: outputTail };
        }
        return message;
      });

      return {
        ...state,
        messages: found
          ? updated
          : [
              ...updated,
              {
                id: nextId(),
                role: "system",
                type: "progress",
                content: cmd,
                progressCmd: cmd,
                progressElapsed: elapsed,
                progressTail: outputTail,
              },
            ],
      };
    });
    return;
  }

  if (type === "ai_recovery") {
    revealAiPanelForTab(tabId);
    updateTabAiState(tabId, (state) => ({
      ...state,
      messages: [
        ...state.messages,
        {
          id: nextId(),
          role: "system",
          type: "recovery",
          content: String(payload.why || ""),
          recoveryOriginal: String(payload.original_cmd || ""),
          recoveryNew: String(payload.new_cmd || ""),
          recoveryWhy: String(payload.why || ""),
        },
      ],
    }));
    return;
  }

  if (type === "agent_start") {
    revealAiPanelForTab(tabId);
    const extras = Array.isArray(payload.extras)
      ? (payload.extras as unknown[]).map((v) => String(v))
      : [];
    updateTabAiState(tabId, (state) => ({
      ...state,
      isGenerating: true,
      messages: [
        ...state.messages,
        {
          id: nextId(),
          role: "system",
          type: "agent_start",
          content: String(payload.goal || ""),
          agentPrimary: String(payload.primary_target || "primary"),
          agentExtras: extras,
          agentContext: parseNovaContextPayload(payload.context),
        },
      ],
    }));
    return;
  }

  if (type === "agent_thinking") {
    const text = String(payload.text || "").trim();
    if (!text) return;
    const iteration = Number(payload.iteration || 0) || undefined;
    updateTabAiState(tabId, (state) => ({
      ...state,
      messages: [
        ...state.messages,
        {
          id: nextId(),
          role: "assistant",
          type: "agent_thinking",
          content: text,
          agentIteration: iteration,
        },
      ],
    }));
    return;
  }

  if (type === "agent_tool_call") {
    const iteration = Number(payload.iteration || 0) || undefined;
    const toolName = String(payload.tool || "");
    const toolArgs =
      payload.args && typeof payload.args === "object"
        ? (payload.args as Record<string, unknown>)
        : {};
    updateTabAiState(tabId, (state) => ({
      ...state,
      messages: [
        ...state.messages,
        {
          id: nextId(),
          role: "assistant",
          type: "agent_tool",
          content: "",
          agentIteration: iteration,
          agentToolName: toolName,
          agentToolArgs: toolArgs,
          agentToolOk: true,
          agentStartedAt: Date.now(),
        },
      ],
    }));
    return;
  }

  if (type === "agent_tool_result") {
    const iteration = Number(payload.iteration || 0) || undefined;
    const toolName = String(payload.tool || "");
    const ok = payload.ok !== false;
    const output = String(payload.output || "");
    const error = payload.error ? String(payload.error) : undefined;
    const data = (payload.data && typeof payload.data === "object")
      ? (payload.data as Record<string, unknown>)
      : {};
    const rawExit = data.exit_code;
    const exitCode =
      typeof rawExit === "number"
        ? rawExit
        : typeof rawExit === "string" && rawExit.trim() !== "" && !Number.isNaN(Number(rawExit))
          ? Number(rawExit)
          : undefined;
    updateTabAiState(tabId, (state) => {
      const reversed = [...state.messages].reverse();
      const matchIdx = reversed.findIndex(
        (m) => m.type === "agent_tool" && m.agentToolName === toolName && m.agentIteration === iteration,
      );
      if (matchIdx === -1) return state;
      const absIdx = state.messages.length - 1 - matchIdx;
      const updated = [...state.messages];
      const prev = updated[absIdx];
      const duration = prev.agentStartedAt ? Date.now() - prev.agentStartedAt : undefined;
      updated[absIdx] = {
        ...prev,
        agentToolOk: ok,
        agentToolOutput: output,
        agentToolError: error,
        agentDurationMs: duration,
        agentToolExitCode: exitCode,
      };
      return { ...state, messages: updated };
    });
    return;
  }

  if (type === "agent_todo_update") {
    const todos = Array.isArray(payload.todos)
      ? (payload.todos as Array<Record<string, unknown>>).map((t) => ({
          id: String(t.id || ""),
          content: String(t.content || ""),
          status: (String(t.status || "pending") as
            | "pending"
            | "in_progress"
            | "completed"
            | "cancelled"),
        }))
      : [];
    updateTabAiState(tabId, (state) => {
      const existingIdx = state.messages.findIndex((m) => m.type === "agent_todo");
      const msg: AiMessage = {
        id: existingIdx >= 0 ? state.messages[existingIdx].id : nextId(),
        role: "assistant",
        type: "agent_todo",
        content: "",
        agentTodos: todos,
      };
      if (existingIdx >= 0) {
        const updated = [...state.messages];
        updated[existingIdx] = msg;
        return { ...state, messages: updated };
      }
      return { ...state, messages: [...state.messages, msg] };
    });
    return;
  }

  if (type === "agent_stopped") {
    updateTabAiState(tabId, (state) => ({
      ...state,
      isGenerating: false,
      messages: [
        ...state.messages,
        {
          id: nextId(),
          role: "system",
          type: "agent_stopped",
          content: "",
          agentStopReason: String(payload.reason || ""),
        },
      ],
    }));
    return;
  }

  if (type === "agent_done" || type === "agent_error") {
    updateTabAiState(tabId, (state) => ({ ...state, isGenerating: false }));
    return;
  }

  if (type === "ai_error") {
    revealAiPanelForTab(tabId);
    updateTabAiState(tabId, (state) => ({
      ...state,
      isGenerating: false,
      messages: [
        ...state.messages,
        { id: nextId(), role: "system", type: "text", content: String(payload.message || "AI error") },
      ],
    }));
    return;
  }

  if (type === "status" && String(payload.status) === "connected") {
    updateTabAiState(tabId, (state) => ({
      ...state,
      isGenerating: false,
    }));
  }
}
