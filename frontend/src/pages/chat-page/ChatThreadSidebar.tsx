import {
  Check,
  Loader2,
  MessageSquare,
  Pencil,
  Plus,
  Search,
  Shield,
  Sunrise,
  Trash2,
  X,
} from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";

import { requestDutyBriefing } from "@/api";
import { Button } from "@/components/ui/button";
import { localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";

import { formatDateTime } from "./chatHelpers";
import { CHAT_MOTION } from "./chatMotion";
import type { ChatPageController } from "./useChatPageController";

type ChatThreadSidebarProps = {
  c: ChatPageController;
  mobile?: boolean;
  onNavigate?: () => void;
};

export function ChatThreadSidebar({ c, mobile = false, onNavigate }: ChatThreadSidebarProps) {
  const reduceMotion = useReducedMotion();
  const {
    lang,
    toast,
    queryClient,
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
  } = c;

  return (
    <aside
      className={cn(
        "relative z-[1] h-full shrink-0 flex-col border-r border-border/60 bg-card",
        mobile ? "flex w-full" : "hidden w-[15.5rem] lg:flex",
      )}
    >
      <div className="flex items-center justify-between gap-2 px-3 pb-2 pt-3.5">
        <h1 className="truncate text-[13px] font-semibold tracking-tight text-foreground">
          {localize(lang, "Чаты", "Chats")}
        </h1>
        <div className="flex items-center gap-0.5">
          <Button
            size="icon"
            variant="ghost"
            className="h-8 w-8 rounded-lg"
            onClick={() => {
              void requestDutyBriefing()
                .then((res) => {
                  const id = res.chat?.id;
                  if (id) {
                    setSearchParams({ chat: String(id) });
                    void queryClient.invalidateQueries({ queryKey: ["assistant", "chats"] });
                    void queryClient.invalidateQueries({ queryKey: ["assistant", "chat", id] });
                  }
                  toast({
                    title: localize(lang, "Дежурный", "Duty"),
                    description: localize(lang, "Брифинг обновлён", "Briefing refreshed"),
                  });
                })
                .catch((error) => {
                  toast({
                    title: localize(lang, "Дежурный", "Duty"),
                    description: error instanceof Error ? error.message : String(error),
                    variant: "destructive",
                  });
                });
            }}
            aria-label={localize(lang, "Брифинг дежурного", "Duty briefing")}
            title={localize(lang, "Брифинг дежурного", "Duty briefing")}
          >
            <Sunrise className="h-4 w-4" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            className="h-8 w-8 rounded-lg"
            onClick={clearLastChatAndNew}
            aria-label={localize(lang, "Новый чат", "New chat")}
            title={localize(lang, "Новый чат", "New chat")}
          >
            <Plus className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="px-2.5 pb-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground/60" />
          <input
            value={chatFilter}
            onChange={(e) => setChatFilter(e.target.value)}
            placeholder={localize(lang, "Поиск…", "Search…")}
            className="h-8 w-full rounded-lg border-0 bg-muted/40 pl-8 pr-2.5 text-[12px] text-foreground outline-none placeholder:text-muted-foreground/55 focus:bg-muted/60"
          />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
        {chatsQuery.isLoading ? (
          <div className="flex items-center gap-2 px-3 py-4 text-xs text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" />
            {localize(lang, "Загрузка", "Loading")}
          </div>
        ) : null}
        {!chatsQuery.isLoading && !filteredChats.length ? (
          <div className="mx-1 rounded-sm border border-dashed border-border/50 px-3 py-8 text-center text-xs text-muted-foreground">
            {chats.length
              ? localize(lang, "Ничего не найдено", "No matches")
              : localize(lang, "История пуста", "No history")}
          </div>
        ) : null}
        {chatGroups.map((group) => (
          <div key={group.id}>
            <div className="px-2.5 pb-1 pt-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/55">
              {lang === "ru" ? group.labelRu : group.labelEn}
            </div>
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
              return (
                <motion.div
                  key={chat.id}
                  layout="position"
                  initial={reduceMotion ? false : { opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={reduceMotion ? undefined : { opacity: 0, y: -2 }}
                  transition={reduceMotion ? { duration: 0 } : CHAT_MOTION.enter}
                  className="group/chat relative mb-0.5"
                >
                  {selected ? (
                    <motion.span
                      layoutId={mobile ? "selected-chat-mobile" : "selected-chat-desktop"}
                      className="pointer-events-none absolute inset-0 rounded-lg bg-muted"
                      transition={
                        reduceMotion
                          ? { duration: 0 }
                          : { type: "spring", stiffness: 420, damping: 38, mass: 0.8 }
                      }
                      aria-hidden
                    />
                  ) : null}
                  <button
                    type="button"
                    onClick={() => {
                      setSearchParams({ chat: String(chat.id) });
                      onNavigate?.();
                    }}
                    className={cn(
                      "relative z-[1] grid w-full min-w-0 grid-cols-[1rem_minmax(0,1fr)] gap-2 rounded-lg px-2.5 py-2 pr-14 text-left transition-colors",
                      selected
                        ? "text-foreground"
                        : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
                    )}
                  >
                    {chat.kind === "duty" ? (
                      <Shield className="mt-0.5 h-3.5 w-3.5 shrink-0 opacity-70" strokeWidth={1.75} />
                    ) : (
                      <MessageSquare className="mt-0.5 h-3.5 w-3.5 shrink-0 opacity-50" strokeWidth={1.75} />
                    )}
                    <span className="min-w-0">
                      <span className="block truncate text-[13px] font-medium tracking-tight">
                        {chat.title}
                      </span>
                      <span className="mt-0.5 block truncate text-[10px] text-muted-foreground/65">
                        {formatDateTime(chat.updated_at, lang)}
                      </span>
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
        ))}
      </div>
    </aside>
  );
}
