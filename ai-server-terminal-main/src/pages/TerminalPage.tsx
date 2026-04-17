import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
} from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Bot, FolderOpen, Monitor, Plus, Search, Server, Settings, X } from "lucide-react";
import {
  XTerminal,
  type AiAssistantSettings,
  type AiAutoReportMode,
  type AiChatMode,
  type AiExecutionMode,
  type AiPreferences,
  type TerminalConnectionStatus,
  type TerminalHandle,
} from "@/components/terminal/XTerminal";
import { AiPanel, type AiCommand, type AiMessage } from "@/components/terminal/AiPanel";
import { LinuxUiPanel } from "@/components/terminal/LinuxUiPanel";
import { SftpPanel, type SftpPanelHandle } from "@/components/terminal/SftpPanel";
import { Button } from "@/components/ui/button";
import { StatusIndicator } from "@/components/StatusIndicator";
import { toast } from "@/hooks/use-toast";
import { fetchFrontendBootstrap, type FrontendServer } from "@/lib/api";
import { QueryStateBlock } from "@/components/ui/page-shell";
import { useTerminalPreferences } from "@/hooks/useTerminalPreferences";
import { useTerminalInputBuffer } from "@/hooks/useTerminalInputBuffer";
import { resolveTheme } from "@/components/terminal/TerminalThemes";
import { TerminalSettingsPanel } from "@/components/terminal/TerminalSettingsPanel";
import { CompletionOverlay } from "@/components/terminal/CompletionOverlay";
import { FileEditorModal } from "@/components/editor/FileEditorModal";
import { useEditorInterceptor } from "@/hooks/useEditorInterceptor";
import { useI18n } from "@/lib/i18n";

interface Tab {
  id: string;
  serverId: number;
  name: string;
  sessionNumber: number;
  status: "connected" | "connecting" | "error";
}

interface TabAiState {
  messages: AiMessage[];
  isGenerating: boolean;
}

let idSeq = 0;

function nextId() {
  idSeq += 1;
  return String(idSeq);
}

function createEmptyAiState(): TabAiState {
  return {
    messages: [],
    isGenerating: false,
  };
}

const AI_PREFERENCES_STORAGE_KEY = "terminal_ai_preferences_v1";

const DEFAULT_AI_SETTINGS: AiAssistantSettings = {
  memoryEnabled: true,
  memoryTtlRequests: 6,
  autoReport: "auto",
  confirmDangerousCommands: true,
  whitelistPatterns: [],
  blacklistPatterns: [],
  showSuggestedCommands: true,
  showExecutedCommands: true,
  // A5: dry-run off by default — users opt in explicitly.
  dryRun: false,
};

const DEFAULT_AI_PREFERENCES: AiPreferences = {
  chatMode: "agent",
  executionMode: "auto",
  settings: DEFAULT_AI_SETTINGS,
};

function clampTtl(value: unknown) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return DEFAULT_AI_SETTINGS.memoryTtlRequests;
  return Math.max(1, Math.min(20, Math.round(parsed)));
}

function normalizePatternList(value: unknown) {
  const source = Array.isArray(value) ? value : [];
  const seen = new Set<string>();
  const normalized: string[] = [];

  for (const item of source) {
    const line = String(item || "").trim();
    if (!line) continue;
    const key = line.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    normalized.push(line);
  }

  return normalized.slice(0, 50);
}

function cloneAiSettings(settings: AiAssistantSettings): AiAssistantSettings {
  return {
    ...settings,
    whitelistPatterns: [...settings.whitelistPatterns],
    blacklistPatterns: [...settings.blacklistPatterns],
  };
}

function cloneAiPreferences(preferences: AiPreferences): AiPreferences {
  return {
    chatMode: preferences.chatMode,
    executionMode: preferences.executionMode,
    settings: cloneAiSettings(preferences.settings),
  };
}

function sanitizeAiSettings(value: unknown): AiAssistantSettings {
  const raw = value && typeof value === "object" ? (value as Partial<AiAssistantSettings>) : {};
  const autoReport = raw.autoReport;
  const normalizedAutoReport: AiAutoReportMode =
    autoReport === "on" || autoReport === "off" || autoReport === "auto" ? autoReport : DEFAULT_AI_SETTINGS.autoReport;

  return {
    memoryEnabled: typeof raw.memoryEnabled === "boolean" ? raw.memoryEnabled : DEFAULT_AI_SETTINGS.memoryEnabled,
    memoryTtlRequests: clampTtl(raw.memoryTtlRequests),
    autoReport: normalizedAutoReport,
    confirmDangerousCommands:
      typeof raw.confirmDangerousCommands === "boolean"
        ? raw.confirmDangerousCommands
        : DEFAULT_AI_SETTINGS.confirmDangerousCommands,
    whitelistPatterns: normalizePatternList(raw.whitelistPatterns),
    blacklistPatterns: normalizePatternList(raw.blacklistPatterns),
    showSuggestedCommands:
      typeof raw.showSuggestedCommands === "boolean"
        ? raw.showSuggestedCommands
        : DEFAULT_AI_SETTINGS.showSuggestedCommands,
    showExecutedCommands:
      typeof raw.showExecutedCommands === "boolean"
        ? raw.showExecutedCommands
        : DEFAULT_AI_SETTINGS.showExecutedCommands,
    // A5: read dry-run out of stored prefs with safe default.
    dryRun: typeof raw.dryRun === "boolean" ? raw.dryRun : DEFAULT_AI_SETTINGS.dryRun,
  };
}

function sanitizeAiPreferences(value: unknown): AiPreferences {
  const raw = value && typeof value === "object" ? (value as Partial<AiPreferences>) : {};
  const chatMode = raw.chatMode === "ask" || raw.chatMode === "agent" ? raw.chatMode : DEFAULT_AI_PREFERENCES.chatMode;
  const executionMode =
    raw.executionMode === "auto" || raw.executionMode === "fast" || raw.executionMode === "step"
      ? raw.executionMode
      : DEFAULT_AI_PREFERENCES.executionMode;

  return {
    chatMode,
    executionMode,
    settings: sanitizeAiSettings(raw.settings),
  };
}

function readStoredAiPreferences(): AiPreferences {
  try {
    const stored = localStorage.getItem(AI_PREFERENCES_STORAGE_KEY);
    if (stored) {
      return sanitizeAiPreferences(JSON.parse(stored));
    }

    const legacyMode = localStorage.getItem("ai_execution_mode");
    if (legacyMode === "auto" || legacyMode === "fast" || legacyMode === "step") {
      return {
        ...cloneAiPreferences(DEFAULT_AI_PREFERENCES),
        chatMode: "agent",
        executionMode: legacyMode,
      };
    }
  } catch {
    // noop
  }

  return cloneAiPreferences(DEFAULT_AI_PREFERENCES);
}

function mapStatus(status: TerminalConnectionStatus): Tab["status"] {
  if (status === "connected") return "connected";
  if (status === "connecting") return "connecting";
  return "error";
}

function findServer(servers: FrontendServer[], id: number) {
  return servers.find((server) => server.id === id);
}

function getNextSessionNumber(tabs: Tab[], serverId: number) {
  return tabs.reduce((max, tab) => {
    if (tab.serverId !== serverId) return max;
    return Math.max(max, tab.sessionNumber);
  }, 0) + 1;
}

function createTab(server: FrontendServer, tabs: Tab[], tabId = nextId()): Tab {
  return {
    id: tabId,
    serverId: server.id,
    name: server.name,
    sessionNumber: getNextSessionNumber(tabs, server.id),
    status: "connecting",
  };
}

function formatTabName(tab: Tab) {
  if (tab.sessionNumber <= 1) return tab.name;
  return `${tab.name} · ${tab.sessionNumber}`;
}

function formatSessionCount(count: number) {
  const mod10 = count % 10;
  const mod100 = count % 100;

  if (mod10 === 1 && mod100 !== 11) return `${count} сессия`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${count} сессии`;
  return `${count} сессий`;
}

interface ServerPickerProps {
  servers: FrontendServer[];
  open: boolean;
  onClose: () => void;
  onSelect: (server: FrontendServer) => void;
  openSessionCounts: Map<number, number>;
}

function ServerPicker({ servers, open, onClose, onSelect, openSessionCounts }: ServerPickerProps) {
  const [search, setSearch] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setSearch("");
    setTimeout(() => inputRef.current?.focus(), 100);
  }, [open]);

  useEffect(() => {
    if (!open) return;

    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };

    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [open, onClose]);

  if (!open) return null;

  const query = search.toLowerCase().trim();
  const filtered = servers.filter((server) => {
    if (!query) return true;
    return (
      server.name.toLowerCase().includes(query) ||
      server.host.toLowerCase().includes(query) ||
      server.username.toLowerCase().includes(query) ||
      (server.group_name || "").toLowerCase().includes(query)
    );
  });

  const groups = new Map<string, FrontendServer[]>();
  for (const server of filtered) {
    const groupName = server.group_name || "Без группы";
    if (!groups.has(groupName)) groups.set(groupName, []);
    groups.get(groupName)!.push(server);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative mx-4 flex max-h-[70vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-2xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary/10">
              <Server className="h-5 w-5 text-primary" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-foreground">Выбор сервера</h2>
              <p className="text-xs text-muted-foreground">{servers.length} серверов доступно</p>
            </div>
          </div>
          <Button
            size="sm"
            variant="ghost"
            className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="border-b border-border/60 px-5 py-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              ref={inputRef}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Поиск по имени, хосту, группе..."
              className="w-full rounded-xl border border-border bg-secondary py-2.5 pl-10 pr-4 text-sm text-foreground placeholder:text-muted-foreground focus:border-primary focus:outline-none"
            />
            {search ? (
              <button
                onClick={() => setSearch("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            ) : null}
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <Server className="mb-3 h-10 w-10 text-muted-foreground/40" />
              <p className="text-sm text-muted-foreground">Серверы не найдены</p>
              {search ? <p className="mt-1 text-xs text-muted-foreground/60">Попробуйте изменить запрос</p> : null}
            </div>
          ) : (
            Array.from(groups.entries()).map(([groupName, groupServers]) => (
              <div key={groupName}>
                <div className="sticky top-0 bg-secondary/40 px-5 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {groupName} ({groupServers.length})
                </div>
                {groupServers.map((server) => {
                  const openSessions = openSessionCounts.get(server.id) ?? 0;
                  return (
                    <button
                      key={server.id}
                      onClick={() => {
                        onSelect(server);
                        onClose();
                      }}
                      className="flex w-full items-center gap-3 border-b border-border/30 px-5 py-3 text-left transition-colors hover:bg-primary/5 active:bg-primary/10"
                    >
                      <div
                        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
                          server.server_type === "rdp" ? "bg-blue-500/10" : "bg-primary/10"
                        }`}
                      >
                        {server.server_type === "rdp" ? (
                          <Monitor className="h-4 w-4 text-blue-500" />
                        ) : (
                          <Server className="h-4 w-4 text-primary" />
                        )}
                      </div>

                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="truncate text-sm font-medium text-foreground">{server.name}</span>
                          <StatusIndicator
                            status={
                              server.status === "online"
                                ? "online"
                                : server.status === "offline"
                                  ? "offline"
                              : "unknown"
                            }
                            showLabel={false}
                          />
                          {openSessions > 0 ? (
                            <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
                              {formatSessionCount(openSessions)}
                            </span>
                          ) : null}
                        </div>
                        <p className="truncate font-mono text-xs text-muted-foreground">
                          {server.username}@{server.host}:{server.port}
                        </p>
                      </div>

                      <span className="shrink-0 text-[10px] uppercase text-muted-foreground/60">{server.server_type}</span>
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

export default function TerminalPage() {
  const { id } = useParams<{ id: string }>();
  const requestedId = useMemo(() => Number(id || 0), [id]);
  const terminalRefs = useRef<Record<string, TerminalHandle | null>>({});
  const sftpRefs = useRef<Record<string, SftpPanelHandle | null>>({});
  const activeTabIdRef = useRef("");

  const { data, isLoading, error } = useQuery({
    queryKey: ["frontend", "bootstrap"],
    queryFn: fetchFrontendBootstrap,
    staleTime: 20_000,
  });

  const servers = useMemo(() => data?.servers ?? [], [data?.servers]);
  const defaultServer = findServer(servers, requestedId) || servers[0];

  const [tabs, setTabs] = useState<Tab[]>([]);
  const [activeTabId, setActiveTabId] = useState("");
  const [tabAiState, setTabAiState] = useState<Record<string, TabAiState>>({});
  const [tabAiPreferences, setTabAiPreferences] = useState<Record<string, AiPreferences>>({});
  const [showServerPicker, setShowServerPicker] = useState(false);
  const [sidePanelMode, setSidePanelMode] = useState<"none" | "ai" | "files" | "ui">("none");
  const [panelWidth, setPanelWidth] = useState(380);
  const [globalAiPreferences, setGlobalAiPreferences] = useState<AiPreferences>(() => readStoredAiPreferences());
  const [settingsOpen, setSettingsOpen] = useState(false);

  const { t } = useI18n();
  const { editorState, closeEditor, handleWsEvent: handleEditorWsEvent } = useEditorInterceptor();
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

  const handleSaveAiDefaults = useCallback(() => {
    const next = cloneAiPreferences(activeAiPreferences);
    setGlobalAiPreferences(next);
    try {
      localStorage.setItem(AI_PREFERENCES_STORAGE_KEY, JSON.stringify(next));
      localStorage.removeItem("ai_execution_mode");
    } catch {
      // noop
    }
    toast({
      title: "Глобальные настройки сохранены",
      description: "Новые AI-чаты будут стартовать с текущими параметрами.",
    });
  }, [activeAiPreferences]);

  const handleResetAiPreferences = useCallback(() => {
    updateActiveTabAiPreferences(() => cloneAiPreferences(globalAiPreferences));
    toast({
      title: "Настройки чата сброшены",
      description: "Для текущего чата снова применены глобальные значения по умолчанию.",
    });
  }, [globalAiPreferences, updateActiveTabAiPreferences]);

  const handleClearChat = useCallback(() => {
    updateActiveTabAiState(() => createEmptyAiState());
  }, [updateActiveTabAiState]);

  const revealAiPanel = useCallback(() => {
    setSidePanelMode("ai");
  }, []);

  const revealUiPanel = useCallback(() => {
    setPanelWidth((current) => Math.max(current, 520));
    setSidePanelMode("ui");
  }, []);

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
    if (handleEditorWsEvent(serverId, payload)) return;

    const type = String(payload.type || "");

    if (type === "ai_status") {
      const status = String(payload.status || "");
      updateTabAiState(tabId, (state) => ({
        ...state,
        isGenerating: status === "thinking" || status === "running" || status === "generating_report",
      }));
      return;
    }

    if (type === "ai_response") {
      const text = String(payload.assistant_text || payload.message || "");
      const mode = String(payload.mode || "answer") as AiMessage["mode"];
      const rawCommands = (payload.commands as AiCommand[] | undefined) || [];

      revealAiPanelForTab(tabId);
      updateTabAiState(tabId, (state) => ({
        ...state,
        messages: [
          ...state.messages,
          {
            id: nextId(),
            role: "assistant",
            type: rawCommands.length > 0 ? "commands" : "text",
            content: text,
            commands: rawCommands.map((command) => ({
              ...command,
              status: (command.status || "pending") as AiCommand["status"],
            })),
            mode,
          },
        ],
      }));
      return;
    }

    if (type === "ai_command_status") {
      const cmdId = Number(payload.id);
      const status = String(payload.status || "done") as AiCommand["status"];
      const exitCode = payload.exit_code !== undefined ? Number(payload.exit_code) : undefined;

      updateTabAiState(tabId, (state) => ({
        ...state,
        messages: state.messages.map((message) => {
          if (message.type !== "commands" || !message.commands?.some((command) => command.id === cmdId)) return message;
          return {
            ...message,
            commands: message.commands.map((command) =>
              command.id === cmdId ? { ...command, status, exit_code: exitCode } : command,
            ),
          };
        }),
      }));
      return;
    }

    // F2-8 v2: captured output from a non-PTY exec_direct channel. Merge it
    // into the matching command so `AiPanel` can render it inline.
    if (type === "ai_direct_output") {
      const cmdId = Number(payload.id);
      const directOutput = String(payload.output || "");
      const exitCode = payload.exit_code !== undefined ? Number(payload.exit_code) : undefined;

      updateTabAiState(tabId, (state) => ({
        ...state,
        messages: state.messages.map((message) => {
          if (message.type !== "commands" || !message.commands?.some((command) => command.id === cmdId)) return message;
          return {
            ...message,
            commands: message.commands.map((command) =>
              command.id === cmdId
                ? { ...command, direct_output: directOutput, exit_code: exitCode ?? command.exit_code }
                : command,
            ),
          };
        }),
      }));
      return;
    }

    // A6: merge explanation text into the matching command card.
    if (type === "ai_explanation") {
      const cmdId = Number(payload.id);
      const explanation = String(payload.explanation || "");
      updateTabAiState(tabId, (state) => ({
        ...state,
        messages: state.messages.map((message) => {
          if (message.type !== "commands" || !message.commands?.some((c) => c.id === cmdId)) return message;
          return {
            ...message,
            commands: message.commands.map((c) =>
              c.id === cmdId ? { ...c, explanation, explaining: false } : c,
            ),
          };
        }),
      }));
      return;
    }

    if (type === "ai_report") {
      const report = String(payload.report || "");
      const reportStatus = String(payload.status || "ok") as AiMessage["reportStatus"];
      if (!report) return;

      revealAiPanelForTab(tabId);
      updateTabAiState(tabId, (state) => ({
        ...state,
        messages: [
          ...state.messages,
          { id: nextId(), role: "assistant", type: "report", content: report, reportStatus },
        ],
      }));
      return;
    }

    if (type === "ai_question") {
      const qId = String(payload.q_id || "");
      const question = String(payload.question || "");
      const cmd = payload.cmd ? String(payload.cmd) : undefined;
      const exitCode = payload.exit_code !== undefined ? Number(payload.exit_code) : undefined;

      revealAiPanelForTab(tabId);
      updateTabAiState(tabId, (state) => ({
        ...state,
        messages: [
          ...state.messages,
          {
            id: nextId(),
            role: "system",
            type: "question",
            content: question,
            qId,
            question,
            questionCmd: cmd,
            questionExitCode: exitCode,
          },
        ],
      }));
      return;
    }

    if (type === "ai_install_progress") {
      const cmd = String(payload.cmd || "");
      const elapsed = Number(payload.elapsed || 0);
      const outputTail = String(payload.output_tail || "");

      revealAiPanelForTab(tabId);
      updateTabAiState(tabId, (state) => {
        let found = false;
        const updated = state.messages.map((message) => {
          if (message.type === "progress" && message.progressCmd === cmd) {
            found = true;
            return { ...message, progressElapsed: elapsed, progressTail: outputTail };
          }
          return message;
        });

        return {
          ...state,
          messages: found
            ? updated
            : [
                ...updated,
                {
                  id: nextId(),
                  role: "system",
                  type: "progress",
                  content: cmd,
                  progressCmd: cmd,
                  progressElapsed: elapsed,
                  progressTail: outputTail,
                },
              ],
        };
      });
      return;
    }

    if (type === "ai_recovery") {
      revealAiPanelForTab(tabId);
      updateTabAiState(tabId, (state) => ({
        ...state,
        messages: [
          ...state.messages,
          {
            id: nextId(),
            role: "system",
            type: "recovery",
            content: String(payload.why || ""),
            recoveryOriginal: String(payload.original_cmd || ""),
            recoveryNew: String(payload.new_cmd || ""),
            recoveryWhy: String(payload.why || ""),
          },
        ],
      }));
      return;
    }

    if (type === "ai_error") {
      revealAiPanelForTab(tabId);
      updateTabAiState(tabId, (state) => ({
        ...state,
        isGenerating: false,
        messages: [
          ...state.messages,
          { id: nextId(), role: "system", type: "text", content: String(payload.message || "AI error") },
        ],
      }));
      return;
    }

    if (type === "status" && String(payload.status) === "connected") {
      updateTabAiState(tabId, (state) => ({
        ...state,
        isGenerating: false,
      }));
    }
  }, [revealAiPanelForTab, updateTabAiState, handleEditorWsEvent]);

  useEffect(() => {
    if (!activeTabId) return;
    const timer = window.setTimeout(() => {
      terminalRefs.current[activeTabId]?.fit();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [activeTabId]);

  const handleSendAi = useCallback((text: string) => {
    if (!text.trim()) return;
    const tabId = activeTabIdRef.current;
    const preferences = tabAiPreferences[tabId] || globalAiPreferences;
    const trimmed = text.trim();

    if (trimmed.toLowerCase().startsWith("/mode")) {
      const [, rawMode = ""] = trimmed.split(/\s+/, 2);
      const normalizedMode = rawMode.trim().toLowerCase();
      const currentMode = preferences.chatMode;

      if (!normalizedMode) {
        updateActiveTabAiState((state) => ({
          ...state,
          messages: [
            ...state.messages,
            {
              id: nextId(),
              role: "assistant",
              type: "text",
              content: `Текущий режим: **${currentMode === "agent" ? "Agent" : "Ask"}**.\n\nИспользуйте \`/mode ask\` или \`/mode agent\`.`,
            },
          ],
        }));
        return;
      }

      if (normalizedMode !== "ask" && normalizedMode !== "agent") {
        updateActiveTabAiState((state) => ({
          ...state,
          messages: [
            ...state.messages,
            {
              id: nextId(),
              role: "assistant",
              type: "text",
              content: "Неизвестный режим. Доступно: `/mode ask`, `/mode agent`.",
            },
          ],
        }));
        return;
      }

      updateTabAiPreferences(tabId, (state) => ({
        ...state,
        chatMode: normalizedMode,
      }));
      updateActiveTabAiState((state) => ({
        ...state,
        messages: [
          ...state.messages,
          {
            id: nextId(),
            role: "assistant",
            type: "text",
            content:
              normalizedMode === "agent"
                ? "Режим переключён на **Agent**. Ассистент будет сразу запускать безопасные команды, а опасные действия по-прежнему потребуют подтверждения."
                : "Режим переключён на **Ask**. Ассистент будет объяснять и предлагать команды, а запуск останется только после вашего подтверждения.",
          },
        ],
      }));
      return;
    }

    updateActiveTabAiState((state) => ({
      ...state,
      isGenerating: true,
      messages: [...state.messages, { id: nextId(), role: "user", type: "text", content: text }],
    }));
    terminalRefs.current[tabId]?.sendAiRequest(
      text,
      preferences.chatMode,
      preferences.executionMode,
      preferences.settings,
    );
  }, [globalAiPreferences, tabAiPreferences, updateActiveTabAiState, updateTabAiPreferences]);

  const handleStopAi = useCallback(() => {
    updateActiveTabAiState((state) => ({
      ...state,
      isGenerating: false,
    }));
    terminalRefs.current[activeTabIdRef.current]?.stopAi();
  }, [updateActiveTabAiState]);

  const handleConfirm = useCallback((id: number) => {
    terminalRefs.current[activeTabIdRef.current]?.sendAiConfirm(id);
  }, []);

  const handleCancel = useCallback((id: number) => {
    terminalRefs.current[activeTabIdRef.current]?.sendAiCancel(id);
  }, []);

  const handleReply = useCallback((qId: string, text: string) => {
    terminalRefs.current[activeTabIdRef.current]?.sendAiReply(qId, text);
  }, []);

  const handleGenerateReport = useCallback((force = false) => {
    terminalRefs.current[activeTabIdRef.current]?.sendAiGenerateReport(force);
  }, []);

  const handleClearAiMemory = useCallback(() => {
    terminalRefs.current[activeTabIdRef.current]?.sendAiClearMemory();
  }, []);

  // A6: set explaining=true optimistically, then fire the WS request.
  const handleExplainCommand = useCallback((cmd: AiCommand) => {
    const tabId = activeTabIdRef.current;
    // Mark as explaining to disable the button / show spinner.
    updateTabAiState(tabId, (state) => ({
      ...state,
      messages: state.messages.map((message) => {
        if (message.type !== "commands" || !message.commands?.some((c) => c.id === cmd.id)) return message;
        return {
          ...message,
          commands: message.commands.map((c) => (c.id === cmd.id ? { ...c, explaining: true } : c)),
        };
      }),
    }));
    terminalRefs.current[tabId]?.sendAiExplainOutput({
      id: cmd.id,
      cmd: cmd.cmd,
      output: cmd.direct_output ?? "",
      exit_code: cmd.exit_code,
    });
  }, [updateTabAiState]);

  const handleTabFileDrop = useCallback((tabId: string, files: File[]) => {
    if (!files.length) return;
    sftpRefs.current[tabId]?.enqueueUploads(files);
    setSidePanelMode("files");
  }, []);

  useEffect(() => {
    if (sidePanelMode === "ui" && activeServer?.server_type !== "ssh") {
      setSidePanelMode("none");
    }
  }, [activeServer?.server_type, sidePanelMode]);

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
      <QueryStateBlock
        loading={isLoading}
        error={
          error
            ? error
            : !isLoading && !data
              ? new Error("Ошибка загрузки данных терминала")
              : !activeTab || !activeServer
                ? new Error("Сервер не найден или недоступен")
                : undefined
        }
        className="p-6"
      >
        {null}
      </QueryStateBlock>
    );
  }

  return (
    <div className="flex h-[100dvh] flex-col bg-background">
      <div className="shrink-0 border-b border-border/80 bg-background/95 px-2.5 py-1.5">
        <div className="flex items-center gap-2">
          <Link
            to="/servers"
            className="inline-flex shrink-0 items-center gap-1 rounded-lg px-2 py-1.5 text-[11px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Назад
          </Link>

          <div className="flex min-w-0 shrink-0 items-center gap-2 rounded-xl border border-border/70 bg-card/60 px-2.5 py-1.5">
            <StatusIndicator
              status={activeTab.status === "connected" ? "online" : activeTab.status === "error" ? "offline" : "unknown"}
              showLabel={false}
            />
            <span className="truncate text-sm font-medium text-foreground">{formatTabName(activeTab)}</span>
            <span className="hidden truncate text-[11px] text-muted-foreground lg:inline">
              {activeServer.username}@{activeServer.host}:{activeServer.port}
            </span>
          </div>

          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1 overflow-x-auto rounded-xl border border-border/70 bg-card/40 p-1">
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTabId(tab.id)}
                  className={`group flex shrink-0 items-center gap-2 rounded-lg border px-2.5 py-1.5 text-sm transition-colors ${
                    tab.id === activeTabId
                      ? "border-border bg-background text-foreground"
                      : "border-transparent bg-transparent text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
                  }`}
                >
                  <StatusIndicator
                    status={tab.status === "connected" ? "online" : tab.status === "error" ? "offline" : "unknown"}
                    showLabel={false}
                  />
                  <span className="max-w-32 truncate">{formatTabName(tab)}</span>
                  {tabs.length > 1 ? (
                    <span
                      role="button"
                      aria-label={`Close ${formatTabName(tab)}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        closeTab(tab.id);
                      }}
                      className="opacity-0 transition-opacity group-hover:opacity-100 hover:text-destructive"
                    >
                      <X className="h-3 w-3" />
                    </span>
                  ) : null}
                </button>
              ))}

              <button
                onClick={addTab}
                className="flex shrink-0 items-center gap-1 rounded-lg border border-dashed border-border/70 px-2.5 py-1.5 text-[11px] text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
                aria-label="Add tab"
                title="Подключить сервер"
              >
                <Plus className="h-3.5 w-3.5" />
                Сервер
              </button>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-1 rounded-xl border border-border/70 bg-card/40 p-1">
            <Button
              type="button"
              size="sm"
              variant={sidePanelMode === "files" ? "secondary" : "ghost"}
              className="h-8 gap-1.5 px-2.5 text-[11px]"
              onClick={() => setSidePanelMode((current) => (current === "files" ? "none" : "files"))}
              title={sidePanelMode === "files" ? "Скрыть файловую панель" : "Показать файловую панель"}
            >
              <FolderOpen className="h-3.5 w-3.5" />
              SFTP
            </Button>
            {activeServer?.server_type === "ssh" ? (
              <Button
                type="button"
                size="sm"
                variant={sidePanelMode === "ui" ? "secondary" : "ghost"}
                className="h-8 gap-1.5 px-2.5 text-[11px]"
                onClick={() => {
                  if (sidePanelMode === "ui") {
                    setSidePanelMode("none");
                    return;
                  }
                  revealUiPanel();
                }}
                title={sidePanelMode === "ui" ? "Скрыть Linux Workspace" : "Показать Linux Workspace"}
              >
                <Monitor className="h-3.5 w-3.5" />
                Linux
              </Button>
            ) : null}
              <Button
                type="button"
                size="sm"
                variant={sidePanelMode === "ai" ? "secondary" : "ghost"}
                className="h-8 gap-1.5 px-2.5 text-[11px]"
                onClick={() => setSidePanelMode((current) => (current === "ai" ? "none" : "ai"))}
                title={sidePanelMode === "ai" ? "Скрыть AI ассистента" : "Показать AI ассистента"}
            >
              <Bot className="h-3.5 w-3.5" />
              AI
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-8 gap-1.5 px-2.5 text-[11px]"
              onClick={() => setSettingsOpen(true)}
              title={t("terminal.settingsBtn")}
            >
              <Settings className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </div>

      <div className="flex min-h-0 flex-1">
        <div
          className={isUiMode ? "hidden" : "min-h-0 flex-1 p-0"}
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
                  fontSize={termPrefs.font_size}
                  fontFamily={termPrefs.font_family}
                  lineHeight={termPrefs.line_height}
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
          className={`relative min-h-0 shrink-0 overflow-hidden transition-[width] ${sidePanelMode === "none" || isUiMode ? "border-l-0" : "border-l border-border"}`}
          style={{ width: sidePanelMode === "none" ? 0 : isUiMode ? "100%" : panelWidth }}
        >
          {sidePanelMode !== "none" && !isUiMode ? (
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
        onClose={closeEditor}
      />
    </div>
  );
}
