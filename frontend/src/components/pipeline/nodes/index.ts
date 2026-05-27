import {
  Bell,
  Bot,
  BrainCircuit,
  Clock,
  ExternalLink,
  FileText,
  GitBranch,
  Link2,
  Mail,
  Merge as MergeIcon,
  MessageCircle,
  Play,
  Puzzle,
  Send,
  Terminal,
  Timer,
  UserCheck,
  Users,
  Zap,
} from "lucide-react";

export { TriggerNode } from "./TriggerNode";
export { AgentNode } from "./AgentNode";
export { ConditionNode } from "./ConditionNode";
export { ParallelNode } from "./ParallelNode";
export { MergeNode } from "./MergeNode";
export { OutputNode } from "./OutputNode";
export { SSHCommandNode } from "./SSHCommandNode";
export { LLMQueryNode } from "./LLMQueryNode";
export { MCPCallNode } from "./MCPCallNode";
export { EmailNode } from "./EmailNode";
export { WaitNode } from "./WaitNode";
export { HumanApprovalNode } from "./HumanApprovalNode";
export { TelegramNode } from "./TelegramNode";
export { TelegramInputNode } from "./TelegramInputNode";

export const NODE_TYPES = {
  "trigger/manual": "TriggerNode",
  "trigger/webhook": "TriggerNode",
  "trigger/schedule": "TriggerNode",
  "trigger/monitoring": "TriggerNode",
  "agent/react": "AgentNode",
  "agent/multi": "AgentNode",
  "agent/ssh_cmd": "SSHCommandNode",
  "agent/llm_query": "LLMQueryNode",
  "agent/mcp_call": "MCPCallNode",
  "logic/condition": "ConditionNode",
  "logic/parallel": "ParallelNode",
  "logic/merge": "MergeNode",
  "logic/wait": "WaitNode",
  "logic/human_approval": "HumanApprovalNode",
  "logic/telegram_input": "TelegramInputNode",
  "output/report": "OutputNode",
  "output/webhook": "OutputNode",
  "output/email": "EmailNode",
  "output/telegram": "TelegramNode",
} as const;

export type NodeType = keyof typeof NODE_TYPES;

export const NODE_PALETTE = [
  {
    category: "Triggers",
    nodes: [
      { type: "trigger/manual" as NodeType, label: "Manual Trigger", icon: Play, iconClassName: "text-amber-400", description: "Start pipeline manually" },
      { type: "trigger/webhook" as NodeType, label: "Webhook", icon: Link2, iconClassName: "text-amber-400", description: "Start via HTTP POST" },
      { type: "trigger/schedule" as NodeType, label: "Schedule", icon: Clock, iconClassName: "text-amber-400", description: "Start on cron schedule" },
      { type: "trigger/monitoring" as NodeType, label: "Monitoring Alert", icon: Bell, iconClassName: "text-amber-400", description: "Start when monitoring opens an alert" },
    ],
  },
  {
    category: "Agents",
    nodes: [
      { type: "agent/react" as NodeType, label: "ReAct Agent", icon: Bot, iconClassName: "text-violet-400", description: "Executes actions on server via SSH+LLM" },
      { type: "agent/multi" as NodeType, label: "Multi-Agent", icon: Users, iconClassName: "text-violet-400", description: "Orchestrated multi-server agent" },
      { type: "agent/ssh_cmd" as NodeType, label: "SSH Command", icon: Terminal, iconClassName: "text-cyan-400", description: "Direct SSH command (no LLM)" },
      { type: "agent/llm_query" as NodeType, label: "LLM Query", icon: BrainCircuit, iconClassName: "text-blue-400", description: "Direct AI reasoning/analysis step" },
      { type: "agent/mcp_call" as NodeType, label: "MCP Call", icon: Puzzle, iconClassName: "text-teal-400", description: "Force a specific MCP tool call" },
    ],
  },
  {
    category: "Logic",
    nodes: [
      { type: "logic/condition" as NodeType, label: "Condition", icon: GitBranch, iconClassName: "text-purple-400", description: "Branch if/else" },
      { type: "logic/parallel" as NodeType, label: "Parallel", icon: Zap, iconClassName: "text-purple-400", description: "Run nodes in parallel" },
      { type: "logic/merge" as NodeType, label: "Merge", icon: MergeIcon, iconClassName: "text-purple-400", description: "Join active branches back together" },
      { type: "logic/wait" as NodeType, label: "Wait", icon: Timer, iconClassName: "text-purple-400", description: "Pause execution for N minutes" },
      { type: "logic/human_approval" as NodeType, label: "Human Approval", icon: UserCheck, iconClassName: "text-yellow-400", description: "Pause and wait for human approve/reject via email & Telegram" },
      { type: "logic/telegram_input" as NodeType, label: "Telegram Input", icon: MessageCircle, iconClassName: "text-purple-400", description: "Wait for a plain-text operator reply in Telegram" },
    ],
  },
  {
    category: "Output",
    nodes: [
      { type: "output/report" as NodeType, label: "Report", icon: FileText, iconClassName: "text-emerald-400", description: "Generate markdown report" },
      { type: "output/webhook" as NodeType, label: "Send Webhook", icon: ExternalLink, iconClassName: "text-emerald-400", description: "POST results to URL" },
      { type: "output/email" as NodeType, label: "Send Email", icon: Mail, iconClassName: "text-emerald-400", description: "Email report via SMTP" },
      { type: "output/telegram" as NodeType, label: "Telegram", icon: Send, iconClassName: "text-sky-400", description: "Send message via Telegram Bot API" },
    ],
  },
];
