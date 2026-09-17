import type { FrontendServer } from "@/lib/api";

type LinuxUiServerSummary = Pick<FrontendServer, "id" | "name" | "host" | "username">;

export interface LinuxUiCapabilities {
  hostname: string;
  current_user: string;
  os_name: string;
  os_id: string;
  kernel: string;
  is_systemd: boolean;
  package_manager: "apt" | "dnf" | "yum" | null;
  commands: {
    systemctl: boolean;
    journalctl: boolean;
    docker: boolean;
    ss: boolean;
    ip: boolean;
    apt: boolean;
    dnf: boolean;
    yum: boolean;
    python3: boolean;
    bash: boolean;
    sh: boolean;
  };
  available_apps: {
    overview: boolean;
    files: boolean;
    terminal: boolean;
    ai: boolean;
    text_editor: boolean;
    quick_run: boolean;
    settings: boolean;
    services: boolean;
    logs: boolean;
    processes: boolean;
    disk: boolean;
    network: boolean;
    docker: boolean;
    packages: boolean;
  };
}

export interface LinuxUiOverview {
  hostname: string;
  current_user: string;
  home_path: string;
  cwd: string;
  os_name: string;
  kernel: string;
  uptime_seconds: number | null;
  process_count: number | null;
  load: {
    one: number | null;
    five: number | null;
    fifteen: number | null;
  };
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

export interface LinuxUiCapabilitiesResponse {
  success: boolean;
  observed_at: string;
  server: LinuxUiServerSummary;
  capabilities: LinuxUiCapabilities;
}

export interface LinuxUiSettingsAccount {
  name: string;
  uid: string;
  home: string;
  shell: string;
}

export interface LinuxUiSettingsSnapshot {
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
    accounts: LinuxUiSettingsAccount[];
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

export interface LinuxUiSettingsResponse {
  success: boolean;
  observed_at: string;
  server: LinuxUiServerSummary;
  settings: LinuxUiSettingsSnapshot;
}

export interface LinuxUiOverviewResponse {
  success: boolean;
  observed_at: string;
  server: LinuxUiServerSummary;
  overview: LinuxUiOverview;
}

export type LinuxUiServiceHealth = "active" | "failed" | "inactive" | "activating" | "deactivating" | "other";
export type LinuxUiServiceAction = "start" | "stop" | "restart" | "reload";

export interface LinuxUiServiceItem {
  unit: string;
  name: string;
  load: string;
  active: string;
  sub: string;
  description: string;
  health: LinuxUiServiceHealth;
  is_active: boolean;
  is_failed: boolean;
}

export interface LinuxUiServicesSummary {
  total: number;
  active: number;
  failed: number;
  inactive: number;
  other: number;
}

export interface LinuxUiServicesResponse {
  success: boolean;
  observed_at: string;
  limit: number;
  server: LinuxUiServerSummary;
  services: LinuxUiServiceItem[];
  summary: LinuxUiServicesSummary;
}

export interface LinuxUiServiceLogsPayload {
  service: string;
  lines: number;
  source: "journalctl" | "systemctl-status";
  content: string;
}

export interface LinuxUiServiceLogsResponse {
  success: boolean;
  observed_at: string;
  server: LinuxUiServerSummary;
  service_logs: LinuxUiServiceLogsPayload;
}

export interface LinuxUiServiceActionPayload {
  service: string;
  action: LinuxUiServiceAction;
}

export interface LinuxUiServiceActionResult {
  success: boolean;
  service: string;
  action: LinuxUiServiceAction;
  dangerous: boolean;
  output: string;
  status_excerpt: string;
}

export interface LinuxUiServiceActionResponse {
  success: boolean;
  performed_at: string;
  server: LinuxUiServerSummary;
  service_action: LinuxUiServiceActionResult;
}

export type LinuxUiProcessAction = "terminate" | "kill_force";

export interface LinuxUiProcessItem {
  pid: number;
  user: string;
  cpu_percent: number | null;
  memory_percent: number | null;
  elapsed: string;
  command: string;
  args: string;
}

export interface LinuxUiProcessesPayload {
  limit: number;
  summary: {
    total: number;
    high_cpu: number;
    high_memory: number;
  };
  top_cpu: LinuxUiProcessItem[];
  top_memory: LinuxUiProcessItem[];
}

export interface LinuxUiProcessesResponse {
  success: boolean;
  observed_at: string;
  server: LinuxUiServerSummary;
  processes: LinuxUiProcessesPayload;
}

export interface LinuxUiProcessActionPayload {
  pid: number;
  action: LinuxUiProcessAction;
}

export interface LinuxUiProcessActionResult {
  success: boolean;
  pid: number;
  action: LinuxUiProcessAction;
  dangerous: boolean;
  output: string;
  still_running: boolean;
  process_excerpt: string;
}

export interface LinuxUiProcessActionResponse {
  success: boolean;
  performed_at: string;
  server: LinuxUiServerSummary;
  process_action: LinuxUiProcessActionResult;
}

export interface LinuxUiLogPreset {
  key: string;
  label: string;
  description: string;
  available: boolean;
}

export interface LinuxUiLogsPayload {
  source: string;
  service: string;
  lines: number;
  available: boolean;
  content: string;
  presets: LinuxUiLogPreset[];
}

export interface LinuxUiLogsResponse {
  success: boolean;
  observed_at: string;
  server: LinuxUiServerSummary;
  logs: LinuxUiLogsPayload;
}

export interface LinuxUiDiskMount {
  filesystem: string;
  mount: string;
  size_gb: number | null;
  used_gb: number | null;
  available_gb: number | null;
  percent: number | null;
}

export interface LinuxUiDiskPathStat {
  path: string;
  size_mb: number | null;
}

export interface LinuxUiDiskPayload {
  summary: {
    mounts: number;
    critical_mounts: number;
    top_directory_mb: number | null;
    largest_log_mb: number | null;
    cleanup_candidates: number;
  };
  mounts: LinuxUiDiskMount[];
  top_directories: LinuxUiDiskPathStat[];
  large_logs: LinuxUiDiskPathStat[];
  cleanup_candidates: string[];
}

export interface LinuxUiDiskResponse {
  success: boolean;
  observed_at: string;
  server: LinuxUiServerSummary;
  disk: LinuxUiDiskPayload;
}

export interface LinuxUiPackageItem {
  name: string;
  version: string;
}

export interface LinuxUiPackagesPayload {
  package_manager: string;
  installed: LinuxUiPackageItem[];
  updates: string[];
  summary: {
    installed_common: number;
    update_candidates: number;
  };
}

export interface LinuxUiPackagesResponse {
  success: boolean;
  observed_at: string;
  server: LinuxUiServerSummary;
  packages: LinuxUiPackagesPayload;
}

export type LinuxUiDockerAction = "start" | "stop" | "restart";

export interface LinuxUiDockerContainer {
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

export interface LinuxUiDockerPayload {
  ready: boolean;
  error: string;
  summary: {
    total: number;
    running: number;
    exited: number;
    restarting: number;
    paused: number;
  };
  containers: LinuxUiDockerContainer[];
}

export interface LinuxUiDockerResponse {
  success: boolean;
  observed_at: string;
  server: LinuxUiServerSummary;
  docker: LinuxUiDockerPayload;
}

export interface LinuxUiDockerLogsPayload {
  container: string;
  lines: number;
  content: string;
}

export interface LinuxUiDockerLogsResponse {
  success: boolean;
  observed_at: string;
  server: LinuxUiServerSummary;
  docker_logs: LinuxUiDockerLogsPayload;
}

export interface LinuxUiDockerActionPayload {
  container: string;
  action: LinuxUiDockerAction;
}

export interface LinuxUiDockerActionResult {
  success: boolean;
  container: string;
  action: LinuxUiDockerAction;
  dangerous: boolean;
  output: string;
  inspect_excerpt: string;
}

export interface LinuxUiDockerActionResponse {
  success: boolean;
  performed_at: string;
  server: LinuxUiServerSummary;
  docker_action: LinuxUiDockerActionResult;
}

export interface LinuxUiNetworkAddress {
  family: string;
  address: string;
  scope: string;
}

export interface LinuxUiNetworkInterface {
  name: string;
  state: string;
  mtu: number | null;
  kind: string;
  mac: string;
  flags: string[];
  addresses: LinuxUiNetworkAddress[];
}

export interface LinuxUiListeningSocket {
  protocol: string;
  state: string;
  local_address: string;
  peer_address: string;
  process: string;
}

export interface LinuxUiNetworkPayload {
  tools: {
    ip: boolean;
    ss: boolean;
  };
  summary: {
    interfaces: number;
    addresses: number;
    routes: number;
    listening: number;
  };
  interfaces: LinuxUiNetworkInterface[];
  routes: string[];
  listening: LinuxUiListeningSocket[];
}

export interface LinuxUiNetworkResponse {
  success: boolean;
  observed_at: string;
  server: LinuxUiServerSummary;
  network: LinuxUiNetworkPayload;
}
