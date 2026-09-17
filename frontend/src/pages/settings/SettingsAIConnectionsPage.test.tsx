import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsAIConnectionsPage from "./SettingsAIConnectionsPage";
import { I18nProvider } from "@/lib/i18n";

const mocks = vi.hoisted(() => ({
  revoke: vi.fn(async () => ({ success: true, revoked: true })),
  update: vi.fn(async (id: number, payload: { concurrency_limit?: number }) => ({
    success: true,
    connection: {
      id,
      public_id: "conn-7",
      target_id: "codex_subscription" as const,
      scope: "personal" as const,
      owner_id: 1,
      name: "Pilot Codex",
      status: "connected",
      enabled: true,
      concurrency_limit: payload.concurrency_limit ?? 1,
      last_error_code: "",
      last_verified_at: null,
      access: { interactive: true, unattended: false },
      manageable: true,
      grants: [],
    },
  })),
  pools: vi.fn(async () => ({ success: true, pools: [] })),
  users: vi.fn(async () => ({ success: true, users: [{ id: 2, username: "alice" }] })),
  groups: vi.fn(async () => ({ success: true, groups: [{ id: 9, name: "ops", member_count: 2 }] })),
  createGrant: vi.fn(async (payload: Record<string, unknown>) => ({
    success: true,
    grant: {
      id: 55,
      connection_id: payload.connection_id,
      user: payload.user_id ? { id: payload.user_id, username: "alice" } : null,
      group: payload.group_id ? { id: payload.group_id, name: "ops" } : null,
      project: null,
      project_role: "",
      allow_interactive: payload.allow_interactive ?? true,
      allow_unattended: payload.allow_unattended ?? false,
      max_slots: payload.max_slots ?? null,
    },
  })),
  principals: vi.fn(async () => ({
    success: true,
    users: [{ id: 2, username: "alice" }],
    groups: [{ id: 9, name: "ops" }],
  })),
  updateGrant: vi.fn(async (id: number, payload: { max_slots?: number | null }) => ({
    success: true,
    grant: {
      id,
      connection_id: 11,
      user: null,
      group: { id: 9, name: "ops" },
      project: null,
      project_role: "",
      allow_interactive: true,
      allow_unattended: false,
      max_slots: payload.max_slots ?? null,
    },
  })),
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
  savePreference: vi.fn(async () => ({ success: true, preference: {} })),
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
    fetchAuthSession: vi.fn(async () => ({
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
    fetchAiProviderConnections: mocks.connections,
    fetchAiProviderPools: mocks.pools,
    fetchAiProviderPreferences: mocks.preferences,
    fetchAiProviderCatalog: mocks.catalog,
    fetchAccessUsers: mocks.users,
    fetchAccessGroups: mocks.groups,
    fetchAiProviderAuthFlow: mocks.authFlow,
    revokeAiProviderConnection: mocks.revoke,
    updateAiProviderConnection: mocks.update,
    updateAiProviderGrant: mocks.updateGrant,
    createAiProviderGrant: mocks.createGrant,
    fetchAiProviderPrincipals: mocks.principals,
    saveAiProviderPreference: mocks.savePreference,
    clearAiProviderPreference: vi.fn(async () => ({ success: true, deleted: 0 })),
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
    expect(screen.getByRole("combobox", { name: "Параллельные запросы" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Параллельность · Pilot Codex" })).toBeInTheDocument();
    expect(screen.getAllByText("1 слот").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("Workspace: пулы и явные гранты")).not.toBeInTheDocument();
    expect(screen.getByText("Доступ")).toBeInTheDocument();
    expect(mocks.pools).not.toHaveBeenCalled();
  });

  it("saves concurrency limit for an existing connection", async () => {
    renderPage();
    await screen.findByText("Pilot Codex");

    fireEvent.click(screen.getByRole("combobox", { name: "Параллельность · Pilot Codex" }));
    fireEvent.click(await screen.findByRole("option", { name: "3 слота" }));

    await waitFor(() => expect(mocks.update).toHaveBeenCalledWith(7, { concurrency_limit: 3 }));
  });

  it("tracks the asynchronous verification flow returned with 202", async () => {
    renderPage();
    await screen.findByText("Pilot Codex");

    fireEvent.click(screen.getByRole("button", { name: "Проверить" }));

    await waitFor(() => expect(mocks.verify).toHaveBeenCalledWith(7));
    expect(await screen.findByText("Вход в CLI: completed")).toBeInTheDocument();
  });

  it("requires confirmation before deleting a connection", async () => {
    renderPage();
    await screen.findByText("Pilot Codex");

    fireEvent.click(screen.getByRole("button", { name: "Удалить" }));
    expect(mocks.revoke).not.toHaveBeenCalled();

    const dialog = screen.getByRole("alertdialog");
    expect(within(dialog).getByText("Удалить подключение?")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Удалить" }));

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

  it("hides reasoning for Cursor and saves without reasoning_effort", async () => {
    mocks.connections.mockResolvedValueOnce({
      success: true,
      connections: [{
        id: 9,
        public_id: "conn-9",
        target_id: "cursor_subscription" as const,
        scope: "personal" as const,
        owner_id: 1,
        name: "Pilot Cursor",
        status: "connected",
        enabled: true,
        concurrency_limit: 1,
        last_error_code: "",
        last_verified_at: null,
        access: { interactive: true, unattended: false },
        manageable: true,
        grants: [],
      }],
    });
    mocks.preferences.mockResolvedValueOnce({
      success: true,
      preferences: [{
        id: 2,
        user_id: 1,
        project_id: 1,
        purpose: "assistant" as const,
        binding: {
          target_id: "cursor_subscription",
          connection_id: 9,
          model_id: "auto",
          reasoning_effort: null,
        },
      }],
      workspace_defaults: [],
    });
    mocks.catalog.mockResolvedValueOnce({
      success: true,
      targets: [],
      purposes: [],
      models_by_target: {
        cursor_subscription: [{
          id: "auto",
          label: "Auto",
          default_reasoning_effort: null,
          reasoning_efforts: [] as const,
        }],
      },
    });
    mocks.savePreference.mockResolvedValueOnce({
      success: true,
      preference: {
        id: 2,
        user_id: 1,
        project_id: 1,
        purpose: "assistant",
        binding: { target_id: "cursor_subscription", connection_id: 9, model_id: "auto", reasoning_effort: null },
      },
    });

    renderPage();

    expect(await screen.findByRole("combobox", { name: "Ассистент и чаты · модель" })).toHaveTextContent("Auto");
    expect(screen.queryByRole("combobox", { name: "Ассистент и чаты · размышление" })).not.toBeInTheDocument();

    fireEvent.click(screen.getAllByRole("button", { name: "Сохранить" })[0]);

    await waitFor(() => expect(mocks.savePreference).toHaveBeenCalled());
    expect(mocks.savePreference).toHaveBeenCalledWith(expect.objectContaining({
      purpose: "assistant",
      binding: expect.not.objectContaining({ reasoning_effort: expect.anything() }),
    }));
    expect(mocks.savePreference.mock.calls[0][0].binding).toEqual({
      target_id: "cursor_subscription",
      connection_id: 9,
      model_id: "auto",
    });
  });

  it("lets admin grant CLI access to a group with slot limit", async () => {
    const api = await import("@/lib/api");
    vi.mocked(api.fetchAuthSession).mockResolvedValue({
      authenticated: true,
      user: {
        id: 1,
        username: "admin",
        email: "admin@example.test",
        is_staff: true,
        ai_cli_runtime_enabled: true,
        features: { ai_connections_personal: true, ai_connections_admin: true },
      },
    } as never);
    mocks.connections.mockResolvedValueOnce({
      success: true,
      connections: [{
        id: 11,
        public_id: "conn-11",
        target_id: "cursor_subscription" as const,
        scope: "workspace" as const,
        owner_id: null,
        name: "Workspace Cursor",
        status: "connected",
        enabled: true,
        concurrency_limit: 4,
        last_error_code: "",
        last_verified_at: null,
        access: { interactive: true, unattended: true },
        manageable: true,
        grants: [{
          id: 40,
          connection_id: 11,
          user: null,
          group: { id: 9, name: "ops" },
          project: null,
          project_role: "",
          allow_interactive: true,
          allow_unattended: false,
          max_slots: 2,
        }],
      }],
    });

    renderPage();

    expect(await screen.findByText("Workspace Cursor")).toBeInTheDocument();
    expect(screen.getByText("ops")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Слоты · ops" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Кому выдать" })).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Лимит слотов" })).toBeInTheDocument();
    expect(screen.getByText("Доступ")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("combobox", { name: "Кому выдать" }));
    fireEvent.click(await screen.findByRole("option", { name: "Группа" }));
    fireEvent.click(screen.getByRole("combobox", { name: "Группа" }));
    fireEvent.click(await screen.findByRole("option", { name: "ops" }));
    fireEvent.click(screen.getByRole("combobox", { name: "Подключение" }));
    fireEvent.click(await screen.findByRole("option", { name: /Workspace Cursor/ }));
    fireEvent.click(screen.getByRole("combobox", { name: "Лимит слотов" }));
    fireEvent.click(await screen.findByRole("option", { name: "2 слота" }));
    fireEvent.click(screen.getByRole("button", { name: "Выдать доступ" }));

    await waitFor(() => expect(mocks.createGrant).toHaveBeenCalled());
    expect(mocks.createGrant).toHaveBeenCalledWith(expect.objectContaining({
      connection_id: 11,
      group_id: 9,
      allow_interactive: true,
      max_slots: 2,
    }));
  });
});
