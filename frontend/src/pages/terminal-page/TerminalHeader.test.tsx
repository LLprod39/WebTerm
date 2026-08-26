import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { FrontendServer } from "@/lib/api";
import { I18nProvider, useI18n } from "@/lib/i18n";

import { TerminalHeader } from "./TerminalHeader";
import { type Tab } from "./model";

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

function LocalizedHeader() {
  const { t } = useI18n();

  return (
    <TerminalHeader
      activeTab={tab}
      activeServer={server}
      tabs={[tab]}
      activeTabId={tab.id}
      sidePanelMode="none"
      t={t}
      addTab={vi.fn()}
      closeTab={vi.fn()}
      setActiveTabId={vi.fn()}
      setSettingsOpen={vi.fn()}
      setSidePanelMode={vi.fn()}
    />
  );
}

function renderHeader(lang: "en" | "ru") {
  localStorage.setItem("weu_lang", lang);
  return render(
    <MemoryRouter>
      <I18nProvider>
        <LocalizedHeader />
      </I18nProvider>
    </MemoryRouter>,
  );
}

describe("TerminalHeader", () => {
  it("does not expose pilot or read-only session modes", () => {
    renderHeader("ru");

    expect(screen.queryByText(/пилот/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/только чтение/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Обзор" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "ИИ" })).toBeInTheDocument();
  });
});
