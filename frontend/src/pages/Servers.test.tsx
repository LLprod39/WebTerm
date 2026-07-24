import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "@/lib/api";
import {
  activateTab,
  renderServers,
  setupServersPageApiMocks,
} from "@/pages/servers/serversPageTestHarness";

vi.mock("@/lib/api", () => ({
  addServerGroupMember: vi.fn(),
  bulkDeleteServerMemorySnapshots: vi.fn(),
  clearMasterPassword: vi.fn(),
  createServer: vi.fn(),
  createServerGroup: vi.fn(),
  createServerKnowledge: vi.fn(),
  createServerShare: vi.fn(),
  deleteServerMemorySnapshot: vi.fn(),
  deleteServer: vi.fn(),
  deleteServerGroup: vi.fn(),
  deleteServerKnowledge: vi.fn(),
  executeServerCommand: vi.fn(),
  fetchAuthSession: vi.fn(),
  fetchFrontendBootstrap: vi.fn(),
  fetchMonitoringDashboard: vi.fn(),
  fetchMonitoringStatus: vi.fn(),
  refreshMonitoringFleet: vi.fn(),
  fetchServerDetails: vi.fn(),
  getGlobalServerContext: vi.fn(),
  getGroupServerContext: vi.fn(),
  getMasterPasswordStatus: vi.fn(),
  listServerKnowledge: vi.fn(),
  listServerMemorySnapshots: vi.fn(),
  listServerShares: vi.fn(),
  purgeServerAiMemory: vi.fn(),
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
  updateServerMemorySnapshot: vi.fn(),
}));

describe("Servers page rules and translations", () => {
  beforeEach(() => {
    setupServersPageApiMocks();
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
    fireEvent.pointerDown(screen.getByRole("button", { name: "Open advanced settings for prod-web-01" }), {
      button: 0,
      ctrlKey: false,
    });
    fireEvent.click(await screen.findByRole("menuitem", { name: "Advanced" }));

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

  it("shows ai_auto knowledge snapshots in the server knowledge modal", async () => {
    vi.mocked(api.listServerMemorySnapshots).mockResolvedValue({
      success: true,
      items: [
        {
          id: 501,
          title: "Canonical Profile",
          content: "Host: 172.25.173.251:22 user=lunix\nDocker контейнеры: nginx-web (порт 80)",
          memory_key: "knowledge_note:501",
          kind: "ai_note",
          version: 1,
          confidence: 0.91,
          freshness: 0.98,
          updated_at: "2026-04-09T12:03:14Z",
          created_at: "2026-04-09T12:03:14Z",
          rewrite_reason: "",
        },
        {
          id: 502,
          title: "Canonical Access/Network",
          content: "Host: 172.25.173.251:22 user=lunix\nCommand used: `systemctl status ssh --no-pager`",
          memory_key: "access",
          kind: "canonical",
          version: 1,
          confidence: 0.88,
          freshness: 0.97,
          updated_at: "2026-04-09T12:03:14Z",
          created_at: "2026-04-09T12:03:14Z",
          rewrite_reason: "",
        },
        {
          id: 503,
          title: "Canonical Human Habits",
          content: "- Повторяющиеся ручные привычки пока не выделены.",
          memory_key: "human_habits",
          kind: "canonical",
          version: 1,
          confidence: 0.55,
          freshness: 0.97,
          updated_at: "2026-04-09T12:03:14Z",
          created_at: "2026-04-09T12:03:14Z",
          rewrite_reason: "",
        },
      ],
    });

    renderServers("en");

    await screen.findByText("prod-web-01");
    fireEvent.pointerDown(screen.getByRole("button", { name: "Open advanced settings for prod-web-01" }), {
      button: 0,
      ctrlKey: false,
    });
    fireEvent.click(await screen.findByRole("menuitem", { name: "Advanced" }));
    fireEvent.click(await screen.findByRole("button", { name: "Knowledge" }));

    expect(screen.getByText("Canonical Profile")).toBeInTheDocument();
    expect(screen.getByText(/Docker контейнеры: nginx-web/)).toBeInTheDocument();
    expect(screen.getByText("Повторяющиеся ручные привычки пока не выделены.")).toBeInTheDocument();
    expect(screen.queryByText(/Command used:/)).not.toBeInTheDocument();
    expect(screen.getAllByText("Summary").length).toBeGreaterThan(0);
    expect(screen.queryByText("knowledge_note:501")).not.toBeInTheDocument();
  });

  it("switches new servers UI strings between Russian and English", async () => {
    renderServers("ru");

    expect(await screen.findByText("Инфраструктура")).toBeInTheDocument();
    await activateTab("Правила");
    expect(await screen.findByText("Инструкции по умолчанию")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Глобально" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Группа" })).toBeInTheDocument();

    expect(screen.queryByRole("tab", { name: "Плейбуки" })).not.toBeInTheDocument();
  });

  it("uses the redesigned server form with inline validation and custom selects", async () => {
    renderServers("en");

    fireEvent.click(await screen.findByRole("button", { name: "Add Server" }));

    expect(await screen.findByRole("dialog", { name: "Create Server" })).toBeInTheDocument();
    expect(screen.getAllByText("Enter a server name.").length).toBeGreaterThan(1);
    expect(document.querySelector("select")).not.toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Name/), { target: { value: "edge-01" } });
    fireEvent.change(screen.getByLabelText(/Host/), { target: { value: "10.0.0.20" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => {
      expect(api.createServer).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "edge-01",
          host: "10.0.0.20",
          username: "root",
          server_type: "ssh",
        }),
      );
    });
  });

  it("tests an existing server connection without native alerts", async () => {
    const alertSpy = vi.mocked(window.alert);
    renderServers("en");

    await screen.findByText("prod-web-01");
    fireEvent.pointerDown(screen.getByRole("button", { name: "Open advanced settings for prod-web-01" }), {
      button: 0,
      ctrlKey: false,
    });
    fireEvent.click(await screen.findByRole("menuitem", { name: "Edit Server" }));

    fireEvent.click(await screen.findByRole("button", { name: "Test connection" }));

    await waitFor(() => {
      expect(api.testServer).toHaveBeenCalledWith(1, {});
    });
    expect(alertSpy).not.toHaveBeenCalled();
  });
});
