import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

import { I18nProvider } from "@/lib/i18n";
import * as api from "@/lib/api";
import Servers from "@/pages/Servers";
import { featureMap } from "@/test/featureFlags";

const bootstrapResponse = {
  success: true,
  servers: [
    {
      id: 1,
      name: "prod-web-01",
      host: "10.0.0.5",
      port: 22,
      username: "ubuntu",
      server_type: "ssh" as const,
      status: "online" as const,
      group_id: 10,
      group_name: "Web",
      is_shared: false,
      can_edit: true,
      share_context_enabled: true,
      shared_by_username: "",
      terminal_path: "/servers/1/terminal",
      minimal_terminal_path: "/servers/1/terminal/minimal",
      last_connected: null,
    },
  ],
  groups: [
    {
      id: 10,
      name: "Web",
      description: "Primary web tier",
      color: "#22c55e",
      server_count: 1,
      role: "owner" as const,
      can_edit: true,
    },
  ],
  stats: { owned: 1, shared: 0, total: 1 },
  recent_activity: [],
};

const globalContext = {
  rules: "Always verify changes before execution.",
  forbidden_commands: ["rm -rf /"],
  required_checks: ["uptime"],
  environment_vars: { ENV: "prod" },
};

const groupContext = {
  id: 10,
  name: "Web",
  rules: "Restart services only during maintenance windows.",
  forbidden_commands: ["systemctl poweroff"],
  environment_vars: { TEAM: "ops" },
};

export const serverDetails = {
  id: 1,
  name: "prod-web-01",
  host: "10.0.0.5",
  port: 22,
  username: "ubuntu",
  server_type: "ssh" as const,
  auth_method: "password" as const,
  key_path: "",
  tags: "",
  notes: "",
  group_id: 10,
  is_active: true,
  corporate_context: "Only for this host",
  network_config: { env_vars: { HOST_ROLE: "web" } },
  has_saved_password: true,
  can_view_password: true,
  can_edit: true,
  is_shared_server: false,
  share_context_enabled: true,
  shared_by_username: "ops-admin",
};

export function renderServers(lang: "en" | "ru" = "en") {
  localStorage.setItem("weu_lang", lang);

  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <I18nProvider>
          <Servers />
        </I18nProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

export function getActionsContainer() {
  const sshLink = screen.getByRole("link", { name: "SSH" });
  const actionsContainer = sshLink.parentElement?.parentElement;
  if (!(actionsContainer instanceof HTMLElement)) {
    throw new Error("Unable to find server actions container");
  }
  return actionsContainer;
}

export function getSparklesButton(container: HTMLElement) {
  const button = within(container).getAllByRole("button")[0];

  if (!(button instanceof HTMLButtonElement)) {
    throw new Error("Unable to find advanced settings button");
  }

  return button;
}

export async function activateTab(label: string) {
  const tab = await screen.findByRole("tab", { name: label });
  fireEvent.mouseDown(tab, { button: 0 });
  fireEvent.click(tab);
}

export function setupServersPageApiMocks() {
  vi.clearAllMocks();
  vi.spyOn(window, "alert").mockImplementation(() => {});
  vi.spyOn(window, "confirm").mockReturnValue(true);
  vi.spyOn(window, "prompt").mockReturnValue("updated value");

  vi.mocked(api.fetchAuthSession).mockResolvedValue({
    authenticated: true,
    user: {
      id: 1,
      username: "admin",
      email: "admin@example.com",
      is_staff: true,
      features: featureMap(),
    },
  });
  vi.mocked(api.fetchFrontendBootstrap).mockResolvedValue(bootstrapResponse);
  vi.mocked(api.fetchMonitoringStatus).mockResolvedValue({
    success: true,
    servers: [
      {
        server_id: 1,
        server_name: "prod-web-01",
        host: "10.0.0.5",
        server_type: "ssh",
        status: "healthy",
        checked_at: "2026-04-06T12:00:00Z",
        age_seconds: 30,
        is_stale: false,
        response_time_ms: 50,
        cpu_percent: 12,
        memory_percent: 34,
        disk_percent: 56,
        load_1m: 0.42,
        metrics_checked_at: "2026-04-06T12:00:00Z",
        metrics_age_seconds: 30,
        is_lite: true,
      },
    ],
    summary: {
      total_servers: 1,
      healthy: 1,
      warning: 0,
      critical: 0,
      unreachable: 0,
      unknown: 0,
      stale: 0,
    },
    meta: {
      stale_after_seconds: 300,
      latest_checked_at: "2026-04-06T12:00:00Z",
      has_stale: false,
    },
  });
  vi.mocked(api.refreshMonitoringFleet).mockResolvedValue({
    success: true,
    servers: [],
    summary: {
      total_servers: 0,
      healthy: 0,
      warning: 0,
      critical: 0,
      unreachable: 0,
      unknown: 0,
      stale: 0,
    },
    meta: { stale_after_seconds: 300, latest_checked_at: null, has_stale: false },
    refreshed: true,
  });
  vi.mocked(api.fetchMonitoringDashboard).mockResolvedValue({
    success: true,
    servers: [
      {
        server_id: 1,
        server_name: "prod-web-01",
        host: "10.0.0.5",
        status: "healthy",
        cpu_percent: 12,
        memory_percent: 34,
        disk_percent: 56,
        memory_used_mb: 1024,
        memory_total_mb: 4096,
        disk_used_gb: 100,
        disk_total_gb: 200,
        net_rx_bytes: 1024,
        net_tx_bytes: 2048,
        load_1m: 0.1,
        uptime_seconds: 3600,
        response_time_ms: 50,
        checked_at: "2026-04-06T12:00:00Z",
      },
    ],
    alerts: [],
    summary: {
      total_servers: 1,
      healthy: 1,
      warning: 0,
      critical: 0,
      unreachable: 0,
      unknown: 0,
      active_alerts: 0,
      avg_cpu: 12,
      avg_memory: 34,
      avg_disk: 56,
    },
    recent_activity: [],
  });
  vi.mocked(api.fetchServerDetails).mockResolvedValue(serverDetails);
  vi.mocked(api.getGlobalServerContext).mockResolvedValue(globalContext);
  vi.mocked(api.getGroupServerContext).mockResolvedValue(groupContext);
  vi.mocked(api.getMasterPasswordStatus).mockResolvedValue({ has_master_password: false });
  vi.mocked(api.listServerKnowledge).mockResolvedValue({ success: true, items: [], categories: [] });
  vi.mocked(api.listServerMemorySnapshots).mockResolvedValue({ success: true, items: [] });
  vi.mocked(api.listServerShares).mockResolvedValue({ success: true, shares: [] });
  vi.mocked(api.saveGlobalServerContext).mockResolvedValue({ success: true });
  vi.mocked(api.saveGroupServerContext).mockResolvedValue({ success: true });
  vi.mocked(api.updateServer).mockResolvedValue({ success: true, message: "ok" });
  vi.mocked(api.addServerGroupMember).mockResolvedValue({ success: true });
  vi.mocked(api.bulkDeleteServerMemorySnapshots).mockResolvedValue({ success: true, deleted_count: 0, snapshot_ids: [] });
  vi.mocked(api.deleteServerMemorySnapshot).mockResolvedValue({ success: true });
  vi.mocked(api.purgeServerAiMemory).mockResolvedValue({
    success: true,
    deleted: { snapshots: 0, revalidations: 0, episodes: 0, events: 0, knowledge: 0 },
  });
  vi.mocked(api.removeServerGroupMember).mockResolvedValue({ success: true });
  vi.mocked(api.subscribeServerGroup).mockResolvedValue({ success: true });
  vi.mocked(api.executeServerCommand).mockResolvedValue({ success: true, output: { stdout: "ok" } });
  vi.mocked(api.revealServerPassword).mockResolvedValue({ success: true, password: "secret" });
  vi.mocked(api.setMasterPassword).mockResolvedValue({ success: true });
  vi.mocked(api.clearMasterPassword).mockResolvedValue({ success: true });
  vi.mocked(api.testServer).mockResolvedValue({ success: true });
  vi.mocked(api.triggerHealthCheck).mockResolvedValue({
    success: true,
    check: {
      id: 1,
      status: "healthy",
      cpu_percent: 12,
      memory_percent: 34,
      disk_percent: 56,
      load_1m: 0.1,
      load_5m: 0.1,
      load_15m: 0.1,
      memory_used_mb: 1024,
      memory_total_mb: 4096,
      disk_used_gb: 100,
      disk_total_gb: 200,
      uptime_seconds: 3600,
      process_count: 42,
      response_time_ms: 50,
      is_deep: false,
      checked_at: "2026-04-06T12:00:00Z",
    },
  });
  vi.mocked(api.createServerGroup).mockResolvedValue({ success: true });
  vi.mocked(api.updateServerGroup).mockResolvedValue({ success: true });
  vi.mocked(api.deleteServerGroup).mockResolvedValue({ success: true });
  vi.mocked(api.createServer).mockResolvedValue({ success: true, server_id: 99, message: "created" });
  vi.mocked(api.deleteServer).mockResolvedValue({ success: true });
  vi.mocked(api.createServerKnowledge).mockResolvedValue({ success: true });
  vi.mocked(api.updateServerKnowledge).mockResolvedValue({ success: true });
  vi.mocked(api.deleteServerKnowledge).mockResolvedValue({ success: true });
  vi.mocked(api.createServerShare).mockResolvedValue({ success: true });
  vi.mocked(api.revokeServerShare).mockResolvedValue({ success: true });
}
