import {
  Check,
  Folder,
  Loader2,
  PanelLeft,
  Pencil,
  Plus,
  Trash2,
  X,
} from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useMemo, useState } from "react";

import { AgentLimitsCard } from "@/boardui/components/application/agent-limits/agent-limits-card";
import { Button } from "@/components/ui/button";
import { localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";

import { formatRelativeChatAge } from "./chatHelpers";
import { CHAT_MOTION } from "./chatMotion";
import type { ChatPageController } from "./useChatPageController";

const CONTEXT_SOFT_LIMIT = 128_000;

type ChatThreadSidebarProps = {
  c: ChatPageController;
  mobile?: boolean;
  onNavigate?: () => void;
  collapsed?: boolean;
  onExpand?: () => void;
};

export function ChatThreadSidebar({
  c,
  mobile = false,
  onNavigate,
  collapsed = false,
  onExpand,
}: ChatThreadSidebarProps) {
  const reduceMotion = useReducedMotion();
  const {
    lang,
    setSearchParams,
    chatFilter,
    setChatFilter,
    chatsQuery,
    chats,
    filteredChats,
    chatGroups,
    activeChatId,
    renamingChatId,
    setRenamingChatId,
    renameDraft,
    setRenameDraft,
    commitRename,
    startRename,
    deleteChatMutation,
    clearLastChatAndNew,
    activeChat,
  } = c;

  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});
  const openGroups = useMemo(() => {
    const map: Record<string, boolean> = {};
    for (const group of chatGroups) {
      map[group.id] =
        collapsedGroups[group.id] === undefined
          ? group.id === chatGroups[0]?.id
          : !collapsedGroups[group.id];
    }
    return map;
  }, [chatGroups, collapsedGroups]);

  const usageLimits = useMemo(() => {
    const usage = (activeChat?.total_usage || {}) as {
      input_tokens?: number;
      output_tokens?: number;
      cache_read_tokens?: number;
      reasoning_tokens?: number;
    };
    const input = Number(usage.input_tokens || 0);
    const output = Number(usage.output_tokens || 0);
    const cache = Number(usage.cache_read_tokens || 0);
    const reasoning = Number(usage.reasoning_tokens || 0);
    const total = input + output + cache + reasoning;
    if (!total) return null;
    const segments = [
      { label: localize(lang, "Вход", "Input"), tokens: input },
      { label: localize(lang, "Выход", "Output"), tokens: output },
    ];
    if (cache > 0) segments.push({ label: localize(lang, "Кэш", "Cache"), tokens: cache });
    if (reasoning > 0) {
      segments.push({ label: localize(lang, "Рассуждение", "Reasoning"), tokens: reasoning });
    }
    const pct = Math.min(1, total / CONTEXT_SOFT_LIMIT);
    return {
      context: { max: CONTEXT_SOFT_LIMIT, segments },
      limits: [
        {
          label: localize(lang, "Контекст сессии", "Session context"),
          used: pct,
          resets: localize(lang, "за чат", "per chat"),
        },
      ],
    };
  }, [activeChat?.total_usage, lang]);

  if (!mobile && collapsed) {
    return (
      <aside
        data-testid="chat-thread-sidebar"
        data-chat-sidebar="collapsed"
        className="relative z-[1] hidden h-full w-12 shrink-0 flex-col items-center gap-1.5 border-e border-border/60 bg-card/40 py-2 lg:flex"
      >
        <Button
          size="icon"
          variant="ghost"
          className="h-8 w-8 rounded-lg"
          onClick={onExpand}
          aria-label={localize(lang, "Показать историю чатов", "Show chat history")}
          title={localize(lang, "История · Ctrl/⌘B", "History · Ctrl/⌘B")}
        >
          <PanelLeft className="h-4 w-4" />
        </Button>
        <Button
          size="icon"
          variant="ghost"
          className="h-8 w-8 rounded-lg"
          onClick={clearLastChatAndNew}
          aria-label={localize(lang, "Новый чат", "New chat")}
        >
          <Plus className="h-4 w-4" />
        </Button>
      </aside>
    );
  }

  return (
    <aside
      data-testid="chat-thread-sidebar"
      data-chat-sidebar={mobile ? "mobile" : "expanded"}
      className={cn(
        "relative z-[1] h-full min-h-0 shrink-0 flex-col overflow-hidden border-border/60 bg-card/40",
        mobile ? "flex w-full border-0" : "hidden w-[16.5rem] border-e lg:flex",
      )}
    >
      <div className="flex min-h-0 flex-1 flex-col px-2.5 pb-2.5 pt-3">
        <div className="mb-2.5 flex items-center px-1">
          <h1 className="truncate text-[13px] font-semibold tracking-tight text-foreground">
            {localize(lang, "Чат", "Chat")}
          </h1>
        </div>

        <button
          type="button"
          onClick={clearLastChatAndNew}
          className="mb-2.5 flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[13px] text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
          aria-label={localize(lang, "Новый чат", "New chat")}
        >
          <Plus className="h-4 w-4 shrink-0" />
          <span>{localize(lang, "Новый чат", "New chat")}</span>
        </button>

        <div className="relative mb-3 px-0.5">
          <input
            id={mobile ? "chat-history-search-mobile" : "chat-history-search"}
            value={chatFilter}
            onChange={(e) => setChatFilter(e.target.value)}
            placeholder={localize(lang, "Поиск…", "Search…")}
            aria-label={localize(lang, "Поиск по истории", "Search history")}
            className="h-8 w-full rounded-lg border-0 bg-muted/45 px-2.5 text-[12px] text-foreground outline-none placeholder:text-muted-foreground/55 focus:bg-muted/65"
          />
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto [scrollbar-width:thin]">
          <div className="mb-1.5 px-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground/80">
            {localize(lang, "История", "History")}
          </div>
          {chatsQuery.isLoading ? (
            <div className="flex items-center gap-2 px-2 py-4 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" />
              {localize(lang, "Загрузка", "Loading")}
            </div>
          ) : null}
          {!chatsQuery.isLoading && !filteredChats.length ? (
            <div className="px-2 py-8 text-center text-xs text-muted-foreground">
              {chats.length
                ? localize(lang, "Ничего не найдено", "No matches")
                : localize(lang, "История пуста", "No history")}
            </div>
          ) : null}

          <div className="flex flex-col gap-0.5">
            {chatGroups.map((group) => {
              const expanded = openGroups[group.id];
              return (
                <div key={group.id} className="flex flex-col">
                  <button
                    type="button"
                    aria-expanded={expanded}
                    onClick={() =>
                      setCollapsedGroups((prev) => ({
                        ...prev,
                        [group.id]: expanded,
                      }))
                    }
                    className="flex w-full cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-muted/50"
                  >
                    <Folder className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                    <span className="truncate text-[12px] text-muted-foreground">
                      {lang === "ru" ? group.labelRu : group.labelEn}
                    </span>
                  </button>
                  <div
                    className={cn(
                      "grid transition-[grid-template-rows,opacity] duration-300 ease-out",
                      expanded ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0",
                    )}
                    aria-hidden={!expanded}
                  >
                    <div className="overflow-hidden">
                      <div className="flex flex-col gap-0.5 pb-1">
                        <AnimatePresence initial={false}>
                          {group.chats.map((chat) => {
                            const selected = chat.id === activeChatId;
                            if (renamingChatId === chat.id) {
                              return (
                                <motion.div
                                  key={chat.id}
                                  layout="position"
                                  initial={reduceMotion ? false : { opacity: 0, y: 4 }}
                                  animate={{ opacity: 1, y: 0 }}
                                  exit={reduceMotion ? undefined : { opacity: 0, y: -2 }}
                                  transition={reduceMotion ? { duration: 0 } : CHAT_MOTION.enter}
                                  className="mb-0.5 flex items-center gap-1 rounded-lg bg-muted px-2 py-1.5"
                                >
                                  <input
                                    autoFocus
                                    value={renameDraft}
                                    onChange={(e) => setRenameDraft(e.target.value)}
                                    onKeyDown={(e) => {
                                      if (e.key === "Enter") commitRename();
                                      if (e.key === "Escape") setRenamingChatId(null);
                                    }}
                                    className="h-6 w-full min-w-0 flex-1 bg-transparent text-[13px] text-foreground outline-none"
                                  />
                                  <button
                                    type="button"
                                    onClick={commitRename}
                                    className="shrink-0 rounded p-1 text-muted-foreground hover:text-foreground"
                                    aria-label={localize(lang, "Сохранить", "Save")}
                                  >
                                    <Check className="h-3.5 w-3.5" />
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => setRenamingChatId(null)}
                                    className="shrink-0 rounded p-1 text-muted-foreground hover:text-foreground"
                                    aria-label={localize(lang, "Отмена", "Cancel")}
                                  >
                                    <X className="h-3.5 w-3.5" />
                                  </button>
                                </motion.div>
                              );
                            }
                            const age = formatRelativeChatAge(chat.updated_at);
                            return (
                              <motion.div
                                key={chat.id}
                                layout="position"
                                initial={reduceMotion ? false : { opacity: 0, y: 4 }}
                                animate={{ opacity: 1, y: 0 }}
                                exit={reduceMotion ? undefined : { opacity: 0, y: -2 }}
                                transition={reduceMotion ? { duration: 0 } : CHAT_MOTION.enter}
                                className="group/chat relative"
                              >
                                <button
                                  type="button"
                                  title={chat.title}
                                  onClick={() => {
                                    setSearchParams({ chat: String(chat.id) });
                                    onNavigate?.();
                                  }}
                                  className={cn(
                                    "flex w-full items-baseline gap-2 rounded-lg px-2 py-[6px] text-left transition-colors",
                                    selected
                                      ? "bg-muted text-foreground"
                                      : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
                                  )}
                                >
                                  <span className="min-w-0 flex-1 truncate text-[13px] leading-5">
                                    {chat.title}
                                    {chat.kind === "telegram" ? (
                                      <span className="ml-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground/70">
                                        TG
                                      </span>
                                    ) : null}
                                  </span>
                                  {age ? (
                                    <span className="shrink-0 text-[10px] tabular-nums text-muted-foreground/55">
                                      {age}
                                    </span>
                                  ) : null}
                                </button>
                                <div className="absolute right-1 top-1/2 z-[2] hidden -translate-y-1/2 items-center gap-0.5 bg-gradient-to-l from-muted from-60% to-transparent pl-4 group-hover/chat:flex">
                                  <button
                                    type="button"
                                    onClick={() => startRename(chat)}
                                    className="rounded p-1 text-muted-foreground/70 hover:bg-background/60 hover:text-foreground"
                                    aria-label={localize(lang, "Переименовать", "Rename")}
                                    title={localize(lang, "Переименовать", "Rename")}
                                  >
                                    <Pencil className="h-3 w-3" />
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => {
                                      const ok = window.confirm(
                                        localize(
                                          lang,
                                          `Удалить чат «${chat.title}»? Действие необратимо.`,
                                          `Delete chat "${chat.title}"? This cannot be undone.`,
                                        ),
                                      );
                                      if (ok) deleteChatMutation.mutate(chat.id);
                                    }}
                                    className="rounded p-1 text-muted-foreground/70 hover:bg-background/60 hover:text-destructive"
                                    aria-label={localize(lang, "Удалить", "Delete")}
                                    title={localize(lang, "Удалить", "Delete")}
                                  >
                                    <Trash2 className="h-3 w-3" />
                                  </button>
                                </div>
                              </motion.div>
                            );
                          })}
                        </AnimatePresence>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {usageLimits ? (
          <div className="shrink-0 border-t border-border/50 pt-2">
            <AgentLimitsCard
              context={usageLimits.context}
              limits={usageLimits.limits}
              plan={localize(lang, "Оператор", "Operator")}
              planHref="/settings/limits"
              defaultExpanded={false}
              className="!rounded-lg !border-0 !bg-transparent !px-2 !pb-1 !pt-1 !shadow-none"
            />
          </div>
        ) : null}
      </div>
    </aside>
  );
}
