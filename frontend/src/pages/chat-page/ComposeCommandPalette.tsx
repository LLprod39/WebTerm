import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Bot,
  ChevronLeft,
  Loader2,
  Pin,
  Server,
  Sparkles,
  Terminal,
  UserRound,
  Users,
} from "lucide-react";

import { fetchAccessUsers, fetchFrontendBootstrap, type AccessUser, type FrontendServer } from "@/api";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

import {
  type SlashCommandDef,
  detectComposeTrigger,
  filterSlashCommands,
  replaceComposeRange,
} from "./composeCommands";

export type PinnedServer = { id: number; name: string; host?: string };
export type PinnedUser = { id: number; username: string };

export type ComposePaletteHandle = {
  /** Returns true if the key was handled (parent should not submit). */
  handleKeyDown: (event: React.KeyboardEvent) => boolean;
};

type BrowseMode = "servers" | "users" | "agents" | null;

type Props = {
  draft: string;
  caret: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onDraftChange: (next: string, caret?: number) => void;
  onSendMessage: (message: string) => void;
  pinnedServers: PinnedServer[];
  pinnedUsers: PinnedUser[];
  onPinServer: (server: PinnedServer) => void;
  onUnpinServer: (id: number) => void;
  onPinUser: (user: PinnedUser) => void;
  onUnpinUser: (id: number) => void;
};

export const ComposeCommandPalette = forwardRef<ComposePaletteHandle, Props>(function ComposeCommandPalette({
  draft,
  caret,
  open,
  onOpenChange,
  onDraftChange,
  onSendMessage,
  pinnedServers,
  pinnedUsers,
  onPinServer,
  onUnpinServer,
  onPinUser,
  onUnpinUser,
}, ref) {
  const { lang } = useI18n();
  const [highlight, setHighlight] = useState(0);
  const [browse, setBrowse] = useState<BrowseMode>(null);
  const [filter, setFilter] = useState("");
  const listRef = useRef<HTMLDivElement | null>(null);

  const trigger = useMemo(() => detectComposeTrigger(draft, caret), [draft, caret]);

  // Auto-open when typing / or @
  useEffect(() => {
    if (trigger) {
      onOpenChange(true);
      if (trigger.type === "slash") {
        setBrowse(null);
        setFilter(trigger.query);
      } else {
        setBrowse("servers");
        setFilter(trigger.query);
      }
      setHighlight(0);
    }
  }, [trigger?.type, trigger?.query]); // eslint-disable-line react-hooks/exhaustive-deps

  const serversQuery = useQuery({
    queryKey: ["compose", "servers"],
    queryFn: fetchFrontendBootstrap,
    enabled: open && (browse === "servers" || trigger?.type === "mention"),
    staleTime: 30_000,
  });

  const usersQuery = useQuery({
    queryKey: ["compose", "users"],
    queryFn: fetchAccessUsers,
    enabled: open && browse === "users",
    staleTime: 60_000,
    retry: false,
  });

  const servers = serversQuery.data?.servers || [];
  const users = usersQuery.data?.users || [];

  const slashItems = useMemo(
    () => (browse ? [] : filterSlashCommands(filter, lang === "ru" ? "ru" : "en")),
    [browse, filter, lang],
  );

  const serverItems = useMemo(() => {
    if (browse !== "servers" && trigger?.type !== "mention") return [];
    const q = filter.toLowerCase();
    return servers
      .filter(
        (s) =>
          !q ||
          s.name.toLowerCase().includes(q) ||
          s.host.toLowerCase().includes(q) ||
          String(s.id).includes(q),
      )
      .slice(0, 40);
  }, [browse, filter, servers, trigger?.type]);

  const userItems = useMemo(() => {
    if (browse !== "users") return [];
    const q = filter.toLowerCase();
    return users
      .filter(
        (u) =>
          !q ||
          u.username.toLowerCase().includes(q) ||
          String(u.id).includes(q) ||
          (u.email || "").toLowerCase().includes(q),
      )
      .slice(0, 40);
  }, [browse, filter, users]);

  const agentItems = useMemo(() => {
    if (browse !== "agents") return [];
    // Lightweight: agents come from pinned or free-text only for now
    return [];
  }, [browse]);

  const mode: "slash" | "servers" | "users" | "agents" | "closed" = !open
    ? "closed"
    : browse === "servers" || trigger?.type === "mention"
      ? "servers"
      : browse === "users"
        ? "users"
        : browse === "agents"
          ? "agents"
          : "slash";

  const itemCount =
    mode === "slash"
      ? slashItems.length
      : mode === "servers"
        ? serverItems.length
        : mode === "users"
          ? userItems.length
          : agentItems.length;

  useEffect(() => {
    setHighlight(0);
  }, [mode, filter]);

  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-idx="${highlight}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [highlight]);

  const clearTrigger = (replacement = "") => {
    if (!trigger) {
      onDraftChange(replacement);
      return;
    }
    const next = replaceComposeRange(draft, trigger.start, trigger.end, replacement);
    onDraftChange(next, trigger.start + replacement.length);
  };

  const applySlash = (cmd: SlashCommandDef) => {
    if (cmd.kind === "browse" && cmd.browse) {
      setBrowse(cmd.browse);
      setFilter("");
      // Keep `/` removed from draft for cleaner UX
      clearTrigger("");
      setHighlight(0);
      return;
    }
    const built = cmd.build?.(filter.includes(" ") ? filter.slice(filter.indexOf(" ") + 1) : "") || "";
    if (cmd.kind === "send") {
      clearTrigger("");
      onOpenChange(false);
      setBrowse(null);
      onSendMessage(built);
      return;
    }
    // insert into draft
    clearTrigger(built + " ");
    onOpenChange(false);
    setBrowse(null);
  };

  const pickServer = (s: FrontendServer) => {
    const pinned = { id: s.id, name: s.name, host: s.host };
    onPinServer(pinned);
    if (trigger?.type === "mention") {
      clearTrigger(`@${s.name} `);
    } else {
      // browsing via /servers — pin only, don't inject text
      clearTrigger("");
    }
    onOpenChange(false);
    setBrowse(null);
  };

  const pickUser = (u: AccessUser) => {
    onPinUser({ id: u.id, username: u.username });
    clearTrigger("");
    onOpenChange(false);
    setBrowse(null);
  };

  const handleKeyDown = (event: React.KeyboardEvent): boolean => {
    if (!open) return false;
    if (event.key === "Escape") {
      if (browse) {
        setBrowse(null);
        setFilter("");
      } else {
        onOpenChange(false);
      }
      return true;
    }
    if (event.key === "ArrowDown") {
      setHighlight((h) => Math.min(Math.max(itemCount - 1, 0), h + 1));
      return true;
    }
    if (event.key === "ArrowUp") {
      setHighlight((h) => Math.max(0, h - 1));
      return true;
    }
    if (event.key === "Enter" && !event.shiftKey && itemCount > 0) {
      if (mode === "slash" && slashItems[highlight]) applySlash(slashItems[highlight]);
      else if (mode === "servers" && serverItems[highlight]) pickServer(serverItems[highlight]);
      else if (mode === "users" && userItems[highlight]) pickUser(userItems[highlight]);
      return true;
    }
    return false;
  };

  useImperativeHandle(ref, () => ({ handleKeyDown }), [
    open,
    browse,
    mode,
    highlight,
    itemCount,
    slashItems,
    serverItems,
    userItems,
  ]);

  if (!open) return null;

  return (
    <div
      className="absolute bottom-full left-0 right-0 z-30 mb-2 overflow-hidden rounded-sm border border-border/80 bg-card/95 shadow-xl"
      role="listbox"
    >
      <div className="flex items-center justify-between border-b border-border/60 px-3 py-2">
        <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
          {browse ? (
            <button
              type="button"
              className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"
              onClick={() => {
                setBrowse(null);
                setFilter("");
              }}
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              {localize(lang, "Команды", "Commands")}
            </button>
          ) : (
            <>
              <Sparkles className="h-3.5 w-3.5 text-primary" />
              {localize(lang, "Команды", "Commands")}
            </>
          )}
          {mode === "servers" ? (
            <span className="font-normal text-muted-foreground">
              · {localize(lang, "Серверы", "Servers")}
            </span>
          ) : null}
          {mode === "users" ? (
            <span className="font-normal text-muted-foreground">
              · {localize(lang, "Пользователи", "Users")}
            </span>
          ) : null}
        </div>
        <span className="text-2xs text-muted-foreground">
          ↑↓ Enter · Esc
        </span>
      </div>

      <div ref={listRef} className="max-h-64 overflow-y-auto p-1">
        {mode === "slash" ? (
          slashItems.length ? (
            slashItems.map((cmd, idx) => (
              <button
                key={cmd.id}
                type="button"
                data-idx={idx}
                role="option"
                aria-selected={idx === highlight}
                className={cn(
                  "flex w-full items-start gap-3 rounded-sm px-3 py-2 text-left transition-colors",
                  idx === highlight ? "bg-primary/15 text-foreground" : "hover:bg-secondary/50",
                )}
                onMouseEnter={() => setHighlight(idx)}
                onClick={() => applySlash(cmd)}
              >
                <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-sm border border-border/60 bg-background/70">
                  {cmd.browse === "servers" ? (
                    <Server className="h-3.5 w-3.5 text-primary" />
                  ) : cmd.browse === "users" ? (
                    <Users className="h-3.5 w-3.5 text-primary" />
                  ) : cmd.browse === "agents" ? (
                    <Bot className="h-3.5 w-3.5 text-primary" />
                  ) : cmd.trigger === "run" ? (
                    <Terminal className="h-3.5 w-3.5 text-primary" />
                  ) : (
                    <Sparkles className="h-3.5 w-3.5 text-primary" />
                  )}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="font-mono text-xs font-semibold text-primary">/{cmd.trigger}</span>
                    <span className="truncate text-sm font-medium">
                      {lang === "ru" ? cmd.labelRu : cmd.labelEn}
                    </span>
                    {cmd.kind === "browse" ? (
                      <span className="rounded border border-border/60 px-1 text-2xs text-muted-foreground">
                        {localize(lang, "просмотр", "browse")}
                      </span>
                    ) : null}
                  </span>
                  <span className="mt-0.5 block truncate text-2xs text-muted-foreground">
                    {lang === "ru" ? cmd.hintRu : cmd.hintEn}
                  </span>
                </span>
              </button>
            ))
          ) : (
            <div className="px-3 py-6 text-center text-xs text-muted-foreground">
              {localize(lang, "Нет команд", "No commands")}
            </div>
          )
        ) : null}

        {mode === "servers" ? (
          serversQuery.isLoading ? (
            <div className="flex items-center gap-2 px-3 py-4 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              {localize(lang, "Загрузка серверов…", "Loading servers…")}
            </div>
          ) : serverItems.length ? (
            serverItems.map((s, idx) => {
              const isPinned = pinnedServers.some((p) => p.id === s.id);
              return (
                <button
                  key={s.id}
                  type="button"
                  data-idx={idx}
                  role="option"
                  aria-selected={idx === highlight}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-sm px-3 py-2 text-left transition-colors",
                    idx === highlight ? "bg-primary/15" : "hover:bg-secondary/50",
                  )}
                  onMouseEnter={() => setHighlight(idx)}
                  onClick={() => (isPinned ? onUnpinServer(s.id) : pickServer(s))}
                >
                  <Server className="h-4 w-4 shrink-0 text-primary" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{s.name}</span>
                    <span className="block truncate font-mono text-2xs text-muted-foreground">
                      {s.host}:{s.port} · {s.status}
                    </span>
                  </span>
                  <span
                    className={cn(
                      "inline-flex items-center gap-1 rounded-sm border px-1.5 py-0.5 text-2xs",
                      isPinned
                        ? "border-primary/40 bg-primary/10 text-primary"
                        : "border-border/60 text-muted-foreground",
                    )}
                  >
                    <Pin className="h-3 w-3" />
                    {isPinned
                      ? localize(lang, "открепить", "unpin")
                      : localize(lang, "прикрепить", "pin")}
                  </span>
                </button>
              );
            })
          ) : (
            <div className="px-3 py-6 text-center text-xs text-muted-foreground">
              {localize(lang, "Серверы не найдены", "No servers found")}
            </div>
          )
        ) : null}

        {mode === "users" ? (
          usersQuery.isLoading ? (
            <div className="flex items-center gap-2 px-3 py-4 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              {localize(lang, "Загрузка…", "Loading…")}
            </div>
          ) : usersQuery.isError ? (
            <div className="px-3 py-6 text-center text-xs text-muted-foreground">
              {localize(
                lang,
                "Нет доступа к списку пользователей (нужны права settings)",
                "No access to users list (settings permission required)",
              )}
            </div>
          ) : userItems.length ? (
            userItems.map((u, idx) => {
              const isPinned = pinnedUsers.some((p) => p.id === u.id);
              return (
                <button
                  key={u.id}
                  type="button"
                  data-idx={idx}
                  role="option"
                  aria-selected={idx === highlight}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-sm px-3 py-2 text-left transition-colors",
                    idx === highlight ? "bg-primary/15" : "hover:bg-secondary/50",
                  )}
                  onMouseEnter={() => setHighlight(idx)}
                  onClick={() => (isPinned ? onUnpinUser(u.id) : pickUser(u))}
                >
                  <UserRound className="h-4 w-4 shrink-0 text-primary" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{u.username}</span>
                    <span className="block truncate text-2xs text-muted-foreground">
                      {u.email || `id ${u.id}`}
                      {u.is_staff ? " · staff" : ""}
                    </span>
                  </span>
                  <span
                    className={cn(
                      "inline-flex items-center gap-1 rounded-sm border px-1.5 py-0.5 text-2xs",
                      isPinned
                        ? "border-primary/40 bg-primary/10 text-primary"
                        : "border-border/60 text-muted-foreground",
                    )}
                  >
                    <Pin className="h-3 w-3" />
                    {isPinned
                      ? localize(lang, "открепить", "unpin")
                      : localize(lang, "прикрепить", "pin")}
                  </span>
                </button>
              );
            })
          ) : (
            <div className="px-3 py-6 text-center text-xs text-muted-foreground">
              {localize(lang, "Пользователи не найдены", "No users found")}
            </div>
          )
        ) : null}

        {mode === "agents" ? (
          <div className="space-y-2 px-3 py-4 text-xs text-muted-foreground">
            <p>
              {localize(
                lang,
                "Вставьте в сообщение: «покажи агентов» или /fleet. Список агентов доступен через чат.",
                "Type “list agents” or /fleet. Agent list is available via chat tools.",
              )}
            </p>
            <button
              type="button"
              className="rounded-sm border border-border/70 px-2 py-1.5 text-foreground hover:bg-secondary/50"
              onClick={() => {
                onOpenChange(false);
                setBrowse(null);
                onSendMessage("Покажи список моих агентов.");
              }}
            >
              {localize(lang, "Спросить про агентов", "Ask about agents")}
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
});
