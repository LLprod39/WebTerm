import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { AuthUser, FrontendServer } from "@/lib/api";
import { I18nProvider, useI18n } from "@/lib/i18n";
import { featureMap } from "@/test/featureFlags";

import { TerminalHeader } from "./TerminalHeader";
import { isTerminalReadOnlyMode, type Tab } from "./model";

const server: FrontendServer = {
  id: 1,
  name: "pilot-host",
  host: "192.0.2.10",
  port: 22,
  username: "pilot",
  server_type: "ssh",
  status: "online",
  group_id: null,
  group_name: "Pilot",
  is_shared: false,
  can_edit: false,
  share_context_enabled: false,
  shared_by_username: "",
  terminal_path: "/servers/1/terminal/",
  minimal_terminal_path: "/servers/1/terminal/minimal/",
  last_connected: null,
  ai_read_only: true,
};

const tab: Tab = {
  id: "tab-1",
  serverId: server.id,
  name: server.name,
  sessionNumber: 1,
  status: "connected",
};

function LocalizedHeader({ readOnlyMode }: { readOnlyMode: boolean }) {
  const { t } = useI18n();

  return (
    <TerminalHeader
      activeTab={tab}
      activeServer={server}
      readOnlyMode={readOnlyMode}
      tabs={[tab]}
      activeTabId={tab.id}
      sidePanelMode="none"
      t={t}
      addTab={vi.fn()}
      closeTab={vi.fn()}
      revealUiPanel={vi.fn()}
      setActiveTabId={vi.fn()}
      setSettingsOpen={vi.fn()}
      setSidePanelMode={vi.fn()}
    />
  );
}

function renderHeader(lang: "en" | "ru", readOnlyMode: boolean) {
  localStorage.setItem("weu_lang", lang);
  return render(
    <MemoryRouter>
      <I18nProvider>
        <LocalizedHeader readOnlyMode={readOnlyMode} />
      </I18nProvider>
    </MemoryRouter>,
  );
}

function authUser(automation: boolean): AuthUser {
  return {
    id: 1,
    username: "pilot-user",
    email: "pilot@example.com",
    is_staff: false,
    access_profile: automation ? "pilot_operator" : "pilot_user",
    features: featureMap({ servers: true, automation }),
  };
}

describe("TerminalHeader read-only pilot notice", () => {
  it("explains the restricted terminal behavior in English", () => {
    renderHeader("en", true);

    const notice = screen.getByRole("status");
    expect(notice).toHaveTextContent("Read-only pilot mode.");
    expect(notice).toHaveTextContent(
      "Commands are checked after you press Enter. Sudo, file changes, shell history, and Tab completion are unavailable.",
    );
  });

  it("explains the restricted terminal behavior in Russian", () => {
    renderHeader("ru", true);

    const notice = screen.getByRole("status");
    expect(notice).toHaveTextContent("Пилотный режим «только чтение».");
    expect(notice).toHaveTextContent(
      "Команды проверяются после нажатия Enter. Sudo, изменение файлов, история shell и автодополнение по Tab недоступны.",
    );
  });

  it("does not show the notice for a writable operator session", () => {
    renderHeader("en", false);

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("matches the effective automation and server read-only gates", () => {
    expect(isTerminalReadOnlyMode({ ...server, ai_read_only: false }, undefined)).toBe(true);
    expect(isTerminalReadOnlyMode({ ...server, ai_read_only: false }, authUser(false))).toBe(true);
    expect(
      isTerminalReadOnlyMode(
        { ...server, ai_read_only: false },
        { ...authUser(true), access_profile: "admin_full" },
      ),
    ).toBe(true);
    expect(isTerminalReadOnlyMode({ ...server, ai_read_only: true }, authUser(true))).toBe(true);
    expect(isTerminalReadOnlyMode({ ...server, ai_read_only: false }, authUser(true))).toBe(false);
  });
});
