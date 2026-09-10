import { api } from "./client";

export interface LinuxCapabilities {
  hostname: string;
  current_user: string;
  os_name: string;
  os_id: string;
  kernel: string;
  is_systemd: boolean;
  package_manager: string | null;
  commands: Record<string, boolean>;
  available_apps: Record<string, boolean>;
}
export interface LinuxOverview {
  hostname: string;
  current_user: string;
  home_path: string;
  cwd: string;
  os_name: string;
  kernel: string;
  uptime_seconds: number | null;
  process_count: number | null;
  load: { one: number | null; five: number | null; fifteen: number | null };
  memory: {
    total_mb: number | null;
    used_mb: number | null;
    percent: number | null;
  };
  disk: {
    mount: string;
    total_gb: number | null;
    used_gb: number | null;
    percent: number | null;
  };
}
export interface LinuxService {
  unit: string;
  name: string;
  load: string;
  active: string;
  sub: string;
  description: string;
  health: string;
  is_active: boolean;
  is_failed: boolean;
}
export interface LinuxProcess {
  pid: number;
  user: string;
  cpu_percent: number | null;
  memory_percent: number | null;
  elapsed: string;
  command: string;
  args: string;
}
export interface LinuxContainer {
  id: string;
  name: string;
  image: string;
  state: string;
  status: string;
  running_for: string;
  ports: string;
  cpu_percent: string;
  memory_percent: string;
  memory_usage: string;
  network_io: string;
  block_io: string;
}
export interface LinuxLogs {
  source?: string;
  service?: string;
  container?: string;
  lines: number;
  content: string;
  available?: boolean;
  unavailable_reason?: string;
  presets?: {
    key: string;
    label: string;
    description: string;
    available: boolean;
  }[];
}
export interface LinuxMount {
  filesystem: string;
  mount: string;
  size_gb: number | null;
  used_gb: number | null;
  available_gb: number | null;
  percent: number | null;
}
export interface LinuxSizePath {
  path: string;
  size_mb: number | null;
}
export interface LinuxInterface {
  name: string;
  state: string;
  mtu: number | null;
  kind: string;
  mac: string;
  flags: string[];
  addresses: { family: string; address: string; scope: string }[];
}
export interface LinuxSocket {
  protocol: string;
  state: string;
  local_address: string;
  peer_address: string;
  process: string;
}
export interface LinuxSettings {
  general: {
    hostname: string;
    timezone: string;
    kernel: string;
    os_release: string;
    uptime: string;
    architecture: string;
    cpu: string;
    total_memory: string;
  };
  users: {
    current_user: string;
    sudo_group: string;
    accounts: { name: string; uid: string; home: string; shell: string }[];
    logged_in: string;
    last_logins: string;
  };
  crontab: {
    user_crontab: string;
    system_crontab: string;
    cron_dirs: string;
    timers: string;
  };
  environment: {
    shell: string;
    locale: string;
    path_directories: string[];
    variables: string;
  };
  security: {
    ssh_config: string;
    firewall: string;
    failed_logins: string;
    listening_ports: string;
  };
}
export interface LinuxSnapshots {
  capabilities: { capabilities: LinuxCapabilities };
  overview: { overview: LinuxOverview };
  services: {
    services: LinuxService[];
    summary: {
      total: number;
      active: number;
      failed: number;
      inactive: number;
      other: number;
    };
    limit: number;
  };
  processes: {
    processes: {
      limit: number;
      summary: { total: number; high_cpu: number; high_memory: number };
      top_cpu: LinuxProcess[];
      top_memory: LinuxProcess[];
    };
  };
  docker: {
    docker: {
      ready: boolean;
      error: string;
      summary: {
        total: number;
        running: number;
        exited: number;
        restarting: number;
        paused: number;
      };
      containers: LinuxContainer[];
    };
  };
  logs: { logs: LinuxLogs };
  "services/logs": { service_logs: LinuxLogs };
  "docker/logs": { docker_logs: LinuxLogs };
  disk: {
    disk: {
      summary: {
        mounts: number;
        critical_mounts: number;
        top_directory_mb: number;
        largest_log_mb: number;
        cleanup_candidates: number;
      };
      mounts: LinuxMount[];
      top_directories: LinuxSizePath[];
      large_logs: LinuxSizePath[];
      cleanup_candidates: string[];
    };
  };
  network: {
    network: {
      tools: Record<string, boolean>;
      summary: {
        interfaces: number;
        addresses: number;
        routes: number;
        listening: number;
      };
      interfaces: LinuxInterface[];
      routes: string[];
      listening: LinuxSocket[];
    };
  };
  packages: {
    packages: {
      package_manager: string;
      installed: { name: string; version: string }[];
      updates: string[];
      summary: { installed_common: number; update_candidates: number };
    };
  };
  settings: { settings: LinuxSettings };
}
export type LinuxAction =
  | {
      kind: "services";
      target: string;
      action: "start" | "stop" | "restart" | "reload";
    }
  | { kind: "processes"; target: number; action: "terminate" | "kill_force" }
  | { kind: "docker"; target: string; action: "start" | "stop" | "restart" };
export interface LinuxActionResult {
  success: boolean;
  output: string;
  dangerous: boolean;
  status_excerpt?: string;
  process_excerpt?: string;
  inspect_excerpt?: string;
  still_running?: boolean;
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
  is_active: boolean;
  updated_at: string;
}
export interface KnowledgeInput {
  title: string;
  content: string;
  category: string;
  is_active: boolean;
  confidence?: number;
}
export interface RollbackSnapshot {
  id: number;
  file_path: string;
  command: string;
  byte_size: number;
  content_truncated: boolean;
  file_existed: boolean | null;
  content_hash: string;
  created_at: string;
  restored_at: string | null;
}
export interface RollbackSnapshotDetail extends RollbackSnapshot {
  server_id: number;
  user_id: number;
  content: string;
}

export const serverOperationsApi = {
  snapshot: <T extends keyof LinuxSnapshots>(
    id: number,
    resource: T,
    params: Record<string, string> = {},
    signal?: AbortSignal,
  ) =>
    api.get<LinuxSnapshots[T] & { observed_at: string }>(
      `/servers/api/${id}/ui/${resource}/?${new URLSearchParams(params)}`,
      signal,
    ),
  action: (id: number, action: LinuxAction) =>
    api.post<{
      service_action?: LinuxActionResult;
      process_action?: LinuxActionResult;
      docker_action?: LinuxActionResult;
      performed_at: string;
    }>(`/servers/api/${id}/ui/${action.kind}/action/`, {
      action: action.action,
      [action.kind === "services"
        ? "service"
        : action.kind === "docker"
          ? "container"
          : "pid"]: action.target,
    }),
  knowledge: (id: number, inactive: boolean, signal?: AbortSignal) =>
    api.get<{
      items: KnowledgeItem[];
      categories: { value: string; label: string }[];
      include_inactive: boolean;
    }>(
      `/servers/api/${id}/knowledge/?include_inactive=${inactive ? "1" : "0"}`,
      signal,
    ),
  createKnowledge: (id: number, body: KnowledgeInput) =>
    api.post(`/servers/api/${id}/knowledge/create/`, body),
  updateKnowledge: (id: number, itemId: number, body: KnowledgeInput) =>
    api.post(`/servers/api/${id}/knowledge/${itemId}/update/`, body),
  deleteKnowledge: (id: number, itemId: number) =>
    api.post(`/servers/api/${id}/knowledge/${itemId}/delete/`),
  snapshots: (id: number, signal?: AbortSignal) =>
    api.get<{ snapshots: RollbackSnapshot[] }>(
      `/servers/api/${id}/snapshots/?limit=100`,
      signal,
    ),
  snapshotDetail: (id: number, snapshotId: number, signal?: AbortSignal) =>
    api.get<{ snapshot: RollbackSnapshotDetail }>(
      `/servers/api/${id}/snapshots/${snapshotId}/`,
      signal,
    ),
  prepareRestore: (id: number, snapshotId: number) =>
    api.post<{ restore_command: string }>(
      `/servers/api/${id}/snapshots/${snapshotId}/restore/`,
    ),
};
