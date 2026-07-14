import { useMutation } from "@tanstack/react-query";
import { Loader2, MessageSquare, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { startAssistantChat, type AssistantChatMessage } from "@/api/assistant-chat";
import { Button } from "@/components/ui/button";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

type LocalMsg = { role: "user" | "assistant" | "system"; content: string };

export function KubernetesAgentDrawer({
  open,
  onClose,
  contextHint,
}: {
  open: boolean;
  onClose: () => void;
  contextHint?: string;
}) {
  const { lang } = useI18n();
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<LocalMsg[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open && messages.length === 0 && contextHint) {
      setMessages([
        {
          role: "system",
          content: localize(
            lang,
            `Контекст Kubernetes: ${contextHint}. Задай вопрос или опиши задачу (диагностика, rollout, Helm ownership).`,
            `Kubernetes context: ${contextHint}. Ask a question or describe a task (diagnosis, rollout, Helm ownership).`,
          ),
        },
      ]);
    }
  }, [open, contextHint, lang, messages.length]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, open]);

  const sendMutation = useMutation({
    mutationFn: async (text: string) => {
      const prefix = contextHint
        ? `[Kubernetes Ops] Context: ${contextHint}\n\nOperator: ${text}`
        : `[Kubernetes Ops]\n\nOperator: ${text}`;
      return startAssistantChat(prefix);
    },
    onSuccess: (res) => {
      const assistant = res.assistant_message;
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: assistant?.content || localize(lang, "(пустой ответ)", "(empty reply)"),
        },
      ]);
    },
    onError: (err) => {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content:
            err instanceof Error
              ? err.message
              : localize(lang, "Не удалось получить ответ ассистента", "Assistant request failed"),
        },
      ]);
    },
  });

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" role="dialog" aria-modal="true">
      <button type="button" className="h-full flex-1 cursor-default" aria-label="Close" onClick={onClose} />
      <aside className="flex h-full w-full max-w-md flex-col border-l border-border bg-card shadow-elev-3">
        <header className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="flex items-center gap-2">
            <MessageSquare className="h-4 w-4 text-ai" />
            <div>
              <div className="font-display text-sm font-semibold text-foreground">
                {localize(lang, "K8s агент", "K8s agent")}
              </div>
              <div className="text-2xs text-muted-foreground">
                {localize(lang, "Inline · assistant chat", "Inline · assistant chat")}
              </div>
            </div>
          </div>
          <Button type="button" size="icon" variant="ghost" className="h-8 w-8" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </header>

        <div className="flex-1 space-y-3 overflow-y-auto px-4 py-3">
          {messages.map((m, i) => (
            <div
              key={`${m.role}-${i}`}
              className={cn(
                "rounded-sm border px-3 py-2 text-xs leading-relaxed",
                m.role === "user"
                  ? "ml-6 border-primary/30 bg-primary/10 text-foreground"
                  : m.role === "system"
                    ? "border-border bg-secondary/30 text-muted-foreground"
                    : "mr-4 border-border bg-surface-0 text-foreground",
              )}
            >
              {m.content}
            </div>
          ))}
          {sendMutation.isPending ? (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              {localize(lang, "Думаю…", "Thinking…")}
            </div>
          ) : null}
          <div ref={bottomRef} />
        </div>

        <footer className="border-t border-border p-3">
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              const text = input.trim();
              if (!text || sendMutation.isPending) return;
              setMessages((prev) => [...prev, { role: "user", content: text }]);
              setInput("");
              sendMutation.mutate(text);
            }}
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={localize(lang, "Спроси про кластер…", "Ask about the cluster…")}
              className="h-10 flex-1 rounded-sm border border-border bg-surface-0 px-3 font-mono text-xs outline-none focus:ring-2 focus:ring-primary/40"
            />
            <Button type="submit" size="sm" className="h-10" disabled={!input.trim() || sendMutation.isPending}>
              {localize(lang, "Отпр.", "Send")}
            </Button>
          </form>
          <div className="mt-2 text-2xs text-muted-foreground">
            <Link to="/chat" className="underline hover:text-foreground">
              {localize(lang, "Полный чат", "Full chat")}
            </Link>
            {" · "}
            <Link to="/agents" className="underline hover:text-foreground">
              Agents
            </Link>
          </div>
        </footer>
      </aside>
    </div>
  );
}

export type { AssistantChatMessage };
