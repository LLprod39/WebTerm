export interface TerminalAiCommand {
  id: number;
  cmd: string;
  why?: string;
  status: string;
  blocked?: boolean;
  requires_confirm?: boolean;
  reason?: string;
  risk_categories?: string[];
  risk_reasons?: string[];
  streaming?: boolean;
  exit_code?: number | null;
  output?: string;
  explanation?: string;
  dry_run?: boolean;
}
export interface TerminalAiQuestion {
  q_id: string;
  question: string;
  cmd?: string;
  exit_code?: number | null;
  options?: { label: string; value: string; description?: string }[];
  allow_multiple?: boolean;
  free_text_allowed?: boolean;
  placeholder?: string;
}
export interface TerminalAiEvent {
  type: string;
  run_id?: string;
  status?: string;
  message?: string;
  code?: string;
  id?: number | string;
  assistant_text?: string;
  commands?: TerminalAiCommand[];
  execution_mode?: string;
  cmd?: string;
  output?: string;
  exit_code?: number | null;
  reason?: string;
  streaming?: boolean;
  dry_run?: boolean;
  report?: string;
  explanation?: string;
  new_id?: number;
  new_cmd?: string;
  original_cmd?: string;
  why?: string;
  requires_confirm?: boolean;
  q_id?: string;
  question?: string;
  options?: TerminalAiQuestion["options"];
  allow_multiple?: boolean;
  free_text_allowed?: boolean;
  placeholder?: string;
  iteration?: number;
  tool?: string;
  args?: Record<string, unknown>;
  ok?: boolean;
  error?: string;
  data?: Record<string, unknown>;
  final_text?: string;
  iterations?: number;
  tool_calls?: number;
  todos?: { id: string; content: string; status: string }[];
  restored_history_count?: number;
  elapsed?: number;
  output_tail?: string;
  count?: number;
  ids?: number[];
}
export type TerminalAiMode = "confirm" | "step" | "fast" | "auto" | "agent";
export interface TerminalAiOptions {
  dryRun: boolean;
  sudoPolicy: "disabled" | "ask" | "approved";
  autoReport: "auto" | "on" | "off";
  blockedCommands: string;
  extraTargetIds: number[];
}
export const defaultTerminalAiOptions: TerminalAiOptions = {
  dryRun: false,
  sudoPolicy: "disabled",
  autoReport: "auto",
  blockedCommands: "",
  extraTargetIds: [],
};
export function terminalAiRequest(
  message: string,
  mode: TerminalAiMode,
  options: TerminalAiOptions,
): Record<string, unknown> {
  return {
    type: "ai_request",
    message: message.trim(),
    chat_mode: mode === "confirm" ? "ask" : "agent",
    execution_mode: mode === "confirm" ? "step" : mode,
    ai_settings: {
      memory_enabled: true,
      memory_ttl_requests: 6,
      auto_report: options.autoReport,
      confirm_dangerous_commands: true,
      dry_run: options.dryRun,
      allowlist_patterns: [],
      blocklist_patterns: options.blockedCommands
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean)
        .slice(0, 50),
      extra_target_server_ids: [...new Set(options.extraTargetIds)]
        .filter((id) => Number.isSafeInteger(id) && id > 0)
        .slice(0, 5),
      nova_session_context_enabled: true,
      nova_recent_activity_enabled: true,
      nova_sudo_policy: options.sudoPolicy,
    },
  };
}
