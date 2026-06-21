import { Link } from "react-router-dom";
import type { Dispatch, SetStateAction } from "react";
import { ArrowLeft, Bot, FolderOpen, Monitor, Plus, Server, Settings, X } from "lucide-react";

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
  const activeStatus =
    activeTab.status === "connected"
      ? t("terminal.statusConnected")
      : activeTab.status === "error"
        ? t("terminal.statusError")
        : t("terminal.statusConnecting");
  const endpoint = `${activeServer.username}@${activeServer.host}:${activeServer.port}`;

  return (
    <header className="shrink-0 border-b border-border/80 bg-background/95 pl-14 pr-3 sm:px-4">
      <div className="flex min-h-[4.25rem] flex-col gap-3 py-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <Link
            to="/servers"
            className="inline-flex h-10 shrink-0 items-center gap-2 rounded-lg px-3 text-sm text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <ArrowLeft className="h-4 w-4" />
            {t("common.back")}
          </Link>

          <div className="hidden h-8 w-px bg-border/80 sm:block" />

          <div className="min-w-0">
            <div className="flex min-w-0 items-center gap-2">
              <Server className="h-4 w-4 shrink-0 text-primary" />
              <h1 className="truncate text-base font-semibold leading-6 text-foreground">
                {formatTabName(activeTab)}
              </h1>
              <span className="inline-flex min-h-7 items-center gap-1.5 rounded-md border border-info/30 bg-info/10 px-2.5 text-xs font-medium text-info">
                <StatusIndicator
                  status={activeTab.status === "connected" ? "online" : activeTab.status === "error" ? "offline" : "unknown"}
                  showLabel={false}
                />
                {activeStatus}
              </span>
            </div>
            <div className="mt-1 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-xs leading-4 text-muted-foreground">
              <span className="font-mono">{endpoint}</span>
              <span aria-hidden>·</span>
              <span>{tabs.length} {t(tabs.length === 1 ? "terminal.sessionOne" : "terminal.sessionMany")}</span>
            </div>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1 rounded-lg border border-border/70 bg-card/60 p-1">
          <Button
            type="button"
            size="sm"
            variant={sidePanelMode === "files" ? "secondary" : "ghost"}
            className="h-10 gap-2 px-3 text-sm"
            onClick={() => setSidePanelMode((current) => (current === "files" ? "none" : "files"))}
            aria-pressed={sidePanelMode === "files"}
            title={sidePanelMode === "files" ? t("terminal.hideFiles") : t("terminal.showFiles")}
          >
            <FolderOpen className="h-4 w-4" />
            {t("terminal.filesPanel")}
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
              title={sidePanelMode === "ui" ? t("terminal.hideWorkspace") : t("terminal.showWorkspace")}
            >
              <Monitor className="h-4 w-4" />
              {t("terminal.workspacePanel")}
            </Button>
          ) : null}
          <Button
            type="button"
            size="sm"
            variant={sidePanelMode === "ai" ? "secondary" : "ghost"}
            className="h-10 gap-2 px-3 text-sm"
            onClick={() => setSidePanelMode((current) => (current === "ai" ? "none" : "ai"))}
            aria-pressed={sidePanelMode === "ai"}
            title={sidePanelMode === "ai" ? t("terminal.hideAi") : t("terminal.showAi")}
          >
            <Bot className="h-4 w-4" />
            {t("terminal.aiPanel")}
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

      <div className="flex items-center gap-2 border-t border-border/50 py-2">
        <div className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
          {tabs.map((tab) => (
            <div
              key={tab.id}
              className={cn(
                "group flex min-h-10 shrink-0 items-center rounded-lg border transition-colors",
                tab.id === activeTabId
                  ? "border-primary/50 bg-primary/10 text-foreground"
                  : "border-transparent bg-transparent text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
              )}
            >
              <button
                type="button"
                onClick={() => setActiveTabId(tab.id)}
                className="flex h-10 min-w-0 items-center gap-2 rounded-l-lg px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                aria-current={tab.id === activeTabId ? "page" : undefined}
              >
                <StatusIndicator
                  status={tab.status === "connected" ? "online" : tab.status === "error" ? "offline" : "unknown"}
                  showLabel={false}
                />
                <span className="max-w-48 truncate">{formatTabName(tab)}</span>
              </button>
              {tabs.length > 1 ? (
                <button
                  type="button"
                  aria-label={`${t("terminal.closeTab")} ${formatTabName(tab)}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    closeTab(tab.id);
                  }}
                  className="mr-1 flex h-8 w-8 items-center justify-center rounded-md opacity-70 transition-colors hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              ) : null}
            </div>
          ))}

          <button
            type="button"
            onClick={addTab}
            className="flex min-h-10 shrink-0 items-center gap-2 rounded-lg border border-dashed border-border/80 px-3 text-sm text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label={t("terminal.connectServer")}
            title={t("terminal.connectServer")}
          >
            <Plus className="h-4 w-4" />
            {t("terminal.server")}
          </button>
        </div>
      </div>
    </header>
  );
}
