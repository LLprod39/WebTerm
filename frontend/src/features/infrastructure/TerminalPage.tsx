import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useBlocker, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Terminal as XTerminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import {
  ArrowLeft,
  Clipboard,
  Copy,
  Maximize2,
  Minimize2,
  Plus,
  Power,
  RefreshCw,
  Terminal,
  X,
  Bot,
  Settings,
} from "lucide-react";
import { infrastructureApi, type ServerDetail } from "@/api/infrastructure";
import { RealtimeConnection, type ConnectionState } from "@/realtime/socket";
import {
  Button,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  Feedback,
  Field,
  LoadingState,
  StatusBadge,
  Drawer,
} from "@/components/ui";
import "@xterm/xterm/css/xterm.css";
import "./terminal.css";
import { TerminalAssistant } from "./TerminalAssistant";
import type { TerminalAiEvent } from "@/api/terminal-ai";
import { terminalPreferencesApi } from "@/api/terminal-preferences";
import { TerminalPreferences } from "./TerminalPreferences";
import { TerminalFileEditor, type FileEditorState } from "./TerminalFileEditor";
interface TerminalEvent {
  type: string;
  data?: string;
  status?: string;
  message?: string;
  code?: string;
  has_encrypted_secret?: boolean;
  auth_method?: string;
  exit_status?: number;
  [key: string]: unknown;
}
interface SessionTab {
  key: number;
  serverId: number;
  name: string;
}
interface EditorTarget {
  path: string;
  elevate: boolean;
}
function TerminalSession({
  serverId,
  active,
}: {
  serverId: number;
  active: boolean;
}) {
  const query = useQuery({
    queryKey: ["server", serverId],
    queryFn: ({ signal }) => infrastructureApi.server(serverId, signal),
  });
  if (query.isPending) return <LoadingState />;
  if (query.error) return <ErrorState error={query.error} />;
  if (!query.data.capabilities.connect_terminal)
    return (
      <EmptyState
        title="Нет доступа к терминалу"
        description="Владелец сервера должен предоставить разрешение на SSH-подключение."
      />
    );
  return <TerminalSurface server={query.data} active={active} />;
}
function TerminalSurface({
  server,
  active,
}: {
  server: ServerDetail;
  active: boolean;
}) {
  const host = useRef<HTMLDivElement>(null);
  const terminal = useRef<XTerminal | null>(null);
  const fit = useRef<FitAddon | null>(null);
  const connection = useRef<RealtimeConnection<TerminalEvent> | null>(null);
  const [transport, setTransport] = useState<ConnectionState>("connecting");
  const [state, setState] = useState("disconnected");
  const [error, setError] = useState("");
  const [needsPassword, setNeedsPassword] = useState(false);
  const [password, setPassword] = useState("");
  const preferences = useQuery({
    queryKey: ["terminal-preferences"],
    queryFn: ({ signal }) => terminalPreferencesApi.get(signal),
  });
  const client = useQueryClient();
  const saveSize = useMutation({
    mutationFn: (font_size: number) =>
      terminalPreferencesApi.update({ font_size }),
    onSuccess: (data) => client.setQueryData(["terminal-preferences"], data),
  });
  const fontSize = preferences.data?.font_size ?? 13;
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [editor, setEditor] = useState<EditorTarget | null>(null);
  const editorRef = useRef<EditorTarget | null>(null);
  const [pendingEditor, setPendingEditor] = useState<EditorTarget | null>(null);
  const [editorState, setEditorState] = useState<FileEditorState>({
    dirty: false,
    pending: false,
  });
  const editorStateRef = useRef<FileEditorState>({
    dirty: false,
    pending: false,
  });
  const reportEditorState = useCallback((next: FileEditorState) => {
    editorStateRef.current = next;
    setEditorState(next);
  }, []);
  const openEditor = useCallback((next: EditorTarget) => {
    if (
      editorRef.current?.path === next.path &&
      editorRef.current.elevate === next.elevate
    )
      return;
    if (editorStateRef.current.dirty || editorStateRef.current.pending) {
      setPendingEditor(next);
      return;
    }
    editorRef.current = next;
    setEditor(next);
  }, []);
  const closeEditor = useCallback(() => {
    editorRef.current = null;
    editorStateRef.current = { dirty: false, pending: false };
    setEditor(null);
  }, []);
  const [clipboardMessage, setClipboardMessage] = useState("");
  const passwordRef = useRef("");
  const [assistantOpen, setAssistantOpen] = useState(false);
  const aiListeners = useRef(new Set<(event: TerminalAiEvent) => void>());
  const subscribeAi = useCallback(
    (listener: (event: TerminalAiEvent) => void) => {
      aiListeners.current.add(listener);
      return () => {
        aiListeners.current.delete(listener);
      };
    },
    [],
  );
  const sendAi = useCallback(
    (event: Record<string, unknown>) =>
      connection.current?.send(event) ?? false,
    [],
  );
  const selection = useCallback(
    () => terminal.current?.getSelection() ?? "",
    [],
  );
  useEffect(() => {
    const term = new XTerminal({
      fontFamily: '"Cascadia Code",Consolas,monospace',
      fontSize: 13,
      lineHeight: 1.2,
      cursorBlink: true,
      scrollback: 10000,
      convertEol: false,
      theme: {
        background: "#111720",
        foreground: "#d6dfeb",
        cursor: "#94b8ff",
        selectionBackground: "#34517a",
        black: "#192330",
        red: "#ed8796",
        green: "#91c9a1",
        yellow: "#e9c483",
        blue: "#8aaff3",
        magenta: "#b6a4df",
        cyan: "#7ac4cf",
        white: "#d6dfeb",
      },
    });
    const addon = new FitAddon();
    term.loadAddon(addon);
    term.open(host.current!);
    terminal.current = term;
    fit.current = addon;
    let disposed = false;
    let sshConnected = false;
    const size = () => {
      if (!disposed && host.current?.offsetWidth) {
        addon.fit();
        connection.current?.send({
          type: "resize",
          cols: term.cols,
          rows: term.rows,
        });
      }
    };
    const connect = () =>
      connection.current?.send({
        type: "connect",
        cols: term.cols,
        rows: term.rows,
        term_type: "xterm-256color",
        ...(passwordRef.current ? { password: passwordRef.current } : {}),
      });
    const socket = new RealtimeConnection<TerminalEvent>({
      path: `/ws/servers/${server.id}/terminal/`,
      onState: (next) => {
        setTransport(next);
        if (next !== "connected") {
          sshConnected = false;
          setState("disconnected");
        }
      },
      onMessage: (event) => {
        for (const listener of aiListeners.current)
          listener(event as TerminalAiEvent);
        if (event.type === "ready") {
          // The backend defaults to interception; wait for preferences and the editor before enabling it.
          connection.current?.send({
            type: "set_editor_intercept",
            enabled: false,
          });
          setError("");
          if (
            event.has_encrypted_secret ||
            server.has_saved_password ||
            server.auth_method === "key" ||
            passwordRef.current
          ) {
            setState("connecting");
            connect();
          } else setNeedsPassword(true);
        } else if (event.type === "output") {
          term.write(event.data ?? "");
        } else if (event.type === "status") {
          sshConnected = event.status === "connected";
          setState(event.status ?? "unknown");
          if (event.status === "connected") {
            setNeedsPassword(false);
            setPassword("");
            passwordRef.current = "";
            term.focus();
          }
        } else if (event.type === "error") {
          sshConnected = false;
          setError(event.message ?? "Ошибка подключения");
          setState("failed");
          if (/password|secret|auth/i.test(event.code ?? event.message ?? ""))
            setNeedsPassword(true);
        } else if (event.type === "editor_intercept") {
          if (typeof event.path === "string")
            openEditor({ path: event.path, elevate: !!event.sudo });
        } else if (event.type === "exit") {
          sshConnected = false;
          setState("disconnected");
          term.writeln(`\r\n[Сеанс завершён, код ${event.exit_status ?? "—"}]`);
        }
      },
    });
    connection.current = socket;
    socket.connect();
    const input = term.onData((data) => {
      if (!sshConnected) return;
      if (!socket.send({ type: "input", data }))
        setError("Соединение потеряно. Команда не отправлена.");
    });
    const resize = new ResizeObserver(size);
    resize.observe(host.current!);
    const tick = setInterval(() => socket.send({ type: "ping" }), 30_000);
    const beforeUnload = (e: BeforeUnloadEvent) => {
      if (sshConnected) e.preventDefault();
    };
    window.addEventListener("beforeunload", beforeUnload);
    size();
    return () => {
      disposed = true;
      clearInterval(tick);
      window.removeEventListener("beforeunload", beforeUnload);
      resize.disconnect();
      input.dispose();
      socket.close();
      term.dispose();
      terminal.current = null;
    };
  }, [server.id, server.auth_method, server.has_saved_password, openEditor]);
  useEffect(() => {
    if (active && host.current?.offsetWidth) {
      fit.current?.fit();
      terminal.current?.focus();
      if (terminal.current)
        connection.current?.send({
          type: "resize",
          cols: terminal.current.cols,
          rows: terminal.current.rows,
        });
    }
  }, [active]);
  useEffect(() => {
    if (terminal.current) {
      terminal.current.options.fontSize = fontSize;
      if (preferences.data) {
        terminal.current.options.fontFamily = `"${preferences.data.font_family}",Consolas,monospace`;
        terminal.current.options.lineHeight = preferences.data.line_height;
        terminal.current.options.cursorStyle = preferences.data.cursor_style;
        terminal.current.options.cursorBlink = preferences.data.cursor_blink;
        terminal.current.options.scrollback = preferences.data.scrollback;
      }
      fit.current?.fit();
    }
    if (transport === "connected")
      connection.current?.send({
        type: "set_editor_intercept",
        enabled:
          !!preferences.data?.intercept_editors &&
          server.capabilities.read_files,
      });
  }, [
    fontSize,
    preferences.data,
    transport,
    state,
    server.capabilities.read_files,
  ]);
  function connectWithPassword() {
    passwordRef.current = password;
    setError("");
    setState("connecting");
    setNeedsPassword(false);
    if (transport === "connected")
      connection.current?.send({
        type: "connect",
        password,
        cols: terminal.current?.cols ?? 100,
        rows: terminal.current?.rows ?? 30,
      });
    else connection.current?.reconnect();
  }
  return (
    <div className="terminal-session">
      <div className="terminal-toolbar">
        <div className="row">
          <span className="mono">
            {server.username}@{server.host}:{server.port}
          </span>
          <StatusBadge status={transport === "connected" ? state : transport} />
        </div>
        <div className="row">
          <Button
            size="sm"
            variant={assistantOpen ? "secondary" : "ghost"}
            onClick={() => setAssistantOpen(!assistantOpen)}
            aria-pressed={assistantOpen}
          >
            <Bot size={15} />
            AI-помощник
          </Button>
          <select
            aria-label="Размер шрифта терминала"
            value={fontSize}
            disabled={saveSize.isPending}
            onChange={(e) => saveSize.mutate(Number(e.target.value))}
          >
            {Array.from({ length: 15 }, (_, i) => i + 10).map((n) => (
              <option key={n} value={n}>
                {n}px
              </option>
            ))}
          </select>
          <Button
            size="icon"
            variant="ghost"
            aria-label="Настройки терминала"
            onClick={() => setSettingsOpen(true)}
          >
            <Settings size={15} />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            aria-label="Копировать выделение"
            onClick={() => {
              const selected = terminal.current?.getSelection();
              if (selected)
                void navigator.clipboard
                  .writeText(selected)
                  .then(() => setClipboardMessage("Выделение скопировано"))
                  .catch(() =>
                    setError(
                      "Не удалось получить доступ к буферу обмена. Используйте Ctrl+Shift+C.",
                    ),
                  );
              else setClipboardMessage("Сначала выделите текст в терминале");
            }}
          >
            <Copy size={14} />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            aria-label="Вставить из буфера"
            disabled={state !== "connected"}
            onClick={() =>
              void navigator.clipboard
                .readText()
                .then((text) => terminal.current?.paste(text))
                .catch(() =>
                  setError("Вставка недоступна. Используйте Ctrl+Shift+V."),
                )
            }
          >
            <Clipboard size={14} />
          </Button>
          <Button
            size="sm"
            onClick={() => {
              setError("");
              connection.current?.reconnect();
            }}
          >
            <RefreshCw size={13} />
            Переподключить
          </Button>
          <Button
            size="icon"
            variant="ghost"
            aria-label="Отключить SSH"
            onClick={() => {
              connection.current?.send({ type: "disconnect" });
              setState("disconnected");
            }}
          >
            <Power size={15} />
          </Button>
        </div>
      </div>
      {error && (
        <div className="terminal-message">
          <Feedback error={new Error(error)} />
          {/host.key|fingerprint|отпечат|ключ/i.test(error) && (
            <Link to={`/infrastructure/servers/${server.id}`}>
              Проверить ключ в настройках сервера →
            </Link>
          )}
        </div>
      )}
      {(preferences.error || saveSize.error) && (
        <Feedback error={preferences.error ?? saveSize.error} />
      )}
      <Drawer
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        title="Настройки терминала"
        description="Настройки сохраняются в вашей учётной записи."
      >
        {preferences.isPending ? (
          <LoadingState />
        ) : preferences.error ? (
          <ErrorState
            error={preferences.error}
            retry={() => void preferences.refetch()}
          />
        ) : (
          <TerminalPreferences
            initial={preferences.data}
            onSaved={() => setSettingsOpen(false)}
          />
        )}
      </Drawer>
      {editor && (
        <TerminalFileEditor
          key={`${editor.path}:${editor.elevate}`}
          server={server}
          path={editor.path}
          elevate={editor.elevate}
          onClose={closeEditor}
          onStateChange={reportEditorState}
        />
      )}
      <ConfirmDialog
        open={pendingEditor !== null}
        onOpenChange={(open) => {
          if (!open) setPendingEditor(null);
        }}
        title="Открыть другой файл без сохранения?"
        description={`Несохранённые изменения ${editor?.path ?? "текущего файла"} будут потеряны. Следующий файл: ${pendingEditor?.path ?? ""}.`}
        pending={editorState.pending}
        confirmLabel="Открыть другой файл"
        onConfirm={() => {
          if (pendingEditor) {
            editorRef.current = pendingEditor;
            setEditor(pendingEditor);
          }
          setPendingEditor(null);
        }}
      />
      {needsPassword && (
        <form
          className="terminal-credentials"
          onSubmit={(e) => {
            e.preventDefault();
            connectWithPassword();
          }}
        >
          <Field
            label={
              server.auth_method === "key_password"
                ? "Парольная фраза ключа"
                : "Пароль SSH"
            }
            htmlFor={`terminal-password-${server.id}`}
          >
            <input
              id={`terminal-password-${server.id}`}
              type="password"
              autoComplete="off"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
          <Button type="submit" variant="primary">
            Подключиться
          </Button>
        </form>
      )}
      <div className={`terminal-body${assistantOpen ? " with-assistant" : ""}`}>
        <div className="terminal-surface" ref={host} />
        <aside className="terminal-assistant-panel" hidden={!assistantOpen}>
          <TerminalAssistant
            server={server}
            connected={transport === "connected" && state === "connected"}
            send={sendAi}
            subscribe={subscribeAi}
            selection={selection}
          />
        </aside>
      </div>
      <div className="terminal-statusbar">
        <span>SSH · xterm-256color</span>
        <span role="status">
          {clipboardMessage || "Ctrl+Shift+C / Ctrl+Shift+V · выделение мышью"}
        </span>
        <span>
          {transport === "connected" ? "Канал подключён" : "Канал отключён"}
        </span>
      </div>
    </div>
  );
}
export default function TerminalPage() {
  const serverId = Number(useParams().id);
  const [params, setParams] = useSearchParams();
  const [tabs, setTabs] = useState<SessionTab[]>([
    { key: 1, serverId, name: `Сервер #${serverId}` },
  ]);
  const [active, setActive] = useState(1);
  const [closing, setClosing] = useState<number | null>(null);
  const nextKey = useRef(2);
  const bootstrap = useQuery({
    queryKey: ["servers"],
    queryFn: ({ signal }) => infrastructureApi.bootstrap(signal),
  });
  const focused = params.get("focus") === "1";
  const selected = tabs.find((t) => t.key === active);
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      tabs.length > 0 && currentLocation.pathname !== nextLocation.pathname,
  );
  function close() {
    const remaining = tabs.filter((t) => t.key !== closing);
    setTabs(remaining);
    if (active === closing) setActive(remaining[0]?.key ?? 0);
    setClosing(null);
  }
  return (
    <div className="terminal-workspace">
      <header className="terminal-page-header">
        <div className="row">
          <Link
            to="/infrastructure/servers"
            className="btn btn-ghost btn-icon"
            aria-label="К серверам"
          >
            <ArrowLeft size={17} />
          </Link>
          <h1>Терминал</h1>
          <span className="muted text-sm">
            {bootstrap.data?.servers.find((s) => s.id === selected?.serverId)
              ?.name ?? ""}
          </span>
        </div>
        <Button
          size="sm"
          onClick={() => {
            const next = new URLSearchParams(params);
            if (focused) next.delete("focus");
            else next.set("focus", "1");
            setParams(next);
          }}
        >
          {focused ? <Minimize2 size={14} /> : <Maximize2 size={14} />}{" "}
          {focused ? "Обычный режим" : "Фокус"}
        </Button>
      </header>
      <div className="terminal-tabbar" role="tablist">
        {tabs.map((tab) => (
          <div
            key={tab.key}
            className={`terminal-tab${active === tab.key ? " active" : ""}`}
          >
            <button
              role="tab"
              aria-selected={active === tab.key}
              onClick={() => setActive(tab.key)}
            >
              <Terminal size={14} />
              {bootstrap.data?.servers.find((s) => s.id === tab.serverId)
                ?.name ?? tab.name}
            </button>
            <button
              aria-label="Закрыть сеанс"
              onClick={() => setClosing(tab.key)}
            >
              <X size={13} />
            </button>
          </div>
        ))}
        <div className="terminal-new">
          <Plus size={14} />
          <select
            aria-label="Открыть новый сеанс"
            value=""
            onChange={(e) => {
              if (!e.target.value) return;
              const id = Number(e.target.value);
              const key = nextKey.current++;
              setTabs((prev) => [
                ...prev,
                { key, serverId: id, name: `Сервер #${id}` },
              ]);
              setActive(key);
            }}
          >
            <option value="">Новый сеанс</option>
            {bootstrap.data?.servers.map((server) => (
              <option key={server.id} value={server.id}>
                {server.name}
              </option>
            ))}
          </select>
        </div>
      </div>
      {tabs.length ? (
        tabs.map((tab) => (
          <div
            key={tab.key}
            className="terminal-session-container"
            style={{ display: active === tab.key ? "flex" : "none" }}
          >
            <TerminalSession
              serverId={tab.serverId}
              active={active === tab.key}
            />
          </div>
        ))
      ) : (
        <EmptyState
          title="Все сеансы закрыты"
          description="Выберите сервер, чтобы открыть новое подключение."
        />
      )}
      <ConfirmDialog
        open={closing != null}
        onOpenChange={(open) => {
          if (!open) setClosing(null);
        }}
        title="Закрыть терминальную сессию?"
        description="SSH-соединение будет закрыто. Несохранённые изменения файлов этой сессии будут потеряны. Убедитесь, что текущая операция завершена."
        onConfirm={close}
        confirmLabel="Закрыть сеанс"
      />
      <ConfirmDialog
        open={blocker.state === "blocked"}
        onOpenChange={(open) => {
          if (!open && blocker.state === "blocked") blocker.reset();
        }}
        title="Покинуть терминал?"
        description="Открытые SSH-сеансы будут закрыты. Несохранённые изменения файлов будут потеряны. Убедитесь, что текущие операции завершены."
        confirmLabel="Закрыть сеансы и перейти"
        onConfirm={() => {
          if (blocker.state === "blocked") blocker.proceed();
        }}
      />
    </div>
  );
}
