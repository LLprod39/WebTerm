import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsAIConnectionsPage from "./SettingsAIConnectionsPage";
import { I18nProvider } from "@/lib/i18n";

const mocks = vi.hoisted(() => ({
  revoke: vi.fn(async () => ({ success: true, revoked: true })),
  pools: vi.fn(async () => ({ success: true, pools: [] })),
  users: vi.fn(async () => ({ success: true, users: [] })),
  verify: vi.fn(async () => ({
    success: true,
    auth_flow: { id: "verify-flow", connection_id: 7, status: "pending", verification_uri: "", user_code: "", error_code: "", expires_at: null },
  })),
  authFlow: vi.fn(async () => ({
    success: true,
    auth_flow: { id: "verify-flow", connection_id: 7, status: "completed", verification_uri: "", user_code: "", error_code: "", expires_at: null },
  })),
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
        features: { ai_connections_personal: true },
      },
    })),
    fetchAiProviderConnections: mocks.connections,
    fetchAiProviderPools: mocks.pools,
    fetchAiProviderPreferences: vi.fn(async () => ({ success: true, preferences: [], workspace_defaults: [] })),
    fetchAiProviderCatalog: vi.fn(async () => ({ success: true, targets: [], purposes: [] })),
    fetchAccessUsers: mocks.users,
    fetchAiProviderAuthFlow: mocks.authFlow,
    revokeAiProviderConnection: mocks.revoke,
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
});
