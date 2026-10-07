import {
  Check,
  Folder,
  Loader2,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  Settings,
  Trash2,
  X,
} from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

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
};

function TreeConnector({ count }: { count: number }) {
  const height = Math.max(24, count * 32);
  const branches = Array.from({ length: count }, (_, i) => {
    const y = 10 + i * 32;
    return `M0.5 0 V${Math.max(0, y - 5)} Q0.5 ${y} 5.5 ${y} H11.5`;
  });
  return (
    <svg
      aria-hidden
      width="12"
      height={height}
      viewBox={`0 0 12 ${height}`}
      fill="none"
      className="pointer-events-none absolute top-0 start-[15px] text-border"
    >
      {branches.map((d, i) => (
        <path key={i} d={d} stroke="currentColor" strokeWidth="1" />
      ))}
    </svg>
  );
}

export function ChatThreadSidebar({ c, mobile = false, onNavigate }: ChatThreadSidebarProps) {
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

  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const openGroups = useMemo(() => {
    const map: Record<string, boolean> = {};
    for (const group of chatGroups) {
      map[group.id] = collapsed[group.id] === undefined ? group.id === chatGroups[0]?.id : !collapsed[group.id];
    }
    return map;
  }, [chatGroups, collapsed]);

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

  return (
    <aside
      className={cn(
        "relative z-[1] h-full shrink-0 flex-col overflow-hidden rounded-2xl wt-chat-panel",
        mobile ? "flex w-full rounded-none border-0 shadow-none" : "hidden w-[16.25rem] lg:flex",
      )}
    >
      <div className="flex min-h-0 flex-1 flex-col gap-3 p-3">
        <div className="flex items-center justify-between gap-2">
          <h1 className="truncate text-[13px] font-semibold tracking-tight text-foreground">
            {localize(lang, "Агент", "Agent")}
          </h1>
          <Button
            size="icon"
            variant="ghost"
            className="h-9 w-9 rounded-full bg-muted/50"
            onClick={() => {
              /* focus search */
              const el = document.getElementById(mobile ? "chat-history-search-mobile" : "chat-history-search");
              el?.focus();
            }}
            aria-label={localize(lang, "Поиск", "Search")}
          >
            <Search className="h-4 w-4" />
          </Button>
        </div>

        <nav className="flex shrink-0 flex-col gap-0.5">
          <button
            type="button"
            onClick={clearLastChatAndNew}
            className="flex w-full items-center gap-2 rounded-xl p-2 text-left text-[13px] text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
            aria-label={localize(lang, "Новый агент", "New agent")}
          >
            <Plus className="h-4 w-4 shrink-0" />
            <span>{localize(lang, "Новый агент", "New agent")}</span>
          </button>
          <Link
            to="/agents"
            onClick={onNavigate}
            className="flex w-full items-center gap-2 rounded-xl p-2 text-[13px] text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
            aria-label={localize(lang, "Автоматизации", "Automations")}
          >
            <MoreHorizontal className="h-4 w-4 shrink-0" />
            <span>{localize(lang, "Автоматизации", "Automations")}</span>
          </Link>
          <Link
            to="/settings"
            onClick={onNavigate}
            className="flex w-full items-center gap-2 rounded-xl p-2 text-[13px] text-muted-foreground transition-colors hover:bg-muted/60 hover:text-foreground"
            aria-label={localize(lang, "Настроить", "Customize")}
          >
            <Settings className="h-4 w-4 shrink-0" />
            <span>{localize(lang, "Настроить", "Customize")}</span>
          </Link>
        </nav>

        <div className="relative px-0.5">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground/60" />
          <input
            id={mobile ? "chat-history-search-mobile" : "chat-history-search"}
            value={chatFilter}
            onChange={(e) => setChatFilter(e.target.value)}
            placeholder={localize(lang, "Поиск…", "Search…")}
            className="h-8 w-full rounded-xl border-0 bg-muted/40 pl-8 pr-2.5 text-[12px] text-foreground outline-none placeholder:text-muted-foreground/55 focus:bg-muted/60"
          />
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto [scrollbar-width:none]">
          <div className="mb-2 px-1 text-[12px] font-medium text-muted-foreground">
            {localize(lang, "История", "History")}
          </div>
          {chatsQuery.isLoading ? (
            <div className="flex items-center gap-2 px-3 py-4 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" />
              {localize(lang, "Загрузка", "Loading")}
            </div>
          ) : null}
          {!chatsQuery.isLoading && !filteredChats.length ? (
            <div className="mx-1 rounded-xl border border-dashed border-border/50 px-3 py-8 text-center text-xs text-muted-foreground">
              {chats.length
                ? localize(lang, "Ничего не найдено", "No matches")
                : localize(lang, "История пуста", "No history")}
            </div>
          ) : null}

          <div className="flex flex-col gap-1">
            {chatGroups.map((group) => {
              const expanded = openGroups[group.id];
              return (
                <div key={group.id} className="flex flex-col">
                  <button
                    type="button"
                    aria-expanded={expanded}
                    onClick={() =>
                      setCollapsed((prev) => ({
                        ...prev,
                        [group.id]: expanded,
                      }))
                    }
                    className="flex w-full cursor-pointer items-center gap-2 rounded-xl p-2 text-left transition-colors hover:bg-muted/50"
                  >
                    <Folder className="h-4 w-4 shrink-0 text-muted-foreground" />
                    <span className="truncate text-[13px] text-muted-foreground">
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
                      <div className="relative flex flex-col gap-0.5 pt-0.5">
                        {expanded && group.chats.length ? (
                          <TreeConnector count={group.chats.length} />
                        ) : null}
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
                                  className="mb-0.5 ml-7 flex items-center gap-1 rounded-xl bg-muted px-2 py-1.5"
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
                                  onClick={() => {
                                    setSearchParams({ chat: String(chat.id) });
                                    onNavigate?.();
                                  }}
                                  className={cn(
                                    "flex w-full items-center gap-2.5 rounded-xl py-[5px] pe-2 ps-9 text-left transition-colors",
                                    selected
                                      ? "bg-muted text-foreground"
                                      : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
                                  )}
                                >
                                  <span className="min-w-0 flex-1 truncate text-[13px]">
                                    {chat.title}
                                    {chat.kind === "telegram" ? (
                                      <span className="ml-1.5 rounded bg-muted px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">
                                        TG
                                      </span>
                                    ) : null}
                                  </span>
                                  <span className="inline-flex shrink-0 items-center justify-center rounded-sm bg-muted/80 px-1 py-px text-[10px] text-muted-foreground">
                                    {formatRelativeChatAge(chat.updated_at)}
                                  </span>
                                </button>
                                <div className="absolute right-1.5 top-1/2 z-[2] hidden -translate-y-1/2 items-center gap-0.5 group-hover/chat:flex">
                                  <button
                                    type="button"
                                    onClick={() => startRename(chat)}
                                    className="rounded p-1 text-muted-foreground/70 hover:bg-muted hover:text-foreground"
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
                                    className="rounded p-1 text-muted-foreground/70 hover:bg-muted hover:text-destructive"
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
          <div className="shrink-0 pt-1">
            <AgentLimitsCard
              context={usageLimits.context}
              limits={usageLimits.limits}
              plan={localize(lang, "Оператор", "Operator")}
              planHref="/settings/limits"
              defaultExpanded={false}
              className="!rounded-xl !px-3 !pb-3 !pt-2"
            />
          </div>
        ) : null}
      </div>
    </aside>
  );
}
