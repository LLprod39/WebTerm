import { Link } from "react-router-dom";
import type { Dispatch, SetStateAction } from "react";
import { ArrowLeft, ShieldCheck, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { StatusIndicator } from "@/components/StatusIndicator";
import type { FrontendServer } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ActionIcons, TerminalIcons } from "@/lib/app-icons";

import {
  formatTabName,
  type SidePanelMode,
  type Tab,
} from "./model";

function statusTone(status: Tab["status"]): "online" | "offline" | "unknown" {
  if (status === "connected") return "online";
  if (status === "error") return "offline";
  return "unknown";
}

export function TerminalHeader({
  activeTab,
  activeServer,
  readOnlyMode,
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
  readOnlyMode: boolean;
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
  const sessionTitle = `${formatTabName(activeTab)} · ${endpoint} · ${activeStatus}`;

  return (
    <header
      className="shrink-0 border-b border-border/80 bg-background/95 pl-12 pr-2 sm:pl-4 sm:pr-3"
      title={sessionTitle}
    >
      {/* Single compact toolbar: back | tabs | panels */}
      <div className="flex h-10 items-center gap-1.5 sm:h-11 sm:gap-2">
        <Link
          to="/servers"
          className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:w-auto sm:gap-1.5 sm:px-2"
          title={t("common.back")}
          aria-label={t("common.back")}
        >
          <ArrowLeft className="h-4 w-4" />
          <span className="hidden text-xs font-medium sm:inline">{t("common.back")}</span>
        </Link>

        <div className="hidden h-5 w-px shrink-0 bg-border/70 sm:block" aria-hidden />

        {/* Session tabs — main identity (status + name live here) */}
        <div className="flex min-w-0 flex-1 items-center gap-0.5 overflow-x-auto">
          {tabs.map((tab) => {
            const isActive = tab.id === activeTabId;
            return (
              <div
                key={tab.id}
                className={cn(
                  "group flex h-8 shrink-0 items-center rounded-md border transition-colors",
                  isActive
                    ? "border-primary/40 bg-primary/10 text-foreground"
                    : "border-transparent text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
                )}
              >
                <button
                  type="button"
                  onClick={() => setActiveTabId(tab.id)}
                  className="flex h-8 min-w-0 items-center gap-1.5 rounded-md px-2 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:px-2.5 sm:text-[13px]"
                  aria-current={isActive ? "page" : undefined}
                  title={
                    isActive
                      ? `${formatTabName(tab)} · ${endpoint}`
                      : formatTabName(tab)
                  }
                >
                  <StatusIndicator status={statusTone(tab.status)} showLabel={false} />
                  <span className="max-w-28 truncate sm:max-w-40">{formatTabName(tab)}</span>
                </button>
                {tabs.length > 1 ? (
                  <button
                    type="button"
                    aria-label={`${t("terminal.closeTab")} ${formatTabName(tab)}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      closeTab(tab.id);
                    }}
                    className="mr-0.5 flex h-6 w-6 items-center justify-center rounded opacity-0 transition-opacity hover:bg-destructive/10 hover:text-destructive group-hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:opacity-70"
                  >
                    <X className="h-3 w-3" />
                  </button>
                ) : null}
              </div>
            );
          })}

          <button
            type="button"
            onClick={addTab}
            className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-dashed border-border/70 text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:w-auto sm:gap-1 sm:px-2"
            aria-label={t("terminal.connectServer")}
            title={t("terminal.connectServer")}
          >
            <ActionIcons.add className="h-3.5 w-3.5" strokeWidth={1.5} />
            <span className="hidden text-xs sm:inline">{t("terminal.server")}</span>
          </button>
        </div>

        {/* Endpoint chip — only when space allows; full string on hover via header title */}
        <div
          className="hidden min-w-0 max-w-[14rem] truncate font-mono text-[11px] leading-none text-muted-foreground xl:block"
          title={endpoint}
        >
          {endpoint}
        </div>

        {/* Panel toggles — icon-first to free vertical space */}
        <div className="flex shrink-0 items-center gap-0.5 rounded-md border border-border/60 bg-card/50 p-0.5">
          <Button
            type="button"
            size="sm"
            variant={sidePanelMode === "files" ? "secondary" : "ghost"}
            className="h-7 gap-1 px-1.5 text-xs sm:px-2"
            onClick={() => setSidePanelMode((current) => (current === "files" ? "none" : "files"))}
            aria-pressed={sidePanelMode === "files"}
            title={sidePanelMode === "files" ? t("terminal.hideFiles") : t("terminal.showFiles")}
          >
            <TerminalIcons.files className="h-3.5 w-3.5" strokeWidth={1.5} />
            <span className="hidden md:inline">{t("terminal.filesPanel")}</span>
          </Button>
          {activeServer.server_type === "ssh" ? (
            <Button
              type="button"
              size="sm"
              variant={sidePanelMode === "ui" ? "secondary" : "ghost"}
              className="h-7 gap-1 px-1.5 text-xs sm:px-2"
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
              <TerminalIcons.workspace className="h-3.5 w-3.5" strokeWidth={1.5} />
              <span className="hidden md:inline">{t("terminal.workspacePanel")}</span>
            </Button>
          ) : null}
          <Button
            type="button"
            size="sm"
            variant={sidePanelMode === "ai" ? "secondary" : "ghost"}
            className="h-7 gap-1 px-1.5 text-xs sm:px-2"
            onClick={() => setSidePanelMode((current) => (current === "ai" ? "none" : "ai"))}
            aria-pressed={sidePanelMode === "ai"}
            title={sidePanelMode === "ai" ? t("terminal.hideAi") : t("terminal.showAi")}
          >
            <TerminalIcons.ai className="h-3.5 w-3.5" strokeWidth={1.5} />
            <span className="hidden md:inline">{t("terminal.aiPanel")}</span>
          </Button>
          <Button
            type="button"
            size="icon"
            variant="ghost"
            className="h-7 w-7"
            onClick={() => setSettingsOpen(true)}
            aria-label={t("terminal.settingsBtn")}
            title={t("terminal.settingsBtn")}
          >
            <TerminalIcons.settings className="h-3.5 w-3.5" strokeWidth={1.5} />
          </Button>
        </div>
      </div>
      {readOnlyMode ? (
        <div
          className="flex items-start gap-2 border-t border-primary/20 px-1 py-2 text-xs leading-5 text-foreground/80 sm:items-center sm:px-2"
          role="status"
          aria-live="polite"
          aria-atomic="true"
        >
          <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary sm:mt-0" aria-hidden="true" />
          <p>
            <span className="font-medium text-foreground">{t("terminal.readOnlyNoticeTitle")}</span>{" "}
            {t("terminal.readOnlyNoticeDescription")}
          </p>
        </div>
      ) : null}
    </header>
  );
}
