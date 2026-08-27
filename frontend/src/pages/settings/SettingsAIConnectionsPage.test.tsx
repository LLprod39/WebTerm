import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsAIConnectionsPage from "./SettingsAIConnectionsPage";
import { I18nProvider } from "@/lib/i18n";

const mocks = vi.hoisted(() => ({
  auth: vi.fn(async () => ({
    authenticated: true,
    user: {
      id: 1,
      username: "pilot",
      email: "pilot@example.test",
      is_staff: false,
      ai_cli_runtime_enabled: true,
      features: { ai_connections_personal: true },
    },
  })),
  grant: vi.fn(async () => ({ success: true, grant: { id: 1 } })),
  revoke: vi.fn(async () => ({ success: true, revoked: true })),
  pools: vi.fn(async () => ({ success: true, pools: [] })),
  users: vi.fn(async () => ({ success: true, users: [] })),
  groups: vi.fn(async () => ({ success: true, groups: [] })),
  savePreference: vi.fn(async () => ({ success: true, preference: { id: 1 } })),
  verify: vi.fn(async () => ({
    success: true,
    auth_flow: { id: "verify-flow", connection_id: 7, status: "pending", verification_uri: "", user_code: "", error_code: "", expires_at: null },
  })),
  authFlow: vi.fn(async () => ({
    success: true,
    auth_flow: { id: "verify-flow", connection_id: 7, status: "completed", verification_uri: "", user_code: "", error_code: "", expires_at: null },
  })),
  preferences: vi.fn(async () => ({ success: true, preferences: [], workspace_defaults: [] })),
  catalog: vi.fn(async () => ({ success: true, targets: [], purposes: [], models_by_target: {} })),
  connections: vi.fn(async () => ({
    success: true,
    connections: [{
      id: 7,
      public_id: "conn-7",
      target_id: "codex_subscription" as const,
      scope: "personal" as const,
      owner_id: 1,
      name: "Pilot Codex",
      status: "connected",
      enabled: true,
      concurrency_limit: 1,
      last_error_code: "",
      last_verified_at: null,
      access: { interactive: true, unattended: false },
      manageable: true,
      grants: [],
    }],
  })),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    fetchAuthSession: mocks.auth,
    fetchAiProviderConnections: mocks.connections,
    fetchAiProviderPools: mocks.pools,
    fetchAiProviderPreferences: mocks.preferences,
    fetchAiProviderCatalog: mocks.catalog,
    fetchAccessUsers: mocks.users,
    fetchAccessGroups: mocks.groups,
    fetchAiProviderAuthFlow: mocks.authFlow,
    revokeAiProviderConnection: mocks.revoke,
    createAiProviderGrant: mocks.grant,
    saveAiProviderPreference: mocks.savePreference,
    startAiProviderAuth: vi.fn(async () => ({
      success: true,
      auth_flow: { id: "flow-1", connection_id: 7, status: "pending", verification_uri: "", user_code: "", error_code: "", expires_at: null },
    })),
    verifyAiProviderConnection: mocks.verify,
  };
});

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <SettingsAIConnectionsPage />
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe("SettingsAIConnectionsPage pilot safety", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.setItem("weu_lang", "ru");
  });

  it("labels personal connection fields and hides workspace administration", async () => {
    renderPage();

    expect(await screen.findByText("Pilot Codex")).toBeInTheDocument();
    expect(screen.getByLabelText("Название подключения")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "CLI-провайдер" })).toBeInTheDocument();
    expect(screen.queryByText("Workspace: пулы и явные гранты")).not.toBeInTheDocument();
    expect(mocks.pools).not.toHaveBeenCalled();
    expect(mocks.users).not.toHaveBeenCalled();
  });

  it("tracks the asynchronous verification flow returned with 202", async () => {
    renderPage();
    await screen.findByText("Pilot Codex");

    fireEvent.click(screen.getByRole("button", { name: "Проверить" }));

    await waitFor(() => expect(mocks.verify).toHaveBeenCalledWith(7));
    expect(await screen.findByText("Вход в CLI: completed")).toBeInTheDocument();
  });

  it("requires confirmation before revoking a connection", async () => {
    renderPage();
    await screen.findByText("Pilot Codex");

    fireEvent.click(screen.getByRole("button", { name: "Отозвать" }));
    expect(mocks.revoke).not.toHaveBeenCalled();

    const dialog = screen.getByRole("alertdialog");
    expect(within(dialog).getByText("Отозвать подключение?")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Отозвать" }));

    await waitFor(() => expect(mocks.revoke).toHaveBeenCalledWith(7));
  });

  it("hides revoked audit records until explicitly requested", async () => {
    mocks.connections.mockResolvedValueOnce({
      success: true,
      connections: [
        {
          id: 7,
          public_id: "conn-7",
          target_id: "codex_subscription" as const,
          scope: "personal" as const,
          owner_id: 1,
          name: "Pilot Codex",
          status: "connected",
          enabled: true,
          concurrency_limit: 1,
          last_error_code: "",
          last_verified_at: null,
          access: { interactive: true, unattended: false },
          manageable: true,
          grants: [],
        },
        {
          id: 8,
          public_id: "conn-8",
          target_id: "codex_subscription" as const,
          scope: "personal" as const,
          owner_id: 1,
          name: "Old Codex",
          status: "revoked",
          enabled: false,
          concurrency_limit: 1,
          last_error_code: "",
          last_verified_at: null,
          access: { interactive: false, unattended: false },
          manageable: true,
          grants: [],
        },
      ],
    });

    renderPage();

    expect(await screen.findByText("Pilot Codex")).toBeInTheDocument();
    expect(screen.queryByText("Old Codex")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Показать отозванные (1)" }));
    expect(screen.getByText("Old Codex")).toBeInTheDocument();
  });

  it("shows the saved Codex model and reasoning mode", async () => {
    mocks.preferences.mockResolvedValueOnce({
      success: true,
      preferences: [{
        id: 1,
        user_id: 1,
        project_id: 1,
        purpose: "assistant" as const,
        binding: {
          target_id: "codex_subscription",
          connection_id: 7,
          model_id: "gpt-5.6-terra",
          reasoning_effort: "high" as const,
        },
      }],
      workspace_defaults: [],
    });
    mocks.catalog.mockResolvedValueOnce({
      success: true,
      targets: [],
      purposes: [],
      models_by_target: {
        codex_subscription: [{
          id: "gpt-5.6-terra",
          label: "GPT-5.6 Terra",
          default_reasoning_effort: "medium" as const,
          reasoning_efforts: ["low", "medium", "high", "xhigh"] as const,
        }],
      },
    });

    renderPage();

    expect(await screen.findByRole("combobox", { name: "Ассистент и чаты · модель" })).toHaveTextContent("GPT-5.6 Terra");
    expect(screen.getByRole("combobox", { name: "Ассистент и чаты · размышление" })).toHaveTextContent("high");
  });

  it("grants a connected workspace Codex connection to a group", async () => {
    mocks.auth.mockResolvedValueOnce({
      authenticated: true,
      user: {
        id: 1,
        username: "admin",
        email: "admin@example.test",
        is_staff: true,
        ai_cli_runtime_enabled: true,
        active_project: { id: "project-1", name: "Pilot", slug: "pilot" },
        features: { ai_connections_personal: true, ai_connections_admin: true },
      },
    });
    mocks.connections.mockResolvedValueOnce({
      success: true,
      connections: [{
        id: 9,
        public_id: "conn-9",
        target_id: "codex_subscription" as const,
        scope: "workspace" as const,
        owner_id: null,
        name: "Team Codex",
        status: "connected",
        enabled: true,
        concurrency_limit: 3,
        last_error_code: "",
        last_verified_at: null,
        access: { interactive: true, unattended: true },
        manageable: true,
        grants: [],
      }],
    });
    mocks.groups.mockResolvedValueOnce({
      success: true,
      groups: [{ id: 2, name: "pilot", member_count: 9, members: [], explicit_permissions: {} }],
    });
    renderPage();

    expect(await screen.findByText("Workspace: пулы и явные гранты")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("combobox", { name: "Workspace-подключение" }));
    fireEvent.click(await screen.findByRole("option", { name: "Team Codex" }));
    fireEvent.click(screen.getByRole("combobox", { name: "Группа" }));
    fireEvent.click(await screen.findByRole("option", { name: "pilot" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Расписания" }));
    fireEvent.click(screen.getByRole("button", { name: "Выдать доступ" }));

    await waitFor(() => expect(mocks.grant).toHaveBeenCalledWith({
      connection_id: 9,
      group_id: 2,
      allow_interactive: true,
      allow_unattended: true,
    }));
  });

  it("saves an administrator selection as the active workspace default", async () => {
    mocks.auth.mockResolvedValueOnce({
      authenticated: true,
      user: {
        id: 1,
        username: "admin",
        email: "admin@example.test",
        is_staff: true,
        ai_cli_runtime_enabled: true,
        active_project: { id: "project-1", name: "Pilot", slug: "pilot" },
        features: { ai_connections_personal: true, ai_connections_admin: true },
      },
    });
    mocks.connections.mockResolvedValueOnce({
      success: true,
      connections: [{
        id: 9,
        public_id: "conn-9",
        target_id: "codex_subscription" as const,
        scope: "workspace" as const,
        owner_id: null,
        name: "Team Codex",
        status: "connected",
        enabled: true,
        concurrency_limit: 3,
        last_error_code: "",
        last_verified_at: null,
        access: { interactive: true, unattended: true },
        manageable: true,
        grants: [],
      }],
    });
    mocks.catalog.mockResolvedValueOnce({
      success: true,
      targets: [],
      purposes: [],
      models_by_target: {
        codex_subscription: [{
          id: "gpt-5.6-terra",
          label: "GPT-5.6 Terra",
          default_reasoning_effort: "medium" as const,
          reasoning_efforts: ["low", "medium", "high"] as const,
        }],
      },
    });
    renderPage();

    await screen.findByText("По умолчанию для активного workspace: Pilot.");
    fireEvent.click(screen.getByRole("combobox", { name: "Ассистент и чаты" }));
    fireEvent.click(await screen.findByRole("option", { name: "Team Codex · Codex CLI" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Сохранить" })[0]);

    await waitFor(() => expect(mocks.savePreference).toHaveBeenCalledWith({
      purpose: "assistant",
      binding: {
        target_id: "codex_subscription",
        connection_id: 9,
        model_id: "gpt-5.6-terra",
        reasoning_effort: "medium",
      },
      project_scoped: true,
      workspace_default: true,
      require_unattended: false,
    }));
  });
});
