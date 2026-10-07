import {
  Archive,
  Bell,
  BellDot,
  Brain,
  Cable,
  Clock,
  Container,
  ExternalLink,
  FileCode2,
  FileSearch,
  FileText,
  GitBranch,
  Globe2,
  HardDrive,
  Link2,
  Mail,
  Merge as MergeIcon,
  MessageCircle,
  Package,
  Play,
  Radar,
  ScrollText,
  Send,
  ServerCog,
  Settings2,
  Terminal,
  Timer,
  UserCheck,
  UsersRound,
  Webhook,
  Zap,
} from "lucide-react";

export { TriggerNode } from "./TriggerNode";
export { AgentNode } from "./AgentNode";
export { ConditionNode } from "./ConditionNode";
export { ParallelNode } from "./ParallelNode";
export { MergeNode } from "./MergeNode";
export { OutputNode } from "./OutputNode";
export { OpsNode } from "./OpsNode";
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
  "ops/server_snapshot": "OpsNode",
  "ops/log_query": "OpsNode",
  "ops/file_action": "OpsNode",
  "ops/package_action": "OpsNode",
  "ops/disk_cleanup": "OpsNode",
  "ops/backup_restore_check": "OpsNode",
  "ops/service_action": "OpsNode",
  "ops/docker_action": "OpsNode",
  "ops/process_action": "OpsNode",
  "ops/http_check": "OpsNode",
  "ops/alert_update": "OpsNode",
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
      { type: "trigger/manual" as NodeType, label: "Manual Trigger", icon: Play, iconClassName: "text-warning", description: "Start pipeline manually" },
      { type: "trigger/webhook" as NodeType, label: "Webhook", icon: Link2, iconClassName: "text-warning", description: "Start via HTTP POST" },
      { type: "trigger/schedule" as NodeType, label: "Schedule", icon: Clock, iconClassName: "text-warning", description: "Start on cron schedule" },
      { type: "trigger/monitoring" as NodeType, label: "Monitoring Alert", icon: Bell, iconClassName: "text-warning", description: "Start when monitoring opens an alert" },
    ],
  },
  {
    category: "Agents",
    nodes: [
      { type: "agent/react" as NodeType, label: "ReAct Agent", icon: Radar, iconClassName: "text-ai", description: "Executes actions on server via SSH+LLM" },
      { type: "agent/multi" as NodeType, label: "Multi-Agent", icon: UsersRound, iconClassName: "text-ai", description: "Orchestrated multi-server agent" },
      { type: "agent/ssh_cmd" as NodeType, label: "SSH Command", icon: Terminal, iconClassName: "text-info", description: "Direct SSH command (no LLM)" },
      { type: "agent/llm_query" as NodeType, label: "LLM Query", icon: Brain, iconClassName: "text-ai", description: "Direct AI reasoning/analysis step" },
      { type: "agent/mcp_call" as NodeType, label: "MCP Call", icon: Cable, iconClassName: "text-info", description: "Force a specific MCP tool call" },
    ],
  },
  {
    category: "Ops",
    nodes: [
      { type: "ops/server_snapshot" as NodeType, label: "Server Snapshot", icon: ServerCog, iconClassName: "text-info", description: "Read-only Linux server snapshot" },
      { type: "ops/log_query" as NodeType, label: "Log Query", icon: ScrollText, iconClassName: "text-success", description: "Read-only Linux/service/Docker logs" },
      { type: "ops/file_action" as NodeType, label: "File Action", icon: FileCode2, iconClassName: "text-warning", description: "Read or write UTF-8 text files" },
      { type: "ops/package_action" as NodeType, label: "Package Action", icon: Package, iconClassName: "text-warning", description: "List or change OS packages" },
      { type: "ops/disk_cleanup" as NodeType, label: "Disk Cleanup", icon: HardDrive, iconClassName: "text-destructive", description: "Inspect disk or clean journal/tmp safely" },
      { type: "ops/backup_restore_check" as NodeType, label: "Backup Check", icon: Archive, iconClassName: "text-success", description: "Check backup freshness and archive integrity" },
      { type: "ops/service_action" as NodeType, label: "Service Action", icon: Settings2, iconClassName: "text-warning", description: "Start/stop/restart systemd service" },
      { type: "ops/docker_action" as NodeType, label: "Docker Action", icon: Container, iconClassName: "text-info", description: "Start/stop/restart Docker container" },
      { type: "ops/process_action" as NodeType, label: "Process Action", icon: Zap, iconClassName: "text-destructive", description: "Terminate or force kill a process" },
      { type: "ops/http_check" as NodeType, label: "HTTP Check", icon: Globe2, iconClassName: "text-success", description: "Verify a URL and expected status/body" },
      { type: "ops/alert_update" as NodeType, label: "Alert Update", icon: BellDot, iconClassName: "text-warning", description: "Resolve a WebTerm monitoring alert" },
    ],
  },
  {
    category: "Logic",
    nodes: [
      { type: "logic/condition" as NodeType, label: "Condition", icon: GitBranch, iconClassName: "text-warning", description: "Branch if/else" },
      { type: "logic/parallel" as NodeType, label: "Parallel", icon: Zap, iconClassName: "text-warning", description: "Run nodes in parallel" },
      { type: "logic/merge" as NodeType, label: "Merge", icon: MergeIcon, iconClassName: "text-warning", description: "Join active branches back together" },
      { type: "logic/wait" as NodeType, label: "Wait", icon: Timer, iconClassName: "text-warning", description: "Pause execution for N minutes" },
      { type: "logic/human_approval" as NodeType, label: "Human Approval", icon: UserCheck, iconClassName: "text-warning", description: "Pause and wait for human approve/reject via email & Telegram" },
      { type: "logic/telegram_input" as NodeType, label: "Telegram Input", icon: MessageCircle, iconClassName: "text-warning", description: "Wait for a plain-text operator reply in Telegram" },
    ],
  },
  {
    category: "Output",
    nodes: [
      { type: "output/report" as NodeType, label: "Report", icon: FileSearch, iconClassName: "text-success", description: "Generate markdown report" },
      { type: "output/webhook" as NodeType, label: "Send Webhook", icon: Webhook, iconClassName: "text-success", description: "POST results to URL" },
      { type: "output/email" as NodeType, label: "Send Email", icon: Mail, iconClassName: "text-success", description: "Email report via SMTP" },
      { type: "output/telegram" as NodeType, label: "Telegram", icon: Send, iconClassName: "text-success", description: "Send message via Telegram Bot API" },
    ],
  },
];
