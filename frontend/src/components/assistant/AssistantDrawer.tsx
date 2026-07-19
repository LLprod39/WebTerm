import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { ExternalLink, Loader2, Send, Sparkles, X } from "lucide-react";

import {
  createAssistantChat,
  fetchAssistantChat,
  fetchAssistantChats,
  sendAssistantChatMessage,
  type AssistantChatMessage,
} from "@/api";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { notify } from "@/lib/notify";

import { useAssistantShell } from "./assistantContext";

const DRAWER_CHAT_KEY = "operator_drawer_chat_id";

function contextSystemLine(
  pageContext: ReturnType<typeof useAssistantShell>["pageContext"],
  lang: "ru" | "en",
): string {
  const bits: string[] = [];
  bits.push(localize(lang, `Контекст страницы: ${pageContext.surface}`, `Page context: ${pageContext.surface}`));
  if (pageContext.entity?.serverId) {
    bits.push(
      localize(
        lang,
        `сервер #${pageContext.entity.serverId}${pageContext.entity.serverName ? ` (${pageContext.entity.serverName})` : ""}`,
        `server #${pageContext.entity.serverId}${pageContext.entity.serverName ? ` (${pageContext.entity.serverName})` : ""}`,
      ),
    );
  }
  if (pageContext.entity?.runId) {
    bits.push(localize(lang, `прогон #${pageContext.entity.runId}`, `run #${pageContext.entity.runId}`));
  }
  if (pageContext.entity?.agentName) {
    bits.push(localize(lang, `агент ${pageContext.entity.agentName}`, `agent ${pageContext.entity.agentName}`));
  }
  return bits.join(" · ");
}

function buildContextPrefix(
  pageContext: ReturnType<typeof useAssistantShell>["pageContext"],
  lang: "ru" | "en",
): string {
  const lines = [
    localize(
      lang,
      "[Контекст UI — не отвечай на это отдельно, учти при ответе]",
      "[UI context — do not answer this separately; use it for your reply]",
    ),
    contextSystemLine(pageContext, lang),
  ];
  return `${lines.join("\n")}\n\n`;
}

export function AssistantDrawer() {
  const { lang } = useI18n();
  const queryClient = useQueryClient();
  const { open, setOpen, pageContext, seedPrompt, consumeSeedPrompt } = useAssistantShell();
  const [draft, setDraft] = useState("");
  const [chatId, setChatId] = useState<number | null>(() => {
    try {
      const saved = Number(localStorage.getItem(DRAWER_CHAT_KEY) || 0);
      return saved > 0 ? saved : null;
    } catch {
      return null;
    }
  });
  const [pendingUser, setPendingUser] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (!chatId) return;
    try {
      localStorage.setItem(DRAWER_CHAT_KEY, String(chatId));
    } catch {
      // ignore
    }
  }, [chatId]);

  const chatQuery = useQuery({
    queryKey: ["assistant", "chat", chatId, "drawer"],
    queryFn: () => fetchAssistantChat(chatId as number),
    enabled: open && Boolean(chatId),
    staleTime: 8_000,
  });

  const messages: AssistantChatMessage[] = chatQuery.data?.messages ?? [];

  useEffect(() => {
    if (!open) return;
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [open, messages.length, pendingUser]);

  useEffect(() => {
    if (!open) return;
    const seed = consumeSeedPrompt();
    if (seed) {
      setDraft(seed);
      window.setTimeout(() => textareaRef.current?.focus(), 50);
    } else {
      window.setTimeout(() => textareaRef.current?.focus(), 50);
    }
  }, [open, consumeSeedPrompt, seedPrompt]);

  const sendMutation = useMutation({
    mutationFn: async (text: string) => {
      const prefix = buildContextPrefix(pageContext, lang);
      const message = `${prefix}${text}`;
      if (chatId) {
        return sendAssistantChatMessage(chatId, message);
      }
      // Prefer existing chat list head if we have none stored
      const list = await fetchAssistantChats().catch(() => null);
      const existing = list?.chats?.[0]?.id;
      if (existing) {
        setChatId(existing);
        return sendAssistantChatMessage(existing, message);
      }
      const created = await createAssistantChat(
        localize(lang, "Ассистент (панель)", "Assistant (drawer)"),
      );
      setChatId(created.id);
      return sendAssistantChatMessage(created.id, message);
    },
    onSuccess: (data) => {
      setPendingUser(null);
      if (data.chat?.id) setChatId(data.chat.id);
      void queryClient.invalidateQueries({ queryKey: ["assistant", "chat", data.chat?.id] });
      void queryClient.invalidateQueries({ queryKey: ["assistant", "chats"] });
    },
    onError: (error) => {
      setPendingUser(null);
      notify.error({
        title: localize(lang, "Не удалось отправить", "Failed to send"),
        description: error instanceof Error ? error.message : undefined,
      });
    },
  });

  const submit = useCallback(() => {
    const text = draft.trim();
    if (!text || sendMutation.isPending) return;
    setPendingUser(text);
    setDraft("");
    sendMutation.mutate(text);
  }, [draft, sendMutation]);

  const chips = pageContext.chips ?? [];

  const emptyHint = useMemo(
    () =>
      localize(
        lang,
        "Ассистент видит текущую страницу. Задайте вопрос или выберите подсказку.",
        "The assistant sees the current page. Ask a question or pick a suggestion.",
      ),
    [lang],
  );

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent
        side="right"
        className="flex w-full flex-col gap-0 p-0 sm:max-w-md"
      >
        <SheetHeader className="space-y-1 border-b border-border px-4 py-3 text-left">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <SheetTitle className="flex items-center gap-2 text-base">
                <Sparkles className="h-4 w-4 text-primary" />
                {localize(lang, "Ассистент", "Assistant")}
              </SheetTitle>
              <p className="mt-1 truncate text-xs text-muted-foreground">
                {contextSystemLine(pageContext, lang)}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <Button variant="ghost" size="sm" className="h-8 px-2 text-xs" asChild>
                <Link to={chatId ? `/chat?chat=${chatId}` : "/chat"} onClick={() => setOpen(false)}>
                  <ExternalLink className="mr-1 h-3.5 w-3.5" />
                  {localize(lang, "Полный чат", "Full chat")}
                </Link>
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="h-8 w-8"
                onClick={() => setOpen(false)}
                aria-label={localize(lang, "Закрыть", "Close")}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </SheetHeader>

        {chips.length > 0 ? (
          <div className="flex flex-wrap gap-1.5 border-b border-border px-4 py-2.5">
            {chips.map((chip) => (
              <button
                key={chip.id}
                type="button"
                className={cn(
                  "rounded-full border border-border bg-surface-1 px-2.5 py-1 text-[11px] font-medium",
                  "text-muted-foreground transition-colors hover:border-border-strong hover:text-foreground",
                )}
                onClick={() => {
                  setDraft(localize(lang, chip.promptRu, chip.promptEn));
                  textareaRef.current?.focus();
                }}
              >
                {localize(lang, chip.labelRu, chip.labelEn)}
              </button>
            ))}
          </div>
        ) : null}

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-4">
          {chatQuery.isLoading && chatId ? (
            <div className="flex items-center justify-center gap-2 py-10 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              {localize(lang, "Загрузка…", "Loading…")}
            </div>
          ) : null}

          {!chatId && !pendingUser && messages.length === 0 ? (
            <div className="workspace-empty rounded-lg border border-dashed border-border px-4 py-8 text-center text-sm text-muted-foreground">
              {emptyHint}
            </div>
          ) : null}

          {messages
            .filter((m) => m.role !== "system")
            .map((message) => (
              <div
                key={message.id}
                className={cn(
                  "rounded-lg border px-3 py-2.5 text-sm leading-6",
                  message.role === "user"
                    ? "ml-6 border-primary/25 bg-primary/10 text-foreground"
                    : "mr-2 border-border bg-card text-foreground",
                )}
              >
                <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                  {message.role === "user"
                    ? localize(lang, "Вы", "You")
                    : localize(lang, "Ассистент", "Assistant")}
                </div>
                <div className="whitespace-pre-wrap break-words">{stripContextPrefix(message.content)}</div>
              </div>
            ))}

          {pendingUser ? (
            <div className="ml-6 rounded-lg border border-primary/25 bg-primary/10 px-3 py-2.5 text-sm leading-6">
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                {localize(lang, "Вы", "You")}
              </div>
              <div className="whitespace-pre-wrap break-words">{pendingUser}</div>
            </div>
          ) : null}

          {sendMutation.isPending ? (
            <div className="mr-2 flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-2.5 text-sm text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              {localize(lang, "Думаю…", "Thinking…")}
            </div>
          ) : null}

          <div ref={endRef} />
        </div>

        <div className="border-t border-border p-3">
          <div className="flex items-end gap-2">
            <Textarea
              ref={textareaRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={localize(lang, "Спросите что угодно…", "Ask anything…")}
              className="min-h-[44px] max-h-32 resize-none text-sm"
              rows={2}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  submit();
                }
              }}
            />
            <Button
              type="button"
              size="icon"
              className="h-10 w-10 shrink-0"
              disabled={!draft.trim() || sendMutation.isPending}
              onClick={submit}
              aria-label={localize(lang, "Отправить", "Send")}
            >
              {sendMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
          <p className="mt-1.5 text-[10px] text-muted-foreground">
            {localize(lang, "Enter — отправить · Shift+Enter — новая строка", "Enter to send · Shift+Enter for newline")}
          </p>
        </div>
      </SheetContent>
    </Sheet>
  );
}

function stripContextPrefix(content: string): string {
  if (!content.startsWith("[") && !content.includes("[Контекст UI") && !content.includes("[UI context")) {
    return content;
  }
  const split = content.split(/\n\n/);
  if (split.length < 2) return content;
  // Drop first block if it looks like our context prefix
  if (split[0].includes("Контекст") || split[0].includes("UI context") || split[0].includes("Page context")) {
    return split.slice(1).join("\n\n");
  }
  return content;
}

