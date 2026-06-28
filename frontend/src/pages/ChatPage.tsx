import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Loader2, MessageSquare, Plus, Send, Workflow } from "lucide-react";

import {
  cancelAssistantAction,
  confirmAssistantAction,
  fetchAssistantChat,
  fetchAssistantChats,
  sendAssistantChatMessage,
  startAssistantChat,
  type AssistantChatSession,
} from "@/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

import { MessageBubble } from "./chat-page/ChatMessageViews";
import { QUICK_PROMPTS, formatDateTime, mergeTurnIntoChat, replaceActionInChat } from "./chat-page/chatHelpers";


export default function ChatPage() {
  const { lang } = useI18n();
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [draft, setDraft] = useState("");
  const [actionWorkingId, setActionWorkingId] = useState<number | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);
  const activeChatId = Number(searchParams.get("chat") || 0) || null;

  const chatsQuery = useQuery({
    queryKey: ["assistant", "chats"],
    queryFn: fetchAssistantChats,
    staleTime: 20_000,
  });

  const activeChatQuery = useQuery({
    queryKey: ["assistant", "chat", activeChatId],
    queryFn: () => fetchAssistantChat(activeChatId as number),
    enabled: Boolean(activeChatId),
    staleTime: 10_000,
  });

  const chats = chatsQuery.data?.chats || [];
  const activeChat = activeChatQuery.data;
  const messages = activeChat?.messages || [];

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, activeChatId]);

  const sendMutation = useMutation({
    mutationFn: (message: string) => (
      activeChatId ? sendAssistantChatMessage(activeChatId, message) : startAssistantChat(message)
    ),
    onSuccess: (turn) => {
      queryClient.setQueryData<AssistantChatSession>(
        ["assistant", "chat", turn.chat.id],
        (previous) => mergeTurnIntoChat(previous, turn),
      );
      void queryClient.invalidateQueries({ queryKey: ["assistant", "chats"] });
      setSearchParams({ chat: String(turn.chat.id) });
      setDraft("");
    },
    onError: (error) => {
      toast({
        title: localize(lang, "Чат не ответил", "Chat failed"),
        description: error instanceof Error ? error.message : String(error),
        variant: "destructive",
      });
    },
  });

  const actionMutation = useMutation({
    mutationFn: ({ actionId, intent }: { actionId: number; intent: "confirm" | "cancel" }) => (
      intent === "confirm" ? confirmAssistantAction(actionId) : cancelAssistantAction(actionId)
    ),
    onMutate: ({ actionId }) => {
      setActionWorkingId(actionId);
    },
    onSuccess: (action) => {
      queryClient.setQueryData<AssistantChatSession | undefined>(
        ["assistant", "chat", action.chat_id],
        (previous) => replaceActionInChat(previous, action),
      );
      void queryClient.invalidateQueries({ queryKey: ["assistant", "chat", action.chat_id] });
      void queryClient.invalidateQueries({ queryKey: ["assistant", "chats"] });
    },
    onError: (error) => {
      toast({
        title: localize(lang, "Действие не выполнено", "Action failed"),
        description: error instanceof Error ? error.message : String(error),
        variant: "destructive",
      });
    },
    onSettled: () => {
      setActionWorkingId(null);
    },
  });

  const isBusy = sendMutation.isPending;
  const selectedTitle = activeChat?.title || localize(lang, "Новый чат", "New chat");
  const prompts = QUICK_PROMPTS[lang];

  const submitMessage = () => {
    const text = draft.trim();
    if (!text || isBusy) return;
    sendMutation.mutate(text);
  };

  return (
    <div className="flex h-[calc(100vh-4rem)] min-h-[620px] bg-background md:h-screen">
      <aside className="hidden w-72 shrink-0 border-r border-border/70 bg-card/45 lg:flex lg:flex-col">
        <div className="flex h-16 items-center justify-between border-b border-border/70 px-4">
          <div className="min-w-0">
            <h1 className="truncate text-sm font-semibold text-foreground">{localize(lang, "Чат", "Chat")}</h1>
            <p className="truncate text-xs text-muted-foreground">WebTermAI</p>
          </div>
          <Button
            size="icon"
            variant="outline"
            onClick={() => setSearchParams({})}
            aria-label={localize(lang, "Новый чат", "New chat")}
            title={localize(lang, "Новый чат", "New chat")}
          >
            <Plus className="h-4 w-4" />
          </Button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-2">
          {chatsQuery.isLoading ? (
            <div className="flex items-center gap-2 px-3 py-3 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              {localize(lang, "Загрузка", "Loading")}
            </div>
          ) : null}
          {!chatsQuery.isLoading && !chats.length ? (
            <div className="rounded-lg border border-dashed border-border/70 px-3 py-6 text-center text-sm text-muted-foreground">
              {localize(lang, "История пуста", "No history")}
            </div>
          ) : null}
          {chats.map((chat) => {
            const selected = chat.id === activeChatId;
            return (
              <button
                key={chat.id}
                type="button"
                onClick={() => setSearchParams({ chat: String(chat.id) })}
                className={cn(
                  "mb-1 grid w-full min-w-0 grid-cols-[1rem_minmax(0,1fr)] gap-2 rounded-lg px-3 py-2.5 text-left transition-colors",
                  selected
                    ? "bg-secondary/70 text-foreground shadow-[inset_0_0_0_1px_hsl(var(--border))]"
                    : "text-muted-foreground hover:bg-secondary/45 hover:text-foreground",
                )}
              >
                <MessageSquare className="mt-0.5 h-4 w-4 shrink-0" />
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium">{chat.title}</span>
                  <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">
                    {formatDateTime(chat.updated_at, lang)}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      </aside>

      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-border/70 bg-card/55 px-4 backdrop-blur">
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-foreground">{selectedTitle}</h2>
            <p className="truncate text-xs text-muted-foreground">
              {localize(lang, "Ассистент платформы", "Platform assistant")}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="hidden rounded-md border-primary/25 bg-primary/10 text-primary sm:inline-flex">
              <Workflow className="mr-1 h-3 w-3" />
              {localize(lang, "Действия", "Actions")}
            </Badge>
            <Button size="sm" variant="outline" className="lg:hidden" onClick={() => setSearchParams({})}>
              <Plus className="h-4 w-4" />
              {localize(lang, "Новый", "New")}
            </Button>
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5">
          <div className="mx-auto flex w-full max-w-6xl flex-col gap-5">
            {!messages.length && !activeChatQuery.isLoading ? (
              <div className="mx-auto flex w-full max-w-3xl flex-col gap-4 pt-[12vh]">
                <div className="flex items-start gap-3 rounded-lg border border-border/80 bg-card/70 p-4 shadow-sm">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-primary/25 bg-primary/10 text-primary">
                    <Bot className="h-5 w-5" />
                  </div>
                  <div className="min-w-0">
                    <h2 className="text-base font-semibold text-foreground">
                      {localize(lang, "Новый рабочий чат", "New working chat")}
                    </h2>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {prompts.map((prompt) => (
                        <button
                          key={prompt}
                          type="button"
                          onClick={() => setDraft(prompt)}
                          className="rounded-lg border border-border/70 bg-background/55 px-3 py-2 text-left text-xs font-medium text-muted-foreground transition-colors hover:border-primary/35 hover:text-foreground"
                        >
                          {prompt}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            ) : null}

            {activeChatQuery.isLoading ? (
              <div className="flex items-center justify-center gap-2 py-12 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                {localize(lang, "Загрузка чата", "Loading chat")}
              </div>
            ) : null}

            {messages.map((message) => (
              <MessageBubble
                key={message.id}
                message={message}
                actionWorkingId={actionWorkingId}
                onConfirmAction={(actionId) => actionMutation.mutate({ actionId, intent: "confirm" })}
                onCancelAction={(actionId) => actionMutation.mutate({ actionId, intent: "cancel" })}
              />
            ))}

            {isBusy ? (
              <div className="grid grid-cols-[2rem_minmax(0,1fr)] gap-3 text-sm text-muted-foreground">
                <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-primary/20 bg-primary/10 text-primary">
                  <Loader2 className="h-4 w-4 animate-spin" />
                </div>
                <div className="flex h-8 items-center">{localize(lang, "Думаю", "Thinking")}</div>
              </div>
            ) : null}
            <div ref={endRef} />
          </div>
        </div>

        <form
          className="shrink-0 border-t border-border/70 bg-card/70 px-4 py-3 backdrop-blur"
          onSubmit={(event) => {
            event.preventDefault();
            submitMessage();
          }}
        >
          <div className="mx-auto flex max-w-6xl items-end gap-2">
            <Textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
              placeholder={localize(lang, "Напишите задачу для ассистента...", "Write a task for the assistant...")}
              className="max-h-40 min-h-12 resize-none border-border/80 bg-background/85 text-sm"
              disabled={isBusy}
            />
            <Button
              type="submit"
              size="icon"
              className="h-12 w-12 shrink-0"
              disabled={!draft.trim() || isBusy}
              aria-label={localize(lang, "Отправить", "Send")}
              title={localize(lang, "Отправить", "Send")}
            >
              {isBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            </Button>
          </div>
        </form>
      </section>
    </div>
  );
}
