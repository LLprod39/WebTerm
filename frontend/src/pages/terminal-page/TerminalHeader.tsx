import { Link } from "react-router-dom";
import type { Dispatch, SetStateAction } from "react";
import { ArrowLeft, Bot, FolderOpen, Monitor, Plus, Settings, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { StatusIndicator } from "@/components/StatusIndicator";
import type { FrontendServer } from "@/lib/api";
import { cn } from "@/lib/utils";

import {
  formatTabName,
  type SidePanelMode,
  type Tab,
} from "./model";

export function TerminalHeader({
  activeTab,
  activeServer,
  tabs,
  activeTabId,
  sidePanelMode,
  t,
  addTab,
  closeTab,
  revealUiPanel,
  setActiveTabId,
  setSettingsOpen,
  setSidePanelMode,
}: {
  activeTab: Tab;
  activeServer: FrontendServer;
  tabs: Tab[];
  activeTabId: string;
  sidePanelMode: SidePanelMode;
  t: (key: string) => string;
  addTab: () => void;
  closeTab: (tabId: string) => void;
  revealUiPanel: () => void;
  setActiveTabId: (tabId: string) => void;
  setSettingsOpen: (open: boolean) => void;
  setSidePanelMode: Dispatch<SetStateAction<SidePanelMode>>;
}) {
  return (
    <div className="shrink-0 border-b border-border/80 bg-background/95 py-2 pl-16 pr-3 sm:px-3">
      <div className="flex flex-wrap items-center gap-2">
        <Link
          to="/servers"
          className="inline-flex h-10 shrink-0 items-center gap-2 rounded-lg px-3 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <ArrowLeft className="h-4 w-4" />
          Назад
        </Link>

        <div className="flex h-10 min-w-0 shrink-0 items-center gap-2 rounded-lg border border-border/70 bg-card/60 px-3">
          <StatusIndicator
            status={activeTab.status === "connected" ? "online" : activeTab.status === "error" ? "offline" : "unknown"}
            showLabel={false}
          />
          <span className="max-w-40 truncate text-sm font-medium text-foreground sm:max-w-56">
            {formatTabName(activeTab)}
          </span>
          <span className="hidden truncate text-[11px] text-muted-foreground lg:inline">
            {activeServer.username}@{activeServer.host}:{activeServer.port}
          </span>
        </div>

        <div className="min-w-[260px] flex-1">
          <div className="flex items-center gap-1 overflow-x-auto rounded-lg border border-border/70 bg-card/40 p-1">
            {tabs.map((tab) => (
              <div
                key={tab.id}
                className={cn(
                  "group flex h-10 shrink-0 items-center rounded-lg border transition-colors",
                  tab.id === activeTabId
                    ? "border-border bg-background text-foreground"
                    : "border-transparent bg-transparent text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
                )}
              >
                <button
                  type="button"
                  onClick={() => setActiveTabId(tab.id)}
                  className="flex h-full min-w-0 items-center gap-2 rounded-l-lg px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  aria-current={tab.id === activeTabId ? "page" : undefined}
                >
                  <StatusIndicator
                    status={tab.status === "connected" ? "online" : tab.status === "error" ? "offline" : "unknown"}
                    showLabel={false}
                  />
                  <span className="max-w-40 truncate">{formatTabName(tab)}</span>
                </button>
                {tabs.length > 1 ? (
                  <button
                    type="button"
                    aria-label={`Закрыть вкладку ${formatTabName(tab)}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      closeTab(tab.id);
                    }}
                    className="mr-1 flex h-8 w-8 items-center justify-center rounded-md opacity-60 transition-colors hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                ) : null}
              </div>
            ))}

            <button
              type="button"
              onClick={addTab}
              className="flex h-10 shrink-0 items-center gap-2 rounded-lg border border-dashed border-border/70 px-3 text-sm text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="Подключить сервер"
              title="Подключить сервер"
            >
              <Plus className="h-4 w-4" />
              Сервер
            </button>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1 rounded-lg border border-border/70 bg-card/40 p-1">
          <Button
            type="button"
            size="sm"
            variant={sidePanelMode === "files" ? "secondary" : "ghost"}
            className="h-10 gap-2 px-3 text-sm"
            onClick={() => setSidePanelMode((current) => (current === "files" ? "none" : "files"))}
            aria-pressed={sidePanelMode === "files"}
            title={sidePanelMode === "files" ? "Скрыть файловую панель" : "Показать файловую панель"}
          >
            <FolderOpen className="h-4 w-4" />
            SFTP
          </Button>
          {activeServer.server_type === "ssh" ? (
            <Button
              type="button"
              size="sm"
              variant={sidePanelMode === "ui" ? "secondary" : "ghost"}
              className="h-10 gap-2 px-3 text-sm"
              onClick={() => {
                if (sidePanelMode === "ui") {
                  setSidePanelMode("none");
                  return;
                }
                revealUiPanel();
              }}
              aria-pressed={sidePanelMode === "ui"}
              title={sidePanelMode === "ui" ? "Скрыть Linux Workspace" : "Показать Linux Workspace"}
            >
              <Monitor className="h-4 w-4" />
              Linux
            </Button>
          ) : null}
          <Button
            type="button"
            size="sm"
            variant={sidePanelMode === "ai" ? "secondary" : "ghost"}
            className="h-10 gap-2 px-3 text-sm"
            onClick={() => setSidePanelMode((current) => (current === "ai" ? "none" : "ai"))}
            aria-pressed={sidePanelMode === "ai"}
            title={sidePanelMode === "ai" ? "Скрыть AI" : "Показать AI"}
          >
            <Bot className="h-4 w-4" />
            AI
          </Button>
          <Button
            type="button"
            size="icon"
            variant="ghost"
            onClick={() => setSettingsOpen(true)}
            aria-label={t("terminal.settingsBtn")}
            title={t("terminal.settingsBtn")}
          >
            <Settings className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
