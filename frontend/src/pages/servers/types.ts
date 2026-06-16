export interface ServerForm {
  name: string;
  server_type: "ssh";
  host: string;
  port: number;
  username: string;
  auth_method: "password" | "key" | "key_password";
  key_path: string;
  ssh_private_key: string;
  password: string;
  tags: string;
  notes: string;
  group_id: number | null;
  is_active: boolean;
  ai_read_only: boolean;
}

export interface ServerGroupForm {
  name: string;
  description: string;
  color: string;
}

export interface ShareItem {
  id: number;
  user_id: number;
  username: string;
  email: string;
  share_context: boolean;
  expires_at: string | null;
  created_at: string | null;
  is_active: boolean;
}

export interface KnowledgeItem {
  id: number;
  title: string;
  content: string;
  category: string;
  category_label: string;
  source: string;
  source_label: string;
  confidence: number;
  updated_at: string | null;
  is_active: boolean;
}

export interface KnowledgeCategoryOption {
  value: string;
  label: string;
}

export type AdvancedTab = "access" | "knowledge" | "context" | "security" | "execute";
export type MainTab = "servers" | "groups" | "rules" | "playbook";

export interface PlaybookTask {
  id: string;
  command: string;
  description: string;
  continueOnError: boolean;
}

export interface Playbook {
  id: string;
  name: string;
  description: string;
  tasks: PlaybookTask[];
  createdAt: string;
}

export interface PlaybookRunResult {
  serverId: number;
  serverName: string;
  taskResults: {
    taskId: string;
    command: string;
    status: "pending" | "running" | "success" | "error" | "skipped";
    output: string;
    exitCode?: number;
  }[];
}

export type UserKnowledgeFilter = "all" | "summary" | "access" | "risks" | "changes" | "instructions";
