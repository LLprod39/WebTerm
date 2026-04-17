import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from "react";
import { Terminal } from "@xterm/xterm";
import type { ITheme } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { SearchAddon } from "@xterm/addon-search";
import { WebLinksAddon } from "@xterm/addon-web-links";
import { Unicode11Addon } from "@xterm/addon-unicode11";
import "@xterm/xterm/css/xterm.css";
import { getWsUrl, fetchWsToken } from "@/lib/api";
import { cn } from "@/lib/utils";

export type TerminalConnectionStatus = "connecting" | "connected" | "disconnected" | "error";

export type AiExecutionMode = "auto" | "step" | "fast";
export type AiChatMode = "ask" | "agent";

export type AiAutoReportMode = "auto" | "on" | "off";

export interface AiAssistantSettings {
  memoryEnabled: boolean;
  memoryTtlRequests: number;
  autoReport: AiAutoReportMode;
  confirmDangerousCommands: boolean;
  whitelistPatterns: string[];
  blacklistPatterns: string[];
  showSuggestedCommands: boolean;
  showExecutedCommands: boolean;
  // A5: dry-run mode — when true the backend returns a synthetic
  // "Would execute: <cmd>" output without touching the remote host.
  dryRun: boolean;
}

export interface AiPreferences {
  chatMode: AiChatMode;
  executionMode: AiExecutionMode;
  settings: AiAssistantSettings;
}

export interface TerminalHandle {
  sendAiRequest: (
    message: string,
    chatMode?: AiChatMode,
    mode?: AiExecutionMode,
    settings?: AiAssistantSettings,
  ) => void;
  sendAiGenerateReport: (force?: boolean) => void;
  sendAiClearMemory: () => void;
  stopAi: () => void;
  sendAiReply: (qId: string, text: string) => void;
  sendAiConfirm: (id: number) => void;
  sendAiCancel: (id: number) => void;
  // A6: request a human-readable explanation for a finished command.
  sendAiExplainOutput: (payload: {
    id: number;
    cmd: string;
    output: string;
    exit_code?: number;
    question?: string;
  }) => void;
  clearTerminal: () => void;
  fit: () => void;
  sendRaw: (payload: Record<string, unknown>) => void;
}

interface XTerminalProps {
  serverId: number;
  active?: boolean;
  themeOverride?: ITheme;
  fontSize?: number;
  fontFamily?: string;
  lineHeight?: number;
  cursorStyle?: "block" | "bar" | "underline";
  cursorBlink?: boolean;
  scrollback?: number;
  onStatusChange?: (status: TerminalConnectionStatus) => void;
  onError?: (message: string) => void;
  onEvent?: (payload: Record<string, unknown>) => void;
  onFilesDrop?: (files: File[]) => void;
  /** Called BEFORE sending data to pty. Return string to type instead, or null for pass-through. */
  onInterceptInput?: (data: string) => string | null;
}

export const XTerminal = forwardRef<TerminalHandle, XTerminalProps>(function XTerminal(
  {
    serverId,
    active = true,
    themeOverride,
    fontSize = 14,
    fontFamily = "'JetBrains Mono', monospace",
    lineHeight = 1.4,
    cursorStyle = "block",
    cursorBlink: cursorBlinkProp = true,
    scrollback = 5000,
    onStatusChange,
    onError,
    onEvent,
    onFilesDrop,
    onInterceptInput,
  }: XTerminalProps,
  ref,
) {
  const containerRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const wsOpenedRef = useRef(false);
  const activeRef = useRef(active);
  const mountedRef = useRef(false);
  const intentionalCloseRef = useRef(false);
  const reconnectDisabledRef = useRef(false);
  const reconnectTimerRef = useRef<number | null>(null);
  const reconnectAttemptRef = useRef(0);
  const pendingMessagesRef = useRef<string[]>([]);
  const lastSizeRef = useRef<{ cols: number; rows: number } | null>(null);
  const dragDepthRef = useRef(0);
  const [isDragActive, setIsDragActive] = useState(false);

  // Store callbacks in refs so the WebSocket effect doesn't restart on every render.
  const onStatusChangeRef = useRef(onStatusChange);
  const onErrorRef = useRef(onError);
  const onEventRef = useRef(onEvent);
  const onInterceptRef = useRef(onInterceptInput);
  useEffect(() => { onStatusChangeRef.current = onStatusChange; });
  useEffect(() => { onErrorRef.current = onError; });
  useEffect(() => { onEventRef.current = onEvent; });
  useEffect(() => { onInterceptRef.current = onInterceptInput; });
  useEffect(() => { activeRef.current = active; }, [active]);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const sendJson = (payload: Record<string, unknown>, queueIfUnavailable = false) => {
    const raw = JSON.stringify(payload);
    const socket = wsRef.current;
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(raw);
      return true;
    }
    if (queueIfUnavailable) {
      const queue = pendingMessagesRef.current;
      if (queue.length >= 50) queue.shift();
      queue.push(raw);
    }
    return false;
  };

  useEffect(() => {
    if (!containerRef.current) return;
    intentionalCloseRef.current = false;
    reconnectDisabledRef.current = false;
    reconnectAttemptRef.current = 0;
    pendingMessagesRef.current = [];
    lastSizeRef.current = null;

    const defaultTheme: ITheme = {
      background: "#0a0e14",
      foreground: "#a3be8c",
      cursor: "#22b8cf",
      selectionBackground: "#22b8cf33",
      black: "#1a1e24",
      red: "#e06c75",
      green: "#a3be8c",
      yellow: "#e5c07b",
      blue: "#61afef",
      magenta: "#c678dd",
      cyan: "#22b8cf",
      white: "#abb2bf",
      brightBlack: "#5c6370",
      brightRed: "#e06c75",
      brightGreen: "#a3be8c",
      brightYellow: "#e5c07b",
      brightBlue: "#61afef",
      brightMagenta: "#c678dd",
      brightCyan: "#22b8cf",
      brightWhite: "#ffffff",
    };

    const term = new Terminal({
      allowProposedApi: true,
      cursorBlink: cursorBlinkProp,
      cursorStyle,
      fontSize,
      fontFamily,
      lineHeight,
      scrollback,
      theme: themeOverride ?? defaultTheme,
    });

    const fit = new FitAddon();
    const search = new SearchAddon();
    const webLinks = new WebLinksAddon();
    const unicode11 = new Unicode11Addon();
    term.loadAddon(fit);
    term.loadAddon(search);
    term.loadAddon(webLinks);
    term.loadAddon(unicode11);
    term.unicode.activeVersion = "11";
    term.open(containerRef.current);

    setTimeout(() => fit.fit(), 50);
    term.writeln("\x1b[36mWebTermAI\x1b[0m");
    term.writeln(`\x1b[90mConnecting to server #${serverId}...\x1b[0m`);

    termRef.current = term;
    fitRef.current = fit;
    const flushPendingMessages = () => {
      const socket = wsRef.current;
      if (!socket || socket.readyState !== WebSocket.OPEN) return;
      while (pendingMessagesRef.current.length > 0) {
        const raw = pendingMessagesRef.current.shift();
        if (!raw) break;
        socket.send(raw);
      }
    };

    const sendResize = (force = false) => {
      if (!activeRef.current) return;
      const cols = term.cols || 120;
      const rows = term.rows || 32;
      const last = lastSizeRef.current;
      if (!force && last && last.cols === cols && last.rows === rows) return;
      lastSizeRef.current = { cols, rows };
      sendJson({ type: "resize", cols, rows });
    };

    const fitAndResize = (force = false) => {
      fit.fit();
      sendResize(force);
    };

    const scheduleReconnect = (message: string) => {
      if (intentionalCloseRef.current || reconnectDisabledRef.current || !mountedRef.current || reconnectTimerRef.current !== null) return;
      reconnectAttemptRef.current += 1;
      const delay = Math.min(8000, reconnectAttemptRef.current <= 1 ? 1000 : reconnectAttemptRef.current <= 2 ? 2000 : 5000);
      term.writeln(`\r\n\x1b[33m${message}. Reconnecting in ${Math.round(delay / 1000)}s...\x1b[0m`);
      onStatusChangeRef.current?.("connecting");
      reconnectTimerRef.current = window.setTimeout(() => {
        reconnectTimerRef.current = null;
        void openSocket();
      }, delay);
    };

    const openSocket = async () => {
      if (intentionalCloseRef.current || !mountedRef.current) return;
      onStatusChangeRef.current?.("connecting");

      try {
        const wsToken = await fetchWsToken();
        if (intentionalCloseRef.current || !mountedRef.current) return;

        const socket = new WebSocket(getWsUrl(serverId, wsToken ?? undefined));
        wsRef.current = socket;
        wsOpenedRef.current = false;

        socket.onopen = () => {
          if (intentionalCloseRef.current) {
            socket.close();
            return;
          }
          reconnectAttemptRef.current = 0;
          wsOpenedRef.current = true;
          const cols = term.cols || 120;
          const rows = term.rows || 32;
          lastSizeRef.current = { cols, rows };
          term.writeln("\x1b[90mWebSocket connected. Starting SSH session...\x1b[0m");
          socket.send(JSON.stringify({ type: "connect", cols, rows, term_type: "xterm-256color" }));
          flushPendingMessages();
        };

        socket.onmessage = (event) => {
          let payload: Record<string, unknown>;
          try {
            payload = JSON.parse(event.data);
          } catch {
            return;
          }
          onEventRef.current?.(payload);
          const type = String(payload.type || "");
          if (type === "output") {
            const chunk = String(payload.data || "");
            term.write(chunk);
            return;
          }
          if (type === "status") {
            const status = String(payload.status || "disconnected") as TerminalConnectionStatus;
            onStatusChangeRef.current?.(status);
            if (status === "connected") {
              reconnectAttemptRef.current = 0;
            }
            if (status === "disconnected") {
              term.writeln("\r\n\x1b[33mConnection closed.\x1b[0m");
            }
            return;
          }
          if (type === "error") {
            const message = String(payload.message || "Terminal error");
            const isFatal = Boolean(payload.fatal);
            onStatusChangeRef.current?.("error");
            onErrorRef.current?.(message);
            term.writeln(`\r\n\x1b[31m${message}\x1b[0m`);
            if (isFatal) {
              reconnectDisabledRef.current = true;
              const socket = wsRef.current;
              if (socket && socket.readyState === WebSocket.OPEN) {
                socket.close();
              }
            }
            return;
          }
          if (type === "exit") {
            const exitStatus = payload.exit_status;
            term.writeln(`\r\n\x1b[33mProcess exited (${String(exitStatus)})\x1b[0m`);
          }
        };

        socket.onerror = () => {
          const message = "WebSocket error while connecting to terminal";
          onErrorRef.current?.(message);
          term.writeln(`\r\n\x1b[31m${message}\x1b[0m`);
        };

        socket.onclose = (event) => {
          const details = event.reason ? `code ${event.code}: ${event.reason}` : `code ${event.code}`;
          const message = wsOpenedRef.current
            ? `WebSocket closed (${details})`
            : `WebSocket handshake failed (${details}). Check frontend host, proxy, and WS URL.`;
          wsOpenedRef.current = false;
          if (wsRef.current === socket) {
            wsRef.current = null;
          }
          onStatusChangeRef.current?.("disconnected");
          onErrorRef.current?.(message);
          if (intentionalCloseRef.current || reconnectDisabledRef.current || !mountedRef.current) {
            return;
          }
          scheduleReconnect(message);
        };
      } catch {
        scheduleReconnect("Unable to prepare terminal WebSocket");
      }
    };

    term.onData((data) => {
      const intercept = onInterceptRef.current;
      if (intercept) {
        const result = intercept(data);
        if (result !== null) {
          // Overlay consumed the key — type the replacement into pty
          if (result.length > 0) sendJson({ type: "input", data: result });
          return;
        }
      }
      sendJson({ type: "input", data });
    });

    const observer = new ResizeObserver(() => {
      if (!activeRef.current) return;
      window.requestAnimationFrame(() => fitAndResize(false));
    });
    observer.observe(containerRef.current);

    const handleWindowResize = () => {
      if (!activeRef.current) return;
      fitAndResize(false);
    };
    window.addEventListener("resize", handleWindowResize);

    void openSocket();
    onStatusChangeRef.current?.("connecting");

    return () => {
      intentionalCloseRef.current = true;
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      observer.disconnect();
      window.removeEventListener("resize", handleWindowResize);
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "disconnect" }));
        wsRef.current.close();
      } else if (wsRef.current && wsRef.current.readyState === WebSocket.CONNECTING) {
        wsRef.current.close();
      }
      wsRef.current = null;
      termRef.current = null;
      fitRef.current = null;
      lastSizeRef.current = null;
      pendingMessagesRef.current = [];
      term.dispose();
    };
  }, [serverId]); // callbacks are accessed via refs — no restart on prop change

  useEffect(() => {
    if (!active) return;
    const term = termRef.current;
    const fit = fitRef.current;
    if (!term || !fit) return;

    const applyFit = () => {
      fit.fit();
      lastSizeRef.current = null;
      sendJson({ type: "resize", cols: term.cols || 120, rows: term.rows || 32 });
    };

    const timer = window.setTimeout(applyFit, 0);
    return () => window.clearTimeout(timer);
  }, [active]);

  // Live-apply settings without recreating the terminal
  useEffect(() => {
    const term = termRef.current;
    if (!term) return;
    if (themeOverride) term.options.theme = themeOverride;
    term.options.fontSize = fontSize;
    term.options.fontFamily = fontFamily;
    term.options.lineHeight = lineHeight;
    term.options.cursorStyle = cursorStyle;
    term.options.cursorBlink = cursorBlinkProp;
    term.options.scrollback = scrollback;
    fitRef.current?.fit();
  }, [themeOverride, fontSize, fontFamily, lineHeight, cursorStyle, cursorBlinkProp, scrollback]);

  useImperativeHandle(ref, () => ({
    sendAiRequest: (
      message: string,
      chatMode?: AiChatMode,
      mode?: AiExecutionMode,
      settings?: AiAssistantSettings,
    ) => {
      if (!message.trim()) return;
      sendJson(
        {
          type: "ai_request",
          message,
          chat_mode: chatMode || "agent",
          execution_mode: mode || "auto",
          ai_settings: settings
            ? {
                memory_enabled: settings.memoryEnabled,
                memory_ttl_requests: settings.memoryTtlRequests,
                auto_report: settings.autoReport,
                confirm_dangerous_commands: settings.confirmDangerousCommands,
                allowlist_patterns: settings.whitelistPatterns,
                blocklist_patterns: settings.blacklistPatterns,
                // A5: forward dry-run flag to the backend WS handler.
                dry_run: settings.dryRun,
              }
            : undefined,
        },
        true,
      );
    },
    sendAiGenerateReport: (force = false) => {
      sendJson({ type: "ai_generate_report", force }, true);
    },
    sendAiClearMemory: () => {
      sendJson({ type: "ai_clear_memory" }, true);
    },
    stopAi: () => {
      sendJson({ type: "ai_stop" }, true);
    },
    sendAiReply: (qId: string, text: string) => {
      sendJson({ type: "ai_reply", q_id: qId, text }, true);
    },
    sendAiConfirm: (id: number) => {
      sendJson({ type: "ai_confirm", id }, true);
    },
    sendAiCancel: (id: number) => {
      sendJson({ type: "ai_cancel", id }, true);
    },
    sendAiExplainOutput: (payload) => {
      sendJson({ type: "ai_explain_output", ...payload }, true);
    },
    clearTerminal: () => {
      termRef.current?.clear();
    },
    fit: () => {
      const term = termRef.current;
      fitRef.current?.fit();
      if (term) {
        lastSizeRef.current = null;
        sendJson({ type: "resize", cols: term.cols || 120, rows: term.rows || 32 });
      }
    },
    sendRaw: (payload: Record<string, unknown>) => {
      sendJson(payload, true);
    },
  }));

  return (
    <div
      className="relative h-full w-full min-h-[200px]"
      onDragEnter={(event) => {
        if (!onFilesDrop || !event.dataTransfer?.types?.includes("Files")) return;
        event.preventDefault();
        dragDepthRef.current += 1;
        setIsDragActive(true);
      }}
      onDragOver={(event) => {
        if (!onFilesDrop || !event.dataTransfer?.types?.includes("Files")) return;
        event.preventDefault();
      }}
      onDragLeave={(event) => {
        if (!onFilesDrop) return;
        event.preventDefault();
        dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
        if (dragDepthRef.current === 0) {
          setIsDragActive(false);
        }
      }}
      onDrop={(event) => {
        if (!onFilesDrop || !event.dataTransfer?.files?.length) return;
        event.preventDefault();
        dragDepthRef.current = 0;
        setIsDragActive(false);
        onFilesDrop(Array.from(event.dataTransfer.files));
      }}
    >
      <div ref={containerRef} className="h-full w-full min-h-[200px]" />
      <div
        className={cn(
          "pointer-events-none absolute inset-0 z-20 flex items-center justify-center bg-primary/10 opacity-0 transition-opacity",
          isDragActive && "opacity-100",
        )}
      >
        <div className="rounded-xl border border-primary/30 bg-background/90 px-4 py-3 text-center shadow-lg backdrop-blur">
          <div className="text-sm font-semibold text-foreground">Upload files</div>
          <div className="mt-1 text-xs text-muted-foreground">Drop files here to send them to the current remote folder.</div>
        </div>
      </div>
    </div>
  );
});
