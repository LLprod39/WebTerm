import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
} from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Bot, Maximize, Monitor, Plus, Search, Server, X } from "lucide-react";
import { XTerminal, type AiExecutionMode, type TerminalConnectionStatus, type TerminalHandle } from "@/components/terminal/XTerminal";
import { AiPanel, type AiCommand, type AiMessage } from "@/components/terminal/AiPanel";
import { Button } from "@/components/ui/button";
import { StatusIndicator } from "@/components/StatusIndicator";
import { fetchFrontendBootstrap, type FrontendServer } from "@/lib/api";

interface Tab {
  id: string;
  serverId: number;
  name: string;
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

function mapStatus(status: TerminalConnectionStatus): Tab["status"] {
  if (status === "connected") return "connected";
  if (status === "connecting") return "connecting";
  return "error";
}

function findServer(servers: FrontendServer[], id: number) {
  return servers.find((server) => server.id === id);
}

interface ServerPickerProps {
  servers: FrontendServer[];
  open: boolean;
  onClose: () => void;
  onSelect: (server: FrontendServer) => void;
  usedServerIds: Set<number>;
}

function ServerPicker({ servers, open, onClose, onSelect, usedServerIds }: ServerPickerProps) {
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
                  const isUsed = usedServerIds.has(server.id);
                  return (
                    <button
                      key={server.id}
                      onClick={() => {
                        onSelect(server);
                        onClose();
                      }}
                      disabled={isUsed}
                      className={`flex w-full items-center gap-3 border-b border-border/30 px-5 py-3 text-left transition-colors ${
                        isUsed ? "cursor-not-allowed opacity-40" : "hover:bg-primary/5 active:bg-primary/10"
                      }`}
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
                          {isUsed ? (
                            <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">открыт</span>
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
  const [showServerPicker, setShowServerPicker] = useState(false);
  const [showAi, setShowAi] = useState(false);
  const [panelWidth, setPanelWidth] = useState(380);
  const [executionMode, setExecutionMode] = useState<AiExecutionMode>(() => {
    try {
      const stored = localStorage.getItem("ai_execution_mode");
      if (stored === "fast" || stored === "step" || stored === "auto") return stored;
    } catch {
      // noop
    }
    return "auto";
  });

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

  useEffect(() => {
    if (!defaultServer || tabs.length > 0) return;

    const firstId = nextId();
    setTabs([{ id: firstId, serverId: defaultServer.id, name: defaultServer.name, status: "connecting" }]);
    setActiveTabId(firstId);
    setTabAiState((prev) => ({
      ...prev,
      [firstId]: prev[firstId] || createEmptyAiState(),
    }));
  }, [defaultServer, tabs.length]);

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
      }
      return next;
    });
  }, [servers, tabs]);

  const activeTab = tabs.find((tab) => tab.id === activeTabId) || tabs[0];
  const activeServer = activeTab ? findServer(servers, activeTab.serverId) : null;
  const activeAiState = activeTabId ? tabAiState[activeTabId] || createEmptyAiState() : createEmptyAiState();
  const aiMessages = activeAiState.messages;
  const isAiGenerating = activeAiState.isGenerating;
  const usedServerIds = useMemo(() => new Set(tabs.map((tab) => tab.serverId)), [tabs]);

  const addTab = useCallback(() => {
    if (!servers.length) return;
    setShowServerPicker(true);
  }, [servers.length]);

  const handleServerSelect = useCallback((server: FrontendServer) => {
    const tabId = nextId();
    setTabs((prev) => [...prev, { id: tabId, serverId: server.id, name: server.name, status: "connecting" }]);
    setActiveTabId(tabId);
    setTabAiState((prev) => ({
      ...prev,
      [tabId]: prev[tabId] || createEmptyAiState(),
    }));
  }, []);

  const closeTab = useCallback((tabId: string) => {
    setTabs((prev) => {
      if (prev.length <= 1) return prev;
      const next = prev.filter((tab) => tab.id !== tabId);
      setActiveTabId((current) => (current === tabId ? next[0]?.id || "" : current));
      return next;
    });
    delete terminalRefs.current[tabId];

    setTabAiState((prev) => {
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
    setExecutionMode(mode);
    try {
      localStorage.setItem("ai_execution_mode", mode);
    } catch {
      // noop
    }
  }, []);

  const handleClearChat = useCallback(() => {
    updateActiveTabAiState(() => createEmptyAiState());
  }, [updateActiveTabAiState]);

  const revealAiPanel = useCallback(() => {
    setShowAi(true);
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

  const handleTabWsEvent = useCallback((tabId: string, payload: Record<string, unknown>) => {
    const type = String(payload.type || "");

    if (type === "ai_status") {
      const status = String(payload.status || "");
      updateTabAiState(tabId, (state) => ({
        ...state,
        isGenerating: status === "thinking" || status === "running",
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
  }, [revealAiPanelForTab, updateTabAiState]);

  useEffect(() => {
    if (!activeTabId) return;
    const timer = window.setTimeout(() => {
      terminalRefs.current[activeTabId]?.fit();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [activeTabId]);

  const handleSendAi = useCallback((text: string) => {
    if (!text.trim()) return;

    updateActiveTabAiState((state) => ({
      ...state,
      isGenerating: true,
      messages: [...state.messages, { id: nextId(), role: "user", type: "text", content: text }],
    }));
    terminalRefs.current[activeTabIdRef.current]?.sendAiRequest(text, executionMode);
  }, [executionMode, updateActiveTabAiState]);

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

  if (isLoading) return <div className="p-6 text-sm text-muted-foreground">Загрузка...</div>;
  if (error || !data) return <div className="p-6 text-sm text-destructive">Ошибка загрузки данных терминала.</div>;
  if (!activeTab || !activeServer) return <div className="p-6 text-sm text-muted-foreground">Сервер не найден или недоступен.</div>;

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)]">
      {/* Tab bar */}
      <div className="flex items-center gap-0.5 px-2 pt-2 bg-background border-b border-border overflow-x-auto shrink-0">
        {tabs.map((tab) => (
          <button key={tab.id} onClick={() => setActiveTabId(tab.id)}
            className={`group flex items-center gap-2 px-3 py-2 text-sm rounded-t-md border border-b-0 transition-colors shrink-0 ${
              tab.id === activeTabId
                ? "bg-card border-border text-foreground"
                : "bg-transparent border-transparent text-muted-foreground hover:text-foreground hover:bg-secondary/50"
            }`}>
            <StatusIndicator
              status={tab.status === "connected" ? "online" : tab.status === "error" ? "offline" : "unknown"}
              showLabel={false} />
            <span className="truncate max-w-32">{tab.name}</span>
            {tabs.length > 1 && (
              <span role="button" aria-label={`Close ${tab.name}`}
                onClick={(e) => { e.stopPropagation(); closeTab(tab.id); }}
                className="opacity-0 group-hover:opacity-100 hover:text-destructive transition-opacity">
                <X className="h-3 w-3" />
              </span>
            )}
          </button>
        ))}
        <button onClick={addTab}
          className="flex items-center gap-1 px-2.5 py-2 text-muted-foreground hover:text-primary transition-colors shrink-0 text-xs"
          aria-label="Add tab" title="Подключить сервер">
          <Plus className="h-4 w-4" />
        </button>
        <div className="ml-auto shrink-0 pl-2">
          <Button
            type="button"
            size="sm"
            variant={showAi ? "default" : "ghost"}
            className="h-8 gap-1.5 text-xs"
            onClick={() => setShowAi((current) => !current)}
            title={showAi ? "Скрыть AI ассистента" : "Показать AI ассистента"}
          >
            <Bot className="h-3.5 w-3.5" />
            AI
          </Button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1">
        <div className="min-h-0 flex-1 bg-terminal-bg p-1">
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
                  onStatusChange={(status) => updateTabStatus(tab.id, status)}
                  onError={(message) =>
                    updateTabAiState(tab.id, (state) => ({
                      ...state,
                      messages: [...state.messages, { id: nextId(), role: "system", type: "text", content: message }],
                    }))
                  }
                  onEvent={(payload) => handleTabWsEvent(tab.id, payload)}
                />
              </div>
            ))}
          </div>
        </div>

        {showAi ? (
          <div className="relative flex min-h-0 shrink-0 border-l border-border" style={{ width: panelWidth }}>
            <div
              onMouseDown={startDrag}
              className="absolute bottom-0 left-0 top-0 z-10 w-1 cursor-col-resize select-none transition-colors hover:bg-primary/40 active:bg-primary/60"
              title="Перетащите для изменения ширины"
            />
            <div className="min-h-0 flex-1 overflow-hidden">
              <AiPanel
                onClose={() => setShowAi(false)}
                onSend={handleSendAi}
                onStop={handleStopAi}
                onConfirm={handleConfirm}
                onCancel={handleCancel}
                onReply={handleReply}
                onClearChat={handleClearChat}
                messages={aiMessages}
                isGenerating={isAiGenerating}
                executionMode={executionMode}
                onModeChange={handleModeChange}
              />
            </div>
          </div>
        ) : null}
      </div>

      <ServerPicker
        servers={servers}
        open={showServerPicker}
        onClose={() => setShowServerPicker(false)}
        onSelect={handleServerSelect}
        usedServerIds={usedServerIds}
      />
    </div>
  );
}
