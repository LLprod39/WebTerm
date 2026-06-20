import { useEffect, useMemo, useRef, useState } from "react";
import {
  Bot,
  FileText,
  Footprints,
  Send,
  Settings2,
  Sparkles,
  Square,
  Trash2,
  Wand2,
  X,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import type {
  AiAssistantSettings,
  AiChatMode,
  AiCommand,
  AiExecutionMode,
  AiMessage,
} from "./ai-types";
import { AiMessageRenderer } from "./ai-panel/AiPanelMessages";
import { AiPanelSettingsDialog } from "./ai-panel/AiPanelSettingsDialog";
import { AgentTodoMsg } from "./ai-panel/AgentTimelineMessages";

interface AiPanelProps {
  onClose: () => void;
  onSend: (text: string) => void;
  onStop: () => void;
  onConfirm?: (id: number) => void;
  onCancel?: (id: number) => void;
  onReply?: (qId: string, text: string) => void;
  onClearChat?: () => void;
  onGenerateReport?: (force?: boolean) => void;
  onClearMemory?: () => void;
  // A6: ask the backend to explain a single executed command inline.
  onExplainCommand?: (cmd: AiCommand) => void;
  onSettingsChange: (settings: AiAssistantSettings) => void;
  onSaveDefaults?: () => void;
  onResetToDefaults?: () => void;
  messages: AiMessage[];
  isGenerating: boolean;
  chatMode: AiChatMode;
  onChatModeChange: (mode: AiChatMode) => void;
  executionMode: AiExecutionMode;
  settings: AiAssistantSettings;
  onModeChange: (mode: AiExecutionMode) => void;
}

const quickPrompts = ["Объясни вывод", "Предложи команду", "Проверь синтаксис", "Что означает ошибка"];

const modeConfig: Record<AiExecutionMode, { icon: typeof Zap; label: string; desc: string }> = {
  auto: { icon: Wand2, label: "Авто", desc: "Режим выбирается автоматически" },
  fast: { icon: Zap, label: "Fast", desc: "Быстрый ответ без лишних шагов" },
  step: { icon: Footprints, label: "Step", desc: "Пошаговый и более подробный режим" },
  // Nova: ReAct agent — no pre-plan, picks tools one at a time. Can
  // operate on extra servers (see settings → Agent → Extra targets).
  agent: {
    icon: Sparkles,
    label: "Nova",
    desc: "Агент: сам выбирает инструменты, делает todo-лист, может работать с несколькими серверами",
  },
};

const chatModeConfig: Record<AiChatMode, { label: string; desc: string }> = {
  ask: {
    label: "Ask",
    desc: "Объясняет и предлагает команды. Запуск только после вашего подтверждения.",
  },
  agent: {
    label: "Agent",
    desc: "Сразу запускает безопасные команды в терминале. Опасные действия требуют подтверждения.",
  },
};

export function AiPanel({
  onClose,
  onSend,
  onStop,
  onConfirm,
  onCancel,
  onReply,
  onClearChat,
  onGenerateReport,
  onClearMemory,
  onExplainCommand,
  onSettingsChange,
  onSaveDefaults,
  onResetToDefaults,
  messages,
  isGenerating,
  chatMode,
  onChatModeChange,
  executionMode,
  settings,
  onModeChange,
}: AiPanelProps) {
  const [input, setInput] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isGenerating]);

  // Product decision: Ask/Agent are both exposed. Execution-mode is
  // restricted to Fast + Nova (agent) for now — Auto and Step are
  // hidden from the UI (see EXPOSED_EXECUTION_MODES) until they are
  // ready for users. If a saved setting picked auto/step, fall back
  // to fast so the segmented control still reflects the live mode.
  useEffect(() => {
    if (executionMode !== "fast" && executionMode !== "agent") {
      onModeChange("fast");
    }
  }, [executionMode, onModeChange]);

  // Sticky-todo logic: find the latest agent_todo message and show it
  // pinned to the top of the scroll area while an agent run is active
  // (between agent_start and agent_stopped / agent_done). After the run
  // finishes, we stop pinning so the chronological position in the
  // timeline remains visible during scroll-back.
  const { stickyTodo, stickyTodoId } = useMemo(() => {
    let runActive = false;
    let latestTodo: AiMessage | null = null;
    for (let i = 0; i < messages.length; i += 1) {
      const t = messages[i].type;
      if (t === "agent_start") {
        runActive = true;
        latestTodo = null; // reset — each run has its own todo
      } else if (t === "agent_stopped") {
        runActive = false;
      } else if (t === "agent_todo") {
        latestTodo = messages[i];
      }
    }
    return {
      stickyTodo: runActive ? latestTodo : null,
      stickyTodoId: runActive ? latestTodo?.id : null,
    };
  }, [messages]);

  const canGenerateReport = messages.length > 0 && !isGenerating;

  const updateSettings = (patch: Partial<AiAssistantSettings>) => {
    onSettingsChange({
      ...settings,
      ...patch,
      whitelistPatterns: patch.whitelistPatterns ? [...patch.whitelistPatterns] : [...settings.whitelistPatterns],
      blacklistPatterns: patch.blacklistPatterns ? [...patch.blacklistPatterns] : [...settings.blacklistPatterns],
    });
  };

  const handleSend = (text?: string) => {
    const message = (text || input).trim();
    if (!message) return;
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";
    onSend(message);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSend();
    }
  };

  const handleInput = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(event.target.value);
    event.target.style.height = "auto";
    event.target.style.height = `${Math.min(event.target.scrollHeight, 120)}px`;
  };

  return (
    <>
      <AiPanelSettingsDialog
        open={settingsOpen}
        onOpenChange={setSettingsOpen}
        chatModeControl={<ChatModeSelector mode={chatMode} onChange={onChatModeChange} />}
        executionModeControl={<ModeSelector mode={executionMode} onChange={onModeChange} />}
        settings={settings}
        onSettingsPatch={updateSettings}
        onClearMemory={onClearMemory}
        onSaveDefaults={onSaveDefaults}
        onResetToDefaults={onResetToDefaults}
      />

      <div className="flex h-full flex-col bg-card">
        {/* Header — neutral status dot + workspace label. No loud pills. */}
        <div className="shrink-0 border-b border-border px-3.5 py-2.5">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <div className="flex h-6 w-6 items-center justify-center rounded-md border border-border/50 bg-background/60">
                <Bot className="h-3 w-3 text-muted-foreground" />
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[13px] font-medium text-foreground">AI</span>
                <span className="inline-flex items-center gap-1.5 text-[11px] text-muted-foreground">
                  <span
                    aria-hidden="true"
                    className={`h-1.5 w-1.5 rounded-full ${
                      isGenerating
                        ? "bg-warning animate-pulse"
                        : "bg-success"
                    }`}
                  />
                  {isGenerating ? "думает…" : "готов"}
                </span>
              </div>
            </div>

            <div className="flex items-center gap-0.5">
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="h-9 w-9 text-muted-foreground hover:text-foreground"
                  onClick={() => setSettingsOpen(true)}
                  title="Настройки"
                  aria-label="AI settings"
                >
                <Settings2 className="h-3.5 w-3.5" />
              </Button>

              {isGenerating ? (
                <Button type="button" size="icon" variant="ghost" className="h-9 w-9 text-warning hover:bg-warning/10" onClick={onStop} title="Стоп" aria-label="Stop">
                  <Square className="h-3.5 w-3.5" />
                </Button>
              ) : null}

              {messages.length > 0 ? (
                <Button type="button" size="icon" variant="ghost" className="h-9 w-9 text-muted-foreground hover:text-destructive" onClick={onClearChat} title="Очистить" aria-label="Clear">
                  <Trash2 className="h-3 w-3" />
                </Button>
              ) : null}

              <Button type="button" size="icon" variant="ghost" className="h-9 w-9 text-muted-foreground hover:text-foreground" onClick={onClose} aria-label="Close">
                <X className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </div>

        {/* Compact mode bar — chat behaviour (Ask/Agent) on the left,
            execution style (Fast/Nova) on the right. Dry-run badge sits
            between them only when the safety toggle is on. */}
        <div className="flex shrink-0 items-center justify-between gap-2 border-b border-border/50 px-3.5 py-2">
          <ChatModeSelector mode={chatMode} onChange={onChatModeChange} />
          <div className="flex items-center gap-1.5">
            {settings.dryRun ? (
              <span className="inline-flex items-center rounded border border-warning/40 bg-warning/10 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-warning">
                dry-run
              </span>
            ) : null}
            <ModeSelector mode={executionMode} onChange={onModeChange} />
          </div>
        </div>

        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-3">
          {stickyTodo ? (
            <div className="sticky top-0 z-10 -mx-3 -mt-3 mb-1 border-b border-border/40 bg-background/95 px-3 pt-2 pb-2 backdrop-blur">
              <AgentTodoMsg msg={stickyTodo} />
            </div>
          ) : null}
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center space-y-5 py-8 text-center">
              <div className="flex h-10 w-10 items-center justify-center rounded-md border border-border/60 bg-background/40">
                <Sparkles className="h-4 w-4 text-muted-foreground" />
              </div>
              <div className="space-y-1">
                <p className="text-[13px] font-medium text-foreground">Чем могу помочь?</p>
                <p className="text-[12px] leading-relaxed text-muted-foreground">
                  Задайте вопрос о терминале, сервере или текущем выводе.
                </p>
              </div>
              <div className="flex flex-wrap justify-center gap-1.5">
                {quickPrompts.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => handleSend(prompt)}
                    className="min-h-8 rounded-md border border-border/60 bg-background/40 px-3 py-1.5 text-[12px] text-muted-foreground transition-colors hover:border-border hover:bg-secondary/60 hover:text-foreground"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            (() => {
              // Hide the currently-sticky todo from the inline list so
              // it doesn't render twice. Keep prev/next neighbour
              // detection correct by computing flags against the
              // filtered list.
              const visible = stickyTodoId
                ? messages.filter((m) => m.id !== stickyTodoId)
                : messages;
              return visible.map((message, idx) => {
                // Mark first/last in a contiguous run of agent messages
                // so the TimelineRow clips the vertical line at the ends.
                const isAgent = (message.type || "").startsWith("agent_");
                const prev = idx > 0 ? visible[idx - 1] : null;
                const next = idx < visible.length - 1 ? visible[idx + 1] : null;
                const prevIsAgent = !!prev && (prev.type || "").startsWith("agent_");
                const nextIsAgent = !!next && (next.type || "").startsWith("agent_");
                return (
                  <AiMessageRenderer
                    key={message.id}
                    msg={message}
                    settings={settings}
                    onConfirm={onConfirm}
                    onCancel={onCancel}
                    onReply={onReply}
                    onExplainCommand={onExplainCommand}
                    isFirstAgent={isAgent && !prevIsAgent}
                    isLastAgent={isAgent && !nextIsAgent}
                  />
                );
              });
            })()
          )}

          {isGenerating ? (
            <div className="flex items-center gap-2 px-0.5 py-1 text-[11px] text-muted-foreground">
              <div className="flex gap-1">
                {[0, 150, 300].map((delay) => (
                  <span
                    key={delay}
                    className="h-1 w-1 animate-bounce rounded-full bg-muted-foreground/60"
                    style={{ animationDelay: `${delay}ms` }}
                  />
                ))}
              </div>
              <span>думает…</span>
            </div>
          ) : null}

          <div ref={messagesEndRef} />
        </div>

        <div className="shrink-0 border-t border-border p-2">
          {messages.length > 0 ? (
            <div className="mb-1.5 flex items-center justify-between gap-2 rounded-md border border-border/50 bg-background/40 px-2.5 py-1.5">
              <span className="text-[11px] text-muted-foreground">Сформировать отчёт</span>
              <Button type="button" size="xs" variant="ghost" onClick={() => onGenerateReport?.(false)} disabled={!canGenerateReport} className="h-8 gap-1 px-2">
                <FileText className="h-3 w-3" />
                Отчёт
              </Button>
            </div>
          ) : null}

          <div className="flex items-end gap-1.5">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={handleInput}
              onKeyDown={handleKeyDown}
              aria-label="AI message"
              placeholder="Сообщение… (Enter — отправить)"
              rows={1}
              className="min-h-10 max-h-[120px] flex-1 resize-none rounded-md border border-border bg-background/60 px-3 py-2 text-[13px] text-foreground transition-colors placeholder:text-muted-foreground/50 focus:border-primary/60 focus:bg-background focus:outline-none"
            />
            <Button
              type="button"
              size="icon"
              onClick={() => handleSend()}
              disabled={!input.trim() || isGenerating}
              className="h-10 w-10 shrink-0 rounded-md"
              aria-label="Send"
            >
              <Send className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </div>
    </>
  );
}
