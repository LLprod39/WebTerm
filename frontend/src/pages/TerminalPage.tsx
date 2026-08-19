import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent as ReactMouseEvent, type MutableRefObject } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import type { TerminalConnectionStatus, TerminalHandle } from "@/components/terminal/XTerminal";
import { ServerPicker } from "@/components/terminal/ServerPicker";
import { cloneAiPreferences, cloneAiSettings, readStoredAiPreferences } from "@/components/terminal/ai-preferences";
import type { AiAssistantSettings, AiChatMode, AiExecutionMode, AiPreferences } from "@/components/terminal/ai-types";
import type { SftpPanelHandle } from "@/components/terminal/SftpPanel";
import { toast } from "@/hooks/use-toast";
import { fetchAuthSession, fetchFrontendBootstrap, type FrontendServer } from "@/lib/api";
import { resolveTheme } from "@/components/terminal/TerminalThemes";
import { TerminalSettingsPanel } from "@/components/terminal/TerminalSettingsPanel";
import { FileEditorModal } from "@/components/editor/FileEditorModal";
import { ConfirmDialog } from "@/components/system/ConfirmDialog";
import { useEditorInterceptor } from "@/hooks/useEditorInterceptor";
import { useI18n } from "@/lib/i18n";
import { useTerminalPreferences } from "@/hooks/useTerminalPreferences";
import { useTerminalInputBuffer } from "@/hooks/useTerminalInputBuffer";
import { TerminalHeader } from "./terminal-page/TerminalHeader";
import { TerminalQueryState } from "./terminal-page/TerminalQueryState";
import { TerminalWorkspace } from "./terminal-page/TerminalWorkspace";
import {
  createEmptyAiState,
  createTab,
  findServer,
  isTerminalReadOnlyMode,
  mapStatus,
  nextId,
  type SidePanelMode,
  type Tab,
  type TabAiState,
} from "./terminal-page/model";
import { useTerminalAiActions } from "./terminal-page/useTerminalAiActions";
import { handleTerminalPageWsEvent } from "./terminal-page/ws-events";
export default function TerminalPage() {
  const { id } = useParams<{ id: string }>();
  const requestedId = useMemo(() => Number(id || 0), [id]);
  const terminalRefs = useRef<Record<string, TerminalHandle | null>>({});
  const sftpRefs = useRef<Record<string, SftpPanelHandle | null>>({});
  const tabCwdRefs = useRef<Record<string, MutableRefObject<string>>>({});
  const activeTabIdRef = useRef("");
  const { data, isLoading, error } = useQuery({
    queryKey: ["frontend", "bootstrap"],
    queryFn: fetchFrontendBootstrap,
    staleTime: 20_000,
  });
  const { data: authData } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const canUseLinuxUi = Boolean(authData?.user?.is_staff);
  const servers = useMemo(() => data?.servers ?? [], [data?.servers]);
  const defaultServer = findServer(servers, requestedId) || servers[0];
  const [tabs, setTabs] = useState<Tab[]>([]);
  const [activeTabId, setActiveTabId] = useState("");
  const [tabAiState, setTabAiState] = useState<Record<string, TabAiState>>({});
  const [tabAiPreferences, setTabAiPreferences] = useState<Record<string, AiPreferences>>({});
  const [showServerPicker, setShowServerPicker] = useState(false);
  const [sidePanelMode, setSidePanelMode] = useState<SidePanelMode>("none");
  const [panelWidth, setPanelWidth] = useState(380);
  const [globalAiPreferences, setGlobalAiPreferences] = useState<AiPreferences>(() => readStoredAiPreferences());
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [pendingCloseTabId, setPendingCloseTabId] = useState<string | null>(null);
  const [isCompactViewport, setIsCompactViewport] = useState(() =>
    typeof window === "undefined" ? false : window.matchMedia("(max-width: 640px)").matches,
  );
  const { t } = useI18n();
  const { editorState, closeEditor, openFileAtPath, handleWsEvent: handleEditorWsEvent } = useEditorInterceptor();
  const { prefs: termPrefs, update: updateTermPrefs } = useTerminalPreferences();
  const resolvedTheme = useMemo(
    () => resolveTheme(termPrefs.theme_name, termPrefs.theme_colors),
    [termPrefs.theme_name, termPrefs.theme_colors],
  );
  const isDragging = useRef(false);
  const dragStartX = useRef(0);
  const dragStartWidth = useRef(0);
  useEffect(() => {
    activeTabIdRef.current = activeTabId;
  }, [activeTabId]);
  useEffect(() => {
    if (typeof window === "undefined") return;
    const media = window.matchMedia("(max-width: 640px)");
    const syncViewport = () => setIsCompactViewport(media.matches);
    syncViewport();
    media.addEventListener("change", syncViewport);
    return () => media.removeEventListener("change", syncViewport);
  }, []);
  const updateTabAiState = useCallback((tabId: string, updater: (state: TabAiState) => TabAiState) => {
    if (!tabId) return;
    setTabAiState((prev) => ({
      ...prev,
      [tabId]: updater(prev[tabId] || createEmptyAiState()),
    }));
  }, []);
  const updateActiveTabAiState = useCallback((updater: (state: TabAiState) => TabAiState) => {
    const tabId = activeTabIdRef.current;
    if (!tabId) return;
    updateTabAiState(tabId, updater);
  }, [updateTabAiState]);
  const updateTabAiPreferences = useCallback((tabId: string, updater: (state: AiPreferences) => AiPreferences) => {
    if (!tabId) return;
    setTabAiPreferences((prev) => ({
      ...prev,
      [tabId]: updater(prev[tabId] || cloneAiPreferences(globalAiPreferences)),
    }));
  }, [globalAiPreferences]);
  const updateActiveTabAiPreferences = useCallback((updater: (state: AiPreferences) => AiPreferences) => {
    const tabId = activeTabIdRef.current;
    if (!tabId) return;
    updateTabAiPreferences(tabId, updater);
  }, [updateTabAiPreferences]);
  const getTabCwdRef = useCallback((tabId: string): MutableRefObject<string> => {
    if (!tabCwdRefs.current[tabId]) {
      tabCwdRefs.current[tabId] = { current: "/" };
    }
    return tabCwdRefs.current[tabId];
  }, []);
  const handleTerminalFileClick = useCallback(
    (_tabId: string, serverId: number, absolutePath: string) => {
      openFileAtPath(serverId, absolutePath);
      toast({
        title: t("terminal.fileLinkOpened"),
        description: absolutePath,
      });
    },
    [openFileAtPath, t],
  );
  useEffect(() => {
    if (!defaultServer || tabs.length > 0) return;
    const firstId = nextId();
    setTabs([createTab(defaultServer, [], firstId)]);
    setActiveTabId(firstId);
    setTabAiState((prev) => ({
      ...prev,
      [firstId]: prev[firstId] || createEmptyAiState(),
    }));
    setTabAiPreferences((prev) => ({
      ...prev,
      [firstId]: prev[firstId] || cloneAiPreferences(globalAiPreferences),
    }));
  }, [defaultServer, globalAiPreferences, tabs.length]);
  useEffect(() => {
    if (!tabs.length) return;
    if (activeTabId && tabs.some((tab) => tab.id === activeTabId)) return;
    setActiveTabId(tabs[0].id);
  }, [tabs, activeTabId]);
  useEffect(() => {
    const availableServerIds = new Set(servers.map((server) => server.id));
    if (!tabs.length) return;
    const removedTabIds = tabs.filter((tab) => !availableServerIds.has(tab.serverId)).map((tab) => tab.id);
    if (!removedTabIds.length) return;
    setTabs((prev) => prev.filter((tab) => availableServerIds.has(tab.serverId)));
    setTabAiState((prev) => {
      const next = { ...prev };
      for (const tabId of removedTabIds) {
        delete next[tabId];
        delete terminalRefs.current[tabId];
        delete sftpRefs.current[tabId];
      }
      return next;
    });
    setTabAiPreferences((prev) => {
      const next = { ...prev };
      for (const tabId of removedTabIds) {
        delete next[tabId];
      }
      return next;
    });
  }, [servers, tabs]);
  const activeTab = tabs.find((tab) => tab.id === activeTabId) || tabs[0];
  const inputBuf = useTerminalInputBuffer({
    serverId: activeTab?.serverId ?? null,
    enabled: true,
  });
  const activeServer = activeTab ? findServer(servers, activeTab.serverId) : null;
  const readOnlyMode = activeServer ? isTerminalReadOnlyMode(activeServer, authData?.user) : false;
  const activeAiState = activeTabId ? tabAiState[activeTabId] || createEmptyAiState() : createEmptyAiState();
  const activeAiPreferences =
    activeTabId && tabAiPreferences[activeTabId]
      ? tabAiPreferences[activeTabId]
      : globalAiPreferences;
  const activeChatMode = activeAiPreferences.chatMode;
  const activeAiSettings = activeAiPreferences.settings;
  const activeExecutionMode = activeAiPreferences.executionMode;
  const aiMessages = activeAiState.messages;
  const isAiGenerating = activeAiState.isGenerating;
  const isUiMode = sidePanelMode === "ui";
  const isMobileSidePanelOpen = isCompactViewport && sidePanelMode !== "none";
  const terminalHiddenByPanel = isUiMode || isMobileSidePanelOpen;
  const sidePanelWidth = sidePanelMode === "none" ? 0 : isUiMode || isCompactViewport ? "100%" : panelWidth;
  const effectiveTerminalFontSize = isCompactViewport ? Math.min(termPrefs.font_size, 14) : termPrefs.font_size;
  const effectiveTerminalLineHeight = isCompactViewport ? Math.max(termPrefs.line_height, 1.2) : termPrefs.line_height;
  const openSessionCounts = useMemo(() => {
    const counts = new Map<number, number>();
    for (const tab of tabs) {
      counts.set(tab.serverId, (counts.get(tab.serverId) ?? 0) + 1);
    }
    return counts;
  }, [tabs]);
  const addTab = useCallback(() => {
    if (!servers.length) return;
    setShowServerPicker(true);
  }, [servers.length]);
  const handleServerSelect = useCallback((server: FrontendServer) => {
    const tabId = nextId();
    setTabs((prev) => [...prev, createTab(server, prev, tabId)]);
    setActiveTabId(tabId);
    setTabAiState((prev) => ({
      ...prev,
      [tabId]: prev[tabId] || createEmptyAiState(),
    }));
    setTabAiPreferences((prev) => ({
      ...prev,
      [tabId]: prev[tabId] || cloneAiPreferences(globalAiPreferences),
    }));
  }, [globalAiPreferences]);
  const closeTab = useCallback((tabId: string) => {
    setTabs((prev) => {
      if (prev.length <= 1) return prev;
      const next = prev.filter((tab) => tab.id !== tabId);
      setActiveTabId((current) => (current === tabId ? next[0]?.id || "" : current));
      return next;
    });
    delete terminalRefs.current[tabId];
    delete sftpRefs.current[tabId];
    setTabAiState((prev) => {
      const next = { ...prev };
      delete next[tabId];
      return next;
    });
    setTabAiPreferences((prev) => {
      const next = { ...prev };
      delete next[tabId];
      return next;
    });
  }, []);
  const requestCloseTab = useCallback((tabId: string) => {
    if (tabs.length <= 1) return;
    setPendingCloseTabId(tabId);
  }, [tabs.length]);
  const pendingCloseTab = useMemo(
    () => tabs.find((tab) => tab.id === pendingCloseTabId) || null,
    [pendingCloseTabId, tabs],
  );
  const updateTabStatus = useCallback((tabId: string, status: TerminalConnectionStatus) => {
    if (!tabId) return;
    setTabs((prev) => prev.map((tab) => (tab.id === tabId ? { ...tab, status: mapStatus(status) } : tab)));
  }, []);
  const handleModeChange = useCallback((mode: AiExecutionMode) => {
    updateActiveTabAiPreferences((state) => ({
      ...state,
      executionMode: mode,
    }));
  }, [updateActiveTabAiPreferences]);
  const handleChatModeChange = useCallback((chatMode: AiChatMode) => {
    updateActiveTabAiPreferences((state) => ({
      ...state,
      chatMode,
    }));
  }, [updateActiveTabAiPreferences]);
  const handleSettingsChange = useCallback((settings: AiAssistantSettings) => {
    updateActiveTabAiPreferences((state) => ({
      ...state,
      settings: cloneAiSettings(settings),
    }));
  }, [updateActiveTabAiPreferences]);
  const {
    handleSendAi,
    handleStopAi,
    handleConfirm,
    handleCancel,
    handleReply,
    handleGenerateReport,
    handleClearAiMemory,
    handleExplainCommand,
    handleSaveAiDefaults: saveAiDefaults,
    handleResetAiPreferences,
    handleClearChat,
  } = useTerminalAiActions({
    activeTabIdRef,
    terminalRefs,
    tabAiPreferences,
    globalAiPreferences,
    updateTabAiState,
    updateActiveTabAiState,
    updateTabAiPreferences,
    setGlobalAiPreferences,
  });
  const handleSaveAiDefaults = useCallback(() => {
    saveAiDefaults(activeAiPreferences);
  }, [activeAiPreferences, saveAiDefaults]);
  const revealAiPanel = useCallback(() => {
    setSidePanelMode("ai");
  }, []);
  const revealUiPanel = useCallback(() => {
    if (!canUseLinuxUi) return;
    setPanelWidth((current) => Math.max(current, 520));
    setSidePanelMode("ui");
  }, [canUseLinuxUi]);
  const revealAiPanelForTab = useCallback((tabId: string) => {
    if (activeTabIdRef.current === tabId) {
      revealAiPanel();
    }
  }, [revealAiPanel]);
  const startDrag = useCallback((event: ReactMouseEvent<HTMLDivElement>) => {
    isDragging.current = true;
    dragStartX.current = event.clientX;
    dragStartWidth.current = panelWidth;
    event.preventDefault();
  }, [panelWidth]);
  useEffect(() => {
    const onMove = (event: MouseEvent) => {
      if (!isDragging.current) return;
      const diff = dragStartX.current - event.clientX;
      setPanelWidth(Math.max(260, Math.min(720, dragStartWidth.current + diff)));
    };
    const onUp = () => {
      isDragging.current = false;
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);
  const handleTabWsEvent = useCallback((tabId: string, serverId: number, payload: Record<string, unknown>) => {
    handleTerminalPageWsEvent({
      tabId,
      serverId,
      payload,
      handleEditorWsEvent,
      getTabCwdRef,
      revealAiPanelForTab,
      updateTabAiState,
    });
  }, [revealAiPanelForTab, updateTabAiState, handleEditorWsEvent, getTabCwdRef]);
  useEffect(() => {
    if (!activeTabId) return;
    const timer = window.setTimeout(() => {
      terminalRefs.current[activeTabId]?.fit();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [activeTabId]);
  const handleTabFileDrop = useCallback((tabId: string, files: File[]) => {
    if (!files.length) return;
    sftpRefs.current[tabId]?.enqueueUploads(files);
    setSidePanelMode("files");
  }, []);
  useEffect(() => {
    if (sidePanelMode === "ui" && (!canUseLinuxUi || activeServer?.server_type !== "ssh")) {
      setSidePanelMode("none");
    }
  }, [activeServer?.server_type, canUseLinuxUi, sidePanelMode]);
  // Sync intercept_editors pref → SSH consumer
  useEffect(() => {
    for (const tab of tabs) {
      terminalRefs.current[tab.id]?.sendRaw({
        type: "set_editor_intercept",
        enabled: termPrefs.intercept_editors,
      });
    }
  }, [termPrefs.intercept_editors, tabs]);
  if (isLoading || error || !data || !activeTab || !activeServer) {
    return (
      <TerminalQueryState
        isLoading={isLoading}
        error={error}
        hasData={Boolean(data)}
        hasActiveConnection={Boolean(activeTab && activeServer)}
      />
    );
  }
  return (
    <div className="flex h-[100dvh] flex-col bg-background">
      <TerminalHeader
        activeTab={activeTab}
        activeServer={activeServer}
        readOnlyMode={readOnlyMode}
        tabs={tabs}
        activeTabId={activeTabId}
        sidePanelMode={sidePanelMode}
        canUseLinuxUi={canUseLinuxUi}
        t={t}
        addTab={addTab}
        closeTab={requestCloseTab}
        revealUiPanel={revealUiPanel}
        setActiveTabId={setActiveTabId}
        setSettingsOpen={setSettingsOpen}
        setSidePanelMode={setSidePanelMode}
      />
      <TerminalWorkspace
        tabs={tabs}
        servers={servers}
        activeTabId={activeTabId}
        sidePanelMode={sidePanelMode}
        sidePanelWidth={sidePanelWidth}
        terminalHiddenByPanel={terminalHiddenByPanel}
        isUiMode={isUiMode}
        isCompactViewport={isCompactViewport}
        resolvedTheme={resolvedTheme}
        termPrefs={termPrefs}
        effectiveTerminalFontSize={effectiveTerminalFontSize}
        effectiveTerminalLineHeight={effectiveTerminalLineHeight}
        inputBuf={inputBuf}
        terminalRefs={terminalRefs}
        sftpRefs={sftpRefs}
        getTabCwdRef={getTabCwdRef}
        startDrag={startDrag}
        updateTabStatus={updateTabStatus}
        updateTabAiState={updateTabAiState}
        handleTabFileDrop={handleTabFileDrop}
        handleTabWsEvent={handleTabWsEvent}
        handleTerminalFileClick={handleTerminalFileClick}
        setSidePanelMode={setSidePanelMode}
        aiMessages={aiMessages}
        isAiGenerating={isAiGenerating}
        activeChatMode={activeChatMode}
        activeExecutionMode={activeExecutionMode}
        activeAiSettings={activeAiSettings}
        handleSendAi={handleSendAi}
        handleStopAi={handleStopAi}
        handleConfirm={handleConfirm}
        handleCancel={handleCancel}
        handleReply={handleReply}
        handleGenerateReport={handleGenerateReport}
        handleClearAiMemory={handleClearAiMemory}
        handleExplainCommand={handleExplainCommand}
        handleSettingsChange={handleSettingsChange}
        handleSaveAiDefaults={handleSaveAiDefaults}
        handleResetAiPreferences={handleResetAiPreferences}
        handleClearChat={handleClearChat}
        handleChatModeChange={handleChatModeChange}
        handleModeChange={handleModeChange}
      />
      <ServerPicker
        servers={servers}
        open={showServerPicker}
        onClose={() => setShowServerPicker(false)}
        onSelect={handleServerSelect}
        openSessionCounts={openSessionCounts}
      />
      <TerminalSettingsPanel
        prefs={termPrefs}
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        onUpdate={updateTermPrefs}
      />
      <FileEditorModal
        serverId={editorState.serverId ?? (activeTab?.serverId || 0)}
        open={editorState.isOpen}
        initialPath={editorState.filePath}
        initialElevated={editorState.elevated}
        onClose={closeEditor}
      />
      <ConfirmDialog
        open={Boolean(pendingCloseTab)}
        onOpenChange={(open) => {
          if (!open) setPendingCloseTabId(null);
        }}
        title={t("terminal.closeTabTitle")}
        description={t("terminal.closeTabDescription").replace("{name}", pendingCloseTab ? pendingCloseTab.name : "")}
        confirmLabel={t("terminal.closeTabConfirm")}
        cancelLabel={t("terminal.cancel")}
        onConfirm={() => {
          if (pendingCloseTab) {
            closeTab(pendingCloseTab.id);
          }
          setPendingCloseTabId(null);
        }}
      />
    </div>
  );
}
