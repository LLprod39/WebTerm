import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { HTMLAttributes, ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "@/lib/i18n";
import Servers from "@/pages/Servers";
import * as api from "@/lib/api";

vi.mock("framer-motion", () => ({
  AnimatePresence: ({ children }: { children: ReactNode }) => <>{children}</>,
  motion: {
    div: ({ children, ...props }: HTMLAttributes<HTMLDivElement>) => <div {...props}>{children}</div>,
  },
}));

vi.mock("@/lib/api", () => ({
  addServerGroupMember: vi.fn(),
  clearMasterPassword: vi.fn(),
  createServer: vi.fn(),
  createServerGroup: vi.fn(),
  createServerKnowledge: vi.fn(),
  createServerShare: vi.fn(),
  deleteServer: vi.fn(),
  deleteServerGroup: vi.fn(),
  deleteServerKnowledge: vi.fn(),
  executeServerCommand: vi.fn(),
  fetchAuthSession: vi.fn(),
  fetchFrontendBootstrap: vi.fn(),
  fetchMonitoringDashboard: vi.fn(),
  fetchServerDetails: vi.fn(),
  getGlobalServerContext: vi.fn(),
  getGroupServerContext: vi.fn(),
  getMasterPasswordStatus: vi.fn(),
  listServerKnowledge: vi.fn(),
  listServerShares: vi.fn(),
  removeServerGroupMember: vi.fn(),
  revealServerPassword: vi.fn(),
  revokeServerShare: vi.fn(),
  saveGlobalServerContext: vi.fn(),
  saveGroupServerContext: vi.fn(),
  setMasterPassword: vi.fn(),
  subscribeServerGroup: vi.fn(),
  testServer: vi.fn(),
  triggerHealthCheck: vi.fn(),
  updateServer: vi.fn(),
  updateServerGroup: vi.fn(),
  updateServerKnowledge: vi.fn(),
}));

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
      rdp: false,
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

const serverDetails = {
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

function renderServers(lang: "en" | "ru" = "en") {
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

function getActionsContainer() {
  const sshButton = screen.getByRole("button", { name: "SSH" });
  const actionsContainer = sshButton.parentElement?.parentElement;
  if (!(actionsContainer instanceof HTMLElement)) {
    throw new Error("Unable to find server actions container");
  }
  return actionsContainer;
}

function getSparklesButton(container: HTMLElement) {
  const button = within(container)
    .getAllByRole("button")
    .find((candidate) => candidate.innerHTML.includes("lucide-sparkles"));

  if (!(button instanceof HTMLButtonElement)) {
    throw new Error("Unable to find advanced settings button");
  }

  return button;
}

async function activateTab(label: string) {
  const tab = await screen.findByRole("tab", { name: label });
  fireEvent.mouseDown(tab, { button: 0 });
  fireEvent.click(tab);
}

describe("Servers page rules and translations", () => {
  beforeEach(() => {
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
        features: {},
      },
    });
    vi.mocked(api.fetchFrontendBootstrap).mockResolvedValue(bootstrapResponse);
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
    vi.mocked(api.listServerShares).mockResolvedValue({ success: true, shares: [] });
    vi.mocked(api.saveGlobalServerContext).mockResolvedValue({ success: true });
    vi.mocked(api.saveGroupServerContext).mockResolvedValue({ success: true });
    vi.mocked(api.updateServer).mockResolvedValue({ success: true, message: "ok" });
    vi.mocked(api.addServerGroupMember).mockResolvedValue({ success: true });
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
  });

  it("saves global and group rules from separate editors", async () => {
    renderServers("en");

    await activateTab("Rules");
    expect(await screen.findByText("Default instructions")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("Default AI instructions for all servers"), {
      target: { value: "Global baseline" },
    });
    fireEvent.change(screen.getByPlaceholderText('{"KEY": "value"}'), {
      target: { value: '{"ENV":"staging"}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save Global Context" }));

    await waitFor(() => {
      expect(api.saveGlobalServerContext).toHaveBeenCalledWith(
        expect.objectContaining({
          rules: "Global baseline",
          environment_vars: { ENV: "staging" },
        }),
      );
    });

    await activateTab("Group");
    expect(await screen.findByText("Group override")).toBeInTheDocument();
    expect(screen.getByText("Effective rules for Web")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("Additional rules for the selected group"), {
      target: { value: "Group-only rule" },
    });
    fireEvent.change(screen.getByPlaceholderText('{"TEAM": "platform"}'), {
      target: { value: '{"TEAM":"platform-core"}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save Group Context" }));

    await waitFor(() => {
      expect(api.saveGroupServerContext).toHaveBeenCalledWith(
        10,
        expect.objectContaining({
          rules: "Group-only rule",
          environment_vars: { TEAM: "platform-core" },
        }),
      );
    });

    expect(api.updateServer).not.toHaveBeenCalled();
  });

  it("keeps server override isolated in the modal and saves via updateServer", async () => {
    renderServers("en");

    await screen.findByText("prod-web-01");
    fireEvent.click(getSparklesButton(getActionsContainer()));

    fireEvent.click(await screen.findByRole("button", { name: "Server Rules" }));
    expect(await screen.findByText("Scope: Server")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save Global Context" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save Group Context" })).not.toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("Instructions specific to this server"), {
      target: { value: "Only for API host" },
    });
    fireEvent.change(screen.getByPlaceholderText('{"env_vars": {"KEY": "value"}}'), {
      target: { value: '{"env_vars":{"HOST_ROLE":"api"}}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save server override" }));

    await waitFor(() => {
      expect(api.updateServer).toHaveBeenCalledWith(1, {
        corporate_context: "Only for API host",
        network_config: { env_vars: { HOST_ROLE: "api" } },
      });
    });

    expect(api.saveGlobalServerContext).not.toHaveBeenCalled();
    expect(api.saveGroupServerContext).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Open inherited rules" }));
    expect(await screen.findByText("Group override")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Rules" })).toBeInTheDocument();
  });

  it("switches new servers UI strings between Russian and English", async () => {
    renderServers("ru");

    expect(await screen.findByText("Инфраструктура")).toBeInTheDocument();
    await activateTab("Правила");
    expect(await screen.findByText("Инструкции по умолчанию")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Глобально" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Группа" })).toBeInTheDocument();

    await activateTab("Плейбуки");
    expect(await screen.findByText("Импортируйте Ansible playbooks (YAML/JSON) или создайте новый с нуля")).toBeInTheDocument();

    await activateTab("Список серверов");
    await screen.findByText("prod-web-01");
    fireEvent.click(getSparklesButton(getActionsContainer()));

    fireEvent.click(await screen.findByRole("button", { name: "Правила сервера" }));
    expect(await screen.findByText("Уровень: Сервер")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Открыть наследуемые правила" })).toBeInTheDocument();
  });
});
