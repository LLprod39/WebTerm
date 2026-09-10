import { describe, expect, it } from "vitest";
import { defaultTerminalAiOptions, terminalAiRequest } from "@/api/terminal-ai";
import { initialTerminalAiState, terminalAiReducer } from "./terminal-ai-state";

describe("Terminal AI execution contracts", () => {
  it("confirmation mode cannot silently start the autonomous agent loop", () => {
    expect(
      terminalAiRequest(" check disk ", "confirm", defaultTerminalAiOptions),
    ).toMatchObject({
      type: "ai_request",
      message: "check disk",
      chat_mode: "ask",
      execution_mode: "step",
      ai_settings: {
        confirm_dangerous_commands: true,
        nova_sudo_policy: "disabled",
      },
    });
  });
  it("preserves rapid command updates and appends adaptive steps", () => {
    let state = terminalAiReducer(initialTerminalAiState, {
      type: "request",
      message: "Check service",
    });
    state = terminalAiReducer(state, {
      type: "event",
      event: {
        type: "ai_response",
        run_id: "run_1",
        commands: [{ id: 1, cmd: "systemctl status nginx", status: "pending" }],
      },
    });
    state = terminalAiReducer(state, {
      type: "event",
      event: {
        type: "ai_command_status",
        run_id: "run_1",
        id: 1,
        status: "done",
        exit_code: 3,
      },
    });
    state = terminalAiReducer(state, {
      type: "event",
      event: {
        type: "ai_response",
        run_id: "run_1",
        commands: [
          { id: 2, cmd: "journalctl -u nginx -n 20", status: "pending" },
        ],
      },
    });
    expect(state.commands).toHaveLength(2);
    expect(state.commands[0]).toMatchObject({
      id: 1,
      status: "done",
      exit_code: 3,
    });
  });
  it("ignores events from a previous run and clears confirmation after disconnect", () => {
    let state = terminalAiReducer(
      { ...initialTerminalAiState, runId: "old" },
      { type: "request", message: "New task" },
    );
    state = terminalAiReducer(state, {
      type: "event",
      event: {
        type: "ai_status",
        run_id: "old",
        status: "waiting_confirm",
        id: 1,
      },
    });
    expect(state.awaitingCommandId).toBeNull();
    state = terminalAiReducer(state, {
      type: "event",
      event: {
        type: "ai_status",
        run_id: "new",
        status: "waiting_confirm",
        id: 4,
      },
    });
    expect(state.awaitingCommandId).toBe(4);
    state = terminalAiReducer(state, {
      type: "event",
      event: { type: "status", status: "disconnected" },
    });
    expect(state.awaitingCommandId).toBeNull();
    expect(state.status).toBe("disconnected");
  });
  it("shows one final answer when Nova mirrors agent_done to ai_response", () => {
    let state = terminalAiReducer(initialTerminalAiState, {
      type: "event",
      event: { type: "agent_done", final_text: "Проверка завершена." },
    });
    state = terminalAiReducer(state, {
      type: "event",
      event: { type: "ai_response", assistant_text: "Проверка завершена." },
    });
    expect(state.messages).toHaveLength(1);
  });
});
