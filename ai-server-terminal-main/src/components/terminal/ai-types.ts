export type AiExecutionMode = "auto" | "step" | "fast" | "agent";
export type AiChatMode = "ask" | "agent";
export type AiAutoReportMode = "auto" | "on" | "off";

export interface AiAssistantSettings {
  memoryEnabled: boolean;
  memoryTtlRequests: number;
  autoReport: AiAutoReportMode;
  confirmDangerousCommands: boolean;
  whitelistPatterns: string[];
  blacklistPatterns: string[];
  showSuggestedCommands: boolean;
  showExecutedCommands: boolean;
  dryRun: boolean;
  extraTargetServerIds: number[];
  novaSessionContextEnabled: boolean;
  novaRecentActivityEnabled: boolean;
}

export interface AiPreferences {
  chatMode: AiChatMode;
  executionMode: AiExecutionMode;
  settings: AiAssistantSettings;
}

export interface AiCommand {
  id: number;
  cmd: string;
  why: string;
  requires_confirm: boolean;
  status?: "pending" | "running" | "done" | "skipped" | "cancelled" | "confirmed";
  exit_code?: number;
  blocked?: boolean;
  reason?: "" | "forbidden" | "outside_allowlist" | "dangerous" | "ask_mode";
  risk_categories?: string[];
  risk_reasons?: string[];
  exec_mode?: "pty" | "direct";
  direct_output?: string;
  explanation?: string;
  explaining?: boolean;
}

export interface AgentTodo {
  id: string;
  content: string;
  status: "pending" | "in_progress" | "completed" | "cancelled";
}

export interface NovaSessionContextView {
  cwd?: string;
  user?: string;
  hostname?: string;
  shell?: string;
  venv?: string;
  python?: string;
  env_summary?: string[];
  source?: string;
  confidence?: string;
}

export interface NovaRecentActivityItem {
  command: string;
  cwd?: string;
  exit_code?: number | null;
  source?: string;
}

export interface NovaContextPayload {
  session?: NovaSessionContextView;
  recent_activity?: NovaRecentActivityItem[];
}

export interface AiQuestionOption {
  label: string;
  value: string;
  description?: string;
}

export interface AiMessage {
  id: string;
  role: "user" | "assistant" | "system";
  type?:
    | "text"
    | "commands"
    | "report"
    | "question"
    | "progress"
    | "recovery"
    | "agent_start"
    | "agent_thinking"
    | "agent_tool"
    | "agent_todo"
    | "agent_stopped";
  content: string;
  commands?: AiCommand[];
  mode?: "execute" | "answer" | "ask";
  reportStatus?: "ok" | "warning" | "error";
  qId?: string;
  question?: string;
  questionOptions?: AiQuestionOption[];
  questionAllowMultiple?: boolean;
  questionFreeTextAllowed?: boolean;
  questionPlaceholder?: string;
  questionSource?: string;
  questionAnswered?: boolean;
  questionAnswer?: string;
  questionCmd?: string;
  questionExitCode?: number;
  progressCmd?: string;
  progressElapsed?: number;
  progressTail?: string;
  recoveryOriginal?: string;
  recoveryNew?: string;
  recoveryWhy?: string;
  agentIteration?: number;
  agentToolName?: string;
  agentToolArgs?: Record<string, unknown>;
  agentToolOk?: boolean;
  agentToolOutput?: string;
  agentToolError?: string;
  agentTodos?: AgentTodo[];
  agentStopReason?: string;
  agentPrimary?: string;
  agentExtras?: string[];
  agentContext?: NovaContextPayload;
  agentStartedAt?: number;
  agentDurationMs?: number;
  agentToolExitCode?: number;
}
