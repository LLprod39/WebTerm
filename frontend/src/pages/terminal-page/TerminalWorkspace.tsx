import type { Dispatch, MouseEvent, MutableRefObject, SetStateAction } from "react";
import type { ITheme } from "@xterm/xterm";

import {
  XTerminal,
  type TerminalConnectionStatus,
  type TerminalHandle,
} from "@/components/terminal/XTerminal";
import { AiPanel } from "@/components/terminal/AiPanel";
import type {
  AiAssistantSettings,
  AiChatMode,
  AiCommand,
  AiExecutionMode,
  AiMessage,
} from "@/components/terminal/ai-types";
import { LinuxUiPanel } from "@/components/terminal/LinuxUiPanel";
import { SftpPanel, type SftpPanelHandle } from "@/components/terminal/SftpPanel";
import { CompletionOverlay } from "@/components/terminal/CompletionOverlay";
import type { FrontendServer } from "@/lib/api";
import type { TerminalPrefs } from "@/api/terminal-preferences";
import type { InputBufResult } from "@/hooks/useTerminalInputBuffer";

import {
  findServer,
  nextId,
  type SidePanelMode,
  type Tab,
  type TabAiState,
} from "./model";

export function TerminalWorkspace({
  tabs,
  servers,
  activeTabId,
  sidePanelMode,
  sidePanelWidth,
  terminalHiddenByPanel,
  isUiMode,
  isCompactViewport,
  resolvedTheme,
  termPrefs,
  effectiveTerminalFontSize,
  effectiveTerminalLineHeight,
  inputBuf,
  terminalRefs,
  sftpRefs,
  getTabCwdRef,
  startDrag,
  updateTabStatus,
  updateTabAiState,
  handleTabFileDrop,
  handleTabWsEvent,
  handleTerminalFileClick,
  setSidePanelMode,
  aiMessages,
  isAiGenerating,
  activeChatMode,
  activeExecutionMode,
  activeAiSettings,
  handleSendAi,
  handleStopAi,
  handleConfirm,
  handleCancel,
  handleReply,
  handleGenerateReport,
  handleClearAiMemory,
  handleExplainCommand,
  handleSettingsChange,
  handleSaveAiDefaults,
  handleResetAiPreferences,
  handleClearChat,
  handleChatModeChange,
  handleModeChange,
}: {
  tabs: Tab[];
  servers: FrontendServer[];
  activeTabId: string;
  sidePanelMode: SidePanelMode;
  sidePanelWidth: number | string;
  terminalHiddenByPanel: boolean;
  isUiMode: boolean;
  isCompactViewport: boolean;
  resolvedTheme: ITheme;
  termPrefs: TerminalPrefs;
  effectiveTerminalFontSize: number;
  effectiveTerminalLineHeight: number;
  inputBuf: InputBufResult;
  terminalRefs: MutableRefObject<Record<string, TerminalHandle | null>>;
  sftpRefs: MutableRefObject<Record<string, SftpPanelHandle | null>>;
  getTabCwdRef: (tabId: string) => MutableRefObject<string>;
  startDrag: (event: MouseEvent<HTMLDivElement>) => void;
  updateTabStatus: (tabId: string, status: TerminalConnectionStatus) => void;
  updateTabAiState: (tabId: string, updater: (state: TabAiState) => TabAiState) => void;
  handleTabFileDrop: (tabId: string, files: File[]) => void;
  handleTabWsEvent: (tabId: string, serverId: number, payload: Record<string, unknown>) => void;
  handleTerminalFileClick: (tabId: string, serverId: number, absolutePath: string) => void;
  setSidePanelMode: Dispatch<SetStateAction<SidePanelMode>>;
  aiMessages: AiMessage[];
  isAiGenerating: boolean;
  activeChatMode: AiChatMode;
  activeExecutionMode: AiExecutionMode;
  activeAiSettings: AiAssistantSettings;
  handleSendAi: (text: string) => void;
  handleStopAi: () => void;
  handleConfirm: (id: number) => void;
  handleCancel: (id: number) => void;
  handleReply: (qId: string, text: string) => void;
  handleGenerateReport: (force?: boolean) => void;
  handleClearAiMemory: () => void;
  handleExplainCommand: (cmd: AiCommand) => void;
  handleSettingsChange: (settings: AiAssistantSettings) => void;
  handleSaveAiDefaults: () => void;
  handleResetAiPreferences: () => void;
  handleClearChat: () => void;
  handleChatModeChange: (chatMode: AiChatMode) => void;
  handleModeChange: (mode: AiExecutionMode) => void;
}) {
  return (
    <div className="flex min-h-0 flex-1">
      <div
        className={terminalHiddenByPanel ? "hidden" : "min-h-0 flex-1 p-0"}
        style={{ backgroundColor: resolvedTheme.background ?? "#0a0e14" }}
      >
        <div className="relative h-full w-full">
          {tabs.map((tab) => (
            <div
              key={tab.id}
              className={`absolute inset-0 ${tab.id === activeTabId ? "z-10" : "pointer-events-none opacity-0"}`}
              aria-hidden={tab.id === activeTabId ? undefined : true}
            >
              <XTerminal
                ref={(handle) => {
                  terminalRefs.current[tab.id] = handle;
                }}
                serverId={tab.serverId}
                active={tab.id === activeTabId}
                themeOverride={resolvedTheme}
                fontSize={effectiveTerminalFontSize}
                fontFamily={termPrefs.font_family}
                lineHeight={effectiveTerminalLineHeight}
                cursorStyle={termPrefs.cursor_style}
                cursorBlink={termPrefs.cursor_blink}
                scrollback={termPrefs.scrollback}
                onStatusChange={(status) => updateTabStatus(tab.id, status)}
                onError={(message) =>
                  updateTabAiState(tab.id, (state) => ({
                    ...state,
                    messages: [...state.messages, { id: nextId(), role: "system", type: "text", content: message }],
                  }))
                }
                onFilesDrop={(files) => handleTabFileDrop(tab.id, files)}
                onEvent={(payload) => handleTabWsEvent(tab.id, tab.serverId, payload)}
                onInterceptInput={tab.id === activeTabId ? inputBuf.interceptInput : undefined}
                cwdRef={getTabCwdRef(tab.id)}
                onFileClick={(absolutePath) => handleTerminalFileClick(tab.id, tab.serverId, absolutePath)}
              />
            </div>
          ))}
          <CompletionOverlay
            suggestions={inputBuf.suggestions}
            selectedIdx={inputBuf.selectedIdx}
            visible={inputBuf.suggestions.length > 0}
          />
        </div>
      </div>

      <div
        className={`relative min-h-0 shrink-0 overflow-hidden transition-[width] ${sidePanelMode === "none" || isUiMode || isCompactViewport ? "border-l-0" : "border-l border-border"}`}
        style={{ width: sidePanelWidth }}
      >
        {sidePanelMode !== "none" && !isUiMode && !isCompactViewport ? (
          <div
            onMouseDown={startDrag}
            className="absolute bottom-0 left-0 top-0 z-20 w-1 cursor-col-resize select-none transition-colors hover:bg-primary/40 active:bg-primary/60"
            title="Перетащите для изменения ширины"
          />
        ) : null}

        {sidePanelMode === "ai" ? (
          <div className="flex h-full min-h-0 flex-col">
            <div className="min-h-0 flex-1 overflow-hidden">
              <AiPanel
                onClose={() => setSidePanelMode("none")}
                onSend={handleSendAi}
                onStop={handleStopAi}
                onConfirm={handleConfirm}
                onCancel={handleCancel}
                onReply={handleReply}
                onGenerateReport={handleGenerateReport}
                onClearMemory={handleClearAiMemory}
                onExplainCommand={handleExplainCommand}
                onSettingsChange={handleSettingsChange}
                onSaveDefaults={handleSaveAiDefaults}
                onResetToDefaults={handleResetAiPreferences}
                onClearChat={handleClearChat}
                messages={aiMessages}
                isGenerating={isAiGenerating}
                chatMode={activeChatMode}
                onChatModeChange={handleChatModeChange}
                executionMode={activeExecutionMode}
                settings={activeAiSettings}
                onModeChange={handleModeChange}
              />
            </div>
          </div>
        ) : null}

        {sidePanelMode === "ui" ? (
          <div className="flex h-full min-h-0 flex-col">
            <div className="relative h-full min-h-0 flex-1">
              {tabs.map((tab) => {
                const tabServer = findServer(servers, tab.serverId);
                if (!tabServer) return null;
                return (
                  <div
                    key={tab.id}
                    className={`absolute inset-0 ${tab.id === activeTabId ? "z-10" : "pointer-events-none opacity-0"}`}
                    aria-hidden={tab.id === activeTabId ? undefined : true}
                  >
                    <LinuxUiPanel
                      server={tabServer}
                      active={tab.id === activeTabId}
                      onClose={() => setSidePanelMode("none")}
                      onOpenAi={() => setSidePanelMode("ai")}
                    />
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}

        {sidePanelMode === "files" ? (
          <div className="flex h-full min-h-0 flex-col">
            <div className="relative h-full min-h-0 flex-1">
              {tabs.map((tab) => {
                const tabServer = findServer(servers, tab.serverId);
                if (!tabServer) return null;
                return (
                  <div
                    key={tab.id}
                    className={`absolute inset-0 ${tab.id === activeTabId ? "z-10" : "pointer-events-none opacity-0"}`}
                    aria-hidden={tab.id === activeTabId ? undefined : true}
                  >
                    <SftpPanel
                      ref={(handle) => {
                        sftpRefs.current[tab.id] = handle;
                      }}
                      server={tabServer}
                      active={tab.id === activeTabId}
                    />
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
